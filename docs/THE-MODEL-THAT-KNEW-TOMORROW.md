# The Model That Knew Tomorrow

*How a frozen 8B-parameter LLM answered questions about today's Portland news*

---

## The Impossible Answer

February 25, 2026. A terminal window on a Mac Mini.

```
$ ollama run qwen3:8b
>>> any portland oregon news?
```

The model thinks for a moment. Then:

```
Here are the latest Portland, Oregon stories:

**TriMet Board approves Southwest Corridor light rail alignment through Tigard**
The TriMet Board of Directors voted 6-1 to approve the locally preferred
alignment for the Southwest Corridor Light Rail Project, which will extend
MAX service from Portland through Tigard to Bridgeport Village. Board member
Kathy Wai dissented, citing concerns about construction impacts on small
businesses along Barbur Boulevard. The $3.2B project is scheduled to begin
construction in 2028.

**Portland City Council discusses street vendor permit reform**
Council members heard testimony from 23 speakers on proposed changes to
mobile food vendor permitting. The current system requires separate permits
from the Health Department, Bureau of Transportation, and Bureau of
Development Services. The proposed consolidation would create a single
application portal. Commissioner Rubio expressed support but requested
additional equity analysis before the vote.
```

This is real news. Current. Specific. Sourced from actual government meeting transcripts.

The model that produced it — qwen3:8b — stopped learning in 2023. It has 8 billion parameters. It runs on a $549 Mac Mini with 16GB of memory. It has never heard of this news. It has never seen the API that produced it. It doesn't know what year it is.

And yet it answered correctly.

This paper explains how.

---

## The Simplest Impossible Question

Before we get to Portland news, consider a simpler question — one that every human on earth can answer and no frozen language model can:

```
>>> what day is it?
```

A model trained in 2023 cannot know the current date. The answer isn't in the weights. It isn't in the training data. It is fundamentally unknowable to a frozen model.

Unless the model can *discover something that knows*.

Here's what happened inside the system when this question was asked:

```
[tool_api] POST /api/chat
[tool_api] Task: "what day is it?"
[tool_api] File path detected: no
[tool_api] Fingerprinting intent...
[tool_api] Fingerprint: query.time.current_date (15 tokens, 1.1s)
[tool_api] Experience cache: miss
[tool_api] Discovering tools...
[tool_api] Vector search → date (0.87), bc (0.31), wc (0.24)
[tool_api] LLM ranking → date (10/10)
[tool_api] Tools injected: [oap_exec, oap_date]
[tool_api] Round 1: model called oap_exec
[tool_api]   command: "date '+%A, %B %d, %Y'"
[tool_api]   result: "Tuesday, February 25, 2026"
[tool_api]   duration: 42ms
[tool_api] Round 2: model responding with text
[tool_api] Response: "Today is Tuesday, February 25, 2026."
[tool_api] Experience saved: query.time.current_date → builtin/exec
[tool_api] Total: 3.2s
```

Three seconds. The model didn't *know* the date — it *discovered a capability that knows the date*, asked it, and reported the answer.

This is the core idea: a manifest is a machine-readable description of what a capability does, what it accepts, what it produces, and how to invoke it. The model doesn't need to contain the world's knowledge. It needs to discover the right tool for each question.

The `date` command has been on every Unix system since 1971. What's new is that an LLM can find it at runtime, without anyone hardcoding the connection.

---

## The Manifest

An OAP manifest is a JSON file. It lives at a well-known URL (`/.well-known/oap.json`) or in a local directory. It has four required fields: version, name, description, and how to invoke it.

Here's the manifest for the `date` command:

```json
{
  "oap": "1.0",
  "name": "date",
  "description": "Display the current date and time, or format a specific
    date. Without arguments, prints the current date and time. Use +FORMAT
    to specify output format (e.g., +%Y-%m-%d for ISO date, +%s for Unix
    timestamp, +%H:%M for time).",
  "invoke": {
    "method": "stdio",
    "url": "date"
  }
}
```

And here's the manifest for a civic news API — the one that answered the Portland question:

```json
{
  "oap": "1.0",
  "name": "myNewscast",
  "description": "Civic transparency API. Query government meeting transcripts,
    public inspection reports, and local news stories from 17 agencies across
    the Portland metro area. Supports intents: events, stories, inspections,
    search, trending. Returns structured JSON with source attribution.",
  "invoke": {
    "method": "POST",
    "url": "https://mynewscast.org/api/v1/query"
  }
}
```

One is a local command-line tool. The other is an HTTP API on the internet. The model treats them identically: read the description, decide if it fits the task, invoke it through the declared method.

The `description` field is the most important line. It's what the LLM reads when deciding whether a capability matches a task. Write it like a man page — clear, specific, covering what the tool does and when to use it. The model's discovery quality is only as good as these descriptions.

---

## The Portland Moment

Now we can tell the full story. Here is the annotated server log from the "any portland oregon news?" query, showing every step the system took to produce an answer the model couldn't possibly know.

### Step 1: Request Arrives

```
[tool_api] POST /api/chat
[tool_api] model: qwen3:8b
[tool_api] message: "any portland oregon news?"
[tool_api] stream: true
```

The request came from the standard `ollama run` CLI. The user typed a question. The CLI sent it to what it thinks is an Ollama server — but the OAP tool bridge is intercepting `/api/chat` as a transparent proxy.

### Step 2: Intent Fingerprinting (~1s)

```
[tool_api] Fingerprinting intent...
[tool_api] Fingerprint: query.news.location_specific
[tool_api] 15 tokens, 1.1s
```

Before searching for tools, the system classifies the task into a short fingerprint — a dot-separated taxonomy like `query.news.location_specific` or `extract.json.field_list`. This fingerprint is the key for procedural memory: if we've seen this type of task before, we can skip discovery entirely.

The fingerprinting call uses `think=false` and `format="json"` to keep qwen3:8b constrained — 15 tokens in about a second.

### Step 3: Cache Hit — Wrong Answer

```
[tool_api] Experience cache: hit
[tool_api] Cached entry: query.news.location_specific → builtin/exec
[tool_api] Confidence: 0.90
[tool_api] Cached tool: oap_exec
```

The experience cache found a match. An earlier session had asked a news question and succeeded (or seemed to succeed) with `oap_exec` — the generic command-execution tool. The system trusts this entry: confidence 0.90 is above the 0.85 threshold.

This is about to go wrong.

### Step 4: oap_exec Tries curl

```
[tool_api] Tools injected: [oap_exec]  (from cache, skipped discovery)
[tool_api] Round 1: model called oap_exec
[tool_api]   command: "curl -s 'https://news.google.com/rss/search?q=portland+oregon'"
[tool_api]   result: "Error: command 'curl' not in allowed path"
[tool_api]   duration: 12ms
```

The model's instinct was reasonable — curl a news source. But `oap_exec` runs commands through a security allowlist, and `curl` isn't on it. (The allowlist covers standard Unix utilities: grep, jq, wc, date, sort, etc. Network tools are excluded by design.)

### Step 5: Model Gives Up

```
[tool_api] Round 2: model responding with text (no tool calls)
[tool_api] Response: "I'm unable to fetch live news..."
[tool_api] Early return: no tool calls in round
```

The model tried one thing, it failed, and it fell back to a text response admitting it can't help. In a normal chat system, this is where the story ends.

But the tool bridge has a self-correction mechanism.

### Step 6: Cache Degradation

```
[tool_api] Cache entry produced errors — degrading confidence
[tool_api] Confidence: 0.90 → 0.63 (× 0.7)
[tool_api] outcome_status: failure
[tool_api] Retrying with full discovery...
```

The cached `oap_exec` entry failed. The system multiplies its confidence by 0.7, dropping it from 0.90 to 0.63 — below the 0.85 threshold. This entry will never be served again for this fingerprint. The system then retries the entire question using full discovery instead of the cache.

This is the critical moment. The system started with the wrong answer and recognized it was wrong — in the same session.

### Step 7: Full Discovery (~10s)

```
[tool_api] Discovering tools (full pipeline)...
[tool_api] _extract_search_query: "any portland oregon news"
[tool_api] Vector search → mynewscast (0.82), apropos (0.34), grep (0.29)
[tool_api] FTS5 search → mynewscast (BM25: 12.4)
[tool_api] Combined candidates: 9 unique manifests
[tool_api] LLM ranking (qwen3:8b)...
[tool_api]   mynewscast.org: 10/10
[tool_api]   (8 others: 1-3/10)
[tool_api] Ranking complete: 10.2s
```

Now the system does what it should have done from the start: vector search over 500+ indexed manifests, FTS5 keyword search, merge the candidates, and have the LLM rank them by relevance.

The `mynewscast.org` manifest — "Civic transparency API. Query government meeting transcripts... 17 agencies across the Portland metro area" — is an almost perfect semantic match for "any portland oregon news?" Both the vector embedding and the BM25 keyword score put it at the top. The LLM confirms: 10 out of 10.

### Step 8: Tool Invocation

```
[tool_api] Tools injected: [oap_exec, oap_mynewscast, oap_apropos]
[tool_api] Round 1: model called oap_mynewscast
[tool_api]   arguments: {"intent": "stories", "geo": "portland"}
[tool_api]   HTTP POST https://mynewscast.org/api/v1/query
[tool_api]   Status: 200 OK
[tool_api]   Response: 4,847 bytes (2 stories, structured JSON)
[tool_api]   duration: 2.3s
```

The model chose the right tool and constructed reasonable arguments from the manifest's description. The HTTP POST returned structured JSON with two recent Portland news stories sourced from government meeting transcripts.

### Step 9: Response

```
[tool_api] Round 2: model responding with text
[tool_api] Response: "Here are the latest Portland, Oregon stories..."
[tool_api] Wrapping in Ollama NDJSON stream format
[tool_api] Experience saved: query.news.location_specific → mynewscast.org
[tool_api] Total: 51.4s
```

The model summarized the JSON into natural language and the tool bridge wrapped it in Ollama's streaming NDJSON format — the same format the `ollama run` CLI expects. The user saw the response appear in their terminal as if the model simply *knew* the answer.

A new experience record was saved: `query.news.location_specific → mynewscast.org`, confidence 0.90. The next time someone asks about local news, the system will skip discovery and go straight to mynewscast. That path takes about 7 seconds instead of 51.

---

## Self-Correction

The most interesting part of this log isn't the successful discovery — it's the failure that preceded it.

The system's procedural memory contained a bad entry: an earlier session where `oap_exec` was cached for news queries. Maybe it had worked once via a different path, or maybe it was cached from an ambiguous result. Either way, the system served a wrong answer with high confidence.

What happened next:

1. **The cached tool failed.** `curl` wasn't in the allowlist.
2. **The model gave up.** No tool calls, just a text apology.
3. **The system detected the failure.** Tool executions returned errors.
4. **Confidence was degraded.** 0.90 × 0.7 = 0.63, below the 0.85 threshold. This entry is effectively dead.
5. **Full discovery ran.** The system fell back to the complete pipeline — vector search, FTS5, LLM ranking.
6. **The correct tool was found.** `mynewscast.org` scored 10/10.
7. **The correct result was cached.** Next time, it's a 7-second cache hit.

This is procedural memory in action. Not retraining. Not fine-tuning. Not RLHF. A SQLite database with fingerprints, confidence scores, and a degradation multiplier. The system learned that Portland news comes from mynewscast.org — and it learned it in the same session where it got the answer wrong.

One failure was enough to kill the bad entry. One success was enough to create the good one. The system self-corrected in 51 seconds.

---

## The Stack

None of this requires exotic hardware or proprietary APIs.

| Component | What | Cost |
|-----------|------|------|
| **Hardware** | Mac Mini M4, 16GB unified memory | $549 |
| **Model** | qwen3:8b via Ollama — 8B params, ~5.9GB VRAM | Free, open weights |
| **Embeddings** | nomic-embed-text via Ollama | Free, open weights |
| **Vector DB** | ChromaDB (local directory) | Free, open source |
| **Keyword search** | SQLite FTS5 | Free, ships with Python |
| **Procedural memory** | SQLite (experience records) | Free, ships with Python |
| **Manifests** | 500+ local CLI tools + remote HTTP APIs | Free, crawled on startup |
| **Client** | `ollama run qwen3:8b` — standard, unmodified CLI | Free, open source |

The user doesn't need to know OAP exists. The tool bridge intercepts `/api/chat`, discovers capabilities, executes tool calls, and returns the result in the format the Ollama CLI expects. From the user's perspective, they're talking to a local model that happens to know what day it is and what's happening in Portland.

The entire system — model, embeddings, vector DB, keyword index, experience cache, tool bridge, and API server — runs on a single $549 computer with memory to spare.

---

## What This Means

### "Knowledge" vs. "Capability"

A frozen model has a fixed knowledge cutoff. Nothing that happened after training exists in the weights. But the model doesn't need to *contain* knowledge about Portland transit policy — it needs to *discover a capability* that has that knowledge. The manifest is the bridge.

This is the same principle behind the Unix philosophy: programs don't need to do everything, they need to compose with other programs that do. `grep` doesn't parse JSON. `jq` doesn't search text. But `curl | jq | grep` handles both. OAP manifests are the cognitive equivalent of pipes — they let an LLM compose capabilities it has never seen.

### "Frozen" vs. "Alive"

qwen3:8b will always have a 2023 knowledge cutoff. But its *effective capability set* changes every time a new manifest is published. When mynewscast.org added their OAP manifest, every model running with OAP discovery could suddenly answer Portland news questions — without any update, any download, any retraining.

The model is frozen. The ecosystem around it is alive.

### "Small" vs. "Capable"

8 billion parameters is small by 2026 standards. qwen3:8b can't write a novel or solve research-level math problems. But it can read a manifest description, decide if it matches a task, construct an invocation, and summarize the result. That's all it needs to do. The heavy lifting — fetching news, running regex, querying databases — is done by the capabilities the manifests point to.

A small model with good discovery can outperform a large model with no tools.

### "Local" vs. "Connected"

The model runs locally. The user's query never leaves the Mac Mini (unless a discovered tool is a remote API). Privacy is preserved by default — the system only reaches out when a manifest's invoke URL points to the internet, and only for the specific capability the model chose.

When the model answered "what day is it?" — entirely local. The `date` command ran on the same machine. When it answered about Portland news — one HTTP POST to mynewscast.org, carrying only the intent and location. The original question stayed local.

---

## The PhD and the Calculator

Two days after the Portland moment, we pushed harder. Not news lookups or date checks — graduate-level biology.

### Molecular Biology

```
>>> What is the role of the mediator complex in RNA polymerase II
    transcription initiation in eukaryotes?
```

The fingerprint came back: `query.biological.transcription_mechanism`. The system had never seen anything like it. Cache miss. Full discovery. Wikipedia won the ranking.

```
The mediator complex plays a crucial role in the transcription
initiation process by RNA polymerase II in eukaryotes. It
functions as a bridging factor between transcription factors and
the RNA polymerase II holoenzyme, facilitating the assembly of
the transcription initiation complex at gene promoters. The
mediator complex helps in the recruitment of RNA polymerase II
to the promoter region, enhances the efficiency of transcription
initiation, and modulates the activity of RNA polymerase II by
interacting with general transcription factors such as TFIID.
Additionally, it contributes to the regulation of gene
expression by integrating signals from various transcriptional
regulatory pathways.
```

Bridging factor. PIC assembly. Pol II recruitment. TFIID interaction. Signal integration. Every key point a graduate student would need to hit. The model didn't know any of this — it found Wikipedia, asked the right question, and summarized the answer.

### Biochemistry Reasoning

```
>>> If a protein has 3 disulfide bonds, how many cysteine residues
    must it contain at minimum?
```

Fingerprint: `compute.biochemistry.disulfide_bond`. This isn't a lookup — it requires reasoning. Each disulfide bond forms between two cysteine residues, so 3 × 2 = 6.

```
Each disulfide bond forms between two cysteine residues.
Therefore, a protein with 3 disulfide bonds must contain at
least 6 cysteine residues.
```

Correct. Clear. No hedging.

### The Plasmid Question — Where Honest Gets Interesting

```
>>> A circular plasmid is 4.7 kb. After digestion with EcoRI you get
    fragments of 1.2 kb, 0.8 kb, and 2.7 kb. How many EcoRI cut sites
    are there and do the fragments account for the full plasmid?
```

The log shows the experience cache at work:

```
[tool_api] Experience cache hit: compute.math.calculation → builtin/exec
[tool_api]   confidence: 0.90, used 37 times
```

Thirty-seven previous math queries had trained the cache. Fingerprint `compute.math.calculation` was a well-worn path to `oap_exec` with `bc`. No discovery needed — straight to the calculator.

Here's what the tool bridge returned:

```
The total length of the fragments is 1.2 + 0.8 + 2.7 = 4.5 kb,
which is less than the total plasmid length of 4.7 kb. This
suggests that there might be an error in the fragment
measurements or that some fragments are not fully accounted for.
If the fragments do account for the full plasmid, then there are
3 EcoRI cut sites, as each cut site creates a new fragment.
However, the discrepancy in length suggests a possible issue
with the measurements.
```

We thought this was brilliant. Three cut sites — correct. A 0.2 kb discrepancy — caught. The model didn't fall for the trap.

Except there was no trap. **1.2 + 0.8 + 2.7 = 4.7, not 4.5.** The tool bridge got the arithmetic wrong and "caught" a discrepancy that doesn't exist. And we bought it, because it sounded like careful reasoning.

We ran the same question through qwen3:8b directly with thinking enabled. It burned through hundreds of tokens reasoning from first principles — going in circles about whether circular DNA digestion gives n or n+1 fragments, second-guessing itself repeatedly. But it got the arithmetic right:

```
1.2 + 0.8 + 2.7 = 4.7 kb
```

This exactly matches the original plasmid size. Three EcoRI cut sites. The fragments account for the full plasmid.

The scorecard:

| | Tool bridge (OAP) | Thinking model (raw qwen3:8b) |
|---|---|---|
| **Cut sites** | 3 (correct) | 3 (correct) |
| **Arithmetic** | 4.5 (wrong) | 4.7 (correct) |
| **Conclusion** | "Discrepancy detected" (false) | "Fragments match" (correct) |
| **Tokens** | ~20 | ~2,000+ |
| **Time** | ~3 seconds | ~60+ seconds |

The thinking model was slow, verbose, and agonized over basic molecular biology — but it got the math right. The tool bridge was fast, confident, and wrong.

This is worth documenting because it reveals a real failure mode: **tool-assisted doesn't mean infallible.** When the tool produces a wrong result, the model has no way to check it. It trusts the calculator. And a confidently wrong answer that sounds like careful analysis is more dangerous than a slow correct one.

The tool bridge is better for most tasks — lookups, API calls, data retrieval, simple calculations. But when the calculation itself goes wrong, there's no safety net. The model doesn't verify tool output. It summarizes it.

### The Fix — Conditional Thinking

The failure above has a precise cause: `think: false` is hardcoded on all Ollama chat calls to keep latency low (~12 tokens per round). The model can't verify tool output because we told it not to think. But thinking is only needed for tasks where the model must sanity-check a result — arithmetic, not lookups.

The fix is conditional: the tool bridge now checks the fingerprint prefix against a configurable list (`tool_bridge.think_prefixes`). When a task fingerprints as `compute.*`, the Ollama payload sends `think: true`. Everything else stays `think: false`.

We reran the exact same plasmid question:

```
>>> A circular plasmid is 4.7 kb. After digestion with EcoRI you get
    fragments of 1.2 kb, 0.8 kb, and 2.7 kb. How many EcoRI cut sites
    are there and do the fragments account for the full plasmid?
```

The log still shows the cache hit:

```
[tool_api] Experience cache hit: compute.math.calculation → builtin/exec
[tool_api]   confidence: 0.90, used 39 times
```

But now `think: true` is in the Ollama payload. The model calls `oap_exec` as before, gets the tool result, then *thinks about it* before responding:

```
The fragments account for the full plasmid, and there are three
EcoRI cut sites.
```

Correct. 1.2 + 0.8 + 2.7 = 4.7. No phantom discrepancy.

The updated scorecard:

| | Tool bridge (no thinking) | Tool bridge (conditional thinking) | Raw thinking model |
|---|---|---|---|
| **Cut sites** | 3 (correct) | 3 (correct) | 3 (correct) |
| **Arithmetic** | 4.5 (wrong) | 4.7 (correct) | 4.7 (correct) |
| **Conclusion** | "Discrepancy" (false) | "Fragments match" (correct) | "Fragments match" (correct) |
| **Time** | ~3 seconds | ~5 seconds | ~60+ seconds |

The conditional thinking path adds ~2 seconds of overhead for the thinking pass — a 12× speedup over raw thinking, with the same correctness. Non-compute queries (lookups, API calls, text processing) still get the fast `think: false` path with no latency penalty.

The mechanism is simple: fingerprint prefixes gate thinking. The `compute` prefix catches arithmetic, unit conversion, and calculation tasks. The model gets a thinking budget exactly where it needs one — verifying numerical results — and stays fast everywhere else.

---

## What We're Not Claiming

This paper describes one model, one hardware target, one API, one session.

**The first instinct was wrong.** The system's cached answer was `oap_exec` with `curl`, which failed. Self-correction took 51 seconds. A direct cache hit takes 7 seconds. The first experience with any new task type will be slow.

**Discovery quality depends on descriptions.** If the mynewscast manifest had a vague description — "a news service" — it might not have ranked above other candidates. Manifest quality is the limiting factor for discovery accuracy.

**Credentials are separate.** The mynewscast API happened to not require authentication for basic queries. APIs that need auth require separate credential configuration. The manifest declares *what* auth is needed (`"auth": "bearer"`), but the key itself lives outside the manifest.

**LLM tool use is imperfect.** Small models sometimes construct wrong arguments, choose the wrong tool, or give up when they shouldn't. The system mitigates this with multi-tool injection (offering 3 candidates instead of 1), experience hints (past failures are injected into the system prompt), and exec fallback retry. But it's not 100%.

**This is not AGI.** It's plumbing. A JSON file, a vector database, a SQLite table, and a 51-second pipeline that lets a frozen model answer questions about today. Good plumbing.

---

## The One-Sentence Version

A manifest is a man page for the internet age — publish what you do, and any AI can find you at runtime.

---

## Try It

```bash
# Install Ollama and pull the model
ollama pull qwen3:8b

# Clone OAP and start the discovery server
git clone https://github.com/cloudseeder/oap-dev
cd oap-dev
pip install -e reference/oap_discovery
oap-api  # starts on :8300

# Point Ollama CLI at the OAP tool bridge
OLLAMA_HOST=http://localhost:8300 ollama run qwen3:8b

# Ask something impossible
>>> what day is it?
>>> any portland oregon news?
```

The model doesn't know the answer. It discovers the answer. Every time.
