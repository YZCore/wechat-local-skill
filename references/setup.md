# 安装和设置

先查看电脑上已有的软件，再按下面的顺序准备。已经装好的部分直接使用。

## 1. 判断现有条件

Windows先运行 `& "<技能目录>/scripts/start.ps1"`。入口依次复用后端环境、已有Python和uv；部署时需要安装Python则使用Windows已有的软件安装渠道。已有Python也可以直接运行下面的Python入口。

运行 `scripts/setup_backend.py --root <目标目录>`，查看已经安装的程序。程序位置和依赖由AI检查；需要了解用户用哪个AI助手、是否要接Obsidian或迁移手机记录时，再问用户。

| 实际情况 | 接下来做什么 |
|---|---|
| Windows、已登录电脑版微信4.x | 部署本地后端后建立索引 |
| 已经装过读取工具 | 用 `wechat.py doctor`查看状态，继续准备缺少的部分 |
| 只有手机记录或电脑历史较少 | 先建立电脑基线，再按扩展流程迁移手机历史 |
| Python已安装 | 复用现有可用Python，运行依赖放在项目独立环境 |
| 已有uv | 用uv建立环境和安装包；否则复用Python自带venv及pip |
| 其他系统或微信数据结构不同 | 说明当前读到的系统及版本，选择对应实现后继续；本包部署脚本适用于Windows |

确定程序放在哪里、使用哪个Python，以及用户要用的AI助手。

电脑版微信尚未准备好时：先检查是否已安装；已安装则让用户打开并登录。未安装则从[微信Windows官网](https://pc.weixin.qq.com/)取得安装程序，完成安装后由用户登录自己的账号，再继续建立索引。Obsidian按用户需要从[官网](https://obsidian.md/download)安装，已有知识库则直接复用。

## 2. 部署程序

随包 `assets/backend`提供已实现的读取、索引、媒体和统计代码；部署脚本把程序放入目标目录，下载固定版本的底层读取模块，在项目内安装依赖，并生成接入文件。

```powershell
& "<技能目录>/scripts/start.ps1" -Root D:/WeChatBridge -Apply
# 已有Python时也可直接调用：
python "<技能目录>/scripts/setup_backend.py" --root D:/WeChatBridge --apply
```

用 `--python <python.exe>`选择已有解释器；用 `--vault <知识库目录>`和`--group <准确群名>`配置知识库与可选绑定群。部署时保留已有文件和账号规则。`--prepare-model`会下载本地多语言语音模型；网络中断时沿用下载缓存，解决网络问题后继续这一项。

程序和依赖会装进所选目录，MCP配置保存在 `connections/mcp-stdio.json`。

## 3. 建立聊天索引

让用户保持电脑版微信已登录。首次运行：

```powershell
python "<技能目录>/scripts/wechat.py" --root D:/WeChatBridge refresh
```

程序生成当前账号的聊天、联系人及朋友圈缓存索引。已有索引先保留，使用会话和消息ID去重。随后查找用户指定的一个会话，并读出其最近消息；根据实际结果说明记录覆盖时间。

## 4. 接通媒体

```powershell
python "<技能目录>/scripts/setup_backend.py" --root D:/WeChatBridge --prepare-model
python "<技能目录>/scripts/wechat.py" --root D:/WeChatBridge call wechat_refresh_media_index
```

按用户实际存在的消息，分别完成图片查看、语音转写、视频画面读取和附件正文读取。依次处理遇到的问题：

- 媒体索引落后：先更新映射。
- 缓存只有缩略图：显示缩略图，并说明这是缩略图。
- 媒体数据尚未在本机保存：指出具体缺失消息；用户需要原文件时，由用户在微信中手动保存，再读取新增本地数据。
- 图片解密条件暂不可用：保留原索引，依据返回状态解决当前读取条件；采集流程继续使用本地接口。
- 语音模型未就绪：完成模型下载后继续转写。
- 附件是DOC/PPT：复用已安装LibreOffice；若该格式确需读取而软件尚未安装，安装后继续。其他新格式按对应文件格式处理。

读取用户要看的图片、语音、视频或附件，并把内容和文件位置提供给用户。

## 5. 连接AI助手

支持本地MCP的宿主：合并 `connections/mcp-stdio.json`中的服务配置，按宿主需要重载，实际调用状态和会话工具。工具超时建议容纳索引重建，当前模板提供300秒供宿主字段映射。

能够运行命令的宿主：直接使用本技能CLI。图像理解还需宿主把返回图像交给支持视觉的模型；文字模型可使用语音转写与附件正文。

在用户使用的AI助手里完成一次读取，例如查看某群最近5张图片。

## 6. 加入笔记、分享和分析场景

按用户所选部分读取 [扩展流程](advanced.md)，完成 Obsidian、原版微信流、群聊分析或手机迁移。此前能完成的聊天查询和媒体读取继续可用。

## 7. 以后怎么用

告诉用户程序和输出文件放在哪里，以及下次可以直接说什么。常用命令见[日常使用](usage.md)。更新记录用 `refresh`，之后可以重新统计数量或本人发言排名。

技术来源：[Agent Skills格式](https://agentskills.io/specification)、[本地MCP接入](https://modelcontextprotocol.io/docs/develop/connect-local-servers)、[WeChatMsg-4x](https://github.com/chenanhan230-del/WeChatMsg-4x)、[wechatauto-replica媒体模块](https://github.com/fanyuantaier/wechatauto-replica)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)。
