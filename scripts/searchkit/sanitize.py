# -*- coding: utf-8 -*-
"""文本净化件（v1.25.2 自子服务 search-api-service 同步，BUGS.md S2）——
应对搜索场景的文本攻击面：网页标题/摘要会被 AI 直接拼进 prompt，攻击者可在
网页里埋「忽略之前指令」类文本，并借助零宽字符/双向控制符（U+200B-200F、
U+202A-202E、U+2066-2069）隐藏指令或做视觉欺骗；Unicode Tag 块（U+E0000-E007F，
ASCII Smuggling 载体）多数界面渲染为空但模型读得到。

来源：search-api-service/scripts/searchkit/sanitize.py（**必须 ≥2026-10-04 版**——
首版 `_INVISIBLE_RE` 曾写 `\u1bca0` 5 位转义错误吞掉全部 ASCII，见子服务 P0；
同步时验收用例：`sanitize_output('abc123 XYZ 中文 456 https://a.com/x?y=1 2026年')`
输出须与输入一致）。与子服务的架构差异：子服务在 server.py 输出出口净化
（引擎层零依赖）；主项目无 server，在**引擎聚合数据源头**净化（dispatch/browser
返回前 + own_search 入库前）——下游 5 份 _format_plain 与 JSON 全部自动干净，
不再逐出口接线（副本漂移温床，见主项目审计⑦/QA-1 教训）。

原则：只做无损或近无损清洗（剥离隐形字符不改变可见内容），不做关键词审查
（误杀不可控，语义审查属调用方 AI 的职责）。
"""

import re

__all__ = ["sanitize_output", "sanitize_result", "sanitize_results"]

# 隐形/方向控制字符：零宽空格、零宽连接符、LTR/RTL 嵌入与翻转、行/段分隔符，
# 以及「ASCII Smuggling」载体——Unicode Tag 块(U+E0000-E007F)与变体选择符补充
# (U+E0100-E01EF)：多数界面渲染为空，但模型读得到，可夹带隐藏指令。
# 注意：5 位以上码位必须 \UXXXXXXXX（8 位）——\u 只取 4 位，写 \u1bca0 会
# 意外生成 '0'-U+1BCA 范围吞掉全部 ASCII（子服务 P0 实锤教训）。
_INVISIBLE_RE = re.compile(
    "[\u00ad\u0600-\u0605\u061c\u06dd\u070f\u08e2\u180e"
    "\u200b-\u200f\u202a-\u202e\u2060-\u2069\u2028\u2029\ufeff"
    "\ufff0-\ufff8\U0001bca0-\U0001bca3\U0001d173-\U0001d17a"
    "\U000e0000-\U000e007f\U000e0100-\U000e01ef]"
)
# 控制字符（保留 \t \n；\r 统一剥——纯文本协议以 \n 分行）
_CTRL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\r]")

# 单行上限：防单条超长结果撑爆调用方；超出以 … 标注截断
_LINE_MAX = 600


def _clean_line(line: str) -> str:
    line = _CTRL_RE.sub("", line)        # 控制字符（含 \x00）先行剥离
    line = _INVISIBLE_RE.sub("", line)
    if len(line) > _LINE_MAX:
        line = line[:_LINE_MAX] + "…"
    return line


def sanitize_output(text: str) -> str:
    """净化一段结果文本：剥离隐形/控制字符（保留换行与制表）、单行截断。
    不改变可见内容——对正常结果零影响。"""
    if not text:
        return text
    return "\n".join(_clean_line(l) for l in text.split("\n"))


def sanitize_result(item: dict) -> dict:
    """净化单条搜索结果的文本字段（title/url/snippet/source 等字符串值）。
    原地修改并返回；url 仅剥控制/隐形字符不截断（截断会破坏链接）。"""
    for k, v in list(item.items()):
        if not isinstance(v, str):
            continue
        if k == "url":
            item[k] = _CTRL_RE.sub("", _INVISIBLE_RE.sub("", v)).strip()
        else:
            item[k] = _clean_line(v)
    return item


def sanitize_results(results: list) -> list:
    """净化结果列表（聚合数据源头调用一次，下游全部出口自动干净）。"""
    for r in results:
        if isinstance(r, dict):
            sanitize_result(r)
    return results
