#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross Search — 多引擎交叉验证搜索引擎

同一个搜索词，同时让 3 个不同搜索引擎各搜一份；
然后自动比对、合并、去重、标出单来源/可疑内容；
最后输出一份“给 AI 用的综合结果”。

超巨型模式（--mega）：
    全部搜索引擎同时上，同一个词并行搜 N 份（默认3），
    份内去重 → 跨份合并去重 → 没收敛就再来一轮，
    直到搜不出新东西为止。重复的被合并但保留“出现份数/引擎数”，
    结果又全又深：被越多份确认的排越前。

用法：
    python cross_search.py --query "OpenClaw" --json
    python cross_search.py --query "DeepSeek" --browser --engines ddg,bing,sogou --json
    python cross_search.py --query "AI 新闻" --max-results 8
    python cross_search.py --query "OpenClaw" --mega --json
"""

import argparse
import difflib
import json
import re
import sqlite3
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
OWN_DB = BASE_DIR / "index" / "own_search.db"

DEFAULT_ENGINES = ["so360", "sogou", "bing"]

CLICKBAIT_WORDS = (
    "震惊", "惊呆", "99%", "不转不是", "速看", "删前速看",
    "震惊世界", "看完彻底", "一分钟看懂", "重磅",
)

SUSPICIOUS_HOST_KEYWORDS = (
    "fake", "hoax", "scam", "spam", "clickbait", "ads",
    "taboola", "outbrain", "doubleclick",
)

REDIRECT_MARKERS = ("/link?", "url=", "click?", "rd?", "go.php", "jump?")


def run_single_engine(query: str, engine: str, max_results: int, browser: bool, ad_filter: str = "medium", safe: bool = False) -> List[Dict]:
    script = BASE_DIR / "scripts" / ("search_browser.py" if browser else "search.py")
    cmd = [
        sys.executable,
        str(script),
        "--query",
        query,
        "--engines",
        engine,
        "--max-results",
        str(max_results),
        "--ad-filter",
        ad_filter,
        "--json",
    ]
    if browser and safe:
        cmd.append("--safe")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=60,
        )
        data = json.loads(proc.stdout)
    except Exception:
        return []
    return data.get("results", [])


def run_full_copy(query: str, max_results: int, browser: bool, ad_filter: str, category: str, engines_csv: str, safe: bool = False) -> List[Dict]:
    """跑一“份”：全部引擎一次聚合搜索（sub-script 内部会自己汇总去重+广告过滤）。"""
    script = BASE_DIR / "scripts" / ("search_browser.py" if browser else "search.py")
    cmd = [
        sys.executable,
        str(script),
        "--query",
        query,
        "--max-results",
        str(max_results),
        "--ad-filter",
        ad_filter,
        "--json",
    ]
    if browser and safe:
        cmd.append("--safe")
    if engines_csv:
        cmd += ["--engines", engines_csv]
    else:
        cmd += ["--category", category or "all"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=120,
        )
        data = json.loads(proc.stdout)
    except Exception:
        return []
    return data.get("results", [])


def norm_url(url: str) -> str:
    try:
        u = urllib.parse.urlparse(url)
        netloc = u.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = re.sub(r"/+$", "", u.path or "")
        return f"{netloc}{path}"
    except Exception:
        return url.lower().strip()


def title_similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def check_local_index(url: str) -> bool:
    if not OWN_DB.exists():
        return False
    try:
        conn = sqlite3.connect(OWN_DB)
        row = conn.execute("SELECT 1 FROM pages WHERE url = ? LIMIT 1", (url,)).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def _check_local_index_bulk(urls: List[str]) -> Dict[str, bool]:
    """一次连接批量查本地索引，避免每条结果开关一次 SQLite。"""
    if not OWN_DB.exists() or not urls:
        return {u: False for u in urls}
    out = {u: False for u in urls}
    try:
        conn = sqlite3.connect(OWN_DB)
        for u in urls:
            if conn.execute("SELECT 1 FROM pages WHERE url = ? LIMIT 1", (u,)).fetchone():
                out[u] = True
        conn.close()
    except Exception:
        pass
    return out


def cross_search(query: str, engines: List[str], max_results: int, browser: bool, ad_filter: str = "medium", safe: bool = False) -> Dict:
    per_engine = {}
    all_items = []  # (result, engine)
    # 引擎并行：每个引擎是独立子进程，串行太慢（3 引擎 30-60s → 并行后≈最慢一个）
    with ThreadPoolExecutor(max_workers=min(len(engines), 6) or 1) as ex:
        future_map = {
            ex.submit(run_single_engine, query, engine, max_results, browser, ad_filter, safe): engine
            for engine in engines
        }
        for fut in as_completed(future_map):
            engine = future_map[fut]
            results = fut.result()
            per_engine[engine] = results
            for r in results:
                all_items.append((r, engine))

    merged: Dict[str, Dict] = {}
    for r, engine in all_items:
        title = r.get("title", "")
        url = r.get("url", "")
        key = norm_url(url) if url else title.lower().strip()
        if not key:
            continue
        if key not in merged:
            merged[key] = {
                "title": title,
                "url": url,
                "snippet": r.get("snippet", ""),
                "source_count": 0,
                "engines": [],
                "confidence": "low",
                "flags": [],
                "local_indexed": False,
            }
        item = merged[key]
        if engine not in item["engines"]:
            item["engines"].append(engine)
            item["source_count"] += 1
        # Use the first non-empty snippet.
        if not item["snippet"] and r.get("snippet"):
            item["snippet"] = r["snippet"]

    # Also merge by high title similarity when URLs differ.
    final_keys = list(merged.keys())
    for i in range(len(final_keys)):
        if final_keys[i] not in merged:
            continue
        a = merged[final_keys[i]]
        for j in range(i + 1, len(final_keys)):
            if final_keys[j] not in merged:
                continue
            b = merged[final_keys[j]]
            if a["url"] and b["url"] and norm_url(a["url"]) == norm_url(b["url"]):
                continue
            if title_similar(a["title"], b["title"]) >= 0.85:
                for eng in b["engines"]:
                    if eng not in a["engines"]:
                        a["engines"].append(eng)
                        a["source_count"] += 1
                if not a["snippet"]:
                    a["snippet"] = b["snippet"]
                # Remove the duplicate entry.
                del merged[final_keys[j]]

    # Confidence + flags + local index check（批量查一次库）.
    bulk_index = _check_local_index_bulk([it.get("url", "") for it in merged.values()])
    for item in merged.values():
        item["source_count"] = len(item["engines"])
        if item["source_count"] >= 3:
            item["confidence"] = "high"
        elif item["source_count"] == 2:
            item["confidence"] = "medium"
        else:
            item["confidence"] = "low"

        flags = []
        if item["source_count"] == 1:
            flags.append("single-source")
        host = urllib.parse.urlparse(item.get("url", "")).netloc.lower()
        if any(k in host for k in SUSPICIOUS_HOST_KEYWORDS):
            flags.append("suspicious-domain")
        title_l = item.get("title", "").lower()
        if any(k.lower() in title_l for k in CLICKBAIT_WORDS):
            flags.append("possible-clickbait")
        url_l = item.get("url", "").lower()
        if any(m in url_l for m in REDIRECT_MARKERS):
            flags.append("redirect-link")
        item["flags"] = flags
        item["local_indexed"] = bulk_index.get(item.get("url", ""), False)

    results = list(merged.values())
    # Sort: local index first? high confidence first, then source count, then title.
    results.sort(
        key=lambda x: (
            x["local_indexed"],
            {"high": 3, "medium": 2, "low": 1}.get(x["confidence"], 0),
            x["source_count"],
            x["title"].lower(),
        ),
        reverse=True,
    )

    high = sum(1 for r in results if r["confidence"] == "high")
    medium = sum(1 for r in results if r["confidence"] == "medium")
    low = sum(1 for r in results if r["confidence"] == "low")
    summary = (
        f"同一关键词在 {len(engines)} 个引擎共得到 {sum(len(v) for v in per_engine.values())} 条原始结果，"
        f"合并去重后 {len(results)} 条；其中高可信 {high} 条，中可信 {medium} 条，低可信/单来源 {low} 条。"
    )

    return {
        "query": query,
        "engines": engines,
        "engine_result_counts": {k: len(v) for k, v in per_engine.items()},
        "summary": summary,
        "results": results,
    }


def mega_search(
    query: str,
    copies: int,
    max_results: int,
    browser: bool,
    max_rounds: int = 2,
    ad_filter: str = "medium",
    engines_csv: str = "",
    safe: bool = False,
) -> Dict:
    """超巨型模式：全部引擎 × N 份并行 × 多轮收敛去重。

    流程：每轮同时跑 N 份“全引擎聚合搜索”→ 份间按 URL/标题合并去重 →
    记录每条结果被几份、几个引擎确认 → 下一轮搜不出新东西即收敛停止。
    重复结果不浪费：合并成一条，出现份数=深度凭证。"""
    merged: Dict[str, Dict] = {}
    rounds_info: List[Dict] = []
    converged = False
    total_raw = 0

    for round_no in range(1, max_rounds + 1):
        copy_results: List[List[Dict]] = []
        with ThreadPoolExecutor(max_workers=max(copies, 1)) as ex:
            futures = [
                ex.submit(run_full_copy, query, max_results, browser, ad_filter, "all", engines_csv, safe)
                for _ in range(copies)
            ]
            for f in as_completed(futures):
                copy_results.append(f.result())

        new_keys = 0
        raw_this_round = 0
        for copy_id, results in enumerate(copy_results):
            raw_this_round += len(results)
            for r in results:
                title = r.get("title", "")
                url = r.get("url", "")
                key = norm_url(url) if url else title.lower().strip()
                if not key:
                    continue
                engine = r.get("source", "") or "unknown"
                if key not in merged:
                    merged[key] = {
                        "title": title,
                        "url": url,
                        "snippet": r.get("snippet", ""),
                        "engines": [],
                        "copies": [],
                        "first_round": round_no,
                        "confidence": "low",
                        "flags": [],
                        "local_indexed": False,
                    }
                    new_keys += 1
                item = merged[key]
                if engine not in item["engines"]:
                    item["engines"].append(engine)
                if copy_id not in item["copies"]:
                    item["copies"].append(copy_id)
                if not item["snippet"] and r.get("snippet"):
                    item["snippet"] = r["snippet"]
        total_raw += raw_this_round
        rounds_info.append(
            {"round": round_no, "raw_results": raw_this_round, "new_unique": new_keys, "unique_so_far": len(merged)}
        )
        # 收敛判定：非首轮且没有新结果 → 稳定了，停；首轮就空 → 也停
        if new_keys == 0 and (round_no > 1 or not merged):
            converged = True
            break

    # 标题相似度二次合并（URL 不同但标题几乎一样的，算同一条）
    keys = list(merged.keys())
    for i in range(len(keys)):
        if keys[i] not in merged:
            continue
        a = merged[keys[i]]
        for j in range(i + 1, len(keys)):
            if keys[j] not in merged:
                continue
            b = merged[keys[j]]
            if title_similar(a["title"], b["title"]) >= 0.85:
                for eng in b["engines"]:
                    if eng not in a["engines"]:
                        a["engines"].append(eng)
                for c in b["copies"]:
                    if c not in a["copies"]:
                        a["copies"].append(c)
                if not a["snippet"]:
                    a["snippet"] = b["snippet"]
                del merged[keys[j]]

    # 可信度：被几个引擎 + 几份共同确认（批量查一次本地索引）
    bulk_index = _check_local_index_bulk([it.get("url", "") for it in merged.values()])
    for item in merged.values():
        item["appearances"] = len(item["copies"])
        n_eng = len(item["engines"])
        n_cop = len(item["copies"])
        if n_eng >= 3 or (n_eng >= 2 and n_cop >= 2):
            item["confidence"] = "high"
        elif n_eng == 2 or n_cop >= 2:
            item["confidence"] = "medium"
        else:
            item["confidence"] = "low"
        flags = []
        if n_eng == 1 and n_cop == 1:
            flags.append("single-source")
        host = urllib.parse.urlparse(item.get("url", "")).netloc.lower()
        if any(k in host for k in SUSPICIOUS_HOST_KEYWORDS):
            flags.append("suspicious-domain")
        title_l = item.get("title", "").lower()
        if any(k.lower() in title_l for k in CLICKBAIT_WORDS):
            flags.append("possible-clickbait")
        url_l = item.get("url", "").lower()
        if any(m in url_l for m in REDIRECT_MARKERS):
            flags.append("redirect-link")
        item["flags"] = flags
        item["local_indexed"] = bulk_index.get(item.get("url", ""), False)

    results = sorted(
        merged.values(),
        key=lambda x: (
            x["local_indexed"],
            {"high": 3, "medium": 2, "low": 1}.get(x["confidence"], 0),
            x["appearances"],
            len(x["engines"]),
        ),
        reverse=True,
    )
    all_engines = sorted({e for it in results for e in it["engines"]})
    high = sum(1 for r in results if r["confidence"] == "high")
    medium = sum(1 for r in results if r["confidence"] == "medium")
    low = sum(1 for r in results if r["confidence"] == "low")
    summary = (
        f"超巨型模式：{copies} 份×全引擎并行，共 {len(rounds_info)} 轮 {total_raw} 条原始结果，"
        f"收敛去重后 {len(results)} 条（{'已收敛' if converged else '达到轮数上限'}）；"
        f"高可信 {high}，中可信 {medium}，低可信/单来源 {low}。"
    )
    return {
        "query": query,
        "mode": "mega",
        "copies": copies,
        "rounds": rounds_info,
        "converged": converged,
        "engines_used": all_engines,
        "summary": summary,
        "results": results,
    }


def _format_plain(data: Dict) -> str:
    lines = [data["summary"], ""]
    if data.get("mode") == "mega":
        lines.append(f"份×引擎: {data.get('copies')} 份 | 收敛: {'是' if data.get('converged') else '否'}")
        for rd in data.get("rounds", []):
            lines.append(
                f"  第{rd['round']}轮: 原始 {rd['raw_results']} 条, 新增 {rd['new_unique']}, 累计 {rd['unique_so_far']}"
            )
        lines.append("")
    for i, r in enumerate(data.get("results", []), 1):
        appear = f" | {r.get('appearances')} 份确认" if r.get("appearances") else ""
        lines.append(f"{i}. [{r['confidence']}] {r['title']}{appear}")
        lines.append(f"   URL: {r['url']}")
        lines.append(f"   来源引擎: {', '.join(r['engines'])}")
        if r["flags"]:
            lines.append(f"   标记: {', '.join(r['flags'])}")
        if r["local_indexed"]:
            lines.append("   本地索引: 已收录")
        lines.append("")
    return "\n".join(lines).strip()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cross Search - 多引擎交叉验证，输出一份给AI的综合结果"
    )
    parser.add_argument("--query", required=True, help="搜索标题/关键词")
    parser.add_argument(
        "--engines",
        default=",".join(DEFAULT_ENGINES),
        help="逗号分隔的引擎，默认 so360,sogou,bing",
    )
    parser.add_argument("--max-results", type=int, default=5, help="每个引擎取多少条")
    parser.add_argument("--browser", action="store_true", help="使用浏览器版搜索")
    parser.add_argument(
        "--mega",
        action="store_true",
        help="超巨型模式：全部引擎同时上，同词并行搜 N 份，多轮汇聚去重直到收敛",
    )
    parser.add_argument("--copies", type=int, default=3, help="mega 模式并行份数（默认 3）")
    parser.add_argument("--rounds", type=int, default=2, help="mega 模式最大轮数（默认 2，收敛即提前停）")
    parser.add_argument(
        "--ad-filter",
        choices=["none", "low", "medium", "high"],
        default="medium",
        help="广告过滤强度（传给底层搜索引擎，默认 medium）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument(
        "--safe",
        action="store_true",
        help="安全模式（需 --browser）：底层浏览器搜索恢复进程沙箱+站点隔离、拦挖矿/危险下载/弹窗",
    )
    args = parser.parse_args(argv)

    engines = [e.strip().lower() for e in args.engines.split(",") if e.strip()]
    if not engines:
        engines = DEFAULT_ENGINES

    if args.mega:
        data = mega_search(
            args.query,
            copies=max(1, args.copies),
            max_results=args.max_results,
            browser=args.browser,
            max_rounds=max(1, args.rounds),
            ad_filter=args.ad_filter,
            engines_csv=",".join(engines) if args.engines and args.engines != ",".join(DEFAULT_ENGINES) else "",
            safe=args.safe,
        )
    else:
        data = cross_search(args.query, engines, args.max_results, args.browser, args.ad_filter, safe=args.safe)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(_format_plain(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
