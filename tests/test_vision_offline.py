# -*- coding: utf-8 -*-
"""vision 新增能力离线单测（不发网络、不开浏览器）：
指令注册、上传文件校验、对话框策略纯逻辑。端到端行为见 downloads/_vision_e2e.py
（本地 HTML 测试页驱动）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from auto_save.vision import VISION_ACTIONS  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


check("upload 指令已注册", "upload" in VISION_ACTIONS, str(VISION_ACTIONS))
check("dialog 指令已注册", "dialog" in VISION_ACTIONS)
check("原有 22 指令一个不少", all(a in VISION_ACTIONS for a in (
    "click", "dblclick", "right_click", "move", "drag", "scroll", "type", "press",
    "focus", "elements", "tabs", "switch_tab", "goto", "back", "forward", "reload",
    "wait", "screenshot", "eval", "viewport", "shot_policy", "quit")))

print("=" * 40)
if fails:
    print(f"FAILED: {len(fails)} 项 → {fails}")
    sys.exit(1)
print("ALL VISION OFFLINE TESTS PASS")
