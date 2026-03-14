# Manifest — Chat + Autonomous Task Execution

A web application that combines interactive chat with background autonomous task execution, powered by OAP manifest discovery. The first Ollama web UI that does both.

## Why This Exists

Every Ollama web UI — Open WebUI, Lobe Chat, LibreChat — is synchronous chat only. You type, the model responds, you type again. None of them can run tasks in the background on a schedule.

Meanwhile, autonomous agent frameworks (AutoGPT, CrewAI) are complex orchestration platforms designed for multi-step reasoning chains. They're powerful but heavy — not what you need when you want a simple cron job that asks an LLM to summarize today's logs every morning.

OAP already solves the hard part: runtime capability discovery. The discovery service finds the right tool for any natural language task, executes it, and learns from the result. Manifest is a thin UI layer on top — a reference implementation demonstrating what OAP makes possible.

The gap it fills:

| Feature | Open WebUI | Lobe Chat | Manifest |
|---------|-----------|-----------|----------|
| Interactive chat | Yes | Yes | Yes |
| Tool calling | Yes (manual config) | Limited | Yes (auto-discovered) |
| Background tasks | No | No | Yes (cron) |
| Tool discovery | No | No | Yes (OAP manifests) |
| Procedural memory | No | No | Yes (experience cache) |

## Architecture

```
Browser → http://localhost:8303
  ├─ /              → Vite SPA (index.html, React Router)
  ├─ /chat          → SPA client-side route
  ├─ /chat/:id      → SPA client-side route
  ├─ /tasks         → SPA client-side route
  ├─ /tasks/:id     → SPA client-side route
  ├─ /settings      → SPA client-side route
  └─ /v1/agent/*    → FastAPI backend (same server)
                       │
                       ├──POST /v1/chat──▶  oap_discovery (:8300)
                       │                      tool discovery + execution
                       │  SQLite (oap_agent.db)  experience / procedural memory
                       │  APScheduler (cron)     Ollama (qwen3:8b + nomic-embed-text)
                       │  SSE event bus          Piper TTS, faster-whisper STT
                       │  Notification queue
```

Self-contained: one `oap-agent-api` command serves both the FastAPI API and the Vite SPA at `http://localhost:8303`. No Node runtime, no Vercel involvement, no proxy layer. Manifest's backend is a thin orchestrator — it calls `/v1/chat` on the discovery service for all LLM and tool work. It never talks to Ollama directly.

### Why a Separate Service?

The discovery service (`oap_discovery`, :8300) handles tool finding, execution, and procedural memory. It's stateless per request — no conversations, no persistence, no scheduling.

The agent service adds the stateful layer: conversation history, task definitions, cron scheduling, and real-time event notifications. Keeping it separate means the discovery service stays focused and the agent is optional — you can use OAP discovery via CLI (`ollama run`), MCP (Claude Desktop), OpenAPI (Open WebUI), or Manifest.

### Integrated Services

Manifest doesn't call these services directly — it sends tasks to the discovery service (`/v1/chat`), which discovers and invokes the right manifests. But scheduled tasks make these services particularly useful:

- **Email scanner** (`oap-email-api` :8305) — IMAP scanning with LLM-powered classification and auto-filing. A scheduled task like "check my email for new personal messages" discovers the email manifest, queries the scanner, and produces a notification with the summary. Tasks can also trigger classification and filing.
- **Reminder service** (`oap-reminder-api` :8304) — SQLite-backed reminders with recurrence support. A scheduled task like "check for due reminders" discovers the reminder manifest and surfaces due items in the notification queue. Chat can also create reminders conversationally ("remind me to call mom Friday at 2pm").

Both services have OAP manifests in `reference/oap_discovery/manifests/` and are auto-indexed by the discovery service on startup.

## Backend: `reference/oap_agent/`

### Data Model

SQLite tables, WAL journal mode, foreign keys enforced:

- **conversations** — id, title, model, timestamps
- **messages** — id, conversation_id (FK), role, content, tool_calls (JSON), metadata (JSON), seq (ordering)
- **tasks** — id, name, prompt, schedule (cron expression), model, enabled flag, timestamps
- **task_runs** — id, task_id (FK), status (running/success/error), prompt, response, tool_calls (JSON), error, duration_ms
- **notifications** — id, type, title, body, source, task_id (FK), run_id, priority, dismissed, created_at
- **agent_settings** — key/value pairs (persona, voice config, last_greeting_at, etc.)
- **user_facts** — extracted facts about the user from conversation history
- **llm_usage** — per-request token accounting (provider, model, tokens_in, tokens_out, cost)

IDs are prefixed short UUIDs: `conv_`, `msg_`, `task_`, `run_`, `notif_`.

### API Endpoints

All local-only on `:8303`. No authentication — Manifest is a local tool, not exposed publicly.

**Chat:**
- `POST /v1/agent/chat` — send message, returns SSE stream (message_saved → tool_call* → assistant_message → done)
- `GET /v1/agent/conversations` — list (paginated)
- `POST /v1/agent/conversations` — create
- `GET /v1/agent/conversations/{id}` — get with messages
- `PATCH /v1/agent/conversations/{id}` — update title/model
- `DELETE /v1/agent/conversations/{id}` — delete

**Tasks:**
- `GET /v1/agent/tasks` — list all
- `POST /v1/agent/tasks` — create (validated: model allowlist, cron frequency >= 5 min, max 20 tasks)
- `GET /v1/agent/tasks/{id}` — get with recent runs
- `PATCH /v1/agent/tasks/{id}` — update
- `DELETE /v1/agent/tasks/{id}` — delete
- `POST /v1/agent/tasks/{id}/run` — trigger immediate execution
- `GET /v1/agent/tasks/{id}/runs` — list runs (paginated)

**Notifications:**
- `GET /v1/agent/notifications` — list pending (undismissed) notifications
- `GET /v1/agent/notifications/count` — pending count
- `POST /v1/agent/notifications/{id}/dismiss` — dismiss one
- `POST /v1/agent/notifications/dismiss-all` — dismiss all

**Events + Health:**
- `GET /v1/agent/events` — SSE stream (task_run_started, task_run_finished, notification_new)
- `GET /v1/agent/health` — health check

### Chat Flow

`POST /v1/agent/chat` accepts `{conversation_id, message, model}` and returns SSE:

1. Save user message to DB → emit `event: message_saved`
2. Build messages array from conversation history
3. `POST http://localhost:8300/v1/chat` with `stream: false`
4. Parse response + debug trace → emit `event: tool_call` for each tool execution
5. Save assistant message to DB → emit `event: assistant_message`
6. Emit `event: done`

SSE (not NDJSON) because `EventSource` has auto-reconnect and better browser support. The discovery service processes everything non-streaming internally (tool loops need full responses), so there are no incremental tokens to stream.

### Task Scheduler

APScheduler 3.x `AsyncIOScheduler` runs in-process, integrating with FastAPI's event loop. `croniter` computes next run times and validates that schedules fire no more frequently than every 5 minutes.

On startup: load all enabled tasks from DB, schedule each with `CronTrigger.from_crontab()`. Tasks created/updated/deleted at runtime dynamically update the scheduler.

Task execution follows the same path as chat — single user message → `/v1/chat` → store result in `task_runs` — but without conversation context.

**Chat priority over tasks.** Ollama processes requests serially per model, so a running background task (e.g. hourly email summary) blocks conversational responses. The agent detects this and routes around the contention:

| Ollama busy? | Conversational? | Escalation enabled? | Action |
|---|---|---|---|
| Yes | Yes | Yes | Escalate to big LLM — task keeps running on Ollama |
| Yes | Yes | No | Cancel task, use Ollama |
| Yes | No (tools) | — | Cancel task, use Ollama (tools need discovery) |
| No | — | — | Normal path, no change |

When escalation is enabled, conversational messages go to the configured big LLM (Claude, GPT-4, etc.) while the task finishes on Ollama — both get served. Tool-route messages always cancel the task because they need discovery on Ollama. If escalation fails (bad key, timeout), falls back to cancel+Ollama. Cancelled tasks retry on their next cron schedule.

Config:
```yaml
escalation:
  enabled: true
  provider: anthropic    # or openai, googleai
  model: claude-sonnet-4-6
  timeout: 60
  max_tokens: 4096
```

API key resolution: `escalation.api_key` > `OAP_ESCALATION_API_KEY` > provider-specific (`OAP_ANTHROPIC_API_KEY`, `OAP_OPENAI_API_KEY`, `OAP_GOOGLEAI_API_KEY`).

### SSE Event Bus

In-memory pub/sub: one `asyncio.Queue` (maxsize 100) per connected SSE client, capped at 50 subscribers. Missed events when the browser is closed are acceptable — the user sees results on next visit via run history.

Events:

| Event | Payload | When |
|-------|---------|------|
| `task_run_started` | `{task_id, run_id, task_name}` | Scheduler begins executing a task |
| `task_run_finished` | `{task_id, run_id, status, duration_ms, ?error, ?task_name}` | Task execution completes or fails |
| `notification_new` | `{task_name, count}` | New notification created (count = total pending) |

### Notification Queue

Tasks produce results. Notifications make those results visible — surfaced in the greeting briefing, the avatar badge, and (future) ambient push channels like presence-triggered announcements.

**Flow:**

```
Scheduler runs task
  → task succeeds
  → scheduler creates notification (type=task_result, title=task name, body=full task result)
  → EventBus publishes notification_new
  → frontend SSE listener updates badge count
  → user opens chat, says "good morning"
  → greeting handler reads pending notifications, formats as multi-line bullet list
  → greeting handler dismisses all presented notifications
  → briefing presented directly to user (no LLM reprocessing — avoids latency and hallucination)
  → frontend refreshes badge count (now 0)
```

**Notification schema:**

| Field | Type | Description |
|-------|------|-------------|
| id | text | `notif_` + short UUID |
| type | text | `task_result` (extensible: `email_summary`, `reminder_due`, etc.) |
| title | text | Human-readable title (typically the task name) |
| body | text | Full task result (raw JSON filtered out, no-news results suppressed via regex) |
| source | text | Producer identifier (`scheduler`, future: `email`, `reminder`) |
| task_id | text | FK to tasks table (nullable) |
| run_id | text | Associated task run (nullable) |
| priority | int | 0 = normal, higher = more important (for future ordering) |
| dismissed | int | 0 = pending, 1 = dismissed |
| created_at | text | ISO 8601 timestamp |

**Design decisions:**

- **Notifications are the only briefing source.** The greeting handler doesn't call external APIs directly — it reads the notification queue. Scheduled tasks that call the email scanner or reminder service produce notifications like any other task. This keeps the agent thin and the data flow uniform.
- **Full results, not snippets.** Notification body stores the complete task result rather than a truncated snippet. Raw JSON responses are filtered out (only human-readable text is stored). A no-news regex suppresses empty or "nothing to report" results from creating notifications at all.
- **Dismissed after presentation.** The greeting handler dismisses all pending notifications after injecting them. This prevents the same results from appearing in the next greeting.
- **Cleanup.** `cleanup_notifications(days=7)` deletes old dismissed notifications. Can be called from a maintenance cron or startup.
- **Extensible type field.** Currently only `task_result`. Future producers (calendar, etc.) add new types without schema changes.

### Greeting Briefing

When a user opens a new conversation with a greeting ("hello", "good morning", "hey"), the agent produces a contextual briefing instead of a generic response.

**Detection:** Regex match on the first message of a conversation. Patterns: hello, hey, hi, good morning/afternoon/evening, what's up, howdy, etc.

**Presentation:** Pending notifications are formatted as a multi-line bullet list and presented directly to the user — the greeting handler builds the briefing itself rather than sending notifications through the LLM. This avoids latency (no extra LLM round-trip) and hallucination (the LLM can't misinterpret or embellish task results). Each notification becomes a labeled bullet:

```
Good morning! Here's your briefing:

• MyNewscast: Top stories: Portland weather clearing, trimet service restored...
• Email Summary: 3 new personal messages — Amy re: dinner Friday, Keric re: network config...
• Reminders: Submit quarterly report (due today)
```

After presentation, all presented notifications are dismissed.

**No notifications?** The greeting falls through to the normal conversational route — a simple friendly response with no briefing.

### Files

```
reference/oap_agent/
  pyproject.toml          -- deps: fastapi, uvicorn, httpx, pyyaml, apscheduler<4, croniter
  config.yaml             -- default config (host, port, db path, discovery URL)
  oap_agent/
    __init__.py
    config.py             -- AgentConfig dataclass + YAML loader + URL validation
    db.py                 -- AgentDB: SQLite schema + CRUD + notifications, thread-safe writes
    executor.py           -- execute_chat(), execute_task() — calls /v1/chat on discovery service
    scheduler.py          -- APScheduler setup, task loading, notification creation on completion
    events.py             -- EventBus class (asyncio.Queue per subscriber, 50 cap)
    memory.py             -- User fact extraction via fire-and-forget LLM call
    transcribe.py         -- Whisper STT via faster-whisper (CTranslate2)
    tts.py                -- Piper neural TTS — text to WAV
    api.py                -- FastAPI app: routes, SSE, greeting briefing, notifications, voice, StaticFiles, main()
    static/               -- Built Vite SPA output (committed, no Node runtime needed)
  frontend/
    package.json          -- react 19, react-router 7, tailwindcss 4, vite 6
    vite.config.ts        -- build output to ../oap_agent/static/, dev proxy to :8303
    tsconfig.json
    index.html
    src/
      main.tsx            -- React app with BrowserRouter
      App.tsx             -- React Router routes
      index.css           -- Tailwind CSS 4 with OAP theme
      lib/types.ts        -- TypeScript types (Conversation, Message, ToolCall, AgentTask, TaskRun, AgentSettings) + parseSSE()
      lib/personaStyles.ts -- Persona visual styles (shape, color, animation parameters)
      hooks/              -- useAvatarAnimation (idle/speaking/listening/thinking/attentive + notification pulse),
                             useAvatarState, useVoiceRecorder, useTTS
      components/         -- AgentLayout, AgentSidebar, ChatView, ChatMessage, ChatInput,
                             AgentEventProvider (SSE + notification count), PersonaAvatar (canvas animation + badge),
                             AvatarDisplay, TaskList, TaskDetail, TaskForm, TaskRunDetail,
                             ToolCallCard, ExperienceBadge, CronInput, Markdown, SettingsView
```

Entry point: `oap-agent-api` (installed via `pip install -e reference/oap_agent`).

## Frontend: Vite SPA

Standalone React SPA served by FastAPI's `StaticFiles` mount. No Node runtime on the server — built output is committed to `oap_agent/static/`.

### Routes (client-side, React Router)

- `/` — redirect to `/chat`
- `/chat` — new conversation
- `/chat/:id` — existing conversation
- `/tasks` — task list + create
- `/tasks/:id` — task detail + run history

All API calls go to `/v1/agent/*` directly (same origin, no proxy layer).

### Components

```
frontend/src/components/
  AgentLayout.tsx          -- Full-height layout: sidebar + <Outlet> + EventProvider
  AgentSidebar.tsx         -- Dark sidebar: conversation list, persona avatar with notification badge, nav links
  AgentEventProvider.tsx   -- React context: EventSource SSE, toast notifications, notification count tracking
  ChatView.tsx             -- Message list + input + SSE stream handling + auto-scroll + notification refresh
  ChatMessage.tsx          -- Message bubble (user/assistant) with tool calls + experience badge
  ChatInput.tsx            -- Textarea + send + model selector
  ToolCallCard.tsx         -- Expandable: tool name, args, result, duration
  ExperienceBadge.tsx      -- Cache hit (green) / miss (gray) / degraded (yellow) badge
  TaskList.tsx             -- Task table with enable/disable toggles + create form
  TaskForm.tsx             -- Create/edit: name, prompt, schedule, model
  TaskDetail.tsx           -- Task info + "Run Now" button + run history
  TaskRunDetail.tsx        -- Expandable run: status badge, prompt, response, tools
  CronInput.tsx            -- Cron expression input + presets dropdown + human-readable description
```

### Dev Workflow

```bash
cd reference/oap_agent/frontend
npm install
npm run dev    # Vite at :5173, proxies /v1/agent → :8303
npm run build  # Output to ../oap_agent/static/
```

### Layout

Manifest's UI is a standalone app layout — full-height sidebar:

```
┌──────────────┬──────────────────────────────────────────┐
│ [+] New Chat │                                          │
│              │  [user] Good morning!                    │
│ Conversations│                                          │
│ > Log files  │  [assistant] Good morning! Here's your  │
│   Data parse │  briefing:                               │
│              │  • MyNewscast found 3 stories...         │
│  ┌────────┐  │  • Email: 2 new from netgate.net         │
│  │ ◉  (3) │  │                                          │
│  │ avatar │  │                                          │
│  └────────┘  │                                          │
│              │ ┌────────────────────────────────────┐   │
│ Tasks  Settn │ │ Type a message...         [Send] ▶ │   │
│              │ └────────────────────────────────────┘   │
└──────────────┴──────────────────────────────────────────┘
```

The persona avatar in the sidebar shows a red notification badge with the pending count. When notifications are pending and the avatar is idle, a gentle pulsing halo animation signals "I have something to tell you." The badge and halo clear when notifications are dismissed (either via greeting or manually).

## Voice

Local-first voice input and output — no cloud APIs, no browser Web Speech API.

**Speech-to-text (STT):** `faster-whisper` (CTranslate2) on the backend. The browser records via MediaRecorder (WebM), sends to `POST /v1/agent/transcribe`, and the transcribed text appears in the chat input. Configurable model size (tiny/base/small), device (auto/cpu/cuda), and compute type.

**Text-to-speech (TTS):** Piper neural TTS on the backend. `POST /v1/agent/tts` accepts text and returns WAV audio. `_clean_for_speech()` strips timestamps, URLs, markdown formatting, and other non-speakable content before synthesis. The frontend plays audio via `HTMLAudioElement` with a stop-speaking button to interrupt playback. Voice model configured via `voice.tts_model_path` (path to `.onnx` voice file).

**Settings (persisted in `agent_settings`):**
- `voice_input_enabled` — show mic button in chat input
- `voice_auto_send` — automatically send after transcription completes
- `voice_auto_speak` — automatically speak assistant responses

**Current flow:** Press mic button → record → release → transcribe → text in input → (auto-send or manual send) → response → (auto-speak or manual). Wake word detection is planned but not yet implemented — currently requires manual mic activation.

### Conversation Management

Conversations can be deleted from the sidebar UI. Hover over a conversation in the sidebar to reveal a delete button. Deletion removes the conversation and all associated messages from the database.

## Known Limitations

The small LLM (qwen3:8b) runs with `num_ctx: 4096` (~12-16K chars) due to the Mac Mini's 16GB shared VRAM — qwen3:8b at 4K context uses ~5.9GB, leaving room for nomic-embed-text alongside it.

- **Files under ~12K chars**: processed directly by the small LLM — no issues
- **Files 12-16K chars**: tight but generally works within the 4096-token context window
- **Files >16K chars**: exceed the small LLM's context window. When `escalation.enabled: true`, these are automatically escalated to the big LLM (Claude, GPT-4 — 200K/128K context) which processes the raw output. When escalation is not configured, falls back to map-reduce summarization via `ollama.generate()`, which is lossy — especially on prose and markdown
- **VRAM constraint**: 16GB shared between CPU and GPU on M4. Increasing `num_ctx` would push VRAM usage beyond what's available

## Security

Manifest is designed for local use on the Mac Mini — no public exposure, no tunnel.

- **Input validation**: Pydantic models with `max_length` constraints (32K for messages/prompts, 200 for names, 64 for IDs). Model names validated by length (max 100 chars), available models fetched dynamically from Ollama `/api/tags`. Cron validation rejects schedules more frequent than every 5 minutes. Max 20 tasks.
- **SQL safety**: parameterized queries throughout, WAL journal mode, `threading.Lock` on all writes.
- **Error sanitization**: generic error messages to SSE clients and API responses. Full details in server logs only.

## Running

```bash
# Install
pip install -e reference/oap_agent

# Start (requires discovery service on :8300)
oap-agent-api                        # defaults: 127.0.0.1:8303
oap-agent-api --config custom.yaml   # custom config

# Health check
curl http://localhost:8303/v1/agent/health

# Open in browser
open http://localhost:8303
```

The SPA is served by FastAPI's `StaticFiles` mount — `html=True` returns `index.html` for all unmatched paths (SPA catch-all). API routes registered first take priority over static files.

### Frontend Development

```bash
cd reference/oap_agent/frontend
npm install
npm run dev      # Vite dev server at :5173, proxies /v1/agent → :8303
npm run build    # Build to ../oap_agent/static/
```
