# 微信 MCP / CLI 工具参考

`wechat-local` 提供 16 个工具，供 AI agent 搜索微信聊天、读取媒体和生成导出文件。MCP 服务名为 `wechat_local`，传输方式为 STDIO。CLI 使用相同工具名：

```powershell
python "<技能目录>/scripts/wechat.py" call <工具名> --参数名 值
python "<技能目录>/scripts/wechat.py" tools
```

[项目介绍](../README.md) · [安装教程](setup.md) · [日常使用](usage.md) · [技能入口](../SKILL.md)

## 聊天与联系人

| 工具 | 常用参数 | 返回内容 |
|---|---|---|
| `wechat_get_index_status` | 无 | 索引路径、更新时间、记录数量和覆盖时间 |
| `wechat_list_sessions` | `keyword=''`、`groups_only=false`、`limit=50`、`offset=0` | 会话 `username`、名称、类型和消息数量 |
| `wechat_list_contacts` | `keyword=''`、`limit=50`、`offset=0` | 联系人账号、昵称、备注和显示名称 |
| `wechat_read_session` | `session`、`limit`、`offset`、`start_time`、`end_time` | 指定会话的消息，按新到旧分页 |
| `wechat_search_messages` | `keyword`、`session=''`、`start_time=0`、`end_time=0`、`limit=50`、`offset=0` | 匹配关键词和时间条件的消息 |
| `wechat_export_session` | `session` | 完整会话的 JSON、Markdown 路径及消息数 |

先用 `wechat_list_sessions` 查到唯一的 `username`，再传入 `session`。时间范围使用 Unix 秒。一般查询每页 1—500 条，`offset` 从 0 开始。CLI 的 `wechat_read_session` 默认读取 100 条。

## 图片、语音、视频与附件

| 工具 | 常用参数 | 返回内容 |
|---|---|---|
| `wechat_get_media_inventory` | 无 | 本机媒体缓存的文件数量和体积 |
| `wechat_get_media_status` | 无 | 媒体索引状态、关联数量和本地语音模型状态 |
| `wechat_list_media_messages` | `session=''`、`kind=''`、`availability=''`、`limit=50`、`offset=0` | 媒体消息的 `identity`、时间、类型和可用状态 |
| `wechat_read_media` | `identity`、`transcribe=true`、`language='zh'`、`frames=3`、`max_chars=20000` | 图片、音频、转写、视频画面或文档正文，以及文件位置 |
| `wechat_search_media_content` | `keyword`、`session=''`、`limit=20`、`offset=0` | 已处理语音、视频和附件中匹配的内容 |

`kind` 使用 `image`、`voice`、`video` 或 `file`。`availability` 使用 `available`、`missing` 或 `candidate`。图片结果标注原图、压缩图或缩略图；语音在本地转写；视频提取 1—6 帧；附件正文支持 PDF、DOC/DOCX、XLS/XLSX、PPT/PPTX 和常见文本。

查看某群最近 5 张图片：

```powershell
python "<技能目录>/scripts/wechat.py" call wechat_list_sessions --keyword "项目群" --limit 5
python "<技能目录>/scripts/wechat.py" call wechat_list_media_messages --session "<会话username>" --kind image --limit 5
python "<技能目录>/scripts/wechat.py" call wechat_read_media --identity "<上一步的identity>"
```

按返回的消息顺序逐条读取。媒体处理结果保存在后端 `exports/media`，可供后续搜索和知识库整理。

## 朋友圈与绑定群

| 工具 | 常用参数 | 返回内容 |
|---|---|---|
| `wechat_query_moments` | `keyword=''`、`author=''`、`main_feed_only=true`、`limit=20`、`offset=0` | 本机朋友圈缓存中的正文、评论和媒体元数据 |
| `wechat_read_recent_moments` | `limit=20` | 最近 1—20 条本机主信息流记录及 Obsidian 导出 |
| `wechat_read_bound_group` | `limit=200`、`refresh=true` | 已配置绑定群的最近消息及 Obsidian 导出 |

朋友圈的 `author` 按显示名称筛选。`main_feed_only=false` 同时查询本机其他已缓存帖子。绑定群和知识库可在安装时用 `--group`、`--vault` 设置。

## 更新索引

| 工具 | 参数 | 作用 |
|---|---|---|
| `wechat_refresh_local_index` | 无 | 更新聊天、联系人和朋友圈缓存索引；CLI 同时更新已启用的媒体映射 |
| `wechat_refresh_media_index` | 无 | 依据聊天索引刷新本机媒体映射 |

CLI 的常规更新入口是 `refresh`：

```powershell
python "<技能目录>/scripts/wechat.py" refresh
```

## 统计与扩展命令

这些命令由 CLI 提供：

| 命令 | 用途 |
|---|---|
| `doctor` | 查看程序、索引、媒体和语音模型状态 |
| `report sent` | 按本人发送消息数量排序，列出前 20 个对象 |
| `report sessions` | 生成各对象数量及严格大于 100 条的清单 |
| `compare --baseline <索引路径>` | 按消息 ID 比较迁移前后的记录 |
| `exclude plan --session <名称或ID>` | 生成会话排除计划 |
| `exclude apply --plan <计划路径>` | 应用指定排除名单 |

Obsidian、手机历史迁移及微信流场景见[扩展操作](advanced.md)。
