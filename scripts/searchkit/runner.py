"""调度器公共执行件（v1.22.0 批 E）：统一调用 search.py / search_browser.py 子进程。

此前 smart_search / cross_search / own_search 各写一份
「选脚本→拼参数→subprocess→解析 JSON」，超时策略各自为政
（240/90、平 60、60+n×40/8、300）。统一到本模块：
- 一处维护命令行拼装（--safe 仅浏览器版有效等差异在此吸收）
- 同一套超时公式 auto_timeout()（按实际解析出的引擎数×模式最坏耗时估算）
- 统一返回信封 {ok, data, returncode, stderr, error, timed_out, timeout_sec}

纯 stdlib 子进程启动器，不 import playwright/auto_save 链
（browser=True 时才惰性 import searchkit.browser 取可用引擎表数引擎数）。"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

__all__ = ["run_search_cli", "auto_timeout"]

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_SEARCH_LW = _SCRIPTS_DIR / "search.py"
_SEARCH_BR = _SCRIPTS_DIR / "search_browser.py"


def auto_timeout(n_engines: int, browser: bool) -> int:
    """按引擎数×模式估子进程超时：
    浏览器版每引擎最坏 ~40s（goto 25s + 选择器 10s + 拟人停顿），
    轻量版纯 requests ~8s；基础 60s 兜启动/解析开销。
    引擎慢的整轮不再被固定上限误杀（此前 smart 240s 会被 finance×9 引擎撑爆）。"""
    return 60 + max(1, n_engines) * (40 if browser else 8)


def _count_engines(engines_csv: str, query: str, category: str, browser: bool) -> int:
    """数这一轮实际会上场的引擎数（显式列表直接数；分类走统一调度解析，
    含 env 里有 Key 的 API 引擎自动插入——与子进程内真实行为同口径）。"""
    if engines_csv:
        return len([e for e in engines_csv.split(",") if e.strip()])
    from .dispatch import _resolve_engines
    if browser:
        from .browser import BROWSER_ENGINES  # 惰性：即将拉起 playwright 子进程， import 代价可忽略
        return len(_resolve_engines("", query, category, available=BROWSER_ENGINES, api_auto=False))
    return len(_resolve_engines("", query, category))


def run_search_cli(
    query: str,
    *,
    browser: bool = False,
    engines: Optional[Union[str, List[str]]] = None,
    category: Optional[str] = None,
    max_results: int = 6,
    ad_filter: str = "medium",
    precision: Optional[int] = None,
    site: str = "",
    safe: bool = False,
    timeout: Optional[int] = None,
) -> Dict:
    """跑一次底层搜索 CLI（search.py 轻量版 / search_browser.py 浏览器版）。

    返回统一信封：
        ok          子进程跑完且 stdout 解析出 JSON（结果好坏看 data["results"]）
        data        子进程输出的 JSON dict（失败时为 {}）
        returncode  子进程退出码（未跑起来为 -1）
        stderr      stderr 末尾 500 字符
        error       超时/启动失败/解析失败的原因（成功为 ""）
        timed_out   是否被超时杀掉
        timeout_sec 本轮实际使用的超时秒数

    v1.22.0 模式审计：precision/site 透传补齐（ad_filter 原有），
    None/空 = 不传参走子进程默认值。"""
    engines_csv = ",".join(engines) if isinstance(engines, (list, tuple)) else (engines or "")
    if timeout is None:
        timeout = auto_timeout(_count_engines(engines_csv, query, category or "general", browser), browser)

    script = _SEARCH_BR if browser else _SEARCH_LW
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
    if precision is not None:
        cmd += ["--precision", str(precision)]
    if site:
        cmd += ["--site", site]
    if engines_csv:
        cmd += ["--engines", engines_csv]
    elif category:
        cmd += ["--category", category]
    # 安全模式只对浏览器版有意义（search.py 纯 requests，不碰可疑站点内容）
    if browser and safe:
        cmd.append("--safe")

    envelope = {
        "ok": False, "data": {}, "returncode": -1,
        "stderr": "", "error": "", "timed_out": False, "timeout_sec": timeout,
    }
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        envelope["error"] = f"timeout(>{timeout}s)"
        envelope["timed_out"] = True
        return envelope
    except Exception as exc:
        envelope["error"] = str(exc)
        return envelope

    envelope["returncode"] = proc.returncode
    envelope["stderr"] = (proc.stderr or "")[-500:]
    try:
        envelope["data"] = json.loads(proc.stdout or "{}")
    except Exception:
        envelope["error"] = "stdout not JSON"
        return envelope
    envelope["ok"] = True
    return envelope
