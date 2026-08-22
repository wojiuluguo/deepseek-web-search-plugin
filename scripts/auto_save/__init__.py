"""auto_save 包：由 auto_save_browser.py（4700+ 行单文件）按安全等级分批拆分而来。
第 1 批（v1.21.1 拆分，绝对安全级）：constants / ffmpeg / cookies。
第 2 批（v1.21.1 拆分，绝对安全级）：urlrules（URL/媒体/安全判定纯函数）。
兼容性契约：
  - `auto_save_browser.py` 仍是唯一命令行入口与唯一被外部 import 的模块；
  - 本包 __init__ re-export 全部拆出的公开名，外部 import 路径零变化；
  - 拆分纯搬迁，零逻辑改动；每批拆完全量回归。"""
from .constants import *  # noqa: F401,F403
from .ffmpeg import *  # noqa: F401,F403
from .cookies import *  # noqa: F401,F403
from .urlrules import *  # noqa: F401,F403
