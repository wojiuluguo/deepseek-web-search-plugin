"""无头拟真（--real-headless on|off，默认 on）：让无头 Chromium 无限接近真实桌面 Chrome。

先破一个误解：无头 ≠ 假浏览器。无头 Chromium 与有头是同一份内核
（Blink/V8/网络栈），TLS 指纹、请求头、HTTP 行为全是真的。能被识破的
缺口只剩三类，本模块逐个补：

  1. JS 静态指纹缺口（本模块主战场）：hardwareConcurrency / deviceMemory /
     permissions.query / WebGL vendor / chrome.app / screen.colorDepth 在
     无头下的默认值异常，是风控的经典探针 → REAL_HEADLESS_JS 逐项补成
     主流桌面值。补丁保持克制：只补"已知会露馅的异常值"，不过度伪造
     （伪造过多反而制造新指纹）。
  2. 行为缺口：轨迹/节奏/停顿 → 交给 humanize.py（本模块不管行为）。
  3. 二进制差异：无头 Chromium 的 sec-ch-ua / 版本特性与本机真 Chrome 有
     微差 → preferred_channel() 探测本机 Google Chrome，launch(channel="chrome")
     直接用真浏览器二进制（指纹 100% 真）。本版先提供接口，launch 调用点
     接线在下一批（避免本批改动面过大）。

与 --stealth 正交：stealth 管通用反检测（webdriver/plugins/UA），
本模块专补无头特有的缺口，两个开关可任意组合。"""
import os
from typing import List, Optional

__all__ = ["set_enabled", "enabled", "preferred_channel", "extra_launch_args", "REAL_HEADLESS_JS"]

# ---- 总开关（main() 里按 --real-headless 设置）----
_ENABLED = True


def set_enabled(v: bool) -> None:
    global _ENABLED
    _ENABLED = bool(v)


def enabled() -> bool:
    return _ENABLED


# 本机 Google Chrome 常见安装位置（Windows；未命中返回 None 用默认 Chromium）
_CHROME_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def preferred_channel() -> Optional[str]:
    """本机装了 Google Chrome → "chrome"（launch 用真 Chrome 二进制），
    否则 None（用 Playwright 自带 Chromium）。--real-headless off 时恒 None。"""
    if not _ENABLED or os.name != "nt":
        return None
    return "chrome" if any(os.path.isfile(p) for p in _CHROME_PATHS) else None


def extra_launch_args() -> List[str]:
    """拟真补充 launch 参数（加在 _browser_launch_args 基础参数之上）。"""
    if not _ENABLED:
        return []
    return [
        "--lang=zh-CN",               # 与伪装的 zh-CN 语言链一致（无头默认 en 是探针）
        "--window-size=1920,1080",    # 主流桌面分辨率（有头模式决定窗口，无头兜底）
        "--disable-infobars",         # 不弹"正在受自动化软件控制"横幅
        "--no-first-run",
        "--no-default-browser-check",
    ]


# 注入位置：_apply_stealth() 开头 add_init_script——在任何页面脚本之前生效。
# 补丁顺序说明：与 playwright-stealth 共存不冲突（双方都 defineProperty 覆盖式注入，
# 后注入者生效；本 JS 只补 stealth 库未覆盖/无头特有的项）。
REAL_HEADLESS_JS = """
// ---- 无头拟真补丁（--real-headless，与 --stealth 正交）----
(() => {
  try {
    // 1) 硬件合理性：无头默认 hardwareConcurrency/deviceMemory 常报异常值
    //    → 补成主流桌面配置（8 核 / 8GB；与桌面 UA 池一致，不产生矛盾信号）
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
    // 2) permissions 探针：无头 Notification.permission 与 permissions.query
    //    结果不一致是经典检测点 → 让 query 跟随真实 permission 状态
    if (navigator.permissions && navigator.permissions.query) {
      const _q = navigator.permissions.query.bind(navigator.permissions);
      navigator.permissions.query = (params) =>
        params && params.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission })
          : _q(params);
    }
    // 3) WebGL 渲染器：无头常报 SwiftShader / 软渲染 → 报主流集成显卡
    for (const proto of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
      if (!proto) continue;
      const _gp = proto.prototype.getParameter;
      proto.prototype.getParameter = function (p) {
        if (p === 37445) return 'Google Inc. (Intel)';
        if (p === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E9B), Direct3D11 vs_5_0 ps_5_0, D3D11)';
        return _gp.apply(this, arguments);
      };
    }
    // 4) chrome.app：真实 Chrome 有、裸 Chromium/部分无头缺 → 补齐骨架
    window.chrome = window.chrome || {};
    if (!window.chrome.app) {
      window.chrome.app = {
        isInstalled: false,
        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
      };
    }
    // 5) 屏幕探针：无头偶发 colorDepth=0 → 主流桌面 24
    try { Object.defineProperty(screen, 'colorDepth', { get: () => 24 }); } catch (e) {}
    // 刻意不做的：伪造 codecs/字体清单——现代无头已正常，过度伪造反而制造新指纹
  } catch (e) { /* 补丁失败不拖页面 */ }
})();
"""
