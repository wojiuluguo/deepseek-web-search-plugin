# -*- coding: utf-8 -*-
"""routing 离线单测：_is_bare_homepage 的伪首页判定（v1.23.2 压测排雷回归锁）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from auto_save.routing import _is_bare_homepage, _looks_like_item_page  # noqa: E402

fails = []


def check(name, got, want):
    print(("PASS " if got == want else "FAIL ") + name + ("" if got == want else f"  [got {got}]"))
    if got != want:
        fails.append(name)


# 真裸首页
check("空路径首页", _is_bare_homepage("https://www.bilibili.com"), True)
check("根斜杠首页", _is_bare_homepage("https://www.douyin.com/"), True)
# v1.23.2 压测排雷：伪首页（动态子域 + 首页文件名）
check("t.bilibili/index.html 伪首页", _is_bare_homepage("https://t.bilibili.com/index.html"), True)
check("index.htm 变体", _is_bare_homepage("https://example.com/index.htm"), True)
check("default.html 变体", _is_bare_homepage("https://example.com/default.html"), True)
check("带 query 的首页", _is_bare_homepage("https://example.com/index.html?from=search"), True)
# 真内容页不许误杀
check("B站视频页", _is_bare_homepage("https://www.bilibili.com/video/BV1GJ411c7Ud"), False)
check("抖音视频页", _is_bare_homepage("https://www.douyin.com/video/7380000000000000000"), False)
check("子目录 index 是内容页", _is_bare_homepage("https://example.com/docs/index.html"), False)
check("普通文章页", _is_bare_homepage("https://example.com/2024/news/123.html"), False)

# ---- _looks_like_item_page（v1.23.2 压测排雷：栏目首页不许抢位）----
check("B站视频页是条目页", _looks_like_item_page("https://www.bilibili.com/video/BV1GJ411c7Ud"), True)
check("抖音视频页是条目页", _looks_like_item_page("https://www.douyin.com/video/7380000000000000000"), True)
check("youtu.be 短ID是条目页", _looks_like_item_page("https://youtu.be/dQw4w9WgXcQ"), True)
check("快手 short-video 是条目页", _looks_like_item_page("https://www.kuaishou.com/short-video/3xabc123"), True)
check("西瓜纯数字ID是条目页", _looks_like_item_page("https://www.ixigua.com/7380000000000000000"), True)
check("专栏首页不是条目页", _looks_like_item_page("https://www.bilibili.com/read/home"), False)
check("动态伪首页不是条目页", _looks_like_item_page("https://t.bilibili.com/index.html"), False)
check("根首页不是条目页", _looks_like_item_page("https://www.bilibili.com/"), False)

print("=" * 40)
if fails:
    print(f"FAILED: {len(fails)} 项 → {fails}")
    sys.exit(1)
print("ALL ROUTING TESTS PASS")
