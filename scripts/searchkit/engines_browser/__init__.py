"""浏览器引擎注册表（v1.22.0 结构优化批 2）：BROWSER_ENGINES 名→函数映射。
加引擎：在对应分类文件加 search_xxx，再在 BROWSER_ENGINES 注册一行。"""
from .web import search_bing, search_sogou, search_so360, search_eastmoney, search_baidu, search_ddg
from .dev import search_github_browser, search_stackoverflow_browser
from .academic import search_arxiv_browser, search_wikipedia_browser
from .alt import search_mojeek_browser, search_ecosia_browser, search_startpage_browser, search_qwant_browser

__all__ = ["BROWSER_ENGINES", "_clean_text", "_result", "_safe_text", "_safe_attr",
           "_extract_from_items"] + [
    "search_bing", "search_sogou", "search_so360", "search_eastmoney", "search_baidu",
    "search_ddg", "search_github_browser", "search_stackoverflow_browser",
    "search_arxiv_browser", "search_wikipedia_browser",
    "search_mojeek_browser", "search_ecosia_browser", "search_startpage_browser", "search_qwant_browser",
]

from .dom import _clean_text, _result, _safe_text, _safe_attr, _extract_from_items  # noqa: E402

BROWSER_ENGINES = {
    "bing": search_bing,
    "sogou": search_sogou,
    "so360": search_so360,
    "baidu": search_baidu,
    "eastmoney": search_eastmoney,
    "ddg": search_ddg,
    "arxiv": search_arxiv_browser,
    "github": search_github_browser,
    "stackoverflow": search_stackoverflow_browser,
    "wikipedia": search_wikipedia_browser,
    "mojeek": search_mojeek_browser,
    "ecosia": search_ecosia_browser,
    "startpage": search_startpage_browser,
    "qwant": search_qwant_browser,
}
