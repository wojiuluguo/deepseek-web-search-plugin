"""境外备选引擎（v1.22.0 结构优化批 2 自 searchkit/browser.py 搬迁，零逻辑改动）：Mojeek/Ecosia/Startpage/Qwant——实测常不可用，仅显式指定时生效。"""
import random
import time
import urllib.parse
from typing import Dict, List

from .dom import _result, _safe_attr, _safe_text, _extract_from_items

__all__ = ["search_mojeek_browser", "search_ecosia_browser", "search_startpage_browser", "search_qwant_browser"]

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
