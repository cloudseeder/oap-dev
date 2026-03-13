# OAP Reference Architecture

**A complete discovery stack that runs on a laptop.**

---

## Design Principle

Knowledge lives where it belongs. Manifests stay on publishers' domains. Discovery runs locally. The expensive model does the work. The cheap model finds the work. No cloud dependency for discovery. No central service to go down, get acquired, or start charging rent.

## The Stack

```
+---------------------------------------------------+
|                    Agent Task                     |
|          "Transcribe last week's Portland         |
|           city council meeting"                   |
+-------------------------+-------------------------+
                          |
                          v
+---------------------------------------------------+
|           Experience Cache (local)               |
|                                                   |
|  Dual-store: SQLite + ChromaDB vectors.           |
|  Embed task → cosine search → cache hit if        |
|  distance < 0.25 and confidence ≥ 0.85.           |
|  Hit? Replay cached invocation. Miss? Continue.   |
+-------------------------+-------------------------+
                          |  (cache miss)
                          v
+---------------------------------------------------+
|             Discovery Layer (local)               |
|                                                   |
|  +--------------+    +-------------------------+  |
|  | Small LLM    |<-->| Vector DB + FTS5        |  |
|  | (8B)         |    | (embedded manifest      |  |
|  |              |    |  index + keyword search) |  |
|  +--------------+    +-------------------------+  |
|                                                   |
|  Intent extraction → vector search + BM25 →       |
|  LLM ranking → up to 3 tools injected             |
+-------------------------+-------------------------+
                          |
                          v
+---------------------------------------------------+
|          Execution Layer (local + escalation)     |
|                                                   |
|  +--------------+    +-------------------------+  |
|  | Small LLM    |--->| Tool bridge executes    |  |
|  | (tool calls, |    | oap_exec + HTTP tools   |  |
|  |  multi-round)|    | in sandboxed subprocess |  |
|  +--------------+    +-------------------------+  |
|         |                                         |
|         v  (large results or escalate_prefix)     |
|  +--------------+                                 |
|  | Big LLM      |  Claude, GPT, Gemini — only    |
|  | (optional)   |  for final reasoning on large   |
|  +--------------+  outputs the small model can't  |
|                     handle                        |
+-------------------------+-------------------------+
                          |
                          v
+---------------------------------------------------+
|              Crawl Layer (background)             |
|                                                   |
|  Periodically fetches /.well-known/oap.json       |
|  from known domains. Embeds new/updated           |
|  manifests. Refreshes vector index.               |
|  Checks health endpoints. Prunes dead entries.    |
+---------------------------------------------------+
```

## Five Cognitive Jobs, Tiered Cost

The key insight: discovery and execution are different cognitive tasks requiring different levels of intelligence. The original design had three tiers. Production experience revealed five distinct jobs at three cost points.

**Experience cache lookup** checks if this task (or one semantically similar) has been seen before. Embed the task with nomic-embed-text (~50ms), cosine search against the experience vector store, replay the cached invocation if the distance is under 0.25. No LLM involved. Near zero cost. This is the fast path — most repeated tasks never reach discovery.

**Intent extraction** preprocesses the raw task before embedding. `_extract_search_query()` strips inline data (everything after `\n`), normalizes colloquial verbs (`pull out` to `filter`), strips trailing prepositions, and appends domain hints. The cleaned query goes to vector search; the full task still goes to LLM ranking unchanged. This step exists because raw user queries embed poorly — "pull out the emails from Amy about invoices" drifts in vector space, while "filter emails" lands precisely.

**Similarity search + keyword search** finds candidate manifests matching the agent's intent. Vector search embeds the cleaned query and returns nearest neighbors from ChromaDB. FTS5 keyword search (SQLite with BM25 ranking) runs in parallel as a complement — deterministic keyword matching fills gaps where vector search drifts on proper nouns, tool names, or domain-specific terms. Results are merged and deduped before LLM ranking. Sub-50ms combined.

**Manifest reasoning** reads the top candidates and picks the
best fit for the task. A small local LLM (8B parameters)
handles this — reading descriptions, evaluating fit, selecting
the winner. Runs on GPU via Ollama. Minimal cost.

**Task execution** is now handled by the tool bridge, not a separate frontier model. The same small LLM that picks manifests also makes tool calls — `oap_exec` for CLI tasks, HTTP invocations for API tools. Multi-round execution loops up to `max_rounds`. For most tasks, the small model handles everything end-to-end.

**Big LLM escalation** (optional) sends the final reasoning step to an external model (Claude, GPT, Gemini) only when the small model demonstrably cannot handle the output — large results exceeding `summarize_threshold` characters, or tasks matching configured `escalate_prefixes`. The small model still does discovery and tool execution. The big model only reasons about the result. Fails silently — falls back to the small model on any error.

The expensive model never wastes tokens on discovery or tool calls. The cheap model handles the full pipeline for the 90% of tasks that don't need frontier reasoning. Escalation is the exception, not the rule.

---

## Minimum Hardware

### Tier 1: Laptop (Development / Personal Agent)

For a developer running their own discovery stack locally.

**CPU:** Any modern 4-core works. An 8+ core chip is better — 
Apple M-series, AMD Ryzen 7, or Intel i7. The small LLM 
benefits from more cores during CPU inference.

**RAM:** 16GB minimum. 32GB recommended. The LLM, vector DB, 
and crawler all share memory — 16GB is tight but functional, 
32GB gives comfortable headroom.

**GPU:** Not required. CPU inference works for the small 
discovery LLM. Apple M-series unified memory is ideal since 
the GPU shares system RAM with no copy overhead. An NVIDIA 
GPU with 8+ GB VRAM accelerates inference but isn't necessary.

**Storage:** 20GB free on an SSD. 50GB on NVMe preferred. 
Models, the vector index, and cached manifests all live on 
disk. SSDs matter — spinning disks bottleneck vector search.

**OS:** macOS or Linux recommended. Windows works through 
WSL2 but adds a layer of friction.

This runs the small LLM for manifest reasoning, the vector database for similarity search, and the crawler — all locally. The frontier model for task execution is called via API (Claude, GPT, etc.) or runs locally if you have the hardware.

**Performance expectations:** Discovery latency under 500ms. Vector search under 50ms. Manifest reasoning 1-3 seconds on CPU, under 500ms with GPU. Handles a manifest index of 100,000+ capabilities comfortably.

### Tier 2: Server (Team / Production)

For a team running a shared discovery service.

**CPU:** 8 cores minimum, 16+ recommended. Concurrent 
discovery queries from multiple agents need parallel 
processing headroom.

**RAM:** 32GB minimum. 64GB recommended. The larger index 
(millions of manifests) and concurrent queries consume 
significantly more memory than a personal setup.

**GPU:** NVIDIA with 12+ GB VRAM minimum — an RTX 3060 or 
better. Recommended: NVIDIA A10 or L4 with 24GB VRAM. GPU 
acceleration drops manifest reasoning from seconds to 
sub-100ms, which matters when serving multiple agents.

**Storage:** 100GB NVMe SSD minimum. 500GB recommended. 
A million-manifest index with cached raw manifests, 
embeddings, and crawl logs adds up.

**Network:** 100 Mbps minimum. 1 Gbps recommended. The 
crawler is constantly fetching manifests and the discovery 
API is serving results — bandwidth matters at production 
scale.

### Tier 3: Virtual / Cloud

Any of the above can run in cloud VMs.

**AWS:** g5.xlarge — one A10G GPU with 24GB VRAM, 4 vCPU, 
16GB RAM. Roughly $500/month.

**GCP:** g2-standard-4 — one L4 GPU with 24GB VRAM, 4 vCPU, 
16GB RAM. Roughly $450/month.

**Azure:** Standard_NC4as_T4_v3 — one T4 GPU with 16GB VRAM, 
4 vCPU, 28GB RAM. Roughly $400/month.

**Budget:** Any 8-core, 32GB RAM VPS with CPU-only inference. 
$50-100/month. The small LLM runs slower but discovery latency 
remains acceptable for most use cases.

### Reference Platform: The $549 Mac Mini

In January 2026, an open-source personal agent called OpenClaw made Mac Minis hard to buy. Within weeks it had over 145,000 GitHub stars and people were buying dedicated Mac Minis as always-on personal agent hardware. The reasons turn out to be architecturally significant, not just convenient — and the same machine runs the entire OAP discovery stack alongside the agent itself.

**Why the Mac Mini is almost suspiciously perfect for this moment:**

**Unix under the hood.** macOS is BSD. Terminal, shell scripts, cron jobs, process daemons, file system permissions — all native. The entire OAP stack assumes Unix primitives: a background crawler process, a database, a local API server. That's not something you bolt onto Windows. It's the native environment on macOS.

**Apple Silicon changed the economics.** The M4 chip in the base Mac Mini runs local LLMs in a way that was impossible three years ago. Unified memory means the CPU and GPU share the same RAM — no copying tensors between system memory and VRAM. A 4B parameter model runs entirely in the chip's neural engine and GPU cores, leaving CPU headroom for everything else. No discrete GPU. No CUDA. No thermal throttling in a closet.

**Always-on at consumer power draw.** A Mac Mini idles at 5-7 watts. That's less than a nightlight. Running 24/7 costs roughly $5-8 per year in electricity. Compare that to a cloud VM at $50-100 per month. The Mac Mini pays for itself versus cloud hosting in under six months and runs for years.

**No Linux expertise required.** A Raspberry Pi or NUC running Ubuntu could technically run the same stack. But OpenClaw hit 145,000 stars because normal people can set it up. macOS has automatic updates, Time Machine backups, and a setup wizard. The barrier to running your own personal agent went from "be a Linux sysadmin" to "buy a Mac Mini and follow a tutorial."

#### The Complete Stack on One Machine

A base-model Mac Mini (M4, 16GB unified memory, 256GB SSD, $549) runs the entire personal agent + OAP discovery stack simultaneously:

```
+-----------------------------------------------------------+
|                   Mac Mini (M4 / 16GB)                    |
|                                                           |
|  +-----------------------------------------------------+  |
|  |               Manifest Agent (:8303)                |  |
|  |  Chat + autonomous tasks + voice (STT/TTS)         |  |
|  |  Vite SPA frontend + FastAPI backend                |  |
|  |  Calls /v1/chat on discovery — never talks to       |  |
|  |  Ollama directly                                    |  |
|  +---------------------------+-------------------------+  |
|                              |                            |
|  +---------------------------v-------------------------+  |
|  |         OAP Discovery + Tool Bridge (:8300)         |  |
|  |                                                     |  |
|  |  +----------------+    +--------------------------+ |  |
|  |  | Ollama         |    | ChromaDB                  | |  |
|  |  | qwen3:8b       |    | Manifest vector index     | |  |
|  |  | + nomic        |    | Experience vector store   | |  |
|  |  |   embed-text   |    | ~100MB for 10K manifests  | |  |
|  |  | ~5.9GB VRAM    |    | ~500MB RAM                | |  |
|  |  +----------------+    +--------------------------+ |  |
|  |                                                     |  |
|  |  +----------------+    +--------------------------+ |  |
|  |  | Crawler        |    | SQLite stores             | |  |
|  |  | (background    |    | FTS5 keyword index        | |  |
|  |  |  + seed crawl  |    | Experience cache          | |  |
|  |  |  on startup)   |    | Reminder DB               | |  |
|  |  | ~50MB RAM      |    | Email cache               | |  |
|  |  +----------------+    +--------------------------+ |  |
|  +------------------------------------------------------+ |
|                                                           |
|  +-----------------------------------------------------+  |
|  |              Additional Services                    |  |
|  |  Trust API (:8301)     — domain attestation         |  |
|  |  Dashboard API (:8302) — adoption tracking          |  |
|  |  Reminder API (:8304)  — recurring reminders        |  |
|  |  Email Scanner (:8305) — IMAP + classification      |  |
|  +-----------------------------------------------------+  |
|                                                           |
|  RAM budget: ~7GB active (9GB free for OS + headroom)     |
|  Storage: ~10GB (models + indexes + manifests + DBs)      |
|  Power: 7-15W under typical load                          |
|  Network: Outbound only (API calls + crawler + IMAP)      |
+-----------------------------------------------------------+
```

#### Bill of Materials

| Component | Cost |
|-----------|------|
| Mac Mini (M4, 16GB, 256GB) | $549 (one-time) |
| Ollama (LLM runtime) | Free |
| qwen3:8b + nomic-embed-text (discovery + tool bridge models) | Free |
| ChromaDB (vector database + experience vectors) | Free |
| Python + FastAPI (all services) | Free |
| Manifest agent (chat + tasks + voice) | Free |
| Claude / GPT API (big LLM escalation, optional) | ~$0-10/month |
| Electricity (always-on operation) | ~$0.50/month |
| **Total first year** | **~$555-675** |

The cost model changed significantly with the tool bridge. The small LLM now handles the full pipeline — discovery, tool execution, and response generation — for most tasks. Big LLM escalation is optional and only fires for large outputs or configured prefixes. Many deployments run entirely local with zero API costs.

Compare to running an equivalent stack in the cloud: a GPU-capable VM for the local LLM ($400-500/month) plus the same frontier API costs. That's $5,000-6,000 per year. The Mac Mini pays for itself in under five weeks.

#### Setup

```bash
# 1. Install Homebrew (if not present)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Install Ollama (local LLM runtime)
brew install ollama
ollama serve &

# 3. Pull the two models the discovery stack needs:
#    - qwen3:8b — small LLM for manifest reasoning, tool calls, and chat
#    - nomic-embed-text — embedding model that converts descriptions to vectors
ollama pull qwen3:8b              # ~4.9 GB, reasoning + tool calling model
ollama pull nomic-embed-text      # ~274 MB, vector embeddings

# 4. Clone the OAP repository
git clone https://github.com/cloudseeder/oap-dev.git
cd oap-dev

# 5. Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 6. Install the reference services
#    Each is a Python package with entry-point commands
pip install -e reference/oap_discovery   # provides: oap-api, oap-crawl, oap
pip install -e reference/oap_trust       # provides: oap-trust-api, oap-trust
pip install -e reference/oap_dashboard   # provides: oap-dashboard-api, oap-dashboard-crawl
pip install -e reference/oap_agent       # provides: oap-agent-api
pip install -e reference/oap_reminder    # provides: oap-reminder-api
pip install -e reference/oap_email       # provides: oap-email-api (requires config.yaml with IMAP credentials)

# 7. Add seed domains for the crawler
#    The crawler fetches https://<domain>/.well-known/oap.json for each
cd reference/oap_discovery
echo "example.com" >> seeds.txt          # add domains you want to index

# 8. Run the initial crawl
#    This fetches manifests, embeds descriptions via nomic-embed-text,
#    and stores the vectors in a local ChromaDB database (./oap_data/)
oap-crawl --once

# 9. Start the discovery API (includes tool bridge, experience cache, Ollama pass-through)
#    Accepts natural-language queries, searches ChromaDB by vector similarity,
#    then uses qwen3:8b to pick the best manifest match.
#    Also serves /v1/chat and /api/chat for tool-augmented LLM conversations.
oap-api &                                # http://localhost:8300

# 10. Start the Manifest agent (optional — chat + task UI)
cd ../oap_agent
oap-agent-api &                          # http://localhost:8303

# 11. Start the trust provider (optional)
cd ../oap_trust
oap-trust-api &                          # http://localhost:8301

# 12. Start the dashboard (optional)
cd ../oap_dashboard
oap-dashboard-crawl --once               # initial crawl into SQLite
oap-dashboard-api &                      # http://localhost:8302

# 13. Start the reminder service (optional)
cd ../oap_reminder
oap-reminder-api &                       # http://localhost:8304

# 14. Start the email scanner (optional — requires IMAP config)
cd ../oap_email
oap-email-api &                          # http://localhost:8305
```

You can verify the stack is running:

```bash
# Check discovery health (should show ollama: true, index_count > 0)
curl http://localhost:8300/health

# Try a discovery query
curl -X POST http://localhost:8300/v1/discover \
  -H "Content-Type: application/json" \
  -d '{"task": "summarize text"}'

# Try the tool bridge — the small LLM discovers tools, calls them, and responds
curl -X POST http://localhost:8300/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3:8b", "messages": [{"role": "user", "content": "what is the weather in Portland?"}]}'

# Open the Manifest agent UI
open http://localhost:8303
```

#### Connecting an Agent: OpenClaw Example

The discovery stack is useful on its own, but the real payoff is when an agent uses it at runtime. [OpenClaw](https://openclaw.ai) is an open-source personal agent that runs locally on the Mac Mini — the same machine running the discovery stack. With OAP discovery enabled, OpenClaw can find and invoke capabilities that weren't in its training data.

```bash
# 12. Install OpenClaw (see openclaw.ai for current instructions)
npm install -g openclaw

# 13. Start OpenClaw with OAP discovery pointed at the local stack
export OAP_DISCOVERY_URL=http://localhost:8300
openclaw start
```

When a user asks OpenClaw to do something it doesn't have a built-in tool for, it queries the local discovery API, gets back a manifest with invocation details, and calls the endpoint directly. The agent never phones home — discovery happens entirely on your machine.

This is the pattern OAP enables for any agent, not just OpenClaw. Any agent that can make an HTTP POST to `/v1/discover` and read the manifest response can use the discovery stack. The integration is one API call.

From unboxing to a personal agent with open internet discovery: under two hours. Most of that is downloading models.

#### Why This Matters

The Mac Mini isn't just convenient hardware. It's a statement about who controls the personal agent.

A personal agent running on Google's servers serves Google's interests alongside yours. A personal agent running on your Mac Mini, in your house, on your network, serves you. The discovery is private — your queries never leave the machine during the discovery phase. The manifest index is yours — no one decides what capabilities you can or can't find. The agent's memory is a folder on your SSD — not a row in someone else's database.

Apple probably doesn't realize they've built the default hardware platform for the personal agent era. They think they're selling a budget desktop. They're actually selling the home server for AI — a Unix machine with consumer UX, local ML acceleration, negligible power draw, and a price point that makes the whole stack accessible to anyone.

One box. $549. Your agent. Your data. Your discovery. No one else's agenda.

---

## Small LLM Recommendations

The discovery LLM's job expanded since the initial design. It still reads manifest descriptions and picks the best match — but now it also makes tool calls, reasons about tool output, and generates user-facing responses via the tool bridge. This requires instruction following, reading comprehension, structured output (JSON tool calls), and basic reasoning. The model needs to be good at tool calling, not just classification.

### Recommended Models (as of March 2026)

**qwen3:8b** — 8 billion parameters, roughly 5.9GB VRAM at Q4 with 4K context. The **production default**. Best balance of tool-calling reliability, reasoning quality, and VRAM usage on 16GB machines. Hybrid think/no-think modes: `think: false` (default) keeps responses to ~12 tokens per tool-call round; `think: true` can be enabled per-task via `think_prefixes` config for tasks requiring output verification. At 4K context (`num_ctx: 4096`) it fits alongside nomic-embed-text with headroom to spare. Apache 2.0 license.

**qwen3.5:9b** — 9 billion parameters. The **latest tested model** as of March 2026. Improved reasoning over qwen3:8b with similar VRAM requirements. Drop-in replacement — same Ollama config, same tool-calling interface.

**Qwen 3 4B** — 4 billion parameters, roughly 3GB VRAM quantized at Q4. A viable option for constrained hardware. Adequate for discovery-only use (manifest matching without tool bridge), but tool-calling reliability drops compared to the 8B models. The path-to-23-tokens optimization work was done on this model.

**Phi-4-mini-instruct** — 3.8 billion parameters, roughly 3GB VRAM quantized. Strong instruction following and reasoning at minimal size, with a 128K context window that handles large manifests easily. MIT license.

**Llama 3.2 3B** — 3 billion parameters, roughly 2GB VRAM quantized. The smallest viable option for discovery-only. Not recommended for tool bridge use — tool-calling reliability is insufficient.

**SmolLM3 3B** — 3 billion parameters, roughly 2GB VRAM quantized. Fully open from Hugging Face with transparent training methodology. Outperforms Llama 3.2 3B on most benchmarks while maintaining the same footprint.

### Model Selection Guidance

**Constrained hardware** — laptop or edge device with 16GB system RAM and no discrete GPU. Use Qwen 3 4B for discovery-only. For tool bridge use, qwen3:8b still works on CPU but expect 5-10 second response times per round.

**Good hardware (recommended)** — M-series Mac or a machine with a gaming GPU (8+ GB VRAM). Use **qwen3:8b** or **qwen3.5:9b**. This is the production sweet spot. The Mac Mini M4 with 16GB runs qwen3:8b at 4K context using ~5.9GB VRAM, leaving room for nomic-embed-text and all services.

**Server with GPU** — dedicated machine with 12+ GB VRAM. Use qwen3:8b with a larger context window (`num_ctx: 8192` or higher) for complex multi-tool tasks. Or run qwen3.5:9b with full context.

### Runtime

**Ollama** is the recommended runtime for all models. Single command install, no Python environment, no CUDA configuration:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull your chosen model
ollama pull qwen3:8b           # Production default
ollama pull qwen3.5:9b         # Latest tested
ollama pull qwen3:4b           # Constrained hardware / discovery-only
ollama pull nomic-embed-text   # Required for embeddings
```

Ollama exposes a local API at `http://localhost:11434` that the discovery service calls. The OAP discovery service proxies Ollama's non-chat `/api/*` endpoints transparently, so agents can use OAP as a drop-in Ollama replacement: `OLLAMA_HOST=http://localhost:8300 ollama run qwen3:8b`.

**Ollama tuning for 16GB machines:** Set `num_ctx: 4096` to cap VRAM usage, `keep_alive: "-1m"` to keep models permanently loaded (eliminates cold-start latency), and warm up on startup with a throwaway `generate("hello")` call. Override context size via `OAP_OLLAMA_NUM_CTX` env var.

---

## Vector Database Recommendations

The vector database stores embedded manifest descriptions and performs similarity search when an agent has a task. Requirements: fast similarity search, metadata filtering, easy to run locally, and handles 100K-10M vectors without breaking a sweat.

### Recommended Options

**ChromaDB** — best for getting started, prototyping, and small indexes under a million manifests. Runs embedded in-process with no server needed. `pip install chromadb` and you're running. In-memory mode eliminates all setup friction. Rewritten in Rust in 2025 — 4x faster than the original. Apache 2.0 license.

**Qdrant** — best for production and larger indexes. Written in Rust with sub-100ms queries on millions of vectors. Excellent metadata filtering for narrowing results by tags, capability type, or trust level. Run via Docker:

```bash
docker run -p 6333:6333 qdrant/qdrant
```

Apache 2.0 license.

**LanceDB** — best for edge and embedded deployments. No server process at all — it's a library that reads/writes directly to disk. Perfect for agents running on laptops or edge devices. Zero operational overhead. Apache 2.0 license.

**Milvus Lite** — best for local development when you want a path to enterprise scale. Runs as an embedded Python library for development, then scales to a distributed cluster for production without changing your code. Apache 2.0 license.

### Embedding Model

Manifests need to be converted to vectors before storage. The embedding model determines how well similarity search matches intent to capability.

**all-MiniLM-L6-v2** — 384 dimensions, 80MB. Fast and good enough for most cases. The default starting point if you want minimal resource usage.

**nomic-embed-text** — 768 dimensions, 274MB. Better semantic understanding than MiniLM. Runs via Ollama (`ollama pull nomic-embed-text`) alongside your discovery LLM with no additional infrastructure. The recommended sweet spot for OAP.

**mxbai-embed-large** — 1024 dimensions, 670MB. Highest quality local embeddings available. Use if discovery accuracy matters more than speed and you have the memory budget.

---

## Crawler Design

The crawler is the background process that builds and maintains your local manifest index. It's conceptually identical to a web crawler, but only looks for one file.

### Basic Crawl Loop

```
1. Maintain a list of domains to crawl (seed list)
2. For each domain:
   a. Fetch https://{domain}/.well-known/oap.json
   b. If found and valid:
      - Embed the description field
      - Store manifest + vector in the database
      - Record timestamp and health status
   c. If not found or invalid:
      - Mark as inactive, retry with backoff
3. Optionally check health endpoints for active manifests
4. Sleep. Repeat.
```

### Seed Discovery

Where does the initial list of domains come from?

**Manual curation.** Start with domains you know. Your own apps. Partner services. Community lists.

**DNS TXT scanning.** Look for `_oap` TXT records on known domains.

**Sitemap-style submission.** Accept domain submissions via a simple API or web form.

**Referral crawling.** When a manifest includes a `publisher.url`, crawl that domain too.

**Web crawl piggyback.** If you're running a general web crawler, check for `/.well-known/oap.json` on every domain you visit.

### Crawl Frequency

**New or recently changed manifests** — every 6 hours. Freshness matters most when a capability first appears or its description is actively being refined.

**Stable manifests** unchanged for 7+ days — every 24-48 hours. Frequent enough to catch updates, infrequent enough to be polite.

**Inactive manifests** where the health check is failing — every 72 hours, then prune. Don't waste crawl cycles on dead capabilities.

Respect the `updated` field in manifests — if it hasn't changed, don't re-embed.

---

## Tool Bridge

The tool bridge is the execution engine that turns OAP from a discovery service into a complete agent runtime. It intercepts Ollama-compatible chat requests, discovers relevant tools from the manifest index, injects them into the conversation, executes tool calls, and loops until the LLM produces a final response.

### Endpoints

**`POST /v1/chat`** — the primary tool-augmented chat endpoint. Accepts Ollama-compatible request format with additional OAP fields (`oap_debug`, streaming control). Discovers tools, injects them, executes tool calls in a multi-round loop.

**`POST /api/chat`** — Ollama wire-compatible alias. Same behavior as `/v1/chat` but returns responses in Ollama NDJSON streaming format. This makes OAP a drop-in Ollama replacement: `OLLAMA_HOST=http://localhost:8300 ollama run qwen3:8b`.

**Ollama pass-through** — non-chat `/api/*` endpoints (`/api/tags`, `/api/show`, `/api/ps`, `/api/generate`, `/api/embed`, `/api/embeddings`) proxy directly to Ollama. This means an agent pointing at OAP for chat also gets model listing, embedding, and generation without any additional configuration.

### Multi-Tool Injection

Each chat round, `_discover_tools()` injects up to `MAX_INJECTED_TOOLS = 3` tools — the LLM's top-ranked manifest plus the next highest-scoring candidates, deduped by domain. This lets the LLM choose between related tools (e.g., `newsapi-top-headlines` vs. `newsapi-everything`) rather than being locked into a single discovery result.

### oap_exec Meta-Tool

A built-in tool always injected first in every chat round. Accepts `command` + optional `stdin`. This bridges LLM CLI knowledge to tool calls — LLMs write better regex in `grep` syntax than in tool parameter schemas.

Security model:
- `shlex.split()` parsing (no `shell=True`)
- PATH allowlist: `/usr/bin/`, `/usr/local/bin/`, `/bin/`, `/opt/homebrew/bin/`
- Configurable `blocked_commands` (default: `rm, rmdir, dd, mkfs, shutdown, reboot`)
- Shell-style pipes via `_split_pipeline()` — each stage validated independently
- File path detection (`_task_has_file_path`) suppresses manifest discovery when file paths are present, making `oap_exec` the only available tool

### Stdio Tool Suppression

After discovery, stdio-invoked tools (those using stdin/stdout) are filtered out — only `oap_exec` and HTTP/API tools remain. Rationale: small LLMs prefer "named" tools over generic `oap_exec` but produce worse results with them. The LLM already knows how to use CLI tools via `oap_exec`; giving it both a named `grep` tool and `oap_exec` causes confusion.

### Credential Injection

API keys from `credentials.yaml` are injected into tool calls at execution time, transparent to the LLM. The system prompt tells the model "API credentials are pre-configured" so it never refuses to call authenticated APIs.

Placement modes (via manifest `invoke.auth_in`):
- `auth_in: "header"` (default) — key as HTTP header
- `auth_in: "query"` — key as query parameter
- `auth: "bearer"` — key as `Authorization: Bearer` header

Domain lookup falls back from indexed domain (`local/alpha-vantage`) to invoke URL hostname (`www.alphavantage.co`), so `credentials.yaml` can use real domain names for local manifests.

### Sandbox

OS-level file-write protection via macOS `sandbox-exec` (Seatbelt). All subprocess execution — oap_exec single commands, pipelines, and manifest stdio tools — is wrapped with a profile that denies file writes except to a configurable sandbox directory (default `/tmp/oap-sandbox`).

- Config: `tool_bridge.danger_will_robinson` (default `false` — sandbox ON)
- The system prompt tells the LLM to write output files to the sandbox directory
- Graceful degradation on Linux (unsandboxed, warning logged)

### Conditional Thinking

Per-fingerprint toggle for `think: true` on Ollama requests. When a task's fingerprint starts with a configured prefix (e.g., `compute`), thinking mode is enabled so the model can verify tool output (arithmetic, data validation). Default: thinking off for speed (~12 tokens per round).

### Map-Reduce Summarization

Fallback for large tool results when big LLM escalation is not configured. When a tool result exceeds `summarize_threshold` (default 16000 chars), it is chunked and summarized via multiple `ollama.generate()` calls, then the summaries are combined. Hierarchy: big LLM escalation (preferred) > map-reduce > truncation.

### Big LLM Escalation

Optional external model escalation for results the small model cannot handle. When enabled (`escalation.enabled: true`), two triggers send the final reasoning to Claude, GPT, or Gemini:

1. **Prefix match** — task fingerprint starts with a configured `escalate_prefix`
2. **Large output** — any `oap_exec` result exceeding `summarize_threshold` chars is automatically escalated, bypassing lossy map-reduce

The small model still handles discovery and tool execution. The big model only reasons about the final result.

Providers: `openai`, `anthropic`, `googleai` (OpenAI-compatible). Per-provider API key env vars (`OAP_OPENAI_API_KEY`, `OAP_ANTHROPIC_API_KEY`, `OAP_GOOGLEAI_API_KEY`) allow provider switching without redeployment. Fails silently on any error — falls back to small model response.

### Debug Mode

`POST /v1/chat` accepts `oap_debug: true` for full execution trace: tools discovered, experience cache status, fingerprint, hints, thinking/escalation flags, and per-round tool executions with timing.

---

## Experience Cache (Procedural Memory)

The experience cache is a learning layer that sits in front of discovery. When the tool bridge successfully completes a task, it caches the full invocation — task text, fingerprint, tool used, parameters, result summary. On subsequent similar tasks, it replays the cached invocation without re-running discovery or LLM ranking.

### Dual-Store Architecture

**SQLite** (`oap_experience.db`) is the system of record. Stores all experience records, failure history, correction entries, and metadata. Survives restarts, supports exact fingerprint lookup.

**ChromaDB** (`experience_vectors/`) is the vector index for similarity lookup. Task texts are embedded with nomic-embed-text and stored as vectors. Primary cache lookup path: embed incoming task (~50ms) > cosine search > cache hit if distance < `vector_similarity_threshold` (default 0.25) and confidence >= 0.85.

Vector similarity replaced fingerprint string matching as the primary cache key because LLM fingerprints are non-deterministic — the same intent produces different fingerprint strings across runs. Embedding similarity is stable.

### Cache Lookup Flow

1. Embed task with nomic-embed-text (~50ms)
2. ChromaDB cosine search for nearest neighbor
3. If distance < 0.25 and confidence >= 0.85: **cache hit** — replay cached invocation
4. Fallback: exact fingerprint match in SQLite
5. If no match: **full discovery** — vector search + LLM ranking > execute > cache on success

### Confidence Degradation

Errors multiply confidence by 0.7. A single failure drops a cached entry below the 0.85 threshold, forcing re-discovery on the next attempt. This self-heals: if an API endpoint goes down and comes back, the next successful invocation restores confidence.

### Negative Caching

Failures are stored with `CorrectionEntry` records that become self-correction hints. `_build_experience_hints(fingerprint)` injects past failure/success hints into the system prompt, guiding the LLM away from known-bad approaches.

### Backfill Migration

On startup, if the vector collection is empty but SQLite has records, all task texts are embedded and upserted into ChromaDB. This handles upgrades from fingerprint-only caching to vector similarity.

---

## FTS5 Keyword Search

SQLite FTS5 with BM25 ranking complements vector search for manifest discovery. Vector search excels at semantic similarity ("find me a way to check the weather" matches a weather API manifest), but drifts on proper nouns, tool names, and domain-specific terms. FTS5 provides deterministic keyword matching that fills these gaps.

Config: `fts.enabled` (default false), `fts.db_path`. When enabled, keyword search runs in parallel with vector search during discovery, and results are merged and deduped before LLM ranking.

---

## Service Architecture

The reference implementation runs six services on a single machine. Three are core (discovery, agent, Ollama), three are optional.

### Port Map

| Port | Service | Purpose |
|------|---------|---------|
| 8300 | Discovery API | Manifest search, tool bridge, experience cache, Ollama pass-through |
| 8301 | Trust API | Domain attestation, capability testing |
| 8302 | Dashboard API | Adoption tracking, manifest listing |
| 8303 | Manifest Agent | Chat UI + autonomous tasks + voice (STT/TTS) |
| 8304 | Reminder API | Recurring reminders for agents |
| 8305 | Email Scanner | IMAP scanning, LLM classification, auto-filing |
| 11434 | Ollama | LLM runtime (proxied through :8300 for chat) |

### Manifest Agent (:8303)

Chat + autonomous task execution. A thin orchestrator that calls `/v1/chat` on the discovery service for all LLM and tool work — it never talks to Ollama directly. Self-contained: `oap-agent-api` serves both the FastAPI backend and a Vite SPA frontend at `http://localhost:8303`.

Key capabilities:
- **Interactive chat** via SSE streaming, with personality and user memory
- **Autonomous tasks** — cron-scheduled background jobs via APScheduler, max 20 tasks, minimum 5-minute intervals
- **Notification queue** — task results produce notifications that power greeting briefings ("Good morning — here's what happened overnight")
- **User memory** — learns facts about the user from conversations via fire-and-forget LLM extraction, stored in SQLite with dedup and LRU eviction
- **Voice** — local STT via faster-whisper (CTranslate2) + TTS via Piper neural voices, both running on the backend

### Reminder Service (:8304)

SQLite-backed reminder service for AI agents. Supports one-time and recurring reminders (daily, weekly, monthly, yearly). Completing a recurring reminder auto-creates the next occurrence. Exposed as an OAP manifest for discovery by the tool bridge.

### Email Scanner (:8305)

IMAP email scanner with LLM-powered classification and auto-filing. Two-phase design:
1. `POST /scan` fetches from IMAP and caches to SQLite (UID-based incremental scanning)
2. Read endpoints query local cache — no IMAP connection needed for reads

The classifier categorizes messages using the local LLM via Ollama. Default categories: `personal`, `machine`, `mailing-list`, `spam`, `offers` — user-configurable via `config.yaml`. Auto-filing moves classified messages into IMAP folders based on category. Designed for cron: `curl -s -X POST localhost:8305/scan && curl -s -X POST localhost:8305/file`.

---

## Putting It All Together

### Minimal Viable Discovery Stack

A working OAP system in five components:

```
+----------------+     +----------------+
|   Crawler      |---->|   ChromaDB     |
|   (Python      |     |   (manifest    |
|    script +    |     |    vectors +   |
|    seed crawl) |     |    experience) |
+----------------+     +-------+--------+
                               |
                        +------v--------+
                        |   Ollama      |
                        |   (qwen3:8b   |
                        |    + nomic    |
                        |    embed)     |
                        +------+--------+
                               |
                        +------v--------+     +-----------+
                        |   Discovery + |---->| SQLite    |
                        |   Tool Bridge |     | (FTS5 +   |
                        |   (FastAPI)   |     |  experience|
                        +------+--------+     |  + email  |
                               |              |  + remind)|
                        +------v--------+     +-----------+
                        |   Manifest    |
                        |   Agent       |
                        |   (FastAPI +  |
                        |    Vite SPA)  |
                        +---------------+
```

**Total dependencies:** Python, Ollama, ChromaDB (pip install). No Docker required. No Kubernetes. No cloud account.

**Total hardware:** Any machine with 16GB RAM and 10GB disk.

**Setup time:** Under an hour. Most of that is downloading the model.

### Example: Direct Discovery Query

```python
# Agent has a task — use the discovery API directly
task = "I need to transcribe a Portland city council meeting from last week"

# 1. Embed the task intent (intent extraction cleans the query first)
task_vector = ollama.embed("nomic-embed-text", task)

# 2. Search the manifest index (vector + optional FTS5)
results = chromadb.query(
    query_embeddings=[task_vector],
    n_results=5
)

# 3. Small LLM picks the best match
candidates = [load_manifest(r) for r in results]
prompt = f"""Given this task: {task}

Which of these capabilities best fits? Read each description carefully.

{format_candidates(candidates)}

Respond with the name of the best match and why."""

best_match = ollama.generate("qwen3:8b", prompt)

# 4. Frontier LLM executes the task using the manifest's invoke field
selected_manifest = get_manifest(best_match.name)
# Hand off to Claude/GPT/etc. with the manifest as context
```

### Example: Tool Bridge (End-to-End)

The more common path now is the tool bridge, which handles discovery and execution in a single request:

```bash
# The tool bridge discovers tools, injects them, executes tool calls,
# and loops until the LLM produces a final text response.
curl -X POST http://localhost:8300/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3:8b",
    "messages": [{"role": "user", "content": "what are the top news headlines today?"}],
    "oap_debug": true
  }'

# With debug, the response includes:
# - tools_discovered: which manifests were found
# - experience_cache: hit/miss status
# - fingerprint: the task's intent fingerprint
# - rounds: per-round tool calls with timing
# - escalated: whether big LLM was used
```

The agent (Manifest or any Ollama-compatible client) just sends chat messages. Discovery, tool injection, execution, credential injection, sandboxing, caching, and escalation all happen transparently inside the tool bridge.

### Production Stack

For a team or service handling concurrent discovery queries:

```
+----------------+     +----------------+
|   Crawler      |---->|   Qdrant       |
|   (scheduled,  |     |   (Docker)     |
|    distributed |     |                |
|    workers)    |     +-------+--------+
+----------------+             |
                        +------v--------+
                        |   Ollama      |
                        |   (qwen3:8b   |
                        |    or 3.5:9b  |
                        |    + GPU)     |
                        +------+--------+
                               |
                        +------v--------+     +-----------+
                        |   Discovery + |---->| Big LLM   |
                        |   Tool Bridge |     | (Claude,  |
                        |   (FastAPI +  |     |  GPT —    |
                        |    experience |     |  escalation|
                        |    cache)     |     |  only)    |
                        +---------------+     +-----------+
```

Add Redis for caching frequent queries. Add a queue (Celery, etc.) for crawl job distribution. Configure big LLM escalation for tasks that exceed the small model's capacity. Same architecture, just hardened for concurrent load.

---

## What This Architecture Enables

**Anyone can run the whole stack.** A small LLM, a vector database, a crawler, and a thin API layer. That's a weekend project. No cloud dependency. No API costs for discovery. The tool bridge means the small model handles end-to-end execution for most tasks — a frontier model is optional, not required.

**Discovery is private.** Your agent's queries never leave your machine during the discovery phase. Only the execution phase — invoking external APIs — requires a network call. What you're searching for stays local. The experience cache means repeated tasks don't even hit discovery.

**The system learns from use.** The experience cache turns every successful task into a cached shortcut. The first time you ask "what's the weather in Portland?" it runs full discovery. The second time, it replays the cached invocation in ~50ms. Negative caching prevents repeating known failures. Over time, the system converges on fast paths for its owner's common tasks.

**Multiple competing indexes can coexist.** Just like there are multiple web search engines, there can be multiple OAP crawlers and indexes. A general-purpose index. A healthcare-specific index. An enterprise-internal index. Competition at the discovery layer. Standardization at the manifest layer.

**The manifest quality drives discovery quality.** The `description` field is simultaneously what the small LLM reads for reasoning, and what gets embedded for vector similarity search. A well-written description clusters near relevant queries in vector space. A vague description gets lost. The quality of discovery is directly proportional to the quality of the manifest — same as the web.

**The small model does more than expected.** The tool bridge revealed that an 8B model with good tool-calling support handles the vast majority of real-world tasks end-to-end — news lookup, weather queries, email scanning, reminder management, file processing, text extraction. Big LLM escalation exists for the long tail (large outputs, complex reasoning), but most users find the small model sufficient for daily use.

---

## Not Prescribed, Illustrated

This document describes one way to build an OAP discovery stack. It is not part of the specification. The spec defines only the manifest format and publishing convention. How you discover, index, and reason about manifests is your business.

We publish this reference architecture to prove the ecosystem is buildable — by anyone, on commodity hardware, in a weekend. The stack described here is functional, affordable, and open. Improve on it.

---

*This document accompanies the [Open Application Protocol specification](SPEC.md), [trust overlay](TRUST.md), [manifesto](MANIFESTO.md), [A2A integration](A2A.md), [robotics](ROBOTICS.md), [OpenClaw integration](OPENCLAW.md), [Ollama tool bridge](OLLAMA.md), [Manifest agent](AGENT.md), [MCP server](MCP.md), [security model](SECURITY.md), and [procedural memory paper](OAP-PROCEDURAL-MEMORY-PAPER.md). OAP is released under CC0 1.0 Universal — no rights reserved.*
