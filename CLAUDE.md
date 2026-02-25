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
- `docs/OLLAMA.md` — OAP + Ollama: manifest discovery as native Ollama tool calling via the tool bridge
- `DEPLOYMENT.md` — Mac Mini + Vercel deployment guide (Phase 7)

### Next.js Application (oap.dev)

The site serves as a developer tool: manifest playground, hosted discovery/trust reference services, and an adoption dashboard. Deployed on Vercel.

#### Routes

- `app/(marketing)/` — Landing page, spec, doc pages (quickstart, architecture, trust, a2a, ollama, robotics, procedural-memory, path-to-23-tokens, manifesto)
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

Crawls domains for manifests, embeds descriptions into ChromaDB via Ollama (nomic-embed-text), and serves a discovery API that matches natural language tasks to manifests using vector search + FTS5 keyword search + small LLM (qwen3:8b).

- Entry points: `oap-api` (:8300), `oap-crawl`, `oap`
- CLI auth: `oap --token <secret>` or `OAP_BACKEND_TOKEN` env var. Required when `OAP_BACKEND_SECRET` is set on the server. All subcommands pass the token as `X-Backend-Token` header.
- Config: `config.yaml` (Ollama URL, ChromaDB path, FTS path, crawler settings)
- Key files: `models.py` (Pydantic types), `validate.py` (validation), `crawler.py`, `db.py` (ChromaDB), `fts_store.py` (SQLite FTS5), `discovery.py` (vector search + FTS5 + LLM + intent extraction), `api.py` (FastAPI), `ollama_client.py` (Ollama API client — `generate()` for `/api/generate` with optional `think` param, `chat()` for `/api/chat`), `config.py` (configuration), `cli.py` (CLI entry point)
- **Intent extraction for vector search**: `discovery.py:_extract_search_query(task)` strips inline data and normalizes colloquial language before embedding for vector search. Tasks like `'pull out lines with email addresses from:\nJohn Smith\njohn@example.com'` contain data that dilutes the embedding signal and domain-biasing terms ("email") that pull toward wrong manifests. The function: (1) takes the first line only (drops data after `\n`); (2) strips trailing prepositions introducing data blocks (`from:`, `in:`, `in this text:`); (3) strips content-specifying clauses (`with X`, `containing X`, `that contain X`, `that match X`, `matching X`) — these describe what's being processed, not what tool is needed; (4) removes quoted literal values (`"..."`); (5) normalizes colloquial verbs (`pull out` → `filter`, `pick out` → `filter`) to match manifest vocabulary; (6) appends `" in text"` as a domain hint if no text-processing concepts present; (7) appends `" search matching pattern"` for line-filtering queries that lack search/match vocabulary (distinguishes grep from other line-processing tools like sort, uniq, comm); (8) falls back to the original task if extraction produces an empty string. Example: `"pull out lines with email addresses from:"` → `"filter lines search matching pattern"`. The cleaned query goes to `embed_query()` for vector search; the full task still goes to the LLM ranking prompt unchanged. Improved grep smoke tests from 50% to 100% pass rate.
- **FTS5 keyword search** (disabled by default via `fts.enabled: false`): `fts_store.py` provides SQLite FTS5 full-text search with BM25 ranking as a complement to vector search. Schema: `manifests` content table (domain, name, description, manifest_json, invoke_method, invoke_url, tags) with a `manifests_fts` virtual table indexing name, description, and tags. Triggers keep FTS in sync on insert/update/delete. `FTSStore` mirrors `ManifestStore`'s interface: `upsert_manifest(domain, manifest)` (no embedding param), `search(query, n_results)`, `get_manifest(domain)`, `list_domains()`, `count()`. Search tokenizes the query, wraps each token in double quotes (safe for FTS5 special chars), joins with OR, and returns results ranked by BM25. In `discovery.py`, `DiscoveryEngine` accepts an optional `fts_store` param. When present, `discover()` runs FTS5 search after vector search using the same cleaned query from `_extract_search_query()`, merges results by domain (vector hits keep original order, FTS-only hits append after), then feeds the combined candidate pool to LLM ranking. Vector-only behavior unchanged when `fts_store is None`. Config: `fts.enabled` (bool, default false), `fts.db_path` (str, default `./oap_fts.db`). Env overrides: `OAP_FTS_ENABLED`, `OAP_FTS_DB_PATH`. In `api.py`, FTS store is created in `lifespan()` when enabled, passed to `DiscoveryEngine`, and manifests are upserted into it during `_index_local_manifests()`. In `crawler.py`, both `load_seeds()` and `crawl_domain()` upsert into FTS alongside ChromaDB when available. FTS5 provides deterministic keyword matching — no embeddings, no drift, sub-millisecond queries at millions of documents — filling gaps where vector search returns irrelevant results due to embedding similarity drift.
- Procedural memory (enabled by default via `experience.enabled: true`): `experience_models.py` (experience record types), `experience_store.py` (SQLite persistence), `experience_engine.py` (three-path routing: cache hit / partial match / full discovery), `experience_api.py` (FastAPI router at `/v1/experience/`), `invoker.py` (HTTP + stdio manifest execution). Three-path routing: (1) **cache_hit** — exact fingerprint match with high confidence → replay cached invocation pattern; (2) **partial_match** — similar fingerprint/domain → validate with discovery then execute; (3) **full_discovery** — no match → full vector search + LLM ranking → execute → cache new experience. SQLite storage at `oap_experience.db`.
- Ollama tool bridge (enabled by default via `tool_bridge.enabled: true`): `tool_models.py` (Pydantic types for Ollama tool schema), `tool_converter.py` (manifest-to-tool conversion with heuristic parameter schema generation), `tool_executor.py` (tool call execution via `invoke_manifest()`, direct CLI execution via `execute_exec_call()`, map-reduce summarization for large results), `tool_api.py` (FastAPI router at `/v1/tools` and `/v1/chat`). `POST /v1/tools` discovers manifests and returns Ollama tool definitions. `POST /v1/chat` is a transparent Ollama proxy that discovers tools, injects them, executes tool calls, and loops up to `max_rounds`. Tool bridge routes (`/v1/chat`, `/v1/tools`) have **no backend token auth** — they are local-only, secured at infrastructure layer by Cloudflare Tunnel path filtering (tunnel only exposes `/v1/discover`, `/v1/manifests`, `/health`). **Chat system prompt**: `tool_api.py` prepends a system message to all chat rounds with: "Always use oap_exec — NEVER answer without calling a tool", pipe examples (`grep -oE regex /path/file | sort -u`), jq select/length examples, `grep -c` for counting, extraction+uniqueness patterns, and inline-text stdin guidance. Combined with `think: false` in the Ollama payload, this keeps qwen3:8b responses to ~12 tokens per round. The system prompt is preserved across retry attempts (cache degradation path). **Multi-tool injection**: `_discover_tools()` injects up to `MAX_INJECTED_TOOLS = 3` tools into each chat round — the LLM's top pick from ranking plus the next highest-scoring candidates from vector search (deduped by domain). This gives the chat model alternatives when vector search ranks the wrong manifest first (e.g., "pull out lines with email addresses" pulling spfquery above grep). The chat model is smart enough to select the right tool from multiple options.
- **oap_exec meta-tool**: `oap_exec` is a built-in meta-tool always injected as the **first tool** in every `/v1/chat` round — not discovered, always available. It bridges the gap between LLM CLI knowledge and the stdio tool parameter model: LLMs write perfect regex in CLI commands but mangle it in tool parameters (e.g. `oap_grep` gets `"[-E] [email\\@][^\\s]+"` while `oap_exec` gets `"grep -E '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}'"` — CLI syntax is all over training data, tool parameter schemas aren't). `oap_exec` accepts two parameters: `command` (the full CLI command string) and optional `stdin` (text to pipe to the process). For files: `oap_exec(command='grep -E pattern /path/file')`. For inline text: `oap_exec(command='grep -E pattern', stdin='the text')`. **Implementation**: `tool_api.py` defines `EXEC_TOOL` (Ollama tool schema with `command` required, `stdin` optional) and `EXEC_REGISTRY_ENTRY` (domain `builtin/exec`, invoke method `exec`). Always injected at position 0 via `tools.insert(0, ...)` (small LLMs prefer earlier tools), and re-injected on degradation retry. In the execution loop, `oap_exec` calls dispatch to `tool_executor.execute_exec_call()` instead of `execute_tool_call()`. When `stdin` is provided, it's piped to the process via `asyncio.create_subprocess_exec()` with `stdin=PIPE` + `proc.communicate(input=stdin_bytes)` (same pattern as `_invoke_stdio`). **Pipeline support**: `oap_exec` supports shell-style pipes (`cmd1 | cmd2 | cmd3`). `tool_executor._split_pipeline()` splits `shlex.split()` output at `|` tokens into stages. Each stage's command is validated against the PATH allowlist independently. Stages are chained via `_run_pipeline()` which connects stdout→stdin between `asyncio.create_subprocess_exec()` calls. Single-command invocations take an unchanged code path via `_run_single()`. **Shlex fallback**: LLMs generate commands with mixed quoting across pipe stages (e.g. `grep -oE '"[^"]+"' file | cut -d" -f2`) that `shlex.split()` can't parse on the full string. When `shlex.split()` raises `ValueError`, `_raw_pipe_split()` splits the raw command string at unquoted `|` characters, then `_tokenize_stage()` tries `shlex.split()` per stage, falling back to `str.split()` for stages with unresolvable quoting (e.g. `cut -d"` where `"` is a literal delimiter character). **Security**: identical to existing stdio tools — `shlex.split()` parses the command (no shell injection), `invoker._validate_stdio_command()` validates every binary in the pipeline against the PATH allowlist (`/usr/bin/`, `/usr/local/bin/`, `/bin/`, `/opt/homebrew/bin/`), `asyncio.create_subprocess_exec()` executes (no `shell=True`), `os.path.expanduser()` expands `~` in arguments. Same `stdio_timeout` (default 10s), same 100KB output cap, same map-reduce summarization for large results, same exit-code-1 handling (grep/diff "no results" convention). **File path detection**: `_task_has_file_path(task)` uses a regex to detect file paths in the user message (patterns like `/tmp/file.txt`, `~/data.json`, `./config.yaml`). When a file path is detected, discovery is suppressed entirely — no `_discover_tools()`, no experience cache check, no experience success tool injection — so `oap_exec` is the **only** tool available. This prevents small LLMs from choosing the "named" tool (e.g. `oap_grep`) and passing the file path as literal stdin text. Inline-text tasks (no file path) go through the full discovery pipeline with `oap_exec` first and discovered tools as alternatives. **Exec fallback retry**: when `oap_exec` errors on a file-path task (bad jq syntax, wrong regex, etc.), the chat loop retries with full discovery including stdio tools (jq, grep, etc.) — unlike normal mode where stdio tools are suppressed. The rationale: `oap_exec` already failed, so the named tool's parameter schema may guide the LLM to construct better arguments on the second attempt. `oap_exec` stays as first tool alongside discovered alternatives. Response metadata shows `oap_experience_cache: "exec_fallback"` on retry. The early-return break also catches file-path retries (not just cache degradation), so the LLM giving up with a text response after errors correctly triggers the retry. **Experience caching**: `oap_exec` successes and failures are cached like any other tool. File path detection handles routing (file tasks skip the cache check entirely), and cache degradation self-corrects if an `oap_exec` entry is ever served to an inline-text task (one failed round → confidence drops below threshold → won't serve again). **Empty result guard**: tool executions returning `"Success (no output)"` are not cached as positive experiences — the result is ambiguous (could be correct "no results" or a mangled pattern). The `tools_had_output` flag tracks whether any tool produced substantive output; experience saves are gated on it at both return points.
- **Stdio tool suppression**: after discovery, all stdio tools (tools whose manifest `invoke.method` is `STDIO`) are filtered out of the tools list and registry. Only `oap_exec` and HTTP/API tools remain available to the LLM. This applies to: (1) the main discovery path after `_discover_tools()`; (2) similar experience tool injection (stdio experience matches are skipped); (3) the degradation retry path (same bulk filter + per-tool filter). Rationale: small LLMs (qwen3:8b) prefer "named" tools (e.g. `oap_grep`) over the generic `oap_exec` regardless of system prompt instructions — tool names carry more weight than prompt guidance. But `oap_exec` produces better results because LLMs write perfect regex in CLI command syntax (heavily represented in training data) while mangling it in tool parameters. Suppressing discovered stdio tools forces all CLI work through `oap_exec` while preserving HTTP/API tools that `oap_exec` can't handle. The existing stdio tool manifests (grep, jq, wc, etc.) remain in the vector DB for discovery ranking — they're just not presented to the LLM as callable tools.
- Experience cache in tool bridge: when both `experience.enabled` and `tool_bridge.enabled` are true, `/v1/chat` uses procedural memory as a discovery cache. Flow: (1) fingerprint the task via `ExperienceEngine.fingerprint_intent()` (1 LLM call using `generate(think=False)`, ~2-3s); (2) check `ExperienceStore.find_by_fingerprint()` for matches with `confidence ≥ threshold` and `outcome.status == "success"`; (3) on **cache hit** → load cached manifest, convert to tool, inject into chat, touch record (increment `use_count`), skip vector search + LLM ranking; (4) on **cache miss** → fall through to full discovery (vector search + LLM ranking), then after successful tool execution save a new `ExperienceRecord` mapping fingerprint → manifest (caches the tool the LLM actually called, not an arbitrary registry entry). Response includes `oap_experience_cache: "hit"|"miss"|"degraded"` metadata. State wired in `api.py` lifespan: `tool_api._experience_engine`, `tool_api._experience_store`, `tool_api._experience_cfg`.
- Experience cache degradation: `_save_experience()` is gated on `not tools_had_errors` — if any `execute_tool_call()` result starts with `"Error"`, the experience is not cached. On a cache hit where tool executions error, `ExperienceStore.degrade_confidence()` multiplies confidence by 0.7 and sets `outcome_status='failure'`, then the chat loop retries with full discovery (vector search + LLM ranking). A single failure drops 0.90 → 0.63 (below 0.85 threshold), so the bad entry won't be served again. Response metadata shows `oap_experience_cache: "degraded"` on retry. **Early-return degradation fix**: when a cache hit produces errors and the LLM gives up with a text response (no tool calls), the early-return path at `tool_api.py:~430` now `break`s out of the inner loop instead of `return`ing, allowing the degradation check at line ~528 to fire. Previously, degradation only ran when the inner loop exhausted `max_rounds`, not when it exited via the "no tool calls" path — so misrouted cache hits that errored would return the error without retrying.
- Negative experience caching and self-correction: when tool execution fails, `_save_failure_experience()` saves the failure details as `CorrectionEntry` records (tool name + JSON args, error string, fix string) on an `ExperienceRecord` with `outcome_status="failure"`, `confidence=0.0`, and `fail_` ID prefix. **Self-correction**: when a session self-corrects (round 1 fails, round 2 succeeds), the fix field on the failure record is populated with the successful tool call (e.g., `oap_grep({"args":"-i error","stdin":"..."})`), and a success experience is also saved for the corrected approach. This means the system learns *both* what failed and what worked in a single session. Failed and successful calls are tracked in `failed_calls` and `successful_calls` lists alongside `tools_had_errors`, and experiences are saved at both return points (early return and max-rounds). Both lists are reset during cache degradation retry.
- Experience hints (`_build_experience_hints`): on subsequent requests, `_build_experience_hints(fingerprint)` queries exact fingerprint failures (`find_failures_by_fingerprint`) and prefix-matched successes (`find_successes_by_prefix` on `ExperienceStore`) using the first two fingerprint segments (e.g., `extract.json` from `extract.json.field_list`). **Only exact-match failures are included** — prefix failure matching was removed because it was too aggressive: one wc failure at `count.text.line_count` would poison ALL `count.text.*` tasks, causing the LLM to refuse tool calls entirely (wc went to 0/25, jq to 37%). Prefix successes are safe (they suggest what works, not what to avoid). Returns a compact hint string injected into the system prompt: `"\n\nNote — previous attempts at this exact task type:\n- oap_grep({"args":"[-Ei]..."}) → Error: invalid option — instead try: oap_grep(...)\n- Previously succeeded: local/jq for similar task\nUse different arguments if retrying the same tool."` Also returns a list of successful tool names for potential injection into discovery results. Fingerprinting is always performed when the experience engine is available (even with `--no-cache`), so experience hints are looked up regardless of cache mode. The pre-computed fingerprint is passed to `_check_experience_cache()` to avoid redundant LLM calls.
- Fingerprint optimization: `fingerprint_intent()` uses `OllamaClient.chat(think=False, temperature=0)` to disable qwen3's thinking chain and ensure deterministic output. With qwen3:8b, `think=false` works correctly at the weight level — no template patching needed. Fingerprinting produces ~15 tokens in ~1s. The system prompt includes examples matching actual manifests (grep, wc, bc, date, jq, apropos, man) for consistent fingerprint classification. **JSON-aware fingerprints**: examples like `"Extract names from: [{"name":"Alice"}...]"` → `extract.json.field_list` teach the classifier to use `*.json.*` fingerprints when tasks contain JSON data or describe JSON operations (field extraction, sorting by field, array length). This separates JSON tasks from text tasks in the fingerprint space — old cache entries like `extract.data.name_list` → awk remain valid for text, while new JSON tasks fingerprint as `extract.json.*` and miss those stale entries. **Critical**: `format="json"` is passed to Ollama to constrain generation at the grammar level — without it, qwen3:4b still generates verbose reasoning in the `content` field even with `think=false` and the patched template (the model is trained to reason, and no template/parameter combination fully suppresses it). With `format="json"`, Ollama enforces valid JSON output only, producing ~23 tokens in ~1.7s.
- Partial match injection: on cache miss, `_get_similar_experience_tools()` queries `ExperienceStore.find_similar()` using the first two segments of the fingerprint (e.g., `extract.json` from `extract.json.field_list`) to find past successes with similar fingerprints in the same domain. Matching tools (with `outcome.status == "success"` and `confidence >= 0.5`) are injected into remaining `MAX_INJECTED_TOOLS` slots without displacing discovery results. Example: if `extract.json.field_value` previously succeeded with jq, a new `extract.json.field_list` task gets jq injected alongside discovery results. Also runs on degradation retry. Debug output includes `similar_experience_tools` field listing which tools came from partial matches.
- Stdio tool schema: stdio manifests are presented to the LLM with two parameters — `stdin` (text piped to the process) and `args` (command-line flags and arguments). `tool_converter._split_stdio_description()` splits the manifest's `input.description` by sentence: sentences containing "argument" go to the `args` parameter description, the rest go to `stdin`. This prevents small LLMs from confusing what goes where (e.g. grep's "The first argument is the regular expression pattern" belongs in `args`, not `stdin`). The executor pipes `stdin` via `stdin_text` and handles `args` splitting context-dependently: when stdin is provided, leading flags (tokens starting with `-`) are split off as separate arguments while the remaining tokens are kept as a single argument (the pattern). This handles both `"-i connection refused"` → `["-i", "connection refused"]` and plain `"connection refused"` → `["connection refused"]`. Without stdin, `shlex.split()` tokenizes args respecting shell quoting conventions. **Args fallback**: small LLMs often invent descriptive key names (e.g. `{"keyword": "image"}` instead of `{"args": "image"}`); the executor falls back to the first non-stdin string value in the arguments dict when `args` is missing. **Stdio default flags**: invoke URLs can include default flags (e.g. `"grep -E"`) — the invoker splits the URL into command + default_args, validates the command, and prepends flags to argv. grep uses `"grep -E"` so extended regex works by default (LLMs naturally generate `+`, `\b`, etc.). **Exit code 1 handling**: many Unix tools (grep, diff, cmp) use exit code 1 for "no results" rather than errors. The invoker treats exit 1 with no stderr as success with empty output, preventing false "Unknown error" failures.
- Local manifests (`reference/oap_discovery/manifests/`): JSON manifest files auto-indexed on API startup under `local/<tool-name>` pseudo-domains. Starter set: `apropos.json`, `man.json`, `grep.json`, `jq.json`, `wc.json`, `date.json`, `bc.json` — Unix tools with stdio invoke method, descriptions written for LLM discovery. `apropos` and `man` enable meta-discovery: the LLM can search for commands by keyword then read their manual pages, bootstrapping knowledge of tools that don't have manifests.
- Map-reduce summarization: when a tool result exceeds `summarize_threshold` (default 8000 chars), `tool_executor.py` splits the response into `chunk_size` chunks on newline boundaries, summarizes each chunk **sequentially** via `ollama.generate()` (`/api/generate`), strips `<think>` blocks from qwen3 responses, and concatenates summaries. Chunks are processed sequentially (not parallel) because Ollama serializes generation requests internally — parallel `asyncio.gather` provided no speed benefit and caused queue timeouts. Each chunk gets a 120s timeout. If combined summaries exceed `max_tool_result`, a final reduce pass consolidates them. Falls back to hard truncation if any Ollama call fails. Configured via `ToolBridgeConfig` fields: `summarize_threshold`, `chunk_size`, `max_tool_result`. `invoker.py` allows up to 100KB responses through to the executor (previously 10KB).
- Debug mode: `POST /v1/chat` accepts `oap_debug: true` to include a full execution trace in the response. When enabled, the response includes an `oap_debug` object with `tools_discovered` (list of tool names found via discovery), `experience_cache` (`"hit"`, `"miss"`, or `"disabled"`), `experience_fingerprint` (the computed intent fingerprint, or null), `experience_hints` (string of past failure/success hints injected into system prompt, or null if none), `similar_experience_tools` (list of tools from partial fingerprint matches, or null), and `rounds` (array of per-round records, each containing the raw `ollama_response` including `<think>` blocks, and `tool_executions` with tool name, arguments, raw result string, and `duration_ms`). Zero overhead when off (default).

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
│  Next.js App        │               │  Ollama (qwen3:8b + nomic)   │
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
- **Ollama tuning**: `ollama.num_ctx: 4096` caps the context window to keep VRAM usage bounded on <24GB machines (Mac Mini M4 has 16GB unified memory). `ollama.timeout: 120` is the base httpx client timeout. `OllamaClient.generate()` accepts per-call `timeout` (default 60s) and `think` (bool, optional) kwargs; `OllamaClient.chat()` also accepts `think`, `temperature`, and `format`. Summarization uses `generate()` with 120s timeout; fingerprinting uses `chat(think=False, temperature=0, format="json")` with 120s timeout; chat tool rounds use `think=False` in the Ollama payload. `num_ctx` is passed via the `options` field to both `/api/generate` and `/api/chat`. Override with `OAP_OLLAMA_NUM_CTX` env var. `ollama.keep_alive: "-1m"` (default) keeps models loaded in memory permanently, preventing cold-start timeouts between requests. Passed to `/api/generate` and `/api/chat` (not `/api/embed` — unsupported). Override in `config.yaml` (e.g. `"30m"`) or set `"0"` to unload immediately after each response. **Model warmup**: during API startup, `lifespan()` sends a throwaway `generate("hello")` call (300s timeout) to force-load the generation model into Ollama memory before any real requests arrive. Logs `Warming up <model>...` / `Model <model> loaded and ready`. If warmup fails, startup continues with a warning. **Model choice — qwen3:8b**: switched from `qwen3t:4b` (patched 4b) to `qwen3:8b` because qwen3:4b's `think=false` is broken at the weight level — the model dumps verbose reasoning (~300-400 tokens, ~10s) into the response content regardless of template or parameter settings. The patched `qwen3t:4b` template suppressed the structured `<think>` block but the model still produced reasoning in the content field. `format="json"` constrains thinking at the grammar level but can't be used for chat rounds (output must be natural language + tool calls). qwen3:8b properly respects `think=false`: 12 tokens, 560ms. Memory: qwen3:8b at 4k context uses ~5.9GB VRAM on M4 unified memory, fitting alongside nomic-embed-text with ~300-500MB free. macOS kernel manages buffer cache aggressively and reclaims as needed. Config uses `generate_model: "qwen3:8b"`. **qwen3t:4b template fix** (historical): `qwen3t:4b` is still available as a patched copy of qwen3:4b created via `ollama create qwen3t:4b` — the template's final block changed from unconditional `<think>` to `{{ if or (not $.IsThinkSet) $.Think }}<think>{{ end }}`. No longer used in production.
- **Setup script**: `scripts/setup-mac-mini.sh` — generates backend secret, creates launchd plists, loads services, runs health checks
- **Manifest factory**: `scripts/manifest-factory.py` — auto-generates OAP manifests from documentation sources via qwen3:8b (previously qwen3t:4b). Generic factory core with pluggable `SourceAdapter` classes (all in one file, ~500 lines). Self-contained: stdlib + httpx only (inline validation mirroring `validate.py` to avoid pydantic import chain). CLI: `--source manpage|help|openapi` (default: manpage), `--dry-run` (preview without Ollama), `--tools sed,awk,cut` (specific tools), `--ollama-url` (override endpoint). Adapters:
  - **ManPageAdapter** (default, `--source manpage`): discovers section-1 tools via `apropos`, filters by path allowlist (matches `invoker.py`) + blocklist (dangerous/interactive/privileged tools) + prefix blocklist (perl*, git*, x86_64*, snmp*), reads man pages via `man <tool> | col -b` (truncated to 5000 chars for 8192 context window), uses grep/wc/date few-shot examples, forces `invoke.method = "stdio"`. On macOS (Mac Mini M4, 16GB unified memory): ~1124 commands discovered, ~539 after filtering, ~5s per tool at 8k context, ~45 min full run. Memory: qwen3:4b at 8k context uses ~3.5GB VRAM, leaves ~300MB free physical — stable with no swapping observed. At 4k context: ~3s per tool, more headroom. At 256k (Ollama default): not recommended on 16GB, causes heavy swapping. 8k is the sweet spot — richer descriptions (more flags, specific use cases, better discovery matching) without memory pressure.
  - **HelpAdapter** (`--source help`): scans allowed PATH dirs for executables, reads `<tool> --help 2>&1` output, same blocklist/allowlist and stdio prompt as ManPage. Use case: Go/Rust CLIs in `/usr/local/bin` that have `--help` but no man page.
  - **OpenAPIAdapter** (`--source openapi --spec <path-or-url>`): parses OpenAPI 3.x / Swagger 2.x JSON specs, extracts endpoints by `operationId` or `method + path`, skips deprecated endpoints, generates HTTP manifests with correct `invoke.method` (GET/POST/etc) and `invoke.url` (base + path). Prompt includes HTTP-specific examples. Requires `--spec` argument (local path or URL).

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

## Future Ideas

- **System monitoring manifests**: A curated `SYSTEM_TOOLS` allowlist of read-only system introspection tools (lsof, ps, df, du, iostat, vmstat, dmesg, who, uptime, sysctl, etc.) gated behind a `--include-system` flag in the manifest factory. These require elevated privileges but are safe (read-only) and useful for LLM-driven diagnostics. Manifests could live in `manifests/system/` so discovery can enable/disable them separately.
- **Discovery test harness** (implemented): `scripts/discovery-test-harness.py` — 200 integration tests across all 7 local manifests (grep, wc, jq, date, bc, apropos, man) plus cross-tool and negative tests. Tests semantic matching quality, invocation correctness, and execution success. Tiered verdicts (PASS/SOFT/WARN/FAIL/SKIP) handle LLM non-determinism. CLI: `--category`, `--test`, `--smoke`, `--dry-run`, `--fail-fast`, `--verbose`, `--json`, `--timeout` (default 120s). Cache tests behind `--include-cache-tests --token <secret>` exercise miss→hit flow via experience API. Target: >80% PASS+SOFT aggregate per category. No model warmup — relies on API server's `lifespan()` warmup on startup. **Full run results (200 tests, 72 min)**: 172 PASS (86%), 21 SOFT, 5 FAIL, 2 SKIP — **96% pass+soft**. By category: grep 35/35 (100%), wc 25/25 (100%), date 25/25 (100%), bc 25/25 (100%), cross 10/10 (100%), jq 33/35 (94%), man 14/15 (93%), apropos 18/20 (90%), neg 8/10 (80%). Failures: jq-019 (jq `-s` slurp on already-array input), jq-030 (missed expected output), apropos-005 (poisoned experience hints — fixed by skipping fixless failure hints), neg-008/009 (LLM too eager to use tools). Main latency bottleneck: map-reduce summarization on large `man`/`apropos` output (single `man tar` test took 200s, 7-chunk apropos queries took 67s+). Fix: bumped `summarize_threshold` from 4000 to 8000.
- **Advanced test harness** (implemented): `scripts/advanced-test-harness.py` — 60 integration tests across 4 categories: file (single-tool file operations), parse (complex data extraction: regex, jq, awk), pipeline (multi-step chained operations), impossible (tasks the system can't solve). Tests use fixture files in `/tmp/oap-test/` (access.log, contacts.txt, data.json, sales.csv, numbers.txt, config.ini, code.py, app.log). CLI: `--category`, `--test`, `--smoke`, `--no-setup`, `--keep-fixtures`, `--verbose`, `--log`, `--timeout` (default 120s), `--token <secret>` (required). **Full run results (30 parse+pipeline tests, 7 min)**: 22 PASS (73%), 8 FAIL. By category: file 15/15 (100%, not in this run), pipeline 13/15 (87%), parse 9/15 (60%). Remaining failures are qwen3:8b model capability ceiling: bad jq syntax, wrong CSV column selection, numeric comparison via regex, LLM refusing to call tools. Progression from infrastructure changes: 23% → 43% (pipe support) → 67% (prompt tuning) → 73% (shlex fallback + exec retry).
- **Big LLM manifest debugger**: Insert a large LLM (e.g., Claude) into the feedback pipeline to diagnose manifest quality issues at runtime. When discovery or tool execution fails, send the task, candidate manifests, and failure context to a big LLM for root-cause analysis — bad description wording, missing input schema, wrong invoke method, etc. Could run as an optional post-mortem step on test harness failures or as a live feedback loop that suggests manifest edits.
- **Non-thinking model for chat rounds** (resolved): qwen3:4b was a thinking model that generated verbose reasoning even with `think=false`. Solved by switching to qwen3:8b which properly respects `think=false` at the weight level (12 tokens/560ms vs 4b's 300+ tokens/10s). 7x faster overall (1m 28s vs 12m 48s for 10 grep smoke tests). Combined with intent extraction, multi-tool injection (top 3 candidates), grep -E default, exit code 1 handling, and flag splitting, this brought grep smoke tests from 50% to 100%.
