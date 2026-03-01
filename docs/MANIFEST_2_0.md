# Manifest 2.0 — Roadmap

Manifest is a chat + autonomous task execution agent for OAP. This document compares Manifest to [OpenClaw](https://openclaw.ai) and lays out the 2.0 feature roadmap.

## OpenClaw Comparison

| Feature | Manifest | OpenClaw |
|---------|----------|----------|
| **Tool discovery** | OAP manifests — runtime discovery via vector search + FTS5 + small LLM | Workspace skills — static SKILL.md files |
| **LLM** | Local Ollama (qwen3:8b) — zero cloud cost | Cloud LLM (Claude, GPT-4) |
| **Voice input** | Local STT via faster-whisper on Apple Silicon | Browser-side Web Speech API (Chrome only) |
| **Voice output** | Browser Web Speech API (TTS) | Browser Web Speech API (TTS) |
| **Autonomous tasks** | Cron-scheduled background execution | Manual triggers |
| **User memory** | SQLite fact extraction + LRU eviction | Session-scoped context |
| **Personality** | Named personas prepended to every conversation | System prompt configuration |
| **Security** | macOS sandbox-exec, PATH allowlist, blocked commands | Cloud provider guardrails |
| **Channels** | Web UI (chat) | Web UI, Slack, Discord |
| **Deployment** | Self-hosted Mac Mini + Cloudflare Tunnel | Cloud-hosted SaaS |

### Where Manifest Leads

- **Local-first**: No cloud APIs for core inference. Ollama on Apple Silicon keeps latency low and cost zero.
- **Runtime discovery**: OAP manifests are discovered at runtime — new capabilities without redeployment.
- **Autonomous execution**: Cron-scheduled tasks run in the background, not just on-demand.
- **OS-level security**: sandbox-exec file-write protection, not just prompt-level guardrails.

### Where OpenClaw Leads

- **Multi-channel**: Slack, Discord, and web — Manifest is web-only (for now).
- **Cloud LLM quality**: GPT-4/Claude produce higher-quality reasoning than qwen3:8b.
- **Managed hosting**: No hardware to maintain.

## Manifest 2.0 Roadmap

### Voice (v2.0.0) — *This Release*

Local-first voice input/output:

- **STT**: faster-whisper on Apple Silicon. MediaRecorder captures WebM in the browser, POST to `/v1/agent/transcribe`, text inserted into chat input for review.
- **TTS**: Browser Web Speech API. Zero backend cost. Speaker button on assistant messages + auto-speak toggle.
- **Settings**: Voice input toggle, auto-send toggle, auto-speak toggle — all persisted in SQLite.

### Channels (v2.1.0) — *Next*

Multi-channel message routing:

- **Slack**: Incoming webhooks + slash commands → route to `/v1/agent/chat`
- **Discord**: Bot gateway → same chat pipeline
- **Architecture**: Channel adapters normalize messages into the existing chat format. One conversation per channel thread.

### Monitoring (v2.2.0) — *Future*

System introspection manifests:

- Read-only tools: `lsof`, `ps`, `df`, `du`, `iostat`, `vmstat`
- Gated behind `--include-system` in manifest factory
- Enables "how's the server doing?" style queries through the chat interface

### Big LLM Escalation Improvements (v2.3.0) — *Future*

- **Streaming escalation**: Stream big LLM responses back to the chat UI in real-time
- **Provider rotation**: Automatic failover between escalation providers
- **Cost tracking**: Per-query cost estimation for escalated requests

## Design Principles

1. **Local-first**: Core inference runs on your hardware. Cloud APIs are optional escalation, never required.
2. **No cloud APIs for voice**: faster-whisper for STT, Web Speech API for TTS. Your voice data stays local.
3. **Apple Silicon optimized**: CTranslate2 (faster-whisper) and Ollama both leverage Metal/CoreML.
4. **Progressive enhancement**: Voice is additive — the text chat experience is unchanged without it.
5. **Review before send**: STT fills the input box, not auto-sends. The user stays in control.
