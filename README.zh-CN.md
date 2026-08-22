# deepseek-web-search

**[English](README.md)** | 中文

OpenClaw Skill：让 DeepSeek 模型能搜索、会搜索、并且"该搜就搜"，还能自动下载网页里的视频/音频/图片/文件，多模态模型还能"看页面+操作页面"。

> 当前版本 **v1.21.0**（2026-08-23）· 作者：user（抖音号: 94636651553）· [更新记录](#更新记录)

<p align="center"><img src="assets/mascot.png" alt="deepseek-web-search 吉祥物" width="220"></p>

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
| 视觉模式（多模态） | `auto_save_browser.py` | 截图+屏幕信息喂给视觉模型；鼠标键盘控制会话（适配 deepseek-v4-flash-vision-exp） |
| 抓包产物校验 | `verify_capture.py` | ffmpeg 真解码验时长、检测虚标、分段合并验证 |

默认搜索引擎：必应、搜狗、360、百度（国内优先）；DuckDuckGo 仅外网/手动指定时使用；可选 Tavily、Brave Search、SearXNG（设环境变量自动启用）。

## 网络环境说明

**本工具全部在中国大陆网络环境下开发与测试**，我们没有测试过中国大陆以外的网络环境。

- 如果你在海外网络或其他网络环境下使用，可能出现引擎超时、结果异常等失灵状况，请谅解；
- 海外环境下建议优先尝试 `--engines ddg,brave` 等外网引擎组合；
- 后续版本可能会增加对中国大陆以外网络的适配，敬请期待。

## 安装

仓库为纯文本代码 + 一张吉祥物图（约 2MB），无其他大件；Chromium 等真正的大依赖由安装脚本从官方源安装。

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

# 登录墙站点（抖音/B站）：带登录 cookie 才放行视频流
python scripts/auto_save_browser.py --url "https://v.douyin.com/xxxx" --cookies "D:/cookies.txt" --json
python scripts/auto_save_browser.py --url "https://v.douyin.com/xxxx" --cookies-from-browser chrome --json

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

# 视觉模式（多模态模型专用）：一次性看页面
python scripts/auto_save_browser.py --url "..." --method text --screenshot --model deepseek-v4-flash-vision-exp --json

# 视觉模式：像人一样看着屏幕操作页面（stdin 逐行 JSON 指令，stdout 收截图+状态）
python scripts/auto_save_browser.py --url "..." --method vision --model deepseek-v4-flash-vision-exp --json
```

## 视觉模式（多模态模型适配，v1.12.0）

适配官方 `deepseek-v4-flash-vision-exp` 多模态模型（发布于 2026-08-21）：给模型一双"眼睛"和一双"手"。

| 能力 | 用法 | 说明 |
|---|---|---|
| 页面截图 | 任意命令加 `--screenshot` | 打开页面→懒加载滚动→整页截图(PNG)+屏幕信息；超长页自动分段（官方单图最长边 8192px） |
| 视觉会话 | `--method vision` | stdin 逐行发 JSON 指令（click/right_click/dblclick/move/scroll/type/press/goto/back/forward/reload/wait/screenshot/eval/quit），stdout 每步返回截图+屏幕状态 |
| 屏幕信息 | 每步自动输出 | 视口尺寸、整页尺寸、DPR、鼠标坐标、滚动位置——模型据此算点击坐标 |
| 模型检测 | `--model <模型名>` | 名称含 vision = 多模态，输出 `vision_capable` + `api_hint`（官方 API 参数，照抄拼请求） |
| 成本防护 | `--max-screenshots`（默认 30）/ `--shot-detail low` | 每张截图 ≤384 token（官方封顶），超限自动停截图；low=512×512 省钱模式 |

**官方参数依据**（api-docs.deepseek.com/guides/vision）：图片按尺寸换算 token，单张封顶 384；格式 JPEG/PNG/GIF/WebP（按实际内容判断）；base64 内联（48MiB 请求体）/ 外部 URL / Files API 三种传入；图片只能放 user 消息。

## 下载可靠性设计（auto_save_browser.py）

`chain` 模式按序自动降级，哪个成功用哪个（v1.13.0 扩容：5 路 → 6 路 + cookie 复试）：

```text
direct → ytdlp → browser → cache → harvest → text   （带了 cookie 且全链失败时追加 ytdlp+cookies 复试）
```

| 场景 | 机制 |
|---|---|
| 媒体页面 | 真实 Chromium 播放 + 网络嗅探 + 206 分段合并 + blob/MSE 抓取 + DOM/JSON 收割 |
| SPA 懒加载图集（小黑盒等） | 迭代滚动收割：逐段滚→等新图挂载→收割本轮→循环到无新增（≤30 轮、200 张封顶）；跨域 CDN 图被 CORS 拦时自动降级脚本直连 |
| 登录墙（抖音/B站） | `--cookies <文件>`（Netscape cookies.txt，"Get cookies.txt" 扩展导出）或 `--cookies-from-browser chrome/edge/firefox`（直接读本机浏览器登录态）——yt-dlp、浏览器、cache、harvest 全路线生效 |
| 抖音图文帖（`/note/`） | 自动转 harvest 收割图集原图（yt-dlp 不支持 note URL），输出 `note_auto_rerouted: true` |
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
├── README.md                # 英文说明（默认）
├── README.zh-CN.md          # 中文说明（本文件）
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

- **网络环境**：全部在中国大陆网络环境下测试，未测试过海外网络环境，海外使用可能失灵（详见上方"网络环境说明"）。
- B站 m4s 分段流、部分 blob/MSE 视频无法靠浏览器缓存拼成完整文件，会自动降级 yt-dlp。
- 没有 100% 不被反爬的方案；浏览器模拟能大幅降低识别概率，但强风控站仍可能失败。
- APP 引流陷阱页（只跳应用商店无真文件）会如实报 `app_only: true`，这是站点本身不提供网页端下载，非脚本缺陷。
- **视觉模式（`--method vision` 无头浏览器会话）按截图付费，消费金额较大，一般用户不推荐使用**；搜索/下载/抓正文等其他路线全部免费。

## 更新记录

### v1.21.0（2026-08-23）

快捷点击 + 点击涟漪（开学前收尾版）：

- **新增快捷点击**：`{"action":"click"}` 不带任何参数 = 直接点**当前鼠标位置**——先 `move` 瞄准再发 `click`，不用重复报坐标；`{"action":"click","button":"right"}` = 在当前位置右键。原坐标模式（x/y）与 DOM 精准模式（selector/text）完全保留，三套并存 AI 按场景自选
- **新增点击涟漪视觉反馈**：三种模式的每次点击都会在点击位置画一圈**扩散涟漪**（白圈黑边，约 0.5s 淡出）——下一张截图直接看到"刚才点在哪"，确认点击生效（截图带 150ms 停留确保拍到）
- 全面检查：9 脚本编译全过、AST 参数链检查通过、快捷/坐标/DOM 三模式及涟漪实测通过
- 后续一两周内**可能**有零星更新（维护者临近开学，不定期）

### v1.20.0（2026-08-22）

虚拟鼠标三形态（用户反馈：固定箭头不像真鼠标）：

- **指针会变形了，跟真鼠标一样**：悬停链接/按钮 → **手指**；悬停输入框 → **I 型文本光标**；其他位置 → **箭头**。每步检测鼠标下元素的 CSS cursor 自动切换（pointer/grab→手、text 或 input/textarea/contenteditable→I 光标、其余→箭头）
- AI 看截图不只知"鼠标在哪"，还知"悬停的东西**能不能点（手指）/能不能输入（I 光标）**"
- 三种形态均白底黑描边 + 热点对齐（箭头/手指尖端、I 光标横杆中心 = 真实鼠标坐标）
- 实测：example.com 链接上=HAND、空白=ARROW、百度输入框=TEXT，三态全过

### v1.19.1（2026-08-22）

维护版（全面审查 + 作者信息 + 项目文章）：

- **全面代码审查**：9 脚本编译全过、AST 参数链检查全过（无未知参数/无编辑残留）、8 处伪装接入点核对、5 条路线运行时冒烟全绿；历史遗留低危项（`\\n` 日志笔误/视觉会话英文提示/concat 失败清理）确认已全部修复，无新 bug
- **作者信息**：抖音号 94636651553 写入 SKILL.md / package.json / 双语 README
- **新增 [ARTICLE.md](ARTICLE.md)**：项目文章——三条铁律（降级链/不信任标称数据/绝不造假）、视觉模式踩坑记、登录墙的不打智慧
- 本版后项目暂停更新一两周（维护者休整）

### v1.19.0（2026-08-22）

视觉会话虚拟鼠标指针：

- **新增虚拟鼠标指针（视觉会话自带，无需参数）**：无头截图不渲染系统光标，AI 此前只能靠 `screen.mouse` 数字坐标猜"鼠标在哪"。现在会话自动注入一个**放大的白色箭头指针（34px，黑描边，任何底色都看得清）**，实时跟随鼠标（CDP 驱动的 move/click/drag 都会触发），截图里直接可见——白色大箭头 = 鼠标当前位置，与 screen.mouse 坐标一致
- 实现：注入式覆盖层（pointer-events:none 不挡点击、挂 documentElement 页面清 body 不丢、DOMContentLoaded 前自动等待）；仅视觉会话启用（整页截图的 fixed 定位会错位，独立截图线不注）
- 实测：move(400,300) → 指针 translate(398,298) 与 screen.mouse(400,300) 同步，截图正常

### v1.18.0（2026-08-22）

登录兜底 + 会话日志自证（实测：抖音扫码手机确认成功但网页仍拒登录）：

- **新增 `--login-rescue` 登录兜底**：强风控站（抖音等）对自动化环境扫码会"手机确认了但服务端拒发 session"（检测 CDP 痕迹，指纹伪装救不了）。正解：人肉在自己平时的浏览器登录目标站，工具加 `--login-rescue` 开会——自动遍历本机 chrome→edge→firefox，谁有目标域登录 cookie 就接种进当前会话并刷新；结果在 stderr 与首屏 `login_rescue` 字段如实报告；配 `--profile` 接种后的新 session 会持久化
- **`--profile --headed` 人肉登录场景自动关本地调试口**：eval 看门狗的 DevTools 调试口是字节级风控的检测面之一，登录窗口期自动收敛（看门狗随之退化为不启用，可接受）
- **视觉会话启动横幅**：stderr 首行输出 `版本 | stealth | profile | headed | idle看门狗 | captcha | 调试口 | login_rescue`——日志自证身份，杜绝"老副本跑出诡异行为（如 --headed 仍 120s 断线）查半天"
- 澄清"120s 未检测登录"日志：那是空闲看门狗（数的是 AI 发指令的间隔，与页面登录无关）；--headed 下新副本自动放宽到 600s，仍打 120s 的一定是老副本
- 实测：横幅/兜底如实报告/JSON 字段透出全通过

### v1.17.0（2026-08-22）

浏览器伪装三档可选，默认全套：

- **新增 `--stealth full|basic|off`（默认 full 全套）**：接入 playwright-stealth 深层指纹补丁（plugins/WebGL/UA-Data/sec-ch-ua/hairline 等 20+ 项），配合原有 webdriver 抹除 + UA/视口/locale 伪装——无头浏览器指纹显著接近真人浏览器；`basic` 保留原半套；`off` 裸奔对照
- **全线接入**：搜索浏览器（search_browser）+ 全部下载/视觉路线（browser/cache/harvest/files/text/vision/screenshot）统一走 `_apply_stealth`；库未安装自动降级 basic 并 stderr 告知，不硬崩
- 新依赖 `playwright-stealth` 已进 requirements.txt 与一键安装脚本
- **实测验证**：off 档 plugins=0（裸奔）/ basic 档 plugins=5（假插件）/ full 档 plugins=3 + brands 无 HeadlessChrome（真实指纹）；必应搜索回归正常
- **已知限制（如实声明）**：搜狗 antispider 属 IP/行为层风控，指纹伪装无法通过——换引擎或 `--profile` 养登录态（已写进 SKILL.md 错误自愈表）

### v1.16.0（2026-08-22）

实测反馈四连修（视口裁切/新标签页/图集忽多忽少/中文输入备忘）：

- **默认视口 800×800 → 1440×900**：实测 800 高度裁掉页面底部（百度"百度一下"按钮被裁半）——完整性优先，清晰度由官方 384 token 封顶兜底；极致清晰可 `--viewport 800x800` 指定
- **新标签页自动跟踪**：点"相关搜索/热搜"等 target=_blank 链接开了新标签时，视觉会话**自动切到新标签**（note 告知），截图/操作都落在新标签；新增 `tabs`（标签清单）/ `switch_tab`（手动切换）指令。必真实测：点必应结果→自动切换→后续指令在新标签执行
- **图集收割加"等图加载完"**：每轮收割前轮询 `img.complete`（最多 3s）——治小黑盒图集"忽多忽少"（7 张/2 张）：此前部分图还在 in-flight 就收割，漏收或误记失败
- **中文输入备忘**：原坐标 type 对中文可能输出 `???`——用 v1.15.0 精准输入 `{"action":"type","selector":"...","text":"中文"}`（键盘通道失败自动 JS 设值兜底，中文可靠）；纯 HTTP 搜中文走 `search.py`
- 登录墙（豆包/抖音/DeepSeek 网页）为站点强制身份验证，工具不绕：`--profile` 持久登录（v1.14.0）是正解

### v1.15.0（2026-08-22）

视觉会话 DOM 精准化——点击/移动/滚动/输入不再靠猜像素：

- **新增 DOM 精准模式（默认推荐）**：`click`/`move`/`scroll` 支持 `"text"`（按页面文字找元素）或 `"selector"`（CSS 选择器）定位，`type` 支持 `"selector"` 定位输入框。执行链：定位元素 → 等可见(3s) → 取包围盒中心执行（scroll=滚进视口）→ 验证 → 失败自动重试（最多 3 次）
- **精准输入自带回读验证**：输完回读输入框内容，不含所输文字就 JS 设值兜底（input/textarea 设 value+补发 input/change 事件；富文本编辑器 execCommand insertText 触发真实 input）——React 受控组件/ProseMirror 认事件不认按键，专治"输入后文字消失"
- **`"expect_gone": true` 可选点击验证**：要求点击后元素消失（关弹窗/关下拉类场景）
- **原坐标模式完全保留**（只给 x/y 走老路径，向后兼容，AI 按场景自选）；实测回归：按文字点击"百度一下"、精准输入+回读验证、元素滚动、坐标模式全过
- 隐藏元素如实报错不硬点（等可见超时 → 重试 3 次 → 明确失败原因）

### v1.14.2（2026-08-22）

验证码检测默认关闭（用户实测：误报导致操作卡死）：

- **`--captcha-mode` 默认从 detect 改为 off**：不再每步检测、不再输出 `captcha_detected`——历史行为里普通页面（轮播图/图标类）被误报验证码，下游 AI 一见就停手，输入/点击/拖拽全卡死。现在默认一路畅通；确需检测时显式 `--captcha-mode detect`
- 说明：终端"回声"是 TTY 对输入的标准回显，不是工具输出（工具 stdout 为纯 JSON 状态流）；手动操作请用 `--headed` 真窗口

### v1.14.1（2026-08-22）

视觉会话健壮性（用户实测反馈的 5 个纯工具问题）：

- **修复验证码误报**：收紧检测选择器——裸 `.slider`（轮播图）与 `[class*="rotate"]`（Tailwind rotate-\* 图标）不再被误判为滑块/旋转验证码；文案关键词去掉"向右滑动"（轮播图标准指示文案）。此前普通页被误报 `captcha_detected`，下游 AI 一见就停手
- **新增 `--captcha-mode allow`**：整体关掉验证码检测（页面实际能操作而检测误报干扰时用）
- **新增 `--linger`**：会话结束（AI 断线/quit/EOF）不立即关浏览器——`--headed` 窗口保留给人看完手动关（上限 1h），无头保留 30s 自退。AI 脚本崩了浏览器现场不再跟着消失
- **新增 `--idle-timeout N`**：空闲看门狗可配置（默认 120s；`--headed` 有人在场自动放宽到 600s 防扫码/人肉操作被误杀；0=关闭只受 `--vision-timeout` 约束）
- 持久化上下文的窗口被手动关闭后清理加了容错；验证码人工接管指引更新为 `--headed --profile`（登录态保留）
- 说明：stdin/stdout 协议为程序管道设计，TTY 手敲会混终端回声（非 bug，文档已注明手动场景用 `--headed`）

### v1.14.0（2026-08-22）

登录持久化 + 一批安全/功能修复：

- **新增 `--profile [目录]` 持久化浏览器用户目录**：登录一次以后免登录（豆包/抖音/B站网页版等登录墙站点），cookie/缓存/登录态跨会话保留，等同真实浏览器。首次 `--method vision --profile --headed` 人肉登录，之后无头免登录。目录含登录 cookie，已 gitignore。
- **修复：`--cookies-from-browser` 此前只在 yt-dlp 路线生效**——浏览器/cache/harvest/vision 路线静默无视该参数（Playwright 没有读本机浏览器的 API）。现在借道 yt-dlp 提取器读取并注入；读不到（浏览器未登录/Chrome 新版加密）如实报错。
- **修复：浏览器路线内部 yt-dlp 降级丢 cookie**（显式 `--method browser --cookies` 时降级不带登录态必败）；chain 的 harvest 环节同样漏传 cookie。
- **修复：安全模式 2GB 上限漏洞**——files 直链流式下载与点击下载路线此前不查大小，可被写满磁盘；现在流式过程超限即中断删除、原生下载落盘后复核。
- **修复：域名匹配子串误判**（`notdouyin.com` 能命中 `douyin.com` 类前缀伪造）→ 全部改精确域名/子域匹配。
- **修复：harvest 瞬时失败永久拉黑**（URL 一次超时后永久跳过，迭代滚动收割漏图）→ 允许跨轮重试最多 2 次。
- **修复：视觉会话重建页面后安全模式弹窗拦截丢失**；启动 URL 失败不再浪费截图预算拍空白页。
- 搜索增强：中文 query 精准度排序此前因整句黏词失效 → 中文二元组分词；search_browser 忽略自签证书（与其他路线对齐）；网络嗅探跳过 >1GB 超大响应防内存打爆、同路径不同 query 的不同文件不再被误去重（真重复靠字节指纹砍）。

### v1.13.1（2026-08-22）

SPA 懒加载图集修复（用户反馈：小黑盒图集只抓到 3 张可见缩略图）：

- **迭代滚动收割**替换旧"跳到底+固定滚 3 次+一次性收割"：harvest 路线现在逐段滚动→等新图挂载→收割本轮新图→循环，直到滚到底无新增（或连续 4 轮空 / 30 轮上限 / 200 张封顶）。IntersectionObserver 型懒加载必须让图片逐段经过视口，旧逻辑根本触发不了。
- **跨域 CDN 降级**：无 CORS 头的 CDN 图（如 `cdn.max-c.com`）此前在页面 fetch 里静默失败；现在自动降级脚本侧直连（带浏览器 UA + 页面 Referer）。
- **小图误判修复**：图集收割不再把 <150KB 的图当垃圾（图集正片常在 6–81KB）；只按 icon/logo 关键词滤真图标。
- 回归：chain 六路兜底全过；Bing 图墙实测收满整个懒加载网格（200 张）。

### v1.13.0（2026-08-22）

登录墙下载 + 兜底链扩容：

- **新增 `--cookies <文件>` / `--cookies-from-browser chrome|edge|firefox`**：抖音/B站类登录墙站点带登录态下载。支持 Netscape cookies.txt（"Get cookies.txt" 浏览器扩展导出）或直接读本机已登录的浏览器。全线生效：yt-dlp（`cookiefile`/`cookiesfrombrowser`）、浏览器与 cache 上下文（`add_cookies` 注入）、harvest、note 转路。
- **chain 兜底链扩容 5 → 6 路**：`direct → ytdlp → browser → cache → harvest → text`，一步失败自动换下一个，首个成功立即返回；每步成败记录在 `attempts` 数组；单路崩溃（页面打不开/缺 Playwright）不再拖死整链。带了 cookie 且全链失败时，最后追加 `ytdlp+cookies` 复试一搏。
- **抖音图文帖（`/note/`）自动转路**：yt-dlp 对 note URL 直接报 Unsupported URL——现在自动识别并转 harvest 收割图集原图（输出 `note_auto_rerouted: true`）；harvest 也空时 chain 继续走兜底链不中断。
- `own_search.py download` 透传 `--method` / `--cookies` / `--cookies-from-browser`。

### v1.12.6（2026-08-22）

仓库同步修复：

- **修复：默认分支落后**。此前发版推到 `master`，而 GitHub 默认分支 `main` 还停在 v1.12.3——现在 `main` 已快进到最新，`master` 已删除，今后只维护单一分支
- 吉祥物从 `.github/` 移到 `assets/`，修复 GitHub README 图片渲染（点开头隐藏目录的图片显示不稳定）

### v1.12.5（2026-08-22）

视觉会话健壮性 + 仓库打磨：

- 视觉会话：`--method vision` 启动后首屏状态现在带 `vision_capable` 和 `model` 字段（AI 进会话第一眼就能判定自己是否支持视觉）
- 视觉会话：`eval` 指令新增 10s 死循环看门狗——用户/恶意 prompt 发的 `while(true){}` 等会卡死 JS 时，DevTools HTTP `/json/close` 端点强杀页面，会话自动重建（再也不会永久卡死）
- Bug 修复：`own_search.py download` 和 `own_search.py seed` 补上 subprocess 超时（1800s / 300s），下游卡死不再拖死父进程
- 仓库：新增项目吉祥物（现位于 `assets/mascot.png`），已嵌入两个 README 页面

### v1.12.4（2026-08-22）

视觉会话全面修复 + 12 项关键 bug 修复。同时包含此前未单独发版的 v1.12.2~v1.12.3 内部迭代（`focus` CSS 选择器聚焦、`elements` 元素标注、验证码检测上报）。
- 数据安全：`verify_capture.py --clean` 在无 ffmpeg 时拒删 broken 文件（无法验证 ≠ 损坏），防止清光用户正片。
- 崩溃修复：`search_and_cache.py` 子进程超时不再整体崩溃（改为返回 JSON 错误）；缓存超时放宽到 300s。
- 安全修复：`own_search.py download --safe` 现在真正传递 `--safe` 给底层浏览器。
- 搜索健壮性：smart_search 浏览器版超时 90s→240s；cross_search mega 超时按引擎数放大并在 `rounds_info` 标记 `timed_out_copies`（不再静默返回空）；URL 去重保留业务参数（`v/id/tid` 等，YouTube 不同视频不再被误判为同一条）。
- 体验：视觉会话提示统一中文；`--query --auto` 与 `--url` 模式对齐增加 chain 兜底；日志换行笔误修复。

## License

MIT
