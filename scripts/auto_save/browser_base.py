"""浏览器基础设施：launch 参数 / 伪装应用 / 安全模式拦截 / 字节落盘 / 启动样板归一。
第 3 批拆分（v1.22.0）：自 auto_save_browser.py 搬迁，零逻辑改动；
另按 --real-headless 挂钩无头拟真（JS 指纹补丁 + launch 参数），与 --stealth 正交。
批 3 归一：routes.py 四份 launch 样板合并为 _open_page() 单实现（差异全部入参）。
依赖方向：browser_base → urlrules/constants/realheadless/cookies（无环）。"""
import os
import random
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from .constants import STEALTH_JS, USER_AGENTS
from .cookies import _inject_login_cookies
from .humanize import human_scroll
from .urlrules import _safe_filename, _safe_request_reason

__all__ = [
    "_setup_safe_mode", "_browser_launch_args", "_apply_stealth", "_save_bytes",
    "_wait_for_render", "_open_page",
    "set_proxy", "get_proxy", "_proxy_urlopen",
]

# ---- 代理（v1.23.0）：模块级状态，全链一处设置处处生效 ----
# 沿用 humanize/realheadless/ytdlp_opts 的行为开关模式：--proxy 解析后 set_proxy()
# 落一次，浏览器路线（_open_page）、urllib 直连（routes 三处）、yt-dlp（ydl_opts）
# 全部读取同一状态。默认空 = 直连（旧行为零变化）。下载核心此前完全没有代理能力
# （search_browser 有 --proxy 但 auto_save 没有），海外/受限网络场景无退路。
_PROXY = {"server": ""}


def set_proxy(server: str) -> str:
    """设置全局代理（http://host:port 或 socks5://...，空串=清除）。返回生效值。"""
    _PROXY["server"] = (server or "").strip()
    return _PROXY["server"]


def get_proxy() -> str:
    return _PROXY["server"]


def _proxy_urlopen(req, timeout: float):
    """带代理状态的 urlopen：未设代理时等价原生 urlopen；设了就走显式
    ProxyHandler（urllib 默认只认环境变量，显式代理必须自建 opener）。"""
    server = _PROXY["server"]
    if not server:
        return urllib.request.urlopen(req, timeout=timeout)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": server, "https": server}))
    return opener.open(req, timeout=timeout)


def _proxy_launch_kw() -> Dict:
    """launch 级 proxy kwargs（Chromium launch/launch_persistent_context 都吃）。"""
    server = _PROXY["server"]
    return {"proxy": {"server": server}} if server else {}


def _setup_safe_mode(context, page) -> Dict[str, int]:
    """安全模式浏览器加固：请求拦截 + 弹窗全关。返回 blocked 计数（闭包自增）。
    进程沙箱/站点隔离由 launch 参数控制（见 _browser_launch_args）。"""
    blocked = {"requests": 0, "popups": 0}

    def _route(route):
        try:
            reason = _safe_request_reason(route.request.url, route.request.resource_type)
            if reason:
                blocked["requests"] += 1
                sys.stderr.write(f"[safe-block] {reason}: {route.request.url[:120]}\n")
                route.abort()
                return
            route.continue_()
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    def _popup(popup):
        blocked["popups"] += 1
        try:
            sys.stderr.write(f"[safe-block] 弹窗已关闭: {popup.url[:120]}\n")
            popup.close()
        except Exception:
            pass

    context.route("**/*", _route)
    page.on("popup", _popup)
    return blocked


def _browser_launch_args(safe: bool) -> List[str]:
    """launch 参数：普通模式关沙箱换兼容性；安全模式恢复 Chromium 进程沙箱
    和站点隔离（每个站点独立进程，渲染进程逃逸也碰不到本机文件）。
    v1.22.0：--real-headless on 时（默认）追加拟真参数（lang/分辨率/首次运行横幅），
    与 safe 正交——安全模式不牺牲拟真。"""
    # v1.22.0 压测修复：Chromium 默认往 exe 同目录写 debug.log——被宿主沙箱/
    # 杀软拦截时整个命令报 exit 1（JSON 完整、Python 实际 return 0，环境层误伤）。
    # --enable-logging=none 对 headless shell 无效（实测仍写），改用 --log-file
    # 重定向到系统临时目录（各环境都允许写），exe 目录零写入。
    # v1.22.1 实测补完（B站压测复现概率性沙箱击杀）：
    #   ① --log-file 只管浏览器主进程，重视频页会拉起 GPU 进程注入 NVIDIA 驱动
    #      （nvAppTimestamps + exe 目录 debug.log 双写）——宿主沙箱按路径黑名单
    #      概率性杀整条命令，这就是"成功却 exit 1"的真凶。--disable-gpu 掐掉
    #      NVIDIA 注入路径，视频软解照常播（B站 206 流实测不受影响）；
    #   ② WebGL 软渲染指纹（SwiftShader）由 realheadless 的 getParameter 补丁罩住
    #      （报集成显卡），stealth 不受损；
    #   ③ CHROME_LOG_FILE 环境变量兜底重定向 GPU/子进程日志（--log-file 的盲区）。
    try:
        _log_file = os.path.join(tempfile.gettempdir(), "dwsp_chromium_debug.log")
        args = ["--disable-blink-features=AutomationControlled", f"--log-file={_log_file}",
                "--disable-gpu",
                # 视频硬解（DXVA/NVDEC）会拉起 NVIDIA 驱动写 ProgramData——
                # 严格沙箱宿主中途杀命令（B站长视频实测复现）。禁硬解走 ffmpeg
                # 软解：流照抓（101 响应实测）、CPU 占用换环境兼容性
                "--disable-accelerated-video-decode",
                # GL 走 SwiftShader 软渲染（v1.22.1 抖音复测追加）：--disable-gpu
                # 后合成器仍可能经 ANGLE→D3D11→NVIDIA 驱动加载 nvapi64（nvAppTimestamps
                # 双写，沙箱概率性击杀的唯一残存路径）——钉死软渲染彻底绕开显卡驱动。
                "--use-angle=swiftshader"]
        os.environ.setdefault("CHROME_LOG_FILE", _log_file)
    except Exception:
        args = ["--disable-blink-features=AutomationControlled", "--disable-gpu",
                "--disable-accelerated-video-decode", "--use-angle=swiftshader"]
    if not safe:
        args += ["--disable-features=IsolateOrigins,site-per-process", "--no-sandbox"]
    try:
        from . import realheadless
        args += realheadless.extra_launch_args()
    except Exception:
        pass
    return args


# ---------- 浏览器伪装（--stealth full|basic|off，v1.17.0 默认 full） ----------
# basic（半套）= 项目自带 STEALTH_JS：抹 webdriver + UA/视口/locale 伪装。
#   挡得住必应/百度级风控，挡不住搜狗 antispider（实测无头会话被甩验证页）。
# full（全套，默认）= playwright-stealth 库：再补 plugins/WebGL/UA-Data/
#   sec-ch-ua/hairline 等 20+ 项深层指纹补丁，中等风控站通过率显著提升。
#   库未安装时自动降级 basic 并 stderr 告知（不硬崩）；off = 完全裸奔（对照调试用）。
# v1.22.0：与 --real-headless（默认 on）正交——无头拟真 JS 补丁独立注入，
#   stealth off 时也生效；两个开关可任意组合（off+off = 纯裸奔对照）。


def _apply_stealth(context, mode: str) -> str:
    """对浏览器上下文应用伪装。返回实际生效的档位（可能降级）。
    v1.22.0：开头先注入 --real-headless 的指纹补丁（若开启），再走 stealth 档位。"""
    try:
        from . import realheadless
        if realheadless.enabled():
            context.add_init_script(realheadless.REAL_HEADLESS_JS)
    except Exception:
        pass
    mode = (mode or "full").lower()
    if mode == "off":
        return "off"
    if mode == "basic":
        context.add_init_script(STEALTH_JS)
        return "basic"
    # full：优先 playwright-stealth，未安装自动降级 basic
    try:
        from playwright_stealth import Stealth
        # navigator_languages 用 zh-CN 与项目一致；UA 不覆盖（保留我们自己的 UA 池/
        # --profile 固定 UA，避免伪装库 UA 与 context UA 打架反而成指纹）
        st = Stealth(navigator_languages_override=("zh-CN", "zh"))
        st.apply_stealth_sync(context)
        return "full"
    except ImportError:
        sys.stderr.write("[stealth] playwright-stealth 未安装，full 降级 basic"
                         "（安装：python -m pip install playwright-stealth）\n")
        context.add_init_script(STEALTH_JS)
        return "basic(degraded)"
    except Exception as exc:
        sys.stderr.write(f"[stealth] full 应用失败({exc})，退回 basic\n")
        try:
            context.add_init_script(STEALTH_JS)
        except Exception:
            pass
        return "basic(fallback)"


# ---- Chromium 通道择优（v1.22.1 实测排雷） ----
# chrome-headless-shell（Playwright 默认无头二进制）无视一切日志参数
# （--log-file / CHROME_LOG_FILE / --disable-logging 实测全部无效，WebRTC
# 一拉就写），把 debug.log 写进 exe 同目录；重视频页还会拉起 GPU 进程注入
# NVIDIA 驱动（ProgramData\nvAppTimestamps 双写）。AI 宿主沙箱/杀软按路径
# 黑名单拦截时整条命令被杀——JSON 已完整、Python 实际 return 0，宿主却报
# exit 1（v1.22.0 未根治的"环境层误伤"，v1.22.1 在 B站压测中复现定性）。
# 完整 Chromium 二进制日志走用户目录、尊重重定向，exe 目录零写入 → 根治。
_LAUNCH_CHANNEL = {"v": None}


def _launch_chromium(p, headless: bool, args, **kw):
    """统一 Chromium launch：通道择优 chrome → chromium → shell 兜底（进程内缓存）。
    chrome = 本机真 Chrome（realheadless 拟真首选，指纹最真）；
    chromium = Playwright 完整构建（new headless，不写 exe 目录 debug.log）；
    shell = chrome-headless-shell（老环境兜底，有 exe 目录日志风险）。"""
    order = []
    try:
        from . import realheadless
        _pc = realheadless.preferred_channel()
        if _pc:
            order.append(_pc)
    except Exception:
        pass
    order.append("chromium")
    if _LAUNCH_CHANNEL["v"] in order:
        order = [_LAUNCH_CHANNEL["v"]]
    last_exc = None
    for ch in order:
        try:
            b = p.chromium.launch(channel=ch, headless=headless, args=args,
                                  **_proxy_launch_kw(), **kw)
            _LAUNCH_CHANNEL["v"] = ch
            return b
        except Exception as exc:
            last_exc = exc
    try:
        b = p.chromium.launch(headless=headless, args=args, **_proxy_launch_kw())
        _LAUNCH_CHANNEL["v"] = "shell"
        return b
    except Exception:
        raise last_exc


def _launch_chromium_persistent(p, user_data_dir: str, headless: bool, args, **kw):
    """launch_persistent_context 的通道择优版（同 _launch_chromium）。"""
    order = []
    try:
        from . import realheadless
        _pc = realheadless.preferred_channel()
        if _pc:
            order.append(_pc)
    except Exception:
        pass
    order.append("chromium")
    if _LAUNCH_CHANNEL["v"] in order:
        order = [_LAUNCH_CHANNEL["v"]]
    last_exc = None
    for ch in order:
        try:
            ctx = p.chromium.launch_persistent_context(
                channel=ch, user_data_dir=user_data_dir, headless=headless, args=args,
                **_proxy_launch_kw(), **kw)
            _LAUNCH_CHANNEL["v"] = ch
            return ctx
        except Exception as exc:
            last_exc = exc
    try:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir, headless=headless, args=args,
            **_proxy_launch_kw())
        _LAUNCH_CHANNEL["v"] = "shell"
        return ctx
    except Exception:
        raise last_exc


def _open_page(p, headed: bool, safe: bool, stealth: str = "full",
               profile_dir: Optional[Path] = None, accept_downloads: bool = False,
               ignore_https_errors: bool = False, random_viewport: bool = False,
               cookie_file: str = "", cookies_from_browser: str = "",
               cookie_route_name: str = "") -> tuple:
    """启动样板归一（v1.22.0 批 3）：routes.py 四份 launch 副本合并为单一实现，
    差异全部入参——持久化目录 / 下载信任 / 自签证书容忍 / 随机视口 / 登录态注入。
    返回 (browser, context, page, blocked)；browser=None 表示走的持久化上下文，
    调用方 finally 里 browser.close() 或 context.close()（持久化要 close 才刷盘）。
    中途失败自清理后重抛（对齐原路线 finally 语义）。"""
    common = {
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "extra_http_headers": {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        # 自动信任自签/过期证书：不少下载站用自签 HTTPS，证书不过连页面都打不开
        # 就谈不上抓包（仅浏览器内忽略，不装系统证书）
        **({"ignore_https_errors": True} if ignore_https_errors else {}),
        **({"accept_downloads": True} if accept_downloads else {}),
        **({"service_workers": "block"} if safe else {}),
    }
    browser = None
    context = None
    try:
        if profile_dir:
            # 持久化用户目录（--profile）：登录态跨会话保留；固定 UA 防会话作废
            try:
                context = _launch_chromium_persistent(
                    p,
                    user_data_dir=str(profile_dir),
                    headless=not headed,
                    args=_browser_launch_args(safe),
                    user_agent=USER_AGENTS[0],
                    viewport={"width": 1920, "height": 1080},
                    **common,
                )
            except Exception as exc:
                sys.stderr.write(f"[profile] 持久化上下文打开失败（目录被占用/损坏）: {exc}\n"
                                 "[profile] 回退一次性上下文\n")
                context = None
        if context is None:
            browser = _launch_chromium(p, headless=not headed, args=_browser_launch_args(safe))
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport=({"width": random.randint(1280, 1920),
                           "height": random.randint(800, 1080)} if random_viewport
                          else {"width": 1920, "height": 1080}),
                **common,
            )
        _apply_stealth(context, stealth)
        # 登录态注入：登录墙资源（抖音 note 图集原图/B站视频流等）带 cookie 才放行。
        # cookies.txt 与本机浏览器登录态（--cookies-from-browser，借道 yt-dlp 提取）都支持
        if cookie_file or cookies_from_browser:
            _inject_login_cookies(context, cookie_file, cookies_from_browser, cookie_route_name)
        page = context.pages[0] if (browser is None and context.pages) else context.new_page()
        blocked = _setup_safe_mode(context, page) if safe else {}
        return browser, context, page, blocked
    except Exception:
        # 半开状态自清理（持久化上下文 close 才把 cookie/缓存刷进用户目录）
        try:
            if browser is not None:
                browser.close()
            elif context is not None:
                context.close()
        except Exception:
            pass
        raise


def _save_bytes(data: bytes, output_dir: Path, url: str, content_type: str, index: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(url, content_type, index)
    path = output_dir / filename
    path.write_bytes(data)
    return path


def _wait_for_render(page, min_text: int = 50, max_wait_sec: float = 10.0) -> bool:
    """JS 渲染页自适应等待：SPA 在 domcontentloaded 后内容可能还没挂载（空页面），
    直接收割/提取只能拿到空白。轮询到页面真的渲染出东西为止：
    - 正文 ≥ min_text 字符，或媒体元素 ≥3 个（图库/播放器页正文少）即认为就绪；
    - 每轮 800ms 并滚动触发懒加载；静态页首轮即通过，零额外耗时；
    - 超时返回 False（真空白页），调用方按原逻辑继续（退 chain 兜底/如实报错）。"""
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        try:
            n = page.evaluate(
                "() => document.body ? (document.body.innerText || '').trim().length : 0"
            ) or 0
        except Exception:
            n = 0
        if n >= min_text:
            return True
        try:
            media = page.evaluate(
                "() => document.querySelectorAll('img,video,audio,source').length"
            ) or 0
        except Exception:
            media = 0
        if media >= 3:
            return True
        try:
            page.wait_for_timeout(800)
            human_scroll(page, 1200)
        except Exception:
            pass
    return False

