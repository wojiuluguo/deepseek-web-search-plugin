"""开发者引擎（v1.22.0 结构优化批 2 自 searchkit/browser.py 搬迁，零逻辑改动）：GitHub/StackOverflow。"""
import random
import time
import urllib.parse
from typing import Dict, List

from .dom import _result, _safe_attr, _safe_text, _extract_from_items

__all__ = ["search_github_browser", "search_stackoverflow_browser"]

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
