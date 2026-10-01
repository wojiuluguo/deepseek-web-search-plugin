# -*- coding: utf-8 -*-
"""搜索单元回归（v1.25.0 普查轮）：site 过滤 / detect_type / normalize 边界。
每条用例都来自实测定性：BUG 修复后固化为回归，非 bug 行为也固化防漂移。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_filter_site_host_suffix():
    """v1.25.0 普查修复回归：--site 必须域后缀匹配，子串域名不得混入。
    旧实现 `site in netloc` 实测放行 notpython.org.evil.com / xpython.org。"""
    from searchkit.adfilter import _filter_site

    results = [
        {"url": "https://www.python.org/abc", "title": "a"},
        {"url": "https://python.org/", "title": "b"},
        {"url": "https://notpython.org.evil.com/a", "title": "c"},
        {"url": "https://xpython.org/", "title": "d"},
        {"url": "https://evil.com/python.org.html", "title": "e"},
        {"url": "https://docs.python.org/dev/", "title": "f"},  # 子域应命中
    ]
    kept = _filter_site(results, "python.org")
    urls = [r["url"] for r in kept]
    assert len(kept) == 3, f"应保留 3 条（www/裸域/子域），实际 {len(kept)}: {urls}"
    assert "https://notpython.org.evil.com/a" not in urls
    assert "https://xpython.org/" not in urls
    # 带端口与空 site
    assert len(_filter_site([{"url": "https://python.org:8080/x", "title": "t"}], "python.org")) == 1
    assert len(_filter_site(results, "")) == len(results)


def test_detect_type_news_boundary():
    """v1.25.0 普查修复回归：news 词表不含"最新/今天"后，
    日常语回落 general，强新闻词仍命中 news。"""
    from smart_search import detect_type

    assert detect_type("今天天气怎么样") == "general"
    assert detect_type("最新版本下载") == "general"
    assert detect_type("最新AI芯片新闻") == "news"
    assert detect_type("突发：某地地震报道") == "news"
    assert detect_type("python asyncio 教程") == "tech"
    assert detect_type("OpenAI 股价") == "finance"


def test_normalize_url_edges():
    """边界不炸 + 跟踪参数丢弃 + 保留参数生效。"""
    from searchkit.normalize import _normalize_url

    assert _normalize_url("") == ""
    assert _normalize_url("javascript:void(0)") == "void(0)"
    assert _normalize_url("https://例え.テスト/パス") == "例え.テスト/パス"
    assert _normalize_url("https://example.com/a?utm_source=x&id=3") == "example.com/a?id=3"


def test_dedupe_skims_rebranded_titles():
    """换皮标题互杀生效（防 SEO 垃圾场），不同 snippet 的高相似标题同杀是既定权衡。"""
    from searchkit.normalize import _dedupe

    kept = _dedupe([
        {"url": "https://a.com/1", "title": "Python 教程：从入门到精通", "snippet": "A" * 100},
        {"url": "https://b.com/2", "title": "Python 教程：从入门到精通（2026版）", "snippet": "B" * 100},
        {"url": "https://c.com/3", "title": "完全不同的另一篇文章标题", "snippet": "C" * 100},
    ])
    assert len(kept) == 2, f"换皮标题应只留 1 条 + 不同文章 1 条，实际 {len(kept)}"


def test_api_engines_not_configured():
    """API 引擎无 Key 抛 NotConfiguredError（普查修正回归）。"""
    from searchkit.engines import api as api_mod
    from searchkit.http import NotConfiguredError

    saved = {var: os.environ.pop(var) for var in
             ("TAVILY_API_KEY", "BRAVE_API_KEY", "SEARXNG_BASE_URL")
             if var in os.environ}
    try:
        for fn in (api_mod.search_tavily, api_mod.search_brave, api_mod.search_searxng):
            try:
                fn("q", 5, 8)
                raise AssertionError(f"{fn.__name__} 无 Key 应抛 NotConfiguredError")
            except NotConfiguredError:
                pass
    finally:
        os.environ.update(saved)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"ALL {len(tests)} SEARCH UNIT TESTS PASS")
