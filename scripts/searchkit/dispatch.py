"""搜索调度（v1.22.0 批 C 自 search.py 搬迁；v1.25.0 压测优化）：
引擎选择(_resolve_engines, 中文优先国内) + 多引擎并发聚合(run_search, 单引擎失败不中断)
+ 纯文本输出(_format_plain)。
v1.25.0 压测优化（downloads/_search_stress 实测数据支撑）：
- P2 引擎并发：旧版串行 17 引擎 45-54s（每引擎 8s 超时+0.4s 间隔）；改
  ThreadPoolExecutor 并发（4 路），实测 all 类 ~50s → 预期 ~12s；
- P1 跳转壳解码：百度/360 结果全是加密跳转壳（实测百度 8 条壳去重坍缩只剩 1 条），
  聚合后并发解码为真实 URL 再去重——去重不再误杀，AI 引用来源直接是真实站点；
- P5 验证码识别：搜狗匿名请求实测返回验证码页（5384B，零结果），引擎函数抛
  CaptchaError，engine_errors 如实标 "captcha suspected" 而非笼统 "no results"。"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from .adfilter import _has_cjk, _low_relevance
from .engines import CATEGORY_ENGINES, DOMESTIC_FIRST, ENGINES
from .http import DEFAULT_ENGINES, CaptchaError, NotConfiguredError
from .normalize import _dedupe
from .resolve import resolve_shell_urls

__all__ = ["_resolve_engines", "run_search", "_format_plain"]

# 引擎并发度：4 路实测对国内引擎无限速恶化（每引擎单请求），再多收益递减
_MAX_WORKERS = 4


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


def run_search(query: str, max_results: int, engines: List[str], timeout: int,
               resolve_shells: bool = True) -> Dict:
    all_results: List[Dict[str, str]] = []
    stats: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    # Fetch extra candidates so ad filtering / precision ranking still has enough results.
    fetch_limit = max_results * 2

    def _run_one(engine: str):
        """单引擎执行（线程池工作函数）：返回 (engine, results, error)。"""
        fn = ENGINES.get(engine)
        if not fn:
            return engine, [], "unsupported engine"
        try:
            return engine, fn(query, fetch_limit, timeout), ""
        except CaptchaError as exc:
            return engine, [], str(exc)
        except NotConfiguredError as exc:
            return engine, [], str(exc)
        except Exception as exc:
            # Keep the helper resilient: one failing engine should not kill all.
            sys.stderr.write(f"[{engine}] error: {exc}\n")
            return engine, [], str(exc)

    # P2 引擎并发：4 路线程池（各引擎独立 urllib 请求 + 正则，无共享可变状态；
    # CA_CERT 在 main() 解析期落定，无竞争）。单引擎失败不中断语义不变。
    workers = max(1, min(_MAX_WORKERS, len(engines)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        by_engine = {e: (r, err) for e, r, err in ex.map(_run_one, engines)}

    # 按声明顺序聚合（确定性输出，与旧串行版同序）
    for engine in engines:
        results, err = by_engine.get(engine, ([], "skipped"))
        stats[engine] = len(results)
        all_results.extend(results)
        if err:
            errors[engine] = err
        elif not results:
            errors[engine] = "no results"
        elif engine == "bing" and _low_relevance(results, query):
            errors[engine] = "low_relevance"

    # P1 跳转壳解码：真实 URL 再去重（修复壳 key 坍缩互杀）；
    # 失败保留原壳（诚实降级），--no-resolve 可关
    if resolve_shells:
        try:
            all_results = resolve_shell_urls(all_results)
        except Exception as exc:
            sys.stderr.write(f"[resolve] 跳过壳解码: {exc}\n")
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
