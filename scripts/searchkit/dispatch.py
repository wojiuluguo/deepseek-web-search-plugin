"""搜索调度（v1.22.0 批 C 自 search.py 搬迁，零逻辑改动）：
引擎选择(_resolve_engines, 中文优先国内) + 多引擎并发聚合(run_search, 单引擎失败不中断)
+ 纯文本输出(_format_plain)。CLI 参数解析留在 search.py main()。"""
import os
import sys
import time
from typing import Dict, List

from .adfilter import _has_cjk, _low_relevance
from .engines import CATEGORY_ENGINES, DOMESTIC_FIRST, ENGINES
from .http import DEFAULT_ENGINES
from .normalize import _dedupe

__all__ = ["_resolve_engines", "run_search", "_format_plain"]

def _resolve_engines(explicit: str, query: str, category: str = "general",
                     available=None, api_auto: bool = True) -> List[str]:
    """Choose engines by explicit list, category, or auto (API first + defaults).

    v1.22.0 批 D：统一分类表按模式可用性过滤——
    available: 该模式可用的引擎名集合（None=轻量版全表）；浏览器版传 browser.BROWSER_ENGINES。
    api_auto: 自动加入有 Key 的 tavily/brave/searxng（浏览器版无 API 引擎，传 False）。"""
    if explicit:
        parts = [e.strip().lower() for e in explicit.split(",") if e.strip()]
        if "auto" in parts:
            return _resolve_engines("", query, category, available, api_auto)
        return parts
    if category and category in CATEGORY_ENGINES:
        chosen = list(CATEGORY_ENGINES[category])
    else:
        chosen = []
    # 统一分类表 → 按本模式可用引擎过滤（默认轻量版 ENGINES；浏览器版传 BROWSER_ENGINES。
    # 如轻量版过滤 eastmoney/mojeek，浏览器版过滤 openalex/tavily 等）
    avail = set(ENGINES) if available is None else set(available)
    chosen = [e for e in chosen if e in avail]
    # Add configured API providers when they exist.
    if api_auto:
        for name in ("tavily", "brave", "searxng"):
            if name == "tavily" and os.getenv("TAVILY_API_KEY") and name not in chosen:
                chosen.insert(0, name)
            elif name == "brave" and os.getenv("BRAVE_API_KEY") and name not in chosen:
                chosen.insert(0, name)
            elif name == "searxng" and os.getenv("SEARXNG_BASE_URL") and name not in chosen:
                chosen.insert(0, name)
    if not chosen:
        chosen = [e for e in DEFAULT_ENGINES if e in avail]
    if _has_cjk(query):
        # 中文查询优先国内引擎，避免 Bing/DDG 在国内抽风或超时。
        chosen.sort(key=lambda e: DOMESTIC_FIRST.index(e) if e in DOMESTIC_FIRST else 99)
    return chosen


def run_search(query: str, max_results: int, engines: List[str], timeout: int) -> Dict:
    all_results: List[Dict[str, str]] = []
    stats: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    # Fetch extra candidates so ad filtering / precision ranking still has enough results.
    fetch_limit = max_results * 2
    for engine in engines:
        fn = ENGINES.get(engine)
        if not fn:
            errors[engine] = "unsupported engine"
            continue
        try:
            results = fn(query, fetch_limit, timeout)
            stats[engine] = len(results)
            all_results.extend(results)
            if not results:
                errors[engine] = "no results"
            elif engine == "bing" and _low_relevance(results, query):
                errors[engine] = "low_relevance"
        except Exception as exc:
            stats[engine] = 0
            errors[engine] = str(exc)
            # Keep the helper resilient: one failing engine should not kill all.
            sys.stderr.write(f"[{engine}] error: {exc}\n")
        # Small delay between free HTML requests to avoid being rate-limited.
        if engine in ("ddg", "bing", "sogou", "so360", "baidu"):
            time.sleep(0.4)
    results = _dedupe(all_results)[:max_results * 3]
    return {
        "query": query,
        "results": results,
        "engine_stats": stats,
        "engine_errors": errors,
    }


def _format_plain(data: Dict) -> str:
    lines = []
    results = data["results"]
    if not results:
        return "没有搜索到结果。可尝试换关键词或稍后再试。"
    lines.append(f"共 {len(results)} 条结果（引擎统计: {data.get('engine_stats', {})}）")
    if data.get("engine_errors"):
        lines.append(f"引擎异常: {data['engine_errors']}")
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title', '')}")
        lines.append(f"   URL: {r.get('url', '')}")
        if r.get("snippet"):
            lines.append(f"   摘要: {r['snippet']}")
        if r.get("source"):
            lines.append(f"   来源: {r['source']}")
        lines.append("")
    return "\n".join(lines).strip()
