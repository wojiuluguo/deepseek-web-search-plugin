# 发版规范（Release Guide）

本文件记录本项目的发版决策规则与流程。每次发版前照此执行。

## 何时发版 / 何时累积不发

| 情形 | 动作 |
|---|---|
| 单点小修、临时修补 | 只更新 [CHANGELOG.md](CHANGELOG.md) / [CHANGELOG.zh-CN.md](CHANGELOG.zh-CN.md)，**不 commit 不 push**（累积模式） |
| 累积了多个修复/功能，**且用户明确说"更新 / 发版 / 同步 GitHub"** | 执行下方完整发版流程 |
| 用户没有明确指示 | 一律不动 GitHub。**"修改/修复/测试"都不等于"发版"** |

> 历史依据：v1.25.1、v1.25.2 均按维护者决策累积不发，待统一更新。

## 发版流程 Checklist

1. **确认累积范围**：`git status` + `git diff` 盘点全部未提交修复，逐项核对 CHANGELOG 已有对应条目。
2. **Release Notes（双语，每版重写）**：
   - 格式沿用历史 Release：**英文在前，中文在后**，附来源链接与完整变更说明；
   - **必须只写本版自己的变化**——每个版本都要重新写，不得复用/拼贴旧版文字；
   - **把对用户有用的内容放前面**：新能力、修了什么痛点、实测数据；裁决细节、搁置记录往后放。
3. **打包 ZIP（git archive，只装必要内容）**：
   - 用 `git archive HEAD -o dist/deepseek-web-search-plugin-vX.Y.Z.zip`（只打 git 跟踪文件，天然排除 .gitignore 内容）；
   - 打包前 `git ls-files` 审一遍清单，确认无测试产物、缓存、临时文件、压测数据混入；
   - zip 里应有：源码、SKILL.md、双语 README、双语 CHANGELOG、安装脚本、package.json、requirements.txt、吉祥物图。
4. **推送 + Release**：commit → push → `gh release create vX.Y.Z`（Notes 第 2 步产物）→ 上传 zip 附件。

## 红线（不可违反）

- **`search-api-service/` 子项目文件夹绝不进本仓库，也绝不进 zip**——其中可能含邮箱号、API 项目信息等敏感数据。该目录已在 `.gitignore`（第 28 行区），发版前用 `git ls-files search-api-service` 复核（必须为 0 条）。
- API Key / cookie / 登录态文件永远不入库（.gitignore 已覆盖 `.gh/`、`downloads/browser_profile/` 等）。
- 根目录 `*.zip`、`dist/`、`downloads/`、`index/`、压测产物一律不入库。

## 版本号约定

- 新功能 / 大修复：次版本号 +1（v1.25 → v1.26）
- 小修 / 裁决轮 / 文档：修订号 +1（v1.25.1 → v1.25.2）
- 版本号需四处同步：SKILL.md、package.json、双语 README 头部、CHANGELOG 新条目。
