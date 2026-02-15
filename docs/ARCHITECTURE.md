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
|             Discovery Layer (local)               |
|                                                   |
|  +--------------+    +-------------------------+  |
|  | Small LLM    |<-->| Vector DB               |  |
|  | (3B-8B)      |    | (embedded manifest      |  |
|  |              |    |  index)                 |  |
|  +--------------+    +-------------------------+  |
|                                                   |
|  "myNewscast Meeting Processor matches this       |
|   task with 0.94 similarity"                      |
+-------------------------+-------------------------+
                          |
                          v
+---------------------------------------------------+
|          Execution Layer (local or cloud)         |
|                                                   |
|  +--------------+    +-------------------------+  |
|  | Frontier LLM |--->| Invoke capability via   |  |
|  | (Claude,     |    | manifest's invoke field |  |
|  |  GPT, etc.)  |    |                         |  |
|  +--------------+    +-------------------------+  |
|                                                   |
|  Reads manifest, constructs request, reasons      |
|  about output, composes next step if needed       |
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

## Three Cognitive Jobs, Three Cost Points

The key insight: discovery and execution are different cognitive tasks requiring different levels of intelligence. Don't waste a frontier model on finding work. Don't trust a tiny model with doing the work.

**Similarity search** finds candidate manifests matching the 
agent's intent. This is pure vector math — no LLM involved. 
Embed the query, compare against the index, return the nearest 
neighbors. Sub-50ms. Near zero cost.

**Manifest reasoning** reads the top candidates and picks the 
best fit for the task. A small local LLM (3B-8B parameters) 
handles this — reading descriptions, evaluating fit, selecting 
the winner. Runs on CPU. Minimal cost.

**Task execution** invokes the selected capability, reasons 
about the output, and composes the next step if needed. This 
is the frontier model's job — Claude, GPT, Gemini. The only 
step that costs real money. The only step that should.

The expensive model never wastes tokens on discovery. The cheap model never attempts complex reasoning. Each model does what it's good at.

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
|  |               OpenClaw Gateway                      |  |
|  |  WhatsApp / Telegram / iMessage / Slack / etc.      |  |
|  |  Persistent memory - Cron jobs - Skills engine      |  |
|  |  ~200MB RAM                                         |  |
|  +---------------------------+-------------------------+  |
|                              |                            |
|  +---------------------------v-------------------------+  |
|  |              OAP Discovery Layer                    |  |
|  |                                                     |  |
|  |  +----------------+    +--------------------------+ |  |
|  |  | Ollama         |    | ChromaDB / LanceDB       | |  |
|  |  | Qwen 3 4B      |    | Manifest vector index    | |  |
|  |  | + nomic        |    | ~100MB for 10K           | |  |
|  |  |   embed-text   |    |   manifests              | |  |
|  |  | ~4GB RAM       |    | ~500MB RAM               | |  |
|  |  +----------------+    +--------------------------+ |  |
|  |                                                     |  |
|  |  +----------------+    +--------------------------+ |  |
|  |  | Crawler        |    | Discovery API            | |  |
|  |  | (background    |    | (FastAPI)                | |  |
|  |  |  process)      |    | ~100MB RAM               | |  |
|  |  | ~50MB RAM      |    |                          | |  |
|  |  +----------------+    +--------------------------+ |  |
|  +------------------------------------------------------+ |
|                                                           |
|  RAM budget: ~5GB active (11GB free for OS + headroom)    |
|  Storage: ~8GB (models + index + manifests)               |
|  Power: 7-15W under typical load                          |
|  Network: Outbound only (API calls + crawler fetches)     |
+-----------------------------------------------------------+
```

#### Bill of Materials

| Component | Cost |
|-----------|------|
| Mac Mini (M4, 16GB, 256GB) | $549 (one-time) |
| Ollama (LLM runtime) | Free |
| Qwen 3 4B + nomic-embed-text (discovery models) | Free |
| ChromaDB or LanceDB (vector database) | Free |
| Python + FastAPI (discovery API) | Free |
| OpenClaw (personal agent) | Free |
| Claude / GPT API (frontier model for task execution) | ~$5-20/month |
| Electricity (always-on operation) | ~$0.50/month |
| **Total first year** | **~$610-730** |

Compare to running an equivalent stack in the cloud: a GPU-capable VM for the local LLM ($400-500/month) plus the same frontier API costs. That's $5,000-6,000 per year. The Mac Mini pays for itself in under five weeks.

#### Setup

```bash
# 1. Install Homebrew (if not present)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Install Ollama (local LLM runtime)
brew install ollama
ollama serve &

# 3. Pull the two models the discovery stack needs:
#    - qwen3:4b — small LLM that reads manifests and picks the best match
#    - nomic-embed-text — embedding model that converts descriptions to vectors
ollama pull qwen3:4b              # ~2.5 GB, reasoning model
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

# 7. Add seed domains for the crawler
#    The crawler fetches https://<domain>/.well-known/oap.json for each
cd reference/oap_discovery
echo "example.com" >> seeds.txt          # add domains you want to index

# 8. Run the initial crawl
#    This fetches manifests, embeds descriptions via nomic-embed-text,
#    and stores the vectors in a local ChromaDB database (./oap_data/)
oap-crawl --once

# 9. Start the discovery API
#    Accepts natural-language queries, searches ChromaDB by vector similarity,
#    then uses qwen3:4b to pick the best manifest match
oap-api &                                # http://localhost:8300

# 10. Start the trust provider (optional)
cd ../oap_trust
oap-trust-api &                          # http://localhost:8301

# 11. Start the dashboard (optional)
cd ../oap_dashboard
oap-dashboard-crawl --once               # initial crawl into SQLite
oap-dashboard-api &                      # http://localhost:8302
```

You can verify the stack is running:

```bash
# Check discovery health (should show ollama: true, index_count > 0)
curl http://localhost:8300/health

# Try a discovery query
curl -X POST http://localhost:8300/v1/discover \
  -H "Content-Type: application/json" \
  -d '{"task": "summarize text"}'
```

#### Connecting an Agent: OpenClaw Example

The discovery stack is useful on its own, but the real payoff is when an agent uses it at runtime. [OpenClaw](https://openclaw.com) is an open-source personal agent that runs locally on the Mac Mini — the same machine running the discovery stack. With OAP discovery enabled, OpenClaw can find and invoke capabilities that weren't in its training data.

```bash
# 12. Install OpenClaw (see openclaw.com for current instructions)
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

The discovery LLM has one job: read a handful of manifest descriptions and decide which one best matches the agent's task. This requires instruction following, reading comprehension, and basic reasoning — not world knowledge, creative writing, or code generation.

### Recommended Models (as of February 2026)

**Qwen 3 4B** — 4 billion parameters, roughly 3GB VRAM quantized at Q4. The recommended default. Best balance of size and reasoning for the discovery task. Hybrid think/no-think modes let you use fast mode for manifest matching where deep chain-of-thought isn't needed. Apache 2.0 license.

**Phi-4-mini-instruct** — 3.8 billion parameters, roughly 3GB VRAM quantized. Strong instruction following and reasoning at minimal size, with a 128K context window that handles large manifests easily. MIT license.

**Llama 3.2 3B** — 3 billion parameters, roughly 2GB VRAM quantized. The smallest viable option. Runs on almost anything including underpowered hardware. Good enough for manifest matching even if it occasionally stumbles on edge cases. Meta license.

**SmolLM3 3B** — 3 billion parameters, roughly 2GB VRAM quantized. Fully open from Hugging Face with transparent training methodology. Outperforms Llama 3.2 3B on most benchmarks while maintaining the same footprint.

**Qwen 2.5 7B Instruct** — 7 billion parameters, roughly 5GB VRAM quantized. The best option if you have the VRAM. Best-in-class instruction following at this size with strong structured reasoning. Overkill for manifest matching, but handles every edge case gracefully.

### Model Selection Guidance

**Constrained hardware** — laptop or edge device with 16GB system RAM. Use Llama 3.2 3B or SmolLM3 3B. They run on CPU without consuming too much memory.

**Good hardware** — M-series Mac or a machine with a gaming GPU. Use Qwen 3 4B or Phi-4-mini. Best reasoning per parameter at a size that still leaves plenty of headroom.

**Server with GPU** — dedicated machine with 12+ GB VRAM. Use Qwen 2.5 7B Instruct. Fast with GPU acceleration and handles edge cases better than the smaller models.

### Runtime

**Ollama** is the recommended runtime for all models. Single command install, no Python environment, no CUDA configuration:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull your chosen model
ollama pull qwen3:4b           # Recommended default
ollama pull phi4-mini          # Alternative
ollama pull llama3.2:3b        # Minimal option
ollama pull qwen2.5:7b         # If you have the VRAM
```

Ollama exposes a local API at `http://localhost:11434` that your discovery service calls.

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

## Putting It All Together

### Minimal Viable Discovery Stack

A working OAP discovery system in four components:

```
+----------------+     +----------------+
|   Crawler      |---->|   ChromaDB     |
|   (Python      |     |   (embedded)   |
|    script)     |     |                |
+----------------+     +-------+--------+
                               |
                        +------v--------+
                        |   Ollama      |
                        |   (Qwen 3 4B  |
                        |    + nomic    |
                        |    embed)     |
                        +------+--------+
                               |
                        +------v--------+
                        |   Discovery   |
                        |   API         |
                        |   (FastAPI)   |
                        +---------------+
```

**Total dependencies:** Python, Ollama, ChromaDB (pip install). No Docker required. No Kubernetes. No cloud account.

**Total hardware:** Any machine with 16GB RAM and 10GB disk.

**Setup time:** Under an hour. Most of that is downloading the model.

### Example Discovery Query

```python
# Agent has a task
task = "I need to transcribe a Portland city council meeting from last week"

# 1. Embed the task intent
task_vector = ollama.embed("nomic-embed-text", task)

# 2. Search the manifest index
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

best_match = ollama.generate("qwen3:4b", prompt)

# 4. Frontier LLM executes the task using the manifest's invoke field
selected_manifest = get_manifest(best_match.name)
# Hand off to Claude/GPT/etc. with the manifest as context
```

### Production Discovery Stack

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
                        |   (Qwen 2.5   |
                        |    7B + GPU)  |
                        +------+--------+
                               |
                        +------v--------+
                        |   Discovery   |
                        |   Service     |
                        |   (FastAPI +  |
                        |    caching)   |
                        +---------------+
```

Add Redis for caching frequent queries. Add a queue (Celery, etc.) for crawl job distribution. Same architecture, just hardened for concurrent load.

---

## What This Architecture Enables

**Anyone can run the whole stack.** A small LLM, a vector database, a crawler, and a thin API layer. That's a weekend project. No cloud dependency. No API costs for discovery. The frontier model only gets called when there's actual work to do.

**Discovery is private.** Your agent's queries never leave your machine during the discovery phase. Only the execution phase — invoking the actual capability — requires a network call. What you're searching for stays local.

**Multiple competing indexes can coexist.** Just like there are multiple web search engines, there can be multiple OAP crawlers and indexes. A general-purpose index. A healthcare-specific index. An enterprise-internal index. Competition at the discovery layer. Standardization at the manifest layer.

**The manifest quality drives discovery quality.** The `description` field is simultaneously what the small LLM reads for reasoning, and what gets embedded for vector similarity search. A well-written description clusters near relevant queries in vector space. A vague description gets lost. The quality of discovery is directly proportional to the quality of the manifest — same as the web.

---

## Not Prescribed, Illustrated

This document describes one way to build an OAP discovery stack. It is not part of the specification. The spec defines only the manifest format and publishing convention. How you discover, index, and reason about manifests is your business.

We publish this reference architecture to prove the ecosystem is buildable — by anyone, on commodity hardware, in a weekend. The stack described here is functional, affordable, and open. Improve on it.

---

*This document accompanies the [Open Application Protocol specification](SPEC.md), [trust overlay](TRUST.md), [manifesto](MANIFESTO.md), and [OpenClaw integration](OPENCLAW.md). OAP is released under CC0 1.0 Universal — no rights reserved.*
