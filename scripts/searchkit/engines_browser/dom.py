"""DOM 提取件（v1.22.0 结构优化批 2 自 searchkit/browser.py 搬迁，零逻辑改动）：
结果构造/安全取文本/取属性/条目批量提取——14 个浏览器引擎共用。"""
import urllib.parse
from typing import Dict, List

__all__ = ["_clean_text", "_result", "_safe_text", "_safe_attr", "_extract_from_items"]


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
