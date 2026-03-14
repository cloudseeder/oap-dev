# Manifest: A Companion Chat App Built on OAP

Manifest is a companion chat app with autonomous task execution, running entirely on a Mac Mini. It uses OAP manifest discovery to give a small language model (qwen3:8b) the ability to discover and invoke tools at runtime — no hardcoded integrations, no retraining.

The project started as a proof-of-concept for the OAP spec and evolved into a real product: a conversational assistant for a family member with memory issues, combining chat, scheduled background tasks, reminders, email scanning, and voice I/O.

## How It Uses OAP

Manifest is a thin orchestrator. The agent never talks to Ollama directly — every user message is forwarded to the discovery service's `/v1/chat` endpoint, which handles tool discovery, injection, execution, and response synthesis.

```
User → Agent UI → /v1/chat → Discovery Service → Ollama
                                  ↓
                           Tool Discovery (vector search + LLM ranking)
                                  ↓
                           Tool Injection (up to 3 tools per round)
                                  ↓
                           Tool Execution (HTTP APIs, CLI via oap_exec)
                                  ↓
                           Response Synthesis
```

When a user asks "what's the weather in Portland?", the discovery service:

1. Embeds the query with nomic-embed-text
2. Searches the manifest index (ChromaDB vectors + SQLite FTS5)
3. Ranks matches with the small LLM
4. Injects the top manifest(s) as Ollama tool definitions
5. The LLM calls the tool, discovery executes it, and returns the result

The agent doesn't know about weather APIs, news APIs, or any specific tool. It only knows how to forward messages to `/v1/chat`. Everything else is discovered from manifests at runtime.

## Architecture

Four services, all on a single Mac Mini (M4, 16GB):

| Service | Port | Role |
|---------|------|------|
| Discovery | 8300 | Manifest index, tool bridge, experience cache, Ollama proxy |
| Agent | 8303 | Chat UI, task scheduler, voice I/O |
| Reminder | 8304 | Recurring reminders with due dates |
| Email | 8305 | IMAP scanner with LLM classification |

All inter-service communication is HTTP. All services auto-start on reboot via macOS launchd.

## The Tool Bridge

The tool bridge (`POST /v1/chat`) is the key OAP integration. It makes the discovery service a drop-in Ollama replacement — the agent (or any Ollama client) gets transparent tool use without knowing OAP exists.

For each chat round:

- **oap_exec** is always injected as the first tool — a meta-tool that lets the LLM run shell commands (with PATH allowlist, blocked commands, and macOS sandbox protection)
- Up to **3 additional tools** are discovered from the manifest index, deduped by domain
- **Credential injection** adds API keys from `credentials.yaml` at execution time — the LLM never sees the keys
- **Stdio tools are suppressed** — small LLMs produce better results with `oap_exec` than with named CLI tool wrappers

The bridge also supports streaming, multi-round tool loops, and an Ollama-compatible `/api/chat` endpoint.

## Experience Cache (Procedural Memory)

Manifest implements the [procedural memory](procedural-memory) concept from the OAP research. After a successful tool invocation, the task, manifest, and result are cached in a dual-store architecture:

- **SQLite** — system of record for invocation history
- **ChromaDB vectors** — embedding similarity lookup for cache hits

On subsequent similar requests, the cache is checked first (cosine distance < 0.25). Cache hits skip discovery entirely and replay the cached invocation — turning a 3-5 second discovery+ranking flow into a ~50ms embedding lookup.

The cache degrades gracefully: errors reduce confidence scores, and negative results are cached with correction hints so the system learns from failures.

## Big LLM Escalation

For complex queries that benefit from stronger reasoning, Manifest can escalate the final response step to an external large LLM (Claude, GPT-4, or Gemini) while keeping the small model for tool discovery and execution. This gives you the cost and latency benefits of a local model for tool routing, with the quality of a frontier model for the answer.

Escalation triggers automatically when:
- The task fingerprint matches configured prefixes (e.g., `compute`, `search`)
- A tool result exceeds the summarization threshold (16k chars)

## Chat Priority

Ollama processes requests serially — a running background task blocks conversational responses. Manifest solves this with a priority system:

- If a background task is running and a user sends a message, the task is cancelled (it retries on next cron schedule)
- If escalation is configured, conversational messages are routed to the big LLM instead, letting the task finish on Ollama
- Tool-requiring messages always go through Ollama (they need discovery), so tasks are cancelled regardless

## Manifests in Use

Manifest ships with 7 curated manifests covering the most common needs:

| Manifest | Type | What It Does |
|----------|------|-------------|
| open-meteo | HTTP API | Weather forecasts and current conditions |
| wikipedia | HTTP API | Article summaries and search |
| alpha-vantage | HTTP API | Stock quotes and financial data |
| newsapi-top-headlines | HTTP API | Breaking news by country/category |
| newsapi-everything | HTTP API | Full-text news search |
| oap-reminder | Local service | Create, list, complete reminders |
| oap-email | Local service | Search and summarize emails |

CLI tools (grep, jq, date, curl, etc.) don't need manifests — `oap_exec` handles them directly using the LLM's training knowledge.

## Voice

Manifest includes local voice I/O:

- **STT**: faster-whisper (CTranslate2) transcribes speech on the Mac Mini — no cloud API
- **TTS**: Piper neural voices synthesize responses locally

Both are optional and configured in the agent's `config.yaml`. See [Piper TTS](piper) for voice model setup.

## User Memory

The agent learns facts about the user from conversations via fire-and-forget LLM extraction. Facts like "prefers morning briefings" or "allergic to shellfish" are stored in SQLite with dedup and LRU eviction, then injected into future conversations as system context.

## Getting Started

Manifest is open source under CC0:

```bash
git clone https://github.com/cloudseeder/manifest.git
cd manifest
./setup.sh
```

Prerequisites: macOS with Homebrew, Python 3.12, Ollama with qwen3:8b and nomic-embed-text.

See the [manifest repo](https://github.com/cloudseeder/manifest) for full setup instructions.
