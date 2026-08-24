"""auto_save 包：由 auto_save_browser.py（4700+ 行单文件）按安全等级分批拆分而来。
第 1 批（v1.21.1 拆分，绝对安全级）：constants / ffmpeg / cookies。
第 2 批（v1.21.1 拆分，绝对安全级）：urlrules（URL/媒体/安全判定纯函数）。
第 3 批（v1.22.0 拆分，比较安全级）：browser_base（浏览器基建 4 函数）；
  同批新增两个可独立使用的能力模块（并联组合，均可单独 import）：
  - humanize：拟人输入（贝塞尔轨迹/微偏移按压/正态键间隔/分步滚动）
  - realheadless：无头拟真（静态指纹补丁 + 真 Chrome 探测）
结构优化批 1（v1.22.0）：routing（意图检测/--method 选路/结果挑选/平台搜索页，
  自门面搬迁零逻辑改动）。
兼容性契约：
  - `auto_save_browser.py` 仍是唯一命令行入口与唯一被外部 import 的模块；
  - 本包 __init__ re-export 全部拆出的公开名，外部 import 路径零变化；
  - 搬迁类拆分零逻辑改动；新增模块带开关，off 时逐字节回退旧行为；每批拆完全量回归。"""
from .constants import *  # noqa: F401,F403
from .ffmpeg import *  # noqa: F401,F403
from .cookies import *  # noqa: F401,F403
from .urlrules import *  # noqa: F401,F403
from .browser_base import *  # noqa: F401,F403
from .humanize import (  # noqa: F401
    set_humanize, humanize_enabled,
    human_move, human_click, human_type, human_scroll, human_pause,
)
from . import realheadless  # noqa: F401
from .shots import *  # noqa: F401,F403
from .vision import *  # noqa: F401,F403
from .routes import *  # noqa: F401,F403
from .routing import *  # noqa: F401,F403

