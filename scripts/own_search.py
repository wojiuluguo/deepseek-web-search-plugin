#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Own Search Engine — 真正的“自己的搜索引擎”（本地独立索引版）

这不是简单的“把多个搜索引擎结果拼在一起”，而是：
1. 自己抓取网页；
2. 自己建立本地索引（SQLite）；
3. 自己排序返回结果。

外部搜索引擎只用于“发现种子 URL”（seed 模式），真正的搜索结果来自本地索引。

用法：
    # 手动收录一个网页
    python own_search.py add --url "https://example.com" --title "Example"

    # 抓取一个网页进索引（遇到反爬自动用 Playwright，也可 --force-browser 强制）
    python own_search.py crawl --url "https://example.com"
    python own_search.py crawl --url "https://example.com" --force-browser

    # 用外部搜索发现一批网页，然后抓进自己的索引
    python own_search.py seed --query "OpenClaw skills" --max-results 5

    # 浏览器版发现（更防反爬）
    python own_search.py seed --query "DeepSeek" --browser --max-results 5

    # 在自己索引里搜索
    python own_search.py search --query "OpenClaw" --json

    # 下载视频/音频/图片（嵌套自动保存浏览器）
    python own_search.py download --url "https://v.douyin.com/xxxx"
    python own_search.py download --query "抖音 猫 视频"
"""

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_DIR = BASE_DIR / "index"
DB_PATH = INDEX_DIR / "own_search.db"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en']
});
"""


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.text_parts = []
        self.skip_depth = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip_depth > 0:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.in_title:
            self.title += data
        else:
            self.text_parts.append(data)

    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.text_parts)).strip()


def extract_html(raw: bytes, encoding: str = "utf-8") -> tuple:
    text = raw.decode(encoding, "ignore")
    parser = TextExtractor()
    try:
        parser.feed(text)
    except Exception:
        pass
    return parser.title.strip(), parser.text()


def fetch(url: str, timeout: int = 10):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        content_type = resp.headers.get("Content-Type", "")
    enc = "utf-8"
    if "gb" in content_type.lower() or "gb2312" in content_type.lower():
        enc = "gb18030"
    return raw, enc


def _fetch_with_playwright(url: str, timeout: int = 15):
    """Playwright fallback for anti-bot sites (e.g. Baidu Baike returns 403 to urllib)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Playwright not installed; cannot fallback for anti-bot page")
    # 复用 auto_save_browser 的自适应渲染等待：SPA 页等到内容挂载，静态页零等待
    # （替代旧的固定睡 1.5s：慢 SPA 爬到空白页，静态页白等 2.3s）
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from auto_save_browser import _wait_for_render
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1366, "height": 900},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
            )
            context.add_init_script(STEALTH_JS)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            # JS 渲染等待：正文≥50字符或媒体≥3个即就绪（每轮滚动触发懒加载）
            _wait_for_render(page)
            # 兜底滚一次到底，触发剩余懒加载
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(800)
            except Exception:
                pass
            html = page.content()
            return html.encode("utf-8"), "utf-8"
        finally:
            if browser is not None:
                browser.close()


def tokenize(text: str) -> List[str]:
    """Simple tokenizer: English words + Chinese unigrams."""
    tokens = []
    for m in re.finditer(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower()):
        tokens.append(m.group(0))
    return tokens


def get_db():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            text TEXT,
            fetched_at REAL,
            source TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS terms (
            term TEXT,
            page_id INTEGER,
            count INTEGER,
            PRIMARY KEY (term, page_id)
        )
        """
    )
    conn.commit()
    return conn


def add_page(conn, url: str, title: str, text: str, source: str = "manual") -> int:
    cur = conn.execute("SELECT id FROM pages WHERE url = ?", (url,))
    row = cur.fetchone()
    if row:
        page_id = row[0]
        conn.execute(
            "UPDATE pages SET title = ?, text = ?, fetched_at = ?, source = ? WHERE id = ?",
            (title, text, time.time(), source, page_id),
        )
        conn.execute("DELETE FROM terms WHERE page_id = ?", (page_id,))
    else:
        cur = conn.execute(
            "INSERT INTO pages (url, title, text, fetched_at, source) VALUES (?, ?, ?, ?, ?)",
            (url, title, text, time.time(), source),
        )
        page_id = cur.lastrowid

    counts: Dict[str, int] = {}
    for tok in tokenize(f"{title}\n{text}"):
        counts[tok] = counts.get(tok, 0) + 1
    conn.executemany(
        "INSERT OR REPLACE INTO terms (term, page_id, count) VALUES (?, ?, ?)",
        [(t, page_id, c) for t, c in counts.items()],
    )
    conn.commit()
    return page_id


def search_index(conn, query: str, limit: int = 10):
    terms = tokenize(query)
    if not terms:
        return []
    rows = conn.execute("SELECT id, url, title, text FROM pages").fetchall()
    scored = []
    for pid, url, title, text in rows:
        text_l = (text or "").lower()
        title_l = (title or "").lower()
        url_l = (url or "").lower()
        score = 0.0
        for t in terms:
            score += text_l.count(t)
            if t in title_l:
                score += 5.0 * title_l.count(t)
            if t in url_l:
                score += 2.0 * url_l.count(t)
        if score > 0:
            scored.append(
                {
                    "score": round(score, 2),
                    "url": url,
                    "title": title,
                    "snippet": text[:300],
                }
            )
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


def cmd_add(args):
    conn = get_db()
    text = ""
    if args.content:
        text = args.content
    elif args.content_file:
        text = Path(args.content_file).read_text(encoding="utf-8", errors="ignore")
    add_page(conn, args.url, args.title or args.url, text, source=args.source)
    conn.close()
    print(json.dumps({"ok": True, "url": args.url, "title": args.title or args.url}, ensure_ascii=False))
    return 0


def cmd_crawl(args):
    conn = get_db()
    try:
        if getattr(args, "force_browser", False):
            print("[crawl] 使用 Playwright 浏览器抓取", file=sys.stderr)
            raw, enc = _fetch_with_playwright(args.url, timeout=args.timeout)
        else:
            try:
                raw, enc = fetch(args.url, timeout=args.timeout)
            except Exception as exc:
                print(f"[crawl] urllib 失败({exc})，改用 Playwright 浏览器抓取", file=sys.stderr)
                raw, enc = _fetch_with_playwright(args.url, timeout=args.timeout)
    except Exception as exc:
        conn.close()
        print(json.dumps({"ok": False, "url": args.url, "error": f"抓取失败: {exc}"}, ensure_ascii=False))
        return 1
    title, text = extract_html(raw, enc)
    add_page(conn, args.url, title or args.url, text, source="crawl")
    conn.close()
    print(json.dumps({"ok": True, "url": args.url, "title": title, "chars": len(text)}, ensure_ascii=False))
    return 0


def cmd_download(args):
    """Download video/audio/image through the built-in auto-save browser."""
    script = BASE_DIR / "scripts" / "auto_save_browser.py"
    cmd = [sys.executable, str(script), "--json"]
    if args.url:
        cmd += ["--url", args.url]
    elif args.query:
        cmd += ["--query", args.query, "--auto"]
    if args.output_dir:
        cmd += ["--output-dir", args.output_dir]
    if getattr(args, "safe", False):
        cmd.append("--safe")
    if getattr(args, "method", ""):
        cmd += ["--method", args.method]
    if getattr(args, "cookies", ""):
        cmd += ["--cookies", args.cookies]
    if getattr(args, "cookies_from_browser", ""):
        cmd += ["--cookies-from-browser", args.cookies_from_browser]
    try:
        # 大文件+chain 多路兜底可能很久，给 30 分钟上限防挂死
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="ignore", timeout=1800)
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "error": "下载超时(>1800s)，已中止"}, ensure_ascii=False))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"下载进程异常: {exc}"}, ensure_ascii=False))
        return 1
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return proc.returncode


def cmd_seed(args):
    """Use external search only to discover seed URLs, then crawl into our own index."""
    script = BASE_DIR / "scripts" / ("search_browser.py" if args.browser else "search.py")
    cmd = [
        sys.executable,
        str(script),
        "--query",
        args.query,
        "--max-results",
        str(args.max_results),
        "--json",
    ]
    try:
        # 浏览器版搜索最坏 ~240s，给 300s 上限防挂死
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="ignore", timeout=300)
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "error": "外部搜索超时(>300s)，种子发现中止"}, ensure_ascii=False))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"搜索进程异常: {exc}"}, ensure_ascii=False))
        return 1
    try:
        data = json.loads(proc.stdout)
    except Exception:
        print(json.dumps({"ok": False, "error": "外部搜索输出无法解析", "stderr": proc.stderr[-500:]}, ensure_ascii=False))
        return 1

    conn = get_db()
    added = []
    for r in data.get("results", []):
        url = r.get("url", "")
        if not url:
            continue
        try:
            if getattr(args, "force_browser", False):
                raw, enc = _fetch_with_playwright(url, timeout=args.timeout)
            else:
                try:
                    raw, enc = fetch(url, timeout=args.timeout)
                except Exception as exc:
                    print(f"[seed] urllib 失败({exc})，改用 Playwright 抓取 {url}", file=sys.stderr)
                    raw, enc = _fetch_with_playwright(url, timeout=args.timeout)
            title, text = extract_html(raw, enc)
            add_page(conn, url, title or r.get("title", ""), text, source="seed")
            added.append({"url": url, "title": title or r.get("title", "")})
        except Exception as exc:
            print(f"[seed] 抓取失败 {url}: {exc}", file=sys.stderr)
    conn.close()
    print(json.dumps({"ok": True, "query": args.query, "added": added, "count": len(added)}, ensure_ascii=False))
    return 0


def cmd_search(args):
    conn = get_db()
    results = search_index(conn, args.query, limit=args.limit)
    conn.close()
    if args.json:
        print(json.dumps({"query": args.query, "results": results, "count": len(results)}, ensure_ascii=False))
    else:
        if not results:
            print("本地索引中没有匹配结果。先用 seed 或 crawl 收录网页。")
        for i, r in enumerate(results, 1):
            print(f"{i}. {r['title']}  (score={r['score']})")
            print(f"   URL: {r['url']}")
            print(f"   {r['snippet']}")
            print()
    return 0


def cmd_stats(args):
    conn = get_db()
    pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    terms = conn.execute("SELECT COUNT(DISTINCT term) FROM terms").fetchone()[0]
    conn.close()
    print(json.dumps({"pages": pages, "unique_terms": terms, "db": str(DB_PATH)}, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Own Search Engine - 本地独立索引搜索引擎")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="手动添加网页/文本")
    p_add.add_argument("--url", required=True)
    p_add.add_argument("--title", default="")
    p_add.add_argument("--content", default="")
    p_add.add_argument("--content-file", default="")
    p_add.add_argument("--source", default="manual")
    p_add.set_defaults(func=cmd_add)

    p_crawl = sub.add_parser("crawl", help="抓取单个网页进索引")
    p_crawl.add_argument("--url", required=True)
    p_crawl.add_argument("--timeout", type=int, default=10)
    p_crawl.add_argument("--force-browser", action="store_true", help="强制用 Playwright 浏览器抓取（反爬站）")
    p_crawl.set_defaults(func=cmd_crawl)

    p_download = sub.add_parser("download", help="下载视频/音频/图片（嵌套自动保存浏览器）")
    p_download.add_argument("--url", default="", help="直接下载该链接中的媒体")
    p_download.add_argument("--query", default="", help="搜索并自动下载第一个视频类结果")
    p_download.add_argument("--output-dir", default="", help="保存目录")
    p_download.add_argument("--safe", action="store_true", help="安全模式：沙箱+拦截挖矿/危险文件+落盘白名单（可疑站点用）")
    p_download.add_argument("--method", default="", help="下载方法：chain(多路兜底)/direct/browser/cache/ytdlp/auto/harvest/files/text（默认自动选路）")
    p_download.add_argument("--cookies", default="", help="Netscape cookies.txt 路径，登录墙站点（抖音/B站）带登录态下载")
    p_download.add_argument("--cookies-from-browser", default="", choices=["chrome", "edge", "firefox"], help="直接读本机浏览器登录 cookie（免导出）")
    p_download.set_defaults(func=cmd_download)

    p_seed = sub.add_parser("seed", help="用外部搜索发现URL，再抓进自己的索引")
    p_seed.add_argument("--query", required=True)
    p_seed.add_argument("--max-results", type=int, default=5)
    p_seed.add_argument("--browser", action="store_true", help="用浏览器版搜索发现URL")
    p_seed.add_argument("--force-browser", action="store_true", help="抓取网页时强制用 Playwright 浏览器")
    p_seed.add_argument("--timeout", type=int, default=10)
    p_seed.set_defaults(func=cmd_seed)

    p_search = sub.add_parser("search", help="在本地自己的索引里搜索")
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_stats = sub.add_parser("stats", help="查看索引统计")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
