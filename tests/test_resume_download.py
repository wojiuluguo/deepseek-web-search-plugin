# -*- coding: utf-8 -*-
"""断点续传 + 代理离线测试：本地 http.server 自建 Range 支持，零外网依赖。
覆盖：完整下载 / .part 续传 / 成品幂等复用 / 代理真实生效（死端口必炸）/ 台账。"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from auto_save.browser_base import _proxy_urlopen, get_proxy, set_proxy  # noqa: E402
from auto_save.routes import _file_direct_download_ua  # noqa: E402

BODY = bytes(range(256)) * 1500  # 384000B 伪随机形态内容
UA = "Mozilla/5.0 (test)"

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


class RangeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            start = int(rng[6:].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(BODY)-1}/{len(BODY)}")
            body = BODY[start:]
        else:
            self.send_response(200)
            body = BODY
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="seg.dat"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), RangeHandler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{port}/seg.dat"

import tempfile  # noqa: E402
work = Path(tempfile.mkdtemp(prefix="dwsp_resume_"))

set_proxy("")  # 直连
# 1) 完整下载
r1 = _file_direct_download_ua(url, work, False, "", UA)
check("完整下载", bool(r1) and Path(r1["path"]).stat().st_size == len(BODY), str(r1))
check("完整下载内容一致", Path(r1["path"]).read_bytes() == BODY)
check("无 .part 残留", not (work / "seg.dat.part").exists())

# 2) 断点续传：删成品、留 100000B 的 .part
Path(r1["path"]).unlink()
(work / "seg.dat.part").write_bytes(BODY[:100000])
r2 = _file_direct_download_ua(url, work, False, "", UA)
check("续传完成且大小正确", bool(r2) and r2.get("size") == len(BODY), str(r2))
check("续传标记 resumed_from", bool(r2) and r2.get("resumed_from") == 100000, str(r2))
check("续传内容一致", bool(r2) and Path(r2["path"]).read_bytes() == BODY)

# 3) 成品幂等复用
r3 = _file_direct_download_ua(url, work, False, "", UA)
check("成品幂等复用", bool(r3) and r3.get("via") == "already-cached", str(r3))

# 4) 代理真实生效：指向死端口必须失败（证明请求走了代理而不是直连绕过）
set_proxy("http://127.0.0.1:1")
import urllib.request  # noqa: E402
try:
    _proxy_urlopen(urllib.request.Request(url), timeout=3)
    check("代理真实生效（死端口必炸）", False, "居然成功了=代理没被使用")
except Exception:
    check("代理真实生效（死端口必炸）", True)
check("get_proxy 生效", get_proxy() == "http://127.0.0.1:1")
set_proxy("")

# 5) 下载台账
from auto_save_browser import _append_manifest  # noqa: E402
mf = work / ".manifest.jsonl"
_append_manifest(work, {"saved": [{"url": url, "path": r2["path"],
                                   "size": len(BODY), "kind": "file"}],
                        "quality": "full"})
_append_manifest(work, {"saved": [], "quality": "empty"})  # 空产物不写
lines = mf.read_text(encoding="utf-8").strip().splitlines()
check("台账 1 条（空产物不记）", len(lines) == 1, str(len(lines)))
rec = json.loads(lines[0])
check("台账字段齐全", rec["url"] == url and rec["size"] == len(BODY)
      and len(rec.get("md5", "")) == 32 and "time" in rec, str(rec))

srv.shutdown()
print("=" * 40)
if fails:
    print(f"FAILED: {len(fails)} 项 → {fails}")
    sys.exit(1)
print("ALL RESUME/PROXY/MANIFEST TESTS PASS")
