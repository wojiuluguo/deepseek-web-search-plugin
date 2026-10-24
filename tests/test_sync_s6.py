# -*- coding: utf-8 -*-
"""BUGS.md S6 同步回归（v1.25.4）——Python 子进程 JSON stdout 强制 UTF-8。

构造性证明：
  ① 中文 Windows 的 GBK 管道里打印 \\xa0 等 GBK 外字符 → 子进程 exit 1（旧行为必现）；
  ② child_env() 注入 PYTHONIOENCODING=utf-8 + PYTHONUTF8=1 后同一段代码正常输出；
  ③ 三个调用 Python JSON 子进程的位置（runner / own_search download /
     search_and_cache）都实际把该 env 传给 subprocess.run。
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from searchkit import runner as R  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}  {detail}")


print("== ① child_env 语义 ==")
_saved = {k: os.environ.get(k) for k in ("PYTHONIOENCODING", "PYTHONUTF8")}
try:
    os.environ["PYTHONIOENCODING"] = "gbk"
    os.environ["PYTHONUTF8"] = "0"
    _env = R.child_env()
    check("child_env 覆盖继承的 GBK", _env.get("PYTHONIOENCODING") == "utf-8",
          str(_env.get("PYTHONIOENCODING")))
    check("child_env 打开 UTF-8 模式", _env.get("PYTHONUTF8") == "1")
    check("child_env 保留其余环境变量", isinstance(_env, dict) and len(_env) >= len(os.environ))
finally:
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

print("== ② 构造性复现：GBK 管道 vs child_env ==")
_code = "print('\\xa0')"
_bad = dict(os.environ)
_bad.update(PYTHONIOENCODING="gbk", PYTHONUTF8="0")
_r_bad = subprocess.run([sys.executable, "-c", _code], capture_output=True, text=True,
                        encoding="utf-8", errors="ignore", env=_bad)
check("GBK 管道打印 \\xa0 必崩（复现旧 bug）", _r_bad.returncode != 0,
      f"rc={_r_bad.returncode}")
_r_ok = subprocess.run([sys.executable, "-c", _code], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", env=R.child_env())
check("child_env 下同一代码正常输出", _r_ok.returncode == 0 and "\xa0" in (_r_ok.stdout or ""),
      f"rc={_r_ok.returncode}")

print("== ③ 三个调用点都传 env ==")


def _capture(mod, fn):
    """替换 mod.subprocess.run，执行 fn，返回捕获的 kwargs。"""
    box = {}
    class _FakeProc:
        returncode = 0
        stdout = '{"results": [], "engine_stats": {}}'
        stderr = ""
    orig = mod.subprocess.run

    def _fake(cmd, **kw):
        box.update(kw)
        return _FakeProc()

    mod.subprocess.run = _fake
    try:
        fn()
    finally:
        mod.subprocess.run = orig
    return box


_box = _capture(R, lambda: R.run_search_cli("probe", engines="bing", max_results=1, timeout=5))
check("runner.run_search_cli 传 env", (_box.get("env") or {}).get("PYTHONIOENCODING") == "utf-8",
      str(_box.get("env"))[:80])

import search_and_cache as _sc  # noqa: E402
_box = _capture(_sc, lambda: _sc.run_search("probe", 1, browser=False))
check("search_and_cache.run_search 传 env",
      (_box.get("env") or {}).get("PYTHONIOENCODING") == "utf-8", str(_box.get("env"))[:80])
_box = _capture(_sc, lambda: _sc.cache_url("https://example.com", ROOT / "downloads", "direct"))
check("search_and_cache.cache_url 传 env",
      (_box.get("env") or {}).get("PYTHONIOENCODING") == "utf-8", str(_box.get("env"))[:80])

import own_search as _os  # noqa: E402
_args = argparse.Namespace(url="https://example.com", query=None, output_dir=None,
                           safe=False, method="files", cookies="", cookies_from_browser="")
_box = _capture(_os, lambda: _os.cmd_download(_args))
check("own_search.cmd_download 传 env",
      (_box.get("env") or {}).get("PYTHONIOENCODING") == "utf-8", str(_box.get("env"))[:80])

print(f"\n== 结果: {passed} pass / {failed} fail ==")
sys.exit(1 if failed else 0)
