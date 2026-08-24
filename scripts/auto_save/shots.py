"""截图/屏幕信息工具（v1.22.0 批 A 自 auto_save_browser.py 搬迁，零逻辑改动）：
视口/整页/分段截图、屏幕信息、独立截图模式（--screenshot 配任意路线）。
vision 会话与主文件 --screenshot 共用；分段上限常量随迁。"""
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from .browser_base import _apply_stealth, _browser_launch_args, _setup_safe_mode, _wait_for_render
from .constants import USER_AGENTS
from .humanize import human_scroll

__all__ = [
    "VISION_MAX_IMAGE_EDGE", "VISION_SEGMENT_MAX_PX", "MOUSE_TRACK_JS",
    "_screen_info", "_scroll_page_to_bottom", "_capture_full_page",
    "_shot_viewport", "_screenshot_standalone",
]

VISION_MAX_IMAGE_EDGE = 8192      # 官方图片最长边上限（px），超长页面必须分段


VISION_SEGMENT_MAX_PX = 6000      # 分段截图单段高度上限（留余量，每段原始分辨率比一张巨图看得清）


# 鼠标位置跟踪（注入页面：截图/视觉会话里读取"鼠标现在在哪"；shots 与 vision 共用，
# 定义在本层避免 vision↔shots 循环引用——vision.py 反向 from .shots import）
MOUSE_TRACK_JS = """
window.__mx = 0; window.__my = 0;
document.addEventListener('mousemove', e => { window.__mx = e.clientX; window.__my = e.clientY; });
"""



def _screen_info(page) -> Dict:
    """屏幕/页面/鼠标信息（让视觉模型知道屏幕多大、页面多长、鼠标在哪）。"""
    try:
        info = page.evaluate(
            """() => ({
                vw: window.innerWidth, vh: window.innerHeight,
                pw: Math.max(document.documentElement.scrollWidth, document.body ? document.body.scrollWidth : 0),
                ph: Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0),
                dpr: window.devicePixelRatio || 1,
                mx: window.__mx || 0, my: window.__my || 0,
                sy: window.scrollY || document.documentElement.scrollTop || 0,
                ae: (document.activeElement && document.activeElement.tagName)
                      ? document.activeElement.tagName.toLowerCase()
                        + (document.activeElement.id ? '#' + document.activeElement.id : '')
                      : '',
            })"""
        ) or {}
    except Exception:
        info = {}
    return {
        "viewport": {"width": info.get("vw", 0), "height": info.get("vh", 0)},
        "page": {"width": info.get("pw", 0), "height": info.get("ph", 0)},
        "device_pixel_ratio": info.get("dpr", 1),
        "mouse": {"x": info.get("mx", 0), "y": info.get("my", 0)},
        "scroll_y": info.get("sy", 0),
        "active_element": info.get("ae", ""),
        "url": page.url,
    }



def _scroll_page_to_bottom(page, step_px: int = 1200, pause_ms: int = 500, max_steps: int = 40) -> bool:
    """逐步滚到底触发懒加载（Playwright full_page 截图不会触发懒加载，必须先滚）。"""
    try:
        for _ in range(max_steps):
            before = page.evaluate("window.scrollY")
            page.mouse.wheel(0, step_px)
            page.wait_for_timeout(pause_ms)
            after = page.evaluate("window.scrollY")
            ph = page.evaluate("Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)")
            if after <= before or after >= ph - page.evaluate("window.innerHeight"):
                break
        return True
    except Exception:
        return False



def _capture_full_page(page, output_dir: Path, prefix: str = "page",
                       segment_max_px: int = VISION_SEGMENT_MAX_PX) -> List[str]:
    """整页截图：滚底触发懒加载 → 回顶 → 全页 PNG；页面超高（>8192px 官方上限）自动
    分段（每段原始分辨率）。返回截图路径列表。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    _scroll_page_to_bottom(page)
    try:
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(600)
    except Exception:
        pass
    try:
        ph = page.evaluate("Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)")
        vw = page.evaluate("window.innerWidth")
    except Exception:
        ph, vw = 0, 0
    stamp = int(time.time())
    paths: List[str] = []
    try:
        if 0 < ph <= VISION_MAX_IMAGE_EDGE:
            # 单张全页截图（高度在官方上限内）
            p = output_dir / f"{prefix}_{stamp}_full.png"
            page.screenshot(path=str(p), full_page=True)
            paths.append(str(p))
        elif ph > VISION_MAX_IMAGE_EDGE:
            # 超高页面：按 scroll 位置分段截（clip 顶部对齐滚动点），每段原始分辨率。
            # 必须 full_page=True：不带它 clip 会被钳到视口内（首段只剩一屏），
            # 且起点超出视口直接抛 "Clipped area outside"（后续段全部丢失）
            seg = 0
            y = 0
            while y < ph and seg < 20:
                h = min(segment_max_px, ph - y)
                p = output_dir / f"{prefix}_{stamp}_seg{seg}.png"
                page.screenshot(path=str(p), full_page=True, clip={"x": 0, "y": y, "width": vw, "height": h})
                paths.append(str(p))
                y += h
                seg += 1
    except Exception:
        pass
    return paths



def _shot_viewport(page, output_dir: Path, prefix: str = "screen") -> Optional[str]:
    """当前视口截图（视觉会话每步操作后的"屏幕快照"）。
    文件名时间戳+序号双保险，同毫秒多张不互相覆盖。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    _shot_viewport._seq = getattr(_shot_viewport, "_seq", 0) + 1
    p = output_dir / f"{prefix}_{int(time.time() * 1000)}_{_shot_viewport._seq:03d}.png"
    try:
        page.screenshot(path=str(p))
        return str(p)
    except Exception:
        return None



def _screenshot_standalone(url: str, output_dir: Path, headed: bool = False, safe: bool = False,
                           stealth: str = "full", profile_dir: Optional[Path] = None) -> Dict:
    """独立截图（--screenshot 标志，配任意模式）：打开页面→渲染等待→懒加载→整页/分段截图。
    不干扰原模式逻辑，截图结果合并进 JSON。
    v1.22.0 模式审计：profile_dir 透传——--profile 登录墙页面截图不再拿空壳页。"""
    result: Dict = {"screenshots": [], "screen": {}}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["error"] = "playwright not installed"
        return result
    try:
        with sync_playwright() as p:
            browser = None
            context = None
            try:
                if profile_dir:
                    # 持久化用户目录：与主路线同款登录态（固定 UA 防会话作废）
                    try:
                        context = p.chromium.launch_persistent_context(
                            user_data_dir=str(profile_dir),
                            headless=not headed,
                            args=_browser_launch_args(safe),
                            user_agent=USER_AGENTS[0],
                            viewport={"width": 1920, "height": 1080},
                            locale="zh-CN", timezone_id="Asia/Shanghai",
                            ignore_https_errors=True,
                            **({"service_workers": "block"} if safe else {}),
                        )
                    except Exception:
                        # 目录被占用（主路线会话还开着）→ 一次性上下文兜底
                        context = None
                if context is None:
                    browser = p.chromium.launch(headless=not headed, args=_browser_launch_args(safe))
                    context = browser.new_context(
                        user_agent=random.choice(USER_AGENTS),
                        viewport={"width": 1920, "height": 1080},
                        locale="zh-CN", timezone_id="Asia/Shanghai",
                        ignore_https_errors=True,
                        **({"service_workers": "block"} if safe else {}),
                    )
                _apply_stealth(context, stealth)
                context.add_init_script(MOUSE_TRACK_JS)
                page = context.pages[0] if (browser is None and context.pages) else context.new_page()
                if safe:
                    _setup_safe_mode(context, page)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                _wait_for_render(page)
                shot_dir = output_dir / "screenshots"
                result["screenshots"] = _capture_full_page(page, shot_dir)
                result["screen"] = _screen_info(page)
            finally:
                if browser is not None:
                    browser.close()
                else:
                    try:
                        context.close()
                    except Exception:
                        pass
    except Exception as exc:
        result["error"] = f"screenshot error: {exc}"
    return result

