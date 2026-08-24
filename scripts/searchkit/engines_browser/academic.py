"""学术引擎（v1.22.0 结构优化批 2 自 searchkit/browser.py 搬迁，零逻辑改动）：arXiv/维基。"""
import random
import time
import urllib.parse
from typing import Dict, List

from .dom import _result, _safe_attr, _safe_text, _extract_from_items

__all__ = ["search_arxiv_browser", "search_wikipedia_browser"]

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
