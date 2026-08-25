"""URL/媒体/安全判定纯函数：输入字符串或响应头 → 返回判定结果。
不碰浏览器、不碰全局可变状态、不写文件——拆分绝对安全级（v1.21.1 第 2 批）。"""

import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Optional

from .constants import (
    SEARCH_REDIRECT_HOSTS, VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS, MEDIA_EXTENSIONS,
    CONTENT_TYPE_EXT, JUNK_EXTENSIONS, JUNK_URL_HINTS, STATIC_ASSET_HOSTS,
    MINING_DOMAINS, STRATUM_PORTS, DANGEROUS_EXTS, SAFE_ALLOWED_EXTS, SAFE_MAX_FILE_BYTES,
    FILE_EXTS,
)

# APP 商店域名：抓到这些链接说明是"引流装APP"陷阱——按钮抓到的"下载链接"
# 其实是下载那个 APP 本身（跳应用商店），不是用户要的文件。绝不存为成果。
APP_STORE_HOSTS = (
    "apps.apple.com", "appstore.com", "itunes.apple.com",
    "play.google.com", "market.android.com",
    "app.mi.com", "appgallery.huawei.com", "appgallery.cloud.huawei.com",
    "myapp.com", "android.myapp.com",
    "app.baidu.com", "shouji.baidu.com",
    "zhushou.360.cn", "app.360.cn",
    "wandoujia.com", "ppzhushou.com", "25pp.com",
    "appgallery", "samsungapps.com",
    "appgallery.market.xiaomi.com",
)

SHELL_BODY_TEXT_LIMIT = 600  # 正文短于这个数且带跳转标记 → 判为落地页壳页

# ---------- 点击式下载兜底（--click-download，默认关闭）----------
# 场景：分享页"点击下载"按钮跳转 APP/JS 处理，页面里没有文件直链。
# 策略（按序）：UA 伪装重试 → 找下载按钮点击 + 网络层嗅探真文件响应
# （Content-Type 是文件本体/URL 以文件扩展名结尾）→ expect_download 兜底
# → scheme 参数解码。抓到真 URL 后 HTTP 流式直下。

CLICK_DOWNLOAD_FILE_TYPES = (
    "application/vnd.android.package-archive",  # APK
    "application/zip", "application/x-zip-compressed",
    "application/x-rar-compressed", "application/vnd.rar",
    "application/x-7z-compressed",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",  # 通用二进制（很多站用它发 APK/zip）
)

DOWNLOAD_BUTTON_TEXTS = ("下载", "立即下载", "点击下载", "免费下载", "安装",
                         "download", "get apk", "get the app", "install")


def _decode_redirect_url(url: str) -> str:
    """Try to extract the real target URL from search-engine redirect links."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if not any(_host_matches(host, rh) for rh in SEARCH_REDIRECT_HOSTS) and "link" not in parsed.path.lower():
            return ""
        query = urllib.parse.parse_qs(parsed.query)
        for key in ("url", "target", "m", "q", "link", "redirect", "u", "to"):
            vals = query.get(key)
            if vals:
                val = vals[0]
                if val.startswith(("http://", "https://")):
                    return val
                decoded = urllib.parse.unquote(val)
                if decoded.startswith(("http://", "https://")):
                    return decoded
    except Exception:
        pass
    return ""


def _is_media_url(url: str, content_type: str) -> bool:
    if url.startswith(("data:", "blob:")):
        return False
    ct = (content_type or "").lower()
    if ct.startswith(("video/", "audio/", "image/")):
        return True
    path = urllib.parse.urlparse(url).path.lower()
    ext = Path(path).suffix
    return ext in MEDIA_EXTENSIONS


def _media_kind(url: str, content_type: str) -> str:
    """判定 URL/响应属于哪类媒体：video / audio / image，非媒体返回空串。"""
    if url.startswith(("data:", "blob:")):
        return ""
    ct = (content_type or "").lower()
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("audio/"):
        return "audio"
    if ct.startswith("image/"):
        return "image"
    path = urllib.parse.urlparse(url).path.lower()
    ext = Path(path).suffix
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in IMAGE_EXTS:
        return "image"
    # 平台伪扩展（v1.22.1 修快手/抖音图集漏收）：图集 CDN 的 URL 结尾不是
    # 标准 .jpg/.webp，而是 …~tplv-photomode-zl.image / .awebp——不识别就
    # 整条判不出媒体类型，正文图集全漏（只能收着头像表情当垃圾成果）。
    if ext in (".image", ".awebp"):
        return "image"
    return ""


def _ext_from_content_type(content_type: str) -> str:
    ct = (content_type or "").lower().split(";")[0].strip()
    return CONTENT_TYPE_EXT.get(ct, "")


def _host_matches(host: str, domain: str) -> bool:
    """域名精确匹配：host 等于 domain 或是其子域名。
    修复子串匹配漏洞——"douyin.com" in "notdouyin.com" 为 True，
    伪造前缀域名能骗过视频站一票否决/APP商店识别等全部域名判断。"""
    h = (host or "").lower().strip()
    d = (domain or "").lower().strip()
    return h == d or h.endswith("." + d)


def _safe_request_reason(url: str, resource_type: str) -> Optional[str]:
    """安全模式请求裁决：返回拦截原因字符串，None 表示放行。"""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host and any(host == d or host.endswith("." + d) for d in MINING_DOMAINS):
        return f"挖矿/恶意域名 {host}"
    if resource_type == "websocket" and any(p in url for p in STRATUM_PORTS):
        return f"矿池 Stratum 端口 {host}"
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if ext in DANGEROUS_EXTS and resource_type in ("document", "other", ""):
        return f"危险文件导航 {ext}"
    return None


def _safe_save_reason(filename: str, size: int) -> Optional[str]:
    """安全模式落盘裁决：返回拒绝原因字符串，None 表示放行。"""
    ext = Path(filename).suffix.lower()
    if ext not in SAFE_ALLOWED_EXTS:
        return f"非白名单扩展名 {ext or '(无扩展名)'}"
    if size > SAFE_MAX_FILE_BYTES:
        return f"超过 {SAFE_MAX_FILE_BYTES // (1024 * 1024)}MB 上限"
    return None


def _is_junk_resource(url: str, content_type: str, size: int, size_strict: bool = True) -> bool:
    """判定垃圾资源。size_strict=False 时跳过尺寸阈值（图集收割场景：
    用户点名要图，几十 KB 的正片图不是垃圾；只按扩展名/URL 关键词滤真图标）。"""
    ct = (content_type or "").lower()
    path = urllib.parse.urlparse(url).path.lower()
    ext = Path(path).suffix
    if ext in JUNK_EXTENSIONS:
        return True
    # 站点 UI/推广物料域（v1.22.1 抖音压测）：pc_client 安装视频、引导图等
    # 大体积推广物料混进产物——域名级一票否决，size_strict 与否都拦。
    if _is_static_asset_host(url):
        return True
    if any(h in url.lower() for h in JUNK_URL_HINTS):
        return True
    if not size_strict:
        return False
    # 小图片基本都是封面/图标，不是内容
    if ct.startswith("image/") and size < 150 * 1024:
        return True
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp") and size < 150 * 1024:
        return True
    # 小音频残片（铃声/音效）
    if ct.startswith("audio/") and 0 < size < 30 * 1024:
        return True
    return False


def _safe_filename(url: str, content_type: str, index: int) -> str:
    parsed = urllib.parse.urlparse(url)
    base = os.path.basename(parsed.path)
    ext = Path(base).suffix.lower()
    if ext not in MEDIA_EXTENSIONS:
        ext = _ext_from_content_type(content_type)
    if not ext:
        ext = ".bin"
    stem = Path(base).stem[:80] if base and Path(base).stem else "media"
    stem = re.sub(r'[\\/:*?"<>|]+', "_", stem).strip(" .")
    if not stem:
        stem = "media"
    return f"{int(time.time())}_{index:03d}_{stem}{ext}"


def _assess_saved_quality(saved: list, wants: set) -> str:
    """成果质量分级（v1.22.1 修"假成功截断兜底链"，平台无关）：
    full    = 解码验证过的合并正片，或完整视频/音频文件（整文件响应，非分段拼装）
    partial = 有用户要的类型（图集的图、音频等），但无验证级 AV
    junk    = 产物与用户意图零交集——典型：要视频只拿到分段残件+封面图/装饰图
    empty   = 无产物
    判据只有两条：①残件(cache-segment)合并失败时不算成果（合并成功会变身
    merged-segment 并带 verified_duration_sec）；②产物媒体类型与 wants 的交集。
    不含任何域名/平台特判——抖音的封面垃圾、快手的头像垃圾、任何站的"抓了个
    寂寞"都按同一把尺子量。"""
    if not saved:
        return "empty"
    got: set = set()
    has_verified = has_complete_av = False
    for i in saved:
        if i.get("kind") == "cache-segment":
            continue  # 拼装残件：合并成功才升格为成果，失败就只是原料
        if i.get("verified_duration_sec"):
            has_verified = True
        # v1.22.1 排雷（B站实测）：url or path 的短路写法在 yt-dlp 条目上翻车——
        # 它的 url 是页面链接（bilibili.com/video/BV… 无扩展名），path 才是 .mp4；
        # 旧写法 url 非空就永远不看 path → 判不出 video → 21.5MB 成品被判 junk
        # → chain 不认账 → browser 路把全部资源重抓一遍（188MB 重复拉流）。
        # 两边都试：URL 判不出再看落盘路径。
        k = (_media_kind(i.get("url", ""), i.get("content_type", ""))
             or _media_kind(i.get("path", ""), i.get("content_type", "")))
        if k:
            got.add(k)
        else:
            # v1.22.1 排雷：_media_kind 只认 video/audio/image——text 路线的 .txt、
            # files 路线的 zip/pdf 全返回 ""，text/file 意图永远进不了 got →
            # 成功下载也被判 junk（要文本拿到正文、要文件拿到文件全是"零交集"）。
            ik = i.get("kind", "")
            if ik == "text":
                got.add("text")
            elif ik in ("file", "download") or str(i.get("path", "")).lower().endswith(FILE_EXTS):
                got.add("file")
        if k in ("video", "audio"):
            has_complete_av = True
    if has_verified or has_complete_av:
        return "full"
    if not wants or (got & wants):
        return "partial"
    return "junk"


# CDN 路由前缀（v1.22.1 排雷）：B站 mcdn（P2P CDN）给同一条流的 URL 加
# /v1/resource 前缀——`mcdn.bilivideo.cn/v1/resource/upgcxcode/…/x.m4s` 与
# `bilivideo.com/upgcxcode/…/x.m4s` 是同一文件，但路径不同 → 按路径去重/分组
# 判成两条资源，同一条流被完整下载 2-3 份（B站实测 130MB 原料，应 ~57MB）。
_CDN_ROUTE_PREFIXES = ("/v1/resource/",)


def _stream_path_norm(url: str) -> str:
    """流资源路径规范化（平台无关）：小写 + 剥 CDN 路由前缀。
    去重/分组一律用规范化路径——同一文件的镜像变体（含路由前缀差异）归一。"""
    try:
        path = urllib.parse.urlparse(url).path.lower()
        for _pref in _CDN_ROUTE_PREFIXES:
            if path.startswith(_pref):
                return path[len(_pref) - 1:]  # 保留前导 /
        return path
    except Exception:
        return (url or "").lower()


def _is_static_asset_host(url: str) -> bool:
    """站点 UI/推广物料域判定（v1.22.1 抖音压测）：douyinstatic.com 的
    pad_guid/mobile_home 引导图、bytednsdoc.com 的 douyin_pc_client.mp4
    （11MB PC 客户端安装推广视频）全不是用户内容——域名级一票否决。"""
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        return any(_host_matches(host, h) for h in STATIC_ASSET_HOSTS)
    except Exception:
        return False


def _stream_basename(url: str) -> str:
    """流资源 basename（v1.22.1 抖音压测）：抖音同一视频的多镜像 URL 路径
    各不相同（tos hash 不同），路径级去重失效——同名 media.mp4 连下 3 份
    （实测 2.6MB×2 收割 + 5.9MB 整取）。视频/音频流文件名含唯一 ID（B站
    m4s）或页面单视频语境下同名即同资源（抖音 media.mp4），按 basename
    去重。图片不适用（同名不同目录的图真实存在）；无媒体扩展名的 API
    路径（/aweme/v1/play 等 basename 无区分度）不参与。"""
    try:
        base = os.path.basename(urllib.parse.urlparse(url).path.lower())
        ext = Path(base).suffix
        if ext not in VIDEO_EXTS and ext not in AUDIO_EXTS:
            return ""
        return base
    except Exception:
        return ""


def _url_group_key(url: str) -> str:
    """分段分组键：规范化目录路径（不含 host——同目录不同 host = CDN 镜像 = 同
    一资源；同一视频的分段共享目录前缀，推荐位视频来自不同目录，靠目录分开）。"""
    try:
        path = _stream_path_norm(url)
        return path.rsplit("/", 1)[0] if "/" in path else path
    except Exception:
        return url


def _url_identity(url: str) -> str:
    """同资源判定键：scheme 无关 + 去 query（v1.22.1 修重复拉流）。
    `//host/x.mp4?a=1`（DOM 协议相对地址）与 `https://host/x.mp4?sig=B`（script JSON
    完整地址）是同一文件——旧去重比完整字符串漏判，同一 media.mp4 被拉两份。"""
    try:
        s = (url or "").strip()
        if s.startswith("//"):
            s = "https:" + s
        p = urllib.parse.urlsplit(s)
        return f"{p.netloc.lower()}{p.path}"
    except Exception:
        return url or ""


def _cap_filename(name: str, max_stem: int = 80) -> str:
    """站点给的文件名硬限长（v1.22.1 修超长写盘失败）：stem 截到 max_stem，
    保住扩展名。Windows 260 字符路径上限下，深层目录 + 站点名（URL 参数拼进
    title）会把三路写入全部打死。"""
    if not name:
        return name
    stem, dot, ext = name.rpartition(".")
    if dot and 0 < len(ext) <= 6 and "/" not in ext:
        return f"{stem[:max_stem]}.{ext}"
    return name[:max_stem + 7]


def _resolve_share_redirect(url: str, timeout: float = 8.0) -> Optional[str]:
    """分享短链解析真实 URL（v1.22.1 修 note 转路盲区）：v.douyin.com/xhslink.com
    这类短链不含 /note/，调度器的 note 预判（子串检查）永远不触发，ytdlp 白撞
    "Unsupported URL"。HEAD 不跟跳读 Location，失败退 GET（只拿响应头不读体）。
    拿不到返回 None，调用方按原 URL 走（浏览器路线自己会跟跳，不会更糟）。"""
    import urllib.request

    from .constants import USER_AGENTS
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url, method=method,
                headers={"User-Agent": USER_AGENTS[0]})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                final = resp.geturl()
                if final and final != url:
                    return final
                return None  # 没跳转：不是短链或已解析，别再折腾
        except Exception:
            continue
    return None


def _extract_shell_redirect(html_text: str) -> Optional[str]:
    """从跳转壳页 HTML 提取真实目标 URL（分享链接常见：api.xxx/share?link_id= 返回壳页）。
    识别 meta refresh / JS location 跳转 / redirect 类 JSON 字段 / og:url。拿不到返回 None。"""
    if not html_text:
        return None
    # meta refresh: <meta http-equiv="refresh" content="0;url=xxx">
    m = re.search(
        r'http-equiv=["\']?refresh["\']?[^>]*content=["\']?\d+;\s*url=([^"\'>\s]+)',
        html_text, re.I,
    )
    if m:
        return m.group(1).replace("&amp;", "&")
    # JS 跳转: location.href='x' / location.replace("x")
    m = re.search(r'location\.(?:href|replace)\s*[=(]\s*["\'](https?://[^"\']+)["\']', html_text)
    if m:
        return m.group(1).replace("&amp;", "&")
    # redirect 类 JSON 字段（redirect_data/share 数据里常带真实链接）
    for key in ("redirect", "redirect_url", "redirectUrl", "redirect_data",
                "link_url", "linkUrl", "share_url", "shareUrl", "jump_url", "target_url", "web_url"):
        m = re.search(key + r'["\']?\s*[:=]\s*["\'](https?://[^"\']+)["\']', html_text)
        if m:
            return m.group(1).replace("&amp;", "&")
    # og:url / canonical
    m = re.search(r'(?:property=["\']og:url["\']|rel=["\']canonical["\'])[^>]*(?:content|href)=["\'](https?://[^"\']+)["\']', html_text, re.I)
    if not m:
        m = re.search(r'(?:content|href)=["\'](https?://[^"\']+)["\'][^>]*(?:property=["\']og:url["\']|rel=["\']canonical["\'])', html_text, re.I)
    if m:
        return m.group(1).replace("&amp;", "&")
    return None


def _is_split_stream_fragment(url: str) -> bool:
    """m4s/ts 是视频站 MSE 分离流分段（视频轨/音频轨拆成两条流）。
    单独抓一条就是"只有画面没声音/只有声音没画面"的残件。"""
    return urllib.parse.urlparse((url or "").split("?")[0]).path.lower().endswith((".m4s", ".ts"))


def _filename_from_disposition(resp, url: str) -> str:
    """从 Content-Disposition 提取文件名（支持 filename*=UTF-8'' 和 filename="），
    拿不到就用 URL 最后一段。"""
    cd = ""
    try:
        cd = resp.headers.get("Content-Disposition", "") or ""
    except Exception:
        pass
    if cd:
        m = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.I)
        if m:
            try:
                return urllib.parse.unquote(m.group(1).strip().strip('"'))
            except Exception:
                pass
        m = re.search(r'filename="?([^";]+)"?', cd, re.I)
        if m:
            name = m.group(1).strip()
            if name:
                return name
    base = os.path.basename(urllib.parse.urlparse(url).path) or "file"
    return base


def _is_app_store_url(url: str) -> bool:
    """判定 URL 是否 APP 商店/引流装APP页面。"""
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(_host_matches(host, h) for h in APP_STORE_HOSTS)


def _decode_scheme_target(href: str) -> str:
    """从 scheme 跳转链接里解出真 URL（theirapp://dl?url=https%3A%2F%2F...）。
    解不出 https 目标就返回空串。"""
    if not href or "://" not in href:
        return ""
    try:
        qs = urllib.parse.urlparse(href).query or href.split("?", 1)[-1]
        params = urllib.parse.parse_qs(qs, keep_blank_values=True)
    except Exception:
        return ""
    for key in ("url", "download", "download_url", "downloadUrl", "link", "target", "redirect"):
        if key in params:
            cand = params[key][0]
            cand = urllib.parse.unquote(cand)
            if cand.startswith(("http://", "https://")):
                return cand
    return ""


__all__ = [
    'APP_STORE_HOSTS',
    'SHELL_BODY_TEXT_LIMIT',
    'CLICK_DOWNLOAD_FILE_TYPES',
    'DOWNLOAD_BUTTON_TEXTS',
    '_decode_redirect_url',
    '_is_media_url',
    '_media_kind',
    '_ext_from_content_type',
    '_host_matches',
    '_safe_request_reason',
    '_safe_save_reason',
    '_is_junk_resource',
    '_safe_filename',
    '_url_group_key',
    '_url_identity',
    '_assess_saved_quality',
    '_cap_filename',
    '_resolve_share_redirect',
    '_extract_shell_redirect',
    '_is_split_stream_fragment',
    '_filename_from_disposition',
    '_is_app_store_url',
    '_decode_scheme_target',
]
