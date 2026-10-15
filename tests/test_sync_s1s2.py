# -*- coding: utf-8 -*-
"""BUGS.md 同步回归（v1.25.2，2026-10-15）——纯 stdlib。

S1（子服务 P1 同源）：子进程空输出被当成功 → 下游 KeyError
S2（子服务 I2 同类）：输出无隐形字符净化（零防护）→ ASCII Smuggling 载体穿透
S3：sanitize 移植的 P0 防坑验收（ASCII 保留用例，BUGS.md 指定）
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
PY = sys.executable

sys.path.insert(0, str(SCRIPTS))

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}  {detail}")


print("== S1a: dispatch._format_plain 空数据不炸 ==")
from searchkit.dispatch import _format_plain  # noqa: E402

out = _format_plain({})
check("data={} 不 KeyError 且返回兜底文案", "没有搜索到结果" in out)
check("data={} 不含 traceback", "results" not in out)
out = _format_plain({"engine_errors": {"tavily": "set TAVILY_API_KEY"}})
check("空结果如实报引擎异常", "set TAVILY_API_KEY" in out)

print("== S1b: runner ok 绑定 returncode ==")
from searchkit import runner as R  # noqa: E402


class _FakeProc:
    def __init__(self, rc, stdout):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = ""


def _patched_run_search_cli(rc, stdout):
    orig = R.subprocess.run
    R.subprocess.run = lambda *a, **k: _FakeProc(rc, stdout)
    try:
        return R.run_search_cli("x", engines=["bing"])
    finally:
        R.subprocess.run = orig


# rc=1 但 stdout 是合法 JSON（旧行为：ok=True → data 下发炸下游）
env = _patched_run_search_cli(1, json.dumps({"results": [], "engine_stats": {}}))
check("rc=1 + 合法 JSON → ok=False", env["ok"] is False, f"env={env}")
check("rc=1 → error 补 'subprocess exit 1'", env["error"] == "subprocess exit 1", f"env={env}")
# rc=0 正常输出 → ok=True（无回归）
env = _patched_run_search_cli(0, json.dumps({"results": [{"title": "t", "url": "u"}], "engine_stats": {}}))
check("rc=0 + 合法 JSON → ok=True", env["ok"] is True, f"env={env}")
check("rc=0 → data 完整下发", env["data"].get("results"), f"env={env}")

print("== S2: 隐形字符净化 ==")
from searchkit.sanitize import sanitize_output, sanitize_result, sanitize_results  # noqa: E402

# S3 指定验收用例：ASCII 必须原样保留（P0 教训：转义错误曾吞全部 ASCII）
ascii_case = "abc123 XYZ 中文 456 https://a.com/x?y=1 2026年"
check("S3 ASCII 保留验收", sanitize_output(ascii_case) == ascii_case,
      f"got={sanitize_output(ascii_case)!r}")
# 隐形字符剥离：零宽空格 / RTL 覆盖 / Tag 块(ASCII Smuggling) / 变体选择符补充
dirty = "for\u200bmat\u202ecode\uE0041hidden\U000e0100tail\ufeffend"
clean = sanitize_output(dirty)
check("零宽空格剥离", "\u200b" not in clean)
check("RTL 覆盖控制符剥离", "\u202e" not in clean)
check("Tag 块剥离(ASCII Smuggling 载体)", "\U000e0041" not in clean)
check("变体选择符补充块剥离", "\U000e0100" not in clean)
check("VS16(U+FE0F) 保留防误伤 emoji", sanitize_output("emoji\U0001f600 ok") == "emoji\U0001f600 ok")
check("可见内容保留", sanitize_output("格式代码") == "格式代码")
# 超长行截断
check("单行 600 上限截断", len(sanitize_output("x" * 700)) == 601)  # 600 + …
# 字段级：url 不截断但剥隐形
item = {"title": "t\u200bit", "snippet": "s" * 700, "url": "https://a.com/\u200bx?q=1"}
sanitize_result(item)
check("字段净化: title", item["title"] == "tit")
check("字段净化: snippet 截断 601", len(item["snippet"]) == 601)
check("字段净化: url 剥隐形且完整", item["url"] == "https://a.com/x?q=1")
check("列表净化: sanitize_results 遍历", sanitize_results([{"title": "a\u200bb"}])[0]["title"] == "ab")

print("== 集成冒烟：接线后真实搜索零回归 ==")
r = subprocess.run([PY, str(SCRIPTS / "search.py"), "--query", "python asyncio",
                    "--engines", "bing", "--max-results", "3", "--json"],
                   capture_output=True, text=True, timeout=120)
try:
    d = json.loads(r.stdout)
    check("JSON 合法且 results 字段在", isinstance(d.get("results"), list))
    check("净化后正常结果无隐形字符残留",
          all(not any(c in (x.get("title", "") + x.get("snippet", ""))
                      for c in "\u200b\u202e\U000e0041") for x in d["results"]))
except Exception as exc:
    check("JSON 合法且 results 字段在", False, f"{exc}; stdout={r.stdout[:120]}")

print(f"\n== 结果: {passed} pass / {failed} fail ==")
sys.exit(1 if failed else 0)
