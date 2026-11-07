# wechat-local：微信聊天记录读取与分析 Skill

让 AI 助手读取 Windows 电脑里的微信聊天记录：搜索群聊和联系人、统计发言、查看聊天图片、转写微信语音、读取视频和附件，再把结果导出到 Obsidian。`wechat-local` 采用 Agent Skills 格式，提供本地 MCP 服务、Python CLI 和可执行的安装流程。

**WeChat chat history for AI agents on Windows.** Search conversations, view images, transcribe voice messages, read videos and documents, query cached Moments, and export to Obsidian through MCP or CLI.

[下载 Skill](https://github.com/YZCore/wechat-local-skill/raw/refs/heads/main/dist/wechat-local-skill.zip) · [English](README.en.md) · [安装教程](references/setup.md) · [使用方法](references/usage.md) · [16 个工具与参数](references/tools.md) · [Agent 文档导航](llms.txt)

## 可以用它做什么

| 你想完成的事 | 功能与输出 |
|---|---|
| 搜索微信聊天记录、整理群聊 | 按联系人、群名、关键词和时间查询消息，导出完整会话 |
| 看某个群最近发的图片 | 定位图片消息，读取实际图片并交给 AI 查看 |
| 把微信语音转成文字 | 提取可播放音频，使用本地语音模型转写 |
| 总结聊天里发来的视频 | 提取视频关键帧和声音转写，结合画面整理内容 |
| 阅读微信里的文档 | 读取 PDF、Word、Excel、PPT 及常见文本附件 |
| 分析自己的发言情况 | 统计各聊天对象的消息数量，按本人发送数列出前 20 名 |
| 整理朋友圈资料 | 查询本机朋友圈缓存中的正文、评论及媒体信息 |
| 把聊天变成知识库笔记 | 导出 Markdown、JSON、CSV，写入选定的 Obsidian vault |
| 补充手机上的旧聊天 | 指导微信迁移到电脑，按消息 ID 合并和比较记录 |

读取范围来自当前微信账号在本机保存的数据。需要更多手机历史时，先通过微信迁移到电脑，再更新索引。

## 快速开始

### 1. 安装技能

下载并解压[技能包](https://github.com/YZCore/wechat-local-skill/raw/refs/heads/main/dist/wechat-local-skill.zip)，把其中的 `wechat-local` 文件夹放入 AI 助手的技能目录，目录内直接包含 `SKILL.md`、`scripts/` 和 `assets/`。

支持 [Agent Skills](https://agentskills.io/specification) 的 AI 助手可加载技能；支持本地 MCP 的助手可连接服务；能够执行 Python 或 PowerShell 的助手可直接使用 CLI。Codex、Claude Code、DeepSeek Harness 等工具可按各自的技能目录和 MCP 设置接入。

### 2. 让 AI 完成设置

在 Windows 电脑版微信登录后，告诉 AI：

> 使用 wechat-local，帮我安装微信聊天记录读取工具，连接到当前 AI 助手。

技能会复用已有 Python 和程序，安装需要的依赖，建立聊天索引，并生成 MCP 配置。项目默认放在 `D:/WeChatBridge`，也可以指定目录。

直接运行安装命令：

```powershell
& "<技能目录>/scripts/start.ps1" -Root D:/WeChatBridge -Apply
```

分步说明见[Windows 安装教程](references/setup.md)。

### 3. 直接说出要查的内容

- “看看项目群最近发的 5 张图片。”
- “把这位好友最近的语音转成文字。”
- “搜索上个月关于合同的聊天，整理时间线。”
- “按我发送的消息数，列出前 20 个聊天对象。”
- “读一下群里发来的表格，总结里面的数据。”
- “把这段聊天整理到 Obsidian。”

## MCP 与命令行接入

安装后，`connections/mcp-stdio.json` 提供 `wechat_local` 的本地 MCP 配置。服务通过 STDIO 与 AI 助手连接，返回查询结果、媒体路径和图片。

同一组工具也可以从 CLI 调用：

```powershell
python "<技能目录>/scripts/wechat.py" doctor
python "<技能目录>/scripts/wechat.py" call wechat_list_sessions --keyword "项目群" --limit 5
python "<技能目录>/scripts/wechat.py" call wechat_read_session --session "<会话username>" --limit 20
python "<技能目录>/scripts/wechat.py" call wechat_list_media_messages --session "<会话username>" --kind image --limit 5
python "<技能目录>/scripts/wechat.py" call wechat_read_media --identity "<消息identity>"
python "<技能目录>/scripts/wechat.py" report sent
```

`tools` 列出工具参数；`refresh` 更新记录；`report sessions` 生成各对象的消息数量清单。接入步骤见[日常使用](references/usage.md)，全部工具见[工具参考](references/tools.md)。

## 常见问题

### AI 怎么读取微信聊天记录？

本项目读取 Windows 微信的本机数据库和媒体缓存，建立可搜索的本地索引。AI 通过 MCP 工具或 CLI 按需查询，再整理成摘要、统计或笔记。

### 可以读取微信图片、语音和文件吗？

可以。聊天图片返回可查看的文件；语音提取成音频并在本地转写；视频提供关键帧和声音转写；文档返回正文和文件位置。媒体结果包含实际取得的文件档位和可用状态。

### 怎样导出到 Obsidian？

安装时用 `--vault <知识库目录>` 选择 vault，或让 AI 把导出的 Markdown 与附件写入已有知识库。具体步骤见[Obsidian 和扩展操作](references/advanced.md)。

### 已经装过微信读取工具，还要重新搭建吗？

先运行 `wechat.py doctor` 查看已有程序、索引和媒体状态，继续使用已准备好的部分。技能会按当前环境补齐依赖和接入设置。

## 给 AI agent 的入口

- [SKILL.md](SKILL.md)：何时使用、读取步骤和任务路由。
- [llms.txt](llms.txt)：可直接抓取的 Markdown 文档导航。
- [安装教程](references/setup.md)：环境识别、部署、索引和 MCP 设置。
- [工具参考](references/tools.md)：16 个 MCP / CLI 工具、参数和返回内容。
- [日常使用](references/usage.md)：搜索、媒体读取、统计及输出位置。
- [扩展操作](references/advanced.md)：Obsidian、微信流、手机迁移和会话排除。

## 项目结构与许可

| 路径 | 用途 |
|---|---|
| `scripts/start.ps1` | Windows 安装入口 |
| `scripts/setup_backend.py` | 部署依赖、准备语音模型、生成 MCP 配置 |
| `scripts/wechat.py` | 工具调用、消息统计、会话排除和迁移比较 |
| `assets/backend/` | 微信聊天索引、媒体读取和统计源码 |
| `references/` | 按任务读取的操作文档 |

代码采用 [GPL-3.0](LICENSE)。底层项目和技术来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
