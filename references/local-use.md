# 本机其他 harness 复用

本机默认后端为 `D:/WeChatBridge/auto-read`。技能本身在共享目录，DSH、Codex 等可以从同一份技能读取操作方法。后端、索引、排除规则和转写模型也各维护一份。

## 直接使用

1. 运行 `python <技能目录>/scripts/wechat.py doctor`，获取实际目录、聊天和媒体状态，以及下一步动作。
2. 如果宿主已显示 `wechat_local` 工具，直接调用；否则先用 CLI 完成用户任务。
3. 按需配置原生 MCP：运行 `python <技能目录>/scripts/setup_backend.py --root D:/WeChatBridge --connection-only`，取得 `connections/mcp-stdio.json`。将其中的服务条目合并到宿主的 MCP 设置，保留其他服务。重载宿主后，调用 `wechat_get_index_status`。

MCP 使用标准 STDIO、JSON参数及图像内容块。语音和文档正文作为文字返回。不同 harness 的配置字段以其已安装版本为准；CLI 可直接使用相同功能。

## 常用命令

```powershell
python "<技能目录>/scripts/wechat.py" call wechat_get_index_status
python "<技能目录>/scripts/wechat.py" call wechat_read_session --session 示例群 --limit 20
python "<技能目录>/scripts/wechat.py" call wechat_search_messages --keyword 会议 --session "项目群" --limit 30
python "<技能目录>/scripts/wechat.py" call wechat_list_media_messages --session 示例群 --kind image --limit 5
python "<技能目录>/scripts/wechat.py" call wechat_read_media --identity "<消息identity>"
python "<技能目录>/scripts/wechat.py" call wechat_query_moments --limit 20
python "<技能目录>/scripts/wechat.py" report sent
python "<技能目录>/scripts/wechat.py" report sessions
```

需要新快照时使用 `refresh`，保留现有索引并按当前排除规则更新。只有媒体映射落后时可单独 `call wechat_refresh_media_index`。

## 内容处理

- 图片：从新到旧先选N条，不先过滤可用性；逐条读取，展示实际图片并简述内容。`original`、`mid`、`thumb`分别表示缓存档位；后两种不统一称为原图。
- 语音：默认生成 WAV 和本地转写；`--transcribe false`只提取可播放音频。
- 视频：默认提取3帧，可用 `--frames 1`至`6`；存在音轨时可转写。画面分析以返回的实际帧为依据。
- 附件：PDF、DOC/DOCX、XLS/XLSX、PPT/PPTX及常见纯文本可读正文。DOC/PPT使用已有LibreOffice转换。其他格式仍返回可取回的文件。读取页数、行数及字符上限以返回结果为准。
- 朋友圈：`wechat_query_moments`返回正文、评论和媒体元数据；聊天媒体解码成功不代表朋友圈原图已一并获取。朋友圈媒体另按实际缓存匹配，保留候选状态。

## 统计与输出

`report sent`按每个会话的本人发送数降序，前20名包含文字和各种附件消息。`report sessions`生成全部对象及严格大于100条的清单；重名对象按ID分开。输出目录和文档路径随返回结果交付。

后端 `exports/media`保存已处理媒体及转写；`exports`保存会话导出与CSV；知识库输出按实际选择的 vault。缓存缺失时报告该条缺失，不用更早的图片替换最近N条。
