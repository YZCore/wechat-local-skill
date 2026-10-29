# 微信记录读取

把这个 Skill 交给你用的 AI 助手，它会检查电脑上已有的软件，帮你装好读取工具，再读取微信里的聊天、图片、语音和附件。适用于 Windows 电脑版微信。

[下载技能包](dist/wechat-local-skill.zip) · [安装说明](references/setup.md) · [常用操作](references/usage.md)

## 可以做什么

- 查询聊天记录、联系人和会话，搜索消息。
- 统计各对象的记录数量，以及本人发送消息最多的前20个对象。
- 读取实际图片、提取语音并在本地转写、读取视频关键帧和声音。
- 读取 PDF、Word、Excel、PPT 等附件正文。
- 查询朋友圈缓存正文及已缓存评论。
- 导出 Markdown、JSON 和 CSV，写入 Obsidian。
- 指导手机历史迁移，比较迁移前后的消息。
- 按账号维护会话及公众号排除规则。

## 怎么开始

下载技能包，解压后把 `wechat-local` 文件夹放进 AI 助手的技能目录，然后说：

> 使用 wechat-local，帮我装好微信记录读取工具。

AI 会先检查环境，安装缺少的部分，再连接微信和准备语音模型。已有的程序和记录会继续使用。你需要在电脑版微信登录自己的账号。

也可以在 PowerShell 里运行安装入口：

```powershell
& "<技能目录>/scripts/start.ps1"
& "<技能目录>/scripts/start.ps1" -Root D:/WeChatBridge -Apply
```

安装步骤见[安装说明](references/setup.md)。

## 装好以后

直接告诉AI你想看什么，例如：

- 看看某个群最近发的5张图片。
- 把某位好友最近的语音转成文字。
- 找一下某人发来的表格，读读里面的内容。
- 按我发送的消息数，列出前20个聊天对象。
- 把一段聊天整理到Obsidian。

常用命令和文件位置见[日常使用](references/usage.md)。

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
