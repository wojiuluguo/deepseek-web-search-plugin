# deepseek-web-search

English | **[中文](README.zh-CN.md)**

An [OpenClaw](https://github.com/openclaw) skill that gives DeepSeek real web search **and** an auto-save browser that downloads videos/audio/images/files from any webpage it opens — plus a vision mode for multimodal models (see a page, operate a page).

> Current version **v1.23.3** (2026-09-14) · Author: user (Douyin ID: 94636651553) · [Changelog](#changelog)

<p align="center"><img src="assets/mascot.png" alt="deepseek-web-search mascot" width="220"></p>

## Feature Overview

| Capability | Script | Description |
|---|---|---|
| Browser-emulated search (recommended) | `search_browser.py` | Playwright-driven real Chromium, anti-bot resistant |
| Lightweight fallback search | `search.py` | Pure stdlib, zero dependencies, used when browser version fails |
| Smart search | `smart_search.py` | Auto-detects academic/tech/finance/news intent, assigns engines, retries on failure |
| Multi-engine cross-validation | `cross_search.py` | 3 engines search in parallel, compare & dedupe; `--mega` = all engines, iterative convergence |
| Search + auto-cache | `search_and_cache.py` | Auto-detects and caches media from result pages after search |
| Local standalone search engine | `own_search.py` | Self-built SQLite index; external search only discovers seed URLs |
| Auto-save browser | `auto_save_browser.py` | Opens webpages and auto-saves videos/audio/images/files/article text |
| Vision mode (multimodal) | `auto_save_browser.py` | Screenshots + screen info fed to vision models; mouse/keyboard control session (for deepseek-v4-flash-vision-exp) |
| Capture verification | `verify_capture.py` | ffmpeg real-decode duration check, inflation detection, segment merge validation |

Default search engines: Bing, Sogou, 360, Baidu (China-first); DuckDuckGo only for external/manual queries; optional Tavily, Brave Search, SearXNG (auto-enabled via environment variables).

## Network Environment Note

**This tool was developed and tested entirely on mainland China network infrastructure.** We have **not** tested it on networks outside mainland China.

- If you use it on overseas or other network environments, engine timeouts or unexpected results may occur — your understanding is appreciated.
- On overseas networks, try `--engines ddg,brave` first for better reachability.
- Support for networks outside mainland China may be added in future versions.

## Installation

The repo is plain-text code plus one mascot image (~240KB); heavy dependencies like Chromium are installed from official sources by the setup script.

```bash
git clone https://github.com/wojiuluguo/deepseek-web-search-plugin.git
cd deepseek-web-search-plugin
python install_dependencies.py     # Windows: double-click install_deps.bat
```

**One-command AI Agent deployment** (OpenClaw / any agent):

```bash
git clone --depth 1 https://github.com/wojiuluguo/deepseek-web-search-plugin.git ~/.openclaw/workspace/skills/deepseek-web-search && cd ~/.openclaw/workspace/skills/deepseek-web-search && python install_dependencies.py
```

`--depth 1` fetches only the latest commit for faster cloning. Verify with `openclaw skills list` — you should see `deepseek-web-search`. The AI-facing entry point is [SKILL.md](SKILL.md).

## Quick Usage

```bash
# Search (browser version, anti-bot)
python scripts/search_browser.py --query "latest AI news" --max-results 6 --json

# Search (lightweight, zero-dependency fallback)
python scripts/search.py --query "DeepSeek news" --json

# Token-efficient output (title + URL + 120-char snippet)
python scripts/search_browser.py --query "anything" --brief --json

# Smart search (auto engine selection)
python scripts/smart_search.py --query "transformer paper" --json

# Cross-validation (3 engines) / mega search (all engines in parallel)
python scripts/cross_search.py --query "OpenClaw" --json
python scripts/cross_search.py --query "OpenClaw" --mega --copies 3 --rounds 2 --json

# Open a webpage and auto-save the video (Douyin/Bilibili etc.)
python scripts/auto_save_browser.py --url "https://v.douyin.com/xxxx" --json

# Login-wall sites (Douyin/Bilibili): attach login cookies for video streams
python scripts/auto_save_browser.py --url "https://v.douyin.com/xxxx" --cookies "D:/cookies.txt" --json
python scripts/auto_save_browser.py --url "https://v.douyin.com/xxxx" --cookies-from-browser chrome --json

# Search, then auto-open the first video result and save it
python scripts/auto_save_browser.py --query "cat videos" --auto --json

# Images only / audio only
python scripts/auto_save_browser.py --query "landscape photos" --auto --media-type image
python scripts/auto_save_browser.py --url "..." --method harvest --media-type audio

# Download files (archives/docs/installers; folder pages batch-download, --zip bundles all)
python scripts/auto_save_browser.py --url "direct file link or page" --json
python scripts/auto_save_browser.py --url "https://.../downloads" --zip

# yt-dlp extras (v1.23.0): full playlists / extract audio / quality cap / global proxy
python scripts/auto_save_browser.py --url "Bilibili collection URL" --playlist --playlist-max 5 --json
python scripts/auto_save_browser.py --url "https://..." --method ytdlp --extract-audio --audio-format mp3 --json
python scripts/auto_save_browser.py --url "https://..." --method ytdlp --quality 720p --json
python scripts/auto_save_browser.py --url "https://..." --proxy "http://127.0.0.1:7890" --json

# Extract article text / novel chapters (auto-merges chapters into one txt)
python scripts/auto_save_browser.py --url "article or chapter-index page" --media-type text

# Local search engine: crawl → index → search
python scripts/own_search.py crawl --url "https://example.com"
python scripts/own_search.py seed --query "OpenClaw" --max-results 5
python scripts/own_search.py search --query "OpenClaw" --json

# Verify captures (real decoded duration + inflation detection)
python scripts/verify_capture.py --dir "downloads/cache/xxx"

# Vision mode (multimodal models): one-shot page screenshot
python scripts/auto_save_browser.py --url "..." --method text --screenshot --model deepseek-v4-flash-vision-exp --json

# Vision mode: operate a page like a human (JSON commands via stdin, screenshots + state via stdout)
python scripts/auto_save_browser.py --url "..." --method vision --model deepseek-v4-flash-vision-exp --json
```

## Vision Mode (for multimodal models, v1.12.0)

Adapts the official `deepseek-v4-flash-vision-exp` multimodal model (released 2026-08-21): gives the model "eyes" and "hands".

| Capability | Usage | Description |
|---|---|---|
| Page screenshots | Add `--screenshot` to any command | Opens page → lazy-load scroll → full-page PNG + screen info; ultra-tall pages auto-segmented (official max edge 8192px) |
| Vision session | `--method vision` | Send JSON commands line-by-line via stdin (click/right_click/dblclick/move/scroll/type/press/focus/**upload/dialog**/elements/tabs/switch_tab/goto/back/forward/reload/wait/screenshot/eval/viewport/shot_policy/quit); each step returns a screenshot + screen state on stdout; v1.23.0 adds **file upload, dialog accept policy, and iframe elements** |
| Screen info | Auto-output each step | Viewport size, full-page size, DPR, mouse coordinates, scroll position — the model computes click coordinates from these |
| Model detection | `--model <name>` | Name contains "vision" = multimodal; outputs `vision_capable` + `api_hint` (official API params, copy-paste into requests) |
| Cost guard | `--max-screenshots` (default 30) / `--shot-detail low` | Each screenshot ≤384 tokens (official cap); auto-stops when limit hit; low = 512×512 budget mode |

**Official parameter basis** (api-docs.deepseek.com/guides/vision): images are tokenized by size, capped at 384 tokens each; formats JPEG/PNG/GIF/WebP (detected from actual content); three input methods — base64 inline (48 MiB body limit), external URL, or Files API; images may only appear in user messages.

## Download Reliability Design (auto_save_browser.py)

`chain` mode tries each method in order and uses the first one that succeeds (v1.13.0: expanded from 5 to 6 routes + cookie retry):

```text
direct → ytdlp → browser → cache → harvest → text   (+ ytdlp-with-cookies retry if cookies were provided)
```

| Scenario | Mechanism |
|---|---|
| Media pages | Real Chromium playback + network sniffing + 206-segment merging + blob/MSE capture + DOM/JSON harvesting |
| Lazy-loaded SPA galleries (Xiaoheihe etc.) | Iterative scroll-harvest: scroll a step → wait for new images to mount → harvest the batch → repeat until no new items (≤30 rounds, 200-file cap); cross-origin CDN images fall back to direct HTTP download when in-page fetch is CORS-blocked |
| Login walls (Douyin/Bilibili) | `--cookies <file>` (Netscape cookies.txt, exported via "Get cookies.txt" extension) or `--cookies-from-browser chrome/edge/firefox` — injected into yt-dlp, browser contexts, cache & harvest routes alike |
| Douyin photo posts (`/note/`) | Auto-rerouted to `harvest` (yt-dlp doesn't support note URLs); output `note_auto_rerouted: true` |
| File pages | Streaming direct download (8MB chunks); folder pages auto-collect ≤50 file links for batch download; filenames restored from Content-Disposition (CJK-safe); v1.23.0 adds **.part resumable downloads** (resume after interruption, idempotent reuse of finished files, rename only on complete EOF) |
| Proxy / manifest (v1.23.0) | `--proxy` plumbing through every exit path (Chromium launch, raw urllib, yt-dlp, share-link resolution); `.manifest.jsonl` ledger records url→file line by line (traceable across runs) |
| "Click to download" → app redirect | `--click-download` 5-level fallback chain: button direct links/scheme decoding → programmatic click + network sniffing (incl. new tabs) → native download events → mobile UA spoofing → page-context fetch |
| App-store funnels | If every "download link" points to an app store, outputs `app_only: true` — honest reporting, no fake results |
| Redirect shells | Dual unwrapping: HTTP 3xx + JS parameter redirects, active piercing (≤3 hops) |
| JS-rendered pages | Adaptive wait: harvests only when body text ≥50 chars or ≥3 media elements, 10s timeout |
| Bad file prevention | ffmpeg real-decode validation after merge; failures/<3s discarded; >30% duration inflation flagged |
| Suspicious sites | `--safe`: process sandbox + mining/executable/popup blocking + on-disk whitelist + 2GB cap |

## Search Quality Design

- **3-tier dedup**: URL normalization → title similarity (≥0.82) → content fingerprint (first 200 chars, ≥0.78)
- **4-level ad filtering**: `--ad-filter none/low/medium/high` (default medium), with subdomain detection and redirect/paid-marker checks
- **Finance intent**: 12 finance keywords trigger a professional finance engine group (EastMoney/Jisilu/Caixin), bypassing paid ads
- **Platform priority**: queries containing platform names (e.g. "douyin") prioritize domain-matched results
- **Error self-healing**: failed rounds/404/empty results automatically retry with different categories or engines

## Optional API Configuration

```powershell
$env:TAVILY_API_KEY = "tvly-..."
$env:BRAVE_API_KEY = "BSA..."
$env:SEARXNG_BASE_URL = "http://127.0.0.1:8080"
```

When set, the corresponding API is preferred, with keyless engines as fallback. Keep keys in environment variables only — never commit them to files.

## Directory Structure

```text
deepseek-web-search-plugin/
├── SKILL.md                 # OpenClaw skill manifest (read by the model)
├── README.md                # English docs (this file, default)
├── README.zh-CN.md          # Chinese docs
├── install_dependencies.py  # One-command dependency installer
├── install_deps.bat         # Windows double-click installer
├── package.json             # Skill metadata
├── requirements.txt         # Dependency list
├── downloads/cache/         # Default cache directory for the auto-save browser
├── index/own_search.db      # Local search engine index (auto-generated)
└── scripts/
    ├── search.py            # Lightweight zero-dependency search (fallback)
    ├── search_browser.py    # Playwright browser search (recommended)
    ├── smart_search.py      # Smart search: intent detection + auto engine switching
    ├── cross_search.py      # Cross-validation / --mega mega search
    ├── search_and_cache.py  # Search + media auto-caching
    ├── own_search.py        # Local standalone search engine
    ├── auto_save_browser.py # Auto-save browser (download core, sole entry point; slimmed to 824 lines in v1.22.0)
    ├── auto_save/           # Download-core module package (split across v1.21.1~v1.22.0)
    │   ├── constants.py     #   Constants: extensions/domain lists/junk filters/safe-mode allowlists/UA pool
    │   ├── ffmpeg.py        #   ffmpeg/ffprobe detection & decode verification
    │   ├── cookies.py       #   Login state: cookie parsing/browser extraction/login rescue
    │   ├── urlrules.py      #   Pure URL/media/security classification functions
    │   ├── browser_base.py  #   Browser infra: launch args/stealth/safe mode
    │   ├── humanize.py      #   Human-like input: Bézier paths/micro-offset presses/normal key intervals
    │   ├── realheadless.py  #   Real-headless: static fingerprint patches + real-Chrome detection
    │   ├── shots.py         #   Screenshots/screen info
    │   ├── vision.py        #   Vision-session protocol (stdin/stdout JSON)
    │   └── routes.py        #   Download routes: browser/cache/harvest/files/text
    ├── searchkit/           # Search module package (split in v1.22.0; shared by light & browser versions)
    │   ├── http.py          #   HTTP utils: UA/CA/GET/POST/result builder
    │   ├── normalize.py     #   URL normalization/dedupe/error-page detection
    │   ├── adfilter.py      #   4-level ad filtering + precision ranking
    │   ├── dispatch.py      #   Engine selection (unified category table + availability filter)
    │   ├── runner.py        #   Subprocess runner (shared by 3 dispatchers)
    │   ├── browser.py       #   Playwright browser engine layer (14 engines)
    │   └── engines/         #   20 lightweight engines (web/dev/academic/community/api)
    └── verify_capture.py    # Capture verification
```

## Security Notes

- Search results and scraped content are treated as untrusted input; no instructions within them are ever executed.
- Scripts only make HTTP search requests and media downloads; no local files are uploaded.
- `--safe` mode for suspicious sites: sandbox isolation + request interception + on-disk whitelist.

## Known Limitations

- **Network environment**: tested entirely on mainland China networks; untested on overseas networks, where some features may not work (see "Network Environment Note" above).
- Bilibili m4s segmented streams and some blob/MSE videos can't be reassembled from browser cache alone; the script auto-falls back to yt-dlp.
- No anti-bot approach is 100% reliable; browser emulation greatly reduces detection but strongly protected sites may still fail.
- App-funnel pages (only app-store redirects, no real files) honestly report `app_only: true` — the site itself offers no web download; this is not a script defect.
- **Vision mode (`--method vision`, headless browser session) is billed per screenshot and costs a nontrivial amount — not recommended for general users**; all other routes (search/download/text) are completely free.
- ⚠️ **NOT recommended: driving Doubao's web UI to write documents with this tool** (tested the hard way!): login is hard, typing keeps hitting login walls, human-verification usually fails, and every attempt burns tokens — just have the AI write files locally instead. P.S. We did eventually log in — but that was us, not you; and even when it works and Doubao replies, the cost is worse than just installing the Doubao app on your phone. It works — it's just not worth it.
- ⚠️ **Douyin web login is effectively unusable via automation — don't force it** (tested the hard way!): ① SMS-code login — phone number/code entry all work, but the big "Login" button just can't be clicked (ironically the tiny corner logout button clicks fine); ② QR login — keeps timing out after scanning. The right way: `--profile --headed` manual login once (then headless forever), or `--login-rescue` to graft your everyday browser's login cookies.

## Development & Testing

- **Development assistant**: code written and maintained by **Zhipu 5.3** (GLM)
- **Testing AIs**: vision-session capabilities cross-tested live with **MiniMax M3** and the **DeepSeek multimodal model** (deepseek-v4-flash-vision-exp)
- **Cost note**: Vision mode (`--method vision`, headless browser session) is billed per screenshot and costs a nontrivial amount — not recommended for general users; all other routes (search/download/text) are completely free

## Changelog

### v1.23.3 (2026-09-14)

All-platform matrix stress round (Bilibili/Kuaishou/Douyin/Weibo/NetEase/Xiaohongshu/WeChat-article/novel-site/GitHub/w3.org across video, image-text, text, music, files): 1 fixed, 1 confirmed-unfixed honestly, limitations recorded as-is.

- **Fix: audio-circuit login-page hijack** — searching "网易云音乐 周杰伦 晴天", the audio round host-matched `music.163.com/login` as the "audio target" (same family as the v1.23.2 video-circuit bug). `_looks_like_item_page` gains audio tokens (song/songDetail/play_detail/sound/album/playlist/program), a query `id=\d` signal (music.163.com/song?id= style item pages), and a login/register veto; the text circuit skips login pages too; `test_routing_offline.py` +8 assertions (suite all green). After the fix the same query honestly returns empty (no song URL existed in results) instead of downloading a login page.
- **Confirmed, unfixed: NetEase song-page direct link (music.163.com/song?id=) hangs** — harvest/chain exceeded 15 minutes with zero stderr output, process idling at near-zero CPU (iframe-rendered page, suspected unbounded wait somewhere). Recorded in the SKILL.md self-heal table (Ctrl+C + switch to `--method ytdlp`); the proper cure is a global `--timeout` watchdog (each chain stage is bounded, their sum is not).
- **Stress matrix (evidence kept in downloads/_stress_v123/)**: Kuaishou video full (27MB mp4 via sogou redirect → yt-dlp); Douyin video full (1.15MB); Weibo full (43 files, request-first refetched mp4s); Bilibili baseline full (28MB); image circuit fell back to Baidu Image and harvested 200 images / 21.5MB (partial; XHS originals need login — documented limitation); w3.org PDF full (UA ladder beats JA3-style Chrome-UA blocking — the v1.22.1 fix works in the field); Journey-to-the-West chapter merge 5/5 chapters into one 106KB txt (chapters-merged); WeChat-article text extraction 16KB (partial).
- **Recorded honestly (not tool bugs)**: arxiv.org unreachable from this network at every layer (connections reset for urllib and yt-dlp alike); yt-dlp.zip asset does not exist (wrong test URL — the tool 404'd honestly and junk→exit-1 semantics held); overseas platforms (YouTube/X) untested (network environment).

### v1.23.2 (2026-09-14)

Stress-test finale: the `--query --auto` full-pipeline stress test caught a **link-picking flaw dating back to v1.22.0** and root-cures it; the skill's quick-pick table gains the new switches.

- **Fix: section pages hijacking link picking** — searching "B站 猫 视频", the platform round selected `t.bilibili.com/index.html` / `bilibili.com/read/home` (section/pseudo homepages) on host match alone, and the whole chain harvested avatar thumbnails on the wrong page (junk). Two platform-agnostic layers: `_is_bare_homepage` now recognizes homepage filenames (index.html/htm, default, home); a new `_looks_like_item_page` gate requires an item-page shape (path with /video/, BV-id, watch keywords, or an ID-like last segment — covers both youtu.be short IDs and numeric IDs), applied to both picking rounds. **Verified live**: the same query now lands on a sogou redirect → yt-dlp resolves the real video BV1GVMszFETr → 2.7MB mp4, quality=full, exit 0.
- **tests**: new `test_routing_offline.py` (18 assertions for bare-homepage/item-page verdicts); suite grows to 5 files.
- Stress matrix (v1.23.1 code + this fix): full suite (5 files), Bilibili `--quality 480p` (full), `--extract-audio mp3` (full), dead-port proxy fast-fail (`WinError 10061` proves proxy reaches yt-dlp), `.manifest.jsonl` ledger on disk, `--query --auto` full pipeline (junk before the fix → full after).

### v1.23.1 (2026-09-14)

Self-review of v1.23.0 on day one (every suspect walked the full verdict → reasons → counter-question → confirm loop): 4 fixed, 2 ruled not-bugs with rationale kept on record.

- **Fix: frame-order assumption** — `page.frames[1:]` implicitly assumed index 0 is the main frame; Playwright only contracts the `main_frame` property, not list order. Now filtered by identity (`fr is not page.main_frame`, 3 sites).
- **Fix: `--proxy` didn't cover the `--query` auto-search step** (while help claimed "every exit path") — counter-question revealed `run_search` already had a `proxy` parameter; all 6 `_search_first_media_url` call sites now pass `proxy=get_proxy()`, so the help text stands.
- **Fix: `_vision_find_el` swallowed Playwright's selector-parse error text** (diagnostics regression) — exception text is preserved into the note again.
- **Fix: `--playlist-max` without `--playlist` was silently ignored** — same class as issue #3 of the project's own v1.12.1 review ("`--safe` accepted but never effective", rated high); a one-shot stderr warning now fires.
- **Ruled not-bugs (on record)**: ① resume lacks ETag/If-Range content validation — strictly better than the old behavior, a full fix needs persisted validators, and media has ffmpeg decode verification as a backstop (documented as a known limitation in the docstring); ② finished file coexisting with `.part` — atomic `replace` plus the already-cached short-circuit make it unreachable in normal flow.
- **Regression**: `tests/run_all.py` all 4 files green; `--playlist-max` warning and download behavior live-tested (count=1); `routing.get_proxy` wiring unit-checked.

### v1.23.0 (2026-09-14)

Capability release: yt-dlp switches + vision-session trio + download-chain proxy/resume/ledger + the project's first real test suite. Zero default-behavior changes (everything is opt-in).

- **yt-dlp switches**: `--playlist` / `--playlist-max N` (download full collections — noplaylist was hardcoded; single-video semantics stay the default); `--extract-audio --audio-format mp3|m4a|...` (audio-only stream saves half the traffic, ffmpeg transcodes); `--quality best|1080p|720p|480p|360p` (resolution cap). Two live-test lessons: the format fallback chain must end in `bestvideo+bestaudio` (DASH-only sites like Bilibili have no progressive single file, so bare `best` never matches); portrait videos' "height" is the long edge (their 480P tier is 480x852), so a `width<=N` alternative is required to hit the same-named tier.
- **Vision-session trio**: ① **Dialogs** — Playwright silently auto-dismisses alert/confirm/prompt by default; the AI never knew a dialog appeared and confirm-based flows were unreachable. Now every dialog is reported via `dialog_events` (still dismissed by default — zero breakage), and `{"action":"dialog","accept":true}` sets a one-shot accept policy (prompt can carry reply text). ② **File upload** — the `upload` command with a 3-step ladder: explicit input selector direct-set > `click_selector` file-chooser interception (expect_file_chooser, the mainstream upload pattern) > auto-find input[type=file] across all frames. ③ **iframes** — elements now annotate cross-frame (child-frame coordinates offset by the iframe's bounding box into main-viewport space, `frame` field marks the source); selector/text locators fall back frame-by-frame when the main frame misses (child-frame bounding_box is officially main-viewport-relative, so coordinate clicks need no conversion).
- **Download-chain additions**: ① `--proxy` plumbed through every exit path (Chromium launch both persistent and one-shot, three raw-urllib sites, yt-dlp, share-link resolution — the download core previously had no proxy support at all); ② **resumable downloads** — files now write to `.part` + `Range: bytes=N-`, resuming after interruption (a 2GB file cut at 90% no longer restarts), renaming only on complete EOF (fixes half-files wearing finished names), with honest handling for no-Range servers and already-cached files; ③ **download ledger** — `.manifest.jsonl` records url→file/size/md5 (<8MB) line by line, traceable across runs.
- **tests/ (the project's first real test directory)**: `python tests/run_all.py` runs everything, pure stdlib with zero new dependencies, 3 files / 28 checks — ytdlp option dict shapes, resume + proxy effectiveness (a local HTTP server with hand-built Range support + a dead-port proxy-must-fail probe), ledger fields, vision command registration.
- **Verified live**: Bilibili `--quality 480p` (13.4MB product) and `--extract-audio mp3` (2.2MB) end to end; `--playlist` on a single video still downloads exactly 1; vision trio 12/12 on a local HTML test page (iframe element annotation, in-iframe click, confirm report + accept, dismiss semantics assertion, both upload moves, filename readback).

### v1.22.1 (2026-08-25)

Fallback-chain activation ("request first, capture later") + 17 fixes from 5-platform stress tests. No usage changes — pure bug fixes plus one paradigm upgrade.

- **New media-fetch paradigm — "request first, capture later" (6-move ladder, feedback-driven, stop on first success, ≤6 total attempts)**: ① tab (in-page fetch with full cookies/referer) → ② desktop (HTTP, desktop UA + referer) → ③ mobile (mobile UA) → ④ bare (no referer) → ⑤ refresh (reload page for a fresh signed URL) → ⑥ fallback round. Feedback-driven: 403 → switch persona; truncated 200 → jump to refresh for a new ticket; 416 → pure GET.
- **Douyin (5)**: segment merger now sorts by Content-Range file offset (out-of-order arrival was corrupting every merge); fMP4 init segment (moov header) merged into its group; byte-identical duplicate segments dropped (login-wall 11×204801B re-sends no longer corrupt files); promo-material domains (douyinstatic/bytednsdoc — an 11MB PC-client installer video!) vetoed at domain level; JSON-escaped URLs (`\/`, `\u002F`) decoded and pseudo-extensions (.image/.awebp) recognized so gallery images stop being missed.
- **Kuaishou (4)**: a complete stream arriving as a single response is now promoted directly (the old "merge needs ≥2 segments" rule was killing whole videos); 206 partial blocks must cover through EOF before promotion; unreadable response bodies (inspector cache evicted) are recorded to the full-refetch ledger instead of silently losing the stream; escaped gallery URLs pre-decoded.
- **Bilibili (4)**: CDN mirror dedupe (path + basename dual gauge, mcdn route prefix normalized — same file was being downloaded 2–3×); content-hash dedupe (byte-identical second copy dropped); yt-dlp product quality-gate fix (a short-circuit `url or path` misjudged 21.5MB files as junk, sending the whole chain re-fetching 188MB); site-asset domain blocked (13MB wallpaper pack).
- **NetEase Music / Xiaohongshu (4)**: yt-dlp progress lines no longer pollute `--json` stdout (`noprogress`); iframe-rendered pages (NetEase g_iframe) now harvested; homepage redirects recognized as downgrades (not follow-through); Xiaohongshu login-wall decoration images blocked (fe-platform.xhscdn).
- **General**: **exit-code semantics — success (real yield) = 0, failure/junk-only = 1** (previously always 0, hosts couldn't retry on failure); quality gate backfilled for files/direct/text routes (a 60MB intact download used to report `quality: null`); Chromium channel preference + hardware video decode disabled + SwiftShader software rendering (root-causes the sandbox false-kill on AI hosts); JSON serialization `default=str` guard (a `set` once crashed output); install_dependencies.py pip detection fix.
- **Stress-test matrix (all passing)**: NetEase Music via ytdlp (full), Bilibili via browser (full — streams + covers, dedupe active), Douyin via chain (full — promo material blocked, exit 0), 60MB file via files (byte-exact match), small exe via files (full).

### v1.22.0 (2026-08-24)

Full modularization refactor (5 batches) + 5-platform stress-test fixes:

- **Batches A/B (download side)**: vision-session protocol split into `auto_save/vision.py` + `shots.py`; download routes split into `auto_save/routes.py` (browser/cache/harvest/files/text); `auto_save_browser.py` slimmed from 4700+ to 1132 lines.
- **Batches C/D (search side)**: `search.py` (961 lines) split into the `searchkit/` package — http/normalize/adfilter/dispatch + engines/ (20 engines in 5 categories); `search_browser.py` (820 lines) merged into searchkit sharing normalization/dedupe/ad-filter/ranking, and the **duplicate engine tables are gone** (light and browser versions now use one unified CATEGORY_ENGINES table, filtered by mode availability at dispatch time).
- **Batch E (dispatcher side)**: the duplicated "pick script → build args → subprocess → parse" logic in smart/cross/own converged into a single `searchkit/runner.py` executor with engine-count-adaptive timeouts (the all-category's 17 engines no longer get killed by a timeout sized for 9).
- **7 real bugs fixed along the way**: arxiv engine's wrong `ns=` parameter name (the academic engine had been broken all along), 3 missing imports in engines/, `--brief` plain-text crash, Chinese precision ranking never working (`\w+` tokenization glued whole Chinese sentences into one token — switched to bigram tokenization).
- **7 stress-test fixes** (live-tested on Douyin/Xiaohongshu/Kuaishou/Xiaoheihe/Qishui Music + two rounds of user reports): ① search picking a platform's bare homepage as a "video link" — now skipped, plus a `_platform_search_url` fallback for 8 platforms; ② engine-indexed platform search pages carrying only partial keywords — now auto-upgraded to full-keyword search pages; ③ yt-dlp running 3 times in chain mode — a `ytdlp_fallback` switch dedupes it inside the chain; ④ harvest saving SVG sprites/login banners/ad images/guide images as "content" — junk-filter rules extended; ⑤ Xiaohongshu search pages asking for images but getting force-routed to the video pipeline by the "video-site veto" — explicit `--media-type` now wins on search/list pages; ⑥ malformed `duration Nones` log line; ⑦ **yt-dlp filename exceeding Windows' 260-char path limit** (Qishui Music's URL params crammed into title/id, all three routes dying with Errno 2 on the `.part` file) — outtmpl truncation + `trim_file_name` hard cap; verified 598 → 97 chars, file writes fine. Round 2 (/note/ posts): ⑧ note reroute was undiagnosable and music-post harvests got dropped — empty/image-only harvests now logged and recorded in attempts as `harvest(note)`, and when the user wants audio/video that harvest can't provide, the chain proceeds to grab the stream and merges the harvest back; ⑨ mojibake fix rolled back (forcing UTF-8 caused mojibake on GBK terminals — Python's locale default is correct); ⑩ exit code 1 identified as an environment-layer false alarm (Chromium hardcodes a debug.log next to its exe; sandbox/AV interception flags the whole command, while main() provably returns 0).
- **Full mode audit fixes (5)** (switch inventory + plumbing check across all 6 entry points): ①searchkit/browser layering inversion (search package imported infra via the download facade → now imports `auto_save.browser_base` directly); ②accompanying infra-copy drift (the fallback `_browser_launch_args` copy missed that same day's `--log-file` fix → unified import source); ③smart_search gained `--ad-filter/--precision/--category` end-to-end passthrough, own_search seed gained `--ad-filter`, runner gained precision/site passthrough; ④`--screenshot --profile` captured login-walled pages as empty shells → profile_dir passthrough
- **Structural cleanup (3 batches, easy → hard, zero logic change)**: batch 1 sunk 9 intent-routing functions into `auto_save/routing.py` (facade 1132 → 824 lines); batch 2 slimmed `searchkit/browser.py` 510 → 257 lines by splitting its 14 browser engines into an `engines_browser/` package (dom/web/dev/academic/alt); batch 3 converged the four duplicated browser-launch templates in routes.py (files/text/harvest/browser) into a single `browser_base._open_page()` — all differences became parameters (profile dir / download trust / self-signed-cert tolerance / random viewport / cookie injection), persistent-context fallback and failure self-cleanup semantics preserved, verified key-by-key equivalent with a fake playwright object (46 checks, all passing).
- **Compatibility contract**: the three facades (auto_save_browser/search/search_browser) remain the sole CLI entry points; every old name stays available via re-imports, so external import paths are unchanged; each batch verified by AST node-by-node diff + runtime acceptance.

### v1.21.1 (2026-08-23)

Download-core modularization refactor (pure structural cleanup, zero functional change):

- **`auto_save_browser.py` split by safety level into the `scripts/auto_save/` package**: batch 1 = constants / ffmpeg / cookies, batch 2 = urlrules (pure URL/media/security classification functions) — the main file slimmed from 4393 to ~4140 lines, all nine routes intact.
- **Compatibility contract**: `auto_save_browser.py` remains the sole CLI entry point and the only module imported externally; every old name stays available via re-imports, so external call paths are unchanged.
- **Pure-move verification**: AST node-by-node diff against the git HEAD original confirms all 29 extracted definitions are logic-identical; 162-case differential test shows old/new outputs identical for the same inputs; `__all__` re-exports added for 51 package-level names; text/direct/files routes verified end-to-end in a real browser, byte-identical to the original.
- Side fix: restored a `List[Path]` type annotation drift from batch 1 (now literally identical to the original).

### v1.21.0 (2026-08-23)

Quick click + click ripple (pre-school-term wrap-up):

- **Quick click**: `{"action":"click"}` with no arguments clicks the **current mouse position** — aim with `move` first, then just send `click`; `{"action":"click","button":"right"}` right-clicks there. The coordinate mode (x/y) and DOM-precise mode (selector/text) are fully preserved — three coexisting modes, chosen per situation.
- **Click ripple feedback**: every click in all three modes draws an **expanding ripple** (white ring, black edge, ~0.5s fade) at the click point — the next screenshot shows exactly where the click landed (a 150ms pause ensures it's captured).
- Full check: all 9 scripts compile, AST parameter-chain check passes; quick/coordinate/DOM modes and the ripple verified live.
- Sporadic updates **possible** within the next week or two (maintainer heading back to school; unscheduled).

### v1.20.0 (2026-08-22)

Three-state virtual cursor (user feedback: a fixed arrow isn't like a real mouse):

- **The cursor now morphs like a real one**: hovering links/buttons → **pointing hand**; hovering input fields → **I-beam text cursor**; elsewhere → **arrow**. Switches automatically by inspecting the element under the pointer via CSS cursor (pointer/grab→hand, text or input/textarea/contenteditable→I-beam, else arrow).
- From a screenshot the AI now knows not just "where the mouse is" but "is the hovered thing **clickable (hand) / typeable (I-beam)**".
- All three shapes white-filled with black outline, hotspot-aligned (arrow/hand tips and I-beam crossbar center = the real mouse coordinate).
- Verified live: link on example.com = HAND, blank area = ARROW, Baidu input = TEXT — all pass.

### v1.19.1 (2026-08-22)

Maintenance release (full audit + author info + project article):

- **Full code audit**: all 9 scripts compile; AST parameter-chain check passes (no unknown args, no edit leftovers); all 8 stealth hookup points verified; 5 routes smoke-tested green. Historical low-severity leftovers (`\\n` log typo / English vision-session notes / concat-failure cleanup) confirmed all fixed — no new bugs found.
- **Author info**: Douyin ID 94636651553 added to SKILL.md / package.json / both READMEs.
- **New [ARTICLE.md](ARTICLE.md)**: the project's story — three iron rules (degradation chains / never trust declared metadata / never fabricate), vision-mode lessons, and the wisdom of not fighting login walls head-on.
- The project pauses updates for a week or two after this release (maintainer rest).

### v1.19.0 (2026-08-22)

Virtual mouse cursor for vision sessions:

- **Virtual mouse cursor (built into vision sessions, no flag needed)**: headless screenshots don't render the OS cursor — the AI previously had to guess "where is the mouse" from `screen.mouse` numbers. Sessions now auto-inject an **enlarged white arrow cursor (34px, black outline, visible on any background)** that follows the mouse in real time (CDP-driven move/click/drag all trigger it). The big white arrow in screenshots IS the current mouse position, consistent with screen.mouse.
- Implementation: injected overlay (pointer-events:none so it never blocks clicks, attached to documentElement so body-clearing pages can't drop it, waits for DOMContentLoaded); enabled only in vision sessions (fixed-position would misplace in full-page screenshots, so the standalone screenshot route skips it).
- Verified live: move(400,300) → cursor translate(398,298) in sync with screen.mouse(400,300), screenshots normal.

### v1.18.0 (2026-08-22)

Login rescue + self-identifying session logs (real-world: Douyin QR confirmed on phone but the web page still refused to log in):

- **New `--login-rescue`**: hard risk-control sites (Douyin etc.) confirm the QR on your phone but refuse to issue a session to an automated browser (CDP detection; fingerprint stealth can't help). The fix: log in to the target site in your everyday browser, then start the session with `--login-rescue` — it walks local chrome→edge→firefox, grafts whichever has target-domain login cookies into the session, and reloads. Result is honestly reported via stderr and the first-state `login_rescue` field; with `--profile` the refreshed session persists.
- **Local debug port auto-disabled for `--profile --headed` manual-login sessions**: the eval-watchdog DevTools port is one of the detection surfaces ByteDance-grade risk control looks at; it's now closed during login windows (the watchdog degrades to disabled — acceptable).
- **Vision session startup banner**: first stderr line shows `version | stealth | profile | headed | idle-watchdog | captcha | debug-port | login_rescue` — logs now prove which build produced them, ending the "an old copy behaves weirdly (e.g. 120s disconnect even with --headed)" mystery.
- Clarified the "120s no login detected" log: that's the idle watchdog counting AI-command gaps, unrelated to page login; new builds relax to 600s under --headed, so a 120s hit means an old copy was running.
- Verified live: banner / honest rescue reporting / JSON field all pass.

### v1.17.0 (2026-08-22)

Three-tier browser stealth, full by default:

- **New `--stealth full|basic|off` (default full)**: playwright-stealth deep-fingerprint patches (plugins/WebGL/UA-Data/sec-ch-ua/hairline, 20+ items) on top of the existing webdriver-erase + UA/viewport/locale disguise — headless fingerprint now closely resembles a real user's browser; `basic` keeps the old half-set; `off` for control testing.
- **Applied everywhere**: search browser + all download/vision routes share `_apply_stealth`; auto-degrades to basic with an stderr notice when the library is missing.
- New dependency `playwright-stealth` added to requirements.txt and the installer.
- **Verified live**: off → plugins=0 (bare), basic → plugins=5 (fake), full → plugins=3 + brands without HeadlessChrome (real-looking); Bing search regression passes.
- **Known limitation (stated honestly)**: Sogou antispider is IP/behavior-level risk control that fingerprint stealth cannot pass — switch engines or warm a `--profile` login (documented in SKILL.md).

### v1.16.0 (2026-08-22)

Four fixes from real-world testing (viewport clipping / new tabs / gallery inconsistency / CJK typing note):

- **Default viewport 800×800 → 1440×900**: 800px height actually clipped page bottoms (Baidu's search button cut in half) — completeness first, sharpness backstopped by the official 384-token cap; use `--viewport 800x800` for max fidelity.
- **New-tab auto-tracking**: clicking target=_blank links (related-searches/hot-topics) now auto-switches the vision session to the new tab (with a note); new `tabs` (list tabs) and `switch_tab` commands. Verified live on Bing: click result → auto-switch → subsequent commands run on the new tab.
- **Gallery harvest waits for images**: each scroll round now polls `img.complete` (up to 3s) before harvesting — fixes inconsistent gallery captures (7 vs 2 images): in-flight images were being skipped or marked failed.
- **CJK typing note**: legacy coordinate `type` may output `???` for CJK — use the v1.15.0 precise typing `{"action":"type","selector":"...","text":"中文"}` (JS-value fallback when the keyboard channel fails); for pure HTTP CJK search use `search.py`.
- Login walls (Doubao/Douyin/DeepSeek web) are site-enforced identity checks the tool does not bypass: `--profile` persistent login (v1.14.0) is the intended path.

### v1.15.0 (2026-08-22)

DOM-precise vision session — click/move/scroll/type no longer rely on guessed pixels:

- **New DOM-precise mode (default recommended)**: `click`/`move`/`scroll` accept `"text"` (locate by on-page text) or `"selector"` (CSS); `type` accepts `"selector"` for the input box. Pipeline: locate → wait visible (3s) → act on bounding-box center (scroll = scroll into view) → verify → auto-retry up to 3 times.
- **Precise typing has read-back verification**: after typing, the input's value/innerText must contain the typed text, otherwise a JS fallback sets the value and dispatches input/change events (contenteditable uses execCommand insertText for a real input event) — React controlled components and ProseMirror honor events, not keystrokes; this fixes "typed text disappears".
- **`"expect_gone": true`** optional click verification (element must disappear — closing popups/dropdowns).
- **Coordinate mode fully preserved** (x/y-only commands behave exactly as before, backward compatible). Regression-tested live: click-by-text, precise typing with verification, element scroll, and coordinate mode all pass.
- Hidden elements fail honestly (wait-visible timeout → 3 retries → clear error) instead of blind-clicking.

### v1.14.2 (2026-08-22)

Captcha detection off by default (real-world feedback: false positives froze all operations):

- **`--captcha-mode` default flipped from `detect` to `off`**: no more per-step detection or `captcha_detected` output — normal pages (carousels/icon classes) used to be falsely flagged, and downstream AI would halt on sight, freezing typing/clicking/dragging. Detection stays available via explicit `--captcha-mode detect`.
- Note: terminal "echo" is standard TTY input display, not tool output (the tool's stdout is a clean JSON state stream); for manual operation use the `--headed` real window.

### v1.14.1 (2026-08-22)

Vision-session robustness (5 tool-level issues from real-world feedback):

- **Fix captcha false positives**: tightened detection selectors — bare `.slider` (image carousels) and `[class*="rotate"]` (Tailwind rotate-\* icons) no longer misreported as slider/rotate captchas; dropped the "向右滑动" keyword (standard carousel hint text). Normal pages used to trigger `captcha_detected`, making downstream AI halt.
- **New `--captcha-mode allow`**: disables captcha detection entirely (for pages that actually work fine while detection keeps misfiring).
- **New `--linger`**: session end (AI disconnect/quit/EOF) no longer closes the browser instantly — `--headed` window is kept for the human to close manually (1h cap); headless gets a 30s grace. A crashed AI script no longer kills the browser session.
- **New `--idle-timeout N`**: configurable idle watchdog (default 120s; auto-relaxed to 600s in `--headed` mode so QR-scan/manual interaction isn't killed; 0=off, only total timeout applies).
- Tolerant cleanup when the persistent-context window is manually closed; captcha handoff guidance updated to `--headed --profile` (login state preserved).
- Note: the stdin/stdout protocol is designed for programmatic pipes; typing manually in a TTY mixes terminal echo (not a bug — documented; manual scenarios should use `--headed`).

### v1.14.0 (2026-08-22)

Persistent login + a batch of security/functional fixes:

- **New `--profile [dir]` persistent browser user-data dir**: log in once, stay logged in across sessions (Doubao/Douyin/Bilibili web and other login-walled sites) — cookies/cache/login state persist like a real browser. First login: `--method vision --profile --headed` (human scans QR), then headless with `--profile`. The dir holds login cookies (gitignored).
- **Fix: `--cookies-from-browser` only worked in the yt-dlp route** — browser/cache/harvest/vision routes silently ignored it (Playwright has no API to read host-browser cookies). Now extracted via yt-dlp's cookie extractor and injected; honest error when unreadable.
- **Fix: browser-route's internal yt-dlp fallback dropped cookies** (explicit `--method browser --cookies` degraded without login state); chain's harvest step also missed passing cookies.
- **Fix: safe-mode 2GB cap holes** — files-route streaming download and click-download never checked size (disk-fill risk); now abort+delete mid-stream over the cap, native downloads re-checked after save.
- **Fix: substring domain matching** (`notdouyin.com` matched `douyin.com`) → exact domain/subdomain matching everywhere.
- **Fix: harvest permanently blacklisted transiently-failed URLs** (one timeout = never retried, lazy galleries lost images) → retry up to 2 times across scroll rounds.
- **Fix: vision session lost safe-mode popup blocking after page rebuild**; startup URL failure no longer wastes screenshot budget on a blank page.
- Search: CJK precision ranking fixed (whole-sentence glue → bigram terms); search_browser now ignores self-signed certs (aligned with other routes); network sniffing skips >1GB responses and same-path-different-query files are no longer wrongly deduped (true duplicates cut by content hash).

### v1.13.1 (2026-08-22)

Lazy-loaded SPA gallery fix (reported: Xiaoheihe gallery pages only yielded ~3 visible thumbnails):

- **Iterative scroll-harvest** replaces the old "jump-to-bottom + fixed 3 scrolls + single harvest": harvest now scrolls step-by-step, waits for newly mounted images, harvests each batch, and repeats until the page bottom yields no new items (or 4 consecutive empty rounds / 30-round cap / 200-file cap). IntersectionObserver-style lazy loading requires images to pass through the viewport — the old logic never triggered them.
- **Cross-origin CDN fallback**: images on CDNs without CORS headers (e.g. `cdn.max-c.com`) used to fail silently in the in-page fetch; now they fall back to a direct script-side HTTP download with browser UA + page Referer.
- **Small-image false-positive fix**: harvest mode no longer discards images <150KB as junk (gallery regulars are often 6–81KB); only icon/logo keyword URLs are filtered.
- Regression: chain direct/ytdlp/browser/cache/harvest/text fallback all pass; Bing image-wall test harvests the full lazy grid (200 files).

### v1.13.0 (2026-08-22)

Login-wall downloads + bigger fallback chain:

- **New: `--cookies <file>` / `--cookies-from-browser chrome|edge|firefox`** — attach login state for Douyin/Bilibili-style paywall/login sites. Netscape cookies.txt (exported via the "Get cookies.txt" browser extension) or read directly from a locally logged-in browser. Injected into every route: yt-dlp (`cookiefile`/`cookiesfrombrowser`), browser & cache contexts (`add_cookies`), harvest, and the note-reroute.
- **chain fallback expanded 5 → 6 routes**: `direct → ytdlp → browser → cache → harvest → text`; each failed step automatically moves to the next, first success returns immediately; per-step outcome recorded in the `attempts` array; a single crashed route (page won't open, Playwright missing) no longer kills the chain. With cookies provided and everything failed, an extra `ytdlp+cookies` retry fires as the last resort.
- **Douyin photo posts (`/note/`) auto-reroute**: yt-dlp reports Unsupported URL on note links — now auto-detected and rerouted to `harvest` for the full-resolution image set (`note_auto_rerouted: true`); if harvest comes back empty, chain continues instead of failing.
- `own_search.py download` now passes through `--method` / `--cookies` / `--cookies-from-browser`.

### v1.12.6 (2026-08-22)

Repo sync fix:

- **Fixed: default branch was stale.** Releases were pushed to `master` while GitHub's default branch `main` still showed v1.12.3 — `main` is now fast-forwarded to the latest and `master` removed, single-branch from now on.
- Mascot moved from `.github/` to `assets/` for reliable README image rendering on GitHub (hidden dot-folders render inconsistently).

### v1.12.5 (2026-08-22)

Vision session robustness + repository polish:

- Vision session: `--method vision` startup now includes `vision_capable` and `model` fields in the first state line (AI can immediately detect whether it supports vision).
- Vision session: `eval` instruction gets a 10s deadlock watchdog — if user-supplied JS contains `while(true){}` or similar hang, the DevTools HTTP `/json/close` endpoint kills the page and the session is rebuilt automatically (no more permanent session freeze).
- Bug fix: `own_search.py download` and `own_search.py seed` now have subprocess timeouts (1800s / 300s) so a stuck downstream no longer freezes the parent.
- Repo: added project mascot (now at `assets/mascot.png`), embedded in both README pages.

### v1.12.4 (2026-08-22)

Vision session overhaul + 12 critical bug fixes. Also ships the previously unreleased v1.12.2~v1.12.3 internal iterations (`focus` action with CSS selectors, `elements` element annotation, captcha detection reporting).
- Data-loss guard: `verify_capture.py --clean` refuses to delete "broken" media when ffmpeg is missing (unverifiable ≠ broken).
- Crash fix: `search_and_cache.py` subprocess timeouts no longer crash the whole script (returns JSON error instead); cache timeout raised to 300s.
- Security fix: `own_search.py download --safe` now actually passes `--safe` to the underlying browser.
- Search robustness: smart_search browser timeout 90s→240s; cross_search mega timeout scales with engine count and reports `timed_out_copies` instead of silently returning empty; URL dedup now keeps business-meaningful query params (`v/id/tid`…, e.g. different YouTube videos no longer collapse into one).
- UX: vision session messages unified to Chinese; `--query --auto` now falls back to the chain route like `--url` mode; log newline typo fixed.

## License

MIT
