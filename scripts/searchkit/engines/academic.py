"""学术引擎：arxiv/openalex/semanticscholar/crossref（v1.22.0 批 C 自 search.py 搬迁，零逻辑改动）。
依赖 searchkit.http 的公共请求件；注册表在 engines/__init__.py。"""
from typing import Dict, List

from ..http import _clean_html, _fetch, _post_json, _result
from ..normalize import _normalize_url

import json
import urllib.parse
import xml.etree.ElementTree as ET


def search_arxiv(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    """arXiv API: academic papers."""
    url = (
        "https://export.arxiv.org/api/query?search_query=all:"
        + urllib.parse.quote(query)
        + "&start=0&max_results="
        + str(max_results)
    )
    page = _fetch(url, timeout=timeout)
    root = ET.fromstring(page)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results: List[Dict[str, str]] = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", default="", namespaces=ns) or ""
        link = entry.findtext("atom:id", default="", namespaces=ns) or ""
        summary = entry.findtext("atom:summary", default="", namespaces=ns) or ""
        results.append(_result(title, link, summary, "arXiv"))
    return results


def search_openalex(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = "https://api.openalex.org/works?search=" + urllib.parse.quote(query) + "&per-page=" + str(max_results)
    data = json.loads(_fetch(url, timeout=timeout, headers={"Accept": "application/json"}))
    results: List[Dict[str, str]] = []
    for item in data.get("results", []):
        title = item.get("display_name", "")
        doi = item.get("doi", "")
        oid = item.get("id", "")
        link = doi or oid or ""
        snippet = str(item.get("publication_year", ""))
        results.append(_result(title, link, snippet, "OpenAlex"))
    return results


def search_semanticscholar(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search?query="
        + urllib.parse.quote(query)
        + "&limit="
        + str(max_results)
        + "&fields=title,url,abstract"
    )
    data = json.loads(_fetch(url, timeout=timeout, headers={"Accept": "application/json"}))
    results: List[Dict[str, str]] = []
    for item in data.get("data", []):
        results.append(
            _result(
                item.get("title", ""),
                item.get("url", ""),
                item.get("abstract") or "",
                "Semantic Scholar",
            )
        )
    return results


def search_crossref(query: str, max_results: int, timeout: int) -> List[Dict[str, str]]:
    url = "https://api.crossref.org/works?query=" + urllib.parse.quote(query) + "&rows=" + str(max_results)
    data = json.loads(_fetch(url, timeout=timeout, headers={"Accept": "application/json"}))
    results: List[Dict[str, str]] = []
    for item in data.get("message", {}).get("items", []):
        title = (item.get("title") or [""])[0]
        link = item.get("URL", "")
        snippet = ", ".join(item.get("container-title", []) or [])
        results.append(_result(title, link, snippet, "Crossref"))
    return results
