"""跳转壳解码（v1.25.0 搜索压测优化 P1）：
搜狗 /link?url=、百度 /link?url=、360 /link?m= 的结果是加密跳转壳——
下游（AI 引用来源/下载电路）拿到的不是真实地址。压测实测：
- 百度壳：GET 跟随 302 直接得真实 URL（0.3-1.5s，成功率 ~80%）；
- 360 壳：返回 200 小页（~378 字节），body 里 JS location.replace("真实URL")；
- 搜狗壳：同为 200 壳页；壳 token 短时效（几分钟后失效），必须紧跟搜索解码。
解码阶梯：明文参数（零成本）→ GET 跟随（302 Location）→ 200 壳页提取
（location.replace / meta refresh / body 首个外链）。并发 8 + 6s 超时 +
失败保留原壳（诚实降级，不阻塞搜索）。"""
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List
from urllib.parse import urlparse, parse_qs, unquote

__all__ = ["is_shell_url", "resolve_shell_url", "resolve_shell_urls"]

_SHELL_HOSTS = ("sogou.com", "baidu.com", "so.com", "360.cn")
_TIMEOUT = 4  # 壳 GET 实测 0.1-1.5s；4s 封顶防止验证码/限流时段拖尾整轮搜索
_WORKERS = 8
_MAX_SHELLS = 24  # 单轮解码壳数上限（8 并发×3 批最坏 ~12s；实际通常 ≤8 个壳 ~1s）
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

_JS_TARGET_RE = re.compile(
    r'(?:location\.(?:href|replace|assign)\(|window\.location(?:\.href)?\s*=)\s*\(?\s*["\']([^"\']+)["\']',
    re.I)
_META_REFRESH_RE = re.compile(r'url=([^"\'>;]+)', re.I)
_URL_RE = re.compile(r'https?://[^\s"\'<>]+')
_PLAIN_KEYS = ("url", "target", "m", "q", "link", "redirect", "u", "to")


def is_shell_url(url: str) -> bool:
    """是否搜索引擎跳转壳（/link 路径 + 壳域名）。"""
    try:
        p = urlparse(url or "")
        host = p.netloc.lower()
        if not host:
            return False
        if not any(host == h or host.endswith("." + h) for h in _SHELL_HOSTS):
            return False
        return "/link" in p.path.lower()
    except Exception:
        return False


def _plain_target(url: str) -> str:
    """阶梯 1：明文/URL 编码参数直接携带目标（部分壳有）。"""
    try:
        q = parse_qs(urlparse(url).query)
        for key in _PLAIN_KEYS:
            vals = q.get(key)
            if vals:
                val = vals[0]
                if val.startswith(("http://", "https://")):
                    return val
                dec = unquote(val)
                if dec.startswith(("http://", "https://")):
                    return dec
    except Exception:
        pass
    return ""


def _page_target(body: str, base_url: str) -> str:
    """从壳页 body 提取目标：JS location 赋值 > meta refresh > body 首个外链
    （外链须与壳域名不同源，防止提取到壳自身的资源）。"""
    try:
        for m in _JS_TARGET_RE.finditer(body):
            u = m.group(1).strip()
            if u.startswith(("http://", "https://")):
                return u
            if u.startswith("//"):
                return "https:" + u
        for m in _META_REFRESH_RE.finditer(body):
            u = unquote(m.group(1).strip())
            if u.startswith(("http://", "https://")):
                return u
        shell_host = urlparse(base_url).netloc.lower()
        for m in _URL_RE.finditer(body):
            u = m.group(0)
            if urlparse(u).netloc.lower() != shell_host:
                return u
    except Exception:
        pass
    return ""


def _same_site(u: str, base_url: str) -> bool:
    """同源判定：解码结果若还落在引擎自己域名上（如 302 到验证页 /s?wd=...），
    视为未解码——壳 token 失效/风控时段的常见落点，保留原壳比引用验证页诚实。"""
    try:
        return (urlparse(u).netloc.lower().removeprefix("www.")
                == urlparse(base_url).netloc.lower().removeprefix("www."))
    except Exception:
        return True


def resolve_shell_url(url: str) -> str:
    """解码单个跳转壳 → 真实 URL；解不出返回原壳（诚实降级）。
    校验：解码结果必须与壳不同源——同源说明 302 落到引擎自家页面（验证页/首页），
    是风控信号而非目标页，保留原壳。"""
    if not is_shell_url(url):
        return url
    target = _plain_target(url)
    if target and not _same_site(target, url):
        return target
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA, "Accept": "text/html,*/*;q=0.8",
            "Referer": f"https://{urlparse(url).netloc}/"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            final = resp.geturl() or ""
            if is_shell_url(final):
                # 200 壳页：从 body 提取（限读 64KB，壳页只有几百字节）
                body = resp.read(65536).decode("utf-8", "ignore")
                target = _page_target(body, final)
                return target if target and not _same_site(target, url) else final
            if _same_site(final, url):
                return url  # 302 落回引擎自家页面（验证页等）：未解码，保留壳
            return final
    except Exception as exc:
        sys.stderr.write(f"[resolve] 壳解码失败（保留原壳）: {url[:70]} → {str(exc)[:60]}\n")
        return url


def resolve_shell_urls(results: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """并发解码结果列表里的跳转壳（原地替换 url 字段）。
    无壳时零开销直接返回；解码异常不影响搜索结果产出。
    v1.25.0 自查加上限：只解前 _MAX_SHELLS 个壳（默认足够覆盖去重后的输出量），
    防极端情况（fetch_limit 级全壳）把整轮搜索拖进 24s 级解码等待。"""
    if not results:
        return results
    shells = {i: r["url"] for i, r in enumerate(results) if is_shell_url(r.get("url", ""))}
    if not shells:
        return results
    todo = dict(list(shells.items())[:_MAX_SHELLS])
    stats = {"total": len(todo), "resolved": 0}

    def _one(pair):
        i, u = pair
        return i, resolve_shell_url(u)

    try:
        with ThreadPoolExecutor(max_workers=min(_WORKERS, len(todo))) as ex:
            for i, real in ex.map(_one, todo.items()):
                if real != todo[i]:
                    results[i]["url"] = real
                    # 来源标注真实站点，AI 引用不再显示壳
                    stats["resolved"] += 1
    except Exception as exc:
        sys.stderr.write(f"[resolve] 壳解码批量异常（保留原壳）: {exc}\n")
    skipped = len(shells) - len(todo)
    sys.stderr.write(f"[resolve] 跳转壳解码 {stats['resolved']}/{stats['total']}"
                     + (f"（超上限跳过 {skipped}）" if skipped else "") + "\n")
    return results
