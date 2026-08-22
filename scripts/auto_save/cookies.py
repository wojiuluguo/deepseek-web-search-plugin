"""登录态：Netscape cookies 解析 / 本机浏览器提取（借道 yt-dlp）/ 登录兜底接种。
三个函数全是"传入 context → 干活 → 返回"纯管道——拆分绝对安全级。"""

import sys
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional


def _parse_netscape_cookies(cookie_file: str):
    """解析 Netscape cookies.txt（浏览器扩展导出的标准格式）→ Playwright add_cookies 列表。
    返回 (cookies, error)：error 非 None 表示文件不可用（不存在/格式坏/没有有效行）。"""
    p = Path(cookie_file)
    if not p.is_file():
        return None, f"cookies 文件不存在: {cookie_file}"
    cookies = []
    try:
        for ln in p.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or ln.startswith("//"):
                continue
            parts = ln.split("\t")
            if len(parts) != 7:
                continue
            domain, _, path_s, secure, expires, name, value = parts
            try:
                exp = int(expires)
            except ValueError:
                exp = -1
            if not name:
                continue
            c = {
                "name": name, "value": value,
                "domain": domain if domain.startswith(".") else "." + domain,
                "path": path_s or "/",
                "secure": secure.upper() == "TRUE",
            }
            # expires=0/-1 → 会话 cookie，Playwright 用 -1 表示
            c["expires"] = exp if exp > 0 else -1
            cookies.append(c)
    except Exception as exc:
        return None, f"cookies 文件读取失败: {exc}"
    if not cookies:
        return None, "cookies 文件里没有有效行（需要 Netscape 格式，'Get cookies.txt' 扩展导出的就是）"
    return cookies, None


def _add_cookies_to_context(context, cookie_file: str):
    """把 cookies.txt 注入浏览器上下文。返回 (True, n) 或 (False, error)。"""
    cookies, err = _parse_netscape_cookies(cookie_file)
    if err:
        return False, err
    try:
        context.add_cookies(cookies)
        return True, len(cookies)
    except Exception as exc:
        return False, f"cookie 注入失败: {exc}"


def _browser_cookies_to_playwright(browser_name: str):
    """读本机浏览器(chrome/edge/firefox)的登录 cookie → Playwright add_cookies 列表。
    借道 yt-dlp 的 cookie 提取器（Playwright 自己没有读本机浏览器的 API——这正是
    v1.13.x 里 --cookies-from-browser 在浏览器路线静默失效的根因）。
    返回 (cookies, error)：error 非 None 表示读不到（未装 yt-dlp / 该浏览器没登录过 /
    Chrome 新版应用级加密解不开），如实报错不装样子。"""
    try:
        from yt_dlp import cookies as ydl_cookies
    except ImportError:
        return None, "yt-dlp not installed（读浏览器 cookie 需要）"
    try:
        jar = ydl_cookies.extract_cookies_from_browser(browser_name)
    except Exception as exc:
        return None, f"读取 {browser_name} cookie 失败: {exc}"
    cookies = []
    for c in jar:
        if not c.name:
            continue
        cookies.append({
            "name": c.name,
            "value": c.value or "",
            "domain": c.domain if c.domain.startswith(".") else "." + c.domain,
            "path": c.path or "/",
            "secure": bool(c.secure),
            "expires": float(c.expires) if c.expires else -1,  # 会话 cookie 用 -1
        })
    if not cookies:
        return None, f"{browser_name} 里没读到 cookie（该浏览器登录过目标站点才会有）"
    return cookies, None


def _inject_login_cookies(context, cookie_file: str, cookies_from_browser: str, route_name: str):
    """统一登录态注入：cookies.txt 文件优先，否则借道 yt-dlp 读本机浏览器。
    供 browser/cache、harvest、vision 路线共用（此前只有 cookies.txt 一条腿）。"""
    if cookie_file:
        ok, info = _add_cookies_to_context(context, cookie_file)
        sys.stderr.write(f"[cookies] {route_name} 注入{str(info) + ' 条' if ok else '失败: ' + str(info)}\n")
        return info if ok else None
    if cookies_from_browser:
        cookies, err = _browser_cookies_to_playwright(cookies_from_browser)
        if cookies:
            try:
                context.add_cookies(cookies)
                sys.stderr.write(f"[cookies] {route_name} 已从 {cookies_from_browser} 注入 {len(cookies)} 条\n")
                return len(cookies)
            except Exception as exc:
                sys.stderr.write(f"[cookies] {route_name} 注入失败: {exc}\n")
                return None
        sys.stderr.write(f"[cookies] {route_name} {err}\n")
    return None


def _base_domain(host: str) -> str:
    """取主域（www.douyin.com → douyin.com）。简单两段启发式，
    com.cn 类三段后缀会取窄一档，接种场景够用（宁可少注不错注）。"""
    parts = (host or "").lower().strip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else (host or "")


def _login_rescue(context, page, url: str) -> str:
    """登录兜底（--login-rescue，v1.18.0）：扫码被风控拒发 session 的兜底——
    自动遍历本机 chrome→edge→firefox，找到含目标域登录 cookie 的那个，
    接种进当前上下文并刷新页面。人肉在自己浏览器登录目标站（天经地义），
    工具只负责把登录态搬进来，绕开"自动化环境扫码不作数"的死锁。"""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host:
        return "login_rescue: URL 无域名，跳过"
    base = _base_domain(host)
    for browser in ("chrome", "edge", "firefox"):
        cookies, err = _browser_cookies_to_playwright(browser)
        if not cookies:
            continue  # 该浏览器读不到/没登录过，试下一个
        hit = [c for c in cookies if (c.get("domain") or "").lstrip(".").endswith(base)]
        if not hit:
            continue  # 有 cookie 但不含目标域
        try:
            context.add_cookies(hit)
        except Exception as exc:
            return f"login_rescue: {browser} cookie 注入失败: {exc}"
        try:
            page.reload(wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
        return f"login_rescue: 已从 {browser} 接种 {len(hit)} 条 {base} 登录 cookie 并刷新页面"
    return ("login_rescue: 本机 chrome/edge/firefox 都没有目标站登录态"
            "（先在自己平时的浏览器里登录一次目标站再试）")


__all__ = [
    '_parse_netscape_cookies',
    '_add_cookies_to_context',
    '_browser_cookies_to_playwright',
    '_inject_login_cookies',
    '_base_domain',
    '_login_rescue',
]
