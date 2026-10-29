# 日常使用

程序默认放在 `D:/WeChatBridge/auto-read`。如果安装时选了其他位置，命令中加 `--root <项目目录>`。

## 连接AI助手

1. 运行 `python <技能目录>/scripts/wechat.py doctor`，查看程序目录和记录状态。
2. AI助手里已经有 `wechat_local` 工具时，直接调用；也可用下面的命令读取。
3. 需要接入MCP时，运行 `python <技能目录>/scripts/setup_backend.py --root D:/WeChatBridge --connection-only`。把生成的 `connections/mcp-stdio.json`加入AI助手的MCP设置，重新加载后调用 `wechat_get_index_status`。

MCP通过STDIO连接，返回文字和图片。配置文件的写法按所用AI助手的要求调整。

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

`report sent`按每个会话的本人发送数降序，前20名包含文字和各种附件消息。`report sessions`生成全部对象及严格大于100条的清单；重名对象按ID分开。把生成的文件位置告诉用户。

后端 `exports/media`保存已处理媒体及转写；`exports`保存会话导出与CSV；知识库输出按实际选择的 vault。缓存缺失时报告该条缺失，不用更早的图片替换最近N条。
