#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search and Cache — 搜索后自动检测并缓存媒体（不自动下载）

逻辑：
1. 先用智能搜索找到相关结果；
2. 自动打开每个结果页面，检测有没有视频/音频/图片/文件；
3. 检测到就直接保存到本地缓存；
4. 默认只缓存，不下载；想要完整下载时加 --download。

用法：
    python search_and_cache.py --query "B站 猫 视频" --json
    python search_and_cache.py --query "抖音 风景" --browser --json
    python search_and_cache.py --query "音乐" --download --json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = BASE_DIR / "downloads" / "cache" / "search_cache"


def run_search(query: str, max_results: int, browser: bool, safe: bool = False) -> Dict:
    script = BASE_DIR / "scripts" / "smart_search.py"
    cmd = [
        sys.executable,
        str(script),
        "--query",
        query,
        "--max-results",
        str(max_results),
        "--json",
    ]
    if browser:
        cmd.append("--browser")
    if safe:
        cmd.append("--safe")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=120,
    )
    try:
        return json.loads(proc.stdout or "{}")
    except Exception:
        return {"results": [], "summary": f"搜索失败: {proc.stderr[-300:]}"}


def cache_url(url: str, cache_dir: Path, method: str, media_type: str = "", safe: bool = False) -> Dict:
    script = BASE_DIR / "scripts" / "auto_save_browser.py"
    cmd = [
        sys.executable,
        str(script),
        "--url",
        url,
        "--method",
        method,
        "--output-dir",
        str(cache_dir),
        "--json",
    ]
    if media_type:
        cmd += ["--media-type", media_type]
    if safe:
        cmd.append("--safe")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=180,
    )
    try:
        data = json.loads(proc.stdout or "{}")
    except Exception:
        data = {"error": proc.stderr[-300:]}
    data["_url"] = url
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Search and Cache - 搜索后自动检测并缓存媒体，不自动下载"
    )
    parser.add_argument("--query", required=True, help="搜索内容")
    parser.add_argument("--max-results", type=int, default=3, help="检查前几个搜索结果（默认3）")
    parser.add_argument("--browser", action="store_true", help="使用浏览器版搜索")
    parser.add_argument("--download", action="store_true", help="检测到媒体后直接下载完整文件（默认只缓存）")
    parser.add_argument(
        "--media-type",
        default="",
        help="只缓存/下载指定类型: video,audio,image 任意逗号组合（默认全部）",
    )
    parser.add_argument("--cache-dir", default=None, help="缓存目录")
    parser.add_argument("--safe", action="store_true", help="安全模式：沙箱+拦截挖矿/危险文件+落盘白名单（可疑站点用）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    cache_dir = Path(args.cache_dir).expanduser().resolve() if args.cache_dir else DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    search_data = run_search(args.query, args.max_results, args.browser, args.safe)
    results = search_data.get("results", [])
    search_summary = search_data.get("summary", "")

    checked = []
    cached_files: List[Dict] = []
    errors = []

    for r in results[: args.max_results]:
        url = r.get("url", "")
        if not url:
            continue
        # 下载模式用 chain；缓存模式按 cache→browser→harvest 多种方式互补，一个不行换下一个。
        methods = ["chain"] if args.download else ["cache", "browser", "harvest"]
        cache_result = None
        for method in methods:
            cache_result = cache_url(url, cache_dir, method, args.media_type, args.safe)
            if cache_result.get("saved"):
                break
        saved = cache_result.get("saved", [])
        checked.append(
            {
                "url": url,
                "title": r.get("title", ""),
                "cached_count": len(saved),
                "method": cache_result.get("method", ""),
                "error": cache_result.get("error"),
            }
        )
        for item in saved:
            item["source_url"] = url
            item["source_title"] = r.get("title", "")
            cached_files.append(item)
        if cache_result.get("error"):
            errors.append({"url": url, "error": cache_result["error"]})

    data = {
        "query": args.query,
        "search_summary": search_summary,
        "cache_dir": str(cache_dir),
        "checked_urls": checked,
        "cached_files": cached_files,
        "cached_count": len(cached_files),
        "errors": errors,
        "mode": "download" if args.download else "cache-only",
        "note": "默认只缓存，不下载。需要完整下载时加 --download。",
    }

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(data["search_summary"])
        print(f"缓存目录: {data['cache_dir']}")
        print(f"检测到并缓存/下载文件数: {data['cached_count']}")
        for i, item in enumerate(cached_files, 1):
            print(f"{i}. {item.get('path')} ({item.get('size', 0)} bytes) [{item.get('kind', '')}]")
        if errors:
            print("错误:")
            for e in errors:
                print(f"  {e['url']}: {e['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
