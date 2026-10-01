"""学术引擎（v1.22.0 结构优化批 2 自 searchkit/browser.py 搬迁，零逻辑改动）：arXiv/维基。"""
import random
import time
import urllib.parse
from typing import Dict, List

from .dom import _result, _safe_attr, _safe_text, _extract_from_items

__all__ = ["search_arxiv_browser", "search_wikipedia_browser"]

def search_arxiv_browser(page, query: str, max_results: int) -> List[Dict[str, str]]:
    """v1.25.0 普查修复：arxiv 结果标题 <p class="title"> 是纯文本无 <a>，旧
    title_sel="p.title a" 永远取不到 href → 从上线起抓空。标题取 p.title 文本、
    URL 取 p.list-title a（DOM 实测 2026-09）。"""
    url = "https://arxiv.org/search/?query=" + urllib.parse.quote(query) + "&searchtype=all"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_selector("li.arxiv-result", timeout=10000)
    except Exception:
        pass
    time.sleep(random.uniform(0.8, 1.5))
    items = page.locator("li.arxiv-result")
    return _extract_from_items(page, items, "p.title", "span.abstract-full", "arXiv", max_results,
                               url_sel="p.list-title a")


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
