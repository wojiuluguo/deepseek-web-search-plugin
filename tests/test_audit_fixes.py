# -*- coding: utf-8 -*-
"""DeepSeek 4.1 审计质疑修复回归（v1.25.1）——纯 stdlib。

覆盖 4 项确证修复：
  ① verify_capture --clean/--assemble 目录边界（防任意目录递归删除）
  ②a own_search URL scheme 白名单（防 file:// 读本地文件，含 playwright 兜底层）
  ②b own_search lan --hosts 私网校验（防绕过 RFC1918 护栏扫公网）
  ③ search_browser --timeout 全局看门狗补齐（+ runner.start_global_timeout 触发）
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
PY = sys.executable

sys.path.insert(0, str(SCRIPTS))
# 注意：不要把 searchkit/ 目录本身插进 sys.path——其 http.py 会遮蔽 stdlib http
# （urllib.request 内部 import http.client 直接 ModuleNotFoundError，实测踩坑）

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}  {detail}")


print("== ① verify_capture 目录边界 ==")
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_vc", SCRIPTS / "verify_capture.py")
_vc = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_vc)

check("_within_downloads: downloads 内为 True",
      _vc._within_downloads(ROOT / "downloads" / "cache" / "sub"))
check("_within_downloads: 外部目录为 False",
      not _vc._within_downloads(Path(tempfile.gettempdir()) / "not_downloads"))
check("_within_downloads: 相似前缀目录不算（防 is_relative_to 绕过争议）",
      not _vc._within_downloads(ROOT / "downloads_evil" / "x"))

# assemble 回归（v1.25.3）：VIDEO_EXTS 是 set、AUDIO_EXTS 是 tuple，旧 `set|tuple`
# 必抛 TypeError（--assemble 从上线起不可用）。用 downloads 内临时目录构造视频/音频
# 分段，断言不再抛类型异常（内容非法时允许 ok=False，但必须是正常 dict 返回）。
with tempfile.TemporaryDirectory(dir=ROOT / "downloads") as td:
    seg = Path(td)
    for n in ("s1.mp4", "s2.mp4", "s3.mp3"):
        (seg / n).write_bytes(b"not-a-real-media" * 10)
    try:
        res = _vc.assemble_segments(seg)
        check("assemble 不再 set|tuple TypeError", isinstance(res, dict) and "ok" in res, str(res)[:120])
    except TypeError as exc:
        check("assemble 不再 set|tuple TypeError", False, f"TypeError: {exc}")

# CLI 级：外部目录 --clean 必须被拒且文件原样保留
with tempfile.TemporaryDirectory() as td:
    victim = Path(td) / "tiny.png"
    victim.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # 一张"小图"
    r = subprocess.run([PY, str(SCRIPTS / "verify_capture.py"), "--dir", td, "--clean"],
                       capture_output=True, text=True, timeout=60)
    check("--clean 外部目录: exit 2", r.returncode == 2, f"rc={r.returncode}")
    check("--clean 外部目录: 文件未被删", victim.exists(), "victim gone!")
    check("--clean 外部目录: 报错含'拒绝'", "拒绝" in (r.stderr + r.stdout))

print("== ②a own_search scheme 白名单 ==")
import own_search as _os
for bad in ("file:///C:/windows/win.ini", "ftp://x/y", "javascript:alert(1)", "C:\\x"):
    try:
        _os._require_http_url(bad)
        check(f"_require_http_url 拒绝 {bad[:22]}", False, "未抛异常")
    except ValueError:
        check(f"_require_http_url 拒绝 {bad[:22]}", True)
check("_require_http_url 放行 https", True if not _os._require_http_url("https://a.com") else False)
# 兜底层同样必须挡（cmd_crawl 的 except 会吞 ValueError 转 playwright）
try:
    _os._fetch_with_playwright("file:///C:/windows/win.ini", timeout=1)
    check("playwright 兜底层挡 file://", False, "未抛异常")
except ValueError:
    check("playwright 兜底层挡 file://", True)
except RuntimeError:
    check("playwright 兜底层挡 file://", True)  # 未装 playwright 时先抛 RuntimeError 也算挡住

print("== ②b lan --hosts 私网校验 ==")
r = subprocess.run([PY, str(SCRIPTS / "own_search.py"), "lan",
                    "--hosts", "8.8.8.8", "--scan-timeout", "1"],
                   capture_output=True, text=True, timeout=120)
check("lan --hosts 8.8.8.8: exit 1", r.returncode == 1, f"rc={r.returncode}")
check("lan --hosts 8.8.8.8: 报错含'非私网'", "非私网" in r.stdout)
r = subprocess.run([PY, str(SCRIPTS / "own_search.py"), "lan",
                    "--hosts", "not-an-ip", "--scan-timeout", "1"],
                   capture_output=True, text=True, timeout=120)
check("lan --hosts 非 IP: exit 1", r.returncode == 1, f"rc={r.returncode}")
r = subprocess.run([PY, str(SCRIPTS / "own_search.py"), "lan",
                    "--hosts", "192.168.31.1", "--scan-timeout", "1"],
                   capture_output=True, text=True, timeout=120)
check("lan --hosts 私网 IP: 正常执行（非 1 即护栏误伤）",
      r.returncode in (0, 1) and "非私网" not in r.stdout)

print("== ③ --timeout 看门狗补齐 ==")
r = subprocess.run([PY, str(SCRIPTS / "search_browser.py"), "--help"],
                   capture_output=True, text=True, timeout=60)
check("search_browser --help 含 --timeout", "--timeout" in r.stdout)
# runner.start_global_timeout 触发：子进程 1s 挂钟 → ~1s 处 exit 1 + [timeout] 标记
probe = ("import sys, time; sys.path.insert(0, r'%s'); "
         "from searchkit.runner import start_global_timeout; "
         "start_global_timeout(1); time.sleep(5)" % SCRIPTS)
t0 = time.time()
r = subprocess.run([PY, "-c", probe], capture_output=True, text=True, timeout=60)
elapsed = time.time() - t0
check("看门狗触发: exit 1", r.returncode == 1, f"rc={r.returncode}")
check("看门狗触发: [timeout] 标记", "[timeout]" in r.stderr)
check("看门狗触发: ~1s 而非 5s", elapsed < 4, f"{elapsed:.1f}s")
check("看门狗关闭(0): 不触发", subprocess.run(
    [PY, "-c", ("import sys, time; sys.path.insert(0, r'%s'); "
                "from searchkit.runner import start_global_timeout; "
                "start_global_timeout(0); print('alive')" % SCRIPTS)],
    capture_output=True, text=True, timeout=30).returncode == 0)

print("== ⑧ 死代码已删 ==")
check("verify_capture._md5_file 不复存在", not hasattr(_vc, "_md5_file"))

print("== ⑨ safe 拒绝原因（v1.25.3） ==")
# --safe 落盘白名单拒绝归档时，错误必须是真实原因——旧行为笼统报
# "链接失效/TLS 被拦/是网页"，用户会把白名单拒绝误判成死链。
from auto_save.routes import _files_route  # noqa: E402
_res = _files_route("http://127.0.0.1:9/probe.zip", ROOT / "downloads" / "_safe_msg_test", safe=True)
check("safe 拒绝归档: 报错含'safe mode 拒绝'", "safe mode 拒绝" in (_res.get("error") or ""),
      str(_res)[:120])
check("safe 拒绝归档: 不谎报链接失效", "link dead" not in (_res.get("error") or ""))

print(f"\n== 结果: {passed} pass / {failed} fail ==")
sys.exit(1 if failed else 0)
