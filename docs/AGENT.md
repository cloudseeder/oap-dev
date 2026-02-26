# OAP Agent — Chat + Autonomous Task Execution

A web application that combines interactive chat with background autonomous task execution, powered by OAP manifest discovery. The first Ollama web UI that does both.

## Why This Exists

Every Ollama web UI — Open WebUI, Lobe Chat, LibreChat — is synchronous chat only. You type, the model responds, you type again. None of them can run tasks in the background on a schedule.

Meanwhile, autonomous agent frameworks (AutoGPT, CrewAI) are complex orchestration platforms designed for multi-step reasoning chains. They're powerful but heavy — not what you need when you want a simple cron job that asks an LLM to summarize today's logs every morning.

OAP already solves the hard part: runtime capability discovery. The discovery service finds the right tool for any natural language task, executes it, and learns from the result. The agent app is a thin UI layer on top — a reference implementation demonstrating what OAP makes possible.

The gap it fills:

| Feature | Open WebUI | Lobe Chat | OAP Agent |
|---------|-----------|-----------|-----------|
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
  └─ /v1/agent/*    → FastAPI backend (same server)
                       │
                       ├──POST /v1/chat──▶  oap_discovery (:8300)
                       │                      tool discovery + execution
                       │  SQLite (oap_agent.db)  experience / procedural memory
                       │  APScheduler (cron)     Ollama (qwen3:8b)
                       │  SSE event bus
```

Self-contained: one `oap-agent-api` command serves both the FastAPI API and the Vite SPA at `http://localhost:8303`. No Node runtime, no Vercel involvement, no proxy layer. The agent backend is a thin orchestrator — it calls `/v1/chat` on the discovery service for all LLM and tool work. It never talks to Ollama directly.

### Why a Separate Service?

The discovery service (`oap_discovery`, :8300) handles tool finding, execution, and procedural memory. It's stateless per request — no conversations, no persistence, no scheduling.

The agent service adds the stateful layer: conversation history, task definitions, cron scheduling, and real-time event notifications. Keeping it separate means the discovery service stays focused and the agent is optional — you can use OAP discovery via CLI (`ollama run`), MCP (Claude Desktop), OpenAPI (Open WebUI), or the agent app.

## Backend: `reference/oap_agent/`

### Data Model

Four SQLite tables, WAL journal mode, foreign keys enforced:

- **conversations** — id, title, model, timestamps
- **messages** — id, conversation_id (FK), role, content, tool_calls (JSON), metadata (JSON), seq (ordering)
- **tasks** — id, name, prompt, schedule (cron expression), model, enabled flag, timestamps
- **task_runs** — id, task_id (FK), status (running/success/error), prompt, response, tool_calls (JSON), error, duration_ms

IDs are prefixed short UUIDs: `conv_`, `msg_`, `task_`, `run_`.

### API Endpoints

All local-only on `:8303`. No authentication — the agent is a local tool, not exposed publicly.

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

**Events + Health:**
- `GET /v1/agent/events` — SSE stream for background task notifications (task_run_started, task_run_finished)
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

### SSE Event Bus

In-memory pub/sub: one `asyncio.Queue` (maxsize 100) per connected SSE client, capped at 50 subscribers. Emits `task_run_started` and `task_run_finished` events. Missed events when the browser is closed are acceptable — the user sees results on next visit via run history.

### Files

```
reference/oap_agent/
  pyproject.toml          -- deps: fastapi, uvicorn, httpx, pyyaml, apscheduler<4, croniter
  config.yaml             -- default config (host, port, db path, discovery URL)
  oap_agent/
    __init__.py
    config.py             -- AgentConfig dataclass + YAML loader + URL validation
    db.py                 -- AgentDB: SQLite schema + CRUD, thread-safe writes
    executor.py           -- execute_chat(), execute_task() — calls /v1/chat on discovery service
    scheduler.py          -- APScheduler setup, task loading, dynamic job management
    events.py             -- EventBus class (asyncio.Queue per subscriber, 50 cap)
    api.py                -- FastAPI app: routes, SSE streaming, Pydantic models, lifespan, StaticFiles mount, main()
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
      lib/types.ts        -- TypeScript types (Conversation, Message, ToolCall, AgentTask, TaskRun) + parseSSE()
      components/         -- AgentLayout, AgentSidebar, ChatView, ChatMessage, ChatInput,
                             AgentEventProvider, TaskList, TaskDetail, TaskForm, TaskRunDetail,
                             ToolCallCard, ExperienceBadge, CronInput
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
  AgentSidebar.tsx         -- Dark sidebar (bg-gray-900): conversation list, "New Chat" button, "Tasks" link
  AgentEventProvider.tsx   -- React context wrapping EventSource for background task notifications
  ChatView.tsx             -- Message list + input + SSE stream handling + auto-scroll
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

The agent UI is a standalone app layout — full-height sidebar:

```
┌──────────────┬──────────────────────────────────────────┐
│ [+] New Chat │                                          │
│              │  [user] Find all log files > 100MB       │
│ Conversations│                                          │
│ > Log files  │  [tool: oap_exec] find / -name '*.log'  │
│   Data parse │    → /var/log/syslog.1 (145MB)    234ms │
│              │                                          │
│ ── Tasks ──  │  [assistant] Found 3 log files...       │
│ > Health chk │  [cache: miss] [round: 1/3]             │
│   Daily rpt  │                                          │
│              │ ┌────────────────────────────────────┐   │
│              │ │ Type a message...         [Send] ▶ │   │
│              │ └────────────────────────────────────┘   │
└──────────────┴──────────────────────────────────────────┘
```

## Security

The agent is designed for local use on the Mac Mini — no public exposure, no tunnel.

- **Input validation**: Pydantic models with `max_length` constraints (32K for messages/prompts, 200 for names, 64 for IDs). Model allowlist (`qwen3:8b`, `qwen3:4b`, `llama3.2:3b`, `mistral:7b`). Cron validation rejects schedules more frequent than every 5 minutes. Max 20 tasks.
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
