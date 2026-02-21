# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Open Application Protocol (OAP) — a cognitive API layer for artificial intelligence. A manifest spec that lets AI learn about capabilities that weren't in its training data, at runtime, without retraining.

OAP is a **pure spec** with a reference architecture for discovery. It is **not** a registry, service, or platform.

- **Manifest** (`/.well-known/oap.json`) — JSON file describing what a capability does, what it accepts, what it produces, and how to invoke it. Designed to be read and reasoned about by LLMs.
- **Discovery** — Not prescribed by the spec. Reference architecture uses crawlers + local vector DB + small LLM for intent-to-manifest matching. The web model, not the registry model.
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
- `docs/OPENCLAW.md` — OpenClaw integration: workspace skill for runtime capability discovery
- `docs/OLLAMA.md` — OAP + Ollama: manifest discovery as native Ollama tool calling via the tool bridge
- `DEPLOYMENT.md` — Mac Mini + Vercel deployment guide (Phase 7)

### Next.js Application (oap.dev)

The site serves as a developer tool: manifest playground, hosted discovery/trust reference services, and an adoption dashboard. Deployed on Vercel.

#### Routes

- `app/(marketing)/` — Landing page, spec, doc pages (quickstart, architecture, trust, a2a, ollama, robotics, procedural-memory, manifesto)
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

All three services live under `reference/` and install as editable Python packages with entry-point commands.

#### Discovery (`reference/oap_discovery/`)

Crawls domains for manifests, embeds descriptions into ChromaDB via Ollama (nomic-embed-text), and serves a discovery API that matches natural language tasks to manifests using vector search + small LLM (qwen3:4b).

- Entry points: `oap-api` (:8300), `oap-crawl`, `oap`
- Config: `config.yaml` (Ollama URL, ChromaDB path, crawler settings)
- Key files: `models.py` (Pydantic types), `validate.py` (validation), `crawler.py`, `db.py` (ChromaDB), `discovery.py` (vector search + LLM), `api.py` (FastAPI), `ollama_client.py` (Ollama API client), `config.py` (configuration), `cli.py` (CLI entry point)
- Procedural memory (experimental, opt-in via `experience.enabled: true`): `experience_models.py` (experience record types), `experience_store.py` (SQLite persistence), `experience_engine.py` (three-path routing: cache hit / partial match / full discovery), `experience_api.py` (FastAPI router at `/v1/experience/`), `invoker.py` (HTTP + stdio manifest execution)
- Ollama tool bridge (enabled by default via `tool_bridge.enabled: true`): `tool_models.py` (Pydantic types for Ollama tool schema), `tool_converter.py` (manifest-to-tool conversion with heuristic parameter schema generation), `tool_executor.py` (tool call execution via `invoke_manifest()`, map-reduce summarization for large results), `tool_api.py` (FastAPI router at `/v1/tools` and `/v1/chat`). `POST /v1/tools` discovers manifests and returns Ollama tool definitions. `POST /v1/chat` is a transparent Ollama proxy that discovers tools, injects them, executes tool calls, and loops up to `max_rounds`. Tool bridge routes (`/v1/chat`, `/v1/tools`) have **no backend token auth** — they are local-only, secured at infrastructure layer by Cloudflare Tunnel path filtering (tunnel only exposes `/v1/discover`, `/v1/manifests`, `/health`).
- Local manifests (`reference/oap_discovery/manifests/`): JSON manifest files auto-indexed on API startup under `local/<tool-name>` pseudo-domains. Starter set: `grep.json`, `jq.json`, `wc.json`, `date.json`, `bc.json` — Unix tools with stdio invoke method, descriptions written for LLM discovery.
- Map-reduce summarization: when a tool result exceeds `summarize_threshold` (default 4000 chars), `tool_executor.py` splits the response into `chunk_size` chunks on newline boundaries, summarizes each chunk in parallel via `ollama.generate()` (`/api/generate`), strips `<think>` blocks from qwen3 responses, and concatenates summaries. If combined summaries exceed `max_tool_result`, a final reduce pass consolidates them. Falls back to hard truncation if any Ollama call fails. Configured via `ToolBridgeConfig` fields: `summarize_threshold`, `chunk_size`, `max_tool_result`. `invoker.py` allows up to 100KB responses through to the executor (previously 10KB).
- Debug mode: `POST /v1/chat` accepts `oap_debug: true` to include a full execution trace in the response. When enabled, the response includes an `oap_debug` object with `tools_discovered` (list of tool names found via discovery) and `rounds` (array of per-round records, each containing the raw `ollama_response` including `<think>` blocks, and `tool_executions` with tool name, arguments, raw result string, and `duration_ms`). Zero overhead when off (default).

#### Trust (`reference/oap_trust/`)

Reference trust provider implementing Layers 0-2: baseline checks, domain attestation via DNS/HTTP challenge, capability testing.

- Entry points: `oap-trust-api` (:8301), `oap-trust`
- Key files: `models.py` (trust types), `attestation.py`, `dns_challenge.py`, `capability_test.py`, `api.py` (FastAPI), `cli.py` (CLI entry point), `config.py` (configuration), `db.py` (SQLite persistence), `keys.py` (Ed25519 key management), `manifest.py` (manifest validation)

#### Dashboard (`reference/oap_dashboard/`)

Adoption tracker: crawls seed domains, stores results in SQLite, serves stats and manifest list.

- Entry points: `oap-dashboard-api` (:8302), `oap-dashboard-crawl`
- Config: `config.yaml` (SQLite path, crawler settings)
- Key files: `db.py` (SQLite schema + CRUD), `crawler.py`, `api.py` (FastAPI)
- Note: Dashboard README to be created during site transition Phase 5.

### Infrastructure

```
Vercel (free tier)                    Mac Mini (M4, 16GB)
┌─────────────────────┐               ┌──────────────────────────────┐
│  Next.js App        │               │  Ollama (qwen3:4b + nomic)   │
│  ├─ Marketing pages │  Cloudflare   │  Discovery API (:8300)       │
│  ├─ Spec docs       │◄── Tunnel ──► │  Trust API (:8301)           │
│  ├─ /playground     │               │  Dashboard API (:8302)       │
│  ├─ /discover       │               │  Crawler (cron)              │
│  ├─ /trust          │               │  ChromaDB (local dir)        │
│  ├─ /dashboard      │               │  SQLite (dashboard.db)       │
│  └─ /api/* (proxy)  │               └──────────────────────────────┘
└─────────────────────┘
```

- **Vercel**: Next.js frontend + API route handlers that proxy to the Mac Mini
- **Mac Mini**: All Python services, Ollama, ChromaDB, SQLite
- **Cloudflare Tunnel**: Three hostnames (`api.oap.dev`, `trust.oap.dev`, `dashboard.oap.dev`) routing to local services. Discovery tunnel should only expose `/v1/discover`, `/v1/manifests`, `/health` — tool bridge routes (`/v1/chat`, `/v1/tools`) and experience routes (`/v1/experience`) stay local-only on `:8300`
- **Env vars**: `BACKEND_URL` (discovery), `TRUST_URL`, `DASHBOARD_URL` — Cloudflare Tunnel hostnames for proxy routes; `BACKEND_SECRET` / `OAP_BACKEND_SECRET` — shared auth token
- **Auth model**: Backend token auth (`X-Backend-Token` / `OAP_BACKEND_SECRET`) is per-route, not global. Protected routes: `/v1/discover`, `/v1/manifests`, `/v1/manifests/{domain}`, `/health`, `/v1/experience/*`. Unprotected routes: `/v1/chat`, `/v1/tools` (local-only, secured by tunnel path filtering)
- **Setup script**: `scripts/setup-mac-mini.sh` — generates backend secret, creates launchd plists, loads services, runs health checks

### OpenClaw Skill (`skills/oap-discover/`)

Workspace skill for [OpenClaw](https://openclaw.ai) that lets the agent discover and invoke OAP capabilities at runtime. When the agent needs a tool it doesn't have built-in, it queries the local discovery API, evaluates the best manifest match, and invokes the capability directly.

- `skills/oap-discover/SKILL.md` — Skill definition: YAML frontmatter + agent instructions
- Install: `cp -r skills/oap-discover ~/.openclaw/workspace/skills/`
- Requires: `OAP_DISCOVERY_URL` env var (e.g., `http://localhost:8300`), `curl` on PATH
- Flow: query `/v1/discover` → evaluate match → invoke via manifest's `invoke` spec → present result
- Handles all auth types (api_key, bearer, oauth2) and invoke methods (GET, POST, stdio)

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
- **Client components** (`'use client'`): PlaygroundEditor, DiscoverSearch, TrustFlow, TrustLookup, DashboardStats, DashboardManifestList, Header (dropdown state)
- **SSRF protection**: All URL fetching goes through `lib/security.ts` (private IP blocking, DNS resolution checks)
- **Rate limiting**: In-memory per-IP rate limiters on all API routes
- **No test framework** for the Next.js frontend. Python reference services use pytest.
- **next lint** script exists but ESLint is not explicitly configured. No formatter currently configured.
