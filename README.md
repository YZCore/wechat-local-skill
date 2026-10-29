# 微信本地工作流 Skill

让 AI harness 读取、整理和分析 Windows 本机微信记录。支持复用已有环境，也能指导新用户从零部署。

[下载技能包](dist/wechat-local-skill.zip) · [技能入口](SKILL.md) · [本机复用](references/local-use.md) · [从零搭建](references/setup.md)

## 可以做什么

- 查询聊天记录、联系人和会话，搜索消息。
- 统计各对象的记录数量，以及本人发送消息最多的前20个对象。
- 读取实际图片、提取语音并在本地转写、读取视频关键帧和声音。
- 读取 PDF、Word、Excel、PPT 等附件正文。
- 查询朋友圈缓存正文及已缓存评论。
- 导出 Markdown、JSON 和 CSV，写入 Obsidian。
- 指导手机历史迁移，比较迁移前后的消息。
- 按账号维护会话及公众号排除规则。

## 场景一：本机已有环境

将本仓库作为 `wechat-local` 技能安装到 harness 的技能目录，然后直接说：

> 使用 wechat-local 技能，检查本机已有环境并复用它，完成我的微信记录读取任务。

技能会先检查后端、索引及模型。已有 MCP 时使用 MCP；可以运行命令时也能通过统一 CLI 使用同一套功能。

```powershell
python "<技能目录>/scripts/wechat.py" doctor
python "<技能目录>/scripts/wechat.py" call wechat_list_sessions --keyword 示例群 --limit 5
python "<技能目录>/scripts/wechat.py" call wechat_list_media_messages --session 示例群 --kind image --limit 5
```

## 场景二：从零开始

把技能包交给目标 harness，并说明：

> 安装并使用这个技能。先判断我的系统、微信和已有软件，再一步一步搭建；已有的部分直接复用。

Windows 入口：

```powershell
& "<技能目录>/scripts/start.ps1"
& "<技能目录>/scripts/start.ps1" -Root D:/WeChatBridge -Apply
```

按实际情况准备运行环境、部署后端、建立聊天索引、接通媒体、连接 harness，再加入 Obsidian 或微信流分享。具体步骤见[从零搭建](references/setup.md)。

## 包内程序

| 入口 | 用途 |
|---|---|
| `scripts/start.ps1` | Windows 环境识别与部署入口 |
| `scripts/setup_backend.py` | 安装项目依赖、准备转写模型、生成 MCP 配置 |
| `scripts/wechat.py` | 调用16个读取工具，执行统计、排除和迁移比较 |
| `assets/backend/` | 聊天索引、媒体读取及统计的实现源码 |
| `references/` | 根据当前任务读取的操作流程 |

项目路径可通过 `--root` 指定。绑定群和知识库由使用者设置。运行数据保存在使用者自己的项目目录，语音转写在本机执行。

## 安装结构

技能目录名使用 `wechat-local`，目录内直接包含 `SKILL.md`、`scripts`、`references` 和 `assets`。采用 [Agent Skills 格式](https://agentskills.io/specification)，可由支持该格式的 harness 加载。

## 来源与许可

本仓库采用 [GPL-3.0](LICENSE)。底层项目及使用来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
