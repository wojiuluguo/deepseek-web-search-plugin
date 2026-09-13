# -*- coding: utf-8 -*-
"""yt-dlp 三开关（playlist / extract-audio / quality）离线单测：
不发网络，断言 _build_ydl_opts 各开关下的字典形态与默认行为零变化。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from auto_save.routes import _build_ydl_opts, _ytdlp_format, set_ytdlp_opts  # noqa: E402

d = Path("downloads/cache")
fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# 1) 默认态 = 旧行为（v1.22.1 逐字段一致）
set_ytdlp_opts(playlist=False, playlist_max=0, extract_audio=False, quality="best")
o = _build_ydl_opts(d)
check("默认 noplaylist=True", o.get("noplaylist") is True, str(o))
check("默认 format 原串", o.get("format") == "bestvideo+bestaudio/best")
check("默认无 postprocessors/playlistend",
      "postprocessors" not in o and "playlistend" not in o)

# 2) --quality
o = _build_ydl_opts(d, {"quality": "720p"})
check("--quality 720p 含 height 封顶", "bestvideo[height<=720]" in o["format"], o["format"])
check("--quality 回退链兜到 DASH 合并", o["format"].endswith("bestvideo+bestaudio/best"))
check("--quality 竖屏 width 招", "bestvideo[width<=720]" in o["format"])

# 3) --playlist + --playlist-max
o = _build_ydl_opts(d, {"playlist": True, "playlist_max": 5})
check("--playlist 解除 noplaylist", "noplaylist" not in o)
check("--playlist-max 5 → playlistend", o.get("playlistend") == 5)
o = _build_ydl_opts(d, {"playlist": True})
check("--playlist 不带 max 无 playlistend", "playlistend" not in o)

# 4) --extract-audio
o = _build_ydl_opts(d, {"extract_audio": True, "audio_format": "m4a"})
check("转音频只拉 bestaudio", o["format"] == "bestaudio/best")
pp = o.get("postprocessors", [{}])[0]
check("FFmpegExtractAudio + m4a", pp.get("key") == "FFmpegExtractAudio"
      and pp.get("preferredcodec") == "m4a", str(pp))

# 5) format 边界（未知值安全回退 best）
check("format 未知值回退 best", _ytdlp_format("垃圾输入") == "bestvideo+bestaudio/best")
check("format 空串回退 best", _ytdlp_format("") == "bestvideo+bestaudio/best")

# 6) 模块级状态生效链 + 还原
set_ytdlp_opts(playlist=True, quality="480p")
o = _build_ydl_opts(d)
check("set_ytdlp_opts 模块级生效", "noplaylist" not in o
      and "bestvideo[height<=480]" in o["format"])
set_ytdlp_opts(playlist=False, playlist_max=0, extract_audio=False,
               audio_format="mp3", quality="best")

print("=" * 40)
if fails:
    print(f"FAILED: {len(fails)} 项 → {fails}")
    sys.exit(1)
print("ALL YTDLP OPTS TESTS PASS")
