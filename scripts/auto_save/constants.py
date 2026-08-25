"""常量区：媒体扩展名/域名表/安全模式名单/UA 池/注入 JS。
全部为纯数据（零逻辑），被各路线只读引用——拆分绝对安全级。"""

from pathlib import Path

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en']
});
"""

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".m4s", ".mkv", ".avi", ".flv", ".ts"}
AUDIO_EXTS = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".wma")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
MEDIA_EXTENSIONS = VIDEO_EXTS | set(AUDIO_EXTS) | set(IMAGE_EXTS)

CONTENT_TYPE_EXT = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
    "video/x-matroska": ".mkv",
    "video/mp2t": ".ts",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/ogg": ".ogg",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

VIDEO_LIKE_HOSTS = (
    "douyin.com",
    "iesdouyin.com",
    "tiktok.com",
    "bilibili.com",
    "b23.tv",
    "youtube.com",
    "youtu.be",
    "weibo.com",
    "kuaishou.com",
    "ixigua.com",
    "xiaohongshu.com",
    "xhslink.com",
)

# 图片电路：只有这些图片站/图片直链才值得导航过去收割
IMAGE_LIKE_HOSTS = (
    "image.baidu.com",
    "pic.sogou.com",
    "image.so.com",
    "tuchong.com",
    "huaban.com",
    "pixabay.com",
    "unsplash.com",
    "pexels.com",
)

# 音频电路：音乐平台/播客站
AUDIO_LIKE_HOSTS = (
    "music.163.com",
    "y.qq.com",
    "kuwo.cn",
    "kugou.com",
    "ximalaya.com",
    "lizhi.fm",
    "qingting.fm",
    "soundcloud.com",
)

# 文件电路：压缩包/文档/表格/演示/电子书/安装包/文本等一切非视频照片音频的东西
FILE_EXTS = (
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".md", ".epub", ".mobi",
    ".apk", ".msi", ".exe", ".iso", ".dmg",
)

# 持久化浏览器用户目录（--profile）：登录一次、cookie/缓存跨会话保留，等同真实浏览器的
# 用户配置。注意：目录里存的是登录 cookie，绝不能进 git（.gitignore 已排除）。
PROFILE_DIR = Path(__file__).resolve().parent.parent.parent / "downloads" / "browser_profile"

SEARCH_REDIRECT_HOSTS = (
    "so.com",
    "sogou.com",
    "baidu.com",
    "sm.cn",
    "bing.com",
    "cn.bing.com",
    "quark.com",
)

# 分享短链域名（v1.22.1）：跳转后才见真实 URL（/note/ 图文帖等），
# 调度器先跟一次重定向再判类型，否则 note 预判（子串检查）永远不触发。
SHARE_SHORTLINK_HOSTS = (
    "v.douyin.com",
    "xhslink.com",
    "www.iesdouyin.com",
)

# 登录墙站点（v1.22.1）：无 cookie 时 direct（拿到 HTML 壳页）/ytdlp（Fresh
# cookies needed）必败——chain 不再白跑这两步，直上 browser 硬抓。
LOGIN_WALL_HOSTS = (
    "douyin.com",
    "iesdouyin.com",
)

# ---------- 垃圾资源过滤 ----------
# 抓包会混入大量页面资源：UI 图、推荐位封面、gif、bin 残片。
# 默认直接跳过不落盘；--save-junk 时存到 junk/ 子目录。

JUNK_EXTENSIONS = {".gif", ".bin", ".svg"}
JUNK_URL_HINTS = (
    "/static/", "/assets/", "/asset/", "/sprite", "/icon", "/emoji",
    "/logo", "/avatar", "/widget", "/common/", "/public/",
    # 压测补充（快手/小红书登录墙页实测漏网）：横幅/登录图/广告位/精灵图/
    # 图标目录（webframe_icon 类）——harvest 关尺寸判定时仍需拦住这些 UI 资产
    "banner", "login", "/ad/", "_icon", "icon.", "sprite", "favicon",
    # 抖音搜索页压测补充：引导图/公告图/激励弹窗图
    "guide", "notice", "incentive",
    # 快手滑图帖压测补充（v1.22.1）：评论区头像（uhead 路径）+ 表情贴图
    # （emotion webp）混进 harvest 产物 25 项垃圾、正文图集全漏——装饰件拦截
    "uhead", "emotion", "emoticon",
    # 快手压测补充（v1.22.1）：风控弹滑块验证码时 captcha.zt.kuaishou.com 的
    # cutPic/bgPic 拼图混进产物（22KB+48KB 两张验证码底图被判 partial）——
    # captcha 端点绝无用户内容
    "captcha",
)

# 站点 UI/推广物料域（v1.22.1 抖音压测排雷）：这些域只放页面皮肤/引导图/
# 客户端安装物料，绝无用户内容——但体积不小（douyin_pc_client.mp4 实测
# 11MB 推广视频、pad_guid/mobile_home 引导图 37 张全混进产物）。
STATIC_ASSET_HOSTS = (
    "douyinstatic.com",   # 抖音站点 UI：pad_guid/mobile_home 引导图、皮肤、二维码
    "bytednsdoc.com",     # 字节静态文档：PC 客户端安装视频/下载物料
    "p-pc-weboff.byteimg.com",  # 抖音 PC web 官方物料：二维码/弹窗背景/扩展壁纸
    # （实测 49 张混进产物，含 douyin-web-extension-wallpapers 壁纸 13MB）
    "fe-platform.xhscdn.com",  # 小红书前端平台资产（v1.22.1 压测）：登录墙弹窗
    # 底图/二维码/平台插画（实测匿名访问 explore 抓到的全是这些装饰件）
)

# ---- 安全模式（--safe）：访问可疑站点时保护本机 ----
# 可执行/安装包/脚本宏扩展名：导航命中即拦（页面自身的 .js 资源不拦，拦了网站全坏；
# 恶意脚本靠域名黑名单 + 落盘白名单 + Chromium 进程沙箱兜底）。
DANGEROUS_EXTS = {
    ".exe", ".msi", ".msix", ".msp", ".scr", ".bat", ".cmd", ".com", ".pif",
    ".ps1", ".psm1", ".vbs", ".vbe", ".jse", ".wsf", ".wsh", ".hta",
    ".jar", ".cpl", ".reg", ".lnk", ".app", ".dmg", ".pkg", ".deb", ".rpm",
    ".apk", ".appimage", ".sh", ".bash",
}
# 已知挖矿/矿池/恶意服务域名（含子域名匹配）
MINING_DOMAINS = {
    "coinhive.com", "authedmine.com", "cryptoloot.com", "crypto-loot.com",
    "jsecoin.com", "minero.cc", "minergate.com", "deepminer.site",
    "webminepool.com", "coinimp.com", "nanopool.org", "supportxmr.com",
    "c3pool.com", "moneroocean.stream", "minexmr.com", "xmrpool.eu",
    "nicehash.com", "2miners.com", "f2pool.com", "antpool.com",
}
# Stratum 挖矿协议常用端口（WebSocket/WebTransport 命中即拦）
STRATUM_PORTS = (":3333", ":4444", ":5555", ":7777", ":8888")
# 安全模式落盘扩展名白名单（媒体 + 文本产物），其余一律不落盘
SAFE_ALLOWED_EXTS = MEDIA_EXTENSIONS | {".txt", ".json"}
# 安全模式单文件大小上限（防磁盘填充）
SAFE_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024


__all__ = [
    'STEALTH_JS',
    'USER_AGENTS',
    'VIDEO_EXTS',
    'AUDIO_EXTS',
    'IMAGE_EXTS',
    'MEDIA_EXTENSIONS',
    'CONTENT_TYPE_EXT',
    'VIDEO_LIKE_HOSTS',
    'IMAGE_LIKE_HOSTS',
    'AUDIO_LIKE_HOSTS',
    'FILE_EXTS',
    'PROFILE_DIR',
    'SEARCH_REDIRECT_HOSTS',
    'SHARE_SHORTLINK_HOSTS',
    'LOGIN_WALL_HOSTS',
    'JUNK_EXTENSIONS',
    'JUNK_URL_HINTS',
    'STATIC_ASSET_HOSTS',
    'DANGEROUS_EXTS',
    'MINING_DOMAINS',
    'STRATUM_PORTS',
    'SAFE_ALLOWED_EXTS',
    'SAFE_MAX_FILE_BYTES',
]
