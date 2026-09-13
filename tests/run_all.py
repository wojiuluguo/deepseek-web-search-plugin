# -*- coding: utf-8 -*-
"""一键测试入口：纯 stdlib，零新依赖。用法：
    python tests/run_all.py            # 全量
    python tests/run_all.py resume     # 只跑名字含关键词的
逐个跑同目录 test_*.py，任一失败即非零退出。"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
keyword = sys.argv[1] if len(sys.argv) > 1 else ""
targets = sorted(p for p in HERE.glob("test_*.py") if keyword in p.name)
if not targets:
    print(f"no test_*.py matched keyword: {keyword!r}")
    sys.exit(2)

failed = []
for t in targets:
    print(f"\n===== {t.name} =====")
    r = subprocess.run([PY, str(t)], cwd=str(HERE.parent))
    if r.returncode != 0:
        failed.append(t.name)

print("\n" + "=" * 50)
if failed:
    print(f"SUITE FAILED: {failed}")
    sys.exit(1)
print(f"SUITE PASS: {len(targets)} files")
