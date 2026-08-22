#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Web Search — Playwright browser-simulation helper.

This script drives a real Chromium browser via Playwright, so search engines
see a genuine browser fingerprint instead of a plain HTTP client. It is more
likely to pass anti-bot checks than the stdlib-only search.py.

Requirements:
    pip install playwright
    python -m playwright install chromium

Usage examples:
    python search_browser.py "OpenClaw web_search provider"
    python search_browser.py --query "DeepSeek V4" --max-results 8 --json
    python search_browser.py --query "今天A股" --engines bing,sogou,so360,baidu
"""

import argparse
import json
import random
import re
import sys
import time
import urllib.parse
from pathlib import Path as _P
from typing import Dict, List

# 安全模式基建复用（同目录 auto_save_browser：常量 + 拦截器，零重复）
sys.path.insert(0, str(_P(__file__).resolve().parent))
try:
    from auto_save_browser import _setup_safe_mode as _SETUP_SAFE_MODE
    from auto_save_browser import _browser_launch_args as _BROWSER_LAUNCH_ARGS
    from auto_save_browser import _apply_stealth as _APPLY_STEALTH
except ImportError:  # 单文件挪走用时退化为普通模式
    def _SETUP_SAFE_MODE(context, page):  # type: ignore
        return {}

    def _BROWSER_LAUNCH_ARGS(safe):  # type: ignore
        # 与 auto_save_browser._browser_launch_args 同口径：safe 时必须恢复进程沙箱
        # （此前的兜底版本无视 safe 参数恒给 --no-sandbox，安全模式被静默削弱）
        args = ["--disable-blink-features=AutomationControlled"]
        if not safe:
            args += ["--disable-features=IsolateOrigins,site-per-process", "--no-sandbox"]
        return args

    def _APPLY_STEALTH(context, mode):  # type: ignore
        # 兜底：单文件挪走时退回半套伪装（STEALTH_JS 上面自带）
        context.add_init_script(STEALTH_JS)
        return "basic"

try:
    from playwright.sync_api import sync_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    # 不在 import 阶段 sys.exit：被 auto_save_browser 等脚本 import 时会把宿主进程一起杀死。
    # 真正用到时（run_search/main）再报错。
    _HAS_PLAYWRIGHT = False

DEFAULT_ENGINES = ["bing", "sogou", "so360", "baidu"]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Edge（Windows 出厂默认浏览器，国内占比极高）
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.51",
]

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


def _clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(str(text).split())


def _result(title: str, url: str, snippet: str, source: str) -> Dict[str, str]:
    return {
        "title": _clean_text(title)[:300],
        "url": url[:500],
        "snippet": _clean_text(snippet)[:500],
        "source": source,
    }


# 有业务含义的 query 参数（保留参与去重 key；其余跟踪参数如 utm_*/spm 等仍丢弃）
_URL_KEEP_PARAMS = ("v", "id", "p", "tid", "pid", "aid", "vid", "q", "w", "keyword",
                    "doc", "item", "thread", "post", "video", "album", "song", "play")


def _normalize_url(url: str) -> str:
    """URL 规范化：去 www.、去跟踪类 query/fragment、去尾斜杠。
    同一页面从 5 个引擎来（带各自跟踪参数）只留一份；
    但保留有业务含义的参数（v/id/tid 等）——YouTube watch?v=aaa 和 watch?v=bbb
    是不同视频，丢了参数会被误判成同一条。"""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path.rstrip("/").lower()
        keep = []
        for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            if k.lower() in _URL_KEEP_PARAMS and v:
                keep.append(f"{k}={v}")
        keep.sort()  # 参数顺序无关
        return f"{host}{path}?{'&'.join(keep)}" if keep else f"{host}{path}"
    except Exception:
        return (url or "").lower()


def _dedupe(results: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """三层去重（对齐业界搜索聚合做法）：
    1. URL 规范化：域名+路径做 key，跟踪参数不影响；
    2. 标题相似度 ≥0.82 判重复：标题换皮的结果全砍；
    3. 摘要指纹：前 200 字符相似度 ≥0.78 判重复：内容一样的缝合怪全砍。"""
    from difflib import SequenceMatcher

    seen_urls = set()
    kept: List[Dict[str, str]] = []
    kept_titles: List[str] = []
    kept_snips: List[str] = []
    for r in results:
        key = _normalize_url(r.get("url", ""))
        if key and key in seen_urls:
            continue
        title = (r.get("title") or "").strip()
        snip = (r.get("snippet") or "").strip()[:200]
        # 第二层：标题相似度（换皮标题）
        if title and any(
            SequenceMatcher(None, title, t).ratio() >= 0.82 for t in kept_titles
        ):
            continue
        # 第三层：摘要指纹（同内容不同来源的缝合稿）
        if snip and len(snip) >= 30 and any(
            SequenceMatcher(None, snip, s).ratio() >= 0.78 for s in kept_snips
        ):
            continue
        if key:
            seen_urls.add(key)
        kept.append(r)
        kept_titles.append(title)
        kept_snips.append(snip)
    return kept


ERROR_PAGE_STRONG = (
    # 强模式：正常结果标题不会出现这些词，命中即挡（不分标题长短）
    "页面不存在", "网页不存在", "链接已失效", "链接失效", "页面已删除",
    "内容不存在", "无法找到该页", "请输入验证码", "人机验证", "安全验证",
    "访问异常", "滑动验证", "just a moment",
)

ERROR_PAGE_WEAK = (
    # 弱模式：可能出现在正常文章标题（如"如何解决404错误"），
    # 只在标题极短时才判错（真实错误页标题如 "404 Not Found"≈13字符；
    # 15 上限：中文教程标题普遍 >15 字符，不会被误杀）
    "404", "403", "500", "not found", "page not found", "forbidden",
    "access denied",
)


def _is_error_result(url: str, title: str) -> bool:
    """错误页/验证码墙判定：标题命中错误模式，或 URL 是错误页路径。
    强模式全挡；弱模式仅极短标题挡（防误杀"如何解决404"这类教程）。"""
    title_l = (title or "").strip().lower()
    if not title_l:
        return True  # 连标题都没有的基本是坏结果
    for pat in ERROR_PAGE_STRONG:
        if pat in title_l:
            return True
    if len(title_l) <= 15:
        for pat in ERROR_PAGE_WEAK:
            if pat in title_l:
                return True
    # 错误页 URL 模式：/error /404 /403 结尾
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(("/404", "/403", "/500", "/error", "/notfound", "/not-found")):
        return True
    return False


def _safe_text(locator) -> str:
    try:
        return locator.inner_text(timeout=2000)
    except Exception:
        return ""


def _safe_attr(locator, name: str) -> str:
    try:
        return locator.get_attribute(name, timeout=2000) or ""
    except Exception:
        return ""


def _extract_from_items(page, items, title_sel: str, snippet_sel: str, source: str, max_results: int) -> List[Dict[str, str]]:
    """Extract results from a Playwright locator collection."""
    results = []
    count = items.count()
    for i in range(min(count, max_results)):
        try:
            item = items.nth(i)
            title_el = item.locator(title_sel).first
            raw_url = _safe_attr(title_el, "href")
            title = _safe_text(title_el)
            if not title or not raw_url:
                continue
            if raw_url.startswith("//"):
                raw_url = "https:" + raw_url
            url = urllib.parse.urljoin(page.url, raw_url)
            if not url.startswith(("http://", "https://")):
                continue
            snippet_el = item.locator(snippet_sel).first
            snippet = _safe_text(snippet_el)
            results.append(_result(title, url, snippet, source))
        except Exception:
            continue
    return results


def search_bing(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&setlang=zh-hans&cc=CN"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector("li.b_algo", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator("li.b_algo")
    return _extract_from_items(page, items, "h2 a", "p", "Bing", max_results)


def search_sogou(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://www.sogou.com/web?query=" + urllib.parse.quote(query)
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector(".vrwrap, .rb", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator(".vrwrap, .rb")
    results = _extract_from_items(page, items, "h3 a, .vr-title a, a", "p, .text-layout, .str_info", "Sogou", max_results)
    if results:
        return results
    # 搜狗对无头浏览器有额外 JS 检测，可能拿不到标准容器；退回解析所有 h3 链接。
    fallback_items = page.locator("h3 a")
    return _extract_from_items(page, fallback_items, "a", "p, .text-layout, .str_info", "Sogou", max_results)


def search_so360(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://www.so.com/s?q=" + urllib.parse.quote(query)
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector(".res-list", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator(".res-list")
    return _extract_from_items(page, items, "h3 a", "p.res-desc, .res-desc", "360搜索", max_results)


def search_eastmoney(page, query: str, max_results: int) -> List[Dict[str, str]]:
    """东方财富站内搜索：专业财经内容，无竞价广告（finance 意图的主力引擎，
    思路来自意图路由——能判出词性的查询直接用专业站，从源头绕开广告引擎）。"""
    url = "https://so.eastmoney.com/news/s?keyword=" + urllib.parse.quote(query)
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector(".news-item, .item, .news_list li", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    # 防御式多候选容器：东财改版频繁，标准容器拿不到就退回全部 h3/标题链接
    items = page.locator(".news-item, .item")
    results = _extract_from_items(page, items, "a", "p, .content, .des", "东方财富", max_results)
    if results:
        return results
    fallback_items = page.locator(".news_list li, div[class*='news'] a")
    return _extract_from_items(page, fallback_items, "a", "p", "东方财富", max_results)


def search_baidu(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://www.baidu.com/s?wd=" + urllib.parse.quote(query)
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector("#content_left .result", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator("#content_left .result")
    return _extract_from_items(page, items, "h3 a", ".c-span-last, .content-right, p", "百度", max_results)


def search_ddg(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector(".result-link", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator("a.result-link")
    results = []
    count = items.count()
    for i in range(min(count, max_results)):
        try:
            link = items.nth(i)
            url = _safe_attr(link, "href")
            title = _safe_text(link)
            if not title or not url.startswith(("http://", "https://")):
                continue
            # DDG Lite snippet is usually in the same table row/next cell.
            snippet = ""
            row = link.locator("xpath=ancestor::tr[1]")
            sn = row.locator("td.result-snippet").first
            snippet = _safe_text(sn)
            results.append(_result(title, url, snippet, "DuckDuckGo"))
        except Exception:
            continue
    return results


def search_arxiv_browser(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://arxiv.org/search/?query=" + urllib.parse.quote(query) + "&searchtype=all"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector("li.arxiv-result", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator("li.arxiv-result")
    return _extract_from_items(page, items, "p.title a", "span.abstract-full", "arXiv", max_results)


def search_github_browser(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://github.com/search?q=" + urllib.parse.quote(query) + "&type=repositories"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector("[data-testid='results-list'] > div, .repo-list-item", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator("[data-testid='results-list'] > div, .repo-list-item")
    return _extract_from_items(page, items, "h3 a, a[href*='/']", "p, .col-9", "GitHub", max_results)


def search_stackoverflow_browser(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://stackoverflow.com/search?q=" + urllib.parse.quote(query)
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector(".s-post-summary", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator(".s-post-summary")
    return _extract_from_items(page, items, ".s-link", ".s-post-summary--content", "Stack Overflow", max_results)


def search_wikipedia_browser(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://zh.wikipedia.org/w/index.php?search=" + urllib.parse.quote(query) + "&title=Special:Search"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector(".mw-search-result", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator(".mw-search-result")
    return _extract_from_items(page, items, ".mw-search-result-heading a", ".searchresult", "Wikipedia", max_results)


def search_mojeek_browser(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://www.mojeek.com/search?q=" + urllib.parse.quote(query)
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector(".result", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator(".result")
    return _extract_from_items(page, items, "h2 a", "p", "Mojeek", max_results)


def search_ecosia_browser(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://www.ecosia.org/search?q=" + urllib.parse.quote(query)
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector(".result", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator(".result")
    return _extract_from_items(page, items, "a[data-test-id='result-link'], h2 a", "p", "Ecosia", max_results)


def search_startpage_browser(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://www.startpage.com/sp/search?query=" + urllib.parse.quote(query)
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector(".w-gl__result", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator(".w-gl__result")
    return _extract_from_items(page, items, "h2 a", ".w-gl__description", "Startpage", max_results)


def search_qwant_browser(page, query: str, max_results: int) -> List[Dict[str, str]]:
    url = "https://www.qwant.com/?q=" + urllib.parse.quote(query) + "&t=web"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector(".result", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator(".result")
    return _extract_from_items(page, items, "a", "p", "Qwant", max_results)


ENGINES = {
    "bing": search_bing,
    "sogou": search_sogou,
    "so360": search_so360,
    "baidu": search_baidu,
    "eastmoney": search_eastmoney,
    "ddg": search_ddg,
    "arxiv": search_arxiv_browser,
    "github": search_github_browser,
    "stackoverflow": search_stackoverflow_browser,
    "wikipedia": search_wikipedia_browser,
    "mojeek": search_mojeek_browser,
    "ecosia": search_ecosia_browser,
    "startpage": search_startpage_browser,
    "qwant": search_qwant_browser,
}

CATEGORY_ENGINES = {
    "general": ["bing", "sogou", "so360", "baidu", "wikipedia"],
    # 外网分类与 search.py 同口径：ddg/brave/searxng 为主力（brave/searxng 需 API Key，
    # 浏览器版没有对应抓取实现，这里用可用的 ddg+wikipedia 兜底；mojeek/ecosia 实测不可用已移除）
    "external": ["bing", "so360", "baidu", "ddg", "wikipedia"],
    "academic": ["arxiv", "bing", "wikipedia"],
    "tech": ["github", "stackoverflow", "bing"],
    "news": ["bing", "sogou", "so360", "baidu"],
    # 财经意图：专业站打头（无竞价广告），通用引擎只做兜底——意图路由的核心收益
    "finance": ["eastmoney", "bing", "sogou"],
    "social": ["sogou", "bing"],
    "all": [
        "arxiv", "github", "stackoverflow", "wikipedia",
        "bing", "sogou", "so360", "baidu", "ddg",
    ],
}

AD_HOST_KEYWORDS = (
    "doubleclick.net", "googleadservices.com", "googlesyndication.com",
    "amazon-adsystem.com", "adservice.google.com", "taboola.com",
    "outbrain.com", "adsterra.com", "propellerads.com", "popads.net",
    "adroll.com", "criteo.com", "pubmatic.com", "rubiconproject.com",
    "openx.net", "smartadserver.com", "mgid.com", "revcontent.com",
    "adservice.com", "adnxs.com", "adsrvr.org",
    # 追加：程序化广告/重定向/联盟广告常见域
    "adform.net", "adition.com", "smaato.net", "yieldmo.com", "sharethrough.com",
    "33across.com", "casalemedia.com", "bidswitch.net",
    "zedo.com", "adcolony.com", "applovin.com", "ironsrc.com", "vungle.com",
    "unityads.unity3d.com", "unity.com/ads", "mintegral.com",
    "adtrack", "adtracker", "clicktracker", "tracking21", "track.ad",
    "adsrv", "adsystem", "adserver", "admarket", "adtraffic",
)

AD_TITLE_KEYWORDS = (
    "广告", "推广", "赞助", "advertisement", "sponsored", "promoted", "ad:",
    "商编", "软广",
)

AD_REDIRECT_MARKERS = (
    "/link?", "url=", "click?", "rd?", "go.php", "jump?",
    "link?url", "jump.php", "rd2?", "redir?", "/aclk", "clicktrack",
    "utm_medium=cpc", "utm_source=ad", "paid=1", "sponsored_click",
)

DOMESTIC_FIRST = ["sogou", "so360", "baidu", "bing", "ddg"]


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _low_relevance(results: List[Dict[str, str]], query: str) -> bool:
    """Heuristic: for Chinese queries, Bing sometimes returns dictionary junk."""
    if not _has_cjk(query):
        return False
    q_chars = set(re.findall(r"[\u4e00-\u9fff]", query))
    if len(q_chars) < 2:
        return False
    for r in results[:3]:
        title_chars = set(re.findall(r"[\u4e00-\u9fff]", r.get("title", "")))
        if len(q_chars & title_chars) >= max(1, len(q_chars) // 2):
            return False
    return True


def _is_ad_result(url: str, title: str, level: str) -> bool:
    if level == "none":
        return False
    netloc = urllib.parse.urlparse(url).netloc.lower()
    title_l = title.lower()
    # 广告专用子域：ad.xxx / ads.xxx / adv.xxx / tracking.xxx（medium 起判广告）
    is_ad_subdomain = netloc.startswith(("ad.", "ads.", "adv.", "tracking.", "track."))
    if level == "low":
        return any(k in netloc for k in AD_HOST_KEYWORDS) or bool(
            re.search(r"\b(sponsored|advertisement)\b", title_l)
        )
    if level == "medium":
        return (
            any(k in netloc for k in AD_HOST_KEYWORDS)
            or is_ad_subdomain
            or any(k in title_l for k in AD_TITLE_KEYWORDS)
        )
    if level == "high":
        if any(k in netloc for k in AD_HOST_KEYWORDS):
            return True
        if is_ad_subdomain:
            return True
        if any(k in title_l for k in AD_TITLE_KEYWORDS):
            return True
        return any(m in url.lower() for m in AD_REDIRECT_MARKERS)
    return False


def _filter_results(results: List[Dict[str, str]], level: str = "medium") -> List[Dict[str, str]]:
    # 错误页/验证码墙是质量问题，任何广告过滤档位（含 none）都挡在结果外
    results = [r for r in results if not _is_error_result(r.get("url", ""), r.get("title", ""))]
    if level == "none":
        return results
    return [r for r in results if not _is_ad_result(r.get("url", ""), r.get("title", ""), level)]


def _filter_site(results: List[Dict[str, str]], site: str) -> List[Dict[str, str]]:
    if not site:
        return results
    site = site.lower().lstrip(".").rstrip("/")
    return [
        r for r in results
        if site in urllib.parse.urlparse(r.get("url", "")).netloc.lower()
    ]


def _query_terms(query: str) -> List[str]:
    r"""分词：英文/数字按词切；中文整句会被 \w+ 黏成一个词（precision 排序对中文
    直接失效），拆成二元组做匹配粒度。"""
    terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9_]+", query) if len(t) > 1]
    cjk = re.findall(r"[\u4e00-\u9fff]", query)
    terms += [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    return terms


def _score_results(results: List[Dict[str, str]], query: str, precision: int = 50) -> List[Dict[str, str]]:
    if precision <= 0:
        return results
    terms = _query_terms(query)
    if not terms:
        return results
    def score(r):
        text = f"{r.get('title', '')} {r.get('url', '')} {r.get('snippet', '')}".lower()
        return sum(text.count(t) for t in terms)
    return sorted(results, key=score, reverse=True)


def _resolve_engines(explicit: str, category: str = "general", query: str = "") -> List[str]:
    if explicit:
        parts = [e.strip().lower() for e in explicit.split(",") if e.strip()]
        if "auto" in parts:
            return _resolve_engines("", category, query)
        return parts
    chosen = list(CATEGORY_ENGINES.get(category, DEFAULT_ENGINES))
    if _has_cjk(query):
        # 中文查询优先国内引擎，避免 Bing/DDG 在国内抽风或超时。
        chosen.sort(key=lambda e: DOMESTIC_FIRST.index(e) if e in DOMESTIC_FIRST else 99)
    return chosen


def _parse_proxy(proxy: str):
    """解析代理字符串为 Playwright proxy 参数。

    支持格式：
        http://127.0.0.1:7890
        socks5://127.0.0.1:1080
        http://user:pass@host:port
        host:port（默认按 http 处理）
    """
    if not proxy:
        return None
    server = proxy.strip()
    scheme = ""
    username = password = None
    if "://" in server:
        scheme, server = server.split("://", 1)
    if "@" in server:
        auth, server = server.rsplit("@", 1)
        if ":" in auth:
            username, password = auth.split(":", 1)
    server = (scheme + "://" + server) if scheme else ("http://" + server)
    info = {"server": server}
    if username is not None:
        info["username"] = username
        info["password"] = password or ""
    return info


def run_search(query: str, max_results: int, engines: List[str], proxy: str = "", safe: bool = False,
               stealth: str = "full") -> Dict:
    if not _HAS_PLAYWRIGHT:
        hint = "playwright 未安装: pip install playwright && python -m playwright install chromium"
        return {"query": query, "results": [], "engine_errors": {"playwright": hint}, "browser": "unavailable"}
    all_results: List[Dict[str, str]] = []
    stats: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    fetch_limit = max_results * 2

    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                headless=True,
                args=_BROWSER_LAUNCH_ARGS(safe),
            )
            context_kwargs = dict(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
                ignore_https_errors=True,  # 与 auto_save_browser 各路线同口径：自签证书站点也能开
            )
            # 安全模式：禁 Service Worker（挖矿/恶意持久化常用）
            if safe:
                context_kwargs["service_workers"] = "block"
            # IP 伪装：所有浏览器流量走指定代理出口，目标站点看到的是代理 IP
            proxy_info = _parse_proxy(proxy)
            if proxy_info:
                context_kwargs["proxy"] = proxy_info
            context = browser.new_context(**context_kwargs)
            _APPLY_STEALTH(context, stealth)
            page = context.new_page()
            # 安全模式：请求拦截 + 弹窗全关（复用 auto_save_browser 的安全基建）
            safe_blocked = _SETUP_SAFE_MODE(context, page) if safe else {}

            for engine in engines:
                fn = ENGINES.get(engine)
                if not fn:
                    errors[engine] = "unsupported engine"
                    continue
                try:
                    results = fn(page, query, fetch_limit)
                    stats[engine] = len(results)
                    all_results.extend(results)
                    if not results:
                        errors[engine] = "no results"
                    elif engine == "bing" and _low_relevance(results, query):
                        errors[engine] = "low_relevance"
                except Exception as exc:
                    stats[engine] = 0
                    errors[engine] = str(exc)
                    sys.stderr.write(f"[{engine}] error: {exc}\n")
                # Human-like pause between engines.
                time.sleep(random.uniform(0.5, 1.2))
        finally:
            if browser is not None:
                browser.close()

    results = _dedupe(all_results)[:max_results * 3]
    out = {
        "query": query,
        "results": results,
        "engine_stats": stats,
        "engine_errors": errors,
        "browser": "playwright-chromium",
    }
    if safe:
        out["safe_mode"] = True
        try:
            out["blocked"] = safe_blocked
        except NameError:
            pass
    return out


def _format_plain(data: Dict) -> str:
    lines = []
    results = data.get("results", [])
    if not results:
        errs = data.get("engine_errors") or ""
        return f"没有搜索到结果。可尝试换关键词或稍后再试。{(' 引擎异常: ' + str(errs)) if errs else ''}"
    stats = data.get("engine_stats")
    lines.append(f"共 {len(results)} 条结果（浏览器模拟{f'，引擎统计: {stats}' if stats else ''}）")
    if data.get("engine_errors"):
        lines.append(f"引擎异常: {data['engine_errors']}")
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title', '(无标题)')}")
        lines.append(f"   URL: {r.get('url', '')}")
        if r.get("snippet"):
            lines.append(f"   摘要: {r['snippet']}")
        if r.get("source"):
            lines.append(f"   来源: {r['source']}")
        lines.append("")
    return "\n".join(lines).strip()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="DeepSeek Web Search Playwright helper (real browser simulation)."
    )
    parser.add_argument("query_pos", nargs="?", help="Search query (positional)")
    parser.add_argument("--query", help="Search query")
    parser.add_argument("--max-results", type=int, default=6, help="Max results (default: 6)")
    parser.add_argument(
        "--engines",
        default="",
        help="Comma-separated engines: bing,sogou,so360,baidu,eastmoney,ddg,arxiv,github,stackoverflow,wikipedia（eastmoney=东方财富专业财经,无竞价广告；mojeek/ecosia/startpage/qwant 实测不可用，仅显式指定时生效）",
    )
    parser.add_argument(
        "--category",
        choices=["general", "external", "academic", "tech", "finance", "news", "social", "all"],
        default="general",
        help="搜索分类: general/external(外网)/academic(学术)/tech(技术)/finance(财经)/news(新闻)/social(社交)/all(全部)",
    )
    parser.add_argument(
        "--ad-filter",
        choices=["none", "low", "medium", "high"],
        default="medium",
        help="广告过滤强度: none=不过滤, low=低, medium=中(默认), high=高(可能误杀真实内容)",
    )
    parser.add_argument("--exact", action="store_true", help="精确匹配：给关键词加引号")
    parser.add_argument(
        "--proxy",
        default="",
        help="IP 伪装代理: http://127.0.0.1:7890 / socks5://host:port / http://user:pass@host:port",
    )
    parser.add_argument("--site", default="", help="只保留指定域名下的结果，例如 github.com")
    parser.add_argument(
        "--precision",
        type=int,
        default=50,
        help="搜索精准度排序 0-100，越高越优先展示关键词重合度高的结果",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--brief", action="store_true", help="精简 JSON 输出（省 token，供大模型直接消费）")
    parser.add_argument(
        "--safe",
        action="store_true",
        help="安全模式：恢复浏览器进程沙箱+站点隔离、拦挖矿/危险下载/弹窗（搜索可疑内容/打开陌生站点时用）",
    )
    parser.add_argument(
        "--stealth",
        choices=["full", "basic", "off"],
        default="full",
        help="浏览器伪装档位：full=全套（默认，playwright-stealth 深层指纹补丁，显著提升搜狗等风控站通过率）；basic=半套（自带伪装）；off=关闭",
    )
    args = parser.parse_args(argv)

    query = (args.query or args.query_pos or "").strip()
    if not query:
        parser.print_help()
        return 2

    if not _HAS_PLAYWRIGHT:
        print(
            "Playwright 未安装。请先执行:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    if args.exact and not query.startswith('"'):
        query = f'"{query.strip()}"'

    engines = _resolve_engines(args.engines, args.category, query)
    data = run_search(query, args.max_results, engines, proxy=args.proxy, safe=args.safe,
                      stealth=args.stealth)

    data["results"] = _filter_results(data.get("results", []), args.ad_filter)
    if args.site:
        data["results"] = _filter_site(data["results"], args.site)
    data["results"] = _score_results(data["results"], query, args.precision)[: args.max_results]
    data["category"] = args.category
    data["proxy"] = args.proxy or None
    data["ad_filter"] = args.ad_filter
    data["precision"] = args.precision
    data["site"] = args.site or None

    # brief：给大模型省 token —— 只留 title/url/精简 snippet，去掉 engine_stats 等元数据
    if args.brief:
        data["results"] = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": (r.get("snippet", "") or "")[:120]}
            for r in data["results"]
        ]
        data.pop("engine_stats", None)
        data.pop("engine_errors", None)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=None if args.brief else 2))
    else:
        print(_format_plain(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
