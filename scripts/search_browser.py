#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Web Search — Playwright browser-simulation helper.

This script drives a real Chromium browser via Playwright, so search engines
see a genuine browser fingerprint instead of a plain HTTP client. It is more
likely to pass anti-bot checks than the stdlib-only search.py.

Requirements:
    pip install playwright
    python -m playwright install chromium

Usage examples:
    python search_browser.py "OpenClaw web_search provider"
    python search_browser.py --query "DeepSeek V4" --max-results 8 --json
    python search_browser.py --query "今天A股" --engines bing,sogou,so360,baidu

v1.22.0 批 D 拆分：实现移入 searchkit.browser（引擎/调度/过滤与轻量版共享，
消灭双表），本文件保留 CLI 入口 main() 与全部旧名 re-import——外部 import
路径零变化（auto_save_browser 仍可 from search_browser import run_search）。
"""

import argparse
import json
import sys

# ---- 拆分（v1.22.0 批 D）：实现移入 searchkit.browser，此处 re-import 保持旧名可用 ----
from searchkit.browser import *  # noqa: F401,F403
from searchkit.browser import (  # noqa: F401  （显式列出防 __all__ 遗漏）
    ENGINES, BROWSER_ENGINES, CATEGORY_ENGINES, DOMESTIC_FIRST, DEFAULT_ENGINES,
    USER_AGENTS, STEALTH_JS, _HAS_PLAYWRIGHT,
    _clean_text, _result, _safe_text, _safe_attr, _extract_from_items,
    _normalize_url, _dedupe, _is_error_result,
    _has_cjk, _low_relevance, _is_ad_result, _filter_results, _filter_site,
    _query_terms, _score_results,
    _resolve_engines, _parse_proxy, run_search, _format_plain,
)
# 全部 search_* 浏览器引擎函数
from searchkit.browser import (  # noqa: F401
    search_bing, search_sogou, search_so360, search_baidu, search_eastmoney,
    search_ddg, search_arxiv_browser, search_github_browser,
    search_stackoverflow_browser, search_wikipedia_browser, search_mojeek_browser,
    search_ecosia_browser, search_startpage_browser, search_qwant_browser,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="DeepSeek Web Search Playwright helper (real browser simulation)."
    )
    parser.add_argument("query_pos", nargs="?", help="Search query (positional)")
    parser.add_argument("--query", help="Search query")
    parser.add_argument("--max-results", type=int, default=6, help="Max results (default: 6)")
    parser.add_argument(
        "--engines",
        default="",
        help="Comma-separated engines: bing,sogou,so360,baidu,eastmoney,ddg,arxiv,github,stackoverflow,wikipedia（eastmoney=东方财富专业财经,无竞价广告；mojeek/ecosia/startpage/qwant 实测不可用，仅显式指定时生效）",
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
    parser.add_argument(
        "--proxy",
        default="",
        help="IP 伪装代理: http://127.0.0.1:7890 / socks5://host:port / http://user:pass@host:port",
    )
    parser.add_argument("--site", default="", help="只保留指定域名下的结果，例如 github.com")
    parser.add_argument(
        "--precision",
        type=int,
        default=50,
        help="搜索精准度排序 0-100，越高越优先展示关键词重合度高的结果",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--brief", action="store_true", help="精简 JSON 输出（省 token，供大模型直接消费）")
    parser.add_argument(
        "--safe",
        action="store_true",
        help="安全模式：恢复浏览器进程沙箱+站点隔离、拦挖矿/危险下载/弹窗（搜索可疑内容/打开陌生站点时用）",
    )
    parser.add_argument(
        "--stealth",
        choices=["full", "basic", "off"],
        default="full",
        help="浏览器伪装档位：full=全套（默认，playwright-stealth 深层指纹补丁，显著提升搜狗等风控站通过率）；basic=半套（自带伪装）；off=关闭",
    )
    args = parser.parse_args(argv)

    query = (args.query or args.query_pos or "").strip()
    if not query:
        parser.print_help()
        return 2

    if not _HAS_PLAYWRIGHT:
        print(
            "Playwright 未安装。请先执行:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    if args.exact and not query.startswith('"'):
        query = f'"{query.strip()}"'

    engines = _resolve_engines(args.engines, args.category, query)
    data = run_search(query, args.max_results, engines, proxy=args.proxy, safe=args.safe,
                      stealth=args.stealth)

    data["results"] = _filter_results(data.get("results", []), args.ad_filter)
    if args.site:
        data["results"] = _filter_site(data["results"], args.site)
    data["results"] = _score_results(data["results"], query, args.precision)[: args.max_results]
    data["category"] = args.category
    data["proxy"] = args.proxy or None
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
