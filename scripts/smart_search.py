#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Search — 自动识别查询类型，自动分配搜索引擎，失败自动换引擎/重搜

目标：搜得准、搜得稳、搜得安心。

用法：
    python smart_search.py --query "transformer 论文" --json
    python smart_search.py --query "python asyncio 报错" --json
    python smart_search.py --query "今天A股行情" --json
    python smart_search.py --query "OpenClaw" --browser --json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent

TYPE_KEYWORDS = {
    "academic": [
        "论文", "学术", "文献", "期刊", "研究", "arxiv", "paper", "thesis",
        "journal", "doi", "citation", "research", "综述", "影响因子",
    ],
    "tech": [
        "python", "javascript", "java", "go语言", "rust", "代码", "编程",
        "报错", "error", "bug", "github", "stackoverflow", "api", "sdk",
        "框架", "库", "开发", "部署", "docker", "kubernetes", "linux",
    ],
    "finance": [
        "股票", "股价", "基金", "财经", "汇率", "黄金", "期货", "财报",
        "a股", "美股", "港股", "理财", "经济", "finance", "market",
        "etf", "降息", "加息", "通胀", "gdp", "cpi",
        "金融", "证券", "股市", "投资", "债券", "外汇", "纳斯达克",
        "道琼斯", "恒生", "牛市", "熊市", "k线", "复盘",
    ],
    "news": [
        "新闻", "最新", "今天", "报道", "热点", "突发", "快讯", "news",
        "breaking", "时政", "国际", "国内",
    ],
    "social": [
        "知乎", "微博", "小红书", "公众号", "社区", "reddit", "forum",
        "贴吧", "论坛", "抖音", "b站",
    ],
    "external": [
        "openai", "google", "github", "english", "how to", "tutorial",
        "docs", "documentation", "api reference",
    ],
}


def detect_type(query: str) -> str:
    q = query.lower()
    scores = {}
    for typ, words in TYPE_KEYWORDS.items():
        score = sum(1 for w in words if w.lower() in q)
        if score:
            scores[typ] = score
    if not scores:
        # 含大量中文且不像学术/技术/财经/新闻，默认 general
        return "general"
    # 新闻/财经/技术/学术等优先级：取分最高；同分时按业务价值排序
    priority = ["academic", "tech", "finance", "news", "social", "external"]
    best = max(scores, key=lambda k: (scores[k], -priority.index(k) if k in priority else 0))
    return best


def run_attempt(query: str, category: str, browser: bool, max_results: int, safe: bool = False) -> Dict:
    script = BASE_DIR / "scripts" / ("search_browser.py" if browser else "search.py")
    cmd = [
        sys.executable,
        str(script),
        "--query",
        query,
        "--category",
        category,
        "--max-results",
        str(max_results),
        "--json",
    ]
    # 安全模式只对浏览器版有意义（search.py 是纯 requests，不碰可疑站点内容）
    if browser and safe:
        cmd.append("--safe")
    # 超时按引擎规模给：浏览器版每引擎最坏 ~36s（goto 25s+选择器 10s），
    # finance=3 引擎/general=4 引擎/all=9 引擎，固定 90s 会把引擎慢的整轮误杀；
    # 轻量版纯 requests 快，维持 90s
    timeout_sec = 240 if browser else 90
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout_sec,
        )
        data = json.loads(proc.stdout or "{}")
        data["_returncode"] = proc.returncode
        data["_stderr"] = proc.stderr[-300:]
        return data
    except Exception as exc:
        return {
            "query": query,
            "results": [],
            "engine_stats": {},
            "engine_errors": {"subprocess": str(exc)},
            "_returncode": -1,
            "_stderr": str(exc),
        }


def smart_search(query: str, browser: bool = False, max_results: int = 6, safe: bool = False) -> Dict:
    detected = detect_type(query)
    # 主分类 + 备用分类（不用 all，避免把 DuckDuckGo 等国外引擎带进国内默认兜底）
    categories = [detected, "general"]
    # 去掉重复
    seen = set()
    unique_categories = []
    for c in categories:
        if c not in seen:
            seen.add(c)
            unique_categories.append(c)

    attempts: List[Dict] = []
    final_results: List[Dict] = []
    final_errors: Dict[str, str] = {}
    final_category = detected

    for cat in unique_categories:
        data = run_attempt(query, cat, browser, max_results, safe)
        results = data.get("results", [])
        errors = data.get("engine_errors", {}) or {}
        attempts.append(
            {
                "category": cat,
                "result_count": len(results),
                "engine_errors": errors,
                "stderr": data.get("_stderr", ""),
            }
        )
        if results:
            final_results = results
            final_errors = errors
            final_category = cat
            break
        # 如果这轮全失败，下一轮自动换分类/引擎
        final_errors = errors

    summary = (
        f"自动识别查询类型：{detected}；"
        f"共尝试 {len(attempts)} 轮搜索；"
        f"最终使用分类：{final_category}；"
        f"获得 {len(final_results)} 条结果。"
    )
    if final_errors:
        summary += f" 部分引擎异常：{final_errors}"

    return {
        "query": query,
        "detected_type": detected,
        "final_category": final_category,
        "attempts": attempts,
        "summary": summary,
        "results": final_results,
        "engine_errors": final_errors,
    }


def _format_plain(data: Dict) -> str:
    lines = [data["summary"], ""]
    for i, r in enumerate(data.get("results", []), 1):
        lines.append(f"{i}. {r.get('title', '')}")
        lines.append(f"   URL: {r.get('url', '')}")
        if r.get("snippet"):
            lines.append(f"   摘要: {r['snippet']}")
        if r.get("source"):
            lines.append(f"   来源: {r['source']}")
        lines.append("")
    return "\n".join(lines).strip()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Smart Search - 自动识别类型、自动分配引擎、失败自动换引擎重搜"
    )
    parser.add_argument("--query", required=True, help="搜索内容")
    parser.add_argument("--max-results", type=int, default=6, help="每轮最多结果数")
    parser.add_argument("--browser", action="store_true", help="使用浏览器版搜索")
    parser.add_argument("--safe", action="store_true", help="安全模式（浏览器版生效）：沙箱+拦截挖矿/危险文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    data = smart_search(args.query, browser=args.browser, max_results=args.max_results, safe=args.safe)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(_format_plain(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
