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

    # 局域网搜索：发现局域网设备/服务/共享并入索引（只读探测，限私网段）
    python own_search.py lan
    python own_search.py lan --hosts 192.168.31.1 --json
    python own_search.py search --query "路由器"

    # 下载视频/音频/图片（嵌套自动保存浏览器）
    python own_search.py download --url "https://v.douyin.com/xxxx"
    python own_search.py download --query "抖音 猫 视频"
"""

import argparse
import ipaddress
import json
import re
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_DIR = BASE_DIR / "index"
DB_PATH = INDEX_DIR / "own_search.db"

# ---- 归一（v1.22.0 批 E）：搜索子进程调用/超时统一到 searchkit.runner ----
sys.path.insert(0, str(Path(__file__).resolve().parent))
from searchkit.runner import run_search_cli, child_env  # noqa: E402

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


def _require_http_url(url: str) -> None:
    """v1.25.1 审计修复（质疑②·高·安全）：URL scheme 白名单。
    stdlib urlopen 原生支持 file://（读本地文件）/ftp:// 等——此前
    `crawl --url file:///C:/windows/win.ini` 会把本地文件读进索引。
    本工具只爬万维网页面，非 http(s) 一律拒绝。"""
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"拒绝非 http(s) URL（防 file:// 等读本地资源）: {url[:120]}")


def fetch(url: str, timeout: int = 10):
    _require_http_url(url)  # v1.25.1：入口白名单（crawl/add/download 三线共用本函数）
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
    _require_http_url(url)  # v1.25.1：兜底层同挡（cmd_crawl 的 except 会吞 fetch 的
    # ValueError 转这里，playwright goto file:// 同样能读本地文件——双保险缺一不可）
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
    # S2 净化（2026-10-15，BUGS.md 同步）：爬取的网页文本入库前剥离隐形/控制字符
    # （零宽/双向符/Tag 块可从任意网页进索引再进输出）——库里永远干净，出口零负担
    from searchkit.sanitize import _clean_line, _CTRL_RE, _INVISIBLE_RE
    title = _CTRL_RE.sub("", _INVISIBLE_RE.sub("", title or "")).strip()
    text = "\n".join(_clean_line(l) for l in (text or "").split("\n"))
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
                              encoding="utf-8", errors="ignore", timeout=1800,
                              env=child_env())  # S6：子进程强制 UTF-8（防 GBK 管道崩溃）
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
    env = run_search_cli(args.query, browser=args.browser, max_results=args.max_results,
                         ad_filter=getattr(args, "ad_filter", "medium"))
    if env["timed_out"]:
        print(json.dumps({"ok": False, "error": f"外部搜索超时(>{env['timeout_sec']}s)，种子发现中止"}, ensure_ascii=False))
        return 1
    if not env["ok"]:
        print(json.dumps({"ok": False, "error": f"搜索进程异常: {env['error']}", "stderr": env["stderr"][-500:]}, ensure_ascii=False))
        return 1
    data = env["data"]

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


# ---- 局域网搜索（v1.25.0 新增）：发现局域网设备/服务/共享并纳入本地索引 ----
# 设计边界（安全第一，全部只读探测）：
# 1. 只扫 RFC1918 私网段（10./172.16-31./192.168.），非私网直接拒绝——杜绝误扫公网；
# 2. 只做无副作用探测：TCP connect 探端口、HTTP GET 拿标题/Server 头、
#    FTP 读 220 banner、SMB 用 `net view` 列共享名（Windows 自带只读枚举）；
# 3. 不尝试任何登录/写入/利用，发现的资源入 own_search 索引（source="lan"），
#    之后用 `search` 子命令即可搜到（与公网页面同一套索引与排序）。
# 纯 stdlib（socket/subprocess/ipaddress），与项目零依赖风格一致。

# 常见服务端口 → (协议, 服务名)。命中即按协议做对应识别。
LAN_PORT_TABLE = {
    80: ("http", "HTTP"), 443: ("https", "HTTPS"),
    8080: ("http", "HTTP-Alt"), 8000: ("http", "HTTP-Dev"),
    8081: ("http", "HTTP-Alt2"), 5000: ("http", "NAS/Synology"),
    32400: ("http", "Plex"), 8096: ("http", "Jellyfin"),
    9200: ("http", "Elasticsearch"), 8384: ("http", "Syncthing"),
    445: ("smb", "SMB"), 21: ("ftp", "FTP"),
}


def _local_ip() -> str:
    """本机出口 IP（UDP connect 技巧，不发任何包）。拿不到返回空。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.255.255", 1))  # 目标不可达也无妨，只为拿路由出口
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def _tcp_probe(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_identify(scheme: str, host: str, port: int, timeout: float) -> Dict[str, str]:
    """GET 首页拿 <title> + Server 头（自签 HTTPS 容忍；失败返回空标记）。"""
    url = f"{scheme}://{host}:{port}/" if port not in (80, 443) else f"{scheme}://{host}/"
    info = {"url": url, "title": "", "server": ""}
    try:
        ctx = ssl._create_unverified_context() if scheme == "https" else None
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Connection": "close"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read(65536).decode("utf-8", "ignore")
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
            info["title"] = re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""
            info["server"] = (resp.headers.get("Server") or "")[:60]
    except Exception as exc:
        info["error"] = str(exc)[:60]
    return info


def _smb_shares(host: str, timeout: float = 8.0) -> List[str]:
    """Windows `net view` 只读枚举 SMB 共享名（不登录不写）。非 Windows/失败返回空。"""
    if sys.platform != "win32":
        return []
    try:
        # net view 输出跟随系统 locale（中文 Windows=GBK），text=True 默认 locale 解码正确；
        # 不按项目 ffmpeg 的 utf-8 规则来——那是给 ffmpeg 的，net 工具是 GBK 输出
        r = subprocess.run(["net", "view", f"\\\\{host}"], capture_output=True,
                           text=True, timeout=timeout)
        lines = r.stdout.splitlines()
        out, in_table = [], False
        for line in lines:
            if set(line.strip()) <= {"-"} and line.strip():
                in_table = True
                continue
            if in_table:
                if "命令成功完成" in line or "successfully" in line.lower():
                    break
                name = line.split()[0] if line.split() else ""
                if name and not name.startswith("\\\\"):
                    out.append(name)
        return out[:20]
    except Exception:
        return []


def _ftp_banner(host: str, port: int, timeout: float) -> str:
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            data = s.recv(128)
            return data.decode("utf-8", "ignore").strip()[:80]
    except OSError:
        return ""


def cmd_lan(args) -> int:
    """lan 子命令：扫描局域网 → 识别服务 → 入索引（source="lan"）。"""
    local_ip = _local_ip()
    if not local_ip:
        print(json.dumps({"error": "无法获取本机出口 IP（无网络接口？）"}, ensure_ascii=False))
        return 1
    try:
        net = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    except ValueError:
        print(json.dumps({"error": f"IP 解析失败: {local_ip}"}, ensure_ascii=False))
        return 1
    if not net.is_private:
        print(json.dumps({
            "error": f"出口网段 {net} 不是私网（RFC1918），拒绝扫描——本工具只允许扫局域网",
            "local_ip": local_ip}, ensure_ascii=False))
        return 1

    ports = sorted({int(p) for p in re.split(r"[,，]", args.ports) if p.strip().isdigit()
                    and int(p) in LAN_PORT_TABLE} or set(LAN_PORT_TABLE))
    hosts = [str(h) for h in net.hosts()]
    if args.hosts:
        # v1.25.1 审计修复（质疑②b·高·安全）：--hosts 此前无校验，
        # `lan --hosts 8.8.8.8` 可绕过上面的 RFC1918 私网护栏去扫公网。
        # 每个显式主机必须是私网 IP（不解析域名——局域网扫描场景只收 IP）。
        import ipaddress as _ipa
        bad = []
        checked = []
        for h in (h.strip() for h in re.split(r"[,，]", args.hosts) if h.strip()):
            try:
                ip = _ipa.ip_address(h)
            except ValueError:
                bad.append(f"{h}（非 IP）")
                continue
            if not ip.is_private:
                bad.append(f"{h}（非私网）")
                continue
            checked.append(str(ip))
        if bad:
            print(json.dumps({
                "error": f"--hosts 存在越界目标，已拒绝扫描: {', '.join(bad)}"
                         "（本工具只允许扫 RFC1918 私网段，与网段护栏同规）",
                "local_ip": local_ip}, ensure_ascii=False))
            return 1
        if not checked:
            print(json.dumps({"error": "--hosts 解析后为空", "local_ip": local_ip},
                             ensure_ascii=False))
            return 1
        hosts = checked

    t0 = time.time()
    sys.stderr.write(f"[lan] 扫描 {net} 的 {len(hosts)} 主机 × {len(ports)} 端口"
                     f"（超时 {args.scan_timeout}s，只读探测）\n")
    # 端口扫描并发 128：254×12 任务 0.3s 超时，实测 ~5-10s
    tasks = [(h, p) for h in hosts for p in ports]
    with ThreadPoolExecutor(max_workers=128) as ex:
        results = list(ex.map(lambda hp: _tcp_probe(hp[0], hp[1], args.scan_timeout), tasks))
    alive = {tp for tp, ok in zip(tasks, results) if ok}
    by_host: Dict[str, List[int]] = {}
    for h, p in alive:
        by_host.setdefault(h, []).append(p)

    findings: List[Dict] = []
    for host, plist in sorted(by_host.items()):
        for p in plist:
            proto, name = LAN_PORT_TABLE[p]
            item = {"host": host, "port": p, "service": name}
            # v1.25.0 自查修正：https 曾落进 else 被当 FTP（实测 443 打出 ftp:// URL）
            if proto in ("http", "https"):
                ident = _http_identify(proto, host, p, args.http_timeout)
                item.update(scheme=proto, title=ident.get("title", ""),
                            server=ident.get("server", ""), url=ident["url"])
            elif proto == "smb":
                shares = _smb_shares(host)
                item.update(scheme="smb", shares=shares)
                for sh in shares:
                    findings.append({"host": host, "port": p, "service": "SMB共享",
                                     "scheme": "smb", "url": f"smb://{host}/{sh}",
                                     "title": f"{host} 共享 {sh}", "server": ""})
            else:  # ftp
                item.update(scheme="ftp", banner=_ftp_banner(host, p, args.http_timeout),
                            url=f"ftp://{host}:{p}/")
            findings.append(item)

    # 入索引（--no-index 只报告不入库）
    indexed = 0
    if not args.no_index:
        conn = get_db()
        for f in findings:
            if not f.get("url"):
                continue
            text_parts = [f.get("title", ""), f.get("server", ""), f.get("banner", "")]
            text_parts += [f"共享 {s}" for s in f.get("shares", [])]
            text = " ".join(t for t in text_parts if t) or f["service"]
            add_page(conn, f["url"], f.get("title") or f["url"], text, source="lan")
            indexed += 1
        conn.close()

    out = {
        "network": str(net), "local_ip": local_ip,
        "hosts_scanned": len(hosts), "ports_per_host": len(ports),
        "elapsed": round(time.time() - t0, 1),
        "services_found": len(findings), "indexed": indexed,
        "findings": findings,
        "note": "发现结果已入本地索引（source=lan），用 `search --query` 即可搜；"
                "全部为只读探测，不含登录/写入操作",
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"网段 {net}（本机 {local_ip}）：{len(hosts)} 主机 × {len(ports)} 端口，"
              f"耗时 {out['elapsed']}s，发现 {len(findings)} 个服务，入索引 {indexed} 条")
        for f in findings:
            extra = (f" 标题={f['title']}" if f.get("title")
                     else f" 共享={','.join(f.get('shares', []))}" if f.get("shares")
                     else f" banner={f.get('banner', '')}" if f.get("banner") else "")
            print(f"  [{f['service']}] {f.get('url', f['host'] + ':' + str(f['port']))}{extra}")
        if not findings:
            print("  （未发现开放服务——设备可能全在休眠/防火墙拦截/网段选错）")
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
    p_seed.add_argument("--ad-filter", choices=["none", "low", "medium", "high"], default="medium",
                        help="广告过滤强度（种子发现默认 medium，防垃圾URL进索引）")
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

    p_lan = sub.add_parser("lan", help="局域网搜索：发现设备/服务/共享并入本地索引（只读探测，限私网段）")
    p_lan.add_argument("--ports", default="", help="逗号分隔的端口列表（默认全部内置常见服务端口：80,443,8080,8000,8081,5000,32400,8096,9200,8384,445,21）")
    p_lan.add_argument("--hosts", default="", help="只扫指定主机（逗号分隔 IP，默认扫整个 /24 网段）")
    p_lan.add_argument("--scan-timeout", type=float, default=0.3, help="端口探测超时秒数（默认 0.3）")
    p_lan.add_argument("--http-timeout", type=float, default=3.0, help="HTTP/FTP 识别超时秒数（默认 3）")
    p_lan.add_argument("--no-index", action="store_true", help="只报告发现结果，不入索引")
    p_lan.add_argument("--json", action="store_true")
    p_lan.set_defaults(func=cmd_lan)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
