#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Web Search — OpenClaw skill helper.

Zero-dependency multi-engine search script (stdlib only).
Default engines are domestic-friendly: Bing, Sogou, 360, Baidu.
Optionally uses Tavily / Brave / SearXNG when the corresponding environment
variables are present.

Usage examples:
    python search.py "OpenClaw web_search provider"
    python search.py --query "DeepSeek V4" --max-results 8 --json
    python search.py --query "Python asyncio" --engines ddg,bing --timeout 10
"""

import argparse
import html
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List

DEFAULT_ENGINES = ["bing", "sogou", "so360", "baidu"]
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 可通过 --cacert 指定自定义 CA 证书包，用于某些需要安装证书的站点。
CA_CERT = None


def _clean_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _fetch(url: str, timeout: int = 8, headers: Dict[str, str] = None) -> str:
    """GET a URL and return decoded text."""
    req_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    ctx = ssl.create_default_context(cafile=CA_CERT) if CA_CERT else ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read()
    # Try common encodings; most modern engines are UTF-8.
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def _post_json(url: str, payload: dict, timeout: int = 8, headers: Dict[str, str] = None) -> dict:
    """POST a JSON payload and return parsed JSON."""
    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }
    if headers:
        req_headers.update(headers)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    ctx = ssl.create_default_context(cafile=CA_CERT) if CA_CERT else ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def _result(title: str, url: str, snippet: str, source: str) -> Dict[str, str]:
    return {
        "title": _clean_html(title)[:300],
        "url": url[:500],
        "snippet": _clean_html(snippet)[:500],
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
    """三层去重（与 search_browser 同口径）：
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
    # 只在标题极短时才判错（真实错误页标题如 "404 Not Found"≈13字符）
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


# ---------------------------------------------------------------------------
# Free HTML engines
# ---------------------------------------------------------------------------

def search_ddg(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    """DuckDuckGo Lite: key-free, usually accessible from many regions."""
    url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
    page = _fetch(url, timeout=timeout)
    results: List[Dict[str, str]] = []
    # DDG Lite result links look like: <a rel="nofollow" href="URL" class="result-link">Title</a>
    # Match any anchor and keep only ones that carry the result-link marker.
    pattern = re.compile(r"<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", re.S | re.I)
    for m in pattern.finditer(page):
        if "result-link" not in m.group(0).lower():
            continue
        href = html.unescape(m.group(1))
        title = _clean_html(m.group(2))
        if not title or not href.startswith(("http://", "https://")):
            continue
        tail = page[m.end(): m.end() + 2500]
        sn = re.search(
            r'class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</(?:td|div)>',
            tail,
            re.S | re.I,
        )
        snippet = _clean_html(sn.group(1)) if sn else ""
        results.append(_result(title, href, snippet, "DuckDuckGo"))
        if len(results) >= max_results:
            break
    return results


def search_bing(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    """Bing HTML results."""
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&setlang=zh-hans&cc=CN"
    page = _fetch(url, timeout=timeout)
    results: List[Dict[str, str]] = []
    blocks = re.findall(r'<li class="b_algo".*?</li>', page, re.S | re.I)
    for block in blocks:
        h2 = re.search(
            r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            block,
            re.S | re.I,
        )
        if not h2:
            continue
        href = html.unescape(h2.group(1))
        title = _clean_html(h2.group(2))
        if not title or not href.startswith(("http://", "https://")):
            continue
        p = re.search(r"<p[^>]*>(.*?)</p>", block, re.S | re.I)
        snippet = _clean_html(p.group(1)) if p else ""
        results.append(_result(title, href, snippet, "Bing"))
        if len(results) >= max_results:
            break
    return results


def search_sogou(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    """Sogou HTML results."""
    url = "https://www.sogou.com/web?query=" + urllib.parse.quote(query)
    page = _fetch(url, timeout=timeout)
    results: List[Dict[str, str]] = []
    # Sogou titles are usually <h3 ...><a ...>Title</a></h3>
    for m in re.finditer(r"<h3[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", page, re.S | re.I):
        href = html.unescape(m.group(1))
        title = _clean_html(m.group(2))
        if not title or not href.startswith(("http://", "https://")):
            continue
        # Find a nearby snippet container.
        tail = page[m.end(): m.end() + 1500]
        sn = re.search(r"<p[^>]*>(.*?)</p>", tail, re.S | re.I) or re.search(
            r'class="[^"]*(?:text-layout|str_info|space-txt)[^"]*"[^>]*>(.*?)</div>',
            tail,
            re.S | re.I,
        )
        snippet = _clean_html(sn.group(1)) if sn else ""
        results.append(_result(title, href, snippet, "Sogou"))
        if len(results) >= max_results:
            break
    return results


def search_so360(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    """360 Search (so.com) HTML results."""
    url = "https://www.so.com/s?q=" + urllib.parse.quote(query)
    page = _fetch(url, timeout=timeout)
    results: List[Dict[str, str]] = []
    for m in re.finditer(r"<h3[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", page, re.S | re.I):
        href = html.unescape(m.group(1))
        title = _clean_html(m.group(2))
        if not title or not href.startswith(("http://", "https://")):
            continue
        tail = page[m.end(): m.end() + 1500]
        sn = re.search(r"<p[^>]*>(.*?)</p>", tail, re.S | re.I) or re.search(
            r'class="[^"]*res-desc[^"]*"[^>]*>(.*?)</(?:p|div)>',
            tail,
            re.S | re.I,
        )
        snippet = _clean_html(sn.group(1)) if sn else ""
        results.append(_result(title, href, snippet, "360搜索"))
        if len(results) >= max_results:
            break
    return results


# ---------------------------------------------------------------------------
# Academic / Tech / Extra HTML engines
# ---------------------------------------------------------------------------

def search_arxiv(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    """arXiv API: academic papers."""
    url = (
        "https://export.arxiv.org/api/query?search_query=all:"
        + urllib.parse.quote(query)
        + "&start=0&max_results="
        + str(max_results)
    )
    page = _fetch(url, timeout=timeout)
    root = ET.fromstring(page)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results: List[Dict[str, str]] = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", default="", ns=ns) or ""
        link = entry.findtext("atom:id", default="", ns=ns) or ""
        summary = entry.findtext("atom:summary", default="", ns=ns) or ""
        results.append(_result(title, link, summary, "arXiv"))
    return results


def search_github(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    """GitHub repository search API (no auth, rate-limited)."""
    url = (
        "https://api.github.com/search/repositories?q="
        + urllib.parse.quote(query)
        + "&per_page="
        + str(max_results)
    )
    page = _fetch(
        url,
        timeout=timeout,
        headers={"Accept": "application/vnd.github+json"},
    )
    data = json.loads(page)
    results: List[Dict[str, str]] = []
    for item in data.get("items", []):
        results.append(
            _result(
                item.get("full_name", ""),
                item.get("html_url", ""),
                item.get("description") or "",
                "GitHub",
            )
        )
    return results


def search_stackoverflow(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    """Stack Exchange API for Stack Overflow questions."""
    url = (
        "https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q="
        + urllib.parse.quote(query)
        + "&site=stackoverflow&pagesize="
        + str(max_results)
    )
    page = _fetch(url, timeout=timeout, headers={"Accept": "application/json"})
    data = json.loads(page)
    results: List[Dict[str, str]] = []
    for item in data.get("items", []):
        tags = " ".join(item.get("tags", []))
        results.append(
            _result(
                item.get("title", ""),
                item.get("link", ""),
                tags,
                "Stack Overflow",
            )
        )
    return results


def search_baidu(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    """Baidu HTML search (may hit captcha; kept as an extra domestic engine)."""
    url = "https://www.baidu.com/s?wd=" + urllib.parse.quote(query)
    page = _fetch(url, timeout=timeout)
    results: List[Dict[str, str]] = []
    blocks = re.findall(
        r'<div[^>]+class="[^"]*(?:result|c-container)[^"]*".*?</div>',
        page,
        re.S | re.I,
    )
    for block in blocks:
        h3 = re.search(
            r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            block,
            re.S | re.I,
        )
        if not h3:
            continue
        href = html.unescape(h3.group(1))
        title = _clean_html(h3.group(2))
        if not title or not href.startswith(("http://", "https://")):
            continue
        sn = re.search(r"<span[^>]*>(.*?)</span>", block, re.S | re.I)
        snippet = _clean_html(sn.group(1)) if sn else ""
        results.append(_result(title, href, snippet, "百度"))
        if len(results) >= max_results:
            break
    return results


# ---------------------------------------------------------------------------
# More free API engines: academic / tech / social / finance / knowledge
# ---------------------------------------------------------------------------

def search_openalex(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = "https://api.openalex.org/works?search=" + urllib.parse.quote(query) + "&per-page=" + str(max_results)
    data = json.loads(_fetch(url, timeout=timeout, headers={"Accept": "application/json"}))
    results: List[Dict[str, str]] = []
    for item in data.get("results", []):
        title = item.get("display_name", "")
        doi = item.get("doi", "")
        oid = item.get("id", "")
        link = doi or oid or ""
        snippet = str(item.get("publication_year", ""))
        results.append(_result(title, link, snippet, "OpenAlex"))
    return results


def search_semanticscholar(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search?query="
        + urllib.parse.quote(query)
        + "&limit="
        + str(max_results)
        + "&fields=title,url,abstract"
    )
    data = json.loads(_fetch(url, timeout=timeout, headers={"Accept": "application/json"}))
    results: List[Dict[str, str]] = []
    for item in data.get("data", []):
        results.append(
            _result(
                item.get("title", ""),
                item.get("url", ""),
                item.get("abstract") or "",
                "Semantic Scholar",
            )
        )
    return results


def search_crossref(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = "https://api.crossref.org/works?query=" + urllib.parse.quote(query) + "&rows=" + str(max_results)
    data = json.loads(_fetch(url, timeout=timeout, headers={"Accept": "application/json"}))
    results: List[Dict[str, str]] = []
    for item in data.get("message", {}).get("items", []):
        title = (item.get("title") or [""])[0]
        link = item.get("URL", "")
        snippet = ", ".join(item.get("container-title", []) or [])
        results.append(_result(title, link, snippet, "Crossref"))
    return results


def search_gitlab(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = "https://gitlab.com/api/v4/projects?search=" + urllib.parse.quote(query) + "&per_page=" + str(max_results)
    data = json.loads(_fetch(url, timeout=timeout, headers={"Accept": "application/json"}))
    results: List[Dict[str, str]] = []
    for item in data:
        results.append(
            _result(
                item.get("name", ""),
                item.get("web_url", ""),
                item.get("description") or "",
                "GitLab",
            )
        )
    return results


def search_npm(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = "https://registry.npmjs.org/-/v1/search?text=" + urllib.parse.quote(query) + "&size=" + str(max_results)
    data = json.loads(_fetch(url, timeout=timeout, headers={"Accept": "application/json"}))
    results: List[Dict[str, str]] = []
    for obj in data.get("objects", []):
        pkg = obj.get("package", {})
        results.append(
            _result(
                pkg.get("name", ""),
                pkg.get("links", {}).get("npm", ""),
                pkg.get("description") or "",
                "npm",
            )
        )
    return results


def search_hackernews(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = "https://hn.algolia.com/api/v1/search?query=" + urllib.parse.quote(query) + "&hitsPerPage=" + str(max_results)
    data = json.loads(_fetch(url, timeout=timeout, headers={"Accept": "application/json"}))
    results: List[Dict[str, str]] = []
    for hit in data.get("hits", []):
        title = hit.get("title") or hit.get("story_title") or ""
        link = hit.get("url") or ("https://news.ycombinator.com/item?id=" + str(hit.get("objectID", "")))
        snippet = hit.get("story_text") or ""
        results.append(_result(title, link, snippet, "Hacker News"))
    return results


def search_reddit(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = "https://www.reddit.com/search.json?q=" + urllib.parse.quote(query) + "&limit=" + str(max_results)
    data = json.loads(_fetch(url, timeout=timeout, headers={"User-Agent": DEFAULT_USER_AGENT}))
    results: List[Dict[str, str]] = []
    for child in data.get("data", {}).get("children", []):
        d = child.get("data", {})
        results.append(
            _result(
                d.get("title", ""),
                d.get("url", ""),
                d.get("selftext", "")[:300],
                "Reddit",
            )
        )
    return results


def search_wikipedia(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = (
        "https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch="
        + urllib.parse.quote(query)
        + "&format=json&utf8=1&srlimit="
        + str(max_results)
    )
    data = json.loads(_fetch(url, timeout=timeout, headers={"Accept": "application/json"}))
    results: List[Dict[str, str]] = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title", "")
        link = "https://zh.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
        results.append(_result(title, link, snippet, "Wikipedia"))
    return results


def search_yahoo_finance(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = (
        "https://query1.finance.yahoo.com/v1/finance/search?q="
        + urllib.parse.quote(query)
        + "&quotesCount="
        + str(max_results)
        + "&newsCount="
        + str(max_results)
    )
    data = json.loads(_fetch(url, timeout=timeout, headers={"User-Agent": DEFAULT_USER_AGENT}))
    results: List[Dict[str, str]] = []
    for q in data.get("quotes", []):
        symbol = q.get("symbol", "")
        title = f"{q.get('shortname') or q.get('longname') or symbol} ({symbol})"
        link = f"https://finance.yahoo.com/quote/{symbol}"
        snippet = q.get("exchange", "")
        results.append(_result(title, link, snippet, "Yahoo Finance"))
    for n in data.get("news", []):
        results.append(
            _result(
                n.get("title", ""),
                n.get("link", ""),
                n.get("publisher", ""),
                "Yahoo Finance News",
            )
        )
    return results


# ---------------------------------------------------------------------------
# Optional API-backed engines (used only when env vars are present)
# ---------------------------------------------------------------------------

def search_tavily(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": False,
    }
    data = _post_json(
        "https://api.tavily.com/search",
        payload,
        timeout=timeout,
        headers={"Authorization": "Bearer " + api_key},
    )
    results: List[Dict[str, str]] = []
    for item in data.get("results", []):
        results.append(
            _result(
                item.get("title", ""),
                item.get("url", ""),
                item.get("content", ""),
                "Tavily",
            )
        )
    return results


def search_brave(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    api_key = os.getenv("BRAVE_API_KEY", "").strip()
    if not api_key:
        return []
    url = "https://api.search.brave.com/res/v1/web/search?q=" + urllib.parse.quote(query) + "&count=" + str(max_results)
    headers = {
        "X-Subscription-Token": api_key,
        "Accept": "application/json",
    }
    page = _fetch(url, timeout=timeout, headers=headers)
    try:
        data = json.loads(page)
    except json.JSONDecodeError:
        return []
    results: List[Dict[str, str]] = []
    for item in data.get("web", {}).get("results", []):
        results.append(
            _result(
                item.get("title", ""),
                item.get("url", ""),
                item.get("description", ""),
                "Brave",
            )
        )
    return results


def search_searxng(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    base = os.getenv("SEARXNG_BASE_URL", "").strip().rstrip("/")
    if not base:
        return []
    url = base + "/search?q=" + urllib.parse.quote(query) + "&format=json"
    try:
        data = json.loads(_fetch(url, timeout=timeout))
    except Exception:
        return []
    results: List[Dict[str, str]] = []
    for item in data.get("results", []):
        results.append(
            _result(
                item.get("title", ""),
                item.get("url", ""),
                item.get("content", ""),
                "SearXNG",
            )
        )
    return results


ENGINES = {
    "tavily": search_tavily,
    "brave": search_brave,
    "searxng": search_searxng,
    "ddg": search_ddg,
    "bing": search_bing,
    "sogou": search_sogou,
    "so360": search_so360,
    "baidu": search_baidu,
    "arxiv": search_arxiv,
    "openalex": search_openalex,
    "semanticscholar": search_semanticscholar,
    "crossref": search_crossref,
    "github": search_github,
    "gitlab": search_gitlab,
    "stackoverflow": search_stackoverflow,
    "npm": search_npm,
    "hackernews": search_hackernews,
    "reddit": search_reddit,
    "wikipedia": search_wikipedia,
    "yahoo_finance": search_yahoo_finance,
}

CATEGORY_ENGINES = {
    "general": ["bing", "sogou", "so360", "baidu", "wikipedia"],
    # 注：mojeek/ecosia/startpage/qwant 仅浏览器版(search_browser.py)支持，轻量版不可列出
    "external": ["bing", "so360", "baidu", "ddg", "brave", "searxng", "wikipedia"],
    "academic": ["arxiv", "openalex", "semanticscholar", "crossref", "bing"],
    "tech": ["github", "gitlab", "stackoverflow", "npm", "hackernews", "bing"],
    "news": ["bing", "sogou", "so360", "baidu", "hackernews"],
    "finance": ["yahoo_finance", "bing", "sogou", "so360", "baidu"],
    "social": ["reddit", "hackernews", "sogou", "bing"],
    "all": [
        "arxiv", "openalex", "semanticscholar", "crossref",
        "github", "gitlab", "stackoverflow", "npm", "hackernews",
        "reddit", "wikipedia", "yahoo_finance",
        "ddg", "bing", "sogou", "so360", "baidu",
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


def _resolve_engines(explicit: str, query: str, category: str = "general") -> List[str]:
    """Choose engines by explicit list, category, or auto (API first + defaults)."""
    if explicit:
        parts = [e.strip().lower() for e in explicit.split(",") if e.strip()]
        if "auto" in parts:
            return _resolve_engines("", query, category)
        return parts
    if category and category in CATEGORY_ENGINES:
        chosen = list(CATEGORY_ENGINES[category])
    else:
        chosen = []
    # Add configured API providers when they exist.
    for name in ("tavily", "brave", "searxng"):
        if name == "tavily" and os.getenv("TAVILY_API_KEY") and name not in chosen:
            chosen.insert(0, name)
        elif name == "brave" and os.getenv("BRAVE_API_KEY") and name not in chosen:
            chosen.insert(0, name)
        elif name == "searxng" and os.getenv("SEARXNG_BASE_URL") and name not in chosen:
            chosen.insert(0, name)
    if not chosen:
        chosen = list(DEFAULT_ENGINES)
    if _has_cjk(query):
        # 中文查询优先国内引擎，避免 Bing/DDG 在国内抽风或超时。
        chosen.sort(key=lambda e: DOMESTIC_FIRST.index(e) if e in DOMESTIC_FIRST else 99)
    return chosen


def _is_ad_result(url: str, title: str, level: str) -> bool:
    """Adjustable ad filtering. High level may also remove some real content."""
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
    out = []
    for r in results:
        if not _is_ad_result(r.get("url", ""), r.get("title", ""), level):
            out.append(r)
    return out


def _filter_site(results: List[Dict[str, str]], site: str) -> List[Dict[str, str]]:
    if not site:
        return results
    site = site.lower().lstrip(".").rstrip("/")
    return [
        r for r in results
        if site in urllib.parse.urlparse(r.get("url", "")).netloc.lower()
    ]


def _score_results(results: List[Dict[str, str]], query: str, precision: int = 50) -> List[Dict[str, str]]:
    """Sort by how many query terms appear in title/url/snippet."""
    if precision <= 0:
        return results
    terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 1]

    def score(r):
        text = f"{r.get('title', '')} {r.get('url', '')} {r.get('snippet', '')}".lower()
        return sum(text.count(t) for t in terms)

    return sorted(results, key=score, reverse=True)


def run_search(query: str, max_results: int, engines: List[str], timeout: int) -> Dict:
    all_results: List[Dict[str, str]] = []
    stats: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    # Fetch extra candidates so ad filtering / precision ranking still has enough results.
    fetch_limit = max_results * 2
    for engine in engines:
        fn = ENGINES.get(engine)
        if not fn:
            errors[engine] = "unsupported engine"
            continue
        try:
            results = fn(query, fetch_limit, timeout)
            stats[engine] = len(results)
            all_results.extend(results)
            if not results:
                errors[engine] = "no results"
            elif engine == "bing" and _low_relevance(results, query):
                errors[engine] = "low_relevance"
        except Exception as exc:
            stats[engine] = 0
            errors[engine] = str(exc)
            # Keep the helper resilient: one failing engine should not kill all.
            sys.stderr.write(f"[{engine}] error: {exc}\n")
        # Small delay between free HTML requests to avoid being rate-limited.
        if engine in ("ddg", "bing", "sogou", "so360", "baidu"):
            time.sleep(0.4)
    results = _dedupe(all_results)[:max_results * 3]
    return {
        "query": query,
        "results": results,
        "engine_stats": stats,
        "engine_errors": errors,
    }


def _format_plain(data: Dict) -> str:
    lines = []
    results = data["results"]
    if not results:
        return "没有搜索到结果。可尝试换关键词或稍后再试。"
    lines.append(f"共 {len(results)} 条结果（引擎统计: {data['engine_stats']}）")
    if data.get("engine_errors"):
        lines.append(f"引擎异常: {data['engine_errors']}")
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   URL: {r['url']}")
        if r["snippet"]:
            lines.append(f"   摘要: {r['snippet']}")
        lines.append(f"   来源: {r['source']}")
        lines.append("")
    return "\n".join(lines).strip()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="DeepSeek Web Search helper for OpenClaw (stdlib-only, multi-engine)."
    )
    parser.add_argument("query_pos", nargs="?", help="Search query (positional)")
    parser.add_argument("--query", help="Search query")
    parser.add_argument("--max-results", type=int, default=6, help="Max results (default: 6)")
    parser.add_argument(
        "--engines",
        default="",
        help="Comma-separated engines: ddg,bing,sogou,so360,baidu,arxiv,openalex,semanticscholar,crossref,github,gitlab,stackoverflow,npm,hackernews,reddit,wikipedia,yahoo_finance,tavily,brave,searxng",
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
    parser.add_argument("--site", default="", help="只保留指定域名下的结果，例如 github.com")
    parser.add_argument(
        "--precision",
        type=int,
        default=50,
        help="搜索精准度排序 0-100，越高越优先展示关键词重合度高的结果",
    )
    parser.add_argument("--cacert", default=None, help="自定义 CA 证书包路径（PEM）")
    parser.add_argument("--timeout", type=int, default=8, help="Per-request timeout seconds")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--brief", action="store_true", help="精简 JSON 输出（省 token，供大模型直接消费）")
    args = parser.parse_args(argv)

    global CA_CERT
    if args.cacert:
        CA_CERT = args.cacert

    query = (args.query or args.query_pos or "").strip()
    if not query:
        parser.print_help()
        return 2

    if args.exact and not query.startswith('"'):
        query = f'"{query.strip()}"'

    engines = _resolve_engines(args.engines, query, args.category)
    data = run_search(query, args.max_results, engines, args.timeout)

    data["results"] = _filter_results(data.get("results", []), args.ad_filter)
    if args.site:
        data["results"] = _filter_site(data["results"], args.site)
    data["results"] = _score_results(data["results"], query, args.precision)[: args.max_results]
    data["category"] = args.category
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
