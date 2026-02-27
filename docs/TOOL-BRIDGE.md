# OAP Tool Bridge — Architecture Map

How a natural language task becomes a tool invocation via a small LLM (qwen3:8b).

## System Overview

```
 User task (natural language)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  POST /v1/chat                                              │
│                                                             │
│  1. Fingerprint ──► Experience Cache ──► hit? ──► skip to 4 │
│  2. Discovery (vector + FTS5 + LLM ranking)                 │
│  3. Tool injection (blacklist filter, oap_exec first, then  │
│     candidates)                                             │
│  4. Ollama /api/chat loop (up to max_rounds)                │
│  5. Execute tool calls ──► return result to LLM             │
│  6. Cache experience (success or failure)                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Data Stores

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  ChromaDB        │  │  SQLite FTS5     │  │  SQLite          │
│  (vector search) │  │  (keyword search)│  │  (experience)    │
│                  │  │                  │  │                  │
│  nomic-embed-text│  │  BM25 ranking    │  │  oap_experience  │
│  manifests +     │  │  name, desc,     │  │  .db             │
│  descriptions    │  │  tags indexed    │  │                  │
│                  │  │                  │  │  • fingerprint   │
│  ~550 manifests  │  │  oap_fts.db      │  │  • manifest      │
│  (13 hand-coded  │  │  (disabled by    │  │  • confidence    │
│   + ~537 factory)│  │   default)       │  │  • corrections   │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

## Component Detail

### 1. Manifest Factory (`scripts/manifest-factory.py`)

Generates OAP manifests from documentation sources via qwen3:8b.

```
Source adapters:
  ManPageAdapter ─── apropos → man <tool> | col -b → LLM → manifest JSON
  HelpAdapter ────── <tool> --help → LLM → manifest JSON
  OpenAPIAdapter ─── OpenAPI spec → parse endpoints → LLM → manifest JSON

Filters:
  PATH allowlist (/usr/bin, /usr/local/bin, /bin, /opt/homebrew/bin)
  + blocklist (dangerous/interactive/privileged tools)
  + prefix blocklist (perl*, git*, x86_64*, snmp*)

Output: ~540 manifests in reference/oap_discovery/manifests/
  13 hand-coded (tracked in git): grep, wc, jq, date, bc, apropos, man,
                                   sed, awk, cut, tr, paste, column
  ~530 factory-generated (gitignored)
```

### 2. Discovery Pipeline (`discovery.py`)

Finds the right manifest for a task using three signals.

```
Task: "find lines containing email addresses"
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
 Vector DB    FTS5      LLM Ranking
 (semantic)  (keyword)  (qwen3:8b)
    │           │           │
    │  embed    │ tokenize  │  rank candidates
    │  query    │ + BM25    │  by task fit
    │           │           │
    └───────────┼───────────┘
                ▼
         Merged candidates
         (vector order, FTS appended)
                │
                ▼
         LLM picks best match
         (or "none" if no fit)
```

**Intent extraction** (`_extract_search_query`): strips inline data, normalizes
colloquial verbs ("pull out" → "filter"), adds domain hints. Cleans the query
for vector embedding while the full task goes to LLM ranking unchanged.

### 3. Experience Cache (`experience_store.py`, `experience_engine.py`)

Procedural memory that learns from every invocation.

```
Task arrives
    │
    ▼
Fingerprint (qwen3:8b, ~23 tokens, ~1.7s)
    │  e.g. "search.text.pattern_match"
    │
    ▼
┌─────────────────────────────────────┐
│  Experience Store (SQLite)          │
│                                     │
│  Lookup by fingerprint:             │
│  ┌─────────────┬────────┬────────┐  │
│  │ fingerprint  │manifest│conf.  │  │
│  ├─────────────┼────────┼────────┤  │
│  │ search.text  │builtin/│ 0.90  │  │ ◄── cache hit: skip discovery
│  │ .pattern_    │exec    │       │  │
│  │ match        │        │       │  │
│  ├─────────────┼────────┼────────┤  │
│  │ fail_extract │builtin/│ 0.00  │  │ ◄── failure: generates hints
│  │ .json.field  │exec    │       │  │
│  └─────────────┴────────┴────────┘  │
└─────────────────────────────────────┘
```

**Three paths:**
- **Cache hit** (confidence ≥ 0.85, status=success): inject cached tool, skip discovery entirely. ~4s total.
- **Partial match** (same fingerprint prefix): inject as additional candidate alongside discovery results.
- **Cache miss**: full discovery pipeline, then cache the result after successful execution.

**Negative experience & self-correction:**
- Failed tool calls saved with `fail_` ID prefix, confidence=0.0
- `CorrectionEntry` records: what was attempted, the error, and the fix (if self-corrected)
- `_build_experience_hints()` injects past failures into the system prompt:
  ```
  Note — previous attempts at this exact task type:
  - oap_exec({"command":"grep -E ..."}) → Error: invalid option — instead try: ...
  ```
- Only exact-fingerprint failures are included (prefix matching was too aggressive — one wc failure would poison all count.text.* tasks)

**Tool blacklist** (negative experience cache):
- After `blacklist_threshold` failures (default 2) for a `(fingerprint, tool)` pair,
  that tool is excluded from injection in `_discover_tools()`
- Solves the multi-tool mis-selection problem: discovery picks the right tool (wikipedia)
  but the chat LLM sees 3 candidates and picks the wrong one (country-info) because
  "capital" matches its description. After 2 failures, country-info is blacklisted for
  that fingerprint and the chat LLM only sees the correct tool.
- Blacklisted tools are also mentioned in experience hints:
  ```
  - local/country-info is EXCLUDED (failed 2 times for this task type)
  ```
- Blacklist persists until failures are cleared via `DELETE /v1/experience/failures?fingerprint=...`
  (optionally filtered by `&tool=...`)
- Config: `experience.blacklist_threshold` / env `OAP_EXPERIENCE_BLACKLIST_THRESHOLD`
- Debug: `oap_debug: true` includes `blacklisted_tools` in the response

**Degradation:**
- Cache hit + tool error → confidence × 0.7 → retry with full discovery
- Single failure drops 0.90 → 0.63 (below 0.85 threshold), won't serve again

### 4. oap_exec — The Meta-Tool (`tool_api.py`, `tool_executor.py`)

A built-in tool that lets the LLM write CLI commands directly instead of
filling tool parameter schemas.

```
Why it exists:
  LLMs write perfect regex in CLI syntax    │ Training data is full of
  grep -E '[a-zA-Z0-9._%+-]+@[a-z.]+'      │ CLI examples
                                             │
  LLMs mangle regex in tool parameters      │ Tool parameter schemas
  oap_grep({"args": "[-E] [email\\@]..."})  │ are not in training data

Solution:
  oap_exec(command='grep -E pattern', stdin='the text')
  │
  ▼
  shlex.split() ──► validate binary against PATH allowlist
                     ──► asyncio.create_subprocess_exec()
                          (no shell=True, no injection)
```

**Always injected first** — position 0 in the tools list (small LLMs prefer earlier tools).

**Stdio suppression:** after discovery, all stdio tools (grep, wc, jq, etc.) are
filtered out. Only `oap_exec` and HTTP/API tools remain. Rationale: small LLMs
pick "named" tools (oap_grep) over generic ones regardless of system prompt
instructions, but `oap_exec` produces better results.

**File path detection:** `_task_has_file_path()` detects file paths in the task.
When present, discovery is skipped entirely — `oap_exec` is the only tool.
Prevents the LLM from passing file paths as literal stdin text.

**Missing stdin detection:** when `oap_exec` returns "Success (no output)" with
no stdin, inline text in the task, and no file path in the command, the result
is rewritten to an error. This triggers the LLM to retry with stdin and records
a correction in the experience cache.

### 5. Summarization (`tool_executor.py`)

Map-reduce for large tool outputs via sequential `ollama.generate()` calls.

```
Tool result > 4000 chars
    │
    ▼
Split into ~4000-char chunks on newline boundaries
    │
    ▼
Summarize each chunk sequentially (Ollama serializes anyway)
    │  120s timeout per chunk
    │
    ▼
Concatenate summaries
    │
    ▼
If still > max_tool_result → final reduce pass
```

**Known issue:** broad queries (e.g. `apropos archives`) can produce massive
output → many chunks → minutes of Ollama time → blocks all other requests
in the serial inference queue.

## What's Working (Smoke Test Results)

```
Category   Pass Rate   Status   Notes
─────────  ─────────   ──────   ─────
grep       35/35 100%  ✓ SOLID  oap_exec + intent extraction + stdin detection
wc         25/25 100%  ✓ SOLID  oap_exec handles all counting tasks
bc         24/25  96%  ✓ SOLID  LLM does math inline (24 SOFTs) — correct, no tool needed
jq         32/35  91%  ~ GOOD   3 failures from LLM jq knowledge gaps
date        6/25  24%  ✗ WEAK   LLM struggles with date formatting flags
apropos     1/6   17%  ✗ WEAK   experience cache steers toward find/grep instead of apropos;
                                large results trigger summarization cascade

Overall: 123/151 (81%) Pass+Soft in 40m 24s
```

### Why date fails

The LLM knows `date` exists but struggles with format strings. Tasks like
"show the date 3 days from now" or "convert epoch to human-readable" require
specific flag knowledge (`-v+3d`, `date -r <epoch>`) that varies across
GNU/BSD implementations. The manifest description could be more prescriptive.

### Why apropos fails

1. Experience cache learned `search.system.command_lookup → builtin/exec` with
   a `find /usr/bin -type f -exec grep -l` pattern (valid for one task, wrong for others)
2. `find ... grep -l` on binaries returns false positives and massive output
3. Massive output triggers map-reduce summarization → monopolizes Ollama → cascading timeouts
4. Correct command (`apropos <keyword>`) is simple but the cache steers away from it

## Request Lifecycle (Happy Path)

```
Client                    tool_api.py              Ollama            Tool
  │                           │                      │                │
  │  POST /v1/chat            │                      │                │
  │  {task: "count lines"}    │                      │                │
  │──────────────────────────►│                      │                │
  │                           │                      │                │
  │                    fingerprint_intent()           │                │
  │                           │─────────────────────►│                │
  │                           │◄─────────────────────│                │
  │                           │  "count.text.        │                │
  │                           │   line_count"        │                │
  │                           │                      │                │
  │                    experience cache hit!          │                │
  │                    inject oap_exec               │                │
  │                           │                      │                │
  │                    /api/chat (tools=[oap_exec])   │                │
  │                           │─────────────────────►│                │
  │                           │◄─────────────────────│                │
  │                           │  oap_exec(command=   │                │
  │                           │  'wc -l', stdin=...) │                │
  │                           │                      │                │
  │                    execute_exec_call()            │                │
  │                           │──────────────────────────────────────►│
  │                           │◄─────────────────────────────────────│
  │                           │  "      3"           │                │
  │                           │                      │                │
  │                    /api/chat (tool result)        │                │
  │                           │─────────────────────►│                │
  │                           │◄─────────────────────│                │
  │                           │  "The text has       │                │
  │                           │   3 lines."          │                │
  │                           │                      │                │
  │  {message: "3 lines",     │                      │                │
  │   oap_experience_cache:   │                      │                │
  │   "hit", oap_round: 2}   │                      │                │
  │◄──────────────────────────│                      │                │
```

## File Map

```
reference/oap_discovery/
├── oap_discovery/
│   ├── tool_api.py          ── /v1/chat, /v1/tools, oap_exec, experience wiring
│   ├── tool_executor.py     ── execute_tool_call, execute_exec_call, summarization
│   ├── tool_converter.py    ── manifest → Ollama tool schema, stdin/args splitting
│   ├── tool_models.py       ── Pydantic types for tools, chat, registry
│   ├── discovery.py         ── vector search + FTS5 + LLM ranking + intent extraction
│   ├── experience_engine.py ── fingerprinting, three-path routing
│   ├── experience_store.py  ── SQLite CRUD for experience records
│   ├── experience_models.py ── ExperienceRecord, CorrectionEntry, etc.
│   ├── experience_api.py    ── /v1/experience/ REST endpoints
│   ├── fts_store.py         ── SQLite FTS5 full-text search
│   ├── db.py                ── ChromaDB manifest store
│   ├── invoker.py           ── HTTP + stdio manifest execution
│   ├── ollama_client.py     ── generate(), chat(), embed() with timeout/think control
│   ├── api.py               ── FastAPI app, lifespan, route wiring
│   └── config.py            ── YAML config + env var overrides
├── manifests/               ── 13 hand-coded + ~530 factory-generated
│   ├── grep.json
│   ├── wc.json
│   ├── jq.json
│   ├── sed.json
│   ├── awk.json
│   ├── cut.json
│   ├── tr.json
│   ├── paste.json
│   ├── column.json
│   ├── date.json
│   ├── bc.json
│   ├── apropos.json
│   ├── man.json
│   └── ... (~530 factory-generated, gitignored)
└── config.yaml              ── Ollama URLs, DB paths, feature flags

scripts/
├── manifest-factory.py      ── auto-generate manifests from man/help/openapi
└── discovery-test-harness.py ── 151 integration tests across all manifests

Data files (gitignored):
├── oap_experience.db        ── experience cache (fingerprints → manifests)
├── oap_fts.db               ── FTS5 keyword index (disabled by default)
└── chroma_db/               ── vector embeddings (nomic-embed-text)
```
