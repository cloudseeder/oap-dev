# Manifest 2.0 — Shipped Features & Roadmap

Manifest is a chat + autonomous task execution agent for OAP. This document compares Manifest to [OpenClaw](https://openclaw.ai), covers what shipped in the 2.0 cycle, and lays out the remaining roadmap.

## OpenClaw Comparison

| Feature | Manifest | OpenClaw |
|---------|----------|----------|
| **Tool discovery** | OAP manifests — runtime discovery via vector search + FTS5 + small LLM | Workspace skills — static SKILL.md files |
| **LLM** | Local Ollama (qwen3:8b) — zero cloud cost | Cloud LLM (Claude, GPT-4) |
| **Voice input** | Local STT via faster-whisper on Apple Silicon | Browser-side Web Speech API (Chrome only) |
| **Voice output** | Local Piper neural TTS on the backend — WAV generation, zero cloud cost | Browser Web Speech API (TTS) |
| **Autonomous tasks** | Cron-scheduled background execution with notification queue | Manual triggers |
| **Notifications** | Greeting briefings — pending task results surfaced naturally on next conversation | None |
| **Email** | IMAP scanner with LLM classification + auto-filing to folders | None |
| **Reminders** | SQLite-backed recurring reminders with auto-next-occurrence | None |
| **Procedural memory** | Dual-store experience cache (SQLite + ChromaDB vectors) — learns from past invocations | Session-scoped context |
| **User memory** | SQLite fact extraction + LRU eviction | Session-scoped context |
| **Personality** | Named personas prepended to every conversation | System prompt configuration |
| **Security** | macOS sandbox-exec, PATH allowlist, blocked commands | Cloud provider guardrails |
| **Channels** | Web UI (chat) | Web UI, Slack, Discord |
| **Deployment** | Self-hosted Mac Mini + Cloudflare Tunnel | Cloud-hosted SaaS |

### Where Manifest Leads

- **Local-first**: No cloud APIs for core inference. Ollama on Apple Silicon keeps latency low and cost zero.
- **Runtime discovery**: OAP manifests are discovered at runtime — new capabilities without redeployment.
- **Autonomous execution**: Cron-scheduled tasks run in the background, not just on-demand. Notification queue surfaces results as natural greeting briefings.
- **OS-level security**: sandbox-exec file-write protection, not just prompt-level guardrails.
- **Full voice stack**: Both STT (faster-whisper) and TTS (Piper neural voices) run locally on the backend. No browser API dependencies, no cloud voice services. Voice data never leaves the machine.
- **Email intelligence**: IMAP scanning with LLM-powered classification and auto-filing — the agent reads and organizes your email.
- **Procedural memory**: Experience cache with vector similarity lookup means the agent gets faster over time. Repeated tasks hit cache in ~50ms instead of full discovery.

### Where OpenClaw Leads

- **Multi-channel**: Slack, Discord, and web — Manifest is web-only (for now).
- **Cloud LLM quality**: GPT-4/Claude produce higher-quality reasoning than qwen3:8b (mitigated by big LLM escalation for complex tasks).
- **Managed hosting**: No hardware to maintain.

## Shipped Features

### Voice — STT + TTS (shipped)

Local-first voice input/output, fully on the backend:

- **STT**: faster-whisper (CTranslate2) on Apple Silicon. MediaRecorder captures WebM in the browser, POST to `/v1/agent/transcribe`, text inserted into chat input for review before sending.
- **TTS**: Piper neural voices on the backend. `POST /v1/agent/tts` generates WAV audio, played back via `HTMLAudioElement`. Multiple voice models supported. Zero cloud cost, zero browser API dependency.
- **Settings**: Voice input toggle, auto-send toggle, auto-speak toggle — all persisted in SQLite `agent_settings` table.
- **Config**: `voice.enabled`, `voice.whisper_model` (tiny/base/small), `voice.tts_enabled`, `voice.tts_model_path`, `voice.tts_models_dir`. See `docs/PIPER.md` for voice model management.

### Email Scanner (shipped)

IMAP email scanner with LLM-powered classification and auto-filing:

- **Two-phase design**: `POST /scan` fetches from IMAP and caches to SQLite, read endpoints query local cache. UID-based incremental scanning.
- **Classifier**: Local LLM via Ollama categorizes messages into configurable categories (personal, machine, mailing-list, spam, offers). User categories merge with defaults via `classifier.categories` in config.yaml.
- **Auto-filing**: `POST /file` moves classified messages to IMAP folders by category. Creates target folders if needed. Designed for cron: `curl -s -X POST localhost:8305/scan && curl -s -X POST localhost:8305/file`.
- **Query parser**: Supports `OR` between terms and field prefixes (`from:`, `to:`, `subject:`, `body:`).

### Reminder Service (shipped)

SQLite-backed reminder service for AI agents:

- One-time and recurring reminders (daily, weekly, monthly, yearly).
- Completing a recurring reminder auto-creates the next occurrence.
- Cleanup endpoint for cron-based maintenance.
- Exposed as OAP manifest for discovery by the agent.

### Experience Cache / Procedural Memory (shipped)

Dual-store architecture for learning from past invocations:

- **SQLite** (system of record) + **ChromaDB** (vector index for similarity lookup).
- Primary cache path: embed task with nomic-embed-text (~50ms) → ChromaDB cosine search → cache hit if distance < 0.25 and confidence >= 0.85. Fallback: exact fingerprint match in SQLite.
- Negative caching stores failures with `CorrectionEntry` records for self-correction hints.
- Experience hints injected into system prompt based on past failures and successes.
- Backfill migration on startup: if vector collection is empty but SQLite has records, all task texts are embedded and upserted.

### Notification System with Greeting Briefings (shipped)

Task-driven notification queue:

- Tasks produce notifications on completion (type=`task_result`, body=first 200 chars).
- SSE `notification_new` events update the frontend badge count in real-time.
- **Greeting briefing**: When the first message of a conversation is a greeting, pending notifications are injected as system context and the LLM produces a natural briefing. Notifications are dismissed after presentation.

## Roadmap — Planned

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

## Version Summary

| Version | Status | Features |
|---------|--------|----------|
| v2.0.0 | **Shipped** | Voice (Piper TTS + faster-whisper STT), email scanner with classification + auto-filing, reminder service, experience cache / procedural memory, notification system with greeting briefings |
| v2.1.0 | Planned | Multi-channel (Slack, Discord) |
| v2.2.0 | Planned | System monitoring manifests |
| v2.3.0 | Planned | Big LLM escalation improvements (streaming, failover, cost tracking) |

## Design Principles

1. **Local-first**: Core inference runs on your hardware. Cloud APIs are optional escalation, never required.
2. **No cloud APIs for voice**: faster-whisper for STT, Piper for TTS. Your voice data stays local.
3. **Apple Silicon optimized**: CTranslate2 (faster-whisper), Piper, and Ollama all leverage Metal/CoreML.
4. **Progressive enhancement**: Voice, email, reminders are additive — the text chat experience is unchanged without them.
5. **Review before send**: STT fills the input box, not auto-sends. The user stays in control.
