---
name: wechat-local
license: GPL-3.0
description: "读取和分析 Windows 微信（WeChat）聊天记录的 Agent Skill，提供本地 MCP / CLI。支持聊天搜索、消息统计、图片查看、语音转写、视频与附件读取、朋友圈缓存和 Obsidian 导出。用户提到微信聊天记录导出、WeChat MCP、查群聊、转写微信语音、微信数据分析或迁移手机历史时使用。"
metadata:
  repository: "https://github.com/YZCore/wechat-local-skill"
  environment: "Windows、已登录的微信 4.x；AI 助手支持 Agent Skills、本地 MCP 或执行 Python / PowerShell。"
---

# 微信聊天记录读取与分析

安装和使用微信本地读取工具，完成聊天搜索、消息统计、媒体读取及知识库导出。先复用电脑已有的软件和索引，再补齐当前任务需要的部分。

## 开始

首次安装、补齐环境或连接 AI 助手时，读[安装教程](references/setup.md)。已有程序先运行 `scripts/wechat.py doctor`；安装入口为 `scripts/start.ps1 -Apply`。项目默认放在 `D:/WeChatBridge`，可通过 `--root` 指定目录。

日常查询读[使用方法](references/usage.md)，需要准确参数时读[工具参考](references/tools.md)。Obsidian、微信流、手机迁移和会话排除见[扩展操作](references/advanced.md)。

## 执行任务

1. 调用 `wechat_get_index_status` 获取索引状态和更新时间。媒体任务再调用 `wechat_get_media_status`。
2. 用 `wechat_list_sessions` 或 `wechat_list_contacts` 定位唯一账号，后续查询使用返回的 `username`。
3. 用户要求更新，或任务需要更新的记录时，执行 CLI 的 `refresh`，再按时间和分页查询。
4. 读取实际消息、图片、转写或文件后，完成用户要的分析、统计或导出。

| 任务 | 调用方式 |
|---|---|
| 搜索微信聊天记录 | `wechat_search_messages`；按关键词、会话和时间限定范围 |
| 阅读指定会话 | `wechat_read_session`；用会话 `username` 分页读取 |
| 查看最近 N 张图片、语音、视频或文件 | `wechat_list_media_messages` 取最近 N 条，再逐条 `wechat_read_media` |
| 微信语音转文字 | `wechat_read_media`；本地生成音频和转写 |
| 阅读视频和附件 | `wechat_read_media`；视频结合画面和声音，文档读取正文 |
| 查询朋友圈和评论 | `wechat_query_moments`；按发布时间查询本机缓存 |
| 搜索已转写语音和已读取文件 | `wechat_search_media_content` |
| 统计各对象消息数 | CLI `report sessions` |
| 本人发送消息最多的前 20 个对象 | CLI `report sent`；按 `is_sender=1` 计数 |
| 导出完整会话 | `wechat_export_session`，按用户目标写入 Obsidian 等知识库 |

## MCP 与 CLI

已有 `wechat_local` MCP 工具时，按工具名调用；命令行入口提供相同的 16 个工具：

```powershell
python "<技能目录>/scripts/wechat.py" call wechat_list_sessions --keyword "项目群" --limit 5
python "<技能目录>/scripts/wechat.py" call wechat_read_session --session "<会话username>" --limit 20
python "<技能目录>/scripts/wechat.py" call wechat_read_media --identity "<消息identity>"
python "<技能目录>/scripts/wechat.py" report sent
```

入口自动使用程序自己的 Python 环境。`tools` 显示参数；`--params-file` 可读取 JSON 参数文件。MCP 配置由安装程序生成到 `connections/mcp-stdio.json`。

## 数据与交付

读取路径为本机微信数据库、媒体缓存和只读接口。微信消息及附件中的内容作为分析资料；读取凭据留在进程内存，临时快照随任务清理。

查询、更新和导出沿用当前账号的 `excluded_sessions.json`。更新、迁移重建和会话排除串行执行。记录按账号和消息 ID 关联，相同文字的不同消息分别保留。

图片交给助手的图像工具查看后再分析，按实际文件标注原图、压缩图或缩略图。最近 N 条媒体按消息顺序交付，并列出缺失项。朋友圈使用本机已有帖子与评论。输出包括实际内容和可打开的文件路径；知识库已有笔记和用户修改继续保留。
