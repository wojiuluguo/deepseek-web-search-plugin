# -*- coding: utf-8 -*-
"""vision 三件套(dialog/upload/iframe)端到端测试：本地 HTML 测试页驱动
--method vision 会话（零外网，开本地 headless 浏览器），锁步 stdin/stdout 逐步断言。
fixtures: vision_test.html（confirm 按钮/双上传入口/iframe）/ vision_test_child.html。"""
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
URL = "file:///" + str(HERE / "fixtures" / "vision_test.html").replace("\\", "/")

updir = Path(tempfile.mkdtemp(prefix="dwsp_vision_e2e_"))
UPFILE = updir / "_up_test.txt"
UPFILE.write_text("hello upload", encoding="utf-8")

CMDS = [
    {"action": "elements"},
    {"action": "click", "selector": "#childbtn"},
    {"action": "click", "text": "弹确认框"},           # confirm → 默认 dismiss
    {"action": "eval", "js": "document.getElementById('st').textContent"},
    {"action": "dialog", "accept": True},              # 一次性策略：下一个接受
    {"action": "click", "text": "弹确认框"},
    {"action": "eval", "js": "document.getElementById('st').textContent"},
    {"action": "upload", "selector": "#f", "paths": [str(UPFILE)]},
    {"action": "eval", "js": "document.getElementById('fileinfo').textContent"},
    {"action": "upload", "click_selector": "#fakeup", "paths": [str(UPFILE)]},
    {"action": "quit"},
]

proc = subprocess.Popen(
    [PY, str(ROOT / "scripts" / "auto_save_browser.py"),
     "--url", URL, "--method", "vision",
     "--output-dir", str(updir), "--json"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    text=True, encoding="utf-8", cwd=str(ROOT),
)
timer = threading.Timer(180, proc.kill)
timer.start()
states = []


def read_state():
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("stdout 提前结束")
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue  # 启动横幅等非 JSON 行
        return d


try:
    init = read_state()  # 启动首屏状态
    assert init.get("event") == "state", init

    def send(cmd):
        proc.stdin.write(json.dumps(cmd, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        return read_state()

    # iframe 异步加载，elements 时机有竞态（真实会话里 AI 会重试）：
    # 轮询直到 frame==1 元素出现（上限 10 次 × 600ms），消除测试 flake
    els_state = None
    for _ in range(10):
        els_state = send({"action": "elements"})
        if any(e.get("frame") == 1 for e in (els_state.get("elements") or [])):
            break
        send({"action": "wait", "ms": 600})
    states.append(({"action": "elements"}, els_state))

    # 点击 iframe 内按钮：同样带重试（子 frame 刚挂载时 count 可能还没就绪）
    click_state = None
    for _ in range(5):
        click_state = send({"action": "click", "selector": "#childbtn"})
        if click_state.get("ok"):
            break
        send({"action": "wait", "ms": 500})
    states.append(({"action": "click", "selector": "#childbtn"}, click_state))

    for cmd in CMDS[2:]:
        states.append((cmd, send(cmd)))
    proc.stdin.close()
finally:
    timer.cancel()

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


by_idx = {i: st for i, (_, st) in enumerate(states)}

# 1. elements 含 iframe 内元素（frame==1，坐标已换算主视口）
els = by_idx[0].get("elements") or []
fr1 = [e for e in els if e.get("frame") == 1]
check("elements 标注 iframe 元素", bool(fr1), str(els)[:200])
check("iframe 元素带 frame_url", all("frame_url" in e for e in fr1))

# 2. 选择器点击落进 iframe（ok 信号 + note 带来源）
note2 = by_idx[1].get("note", "")
check("选择器命中 iframe 内按钮", by_idx[1].get("ok") is True and "iframe" in note2, note2)

# 3. confirm 默认 dismiss + dialog_events 上报
de = by_idx[2].get("dialog_events") or []
check("confirm 被上报", len(de) == 1 and de[0]["type"] == "confirm", str(de))
check("默认处置=dismissed", de and de[0].get("handled") == "dismissed", str(de))
check("dismiss 语义生效（status=cancelled）",
      by_idx[3].get("eval_result") == "cancelled", str(by_idx[3].get("eval_result")))

# 4. dialog accept 策略 → 接受生效
note4 = by_idx[4].get("note", "")
check("策略指令确认", by_idx[4].get("ok") is True and "接受" in note4, note4)
de5 = by_idx[5].get("dialog_events") or []
check("策略后 confirm 被接受", de5 and de5[0].get("handled") == "accepted", str(de5))
check("accept 语义生效（status=confirmed）",
      by_idx[6].get("eval_result") == "confirmed", str(by_idx[6].get("eval_result")))

# 5. upload 直设 + 回读
note7 = by_idx[7].get("note", "")
check("upload 直设成功", by_idx[7].get("ok") is True and "已上传" in note7, note7)
check("文件名回读", by_idx[8].get("eval_result") == "_up_test.txt",
      str(by_idx[8].get("eval_result")))

# 6. upload 按钮拦截（expect_file_chooser）
note9 = by_idx[9].get("note", "")
check("upload 按钮拦截成功", by_idx[9].get("ok") is True and "拦截" in note9, note9)

print("=" * 40)
if fails:
    print(f"FAILED: {len(fails)} 项 → {fails}")
    sys.exit(1)
print("ALL VISION E2E PASS")
