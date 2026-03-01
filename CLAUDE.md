# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Open Application Protocol (OAP) — a cognitive API layer for artificial intelligence. A manifest spec that lets AI learn about capabilities that weren't in its training data, at runtime, without retraining.

OAP is a **pure spec** with a reference architecture for discovery. It is **not** a registry, service, or platform.

- **Manifest** (`/.well-known/oap.json`) — JSON file describing what a capability does, what it accepts, what it produces, and how to invoke it. Designed to be read and reasoned about by LLMs.
- **Discovery** — Not prescribed by the spec. Reference architecture uses crawlers + local vector DB + FTS5 keyword search + small LLM for intent-to-manifest matching. The web model, not the registry model.
- **Trust** — Separate companion overlay (like TLS is to HTTP). Graduated levels: domain attestation, capability attestation, compliance certification.

Protocol version: 1.0. License: CC0 1.0 (Public Domain).

## Repository Structure

### Spec & Documentation

- `README.md` — Project overview and vision (the public face)
- `docs/SPEC.md` — Manifest specification v1.0 (the authoritative reference)
- `docs/ARCHITECTURE.md` — Reference discovery architecture (local vector DB + small LLM + crawler)
- `docs/TRUST.md` — Trust overlay specification (companion protocol)
- `docs/MANIFESTO.md` — Why manifests are the cognitive API for AI
- `docs/A2A.md` — OAP + A2A integration: how discovery (OAP) and conversation (A2A) complement each other
- `docs/ROBOTICS.md` — OAP for robotics: manifests as the cognitive interface for physical capabilities (sensors, actuators, tools)
- `docs/OAP-PROCEDURAL-MEMORY-PAPER.md` — Procedural memory paper: OAP manifests as learning substrate for small LLMs
- `docs/PATH-TO-23-TOKENS.md` — Path to 23 Tokens: debugging qwen3:4b intent fingerprinting from 3674 tokens/112s to 23 tokens/1.7s
- `docs/OPENCLAW.md` — OpenClaw integration: workspace skill for runtime capability discovery
- `docs/THE-MODEL-THAT-KNEW-TOMORROW.md` — The Model That Knew Tomorrow: how a frozen 8B-parameter LLM answered questions about today's Portland news via runtime manifest discovery
- `docs/OLLAMA.md` — OAP + Ollama: manifest discovery as native Ollama tool calling via the tool bridge
- `docs/OPENAPI-TOOL-SERVER.md` — OpenAPI tool server: exposing manifests as a standard OpenAPI 3.1 spec for Open WebUI, LangChain, etc.
- `docs/MCP.md` — MCP server: exposing manifests as MCP tools for Claude Desktop and MCP clients
- `docs/AGENT.md` — Manifest: chat + autonomous task execution architecture and rationale
- `docs/MANIFEST_2_0.md` — Manifest 2.0 roadmap: OpenClaw comparison, voice, channels, monitoring
- `docs/SECURITY.md` — Security model: defense-in-depth from network isolation to OS sandbox
- `DEPLOYMENT.md` — Mac Mini + Vercel deployment guide (Phase 7)

### Next.js Application (oap.dev)

The site serves as a developer tool: manifest playground, hosted discovery/trust reference services, and an adoption dashboard. Deployed on Vercel.

#### Routes

- `app/(marketing)/` — Landing page, spec, doc pages (quickstart, architecture, trust, a2a, ollama, openapi-tool-server, robotics, procedural-memory, path-to-23-tokens, manifesto)
- `app/playground/` — Manifest playground: validate JSON or fetch+validate from URL
- `app/discover/` — Discovery reference UI: natural language task-to-manifest matching
- `app/trust/` — Trust reference UI: attestation flow + lookup
- `app/dashboard/` — Adoption dashboard: stats, growth chart, manifest list
- `app/api/playground/validate/` — POST: validate manifest JSON or fetch from URL
- `app/api/discover/` — POST proxy to discovery service (:8300)
- `app/api/discover/health/` — GET proxy for discovery health check
- `app/api/discover/manifests/` — GET proxy for manifest listing
- `app/api/trust/[...path]/` — Catch-all proxy to trust service (:8301)
- `app/api/dashboard/stats/` — GET proxy for dashboard statistics (:8302)
- `app/api/dashboard/manifests/` — GET proxy for dashboard manifest list (:8302)

#### Key Libraries

- `lib/manifest-v1.ts` — v1.0 manifest validation (ported from Python reference)
- `lib/types-v1.ts` — v1.0 TypeScript types (ported from Python reference)
- `lib/proxy.ts` — Reusable proxy helper for backend services (via `BACKEND_URL`, `TRUST_URL`, `DASHBOARD_URL` env vars)
- `lib/markdown.ts` — Markdown rendering with unified/remark/rehype pipeline + auto-generated TOC
- `lib/dns.ts` — Manifest fetching (`fetchManifest`, `fetchManifestForDomain`) + DNS verification
- `lib/security.ts` — SSRF protection (private IP blocking, DNS resolution) + rate limiting

#### Key Components

- `components/PlaygroundEditor.tsx` — Client-side JSON editor + URL fetch + validation
- `components/PlaygroundResult.tsx` — Validation results (errors/warnings) + manifest preview
- `components/ManifestViewer.tsx` — Structured v1.0 manifest display
- `components/DiscoverSearch.tsx` — Natural language discovery input + results
- `components/TrustFlow.tsx` — Step-by-step domain attestation (Layer 0 checks → challenge → verify)
- `components/TrustLookup.tsx` — Look up existing attestations for any domain
- `components/DashboardStats.tsx` — Stat cards + inline SVG growth chart
- `components/DashboardManifestList.tsx` — Paginated manifest table with health badges
- `components/DiscoverResult.tsx` — Discovery search result cards
- `components/CodeBlock.tsx` — Syntax-highlighted code display
- `components/Footer.tsx` — Site footer with navigation links
- `components/TrustBadges.tsx` — Trust level badge display

### Python Reference Services

All four services live under `reference/` and install as editable Python packages with entry-point commands.

#### Discovery (`reference/oap_discovery/`)

Crawls domains for manifests, embeds descriptions into ChromaDB via Ollama (nomic-embed-text), and serves a discovery API that matches natural language tasks to manifests using vector search + FTS5 keyword search + small LLM (qwen3:8b).

- Entry points: `oap-api` (:8300), `oap-crawl`, `oap`
- CLI auth: `oap --token <secret>` or `OAP_BACKEND_TOKEN` env var. Required when `OAP_BACKEND_SECRET` is set on the server.
- Config: `config.yaml` (Ollama URL, ChromaDB path, FTS path, crawler settings). Gitignored — track `config.yaml.example` instead. Copy to `config.yaml` on first deploy.
- Key files: `models.py` (Pydantic types), `validate.py` (validation), `crawler.py`, `db.py` (ChromaDB), `fts_store.py` (SQLite FTS5), `discovery.py` (vector search + FTS5 + LLM + intent extraction), `api.py` (FastAPI), `ollama_client.py` (Ollama API client), `openapi_server.py` (OpenAPI 3.1 tool server), `config.py` (configuration), `cli.py` (CLI entry point)
- **Intent extraction**: `discovery.py:_extract_search_query(task)` strips inline data and normalizes colloquial language before embedding. Drops data after `\n`, strips trailing prepositions, normalizes verbs (`pull out` → `filter`), appends domain hints. The cleaned query goes to vector search; the full task still goes to LLM ranking unchanged.
- **FTS5 keyword search**: `fts_store.py` provides SQLite FTS5 with BM25 ranking as a complement to vector search. Config: `fts.enabled` (bool, default false), `fts.db_path`. Env overrides: `OAP_FTS_ENABLED`, `OAP_FTS_DB_PATH`. Deterministic keyword matching filling gaps where vector search drifts.
- **Procedural memory** (enabled by default via `experience.enabled: true`): Three-path routing: (1) **cache_hit** — exact fingerprint match → replay cached invocation; (2) **partial_match** — similar fingerprint → validate with discovery then execute; (3) **full_discovery** — no match → full vector search + LLM ranking → execute → cache. SQLite storage at `oap_experience.db`. Files: `experience_models.py`, `experience_store.py`, `experience_engine.py`, `experience_api.py` (router at `/v1/experience/`), `invoker.py`.
- **Ollama tool bridge** (enabled by default via `tool_bridge.enabled: true`): `POST /v1/chat` and `POST /api/chat` — transparent Ollama proxy that discovers tools, injects them, executes tool calls, and loops up to `max_rounds`. The `/api/chat` alias makes OAP a drop-in Ollama replacement (`OLLAMA_HOST=http://localhost:8300 ollama run qwen3:8b`). Streaming wraps final result in Ollama NDJSON format. **Ollama pass-through**: non-chat `/api/*` endpoints proxy directly to Ollama. Tool bridge routes have **no backend token auth** — local-only, secured by Cloudflare Tunnel path filtering. Key files: `tool_models.py`, `tool_converter.py`, `tool_executor.py`, `tool_api.py`.
- **Chat system prompt** (`tool_api.py`): "NEVER answer without calling a tool", API tool preference for web/API data, oap_exec for CLI tasks, pipe/jq examples, inline-text stdin guidance. States "API credentials are pre-configured" so LLMs don't refuse to call authed APIs. Combined with `think: false` (default) keeps qwen3:8b to ~12 tokens per round.
- **Conditional thinking**: `tool_bridge.think_prefixes` (list of fingerprint prefixes, default empty). When a task's fingerprint starts with a listed prefix, `think: true` is sent to Ollama so the model can verify tool output (e.g. arithmetic). Config: `think_prefixes: [compute]`. Debug output includes `thinking_enabled: true/false`.
- **Big LLM escalation**: `tool_bridge.escalate_prefixes` (list of fingerprint prefixes, default empty). When a task's fingerprint starts with a listed prefix and `escalation.enabled: true`, the final reasoning step is sent to an external big LLM (GPT-4, Claude, etc.) instead of the small model. The small model still handles tool discovery and execution. Additionally, large `oap_exec` results (>`summarize_threshold` chars) are automatically escalated to the big LLM when escalation is enabled, bypassing lossy map-reduce summarization — this catches any large-output scenario regardless of fingerprint prefix. Config: `escalate_prefixes: [compute]` + `escalation:` section with `provider` (`openai` or `anthropic`), `base_url`, `model`, `timeout`. API key resolution: `escalation.api_key` > `OAP_ESCALATION_API_KEY` > provider-specific (`OAP_OPENAI_API_KEY`, `OAP_ANTHROPIC_API_KEY`, `OAP_GOOGLEAI_API_KEY`). Per-provider env vars let you switch providers without redeploying. Provider `googleai` uses OpenAI-compatible path with `base_url: https://generativelanguage.googleapis.com/v1beta/openai`. Fails silently — falls back to small LLM response on any error. Debug output includes `escalated: true/false`. Key file: `escalation.py`.
- **Multi-tool injection**: `_discover_tools()` injects up to `MAX_INJECTED_TOOLS = 3` tools per chat round — LLM's top pick plus next highest-scoring candidates (deduped by domain).
- **oap_exec meta-tool**: Built-in tool always injected first in every `/v1/chat` round. Accepts `command` + optional `stdin`. Bridges LLM CLI knowledge to tool calls (LLMs write better regex in CLI syntax than in tool parameters). Supports shell-style pipes via `_split_pipeline()`. Security: `shlex.split()` parsing, PATH allowlist validation (`/usr/bin/`, `/usr/local/bin/`, `/bin/`, `/opt/homebrew/bin/`), `asyncio.create_subprocess_exec()` (no `shell=True`), `blocked_commands` config (default: `[rm, rmdir, dd, mkfs, shutdown, reboot]`) — bare-name matching per pipeline stage via `os.path.basename()` so both `rm` and `/bin/rm` are caught. Override via `tool_bridge.blocked_commands` in `config.yaml`; set to `[]` to allow all. File path detection (`_task_has_file_path`) suppresses discovery when file paths present — `oap_exec` becomes the only tool.
- **Sandbox** (`sandbox.py`): OS-level file-write protection via macOS `sandbox-exec`. All subprocess execution (oap_exec single commands, pipelines, and manifest stdio tools) is wrapped with a Seatbelt profile that denies file writes except to a configurable sandbox directory. Config: `tool_bridge.danger_will_robinson` (default `false` — sandbox ON; set `true` to disable), `tool_bridge.sandbox_dir` (default `/tmp/oap-sandbox`). Env overrides: `OAP_TOOL_BRIDGE_DANGER_WILL_ROBINSON`, `OAP_TOOL_BRIDGE_SANDBOX_DIR`. Graceful degradation on Linux (unsandboxed, warning logged). The system prompt tells the LLM to write output files to the sandbox directory. Three wrapped call sites: `tool_executor.py:_run_single()`, `tool_executor.py:_run_pipeline()`, `invoker.py:_invoke_stdio()`.
- **Stdio tool suppression**: After discovery, stdio tools are filtered out — only `oap_exec` and HTTP/API tools remain. Rationale: small LLMs prefer "named" tools over generic `oap_exec` but produce worse results with them.
- **Credential injection** (`tool_executor.py:_inject_credentials`): Injects API keys from `credentials.yaml` into tool calls at execution time. Supports two placement modes via manifest `invoke.auth_in`:
  - `auth_in: "header"` (default) — key added as HTTP header (name from `auth_name`, default `X-API-Key`)
  - `auth_in: "query"` — key returned as extra query params, merged into request params before `invoke_manifest`
  - `auth: "bearer"` — key added as `Authorization: Bearer <key>` header
  - **Domain lookup**: first tries the indexed domain (e.g. `local/alpha-vantage`), then falls back to the invoke URL hostname (e.g. `www.alphavantage.co`). This lets `credentials.yaml` use real domain names for local manifests.
  - **credentials.yaml format**: domain-keyed YAML, loaded via `config.py:load_credentials()`. Path configured in `tool_bridge.credentials_file` (default `credentials.yaml`, relative to CWD).
  - Credential injection is transparent to the LLM — the system prompt tells it "API credentials are pre-configured" so it always calls the tool.
- **OpenAPI tool server** (enabled when `tool_bridge.enabled: true`): `openapi_server.py` at `/v1/openapi.json` and `/v1/tools/call/{tool_name}`. Standard OpenAPI 3.1 tool server for Open WebUI, LangChain, etc. Exposes all manifests (no stdio suppression). Same security and credential injection as chat flow.
- **Experience cache in tool bridge**: `/v1/chat` uses procedural memory as discovery cache. Flow: fingerprint → cache check → hit (skip discovery) or miss (full discovery → cache on success). Degradation: errors multiply confidence by 0.7, single failure drops below threshold. Negative caching stores failures with `CorrectionEntry` records for self-correction hints.
- **Fingerprint optimization**: `fingerprint_intent()` uses `chat(think=False, temperature=0, format="json")` for deterministic ~15-token output in ~1s. JSON-aware fingerprints separate JSON tasks from text tasks in fingerprint space.
- **Experience hints**: `_build_experience_hints(fingerprint)` injects past failure/success hints into system prompt. Only exact-match failures (prefix matching was too aggressive). Prefix successes suggest what works for similar tasks.
- Local manifests (`reference/oap_discovery/manifests/`): JSON files auto-indexed on startup under `local/<tool-name>` pseudo-domains. Starter set: `apropos.json`, `man.json`, `grep.json`, `jq.json`, `wc.json`, `date.json`, `bc.json` (stdio), plus HTTP API manifests: `alpha-vantage.json`, `newsapi-top-headlines.json`, `newsapi-everything.json`, `open-meteo.json`, `wikipedia.json`, etc.
- **Seed domain crawling on startup**: `api.py` lifespan crawls remote domains from `seeds.txt` after indexing local manifests. Seeds file: `reference/oap_discovery/seeds.txt`.
- **Map-reduce summarization**: fallback for large tool results when big LLM escalation is not configured. Hierarchy: big LLM (if `escalation.enabled`) → map-reduce via `ollama.generate()` → truncation. Configured via `ToolBridgeConfig` fields: `summarize_threshold` (default 16000 chars), `chunk_size`, `max_tool_result`.
- **Debug mode**: `POST /v1/chat` accepts `oap_debug: true` for full execution trace including tools discovered, experience cache status, fingerprint, hints, and per-round tool executions with timing.

#### Trust (`reference/oap_trust/`)

Reference trust provider implementing Layers 0-2: baseline checks, domain attestation via DNS/HTTP challenge, capability testing.

- Entry points: `oap-trust-api` (:8301), `oap-trust`
- Key files: `models.py` (trust types), `attestation.py`, `dns_challenge.py`, `capability_test.py`, `api.py` (FastAPI), `cli.py` (CLI entry point), `config.py` (configuration), `db.py` (SQLite persistence), `keys.py` (Ed25519 key management), `manifest.py` (manifest validation)

#### Dashboard (`reference/oap_dashboard/`)

Adoption tracker: crawls seed domains, stores results in SQLite, serves stats and manifest list.

- Entry points: `oap-dashboard-api` (:8302), `oap-dashboard-crawl`
- Config: `config.yaml` (SQLite path, crawler settings)
- Key files: `db.py` (SQLite schema + CRUD), `crawler.py`, `api.py` (FastAPI)

### Infrastructure

```
Vercel (free tier)                    Mac Mini (M4, 16GB)
┌─────────────────────┐               ┌──────────────────────────────┐
│  Next.js App        │               │  Ollama (qwen3:8b + nomic)   │
│  ├─ Marketing pages │  Cloudflare   │  Discovery API (:8300)       │
│  ├─ Spec docs       │◄── Tunnel ──► │  Trust API (:8301)           │
│  ├─ /playground     │               │  Dashboard API (:8302)       │
│  ├─ /discover       │               │  Manifest (self-contained :8303)│
│  ├─ /trust          │               │  Crawler (cron)              │
│  ├─ /dashboard      │               │  ChromaDB (local dir)        │
│  └─ /api/* (proxy)  │               │  SQLite (*.db)               │
└─────────────────────┘               └──────────────────────────────┘
```

- **Vercel**: Next.js frontend + API route handlers that proxy to the Mac Mini
- **Mac Mini**: All Python services, Ollama, ChromaDB, SQLite
- **Cloudflare Tunnel**: Three hostnames (`api.oap.dev`, `trust.oap.dev`, `dashboard.oap.dev`). Discovery tunnel exposes only `/v1/discover`, `/v1/manifests`, `/health`. Tool bridge, OpenAPI, Ollama pass-through, and experience routes stay local-only on `:8300`.
- **Manifest** (`:8303`): local-only, not tunnel-exposed. Self-contained — serves both FastAPI API and Vite SPA frontend via StaticFiles mount
- **Env vars**: `BACKEND_URL` (discovery), `TRUST_URL`, `DASHBOARD_URL` — Cloudflare Tunnel hostnames; `BACKEND_SECRET` / `OAP_BACKEND_SECRET` — shared auth token
- **Auth model**: Backend token auth (`X-Backend-Token` / `OAP_BACKEND_SECRET`) is per-route, not global. Protected: `/v1/discover`, `/v1/manifests`, `/v1/manifests/{domain}`, `/health`, `/v1/experience/*`. Unprotected (local-only): `/v1/chat`, `/v1/tools`, `/api/chat`, `/v1/openapi.json`, `/v1/tools/call/*`, `/api/tags`, `/api/show`, `/api/ps`, `/api/generate`, `/api/embed`, `/api/embeddings`
- **Ollama tuning**: `num_ctx: 4096` (caps VRAM on 16GB), `timeout: 120`, `keep_alive: "-1m"` (permanent model loading). Model warmup on startup via throwaway `generate("hello")`. Override with `OAP_OLLAMA_NUM_CTX`. qwen3:8b at 4k context uses ~5.9GB VRAM, fitting alongside nomic-embed-text.
- **Setup script**: `scripts/setup-mac-mini.sh` — generates backend secret, creates launchd plists, loads services, runs health checks
- **Manifest factory**: `scripts/manifest-factory.py` — auto-generates OAP manifests from documentation sources via qwen3:8b. Pluggable `SourceAdapter` classes. CLI: `--source manpage|help|openapi`, `--dry-run`, `--tools sed,awk,cut`, `--ollama-url`. Adapters: ManPageAdapter (man pages), HelpAdapter (`--help` output), OpenAPIAdapter (OpenAPI 3.x / Swagger 2.x specs).

#### Manifest (`reference/oap_agent/`)

Manifest — chat + autonomous task execution. Thin orchestrator that calls `/v1/chat` on the discovery service for all LLM and tool work — never talks to Ollama directly. Combines interactive conversation with cron-scheduled background tasks. Self-contained: `oap-agent-api` serves both API and UI at `http://localhost:8303` — no Node runtime, no Vercel involvement.

- Entry point: `oap-agent-api` (:8303) — serves both FastAPI backend and Vite SPA frontend
- Config: `config.yaml` (host, port, SQLite path, discovery URL/model/timeout, debug flag, max_tasks)
- Key files: `config.py`, `db.py` (SQLite: conversations, messages, tasks, task_runs, agent_settings, user_facts — WAL mode, foreign keys), `executor.py` (calls `/v1/chat` on discovery), `scheduler.py` (APScheduler 3.x), `events.py` (EventBus), `api.py` (FastAPI + SSE + StaticFiles mount), `memory.py` (user fact extraction via Ollama pass-through)
- **Frontend** (`frontend/`): Vite 6 + React 19 + React Router 7 + Tailwind CSS 4 SPA. Built output committed to `oap_agent/static/`. Dev: `cd frontend && npm run dev`. Build: `npm run build` outputs to `../oap_agent/static/`.
- SPA routes: `/` (redirect to `/chat`), `/chat`, `/chat/:id`, `/tasks`, `/tasks/:id`, `/settings`
- API routes: `/v1/agent/chat` (POST SSE), `/v1/agent/conversations` (CRUD), `/v1/agent/tasks` (CRUD), `/v1/agent/tasks/:id/run` (POST), `/v1/agent/tasks/:id/runs` (GET), `/v1/agent/settings` (GET/PATCH), `/v1/agent/memory` (GET), `/v1/agent/memory/:id` (DELETE), `/v1/agent/events` (SSE), `/v1/agent/health` (GET)
- Task scheduling: APScheduler in-process, cron validation rejects intervals < 5 minutes, max 20 tasks
- Input validation: model allowlist (`qwen3:8b`, `qwen3:4b`, `llama3.2:3b`, `mistral:7b`), `max_length` on all string fields
- **Personality + user memory** (agent-owned, configured via Settings UI). Named persona is prepended as a system message to every `/v1/chat` call. User memory learns facts about the user from conversations via fire-and-forget LLM extraction (calls `/api/generate` on discovery's Ollama pass-through). Facts stored in `user_facts` table with UNIQUE dedup and LRU eviction. Settings stored in `agent_settings` table, seeded with defaults on first run. Key file: `memory.py`.
- **Voice** (STT + TTS): Local-first voice input/output. STT via `faster-whisper` (CTranslate2) on the backend — mic → MediaRecorder WebM → `POST /v1/agent/transcribe` → text in chat input. TTS via browser Web Speech API — zero backend cost. Config: `voice.enabled` (default true), `voice.whisper_model` (tiny/base/small, default base), `voice.device` (auto/cpu/cuda), `voice.compute_type` (auto/int8/float16/float32), `voice.language` (null = auto-detect). Settings: `voice_input_enabled`, `voice_auto_send`, `voice_auto_speak` (persisted in `agent_settings`). Key files: `transcribe.py`, `api.py` (transcribe endpoint), frontend hooks `useVoiceRecorder.ts` + `useTTS.ts`.
- See `docs/AGENT.md` for full architecture rationale and design decisions

### OpenClaw Skill (`skills/oap-discover/`)

Workspace skill for [OpenClaw](https://openclaw.ai) that lets the agent discover and invoke OAP capabilities at runtime.

- `skills/oap-discover/SKILL.md` — Skill definition: YAML frontmatter + agent instructions
- Install: `cp -r skills/oap-discover ~/.openclaw/workspace/skills/`
- Requires: `OAP_DISCOVERY_URL` env var (e.g., `http://localhost:8300`), `curl` on PATH

### MCP Server (`reference/oap_mcp/`)

MCP server exposing OAP manifest discovery to Claude Desktop and MCP clients. Three tools, no heavy dependencies.

- Entry point: `oap-mcp` (stdio transport)
- Config: `OAP_URL` (default `http://localhost:8300`), `OAP_TOKEN`, `OAP_TIMEOUT` (default `120`). CLI args override env vars.
- Tools: `oap_discover(task, top_k)`, `oap_call(tool_name, arguments)`, `oap_exec(command, stdin)`
- Claude Desktop config: `{"mcpServers": {"oap": {"command": "oap-mcp", "env": {"OAP_URL": "http://localhost:8300", "OAP_TOKEN": "your-token"}}}}`

### Legacy Registry

The full registry implementation (Firestore-backed) is preserved on the **`registry-v1`** branch.

## Commands

```bash
npm install
npm run dev          # Development server on http://localhost:3000
npm run build        # Production build
npm run start        # Start production server
```

### Python Services (local development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e reference/oap_discovery
pip install -e reference/oap_trust
pip install -e reference/oap_dashboard
pip install -e reference/oap_mcp
pip install -e reference/oap_agent
```

## Key Design Principles

1. **One-page spec.** If it doesn't fit on one page, it's too complex.
2. **Five-minute adoption.** A solo developer can add OAP in the time it takes to write a README.
3. **No gatekeepers.** No registration, no approval, no fees. Publish and you're in.
4. **Machine-first, human-readable.** Designed for AI to consume, but any developer can read and write a manifest.
5. **Unix philosophy.** Describe what you accept and what you produce. Let the invoker handle composition.
6. **The web model.** Standardize the format. Let the ecosystem build the discovery.
7. **No agent/app distinction.** A capability is a capability — `grep` is an agent with a man page.

## Manifest Format (v1.0)

Only four fields are required: `oap`, `name`, `description`, `invoke`. The `description` field is the most important — it's the text an LLM reads to decide if a capability fits a task.

```json
{
  "oap": "1.0",
  "name": "Capability Name",
  "description": "Plain English description — write it like a man page.",
  "input": { "format": "text/plain", "description": "What this needs" },
  "output": { "format": "application/json", "description": "What this produces" },
  "invoke": { "method": "POST", "url": "https://example.com/api/endpoint" }
}
```

## Architecture Notes

- **Next.js 16 App Router** with TypeScript and Tailwind CSS 4
- **Markdown rendering** uses unified/remark/rehype pipeline with rehype-slug for heading IDs, rehype-sanitize for XSS protection, and auto-generated TOC extracted from rendered HTML
- **API proxy pattern**: Next.js API routes proxy to Python backend services. `lib/proxy.ts` routes via per-service URL env vars (`BACKEND_URL`, `TRUST_URL`, `DASHBOARD_URL`) in tunnel mode, falls back to port-swapping for local dev
- **Client components** (`'use client'`): PlaygroundEditor, DiscoverSearch, TrustFlow, TrustLookup, DashboardStats, DashboardManifestList, Header (dropdown state), all `components/agent/*.tsx`
- **SSRF protection**: All URL fetching goes through `lib/security.ts` (private IP blocking, DNS resolution checks)
- **Rate limiting**: In-memory per-IP rate limiters on all API routes
- **No test framework** for the Next.js frontend. Python reference services use pytest.
- **next lint** script exists but ESLint is not explicitly configured. No formatter currently configured.

## Future Ideas

- **System monitoring manifests**: Read-only system introspection tools (lsof, ps, df, du, iostat, vmstat, etc.) gated behind `--include-system` flag in the manifest factory.
- **Discovery test harness** (implemented): `scripts/discovery-test-harness.py` — 200 tests across 7 local manifests. CLI: `--category`, `--test`, `--smoke`, `--dry-run`, `--fail-fast`, `--verbose`, `--json`, `--timeout`. Cache tests behind `--include-cache-tests --token <secret>`. Full run: **96% pass+soft** (172 PASS, 21 SOFT, 5 FAIL, 2 SKIP).
- **Advanced test harness** (implemented): `scripts/advanced-test-harness.py` — 60 tests across file/parse/pipeline/impossible categories. CLI: `--category`, `--test`, `--smoke`, `--no-setup`, `--keep-fixtures`, `--verbose`, `--log`, `--timeout`, `--token <secret>`. Full run: **73% pass** (22/30 parse+pipeline).
- **Big LLM manifest debugger**: Insert a large LLM (e.g., Claude) into the feedback pipeline to diagnose manifest quality issues at runtime.
