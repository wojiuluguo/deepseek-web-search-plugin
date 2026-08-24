"""拟人输入（--humanize on|off，默认 on）：把自动化操作伪装成真人 USB 级输入。

为什么能骗过"人机检测"——两层分开说：
  1. 事件层（本来就不输）：Playwright mouse/keyboard 底层走 CDP
     Input.dispatchMouseEvent / dispatchKeyEvent，页面拿到的每个事件
     isTrusted=true——与 USB 硬件输入在 JS 眼里完全同级，event.isTrusted
     这条路查不出我们，不需要额外做什么。
  2. 行为层（本模块主战场）：机器的破绽从来不在事件对象，而在模式——
     瞬移直线、匀速移动、点击零偏移、打字等间隔，人类不可能这样。
     行为风控（抖音/搜狗 antispider 级）全靠轨迹统计抓机器。
     → 贝塞尔轨迹 + 缓入缓出 + 手抖、点击微偏移 + 按压时长、
       正态键间隔 + 标点后思考停顿、滚动分步 + 步间微停。

安全契约：
  - 总开关 set_humanize(False)（--humanize off）→ 逐字节退回原生 API，
    行为与旧版完全一致（对照调试用）；
  - 任何拟真步骤抛异常 → 自动退回原生调用：最坏情况=没拟真，绝不挂任务；
  - 纯函数式记账（_LAST_POS 指针位置），不碰页面状态、不产生全局副作用。
"""
import random
import time

__all__ = [
    "set_humanize", "humanize_enabled",
    "human_move", "human_click", "human_type", "human_scroll", "human_pause",
]

# ---- 总开关（main() 里按 --humanize 设置；模块级避免参数层层穿透各路线）----
_HUMANIZE = True


def set_humanize(enabled: bool) -> None:
    global _HUMANIZE
    _HUMANIZE = bool(enabled)


def humanize_enabled() -> bool:
    return _HUMANIZE


# CDP 不告诉我们鼠标当前在哪，自己记账（每页一份"指针位置记忆"）
_LAST_POS: dict = {}


def _last_pos(page) -> tuple:
    key = id(page)
    if key not in _LAST_POS:
        _LAST_POS[key] = (random.randint(80, 400), random.randint(80, 300))
    return _LAST_POS[key]


def _bezier(p0, p1, p2, p3, t):
    """三阶贝塞尔插值点。"""
    u = 1 - t
    return (u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1])


def human_move(page, x: int, y: int, *, fast: bool = False) -> None:
    """拟人移动：三阶贝塞尔轨迹（随机控制点=弧线）+ smoothstep 缓入缓出
    + 每步 ±1.2px 手抖 + 距离自适应步数。fast=True 用于点击前的就位（更快）。"""
    if not _HUMANIZE:
        page.mouse.move(x, y)
        return
    try:
        x, y = int(x), int(y)
        sx, sy = _last_pos(page)
        dist = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
        steps = max(8, min(42, int(dist / 22)))            # 距离越长步数越多
        # 控制点：起终点连线两侧随机外扩——人手轨迹是弧线不是直线
        cx1 = sx + (x - sx) * random.uniform(0.2, 0.5) + random.uniform(-90, 90)
        cy1 = sy + (y - sy) * random.uniform(0.2, 0.5) + random.uniform(-70, 70)
        cx2 = sx + (x - sx) * random.uniform(0.5, 0.8) + random.uniform(-90, 90)
        cy2 = sy + (y - sy) * random.uniform(0.5, 0.8) + random.uniform(-70, 70)
        base_delay = (0.004 if fast else 0.008) + random.uniform(0, 0.004)
        for i in range(1, steps + 1):
            t = i / steps
            ease = t * t * (3 - 2 * t)                     # smoothstep：起手慢-中途快-收尾慢
            px, py = _bezier((sx, sy), (cx1, cy1), (cx2, cy2), (x, y), ease)
            page.mouse.move(int(px + random.uniform(-1.2, 1.2)),
                            int(py + random.uniform(-1.2, 1.2)))
            time.sleep(base_delay)
        page.mouse.move(x, y)                              # 精确落点收尾
        _LAST_POS[id(page)] = (x, y)
    except Exception:
        # 拟真轨迹失败 → 退原生 move；原生也失败 → 向上抛（调用方如 human_click
        # 需要知道"没移动到位"，否则会在错误位置 down/up 点错地方）
        page.mouse.move(x, y)
        _LAST_POS[id(page)] = (x, y)


def human_click(page, x: int, y: int, button: str = "left") -> None:
    """拟人点击：轨迹移动到落点附近 → ±2px 微偏移（人不可能点得正中）
    → down/up 之间带 40~120ms 按压时长（人手有物理行程）。"""
    if not _HUMANIZE:
        page.mouse.click(x, y, button=button)
        return
    try:
        human_move(page, x + random.uniform(-2, 2), y + random.uniform(-2, 2), fast=True)
        page.mouse.down(button=button)
        time.sleep(random.uniform(0.04, 0.12))             # 人类按压时长
        page.mouse.up(button=button)
        _LAST_POS[id(page)] = (x, y)
    except Exception:
        try:
            page.mouse.click(x, y, button=button)
        except Exception:
            pass


def human_type(page, text: str) -> None:
    """拟人打字：逐字符上屏，键间隔正态分布 μ=110ms σ=45ms（夹在 [35,420]ms），
    标点/空格后 12% 概率出现 0.3~0.9s 思考停顿。
    注：中文场景真实输入走 IME 逐字上屏，与逐字符 type 的行为面一致，不额外伪造。"""
    if not _HUMANIZE:
        page.keyboard.type(text, delay=30)
        return
    try:
        for ch in str(text):
            page.keyboard.type(ch)
            delay = max(0.035, min(0.42, random.gauss(0.11, 0.045)))
            time.sleep(delay)
            if ch in "，。！？,.!? " and random.random() < 0.12:
                time.sleep(random.uniform(0.3, 0.9))       # 想下一句
    except Exception:
        try:
            page.keyboard.type(text, delay=30)
        except Exception:
            pass


def human_scroll(page, dy: int) -> None:
    """拟人滚动：真实滚轮是一格一格的——按剩余距离 25%~55% 分步下压，
    步间 50~160ms 微停；dy 可负（回滚）。总位移与原生调用严格一致。"""
    if not _HUMANIZE or dy == 0:
        page.mouse.wheel(0, dy)
        return
    try:
        remaining = int(dy)
        while remaining != 0:
            step = int(remaining * random.uniform(0.25, 0.55))
            if abs(step) < 40:                             # 尾步一次性收完
                step = remaining
            page.mouse.wheel(0, step)
            remaining -= step
            if remaining:
                time.sleep(random.uniform(0.05, 0.16))
    except Exception:
        try:
            page.mouse.wheel(0, dy)
        except Exception:
            pass


def human_pause(lo: float = 0.4, hi: float = 1.6) -> None:
    """人会停顿：操作之间/页面之间的随机阅读停顿（关掉时直接不停）。"""
    if _HUMANIZE:
        time.sleep(random.uniform(lo, hi))
