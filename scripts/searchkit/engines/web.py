"""通用网页引擎：ddg/bing/sogou/so360/baidu/维基/雅虎财经（v1.22.0 批 C 自 search.py 搬迁，零逻辑改动）。
依赖 searchkit.http 的公共请求件；注册表在 engines/__init__.py。"""
from typing import Dict, List

from ..http import DEFAULT_USER_AGENT, _clean_html, _fetch, _post_json, _result
from ..normalize import _normalize_url

import html
import json
import re
import urllib.parse


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
