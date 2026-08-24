"""浏览器引擎层（v1.22.0 批 D 自 search_browser.py 搬迁，逻辑零改动）：
Playwright 驱动真 Chromium 搜索，14 个 page 级引擎 + BROWSER_ENGINES 注册表 +
playwright 版 run_search/代理解析/纯文本输出。

消灭双表：归一/去重/广告过滤/精准度排序/分类表全部复用 searchkit 共享模块，
本文件只保留浏览器特有部分（DOM 提取、UA 轮换、伪装、安全基建挂钩）。

依赖：可选 playwright（未装时 _HAS_PLAYWRIGHT=False，run_search 返回提示）；
可选 auto_save_browser 安全基建（挪走时退化为普通模式）。
"""
import random
import re
import sys
import time
import urllib.parse
from pathlib import Path as _P
from typing import Dict, List

# scripts/ 目录入 path（import auto_save_browser 用；searchkit 位于 scripts/ 下）
_scripts_dir = str(_P(__file__).resolve().parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# 安全模式基建复用（v1.22.0 模式审计修复：直接用 auto_save.browser_base 单一实现，
# 不再从下载门面 auto_save_browser 转载——搜索包不反向依赖下载门面，
# 也消灭了此处曾有的 _browser_launch_args 复制副本漂移问题）
try:
    from auto_save.browser_base import _setup_safe_mode as _SETUP_SAFE_MODE
    from auto_save.browser_base import _browser_launch_args as _BROWSER_LAUNCH_ARGS
    from auto_save.browser_base import _apply_stealth as _APPLY_STEALTH
except ImportError:  # auto_save 包不可用时退化为普通模式
    def _SETUP_SAFE_MODE(context, page):  # type: ignore
        return {}

    def _BROWSER_LAUNCH_ARGS(safe):  # type: ignore
        # 与 browser_base 同口径：safe 时必须恢复进程沙箱
        args = ["--disable-blink-features=AutomationControlled"]
        if not safe:
            args += ["--disable-features=IsolateOrigins,site-per-process", "--no-sandbox"]
        return args

    def _APPLY_STEALTH(context, mode):  # type: ignore
        # 兜底：退回半套伪装（STEALTH_JS 下面自带）
        context.add_init_script(STEALTH_JS)
        return "basic"

try:
    from playwright.sync_api import sync_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    # 不在 import 阶段 sys.exit：被 auto_save_browser 等脚本 import 时会把宿主进程一起杀死。
    # 真正用到时（run_search/main）再报错。
    _HAS_PLAYWRIGHT = False

# ---- 共享件（批 D 消灭双表：不再各自复制一份） ----
from .adfilter import (  # noqa: F401
    AD_HOST_KEYWORDS, AD_TITLE_KEYWORDS, AD_REDIRECT_MARKERS,  # noqa: F401
    _has_cjk, _low_relevance, _is_ad_result, _filter_results, _filter_site,  # noqa: F401
    _query_terms, _score_results,  # noqa: F401
)
from .normalize import (  # noqa: F401
    _URL_KEEP_PARAMS, _normalize_url, _dedupe,  # noqa: F401
    ERROR_PAGE_STRONG, ERROR_PAGE_WEAK, _is_error_result,  # noqa: F401
)
from .engines import CATEGORY_ENGINES, DOMESTIC_FIRST  # noqa: F401
from .http import DEFAULT_ENGINES  # noqa: F401

__all__ = [
    "ENGINES", "BROWSER_ENGINES", "CATEGORY_ENGINES", "DOMESTIC_FIRST", "DEFAULT_ENGINES",
    "USER_AGENTS", "STEALTH_JS", "_HAS_PLAYWRIGHT",
    "AD_HOST_KEYWORDS", "AD_TITLE_KEYWORDS", "AD_REDIRECT_MARKERS",
    "ERROR_PAGE_STRONG", "ERROR_PAGE_WEAK",
    "_clean_text", "_result", "_safe_text", "_safe_attr", "_extract_from_items",
    "_normalize_url", "_dedupe", "_is_error_result",
    "_has_cjk", "_low_relevance", "_is_ad_result", "_filter_results", "_filter_site",
    "_query_terms", "_score_results",
    "_resolve_engines", "_parse_proxy", "run_search", "_format_plain",
] + [
    "search_bing", "search_sogou", "search_so360", "search_baidu", "search_eastmoney",
    "search_ddg", "search_arxiv_browser", "search_github_browser",
    "search_stackoverflow_browser", "search_wikipedia_browser", "search_mojeek_browser",
    "search_ecosia_browser", "search_startpage_browser", "search_qwant_browser",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Edge（Windows 出厂默认浏览器，国内占比极高）
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.51",
]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en']
});
"""


# ---- 拆分（v1.22.0 结构优化批 2）：DOM 提取件 + 14 浏览器引擎移入 engines_browser 包 ----
# 本模块保留调度层（run_search/_resolve_engines/_parse_proxy/_format_plain）；
# 此处 re-import 保持旧名（search_browser/searchkit.browser 的外部 import 零变化）。
from .engines_browser import BROWSER_ENGINES  # noqa: F401
from .engines_browser.dom import (  # noqa: F401
    _clean_text, _result, _safe_text, _safe_attr, _extract_from_items,
)
from .engines_browser.web import (  # noqa: F401
    search_bing, search_sogou, search_so360, search_eastmoney, search_baidu, search_ddg,
)
from .engines_browser.dev import search_github_browser, search_stackoverflow_browser  # noqa: F401
from .engines_browser.academic import search_arxiv_browser, search_wikipedia_browser  # noqa: F401
from .engines_browser.alt import (  # noqa: F401
    search_mojeek_browser, search_ecosia_browser, search_startpage_browser, search_qwant_browser,
)
# 旧 search_browser.ENGINES 即浏览器引擎表；保留同名别名，外部 import 路径零变化
ENGINES = BROWSER_ENGINES


def _resolve_engines(explicit: str, category: str = "general", query: str = "") -> List[str]:
    """浏览器版引擎选择（v1.22.0 批 D）：参数顺序与旧 search_browser 相同
    （auto_save_browser 以位置参数 _resolve_engines("", "general") 调用），
    内部走统一调度 dispatch._resolve_engines 并按浏览器可用表过滤（无 API 引擎）。"""
    from .dispatch import _resolve_engines as _resolve
    return _resolve(explicit, query, category, available=BROWSER_ENGINES, api_auto=False)


def _parse_proxy(proxy: str):
    """解析代理字符串为 Playwright proxy 参数。

    支持格式：
        http://127.0.0.1:7890
        socks5://127.0.0.1:1080
        http://user:pass@host:port
        host:port（默认按 http 处理）
    """
    if not proxy:
        return None
    server = proxy.strip()
    scheme = ""
    username = password = None
    if "://" in server:
        scheme, server = server.split("://", 1)
    if "@" in server:
        auth, server = server.rsplit("@", 1)
        if ":" in auth:
            username, password = auth.split(":", 1)
    server = (scheme + "://" + server) if scheme else ("http://" + server)
    info = {"server": server}
    if username is not None:
        info["username"] = username
        info["password"] = password or ""
    return info


def run_search(query: str, max_results: int, engines: List[str], proxy: str = "", safe: bool = False,
               stealth: str = "full") -> Dict:
    if not _HAS_PLAYWRIGHT:
        hint = "playwright 未安装: pip install playwright && python -m playwright install chromium"
        return {"query": query, "results": [], "engine_errors": {"playwright": hint}, "browser": "unavailable"}
    all_results: List[Dict[str, str]] = []
    stats: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    fetch_limit = max_results * 2

    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                headless=True,
                args=_BROWSER_LAUNCH_ARGS(safe),
            )
            context_kwargs = dict(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
                ignore_https_errors=True,  # 与 auto_save_browser 各路线同口径：自签证书站点也能开
            )
            # 安全模式：禁 Service Worker（挖矿/恶意持久化常用）
            if safe:
                context_kwargs["service_workers"] = "block"
            # IP 伪装：所有浏览器流量走指定代理出口，目标站点看到的是代理 IP
            proxy_info = _parse_proxy(proxy)
            if proxy_info:
                context_kwargs["proxy"] = proxy_info
            context = browser.new_context(**context_kwargs)
            _APPLY_STEALTH(context, stealth)
            page = context.new_page()
            # 安全模式：请求拦截 + 弹窗全关（复用 auto_save_browser 的安全基建）
            safe_blocked = _SETUP_SAFE_MODE(context, page) if safe else {}

            for engine in engines:
                fn = BROWSER_ENGINES.get(engine)
                if not fn:
                    errors[engine] = "unsupported engine"
                    continue
                try:
                    results = fn(page, query, fetch_limit)
                    stats[engine] = len(results)
                    all_results.extend(results)
                    if not results:
                        errors[engine] = "no results"
                    elif engine == "bing" and _low_relevance(results, query):
                        errors[engine] = "low_relevance"
                except Exception as exc:
                    stats[engine] = 0
                    errors[engine] = str(exc)
                    sys.stderr.write(f"[{engine}] error: {exc}\n")
                # Human-like pause between engines.
                time.sleep(random.uniform(0.5, 1.2))
        finally:
            if browser is not None:
                browser.close()

    results = _dedupe(all_results)[:max_results * 3]
    out = {
        "query": query,
        "results": results,
        "engine_stats": stats,
        "engine_errors": errors,
        "browser": "playwright-chromium",
    }
    if safe:
        out["safe_mode"] = True
        try:
            out["blocked"] = safe_blocked
        except NameError:
            pass
    return out


def _format_plain(data: Dict) -> str:
    lines = []
    results = data.get("results", [])
    if not results:
        errs = data.get("engine_errors") or ""
        return f"没有搜索到结果。可尝试换关键词或稍后再试。{(' 引擎异常: ' + str(errs)) if errs else ''}"
    stats = data.get("engine_stats")
    lines.append(f"共 {len(results)} 条结果（浏览器模拟{f'，引擎统计: {stats}' if stats else ''}）")
    if data.get("engine_errors"):
        lines.append(f"引擎异常: {data['engine_errors']}")
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title', '(无标题)')}")
        lines.append(f"   URL: {r.get('url', '')}")
        if r.get("snippet"):
            lines.append(f"   摘要: {r['snippet']}")
        if r.get("source"):
            lines.append(f"   来源: {r['source']}")
        lines.append("")
    return "\n".join(lines).strip()
