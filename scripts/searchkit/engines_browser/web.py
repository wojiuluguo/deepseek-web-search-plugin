"""网页引擎（v1.22.0 结构优化批 2 自 searchkit/browser.py 搬迁，零逻辑改动）：bing/搜狗/360/东财/百度/DDG。"""
import random
import time
import urllib.parse
from typing import Dict, List

from .dom import _result, _safe_attr, _safe_text, _extract_from_items

__all__ = ["search_bing", "search_sogou", "search_so360", "search_eastmoney", "search_baidu", "search_ddg"]

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
