"""引擎注册表（v1.22.0 批 C）：ENGINES 名→函数映射 + CATEGORY_ENGINES 分类表。
加引擎：在对应分类文件加 search_xxx，再在 ENGINES 注册一行。"""
from .web import search_ddg, search_bing, search_sogou, search_so360, search_baidu, \
    search_wikipedia, search_yahoo_finance
from .dev import search_github, search_gitlab, search_stackoverflow, search_npm
from .academic import search_arxiv, search_openalex, search_semanticscholar, search_crossref
from .community import search_hackernews, search_reddit
from .api import search_tavily, search_brave, search_searxng

__all__ = ["ENGINES", "CATEGORY_ENGINES", "DOMESTIC_FIRST"] + [
    "search_ddg", "search_bing", "search_sogou", "search_so360", "search_baidu",
    "search_wikipedia", "search_yahoo_finance", "search_github", "search_gitlab",
    "search_stackoverflow", "search_npm", "search_arxiv", "search_openalex",
    "search_semanticscholar", "search_crossref", "search_hackernews", "search_reddit",
    "search_tavily", "search_brave", "search_searxng",
]

ENGINES = {
    "tavily": search_tavily,
    "brave": search_brave,
    "searxng": search_searxng,
    "ddg": search_ddg,
    "bing": search_bing,
    "sogou": search_sogou,
    "so360": search_so360,
    "baidu": search_baidu,
    "arxiv": search_arxiv,
    "openalex": search_openalex,
    "semanticscholar": search_semanticscholar,
    "crossref": search_crossref,
    "github": search_github,
    "gitlab": search_gitlab,
    "stackoverflow": search_stackoverflow,
    "npm": search_npm,
    "hackernews": search_hackernews,
    "reddit": search_reddit,
    "wikipedia": search_wikipedia,
    "yahoo_finance": search_yahoo_finance,
}


# 统一分类表（v1.22.0 批 D 消灭双表）：轻量版/浏览器版共用本表，
# dispatch._resolve_engines 按各模式可用引擎过滤（轻量版无 eastmoney/mojeek 等，
# 浏览器版无 tavily/brave/openalex 等）。浏览器独有引擎（eastmoney）可列在表中，
# 轻量版解析时自动过滤，不再报 unsupported engine。
CATEGORY_ENGINES = {
    "general": ["bing", "sogou", "so360", "baidu", "wikipedia"],
    # 注：mojeek/ecosia/startpage/qwant 仅浏览器版(searchkit/browser.py)支持；
    # brave/searxng 需 API Key，仅轻量版有效（浏览器版自动过滤）
    "external": ["bing", "so360", "baidu", "ddg", "brave", "searxng", "wikipedia"],
    "academic": ["arxiv", "openalex", "semanticscholar", "crossref", "bing", "wikipedia"],
    "tech": ["github", "gitlab", "stackoverflow", "npm", "hackernews", "bing"],
    "news": ["bing", "sogou", "so360", "baidu", "hackernews"],
    # eastmoney=东方财富专业财经（仅浏览器版）；yahoo_finance 仅轻量版——各自自动过滤
    "finance": ["eastmoney", "yahoo_finance", "bing", "sogou", "so360", "baidu"],
    "social": ["reddit", "hackernews", "sogou", "bing"],
    "all": [
        "arxiv", "openalex", "semanticscholar", "crossref",
        "github", "gitlab", "stackoverflow", "npm", "hackernews",
        "reddit", "wikipedia", "yahoo_finance",
        "bing", "sogou", "so360", "baidu", "ddg",
    ],
}


DOMESTIC_FIRST = ["sogou", "so360", "baidu", "bing", "ddg"]
