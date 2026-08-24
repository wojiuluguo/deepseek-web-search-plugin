"""开发者引擎：github/gitlab/stackoverflow/npm（v1.22.0 批 C 自 search.py 搬迁，零逻辑改动）。
依赖 searchkit.http 的公共请求件；注册表在 engines/__init__.py。"""
from typing import Dict, List

from ..http import _clean_html, _fetch, _post_json, _result
from ..normalize import _normalize_url

import json
import urllib.parse


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
