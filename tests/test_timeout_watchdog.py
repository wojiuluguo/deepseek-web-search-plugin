# -*- coding: utf-8 -*-
"""全局 --timeout 看门狗测试（v1.24.0）：子进程真实触发——sleep 大于阈值，
断言进程被看门狗强制退出（exit 1 + [timeout] 标记）。"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# 看门狗按墙钟截杀，需要一个必然跑超 3s 的任务：B站 chain（direct→ytdlp→browser）。
# 即使网络慢/快，进程在 3s 时必然仍在运行（ytdlp/浏览器阶段），看门狗必然触发。
target = "https://www.bilibili.com/video/BV1GJ411c7Ud"
t0 = time.time()
p = subprocess.run(
    [PY, str(ROOT / "scripts" / "auto_save_browser.py"),
     "--url", target, "--timeout", "3",
     "--output-dir", str(ROOT / "downloads" / "_watchdog_test")],
    capture_output=True, text=True, timeout=30, cwd=str(ROOT),
    encoding="utf-8", errors="ignore",
)
elapsed = time.time() - t0
marker = "[timeout]" in (p.stderr or "")
ok = p.returncode == 1 and marker and 2.5 <= elapsed < 15
print(("PASS " if ok else "FAIL ") + f"看门狗 3s 截杀: exit={p.returncode} elapsed={elapsed:.1f}s "
      f"marker={marker}")
print(f"     stderr尾: {(p.stderr or '')[-120:]}")
sys.exit(0 if ok else 1)
