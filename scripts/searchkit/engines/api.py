"""API Key 引擎：tavily/brave/searxng（环境变量存在才启用）（v1.22.0 批 C 自 search.py 搬迁，零逻辑改动）。
依赖 searchkit.http 的公共请求件；注册表在 engines/__init__.py。"""
from typing import Dict, List

from ..http import _clean_html, _fetch, _post_json, _result
from ..normalize import _normalize_url

import json
import os
import urllib.parse


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
