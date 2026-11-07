# wechat-local: WeChat chat history for AI agents

Read and analyze WeChat chat history on Windows through an Agent Skill, a local MCP server, or a Python CLI. Search conversations, view chat images, transcribe voice messages, read videos and documents, query cached Moments, and export notes to Obsidian.

[中文](README.md) · [Download the skill](https://github.com/YZCore/wechat-local-skill/raw/refs/heads/main/dist/wechat-local-skill.zip) · [Setup guide](references/setup.md) · [Usage](references/usage.md) · [Tool reference](references/tools.md) · [Agent documentation index](llms.txt)

## What you can do

| Task | Result |
|---|---|
| Search WeChat conversations | Messages filtered by contact, group, keyword, and time |
| Read chat images | Actual image files that a vision-capable agent can inspect |
| Transcribe voice messages | Playable audio and local speech-to-text output |
| Summarize shared videos | Video frames and audio transcripts |
| Read shared documents | Text from PDF, Word, Excel, PowerPoint, and common text files |
| Analyze messaging activity | Message counts per conversation and your top 20 recipients |
| Query cached WeChat Moments | Post text, cached comments, and media metadata |
| Export to a knowledge base | Markdown, JSON, CSV, and Obsidian notes |
| Include phone chat history | Guided WeChat migration to PC and comparison by message ID |

Data comes from the current account's records saved on the computer. Phone history can be included by migrating it through WeChat and refreshing the local index.

## Quick start

1. Download the skill ZIP and extract the `wechat-local` folder into your AI assistant's skills directory. The folder contains `SKILL.md`, `scripts/`, and `assets/` directly.
2. Sign in to WeChat on Windows.
3. Ask your assistant: **Use wechat-local to set up WeChat chat history access and connect it to this assistant.**

The installer reuses existing programs, prepares the Python environment, builds the chat index, and writes the MCP connection configuration. The default project directory is `D:/WeChatBridge`.

You can also start installation from PowerShell:

```powershell
& "<skill-directory>/scripts/start.ps1" -Root D:/WeChatBridge -Apply
```

The [setup guide](references/setup.md) covers the individual steps. The detailed operation guides are written in Chinese; executable commands and tool names work in either language.

## Connect an AI assistant

The skill follows the [Agent Skills specification](https://agentskills.io/specification). Assistants that load skills can use `SKILL.md`; assistants with local MCP support can use `connections/mcp-stdio.json`; assistants that execute local commands can use the CLI. Codex, Claude Code, and DeepSeek Harness can use the entry point supported by their host.

The `wechat_local` MCP server uses STDIO. The CLI exposes the same 16 tools:

```powershell
python "<skill-directory>/scripts/wechat.py" doctor
python "<skill-directory>/scripts/wechat.py" call wechat_list_sessions --keyword "<group-name>" --limit 5
python "<skill-directory>/scripts/wechat.py" call wechat_read_session --session "<session-username>" --limit 20
python "<skill-directory>/scripts/wechat.py" call wechat_list_media_messages --session "<session-username>" --kind image --limit 5
python "<skill-directory>/scripts/wechat.py" call wechat_read_media --identity "<message-identity>"
python "<skill-directory>/scripts/wechat.py" report sent
```

Use `tools` to inspect arguments and `refresh` to update records. See the [tool reference](references/tools.md) for the full list.

## Example requests

- Show the five most recent images in a group chat.
- Transcribe a contact's recent voice messages.
- Find last month's messages about a contract and build a timeline.
- Rank my top 20 conversations by the number of messages I sent.
- Read a spreadsheet shared in a chat and summarize its contents.
- Export a conversation to my Obsidian vault.

## Documentation for agents

- [SKILL.md](SKILL.md): task matching, workflow, and references.
- [llms.txt](llms.txt): concise documentation index with raw Markdown links.
- [Setup](references/setup.md): deployment, indexing, and MCP connection.
- [Tools](references/tools.md): names, arguments, and outputs.
- [Usage](references/usage.md): search, media processing, reports, and output paths.
- [Advanced operations](references/advanced.md): Obsidian, WeChatBridge sharing, phone migration, and conversation exclusions.

## License

[GPL-3.0](LICENSE). Upstream projects and technical sources are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
