"""searchkit 包：由 search.py（961 行单文件）按职责拆分而来（v1.22.0 批 C）。
http=请求件 / normalize=归一去重 / engines=引擎注册 / adfilter=广告过滤 / dispatch=调度。
批 D 起 browser=Playwright 浏览器引擎层（独立入口 search_browser.py）。
兼容契约：search.py/search_browser.py 仍是 CLI 入口与被 import 的门面；本包 re-export 全部旧名。
注意：此处不 import .browser——轻量版（search.py）启动不应拉起 playwright/auto_save 链。"""
from .http import *  # noqa: F401,F403
from .http import set_ca_cert  # noqa: F401
from .normalize import *  # noqa: F401,F403
from .engines import *  # noqa: F401,F403
from .adfilter import *  # noqa: F401,F403
from .dispatch import *  # noqa: F401,F403
