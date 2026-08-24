"""社区引擎：hackernews/reddit（v1.22.0 批 C 自 search.py 搬迁，零逻辑改动）。
依赖 searchkit.http 的公共请求件；注册表在 engines/__init__.py。"""
from typing import Dict, List

from ..http import DEFAULT_USER_AGENT, _clean_html, _fetch, _post_json, _result
from ..normalize import _normalize_url

import json
import urllib.parse


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
