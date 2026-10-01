# -*- coding: utf-8 -*-
"""引擎选择器 HTML 夹具测试（v1.25.0，问题清单 #4 落地第一块砖）。

背景：34 个引擎的选择器/正则零测试守护——站点改版即哑且无告警
（v1.21.0 时代 alt.py 四个死引擎挂了几个版本才被人工发现）。
本测试用真实录制响应（bing/baidu）+ 手工最小结构夹具（sogou/so360/ddg），
monkeypatch searchkit.http._fetch 喂夹具给引擎函数，断言：
1. 解析出 >=1 条结果；
2. 字段齐全（title/url/source），url 为绝对地址或引擎壳相对路径。

站点改版后：重新跑 downloads/_search_stress/record_fixtures.py 录新夹具，
本测试红了就是选择器该修的信号——不用等线上发现。
纯 stdlib，与 tests/ 既有风格一致（直接运行，断言失败非零退出）。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURES = ROOT / "tests" / "fixtures" / "engine_html"


def _feed(fixture: str):
    """monkeypatch 喂夹具。注意必须 patch 使用方模块 searchkit.engines.web 的
    _fetch——它 `from ..http import _fetch` 在导入时已绑定名字，patch http 模块
    不会生效（经典 monkeypatch 陷阱，v1.25.0 实测踩过后修正）。"""
    import searchkit.engines.web as web_mod

    html = (FIXTURES / fixture).read_text(encoding="utf-8")
    web_mod._fetch = lambda url, timeout=8, headers=None: html


def _assert_results(results, min_count=1, label=""):
    assert len(results) >= min_count, f"[{label}] 期望 >= {min_count} 条结果，实际 {len(results)}"
    for r in results:
        assert r.get("title"), f"[{label}] title 不能为空"
        assert r.get("url"), f"[{label}] url 不能为空"
        assert r.get("source"), f"[{label}] source 不能为空"


def test_bing_real_fixture():
    from searchkit.engines.web import search_bing

    _feed("bing_real.html")
    _assert_results(search_bing("python asyncio", 8, 8), min_count=3, label="bing")


def test_baidu_real_fixture():
    from searchkit.engines.web import search_baidu

    _feed("baidu_real.html")
    _assert_results(search_baidu("python asyncio", 8, 8), min_count=3, label="baidu")


def test_sogou_min_fixture():
    from searchkit.engines.web import search_sogou

    _feed("sogou_min.html")
    results = search_sogou("python asyncio", 8, 8)
    _assert_results(results, min_count=3, label="sogou")
    # 壳相对路径保留（resolve.py 会跟随解码；此处只断言解析层不丢不补错）
    assert any("/link?url=" in r["url"] for r in results), "搜狗壳链接应原样保留"


def test_so360_min_fixture():
    from searchkit.engines.web import search_so360

    _feed("so360_min.html")
    results = search_so360("php generator", 8, 8)
    _assert_results(results, min_count=2, label="so360")
    assert any("/link?m=" in r["url"] for r in results), "360 壳链接应原样保留"


def test_ddg_min_fixture():
    from searchkit.engines.web import search_ddg

    _feed("ddg_min.html")
    _assert_results(search_ddg("python asyncio", 8, 8), min_count=2, label="ddg")


def test_api_engines_not_configured():
    """API 引擎无 Key 时应抛 NotConfiguredError 而非静默返回 []（v1.25.0 普查修正）。"""
    from searchkit.engines import api as api_mod
    from searchkit.http import NotConfiguredError

    saved = {var: os.environ.pop(var) for var in
             ("TAVILY_API_KEY", "BRAVE_API_KEY", "SEARXNG_BASE_URL")
             if var in os.environ}
    try:
        for fn in (api_mod.search_tavily, api_mod.search_brave, api_mod.search_searxng):
            try:
                fn("q", 5, 8)
                raise AssertionError(f"{fn.__name__} 无 Key 时应抛 NotConfiguredError")
            except NotConfiguredError:
                pass
    finally:
        os.environ.update(saved)


def test_normalize_shell_keeps_query():
    """壳 URL 去重 key 必须保留 query（v1.25.0 坍缩修复回归）。"""
    from searchkit.normalize import _normalize_url

    a = _normalize_url("http://www.baidu.com/link?url=TOKEN_A")
    b = _normalize_url("http://www.baidu.com/link?url=TOKEN_B")
    assert a != b, "不同 token 的壳 URL 不应坍缩成同一个去重 key"
    assert a == "baidu.com/link?url=TOKEN_A"


def test_resolve_shell_same_site_guard():
    """解码 302 落回引擎自家页面（验证页）时应保留原壳而非引用验证页。"""
    from searchkit.resolve import _same_site

    assert _same_site("https://www.baidu.com/s?wd=x", "http://www.baidu.com/link?url=T")
    assert not _same_site("https://docs.python.org/3/", "http://www.baidu.com/link?url=T")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"ALL {len(tests)} ENGINE FIXTURE TESTS PASS")
