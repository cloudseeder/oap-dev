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
- `docs/MANIFEST_2_0.md` — Manifest 2.0 roadmap: OpenClaw comparison, voice, channels, monitoring
- `docs/THE-SMALL-MODEL-PROBLEM.md` — The Small Model Problem: real-world failures switching between small LLMs, compensating logic, and why manifest descriptions matter
- `DEPLOYMENT.md` — Mac Mini + Vercel deployment guide (Trust + Dashboard only)

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

Discovery, Agent, Reminder, and Email have moved to the [manifest repo](https://github.com/cloudseeder/manifest). This repo retains Trust and Dashboard (website backends) plus the MCP server.

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
│  Next.js App        │               │  Trust API (:8301)           │
│  ├─ Marketing pages │  Cloudflare   │  Dashboard API (:8302)       │
│  ├─ Spec docs       │◄── Tunnel ──► │                              │
│  ├─ /playground     │               │  + Manifest repo services:   │
│  ├─ /discover       │               │    Discovery API (:8300)     │
│  ├─ /trust          │               │    Agent (:8303)             │
│  ├─ /dashboard      │               │    Reminder (:8304)          │
│  └─ /api/* (proxy)  │               │    Email (:8305)             │
└─────────────────────┘               └──────────────────────────────┘
```

- **Vercel**: Next.js frontend + API route handlers that proxy to the Mac Mini
- **Mac Mini**: Trust + Dashboard (this repo) alongside Discovery, Agent, Reminder, Email ([manifest repo](https://github.com/cloudseeder/manifest))
- **Cloudflare Tunnel**: Three hostnames (`api.oap.dev`, `trust.oap.dev`, `dashboard.oap.dev`). Discovery tunnel exposes only `/v1/discover`, `/v1/manifests`, `/health`.
- **Env vars**: `BACKEND_URL` (discovery), `TRUST_URL`, `DASHBOARD_URL` — Cloudflare Tunnel hostnames; `BACKEND_SECRET` / `OAP_BACKEND_SECRET` — shared auth token
- **Setup script**: `scripts/setup-mac-mini.sh` — Trust + Dashboard only. Generates backend secret, creates launchd plists, loads services, runs health checks
- **Manifest factory**: `scripts/manifest-factory.py` — auto-generates OAP manifests from documentation sources via qwen3:8b. Pluggable `SourceAdapter` classes. CLI: `--source manpage|help|openapi`, `--dry-run`, `--tools sed,awk,cut`, `--ollama-url`. Adapters: ManPageAdapter (man pages), HelpAdapter (`--help` output), OpenAPIAdapter (OpenAPI 3.x / Swagger 2.x specs).

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
pip install -e reference/oap_trust
pip install -e reference/oap_dashboard
pip install -e reference/oap_mcp
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

## Future Ideas

- **System monitoring manifests**: Read-only system introspection tools (lsof, ps, df, du, iostat, vmstat, etc.) gated behind `--include-system` flag in the manifest factory.
- **Discovery test harness** (implemented): `scripts/discovery-test-harness.py` — 200 tests across 7 local manifests. CLI: `--category`, `--test`, `--smoke`, `--dry-run`, `--fail-fast`, `--verbose`, `--json`, `--timeout`. Cache tests behind `--include-cache-tests --token <secret>`. Full run: **96% pass+soft** (172 PASS, 21 SOFT, 5 FAIL, 2 SKIP).
- **Advanced test harness** (implemented): `scripts/advanced-test-harness.py` — 60 tests across file/parse/pipeline/impossible categories. CLI: `--category`, `--test`, `--smoke`, `--no-setup`, `--keep-fixtures`, `--verbose`, `--log`, `--timeout`, `--token <secret>`. Full run: **73% pass** (22/30 parse+pipeline).
- **Big LLM manifest debugger**: Insert a large LLM (e.g., Claude) into the feedback pipeline to diagnose manifest quality issues at runtime.
