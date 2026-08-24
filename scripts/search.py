#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Web Search — OpenClaw skill helper.

Zero-dependency multi-engine search script (stdlib only).
Default engines are domestic-friendly: Bing, Sogou, 360, Baidu.
Optionally uses Tavily / Brave / SearXNG when the corresponding environment
variables are present.

Usage examples:
    python search.py "OpenClaw web_search provider"
    python search.py --query "DeepSeek V4" --max-results 8 --json
    python search.py --query "Python asyncio" --engines ddg,bing --timeout 10

v1.22.0 批 C 拆分：实现移入 searchkit 包（http/normalize/engines/adfilter/dispatch），
本文件保留 CLI 入口 main() 与全部旧名 re-import——外部 import 路径零变化。
"""

import argparse
import json
import sys

# ---- 拆分（v1.22.0 批 C）：实现移入 searchkit 包，此处 re-import 保持旧名可用 ----
from searchkit.http import (  # noqa: F401
    DEFAULT_ENGINES, DEFAULT_USER_AGENT, CA_CERT, set_ca_cert,
    _clean_html, _fetch, _post_json, _result,
)
from searchkit.normalize import (  # noqa: F401
    _URL_KEEP_PARAMS, _normalize_url, _dedupe,
    ERROR_PAGE_STRONG, ERROR_PAGE_WEAK, _is_error_result,
)
from searchkit.engines import (  # noqa: F401
    ENGINES, CATEGORY_ENGINES, DOMESTIC_FIRST,
)
from searchkit.adfilter import (  # noqa: F401
    AD_HOST_KEYWORDS, AD_TITLE_KEYWORDS, AD_REDIRECT_MARKERS,
    _has_cjk, _low_relevance, _is_ad_result, _filter_results,
    _filter_site, _score_results,
)
from searchkit.dispatch import _resolve_engines, run_search, _format_plain  # noqa: F401
# 全部 search_* 引擎函数
from searchkit.engines import *  # noqa: F401,F403


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="DeepSeek Web Search helper for OpenClaw (stdlib-only, multi-engine)."
    )
    parser.add_argument("query_pos", nargs="?", help="Search query (positional)")
    parser.add_argument("--query", help="Search query")
    parser.add_argument("--max-results", type=int, default=6, help="Max results (default: 6)")
    parser.add_argument(
        "--engines",
        default="",
        help="Comma-separated engines: ddg,bing,sogou,so360,baidu,arxiv,openalex,semanticscholar,crossref,github,gitlab,stackoverflow,npm,hackernews,reddit,wikipedia,yahoo_finance,tavily,brave,searxng",
    )
    parser.add_argument(
        "--category",
        choices=["general", "external", "academic", "tech", "finance", "news", "social", "all"],
        default="general",
        help="搜索分类: general/external(外网)/academic(学术)/tech(技术)/finance(财经)/news(新闻)/social(社交)/all(全部)",
    )
    parser.add_argument(
        "--ad-filter",
        choices=["none", "low", "medium", "high"],
        default="medium",
        help="广告过滤强度: none=不过滤, low=低, medium=中(默认), high=高(可能误杀真实内容)",
    )
    parser.add_argument("--exact", action="store_true", help="精确匹配：给关键词加引号")
    parser.add_argument("--site", default="", help="只保留指定域名下的结果，例如 github.com")
    parser.add_argument(
        "--precision",
        type=int,
        default=50,
        help="搜索精准度排序 0-100，越高越优先展示关键词重合度高的结果",
    )
    parser.add_argument("--cacert", default=None, help="自定义 CA 证书包路径（PEM）")
    parser.add_argument("--timeout", type=int, default=8, help="Per-request timeout seconds")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--brief", action="store_true", help="精简 JSON 输出（省 token，供大模型直接消费）")
    args = parser.parse_args(argv)

    if args.cacert:
        set_ca_cert(args.cacert)  # v1.22.0 批 C：改为设置 searchkit.http.CA_CERT

    query = (args.query or args.query_pos or "").strip()
    if not query:
        parser.print_help()
        return 2

    if args.exact and not query.startswith('"'):
        query = f'"{query.strip()}"'

    engines = _resolve_engines(args.engines, query, args.category)
    data = run_search(query, args.max_results, engines, args.timeout)

    data["results"] = _filter_results(data.get("results", []), args.ad_filter)
    if args.site:
        data["results"] = _filter_site(data["results"], args.site)
    data["results"] = _score_results(data["results"], query, args.precision)[: args.max_results]
    data["category"] = args.category
    data["ad_filter"] = args.ad_filter
    data["precision"] = args.precision
    data["site"] = args.site or None

    # brief：给大模型省 token —— 只留 title/url/精简 snippet，去掉 engine_stats 等元数据
    if args.brief:
        data["results"] = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": (r.get("snippet", "") or "")[:120]}
            for r in data["results"]
        ]
        data.pop("engine_stats", None)
        data.pop("engine_errors", None)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=None if args.brief else 2))
    else:
        print(_format_plain(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
