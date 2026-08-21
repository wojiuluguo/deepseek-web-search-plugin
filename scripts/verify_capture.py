#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verify Capture — 浏览器抓包产物事后校验（对 auto_save_browser.py 的产物做最终裁决）

背景：auto_save_browser.py 抓抖音/B站后，产物目录里可能混着：
  - 垃圾资源（封面/图标/gif/推荐位残片）
  - 硬拼的 merged_*.mp4（分段不兼容时 Duration 虚标或不可播）
  - 抓包中途挂死导致的残缺分段

铁律（与抓取端一致）：
  1. 真实可播时长 = ffmpeg 解码到 null 的 time= 实测；ffprobe/moov 标称 Duration 不可信
  2. moov 标称 vs 解码实测差 >30% → 判 duration_inflated（虚标）
  3. 解码失败的视频 → 判 broken；merged_* 一律不豁免

用法：
    # 扫描产物目录，逐文件给结论（默认人类可读）
    python verify_capture.py --dir "downloads/cache/xxx"

    # JSON 输出（给 AI）
    python verify_capture.py --dir "downloads/cache/xxx" --json

    # 扫描后自动删除垃圾和坏文件
    python verify_capture.py --dir "downloads/cache/xxx" --clean

    # 把 cache_segments 里的分段用 ffmpeg concat demuxer 正规重组装（非硬拼）
    python verify_capture.py --assemble "downloads/cache/xxx/cache_segments"

    # 双抓对比：同一 URL 抓两次 MD5 是否一致（确认没抓漏）
    python verify_capture.py --recheck "https://.../video.mp4"
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from auto_save_browser import (  # noqa: E402
    AUDIO_EXTS,
    IMAGE_EXTS,
    JUNK_EXTENSIONS,
    VIDEO_EXTS,
    _decoded_duration,
    _ffmpeg_path,
    _ffprobe_info,
    _ffprobe_path,
    _probe_resolution,
)

MIN_PLAYABLE_SEC = 3.0          # 短于这个不算正片
INFLATE_TOLERANCE = 0.70        # 解码实测 < 标称的 70% → 虚标
TINY_IMAGE_BYTES = 150 * 1024   # 与抓取端 _is_junk_resource 同阈值
TINY_AUDIO_BYTES = 30 * 1024


def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _md5_url(url: str, timeout: int = 60) -> Optional[str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Referer": url,
    })
    h = hashlib.md5()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for chunk in iter(lambda: resp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_file(path: Path) -> Dict:
    """对单个文件给出裁决。video/merged 用解码实测，图片/小音频用体量规则。"""
    ext = path.suffix.lower()
    size = path.stat().st_size
    item = {"file": str(path), "name": path.name, "ext": ext, "size": size}

    if ext in JUNK_EXTENSIONS:
        item.update(kind="junk", verdict="junk", reason="垃圾扩展名")
        return item
    if ext in IMAGE_EXTS:
        if size < TINY_IMAGE_BYTES:
            item.update(kind="junk", verdict="junk", reason=f"图片<{TINY_IMAGE_BYTES//1024}KB,封面/图标")
        else:
            item.update(kind="image", verdict="ok", reason="有效图片")
        return item
    if ext in AUDIO_EXTS:
        if size < TINY_AUDIO_BYTES:
            item.update(kind="junk", verdict="junk", reason=f"音频<{TINY_AUDIO_BYTES//1024}KB,提示音残片")
            return item
    if ext not in VIDEO_EXTS and ext not in AUDIO_EXTS:
        item.update(kind="other", verdict="skip", reason="非媒体文件")
        return item

    kind = "audio" if ext in AUDIO_EXTS else "video"
    is_merged = path.name.startswith(("merged_", "assembled_"))
    is_segment = ext in (".m4s", ".ts") and not is_merged
    item["kind"] = kind

    info = _ffprobe_info(str(path))
    nominal = None
    if info and info.get("format", {}).get("duration"):
        try:
            nominal = float(info["format"]["duration"])
        except (TypeError, ValueError):
            nominal = None
    item["nominal_duration_sec"] = round(nominal, 2) if nominal else None
    res = _probe_resolution(info)
    if res:
        item["resolution"] = f"{res[0]}x{res[1]}"

    if is_segment:
        item.update(verdict="fragment", reason="原始分段(未合并)", real_duration_sec=None)
        return item

    real = _decoded_duration(str(path)) if _ffmpeg_path() else None
    item["real_duration_sec"] = round(real, 2) if real else None

    if real is None:
        if not _ffmpeg_path():
            item.update(verdict="broken", reason="无 ffmpeg,无法验证")
        elif nominal:
            item.update(verdict="broken", reason=f"解码失败,标称{nominal:.1f}s(虚标/损坏)")
        else:
            item.update(verdict="broken", reason="解码失败且无元数据(残缺/截断)")
        return item
    if real < MIN_PLAYABLE_SEC:
        item.update(verdict="fragment", reason=f"真实时长{real:.1f}s<{MIN_PLAYABLE_SEC}s,残片")
        return item
    if nominal and real < nominal * INFLATE_TOLERANCE:
        item.update(
            verdict="duration_inflated",
            reason=f"标称{nominal:.1f}s但实测{real:.1f}s,moov虚标"
            + ("(硬拼分段)" if is_merged else ""),
        )
        return item
    item.update(verdict="ok", reason="可播" + ("(解码实测通过)" if is_merged else ""))
    return item


def scan_dir(target: Path) -> Dict:
    """扫描产物目录：逐文件裁决 → 正片/候选/垃圾分层 + 总览。"""
    files = sorted(
        p for p in target.rglob("*")
        if p.is_file() and p.suffix.lower() not in (".txt", ".json", ".url")
    )
    items = [classify_file(p) for p in files]

    ok_items = [i for i in items if i["verdict"] == "ok" and i["kind"] in ("video", "audio")]
    ok_items.sort(key=lambda x: x.get("real_duration_sec") or 0, reverse=True)
    for idx, i in enumerate(ok_items):
        i["role"] = "main" if idx == 0 else "candidate"

    junk = [i for i in items if i["verdict"] == "junk"]
    broken = [i for i in items if i["verdict"] == "broken"]
    inflated = [i for i in items if i["verdict"] == "duration_inflated"]
    main = ok_items[0] if ok_items else None

    return {
        "dir": str(target),
        "total_files": len(items),
        "main": {k: main.get(k) for k in ("file", "real_duration_sec", "resolution", "size")} if main else None,
        "candidates": [
            {"file": i["file"], "real_duration_sec": i["real_duration_sec"]}
            for i in ok_items[1:]
        ],
        "junk_count": len(junk),
        "broken_count": len(broken),
        "inflated_count": len(inflated),
        "fragment_count": sum(1 for i in items if i["verdict"] == "fragment"),
        "playable_total_sec": round(sum(i.get("real_duration_sec") or 0 for i in ok_items), 2),
        "ffmpeg_found": _ffmpeg_path() is not None,
        "items": items,
    }


def clean_dir(report: Dict, also_broken: bool = True) -> Dict:
    """删除垃圾；默认连 broken/inflated 一起删（都可判定为不可用产物）。"""
    removed = []
    verdicts = {"junk"}
    if also_broken:
        verdicts |= {"broken", "duration_inflated"}
    for i in report["items"]:
        if i.get("verdict") in verdicts:
            try:
                Path(i["file"]).unlink()
                removed.append(i["file"])
            except OSError:
                pass
    return {"removed": removed, "removed_count": len(removed)}


def assemble_segments(seg_dir: Path) -> Dict:
    """用 ffmpeg concat demuxer 正规重组装（remux，非硬拼字节）。
    只装体量最大的同扩展名组，装完解码验证，不通过就删掉不留坏文件。"""
    if not _ffmpeg_path():
        return {"ok": False, "error": "无 ffmpeg，无法重组装"}
    files = [p for p in seg_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS | AUDIO_EXTS]
    if len(files) < 2:
        return {"ok": False, "error": f"分段不足({len(files)}个),无需组装"}

    groups: Dict[str, List[Path]] = {}
    for p in files:
        groups.setdefault(p.suffix.lower(), []).append(p)
    ext, parts = max(groups.items(), key=lambda kv: sum(p.stat().st_size for p in kv[1]))
    parts.sort(key=lambda p: p.name)

    out_ext = ".mp4" if ext in (".mp4", ".m4s", ".m4v", ".ts") else ext
    out_path = seg_dir.parent / f"assembled_{int(time.time())}{out_ext}"
    list_path = seg_dir / f"_concat_{int(time.time())}.txt"
    try:
        with open(list_path, "w", encoding="utf-8") as f:
            for p in parts:
                f.write(f"file '{p.resolve()}'\n")
        import subprocess
        proc = subprocess.run(
            [_ffmpeg_path(), "-y", "-hide_banner", "-f", "concat", "-safe", "0",
             "-i", str(list_path), "-c", "copy", str(out_path)],
            capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=300,
        )
        if proc.returncode != 0 or not out_path.exists():
            return {"ok": False, "error": "concat remux 失败(分段容器不兼容)", "stderr_tail": proc.stderr[-300:]}
        real = _decoded_duration(str(out_path))
        if real is None or real < MIN_PLAYABLE_SEC:
            out_path.unlink(missing_ok=True)
            return {"ok": False, "error": f"组装后解码验证不通过(实测{real}s),已删除"}
        return {
            "ok": True, "file": str(out_path), "segments": len(parts),
            "real_duration_sec": round(real, 2),
        }
    finally:
        list_path.unlink(missing_ok=True)


def recheck_url(url: str) -> Dict:
    """铁律2：同一链接抓两次，MD5 一致 → 内容稳定，没抓漏。"""
    try:
        h1, h2 = _md5_url(url), _md5_url(url)
        return {
            "url": url, "md5_first": h1, "md5_second": h2,
            "match": h1 == h2,
            "conclusion": "两次一致:内容稳定,单次抓取可信" if h1 == h2
                          else "两次不一致:动态链接,需以浏览器上下文抓取为准",
        }
    except Exception as exc:
        return {"url": url, "match": None, "error": str(exc)}


def _fmt_report(r: Dict) -> str:
    lines = [f"目录: {r['dir']}", f"文件总数: {r['total_files']}  ffmpeg: {'有' if r['ffmpeg_found'] else '无(视频结论受限)'}"]
    main = r.get("main")
    if main:
        res = f"  {main['resolution']}" if main.get("resolution") else ""
        lines.append(f"正片: {Path(main['file']).name}  实测{main['real_duration_sec']}s{res}  {main['size']//1024}KB")
    else:
        lines.append("正片: 无(目录里没有可播媒体)")
    lines.append(
        f"统计: 可播总时长{r['playable_total_sec']}s | 候选{len(r['candidates'])} | "
        f"垃圾{r['junk_count']} | 坏文件{r['broken_count']} | 虚标{r['inflated_count']} | 残片{r['fragment_count']}"
    )
    for i in r["items"]:
        if i.get("verdict") in ("ok", "skip"):
            continue
        lines.append(f"  [{i['verdict']}] {i['name']} — {i.get('reason', '')}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify Capture: 浏览器抓包产物事后校验（真实解码裁决正片/垃圾/虚标/坏文件）"
    )
    parser.add_argument("--dir", help="要校验的产物目录")
    parser.add_argument("--clean", action="store_true", help="校验后自动删除垃圾/坏文件/虚标文件")
    parser.add_argument("--keep-broken", action="store_true", help="--clean 时保留 broken/inflated,只删垃圾")
    parser.add_argument("--assemble", metavar="SEG_DIR", help="把分段目录用 ffmpeg concat 正规重组装")
    parser.add_argument("--recheck", metavar="URL", help="同一 URL 抓两次 MD5 对比,确认没抓漏")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    if args.recheck:
        out = recheck_url(args.recheck)
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json
              else f"{out.get('conclusion') or out.get('error')}\nMD5#1: {out.get('md5_first')}\nMD5#2: {out.get('md5_second')}")
        return 0

    if args.assemble:
        out = assemble_segments(Path(args.assemble).expanduser().resolve())
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(f"组装成功: {out['file']}  {out['segments']}段  实测{out['real_duration_sec']}s" if out["ok"]
                  else f"组装失败: {out['error']}")
        return 0 if out["ok"] else 1

    if not args.dir:
        parser.print_help()
        return 2

    target = Path(args.dir).expanduser().resolve()
    if not target.is_dir():
        print(json.dumps({"error": f"目录不存在: {target}"}) if args.json else f"目录不存在: {target}",
              file=sys.stderr)
        return 2

    report = scan_dir(target)
    if args.clean:
        report["clean"] = clean_dir(report, also_broken=not args.keep_broken)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else _fmt_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
