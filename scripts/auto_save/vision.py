"""视觉会话协议层（v1.22.0 批 A 自 auto_save_browser.py 搬迁，零逻辑改动）：
stdin/stdout JSON 协议、DOM 精准操作、元素标注/验证码检测 JS、看门狗、
虚拟光标覆盖层。唯一入口 _vision_route（--method vision）。
__file__ 注意：本模块位于 scripts/auto_save/ 下，仓库根 = parent.parent.parent
（_skill_version 读 package.json 已按此修正）。"""
import json
import random
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .browser_base import _apply_stealth, _browser_launch_args, _setup_safe_mode, _wait_for_render
from .constants import USER_AGENTS
from .cookies import _inject_login_cookies, _login_rescue
from .humanize import human_click, human_move, human_scroll, human_type
from .shots import MOUSE_TRACK_JS, _screen_info, _shot_viewport

__all__ = [
    "VISION_MODEL_NAME", "VISION_DEFAULT_MAX_SCREENS", "VISION_ACTIONS",
    "MOUSE_TRACK_JS", "CURSOR_OVERLAY_JS", "ELEMENTS_JS", "CAPTCHA_JS",
    "_is_vision_model", "_vision_api_hint", "_free_port", "_eval_watchdog_thread",
    "_vision_find_el", "_vision_el_center", "_click_flash", "_vision_dom_action",
    "_vision_dom_type", "_vision_exec_action", "_skill_version", "_vision_route",
]



VISION_MODEL_NAME = "deepseek-v4-flash-vision-exp"


VISION_DEFAULT_MAX_SCREENS = 30   # 视觉会话单次截图数上限（成本防护：每张≤384 token）
# MOUSE_TRACK_JS 定义在 shots.py（双方共用，防循环引用）；此处 from .shots 引入并 re-export。


CURSOR_OVERLAY_JS = """
(() => {
    if (window.__aiCursor) return;
    const STROKE = 'stroke="#000000" stroke-linejoin="round"';
    const SHAPES = {
        // 经典箭头（热点在左上尖角）
        arrow: { svg: '<path d="M4 2 L4 20 L8.5 15.5 L11.5 22 L14 20.8 L11 14.5 L17 14 Z" fill="#ffffff" ' + STROKE + ' stroke-width="1.4"/>', dx: -2, dy: -2 },
        // 指向手（热点在食指指尖）
        hand:  { svg: '<path d="M9.2 1.6 a1.5 1.5 0 0 1 3 0 V10 h0.8 a3.8 3.8 0 0 1 3.8 3.8 v2.8 c0 4-2.4 6-5.8 6 -3.2 0-5-1.7-5.9-4.5 L3.9 13.3 a1.6 1.6 0 0 1 2.9-1.3 L8.2 14 l1-1.5 Z" fill="#ffffff" ' + STROKE + ' stroke-width="1.3"/>', dx: -4, dy: -2 },
        // I 型文本光标（白粗描底+黑细线，热点在横杆中心）
        text:  { svg: '<path d="M7 2.5 H17 M12 2.5 V21.5 M7 21.5 H17" fill="none" stroke="#ffffff" stroke-width="3"/><path d="M7 2.5 H17 M12 2.5 V21.5 M7 21.5 H17" fill="none" stroke="#000000" stroke-width="1.3"/>', dx: -17, dy: -17 },
    };
    const el = document.createElement('div');
    el.id = '__ai_cursor__';
    el.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483647;'
        + 'pointer-events:none;width:34px;height:34px;';
    let curShape = '';
    const place = (x, y) => { el.style.transform = 'translate(' + (x + el.__dx) + 'px,' + (y + el.__dy) + 'px)'; };
    const setShape = (name) => {
        if (name === curShape || !SHAPES[name]) return;
        curShape = name;
        el.innerHTML = '<svg width="34" height="34" viewBox="0 0 24 24" '
            + 'style="filter:drop-shadow(0 1px 3px rgba(0,0,0,.9))">' + SHAPES[name].svg + '</svg>';
        el.__dx = SHAPES[name].dx; el.__dy = SHAPES[name].dy;
    };
    // 判定形态：优先元素自己的 CSS cursor；auto/default 时按可编辑性推断（同浏览器行为）
    const shape_for = (node) => {
        if (!node || node.nodeType !== 1) return 'arrow';
        const c = getComputedStyle(node).cursor;
        if (c === 'pointer' || c === 'grab' || c === 'grabbing' || c === 'move') return 'hand';
        if (c === 'text') return 'text';
        if (c === 'auto' || c === '' || c === 'default') {
            const t = node.tagName;
            if (t === 'INPUT' || t === 'TEXTAREA' || node.isContentEditable) return 'text';
        }
        return 'arrow';
    };
    const onMove = e => {
        setShape(shape_for(document.elementFromPoint(e.clientX, e.clientY)));
        place(e.clientX, e.clientY);
    };
    // 点击视觉反馈（v1.21.0）：在点击位置画一圈扩散涟漪（白圈黑边，~0.5s 淡出），
    // 截图里能直接看到"刚才在这里点了"。由 Python 侧 _click_flash 在每次点击后调用。
    window.__aiCursorFlash = (x, y) => {
        const f = document.createElement('div');
        f.id = '__ai_click_ripple__';
        f.style.cssText = 'position:fixed;left:' + (x - 18) + 'px;top:' + (y - 18) + 'px;'
            + 'width:36px;height:36px;z-index:2147483646;pointer-events:none;'
            + 'border:3px solid #ffffff;box-shadow:0 0 0 2px #000000, inset 0 0 0 2px #000000;'
            + 'border-radius:50%;transform:scale(.3);opacity:1;'
            + 'transition:transform .35s ease-out, opacity .5s ease-out';
        document.documentElement.appendChild(f);
        requestAnimationFrame(() => {
            f.style.transform = 'scale(1.3)';
            f.style.opacity = '0';
        });
        setTimeout(() => f.remove(), 600);
    };
    const boot = () => {
        document.documentElement.appendChild(el);
        setShape('arrow');
        document.addEventListener('mousemove', onMove, true);
        place(window.__mx || 0, window.__my || 0);
    };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else { boot(); }
    window.__aiCursor = true;
})();
"""


VISION_ACTIONS = ("click", "dblclick", "right_click", "move", "drag", "scroll",
                  "type", "press", "focus", "elements", "tabs", "switch_tab",
                  "goto", "back", "forward", "reload", "wait", "screenshot",
                  "eval", "viewport", "shot_policy", "quit")


ELEMENTS_JS = """
() => {
    const out = [];
    const sel = 'a, button, input, select, textarea, [role=button], [onclick], [tabindex]';
    document.querySelectorAll(sel).forEach(el => {
        try {
            const r = el.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) return;              // 不可见
            if (r.bottom < 0 || r.top > innerHeight) return;      // 视口外
            const style = getComputedStyle(el);
            if (style.visibility === 'hidden' || style.display === 'none') return;
            const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '')
                .replace(/\\s+/g, ' ').trim().slice(0, 40);
            out.push({
                tag: el.tagName.toLowerCase(),
                text: text,
                x: Math.round(r.x + r.width / 2),   // 中心点（直接喂给 click）
                y: Math.round(r.y + r.height / 2),
                w: Math.round(r.width),
                h: Math.round(r.height),
                type: el.type || '',
                name: el.name || '',
            });
        } catch (e) {}
    });
    return out.slice(0, 60);  // 上限 60 个防刷屏
}
"""


CAPTCHA_JS = """
() => {
    const found = [];
    // 1. 已知验证码 iframe / class / id 特征（只留验证码专属选择器）
    const sigs = {
        geetest: ['.geetest_holder', '.geetest_widget', 'iframe[src*="geetest"]'],
        recaptcha: ['.recaptcha-checkbox', 'iframe[src*="recaptcha"]', '.g-recaptcha'],
        hcaptcha: ['iframe[src*="hcaptcha"]', '.h-captcha'],
        slider: ['.slide-verify', '.nc_wrapper', '.geetest_slider',
                 '[class*="slide-verify"]', '[class*="captcha-slider"]', '[class*="captcha"]'],
        rotate: ['.rotate-captcha', '[class*="rotate-captcha"]'],
    };
    for (const [kind, sels] of Object.entries(sigs)) {
        for (const s of sels) {
            try {
                const el = document.querySelector(s);
                if (el) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 10 && r.height > 10) { found.push(kind); break; }
                }
            } catch (e) {}
        }
    }
    // 2. 验证码关键词（中文站点常见文案；不含"向右滑动"——那是轮播图的标准指示文案）
    const body = (document.body ? document.body.innerText : '').slice(0, 20000);
    if (/请拖动滑块|拖动滑块完成|拖动到最右侧|点击验证|请点击图中|按顺序点击/.test(body)) {
        found.push('slider_or_click_captcha');
    }
    return [...new Set(found)];
}
"""



def _is_vision_model(model: str) -> bool:
    """判定模型是否支持视觉（多模态）。官方目前仅 deepseek-v4-flash-vision-exp
    接受图片输入（名称含 vision），普通模型传图会直接报错。"""
    return bool(model) and "vision" in model.lower()



def _vision_api_hint(detail: str = "original") -> Dict:
    """喂给调用方 AI 的官方 API 参数提示（照官方文档拼请求用）。"""
    return {
        "model": VISION_MODEL_NAME,
        "detail": detail,                       # low=512×512 更省 token / original=原图
        "max_tokens_per_image": 384,            # 单张 token 封顶（成本估算用）
        "image_formats": ["JPEG", "PNG", "GIF", "WebP"],
        "send_as": "base64 data URL 或 Files API file_id",
        "note": "图片只能放 user 消息；本工具产出的 PNG 直接 base64 内联即可",
    }



def _free_port() -> int:
    """挑一个本机空闲端口（视觉会话给浏览器开本地 DevTools 调试口用）。"""
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port



def _eval_watchdog_thread(debug_port: int, timeout_s: float, cancelled, fired) -> None:
    """eval 看门狗：超时仍未被取消时，经 DevTools HTTP 端点强杀全部 page target。

    为什么走 HTTP /json/close：卡死的 renderer（如 while(true)）不响应任何
    协议消息，但浏览器进程本身还活着，直接处理 /json/list 和 /json/close；
    页面一关，主线程阻塞中的 page.evaluate 立刻以 "Target closed" 解卡。
    纯 stdlib 实现，不需要 renderer 配合，也不受 Playwright 跨线程限制。"""
    if cancelled.wait(timeout_s):
        return  # eval 已按时返回，看门狗无事可做
    base = f"http://127.0.0.1:{debug_port}"
    try:
        targets = json.load(urllib.request.urlopen(f"{base}/json/list", timeout=5))
        closed = 0
        for t in targets:
            if t.get("type") == "page":
                try:
                    urllib.request.urlopen(f"{base}/json/close/{t['id']}", timeout=5)
                    closed += 1
                except Exception:
                    pass
        if closed:
            fired.set()
    except Exception:
        pass  # 看门狗自身失败不影响主流程（退化为原始行为：eval 一直阻塞）




# ---------- DOM 精准化（v1.15.0）：文字/选择器定位 + 等可见 + 中心点 + 验证 + 重试 ----------
# 背景：纯坐标点击靠 AI 从截图猜像素，SPA 页面元素动态挂载/懒加载时经常点空。
# 精准模式让 AI 像 Playwright 原生脚本一样"找元素再操作"：



def _vision_find_el(page, cmd: Dict, for_type: bool = False):
    """按 selector / 页面文字定位元素。返回 (locator, 定位说明) 或 (None, 原因)。
    注意：type 指令的 "text" 是要输入的内容（历史语义，不能动），所以 type 只认 selector。"""
    sel = str(cmd.get("selector", "") or "").strip()
    txt = "" if for_type else str(cmd.get("text", "") or "").strip()
    if sel:
        try:
            return page.locator(sel).first, f"选择器 {sel}"
        except Exception as exc:
            return None, f"选择器无效: {exc}"
    if txt:
        return page.get_by_text(txt, exact=False).first, f"文字“{txt}”"
    return None, "缺少 selector/text 定位参数"



def _vision_el_center(page, el) -> Optional[Tuple[float, float]]:
    """元素包围盒中心坐标（视口像素，与视觉会话坐标同一基准）。"""
    try:
        box = el.bounding_box()
    except Exception:
        return None
    if not box:
        return None
    return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)



def _click_flash(page, x: float, y: float) -> None:
    """点击视觉反馈（v1.21.0）：在点击位置触发一圈扩散涟漪（白圈黑边，~0.5s 淡出），
    下一张截图里能直接看到"刚才在这里点了"。涟漪函数由 CURSOR_OVERLAY_JS 注入；
    注入失败（极端：覆盖层没起来）时静默跳过——不影响点击本身。"""
    try:
        page.evaluate(
            "([x, y]) => { if (window.__aiCursorFlash) window.__aiCursorFlash(x, y); }",
            [x, y],
        )
    except Exception:
        pass



def _vision_dom_action(page, act: str, cmd: Dict, max_attempts: int = 3) -> Dict:
    """DOM 精准执行 click/dblclick/right_click/move/scroll：
    定位(selector/文字) → 等可见(3s) → 包围盒中心执行(scroll=滚进视口) →
    expect_gone 可选验证 → 失败自动重试（默认 3 次，间隔 400ms）。"""
    reason = "未尝试"
    for attempt in range(1, max_attempts + 1):
        el, how = _vision_find_el(page, cmd)
        if el is None:
            return {"ok": False, "note": f"DOM精准模式定位失败: {how}"}
        try:
            el.wait_for(state="visible", timeout=3000)
            if act == "scroll":
                el.scroll_into_view_if_needed(timeout=3000)
                return {"ok": True, "note": f"已按{how}定位并把元素滚动到视口内"}
            center = _vision_el_center(page, el)
            if not center:
                raise RuntimeError("拿不到元素包围盒（元素可能刚被页面移除）")
            cx, cy = center
            if act == "move":
                human_move(page, cx, cy)
                return {"ok": True, "note": f"已按{how}定位，鼠标移到元素中心 ({int(cx)},{int(cy)})"}
            if act == "dblclick":
                page.mouse.dblclick(cx, cy)
            elif act == "right_click":
                human_click(page, cx, cy, button="right")
            else:
                human_click(page, cx, cy)
            _click_flash(page, cx, cy)  # 点击涟漪反馈（截图可见"点在这"）
            page.wait_for_timeout(300)
            if cmd.get("expect_gone"):
                # 可选效果验证：要求点击后元素消失（关弹窗/关下拉这类）
                if el.is_visible():
                    raise RuntimeError("点击后元素仍可见（expect_gone 验证未通过）")
                return {"ok": True, "note": f"已按{how}定位点击 ({int(cx)},{int(cy)})，元素已消失（验证通过）"}
            return {"ok": True, "note": f"已按{how}定位点击元素中心 ({int(cx)},{int(cy)})"}
        except Exception as exc:
            reason = str(exc)
            if attempt < max_attempts:
                try:
                    page.wait_for_timeout(400)
                except Exception:
                    pass
    return {"ok": False, "note": f"DOM精准{act}失败（已重试{max_attempts}次）: {reason[:160]}"}



def _vision_dom_type(page, cmd: Dict, max_attempts: int = 3) -> Dict:
    """DOM 精准输入（type + selector）：等输入框可见 → 点中心聚焦 → 键盘输入 →
    回读验证（value/innerText 应包含所输内容）→ 不过则 JS 设值兜底
    （input/textarea 设 value+补发 input/change 事件；富文本编辑器用
    execCommand insertText 触发真实 input——React 受控组件/ProseMirror 认这套，
    治"输入后文字消失"）→ 仍失败重试。"""
    text = str(cmd.get("text", ""))
    if not text:
        return {"ok": False, "note": "type 缺少 text（要输入的内容）"}
    reason = "未尝试"
    for attempt in range(1, max_attempts + 1):
        el, how = _vision_find_el(page, cmd, for_type=True)
        if el is None:
            return {"ok": False, "note": f"DOM精准输入需要 selector 定位输入框: {how}"}
        try:
            el.wait_for(state="visible", timeout=3000)
            center = _vision_el_center(page, el)
            if center:
                human_click(page, center[0], center[1])  # 点中心聚焦输入框
            human_type(page, text)
            page.wait_for_timeout(250)
            val = el.evaluate(
                "e => (e.value !== undefined ? e.value : (e.innerText || '')) || ''"
            )
            if text in val:
                return {"ok": True, "note": f"已按{how}聚焦并输入 {len(text)} 字（回读验证通过）"}
            # 回读没有 → 受控组件没吃到按键：JS 设值兜底 + 补发事件
            el.evaluate(
                """(e, t) => {
                    if (e.value !== undefined) {
                        e.value = t;
                        e.dispatchEvent(new Event('input', {bubbles: true}));
                        e.dispatchEvent(new Event('change', {bubbles: true}));
                    } else {
                        e.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('insertText', false, t);
                    }
                }""",
                text,
            )
            page.wait_for_timeout(250)
            val2 = el.evaluate(
                "e => (e.value !== undefined ? e.value : (e.innerText || '')) || ''"
            )
            if text in val2:
                return {"ok": True,
                        "note": f"已按{how}输入 {len(text)} 字（键盘输入未生效，JS 设值兜底生效，已验证）"}
            reason = f"回读验证失败：输入框内容不含所输文本（现有内容 {len(val2)} 字符）"
        except Exception as exc:
            reason = str(exc)
        if attempt < max_attempts:
            try:
                page.wait_for_timeout(400)
            except Exception:
                pass
    return {"ok": False, "note": f"DOM精准输入失败（已重试{max_attempts}次）: {reason[:160]}"}



def _vision_exec_action(page, cmd: Dict, output_dir: Path, prefix: str,
                        wait_cap_ms: int = 0, debug_port: int = 0) -> Dict:
    """执行一条视觉会话指令，返回 {ok, note}。指令格式见 _vision_route 文档。
    wait_cap_ms>0 时 wait 指令的毫秒数被钳到该值（会话剩余预算），防长 wait 拖爆总超时。
    debug_port>0 时 eval 指令带死循环看门狗（超时强杀页面，会话保活）。"""
    act = (cmd.get("action") or "").strip().lower()
    # DOM 精准模式（v1.15.0，默认推荐）：给了 selector（或 click/move/scroll 给了 text）
    # 就走"定位→等可见→包围盒中心→验证→重试"精准路径，比从截图猜像素准。
    # type 的 text 是输入内容（历史语义），type 精准模式只认 selector。
    # 只给 x/y 时保持原坐标行为完全不变（向后兼容，AI 按场景自选）。
    _has_locator = bool(str(cmd.get("selector", "") or "").strip())
    if act in ("click", "dblclick", "right_click", "move", "scroll"):
        if _has_locator or str(cmd.get("text", "") or "").strip():
            return _vision_dom_action(page, act, cmd)
    if act == "type" and _has_locator:
        return _vision_dom_type(page, cmd)
    # v1.21.0 快捷点击：click/dblclick/right_click 不给 x/y 也不给定位 →
    # 直接点"当前鼠标位置"（先 move 瞄准，再发 {"action":"click"} 即可，不用重复报坐标；
    # 可选 "button":"right" 换右键）。move 仍需坐标/定位（移到原地没意义）。
    quick = False
    if act in ("click", "dblclick", "right_click", "move") and ("x" not in cmd or "y" not in cmd):
        if act == "move":
            return {"ok": False, "note": "move 缺少定位：精准模式给 selector 或 text（推荐），坐标模式给 x/y（先发 elements 拿准坐标）"}
        try:
            cur = page.evaluate("() => ({x: window.__mx || 0, y: window.__my || 0})") or {}
        except Exception as exc:
            return {"ok": False, "note": f"快捷点击失败：读不到当前鼠标位置（{exc}）"}
        x, y = int(cur.get("x", 0)), int(cur.get("y", 0))
        quick = True
    else:
        x, y = cmd.get("x", 0), cmd.get("y", 0)
    try:
        if act == "click":
            # button 参数：{"action":"click","button":"right"} = 右键（默认左键）
            btn = "right" if str(cmd.get("button", "")).lower() == "right" else "left"
            human_click(page, x, y, button=btn)
        elif act == "dblclick":
            page.mouse.dblclick(x, y)
        elif act == "right_click":
            human_click(page, x, y, button="right")
        elif act == "move":
            human_move(page, x, y)
        elif act == "drag":
            # 拖动三件套：move→down→move(steps 分步插值)→up。
            # 覆盖滑块/画布类（mousedown-mousemove-mouseup 监听）；
            # HTML5 draggable 元素（dragstart 事件）此模拟不保证触发
            if any(k not in cmd for k in ("x", "y", "to_x", "to_y")):
                return {"ok": False, "note": "drag needs 'x','y'（起点）和 'to_x','to_y'（终点，视口像素）"}
            tx, ty = int(cmd["to_x"]), int(cmd["to_y"])
            human_move(page, x, y)
            page.mouse.down()
            human_move(page, tx, ty)  # 按住状态下的拟人拖拽轨迹
            page.mouse.up()
            return {"ok": True, "note": f"已拖动 ({x},{y}) → ({tx},{ty})"}
        elif act == "scroll":
            # x=横向增量(罕见,原生直发), y=纵向增量（正=向下,拟人分步）
            if x:
                page.mouse.wheel(x, cmd.get("y", 600))
            else:
                human_scroll(page, int(cmd.get("y", 600) or 0))
        elif act == "type":
            text = str(cmd.get("text", ""))
            if not text:
                return {"ok": False, "note": "type 缺少 text（要输入的内容）"}
            human_type(page, text)
            return {"ok": True, "note": f"已输入 {len(text)} 个字符"}
        elif act == "press":
            page.keyboard.press(str(cmd.get("key", "Enter")))
        elif act == "focus":
            # 按 CSS 选择器聚焦元素（比裸坐标点更可靠：盲点坐标会打到 BODY 上输入失效）
            sel = str(cmd.get("selector", ""))
            if not sel:
                return {"ok": False, "note": "focus 缺少 selector（CSS 选择器，如 input[name=q]）"}
            el = page.locator(sel).first
            el.focus(timeout=3000)
            tag = el.evaluate("e => e.tagName")
            return {"ok": True, "note": f"已聚焦 {tag}（选择器 {sel}）"}
        elif act == "goto":
            target = str(cmd.get("url", ""))
            if not target:
                return {"ok": False, "note": "goto 缺少 url（要打开的网址）"}
            page.goto(target, wait_until="domcontentloaded", timeout=30000)
            _wait_for_render(page, max_wait_sec=4.0)  # 同启动：会话内可交互，不用等满 10s
            # 懒加载滚动后回顶：视觉会话依赖视口坐标，停在页底会让 elements 坐标全错
            try:
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(300)
            except Exception:
                pass
        elif act == "back":
            page.go_back(timeout=15000)
        elif act == "forward":
            page.go_forward(timeout=15000)
        elif act == "reload":
            page.reload(wait_until="domcontentloaded", timeout=30000)
        elif act == "viewport":
            # 改视口尺寸：DeepSeek 视觉原生 800×800（超范围官方会压糊）；
            # 改完坐标基准变了，AI 需重新 elements 拿新坐标
            try:
                w, h = int(cmd.get("width", 0)), int(cmd.get("height", 0))
            except (TypeError, ValueError):
                return {"ok": False, "note": "viewport 参数需为整数"}
            if not (200 <= w <= 3840 and 200 <= h <= 3840):
                return {"ok": False, "note": "viewport 缺少 width/height（各 200-3840 px）"}
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(300)  # 等重排稳定
            return {"ok": True, "note": f"viewport 已改为 {w}×{h}（坐标基准变了，建议重新 elements）"}
        elif act == "wait":
            ms = int(cmd.get("ms", 1000))
            if wait_cap_ms > 0:
                ms = max(0, min(ms, wait_cap_ms))  # 钳到剩余预算：长 wait 拖爆总超时
            page.wait_for_timeout(ms)
        elif act == "elements":
            # 元素标注：返回视口内所有可见可点元素（tag/text/中心坐标/尺寸）。
            # 视觉模型点按钮前先 elements 拿准坐标，不用从截图里猜像素
            els = page.evaluate(ELEMENTS_JS) or []
            return {"ok": True, "note": "", "elements": els}
        elif act == "tabs":
            # 标签页清单：点击开了新标签后用 tabs 看、switch_tab 切过去
            tabs_info = []
            try:
                for i, p in enumerate(page.context.pages):
                    u = ""
                    t = ""
                    try:
                        u = p.url[:100]
                        t = (p.title() or "")[:40]
                    except Exception:
                        pass
                    tabs_info.append({"index": i, "url": u, "title": t,
                                      "current": p is page})
                return {"ok": True, "note": "", "tabs": tabs_info}
            except Exception as exc:
                return {"ok": False, "note": f"tabs 失败: {exc}"}
        elif act == "switch_tab":
            # 切标签页：{"action":"switch_tab","index":1}。点击开新标签后看新标签内容
            try:
                idx = int(cmd.get("index", -1))
            except (TypeError, ValueError):
                return {"ok": False, "note": "switch_tab 缺少 index（整数，先发 tabs 查清单）"}
            pages = page.context.pages
            if not (0 <= idx < len(pages)):
                return {"ok": False, "note": f"index 超范围（现有 {len(pages)} 个标签，先发 tabs 查清单）"}
            return {"ok": True, "note": "", "_switch_to": pages[idx]}
        elif act == "eval":
            # 防死循环卡死会话：evaluate 必须在主线程跑（Playwright sync API
            # 禁止跨线程调用），另起看门狗线程盯梢——10s 不返回就经 DevTools
            # HTTP 端点强杀页面，阻塞中的 evaluate 随即抛 "Target closed" 解卡；
            # 调用方收到 _page_dead 后重建页面，会话保活（AI 重新 goto 即可）
            import threading as _th
            js = str(cmd.get("js", "1+1"))
            cancelled, fired = _th.Event(), _th.Event()
            wt = None
            if debug_port:
                wt = _th.Thread(target=_eval_watchdog_thread,
                                args=(debug_port, 10, cancelled, fired), daemon=True)
                wt.start()
            try:
                val = page.evaluate(js)
            except Exception as exc:
                cancelled.set()
                if wt:
                    wt.join(5)
                if fired.is_set():
                    return {"ok": False, "_page_dead": True,
                            "note": "eval 超时(>10s)：疑似死循环 JS，页面已重置（会话保留，请重新 goto）"}
                return {"ok": False, "note": f"eval 失败: {str(exc)}"[:300]}
            cancelled.set()
            if wt:
                wt.join(5)
            if fired.is_set() or page.is_closed():
                # 竞态兜底：eval 刚返回但看门狗已开杀 → 同样走页面重建
                return {"ok": False, "_page_dead": True,
                        "note": "eval 超时(>10s)：页面已重置（会话保留，请重新 goto）"}
            # data 字段给结构化结果（note 是纯文本给 AI 看的）
            return {"ok": True, "note": f"eval: {val}"[:400], "data": val}
        elif act in ("screenshot", "quit"):
            pass  # 由调用方处理
        else:
            return {"ok": False, "note": f"未知动作: {act}（支持: {', '.join(VISION_ACTIONS)}）"}
        # 点击类动作（坐标/快捷模式）：涟漪反馈 + 短暂停留让下一张截图拍到扩散中的圈
        if act in ("click", "dblclick", "right_click"):
            _click_flash(page, x, y)
            try:
                page.wait_for_timeout(150)
            except Exception:
                pass
            if quick:
                return {"ok": True, "note": f"快捷点击：已在当前鼠标位置 ({x},{y}) 完成 {act}"}
        return {"ok": True, "note": ""}
    except Exception as exc:
        return {"ok": False, "note": f"{act} 失败: {exc}"}



def _skill_version() -> str:
    """读 package.json 版本号（项目版本唯一真相源）。
    会话启动横幅用它——日志必须自证版本，杜绝"老副本跑出诡异行为查半天"。"""
    try:
        pkg = Path(__file__).resolve().parent.parent.parent / "package.json"
        return json.loads(pkg.read_text(encoding="utf-8")).get("version", "?")
    except Exception:
        return "?"



def _vision_route(url: str, output_dir: Path, headed: bool = False, safe: bool = False,
                  max_screens: int = VISION_DEFAULT_MAX_SCREENS,
                  detail: str = "original", model: str = "",
                  session_timeout_sec: int = 900,
                  viewport_w: int = 1440, viewport_h: int = 900,
                  cookie_file: str = "", cookies_from_browser: str = "",
                  profile_dir: Optional[Path] = None,
                  captcha_mode: str = "off",
                  idle_timeout: Optional[int] = None,
                  linger: bool = False,
                  stealth: str = "full",
                  login_rescue: bool = False) -> Dict:
    """视觉会话模式（--method vision）：给多模态模型的"眼睛+手"。

    协议（stdin/stdout 各一行一个 JSON，AI Agent 驱动）：
      1. 启动后 stdout 输出初始状态（首屏截图 + 屏幕信息）
      2. AI 逐行往 stdin 写指令 JSON，例如：
         {"action":"click","text":"扫码登录"}          按页面文字找元素点中心（DOM精准，默认推荐）
         {"action":"click","selector":"button.submit"} 按选择器点元素中心（DOM精准，默认推荐）
         {"action":"click","x":100,"y":200}            按视口坐标点（原坐标模式，兼容保留）
         {"action":"click"}                            快捷点击：直接点当前鼠标位置（先 move 瞄准再发，不用重复报坐标）
         {"action":"click","button":"right"}           快捷右键：在当前鼠标位置右键（默认左键）
         {"action":"right_click","x":..,"y":..}        右键 / {"action":"dblclick",...} 双击（同样支持 text/selector）
         {"action":"move","text":"登录"}               鼠标移到元素中心；{"action":"move","x":..,"y":..} 坐标模式
         {"action":"drag","x":..,"y":..,"to_x":..,"to_y":..}  拖动（滑块/画布类；HTML5 draggable 不保证触发）
         {"action":"scroll","selector":"#footer"}      把元素滚进视口；{"action":"scroll","x":0,"y":600} 原坐标滚动（y 正=向下）
         {"action":"type","selector":"input[name=q]","text":"关键词"}  精准输入（点聚焦+输入+回读验证+JS兜底，治"输入后消失"）
         {"action":"type","text":"关键词"}             原模式：敲进当前焦点元素
         {"action":"press","key":"Enter"}              按键（精准输入后按回车提交）
         {"action":"focus","selector":"input[name=q]"} 按 CSS 选择器聚焦（输入前先 focus 比裸坐标点更可靠）
         {"action":"elements"}                         元素标注：返回视口内全部可点元素（tag/text/中心坐标/尺寸），点按钮前先拿这个
         {"action":"goto","url":"https://.."}          跳转 / back / forward / reload（启动 URL 失败会话也保活，可 goto 重试）
         {"action":"wait","ms":800}                    等待（等动画/懒加载）
         {"action":"screenshot"}                       主动重新截图
         {"action":"eval","js":"1+1"}                  执行 JS（只读用途，结构化结果放 state 的 eval_result 字段）
         {"action":"viewport","width":1280,"height":800}  改视口（默认 800×800=DeepSeek 原生；改完重新 elements）
         {"action":"shot_policy","every":3}            截图节奏：每 3 个成功动作截 1 张（默认 1=动一次拍一次）
         {"action":"shot_policy","interval_ms":1000}   空闲时每秒自动截 1 张（默认 0=关；预算耗尽自动停）
         {"action":"quit"}                             结束会话
         可选验证参数：click 加 "expect_gone": true = 点击后要求元素消失（关弹窗/关下拉类），
         验证不过会自动重试（click/move/scroll/type 精准模式失败均自动重试最多 3 次）。
      3. 每条指令执行后 stdout 输出新状态（新截图 + 屏幕信息），直到 quit 或 stdin 关闭

    兜底（防 AI 侧故障拖死本进程）：
      - 会话总时长上限 session_timeout_sec（默认 900s）：超时自动收尾退出，
        绝不因 AI 卡死/不发 quit 变僵尸进程；
      - 指令间隔看门狗：连续 idle_limit 秒收不到下一条指令视为 AI 断线，自动收尾退出
        （默认 120s；--headed 有人在场自动放宽 600s；--idle-timeout 显式覆盖，0=关闭）；
      - --linger：会话结束不立即关浏览器——--headed 窗口留给人看完手动关（上限1h），
        无头 30s 宽限自退。AI 脚本崩了浏览器现场不再消失；
      - 任何单条指令异常都返回 failed 状态继续会话，不会整体崩溃。

    状态 JSON 字段：
      event="state" | screenshot=最新截图路径 | screen=屏幕信息（视口/整页尺寸/DPR/鼠标/滚动）
      screenshots_used/max=截图计数（成本防护：单张≤384 token，超上限不再截图只报状态）
      api_hint=官方 API 调用参数（model/detail/384token 封顶等，照抄即可拼请求）
    """
    base = {"mode": "vision_session", "source_url": url, "output_dir": str(output_dir),
            "model": model or VISION_MODEL_NAME,
            "vision_capable": _is_vision_model(model) if model else True}
    shots_used = 0
    all_shots: List[str] = []
    last_auto_shot = time.time()  # 自动截图计时基准（任何一次截图都重置）

    def _emit_state(page, done: bool = False, note: str = "", extra: Optional[Dict] = None,
                    shoot: bool = True):
        nonlocal shots_used, last_auto_shot
        shot = None
        # shoot=False：坏JSON/失败指令页面没变化，不新截图（省配额），回退上一张
        if shoot and shots_used < max_screens:
            shot = _shot_viewport(page, output_dir)
            if shot:
                shots_used += 1
                all_shots.append(shot)
                last_auto_shot = time.time()  # 拍过就重置自动截图计时，避免动作拍完紧跟自动拍
        # 验证码检测默认关闭（v1.14.2）：此前默认每步检测+上报 captcha_detected，
        # 误报（轮播图/图标类）会让下游 AI"见到验证码就停手"，操作全部卡死。
        # 现在默认不检测不输出；确需检测时显式 --captcha-mode detect。
        captcha = []
        if captcha_mode == "detect":
            try:
                captcha = page.evaluate(CAPTCHA_JS) or []
            except Exception:
                pass
        state = {
            "event": "state",
            "done": done,
            "screenshot": shot or (all_shots[-1] if all_shots else None),
            "screen": _screen_info(page),
            "screenshots_used": shots_used,
            "screenshots_max": max_screens,
            "screenshot_budget_exhausted": shots_used >= max_screens,
            "api_hint": _vision_api_hint(detail),
        }
        if captcha:
            state["captcha_detected"] = captcha
            state["captcha_help"] = ("验证码只检测不绕过（合法合规）。人工接管：--headed --profile "
                                     "重开会话（登录态保留），人手动完成验证后 AI 发 wait 指令继续")
        if note:
            state["note"] = note
        if extra:
            state.update(extra)
        print(json.dumps(state, ensure_ascii=False), flush=True)
        return state

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {**base, "error": "playwright not installed"}

    try:
        with sync_playwright() as p:
            # 本地调试端口：eval 看门狗用它经 /json/close 强杀死循环页面
            # （仅绑 127.0.0.1，无对外暴露；其他路线不开，避免多余端口）。
            # --profile --headed 的人肉登录场景不开：字节级风控会扫调试端口，
            # 登录窗口期检测面越小越好（eval 看门狗随之退化为不启用，可接受）
            debug_port = 0 if (profile_dir and headed) else _free_port()
            browser = None
            context = None
            if profile_dir:
                # 持久化用户目录（--profile）：登录态/缓存跨会话保留，像真实浏览器。
                # 固定 UA：UA 每次变会让部分站点作废登录会话。
                # 同一目录同时只能开一个会话（Chromium 目录锁），打开失败如实降级。
                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        headless=not headed,
                        args=_browser_launch_args(safe) + ([f"--remote-debugging-port={debug_port}"] if debug_port else []),
                        user_agent=USER_AGENTS[0],
                        viewport={"width": viewport_w, "height": viewport_h},
                        locale="zh-CN", timezone_id="Asia/Shanghai",
                        ignore_https_errors=True,
                        **({"service_workers": "block"} if safe else {}),
                    )
                except Exception as exc:
                    sys.stderr.write(f"[profile] 持久化上下文打开失败（目录被占用/损坏）: {exc}\n"
                                     "[profile] 回退一次性上下文\n")
                    context = None
            if context is None:
                browser = p.chromium.launch(
                    headless=not headed,
                    args=_browser_launch_args(safe) + ([f"--remote-debugging-port={debug_port}"] if debug_port else []))
                context = browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    # 视口默认 800×800 = DeepSeek 视觉原生分辨率（超范围会被官方压糊）；
                    # AI 可用 viewport 指令或 --viewport 参数改（不局限于 DeepSeek）
                    viewport={"width": viewport_w, "height": viewport_h},
                    locale="zh-CN", timezone_id="Asia/Shanghai",
                    ignore_https_errors=True,
                    **({"service_workers": "block"} if safe else {}),
                )
            try:
                stealth_used = _apply_stealth(context, stealth)
                # 虚拟鼠标指针：无头截图不渲染系统光标——注入放大白色箭头覆盖层，
                # AI 在截图里直接看到"鼠标在哪"（screen.mouse 坐标仍在状态流里）
                context.add_init_script(MOUSE_TRACK_JS + CURSOR_OVERLAY_JS)
                # 登录态注入（--cookies / --cookies-from-browser）：
                # 豆包等登录墙站点带 cookie 开会，否则能打字但发送无反应
                if cookie_file or cookies_from_browser:
                    _inject_login_cookies(context, cookie_file, cookies_from_browser, "vision")
                page = context.pages[0] if (browser is None and context.pages) else context.new_page()
                if safe:
                    _setup_safe_mode(context, page)
                # 目录已有旧截图时提醒（自动清理有误删风险，只提示）
                try:
                    old_shots = len(list(output_dir.glob("screen_*.png")))
                    if old_shots:
                        print(f"[提示] 输出目录已有 {old_shots} 张旧截图，本次会话截图会继续追加",
                              file=sys.stderr)
                except Exception:
                    pass
                startup_failed = None
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as exc:
                    # 启动 URL 失败不杀会话：切空白页保活，AI 可发 goto 指令换 URL 重试
                    startup_failed = str(exc)
                    try:
                        page.goto("about:blank")
                    except Exception:
                        pass
                if startup_failed is None:
                    # 视觉会话等 4s 就够：会话可交互，AI 可自行 wait/reload；
                    # 共享版默认 10s 会让文字少的页面（图库等）白等
                    _wait_for_render(page, max_wait_sec=4.0)
                    # 懒加载滚动后回顶：视觉会话依赖视口坐标，停在页底会让 elements 坐标全错
                    try:
                        page.evaluate("window.scrollTo(0, 0)")
                        page.wait_for_timeout(300)
                    except Exception:
                        pass
                # 首屏带上 vision_capable/model：AI 进会话第一眼就知道自己能不能看图
                # （此前只在 return 路径的 dict 里有，stdout 状态流里看不到）
                init_extra = {"vision_capable": base["vision_capable"], "model": base["model"]}
                # 登录兜底（--login-rescue）：扫码被风控拒发 session 时，自动从本机
                # 浏览器接种目标域登录 cookie 并刷新（人肉在真浏览器登录，工具搬登录态）
                rescue_note = ""
                if login_rescue and startup_failed is None:
                    rescue_note = _login_rescue(context, page, url)
                    sys.stderr.write(f"[{rescue_note}]\n")
                    if "已从" in rescue_note:
                        # 接种后刷新过页面：补一轮渲染等待+回顶，坐标基准才准
                        _wait_for_render(page, max_wait_sec=4.0)
                        try:
                            page.evaluate("window.scrollTo(0, 0)")
                            page.wait_for_timeout(300)
                        except Exception:
                            pass
                    init_extra["login_rescue"] = rescue_note
                # 重定向告警：请求 URL 与最终 URL 不一致时告知 AI
                if startup_failed is None and url and page.url != url and page.url != "about:blank":
                    init_extra["redirected_from"] = url
                _emit_state(page, note=(f"启动 URL 打不开：{startup_failed}"
                                        "（会话保留，可发 goto 指令换 URL）") if startup_failed else "",
                            extra=init_extra, shoot=not startup_failed)  # 启动失败不拍空白页浪费截图预算
                # 指令循环：stdin 逐行 JSON → 执行 → 输出新状态（EOF/quit 退出）。
                # 看门狗兜底（跨平台方案：读线程+队列，Windows 的 stdin 不是 socket
                # 用不了 selectors）：AI 卡死不发指令（120s 断线）或会话超总时长
                # （默认 900s）都自动收尾退出——绝不因调用方故障变成挂死进程
                import queue as _queue
                import threading as _threading

                cmd_q: "queue.Queue[Optional[str]]" = _queue.Queue()

                # 新标签页自动跟踪（v1.16.0）：点击开了新标签（相关搜索/热搜常
                # target=_blank）时工具此前还盯旧页截图。现在监听 context 级
                # page 事件，新标签出现即自动切过去（note 告知，AI 也可 switch_tab 切回）
                new_tab_box: "queue.Queue" = _queue.Queue()

                def _on_new_tab(np):
                    try:
                        new_tab_box.put(np)
                    except Exception:
                        pass

                try:
                    page.context.on("page", _on_new_tab)
                except Exception:
                    pass

                def _stdin_reader():
                    try:
                        for ln in sys.stdin:
                            cmd_q.put(ln)
                    except Exception:
                        pass
                    finally:
                        cmd_q.put(None)  # EOF/异常统一哨兵

                reader = _threading.Thread(target=_stdin_reader, daemon=True)
                reader.start()
                session_start = time.time()
                # 空闲看门狗：默认 120s 判 AI 断线；--headed 有人在场自动放宽到 600s
                # （扫码/人肉操作不被误杀）；--idle-timeout 显式覆盖（0=关闭，只受总时长约束）
                if idle_timeout is not None and idle_timeout > 0:
                    idle_limit = idle_timeout
                elif idle_timeout == 0:
                    idle_limit = max(session_timeout_sec, 1)
                elif headed:
                    idle_limit = 600
                else:
                    idle_limit = 120
                # 启动横幅（stderr）：版本+关键参数一目了然——日志自证身份，
                # 杜绝"老副本跑出诡异行为（如 --headed 仍 120s 断线）查半天"
                sys.stderr.write(
                    f"[vision] deepseek-web-search v{_skill_version()} | "
                    f"stealth={stealth_used} profile={'开' if profile_dir else '关'} "
                    f"headed={headed} idle看门狗={idle_limit}s captcha={captcha_mode} "
                    f"调试口={'开' if debug_port else '关'} "
                    f"login_rescue={'开' if login_rescue else '关'}\n"
                )
                # 截图节奏（shot_policy 指令可调）：默认动一次拍一张；空闲自动拍默认关
                shot_every = 1
                auto_interval_ms = 0
                actions_since_shot = 0
                last_cmd_time = session_start
                while True:
                    now = time.time()
                    if now - session_start > session_timeout_sec:
                        _emit_state(page, done=True, note="会话总时长到达上限，自动收尾")
                        break
                    # 等待切片：取「空闲看门狗剩余」「下次自动截图」两者最早的（每片上限 2s）
                    wait = (last_cmd_time + idle_limit) - now
                    if auto_interval_ms:
                        wait = min(wait, auto_interval_ms / 1000.0)
                    wait = max(0.05, min(wait, 2.0))
                    try:
                        line = cmd_q.get(timeout=wait)
                        last_cmd_time = time.time()
                    except _queue.Empty:
                        now2 = time.time()
                        if now2 - last_cmd_time >= idle_limit:
                            _emit_state(page, done=True,
                                        note=f"空闲看门狗：{idle_limit}s 未收到指令，判定 AI 侧断线，自动收尾")
                            break
                        # 空闲自动截图：到点且预算没耗尽才拍；耗尽则自动关并告知（防刷屏）
                        if auto_interval_ms and (now2 - last_auto_shot) * 1000 >= auto_interval_ms:
                            if shots_used < max_screens:
                                _emit_state(page, note="空闲自动截图")
                            else:
                                _emit_state(page, note="自动截图已停：截图预算耗尽", shoot=False)
                                auto_interval_ms = 0
                        continue
                    if line is None:  # EOF：stdin 关闭
                        _emit_state(page, done=True, note="stdin 已关闭（EOF），会话结束")
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cmd = json.loads(line)
                    except Exception:
                        _emit_state(page, note="指令不是合法 JSON，已忽略", shoot=False)
                        continue
                    act = (cmd.get("action") or "").strip().lower()
                    if act == "quit":
                        _emit_state(page, done=True, note="会话已关闭")
                        break
                    if act == "shot_policy":
                        # 截图节奏调整：every=每 N 个成功动作截一张（默认1）；
                        # interval_ms=空闲时自动截图间隔（默认0=关）。两者可只给其一
                        try:
                            shot_every = max(1, int(cmd.get("every", shot_every)))
                            auto_interval_ms = max(0, int(cmd.get("interval_ms", auto_interval_ms)))
                        except (TypeError, ValueError):
                            _emit_state(page, note="shot_policy 参数需为整数（every≥1，interval_ms≥0）", shoot=False)
                            continue
                        if auto_interval_ms:
                            last_auto_shot = time.time()  # 开启后从现在起计时，不追补历史
                        _emit_state(page, note=(f"截图节奏: 每 {shot_every} 个动作一张"
                                                + (f"，空闲每 {auto_interval_ms}ms 自动一张"
                                                   if auto_interval_ms else "，自动截图关")),
                                    shoot=False)
                        continue
                    # 新标签自动切换：上一步点击开了新标签（相关搜索/热搜类）→
                    # 切过去再执行本条指令，截图/操作都落在新标签上
                    try:
                        np = new_tab_box.get_nowait()
                        if np is not page and not np.is_closed():
                            try:
                                np.wait_for_load_state("domcontentloaded", timeout=8000)
                            except Exception:
                                pass
                            page = np
                            _emit_state(page, note=f"点击打开了新标签页，已自动切换：{page.url[:100]}",
                                        shoot=False)
                    except _queue.Empty:
                        pass
                    # wait 钳到剩余预算：超时检查在指令间隙，长 wait 会拖爆总超时
                    remaining_ms = int((session_timeout_sec - (time.time() - session_start)) * 1000)
                    r = _vision_exec_action(page, cmd, output_dir, "vision",
                                            wait_cap_ms=max(0, remaining_ms),
                                            debug_port=debug_port)
                    if r.get("_page_dead"):
                        # eval 死循环兜底：看门狗已杀掉卡死页面，context 还活着，
                        # 这里直接重建空白页，会话保活（AI 重新 goto 即可）
                        try:
                            page = context.new_page()
                            if safe:
                                # 重建页要重挂弹窗拦截：context.route 还在，但 popup
                                # 监听挂在旧 page 上，跟旧页一起丢了（修复安全模式缺口）
                                def _close_rebuilt_popup(popup):
                                    try:
                                        popup.close()
                                    except Exception:
                                        pass
                                page.on("popup", _close_rebuilt_popup)
                        except Exception:
                            # context 也没了：输出收尾状态后走异常路径，
                            # finally 里 browser.close() 正常清理，绝不挂死
                            print(json.dumps({
                                "event": "state", "done": True,
                                "screenshot": all_shots[-1] if all_shots else None,
                                "screenshots_used": shots_used, "screenshots_max": max_screens,
                                "note": "eval 死循环且页面无法重建，会话自动收尾",
                            }, ensure_ascii=False), flush=True)
                            raise
                        _emit_state(page, note=r.get("note", "页面已重置"), shoot=False)
                        continue
                    if act == "screenshot":
                        r = {"ok": True, "note": ""}
                    # switch_tab 指令：真正切页由会话循环做（page 是循环局部变量）
                    if r.get("_switch_to") is not None:
                        target_pg = r["_switch_to"]
                        if not target_pg.is_closed():
                            page = target_pg
                            r = {"ok": True,
                                 "note": f"已切到标签 {page.url[:100]}（坐标基准变了，建议重新 elements）"}
                        else:
                            r = {"ok": False, "note": "目标标签已关闭，发 tabs 重新查清单"}
                    if act in ("goto", "reload", "back", "forward"):
                        page.wait_for_timeout(800)
                    # elements 指令的元素清单带进状态（视觉模型直接读坐标点按钮）
                    extra = {}
                    if r.get("elements"):
                        extra["elements"] = r["elements"]
                    if r.get("tabs"):
                        extra["tabs"] = r["tabs"]
                    if "data" in r:
                        extra["eval_result"] = r["data"]  # eval 结构化结果
                    extra = extra or None
                    # 截图节奏：screenshot 指令强制拍；成功动作每 every 张拍一次；失败不拍
                    if act == "screenshot":
                        shoot_now, actions_since_shot = True, 0
                    elif r.get("ok", True):
                        actions_since_shot += 1
                        shoot_now = actions_since_shot >= shot_every
                        if shoot_now:
                            actions_since_shot = 0
                    else:
                        shoot_now = False
                    _emit_state(page, note=r.get("note", ""), extra=extra, shoot=shoot_now)
            finally:
                if linger:
                    # 会话结束不立即关浏览器（--linger）：AI 脚本崩了/EOF/quit 时现场保留——
                    # --headed 窗口留给人看完手动关（上限 1h 防真僵尸）；无头没人看，30s 宽限即退
                    try:
                        print(json.dumps({
                            "event": "state", "done": True,
                            "note": ("AI 已断开，浏览器窗口保留中——看完手动关闭窗口即退出"
                                     if headed else "AI 已断开，无头浏览器保留 30s 后自动退出"),
                        }, ensure_ascii=False), flush=True)
                        deadline = time.time() + (3600 if headed else 30)
                        while time.time() < deadline:
                            time.sleep(1)
                            try:
                                if browser is not None:
                                    if not browser.is_connected():
                                        break  # 用户关了窗口
                                elif context is not None:
                                    if not context.pages:
                                        break  # 持久化上下文的窗口被关闭
                            except Exception:
                                break  # 连接已死 = 窗口已关
                    except Exception:
                        pass
                if browser is not None:
                    browser.close()
                elif context is not None:
                    try:
                        context.close()  # 持久化上下文：close 才把 cookie/缓存刷进用户目录
                    except Exception:
                        pass  # 窗口已被用户手动关闭时 close 会抛，属正常收尾
        return {**base, "count": len(all_shots), "screenshots": all_shots,
                "screenshots_used": shots_used, "api_hint": _vision_api_hint(detail)}
    except Exception as exc:
        return {**base, "count": len(all_shots), "screenshots": all_shots,
                "screenshots_used": shots_used, "error": f"vision session error: {exc}"}

