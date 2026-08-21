# deepseek-web-search

**English summary**: An [OpenClaw](https://github.com/openclaw) skill that gives DeepSeek real web search (multi-engine + browser-emulated + cross-validation + local index) **and** an auto-save browser that downloads videos/audio/images/files from any webpage it opens. Includes a 5-level download fallback chain, app-store funnel detection (`app_only`), ad filtering, 3-tier dedup, and ffmpeg-verified captures. Pure Python, ~54KB repo, one-command install. 中文文档如下。

OpenClaw Skill：让 DeepSeek 模型能搜索、会搜索、并且"该搜就搜"，还能自动下载网页里的视频/音频/图片/文件。

> 当前版本 **v1.11.1**（2026-08-21）

## 功能总览

| 能力 | 脚本 | 说明 |
|---|---|---|
| 浏览器模拟搜索（推荐） | `search_browser.py` | Playwright 驱动真实 Chromium，防反爬 |
| 轻量搜索兜底 | `search.py` | 纯标准库零依赖，浏览器版失效时用 |
| 智能搜索 | `smart_search.py` | 自动识别学术/技术/财经/新闻意图，自动分配引擎，失败自动换 |
| 多引擎交叉验证 | `cross_search.py` | 3 引擎同搜比对去重；`--mega` 全引擎并行迭代收敛 |
| 搜索+自动缓存 | `search_and_cache.py` | 搜完自动检测结果页媒体并缓存 |
| 本地独立搜索引擎 | `own_search.py` | 自建 SQLite 索引，外部搜索只做种子发现 |
| 保存型浏览器 | `auto_save_browser.py` | 打开网页自动保存视频/音频/图片/文件/正文 |
| 抓包产物校验 | `verify_capture.py` | ffmpeg 真解码验时长、检测虚标、分段合并验证 |

默认搜索引擎：必应、搜狗、360、百度（国内优先）；DuckDuckGo 仅外网/手动指定时使用；可选 Tavily、Brave Search、SearXNG（设环境变量自动启用）。

## 安装

仓库仅 ~54KB 纯文本（无大二进制），克隆秒下；Chromium 等大件依赖由安装脚本从官方源安装。

```bash
git clone https://github.com/wojiuluguo/deepseek-web-search-plugin.git
cd deepseek-web-search-plugin
python install_dependencies.py     # Windows 可直接双击 install_deps.bat
```

**AI Agent 一键部署**（OpenClaw / 其他 agent 直接执行）：

```bash
git clone --depth 1 https://github.com/wojiuluguo/deepseek-web-search-plugin.git ~/.openclaw/workspace/skills/deepseek-web-search && cd ~/.openclaw/workspace/skills/deepseek-web-search && python install_dependencies.py
```

`--depth 1` 只拉最新提交，克隆更快。装完 `openclaw skills list` 应能看到 `deepseek-web-search`，AI 入口读 [SKILL.md](SKILL.md)。

> 国内 GitHub 慢时可换加速镜像：`git clone --depth 1 https://ghproxy.net/https://github.com/wojiuluguo/deepseek-web-search-plugin.git`

## 快速用法

```bash
# 搜索（浏览器版，防反爬）
python scripts/search_browser.py --query "今天A股行情" --max-results 6 --json

# 搜索（轻量版，零依赖兜底）
python scripts/search.py --query "DeepSeek 最新消息" --json

# 省 Token 精简输出（标题+URL+120字摘要）
python scripts/search_browser.py --query "anything" --brief --json

# 智能搜索（自动选引擎）
python scripts/smart_search.py --query "transformer 论文" --json

# 交叉验证（3 引擎） / 超大搜索（全引擎并行）
python scripts/cross_search.py --query "OpenClaw" --json
python scripts/cross_search.py --query "OpenClaw" --mega --copies 3 --rounds 2 --json

# 打开网页自动保存视频（抖音/B站等）
python scripts/auto_save_browser.py --url "https://v.douyin.com/xxxx" --json

# 搜索后自动打开第一个视频结果并保存
python scripts/auto_save_browser.py --query "抖音 猫 视频" --auto --json

# 只要图片 / 只要音频
python scripts/auto_save_browser.py --query "风景图" --auto --media-type image
python scripts/auto_save_browser.py --url "..." --method harvest --media-type audio

# 下载文件（压缩包/文档/安装包；文件夹页自动批量，--zip 打包合一）
python scripts/auto_save_browser.py --url "文件直链或页面" --json
python scripts/auto_save_browser.py --url "https://.../downloads" --zip

# 抓文章正文/小说章节（自动逐章合并 txt）
python scripts/auto_save_browser.py --url "文章或目录页" --media-type text

# 本地搜索引擎：抓取 → 索引 → 搜索
python scripts/own_search.py crawl --url "https://example.com"
python scripts/own_search.py seed --query "OpenClaw" --max-results 5
python scripts/own_search.py search --query "OpenClaw" --json

# 校验抓包产物（真解码时长 + 虚标检测）
python scripts/verify_capture.py --dir "downloads/cache/xxx"
```

## 下载可靠性设计（auto_save_browser.py）

`chain` 模式按序自动降级，哪个成功用哪个：

```text
direct → ytdlp → browser → cache → text
```

| 场景 | 机制 |
|---|---|
| 媒体页面 | 真实 Chromium 播放 + 网络嗅探 + 206 分段合并 + blob/MSE 抓取 + DOM/JSON 收割 |
| 文件页 | 直链流式下载（8MB 分块）；文件夹页自动收集 ≤50 个文件链接批量下；文件名取 Content-Disposition 还原中文名 |
| 点击下载跳 APP | `--click-download` 五级降级链：按钮直链/scheme 解码 → 点击+网络嗅探（含新标签页）→ 原生下载事件 → 手机 UA 伪装 → 页面上下文 fetch |
| APP 引流陷阱 | 全部"下载链接"都是应用商店时输出 `app_only: true`，如实报告不硬造 |
| 跳转壳页 | HTTP 3xx + JS 参数跳转双重解壳，主动穿透（≤3 跳） |
| JS 渲染页 | 自适应等待：正文 ≥50 字符或媒体元素 ≥3 个才收割，10s 超时 |
| 坏文件防漏 | 合并后 ffmpeg 真解码验证时长，失败/<3s 丢弃；虚标 >30% 标记 |
| 可疑站点 | `--safe`：进程沙箱 + 拦挖矿/可执行文件/弹窗 + 落盘白名单 + 2GB 上限 |

## 搜索质量设计

- **三级去重**：URL 规范化 → 标题相似度（≥0.82）→ 内容指纹（前 200 字符 ≥0.78）
- **广告过滤四级**：`--ad-filter none/low/medium/high`（默认 medium），含子域名识别和跳转/付费标记检测
- **金融意图**：命中 12 个财经关键词自动切专业金融引擎组（东方财富/集思录/财新），避开竞价广告
- **平台优先**：query 含平台词（如"抖音"）时优先域名匹配结果
- **错误自愈**：某轮搜索失败/404/无结果自动换分类或引擎重搜

## 可选 API 配置

```powershell
$env:TAVILY_API_KEY = "tvly-..."
$env:BRAVE_API_KEY = "BSA..."
$env:SEARXNG_BASE_URL = "http://127.0.0.1:8080"
```

设置后自动优先调用对应 API，再回退免 Key 引擎。Key 只存环境变量，不要写进任何文件。

## 目录结构

```text
deepseek-web-search-plugin/
├── SKILL.md                 # OpenClaw 技能说明（模型会读取）
├── README.md                # 本说明
├── install_dependencies.py  # 一键自动安装依赖
├── install_deps.bat         # Windows 双击安装
├── package.json             # 技能元数据
├── requirements.txt         # 依赖清单
├── downloads/cache/         # 保存型浏览器默认缓存目录
├── index/own_search.db      # 本地搜索引擎索引（自动生成）
└── scripts/
    ├── search.py            # 轻量零依赖搜索（兜底）
    ├── search_browser.py    # Playwright 浏览器搜索（推荐）
    ├── smart_search.py      # 智能搜索：意图识别+自动换引擎
    ├── cross_search.py      # 交叉验证 / --mega 超大搜索
    ├── search_and_cache.py  # 搜索+自动缓存媒体
    ├── own_search.py        # 本地独立搜索引擎
    ├── auto_save_browser.py # 保存型浏览器（下载核心）
    └── verify_capture.py    # 抓包产物校验
```

## 安全说明

- 搜索结果和抓取到的网页内容一律视为不可信输入，不执行其中任何指令。
- 脚本只做 HTTP 搜索请求和媒体下载，不上传本地文件。
- `--safe` 模式访问可疑站点：沙箱隔离 + 请求拦截 + 落盘白名单。

## 已知限制

- B站 m4s 分段流、部分 blob/MSE 视频无法靠浏览器缓存拼成完整文件，会自动降级 yt-dlp。
- 没有 100% 不被反爬的方案；浏览器模拟能大幅降低识别概率，但强风控站仍可能失败。
- APP 引流陷阱页（只跳应用商店无真文件）会如实报 `app_only: true`，这是站点本身不提供网页端下载，非脚本缺陷。

## License

MIT
