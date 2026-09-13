"""意图路由层（v1.22.0 结构优化批 1 自 auto_save_browser.py 搬迁，零逻辑改动）：
query/URL 媒体意图检测、--method 自动选路、搜索结果目标挑选、平台搜索页构造。
_search_first_media_url 惰性 import searchkit.browser（原经 search_browser 门面，
现直连搜索包，与批 D 分层修复同向）；被调用才拉起，--help 等场景零开销。"""
import re
import sys
import urllib.parse
from typing import Dict, List, Optional

from .browser_base import get_proxy
from .constants import (
    AUDIO_EXTS, FILE_EXTS, IMAGE_EXTS,
    AUDIO_LIKE_HOSTS, IMAGE_LIKE_HOSTS, SEARCH_REDIRECT_HOSTS, VIDEO_LIKE_HOSTS,
)
from .urlrules import _decode_redirect_url, _host_matches

__all__ = [
    "_is_bare_homepage", "_platform_search_url", "_pick_video_url",
    "_detect_media_intent", "_detect_url_media_type", "_route_method",
    "_pick_media_url", "_baidu_image_search_url", "_search_first_media_url",
]


def _is_bare_homepage(u: str) -> bool:
    """平台裸首页（路径只有 / 或空，或指向首页文件）：是官网入口，不是具体视频页。
    压测发现：搜"抖音 猫 视频"时引擎返回 douyin.com 首页，被当视频链接挑中，
    开出来的只有首页宣传片——必须跳过，让兜底逻辑去平台搜索页。
    v1.23.2 压测二次排雷（B站）：t.bilibili.com/index.html 这类"伪首页"
    （动态子域 + 首页文件名）路径非空，旧判定漏网——平台轮 host 匹配就选中，
    chain 全链在动态首页上收割头像缩略图。补常见首页文件名判定（平台无关）：
    真视频页路径（/video/BVxxx、/video/数字）不含这些文件名，误杀风险≈0。"""
    try:
        p = urllib.parse.urlparse(u)
        path = p.path.strip("/").lower()
        if path == "":
            return True
        # 伪首页：站点根入口的常见文件名（不带更深的目录）
        return "/" not in path and path in (
            "index.html", "index.htm", "index.shtml",
            "default.html", "default.htm", "home.html", "home.htm",
        )
    except Exception:
        return False


def _platform_search_url(query: str) -> str:
    """query 提到平台但搜索结果里没有具体视频页时，直奔该平台自己的搜索页
    （浏览器开搜索页收割自动播放的结果视频，比开首页强得多）。"""
    q = (query or "").lower()
    kw = urllib.parse.quote(query)
    if "抖音" in q:
        return f"https://www.douyin.com/search/{kw}"
    if "tiktok" in q:
        return f"https://www.tiktok.com/search?q={kw}"
    if any(w in q for w in ("b站", "哔哩", "bilibili")):
        return f"https://search.bilibili.com/all?keyword={kw}"
    if "快手" in q:
        return f"https://www.kuaishou.com/search/video?searchKey={kw}"
    if any(w in q for w in ("小红书", "xhs")):
        return f"https://www.xiaohongshu.com/search_result?keyword={kw}"
    if "微博" in q:
        return f"https://s.weibo.com/weibo?q={kw}"
    if "西瓜" in q:
        return f"https://www.ixigua.com/search/{kw}/"
    if any(w in q for w in ("youtube", "油管")):
        return f"https://www.youtube.com/results?search_query={kw}"
    return ""


_ITEM_PATH_RE = re.compile(
    r"(?:/video/|/note/|/short-video/|/watch|/clip/|/status/|bv[\w]{6,}|/av\d+"
    r"|/song|songdetail|play_detail|/sound|/album|/playlist|/program)", re.I)

# 登录/注册页是"永非内容页"的平台无关信号——任何电路都不该把它们挑成目标
_NEVER_ITEM_PATH_RE = re.compile(r"(?:^|/)(?:login|register|signup|signin)(?:[./?#]|$)", re.I)


def _looks_like_item_page(u: str) -> bool:
    """内容条目页判定（平台无关弱启发，v1.23.2 压测排雷）：
    挑链路只该挑"能开出媒体的条目页"，站点栏目首页（/read/home、/index.html、
    动态页）不该抢位——旧逻辑只看 host 匹配，B站专栏首页/动态首页轮番抢中，
    chain 全链在错误页面上收割垃圾。判据：路径含条目关键词（/video/、BV号、
    watch 等）或末段是 ID 形态（≥6 位字母数字 / ≥4 位连续数字，youtu.be 短 ID
    靠前者、抖音/西瓜纯数字 ID 靠后者）。防误杀：真视频 URL 全部有 ID 形态。
    v1.23.3 补音频 token（music.163.com/song?id= 这类 query-id 页）+ query
    id=\d 信号 + 登录/注册页一票否决（v1.23.3 压测排雷：音频电路选中
    music.163.com/login——登录页 host 匹配音乐站域，旧音频轮无门）。"""
    try:
        p = urllib.parse.urlparse(u)
        path = p.path.lower()
        if _NEVER_ITEM_PATH_RE.search(path):
            return False
        if _ITEM_PATH_RE.search(path):
            return True
        # query 带数字 id（music.163.com/song?id=186016 式条目页）
        if re.search(r"(?:^|[?&])id=\d+", p.query, re.I):
            return True
        last = path.rstrip("/").rsplit("/", 1)[-1]
        if not last:
            return False
        if re.fullmatch(r"[a-z0-9_-]{6,}", last) and re.search(r"\d", last):
            return True  # 字母数字混合长 ID（youtu.be/dQw4w9WgXcQ 式）
        return bool(re.search(r"\d{4,}", last))  # 末段长数字 ID（抖音/西瓜式）
    except Exception:
        return False


def _pick_video_url(results: List[Dict[str, str]], query: str = "") -> str:
    """挑搜索结果里的视频链接。query 含平台词（抖音/B站等）时该平台结果优先；
    平台结果不存在时如实回退第一个视频类链接（不编造）。"""
    # query → 首选域名偏好（用户说“去抖音搜”就必须先挑抖音）
    PLATFORM_HINTS = {
        "抖音": ("douyin.com", "iesdouyin.com"),
        "tiktok": ("tiktok.com",),
        "b站": ("bilibili.com", "b23.tv"),
        "哔哩": ("bilibili.com", "b23.tv"),
        "bilibili": ("bilibili.com", "b23.tv"),
        "快手": ("kuaishou.com",),
        "西瓜": ("ixigua.com",),
        "小红书": ("xiaohongshu.com", "xhslink.com"),
        "微博": ("weibo.com",),
        "youtube": ("youtube.com", "youtu.be"),
        "油管": ("youtube.com", "youtu.be"),
    }
    preferred: tuple = ()
    q = (query or "").lower()
    for word, hosts in PLATFORM_HINTS.items():
        if word in q:
            preferred = hosts
            break

    def _host_of(u: str) -> str:
        return urllib.parse.urlparse(u).netloc.lower()

    # 第一轮：只挑首选平台的视频链接（跳过裸首页/伪首页/栏目首页）
    if preferred:
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            for cand in (_decode_redirect_url(url), url):
                if cand and not _is_bare_homepage(cand) \
                        and _looks_like_item_page(cand) \
                        and any(_host_matches(_host_of(cand), h) for h in preferred):
                    return cand
    # 第二轮（无偏好或首选平台无结果）：第一个视频类链接（跳过裸首页/栏目首页）
    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        # Try the real URL hidden in redirect links.
        decoded = _decode_redirect_url(url)
        for cand in (decoded, url):
            if not cand or _is_bare_homepage(cand) or not _looks_like_item_page(cand):
                continue
            host = _host_of(cand)
            if any(_host_matches(host, vh) for vh in VIDEO_LIKE_HOSTS):
                return cand
        # Search-engine redirect links are acceptable too: the browser can follow them.
        host = _host_of(url)
        if any(_host_matches(host, rh) for rh in SEARCH_REDIRECT_HOSTS):
            return url
    return ""


def _detect_media_intent(query: str, media_types: str = "") -> str:
    """检测这次搜索要的媒体类型（导航决策，不是落盘过滤）。
    优先级：--media-type 单选 > query 关键词推断 > 默认 video。
    检测结果决定走哪条电路：图片找图片页、音频找音乐站，不再全挤到视频电路。"""
    types = [t.strip() for t in re.split(r"[,，]", (media_types or "").strip()) if t.strip()]
    if len(types) == 1 and types[0] in ("video", "audio", "image", "file", "text"):
        return types[0]
    q = (query or "").lower()
    if any(w in q for w in ("图片", "照片", "壁纸", "头像", "表情包", "原图", "插画", "写真")):
        return "image"
    if any(w in q for w in ("音乐", "歌曲", "音频", "铃声", "伴奏", "纯音乐", "播客", "广播剧")):
        return "audio"
    if any(w in q for w in ("文件", "压缩包", "文档", "课件", "报告", "电子书", "安装包",
                            "pdf", "zip", "rar", "7z", "docx", "xlsx", "pptx", "epub", "tar.gz")):
        return "file"
    if any(w in q for w in ("小说", "文章", "正文", "全文", "章节", "原文阅读")):
        return "text"
    return "video"


def _detect_url_media_type(url: str, media_types: str = "") -> str:
    """按 URL 特征识别目标媒体类型（--url 模式的专用电路选择）。
    优先级：搜索列表页的显式 --media-type 单选 > 视频站域名 > --media-type 单选 >
    URL 扩展名（图/音/文件）> 图/音站域名 > 默认 video。
    视频站一票否决：抖音/B站等"视频流+音频流分离"的站点，页面里的音频就是视频的
    伴音轨，必须整体走视频路（yt-dlp 下双流合并 / cache 分段合并），绝不能因为
    --media-type audio 被导去音频专用线只抓半条伴音流。
    例外：搜索/列表页是九宫格混合内容，显式单选代表用户意图，优先于否决。"""
    u = (url or "").strip()
    parsed = urllib.parse.urlparse(u)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    types = [t.strip() for t in re.split(r"[,，]", (media_types or "").strip()) if t.strip()]
    explicit = types[0] if len(types) == 1 and types[0] in ("video", "audio", "image", "file", "text") else ""
    # 搜索/列表页（九宫格混合内容，非具体视频详情页）：用户显式 --media-type 单选
    # 最懂意图，优先于视频站否决（压测：小红书 search_result 要图被否决去视频链，
    # 只收到 svg 精灵；harvest 才能收到封面图）
    if explicit and "search" in path:
        return explicit
    # 第一优先：视频站域名。无论 --media-type 怎么单选，视频页永远走视频路。
    if any(_host_matches(host, vh) for vh in VIDEO_LIKE_HOSTS):
        return "video"
    if explicit:
        return explicit
    if path.endswith(IMAGE_EXTS):
        return "image"
    if path.endswith(AUDIO_EXTS):
        return "audio"
    if path.endswith(FILE_EXTS):
        return "file"
    if any(_host_matches(host, h) for h in IMAGE_LIKE_HOSTS):
        return "image"
    if any(_host_matches(host, h) for h in AUDIO_LIKE_HOSTS):
        return "audio"
    return "video"


def _route_method(url: str, media_types: str, explicit_method: Optional[str]) -> str:
    """--url 模式方法选路：显式 --method 原样尊重；未指定时按媒体类型自动选。
    照片/音频页面 → harvest 专用线；文件（直链或页面）→ files 专用线；
    文本（--media-type text）→ text 专用线；视频/媒体直链 → chain（原路不变）。"""
    if explicit_method:
        return explicit_method
    media_type = _detect_url_media_type(url, media_types)
    path = urllib.parse.urlparse((url or "").strip()).path.lower()
    direct_link = path.endswith(IMAGE_EXTS + AUDIO_EXTS + (".mp4", ".m4s", ".webm", ".mov", ".mkv", ".flv", ".ts"))
    if media_type == "file":
        return "files"
    if media_type == "text":
        return "text"
    if media_type in ("image", "audio") and not direct_link:
        return "harvest"
    return "chain"


def _pick_media_url(results: List[Dict[str, str]], query: str, media_type: str = "video") -> str:
    """按媒体类型挑目标页面。
    video → 原视频逻辑原样委托 _pick_video_url（视频电路不动）；
    image/audio → 只挑对应类型结果（图片站/音乐站/直链扩展名），
    明确跳过视频站和搜索引擎跳转壳，防止图片/音频需求误开视频页。
    file → 只挑文件直链（zip/pdf/docx 等扩展名结尾）。"""
    if media_type == "video":
        return _pick_video_url(results, query)

    if media_type == "file":
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            for cand in (_decode_redirect_url(url), url):
                if cand and urllib.parse.urlparse(cand).path.lower().endswith(FILE_EXTS):
                    return cand
        return ""

    if media_type == "text":
        # 文本：挑文章页——跳过视频站/图片站/音乐站；优先非跳转壳（解不出真实地址的壳链接只当兜底）
        def _host_of(u):
            return urllib.parse.urlparse(u).netloc.lower()

        fallback = ""
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            cand = _decode_redirect_url(url) or url
            host = _host_of(cand)
            # 登录/注册页永非内容页（平台无关）
            if _NEVER_ITEM_PATH_RE.search(urllib.parse.urlparse(cand).path.lower()):
                continue
            if any(_host_matches(host, vh) for vh in VIDEO_LIKE_HOSTS):
                continue
            if any(_host_matches(host, h) for h in IMAGE_LIKE_HOSTS) or any(_host_matches(host, h) for h in AUDIO_LIKE_HOSTS):
                continue
            # 文件直链（zip/pdf 等）是 file 电路的目标，文本电路跳过
            if urllib.parse.urlparse(cand).path.lower().endswith(FILE_EXTS):
                continue
            if not fallback:
                fallback = cand
            if cand == url and any(_host_matches(host, rh) for rh in SEARCH_REDIRECT_HOSTS):
                continue
            return cand
        return fallback

    hosts = IMAGE_LIKE_HOSTS if media_type == "image" else AUDIO_LIKE_HOSTS
    exts = IMAGE_EXTS if media_type == "image" else AUDIO_EXTS

    def _host_of(u: str) -> str:
        return urllib.parse.urlparse(u).netloc.lower()

    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        for cand in (_decode_redirect_url(url), url):
            if not cand:
                continue
            # v1.23.3 压测排雷：host 分支加条目页门——music.163.com/login 曾被
            # 当"音频目标"选中（登录页 host 匹配音乐站域）；直链扩展名分支不受门限
            if any(_host_matches(_host_of(cand), h) for h in hosts) \
                    and not _is_bare_homepage(cand) and _looks_like_item_page(cand):
                return cand
            if urllib.parse.urlparse(cand).path.lower().endswith(exts):
                return cand
    return ""


def _baidu_image_search_url(query: str) -> str:
    """构造百度图片搜索页 URL。图片电路的外援：没有通用的图片搜索下载库，
    就像视频借力 yt-dlp 一样，图片借力百度图片站直接导航收割。"""
    return "https://image.baidu.com/search/index?tn=baiduimage&word=" + urllib.parse.quote(query)


def _search_first_media_url(
    query: str, max_results: int, media_type: str = "video", safe: bool = False
) -> str:
    """搜索并按媒体类型挑目标。
    video：原两级引擎逻辑（国内优先→通用兜底），行为不变；
    image：结果里没图片类链接时直奔百度图片搜索页（不再误开视频页）；
    audio：没挑到就换关键词(+mp3)重搜一次，再没有如实返回空。"""
    # 惰性 import（v1.22.0 结构优化批 1：直连 searchkit.browser，不经 search_browser
    # 门面——与模式审计 P14 分层修复同向；被调用才拉起，--help 场景零开销）。
    # scripts/ 目录已在 sys.path（本包 auto_save 即位于其下）。
    from searchkit.browser import run_search

    # 国内优先：与 search_browser.DOMESTIC_FIRST 同口径（搜狗/360/百度/必应，不含 DDG 防超时）。
    domestic = ["sogou", "so360", "baidu", "bing"]

    if media_type == "video":
        data = run_search(query, max_results, domestic, proxy=get_proxy(), safe=safe)
        url = _pick_media_url(data.get("results", []), query, "video")
        if not url:
            # 国内引擎没找到时再退回通用引擎组合。
            from searchkit.browser import _resolve_engines
            data = run_search(query, max_results, _resolve_engines("", "general"),
                              proxy=get_proxy(), safe=safe)
            url = _pick_media_url(data.get("results", []), query, "video")
        if url:
            # 引擎索引的平台搜索页只带残缺关键词（如只"抖音"二字，压测实测），
            # 换成全关键词自建搜索页——搜出来的才是目标内容
            plat = _platform_search_url(query)
            if plat:
                p_host = urllib.parse.urlparse(plat).netloc.lower().removeprefix("www.")
                u_parsed = urllib.parse.urlparse(url)
                u_host = u_parsed.netloc.lower().removeprefix("www.")
                if "search" in u_parsed.path.lower() and (u_host == p_host or u_host.endswith("." + p_host)):
                    url = plat
            return url
        # 两轮都没有具体视频页：query 提到平台时直奔平台搜索页（开首页只有宣传片，
        # 开搜索页才有自动播放的目标内容可收割）。
        return _platform_search_url(query)

    if media_type == "image":
        data = run_search(query, max_results, domestic, proxy=get_proxy(), safe=safe)
        url = _pick_media_url(data.get("results", []), query, "image")
        if url:
            return url
        # 搜索结果里没有图片类链接：直接导航百度图片搜索页再收割
        return _baidu_image_search_url(query)

    if media_type == "file":
        # 文件电路：先原词挑文件直链，挑不到换"关键词 下载"重搜一次
        for q in (query, f"{query} 下载"):
            data = run_search(q, max_results, domestic, proxy=get_proxy(), safe=safe)
            url = _pick_media_url(data.get("results", []), query, "file")
            if url:
                return url
        return ""

    if media_type == "text":
        # 文本电路：挑第一个非视频站的结果（文章页优先，跳过视频站和跳转壳）
        data = run_search(query, max_results, domestic, proxy=get_proxy(), safe=safe)
        url = _pick_media_url(data.get("results", []), query, "text")
        return url

    # audio：先按原词挑，挑不到换 "关键词 mp3" 重搜（只认音乐站/音频直链）
    for q in (query, f"{query} mp3"):
        data = run_search(q, max_results, domestic, safe=safe)
        url = _pick_media_url(data.get("results", []), query, "audio")
        if url:
            return url
    return ""
