# OAP + Ollama: Manifest Discovery as Tool Calling

Ollama supports tool calling — the model requests a function, the host executes it, and the result goes back into the conversation. OAP discovers capabilities at runtime — a natural language query finds manifests that match the intent. The tool bridge connects these two ideas: any Ollama consumer gets dynamic tools from the open internet without hardcoding tool definitions.

No code changes. No tool registry. The model asks for what it needs, and OAP finds it.

## The problem

Every Ollama application that uses tool calling hardcodes its `tools` array. Adding a new capability means writing a new function definition, implementing the execution logic, and redeploying. The tools are static — frozen at build time.

OAP already solves runtime capability discovery for agents. The tool bridge makes that same discovery available as native Ollama tools. Instead of a static array, the tools come from manifests published across the open internet.

## How it works

| Ollama concept | OAP equivalent |
|----------------|----------------|
| Tool definition | Manifest |
| Function name | `oap_` + snake_case manifest name |
| Parameters (JSON Schema) | Heuristic schema from `input` spec |
| Tool execution | `invoke_manifest()` via manifest's `invoke` spec |
| `tools` array | Discovery results converted at request time |

The chat proxy flow:

```
┌──────────────┐    ┌─────────────────────────────────┐    ┌────────────┐
│              │    │  OAP Discovery Service           │    │            │
│  Ollama      │    │                                  │    │  Ollama    │
│  Consumer    │───►│  1. Extract task from user msg    │───►│  Server    │
│  (any app)   │    │  2. Discover manifests            │    │            │
│              │◄───│  3. Convert to tool definitions   │◄───│            │
│              │    │  4. Forward to Ollama with tools   │    │            │
│              │    │  5. Execute tool calls via invoke  │    │            │
│              │    │  6. Loop until done                │    │            │
└──────────────┘    └─────────────────────────────────┘    └────────────┘
```

The consumer sends a normal chat request. The discovery service intercepts it, finds relevant manifests, converts them to Ollama tool definitions, and injects them into the request. When Ollama calls a tool, the bridge executes it against the real manifest endpoint and feeds the result back. The consumer sees a normal chat response — it doesn't need to know OAP exists.

## The endpoints

The tool bridge adds two endpoints to the discovery service (`:8300` by default).

### `POST /v1/tools` — discover and convert

Takes a natural language task, discovers matching manifests, and returns Ollama-format tool definitions. Use this when you want to inject OAP tools into your own Ollama calls.

**Request:**

```bash
curl -X POST http://localhost:8300/v1/tools \
  -H "Content-Type: application/json" \
  -d '{"task": "set a reminder for Friday at 2pm", "top_k": 3}'
```

**Response:**

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "oap_fingerstring_reminders",
        "description": "Sets and manages reminders for a user. Accepts a natural language description of what to remember and when...",
        "parameters": {
          "type": "object",
          "properties": {
            "action": {"type": "string", "description": "The 'action' value"},
            "reminder": {"type": "string", "description": "The 'reminder' value"},
            "when": {"type": "string", "description": "The 'when' value"},
            "deliver_via": {"type": "string", "description": "The 'deliver_via' value"}
          },
          "required": ["action", "reminder", "when", "deliver_via"]
        }
      }
    }
  ],
  "registry": {
    "oap_fingerstring_reminders": {
      "tool": { "..." : "..." },
      "domain": "fingerstring.com",
      "manifest": { "..." : "..." }
    }
  }
}
```

The `registry` maps tool names back to their source domains and full manifests. The bridge uses this internally for execution; clients can use it for display or logging.

### `POST /v1/chat` — transparent proxy

Drop-in replacement for Ollama's `/api/chat`. Point your app here instead of directly at Ollama. The bridge discovers tools, injects them, executes tool calls, and returns the final response.

**Request:**

```json
{
  "model": "qwen3:4b",
  "messages": [
    {"role": "user", "content": "Set a reminder to submit the quarterly report on Friday at 2pm"}
  ],
  "stream": false,

  "oap_discover": true,
  "oap_top_k": 3,
  "oap_auto_execute": true,
  "oap_max_rounds": 3
}
```

| Extension field | Default | Description |
|----------------|---------|-------------|
| `oap_discover` | `true` | Enable OAP tool discovery for this request |
| `oap_top_k` | `3` | Number of manifests to discover (1–20) |
| `oap_auto_execute` | `true` | Automatically execute tool calls against manifest endpoints |
| `oap_max_rounds` | `3` | Maximum tool-call loops before returning (1–10) |

All extension fields are optional. Without them, the proxy still discovers and executes tools using defaults.

**Response** (standard Ollama format + metadata):

```json
{
  "model": "qwen3:4b",
  "message": {
    "role": "assistant",
    "content": "Done! I've set a reminder for you to submit the quarterly report on Friday at 2pm."
  },
  "oap_tools_injected": 1,
  "oap_round": 2
}
```

`oap_tools_injected` tells you how many OAP tools were discovered. `oap_round` tells you how many tool-call rounds it took. The rest of the response is standard Ollama.

## Manifest-to-tool conversion

The bridge converts each manifest's `input` spec into a JSON Schema `parameters` object using heuristics:

| Input spec | Generated parameters |
|-----------|---------------------|
| `text/plain` | `{input: string}` — the text content |
| `application/json` with quoted `'field'` names in description | Extracted fields, each as `string` |
| `application/json` without parseable fields | `{data: string}` — raw JSON as string |
| No `input` spec | `{input: string}` — generic input |
| `stdio` invoke method | `{args: string}` — command-line arguments |

### Tool naming

Tool names are prefixed with `oap_` and converted to snake_case:

- "Fingerstring Reminders" → `oap_fingerstring_reminders`
- "Summarize" → `oap_summarize`
- "myNewscast" → `oap_mynewscast`

### Concrete example: Fingerstring Reminders

The manifest's `input` description contains:

> JSON object with **'action'** (set, list, cancel, update), **'reminder'** (natural language description), **'when'** (natural language time like 'tomorrow at 9am'), and optional **'deliver_via'** (webhook, email, sms).

The converter extracts the single-quoted field names and generates:

```json
{
  "type": "object",
  "properties": {
    "action":     {"type": "string", "description": "The 'action' value"},
    "reminder":   {"type": "string", "description": "The 'reminder' value"},
    "when":       {"type": "string", "description": "The 'when' value"},
    "deliver_via": {"type": "string", "description": "The 'deliver_via' value"}
  },
  "required": ["action", "reminder", "when", "deliver_via"]
}
```

The model sees these as normal tool parameters. When it calls the tool, the bridge passes the arguments directly to the manifest's invoke URL as a JSON body.

## Integration patterns

### Direct tool injection

Use `/v1/tools` to get tool definitions, then inject them into your own `/api/chat` calls to Ollama. You control the conversation loop.

```bash
# 1. Discover tools
TOOLS=$(curl -s http://localhost:8300/v1/tools \
  -d '{"task": "set reminders"}' | jq '.tools')

# 2. Call Ollama directly with discovered tools
curl http://localhost:11434/api/chat -d "{
  \"model\": \"qwen3:4b\",
  \"messages\": [{\"role\": \"user\", \"content\": \"Remind me to call mom tomorrow\"}],
  \"tools\": $TOOLS,
  \"stream\": false
}"
```

Best for: apps that already manage their own Ollama conversations and want to augment with discovered tools.

### Transparent proxy

Point your app at `http://localhost:8300/v1/chat` instead of `http://localhost:11434/api/chat`. The bridge handles everything — discovery, injection, execution, looping.

```bash
curl http://localhost:8300/v1/chat -d '{
  "model": "qwen3:4b",
  "messages": [{"role": "user", "content": "Remind me to call mom tomorrow"}],
  "stream": false
}'
```

Best for: new apps or quick integration. Zero code changes beyond changing the URL.

### Hybrid — your tools + discovered tools

Provide your own tools in the request. The bridge discovers additional tools and merges them. Your tools take precedence (they're appended after OAP tools, so the model sees both).

```json
{
  "model": "qwen3:4b",
  "messages": [{"role": "user", "content": "Check the weather and set a reminder if it'll rain"}],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string", "description": "City name"}
          },
          "required": ["location"]
        }
      }
    }
  ],
  "oap_discover": true
}
```

The model sees `get_weather` (yours) and `oap_fingerstring_reminders` (discovered). It can use both in the same conversation.

## Configuration

The tool bridge is configured in `config.yaml` under the `tool_bridge:` section:

```yaml
tool_bridge:
  enabled: true         # Enable /v1/tools and /v1/chat endpoints
  default_top_k: 3      # Default number of manifests to discover per request
  max_rounds: 3         # Maximum tool-call loop iterations
  ollama_timeout: 120   # Timeout (seconds) for Ollama /api/chat calls (model inference)
  http_timeout: 30      # Timeout (seconds) for HTTP tool execution
  stdio_timeout: 10     # Timeout (seconds) for stdio tool execution
```

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `true` | Master switch. Set to `false` to disable both endpoints. |
| `default_top_k` | `3` | How many manifests to discover when `top_k` isn't specified in the request. |
| `max_rounds` | `3` | Cap on tool-call rounds per chat request. The per-request `oap_max_rounds` is clamped to this value. |
| `ollama_timeout` | `120` | Seconds to wait for Ollama `/api/chat` inference calls. Set high — small models with tool definitions can take 30-60s per round. |
| `http_timeout` | `30` | Seconds to wait for HTTP-based tool invocations against manifest endpoints. |
| `stdio_timeout` | `10` | Seconds to wait for stdio-based tool invocations. |

### Environment variable overrides

Every config field can be overridden with an environment variable following the pattern `OAP_TOOL_BRIDGE_<KEY>`:

| Variable | Example |
|----------|---------|
| `OAP_TOOL_BRIDGE_ENABLED` | `true` / `false` |
| `OAP_TOOL_BRIDGE_DEFAULT_TOP_K` | `5` |
| `OAP_TOOL_BRIDGE_MAX_ROUNDS` | `5` |
| `OAP_TOOL_BRIDGE_OLLAMA_TIMEOUT` | `180` |
| `OAP_TOOL_BRIDGE_HTTP_TIMEOUT` | `60` |
| `OAP_TOOL_BRIDGE_STDIO_TIMEOUT` | `15` |

Environment variables take precedence over `config.yaml` values.

## Drop-in Ollama replacement

The OAP server implements the full Ollama API surface. Point any standard Ollama client at `localhost:8300` instead of `localhost:11434` and every chat request gets automatic tool discovery + execution — no code changes, no configuration beyond the URL.

### How it works

| Endpoint | Behavior |
|----------|----------|
| `POST /api/chat` | Routes through the tool bridge — discovers tools, injects them, executes tool calls, loops until done. Same as `/v1/chat`. |
| `GET /api/tags` | Pass-through to Ollama — lists available models |
| `POST /api/show` | Pass-through to Ollama — model info |
| `GET /api/ps` | Pass-through to Ollama — loaded models |
| `POST /api/generate` | Pass-through to Ollama — text generation |
| `POST /api/embed` | Pass-through to Ollama — embeddings |
| `POST /api/embeddings` | Pass-through to Ollama — embeddings (alias) |

`/api/chat` is the only endpoint with OAP behavior. Everything else proxies directly to the real Ollama server — the OAP server is transparent for non-chat operations.

### Streaming

Standard Ollama clients send `stream: true` by default (including `ollama run`). The tool bridge processes everything non-streaming internally — tool execution loops require complete responses to decide the next action. When the request has `stream: true`, the bridge runs its full tool loop, then emits the final result as NDJSON: a content chunk (`done: false`) followed by a done sentinel (`done: true`) with timing metrics. Clients see the complete response arrive at once rather than token-by-token, which is fine since tool execution (not generation) is the bottleneck.

### Ollama CLI

The `ollama` CLI uses the `OLLAMA_HOST` environment variable to connect to a custom server. Use **interactive mode** — one-shot mode uses `/api/generate` (pass-through, no tools) instead of `/api/chat` (tool bridge).

```bash
# Interactive mode — uses /api/chat, gets tool discovery
OLLAMA_HOST=http://localhost:8300 ollama run qwen3:8b
>>> what day is it?
It is Wednesday, February 25, 2026.

# List models (proxied to real Ollama)
OLLAMA_HOST=http://localhost:8300 ollama list

# Shell alias for convenience
alias oap='OLLAMA_HOST=http://localhost:8300 ollama'
oap run qwen3:8b
```

> **Note:** One-shot mode (`ollama run qwen3:8b "prompt"`) sends the request via `/api/generate`, which passes through to Ollama without tool discovery. Use interactive mode for tool-augmented chat.
>
> **macOS:** Ensure the Ollama desktop app is not also listening on port 8300. Check with `lsof -i :8300` — only the OAP Python process should be listed.

### Open WebUI

[Open WebUI](https://github.com/open-webui/open-webui) connects to Ollama via the `OLLAMA_BASE_URL` environment variable. Point it at the OAP server:

```bash
# Docker
docker run -d -p 3000:8080 \
  -e OLLAMA_BASE_URL=http://host.docker.internal:8300 \
  -v open-webui:/app/backend/data \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main

# Docker Compose
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    ports: ["3000:8080"]
    environment:
      OLLAMA_BASE_URL: http://host.docker.internal:8300
    volumes:
      - open-webui:/app/backend/data
```

Open WebUI will list models from `/api/tags`, show loaded models from `/api/ps`, and route all chat through `/api/chat` — which means every conversation gets OAP tool discovery automatically. The UI works normally; tool execution happens server-side and the user sees the final answer.

> **Tip:** If Open WebUI is running on the same machine (not in Docker), use `http://localhost:8300` directly.

### Other compatible clients

Any application that speaks the Ollama API can use the OAP server. Common patterns:

| Client | Configuration |
|--------|--------------|
| `ollama` CLI (interactive) | `OLLAMA_HOST=http://localhost:8300 ollama run qwen3:8b` |
| Open WebUI | `OLLAMA_BASE_URL=http://localhost:8300` |
| chatbot-ui | `OLLAMA_API_BASE_URL=http://localhost:8300` |
| Flowise | Ollama node → Base URL: `http://localhost:8300` |
| n8n | Ollama credentials → Base URL: `http://localhost:8300` |
| LangChain | `ChatOllama(base_url="http://localhost:8300")` |
| LlamaIndex | `Ollama(base_url="http://localhost:8300")` |
| promptfoo | `providers: [{id: "ollama:qwen3:8b", config: {apiBaseUrl: "http://localhost:8300"}}]` |
| curl | `curl http://localhost:8300/api/chat -d '{"model":"qwen3:8b","messages":[...]}'` |

### Demo

Run the demo script to verify all endpoints work:

```bash
./scripts/demo-ollama-compat.sh              # default: localhost:8300
./scripts/demo-ollama-compat.sh http://my-server:8300  # custom URL
```

The script tests `/api/tags`, `/api/ps`, `/api/show`, `/api/chat` (both streaming and non-streaming), and `/api/generate`.

## Experience cache

The tool bridge includes a procedural memory system — a dual-store experience cache that remembers past tool invocations and replays them for similar future requests, skipping the full discovery + LLM ranking pipeline.

**Architecture:** SQLite (`oap_experience.db`) is the system of record for invocation history. ChromaDB (`experience_vectors/`) stores task embeddings for similarity lookup. Both stores are kept in sync.

**Lookup flow:** Embed the incoming task with `nomic-embed-text` (~50ms) → ChromaDB cosine search → cache hit if distance < `vector_similarity_threshold` (default 0.25) and confidence >= 0.85. Fallback: exact fingerprint match in SQLite. On miss: full discovery → execute → cache the result for next time.

**Why vectors instead of string matching:** LLM-generated fingerprints are non-deterministic — the same intent produces slightly different fingerprints across runs. Vector similarity on the original task text is stable and catches paraphrases ("what's the weather" vs "check the forecast").

**Degradation:** Errors multiply confidence by 0.7, so a single failure drops the entry below the 0.85 threshold. Negative caching stores failures with `CorrectionEntry` records that provide self-correction hints on retry.

**Backfill migration:** On startup, if the vector collection is empty but SQLite has records, all task texts are embedded and upserted automatically.

Config: `experience.enabled` (default `true`), `experience.vector_similarity_threshold` (cosine distance, default 0.25).

## Credential injection

The bridge authenticates tool calls automatically via a local credential store. Manifests don't need to know about credentials — they declare auth requirements, and the bridge injects the right key at execution time.

**Format:** `credentials.yaml`, keyed by domain:

```yaml
www.alphavantage.co:
  api_key: "your-key-here"
  auth_in: "query"       # "header" (default), "query", or "bearer"
  auth_name: "apikey"    # query param or header name
```

**Placement modes** (via manifest `invoke.auth_in`):
- `auth_in: "header"` (default) — key added as HTTP header (name from `auth_name`, default `X-API-Key`)
- `auth_in: "query"` — key added as query parameter, merged into request params
- `auth: "bearer"` — key added as `Authorization: Bearer <key>` header

**Domain lookup:** First tries the indexed domain (e.g. `local/alpha-vantage`), then falls back to the invoke URL hostname (e.g. `www.alphavantage.co`). This lets `credentials.yaml` use real domain names for local manifests.

Credential injection is transparent to the LLM — the system prompt tells it "API credentials are pre-configured" so it always calls the tool without hesitation.

Config: `tool_bridge.credentials_file` (default `credentials.yaml`, relative to CWD).

## Multi-tool injection

The bridge injects up to 3 tools per chat round — the LLM's top discovery pick plus the next highest-scoring candidates (deduped by domain). This lets the model choose between related capabilities in a single round rather than requiring multiple discovery cycles.

For example, a task like "check the news and weather" might inject `oap_newsapi_top_headlines`, `oap_open_meteo`, and `oap_wikipedia` in a single round, letting the model call whichever ones it needs.

Config: `MAX_INJECTED_TOOLS = 3` (constant in `tool_api.py`).

## Fingerprint optimization

Intent fingerprinting uses `chat(think=False, temperature=0, format="json")` for deterministic ~15-token output in ~1s. JSON-aware fingerprints separate JSON tasks from text tasks in fingerprint space.

Fingerprints are no longer the primary cache key (vector similarity replaced them), but they're still used for:
- Logging and debug traces
- Failure tracking and blacklisting
- Experience hints (past failure/success context injected into system prompt)
- Conditional thinking and escalation prefix matching

## Conditional thinking

By default, the bridge sends `think: false` to Ollama to keep responses fast (~12 tokens per round with qwen3:8b). For tasks that benefit from reasoning — like arithmetic verification — you can enable thinking selectively.

Config: `tool_bridge.think_prefixes` (list of fingerprint prefixes, default empty). When a task's fingerprint starts with a listed prefix, `think: true` is sent to Ollama. Debug output includes `thinking_enabled: true/false`.

```yaml
tool_bridge:
  think_prefixes:
    - compute
    - calculate
```

## Big LLM escalation

The small local model (qwen3:8b) handles tool discovery and execution. For tasks that need deeper reasoning — complex analysis, large document processing, arithmetic verification — the final reasoning step can be escalated to a big cloud LLM (GPT-4, Claude, Gemini).

**How it works:** The small model discovers tools and executes them as usual. When escalation triggers, the tool results and conversation context are sent to the big LLM for the final response instead of back to the small model.

**Two escalation triggers:**
1. **Prefix matching:** `tool_bridge.escalate_prefixes` (list of fingerprint prefixes). When a task's fingerprint starts with a listed prefix, escalation activates.
2. **Large output:** When an `oap_exec` result exceeds `summarize_threshold` chars and escalation is enabled, it escalates automatically — catching any large-output scenario regardless of fingerprint prefix.

**Providers:** OpenAI, Anthropic, and Google AI (via OpenAI-compatible endpoint). Per-provider env vars (`OAP_OPENAI_API_KEY`, `OAP_ANTHROPIC_API_KEY`, `OAP_GOOGLEAI_API_KEY`) let you switch providers without redeploying.

Config:
```yaml
escalation:
  enabled: true
  provider: anthropic    # openai, anthropic, or googleai
  model: claude-sonnet-4-20250514
  timeout: 120

tool_bridge:
  escalate_prefixes:
    - compute
    - analyze
```

Fails silently — falls back to small LLM response on any error. Debug output includes `escalated: true/false`.

## Map-reduce summarization

When tool results exceed the small LLM's context window and big LLM escalation is not configured, the bridge falls back to map-reduce summarization via `ollama.generate()`. The result is chunked, each chunk summarized independently, then the summaries are combined. This is lossy — especially on prose and markdown — but preserves the key information.

Hierarchy: big LLM escalation (if `escalation.enabled`) → map-reduce → truncation.

Config: `tool_bridge.summarize_threshold` (default 16000 chars), `tool_bridge.chunk_size`, `tool_bridge.max_tool_result`.

## What's next

Planned improvements:

- **LLM-generated schemas at crawl time.** Instead of heuristic parameter extraction at request time, use the LLM during crawling to generate richer JSON Schema from manifest descriptions. Cache the schemas alongside the manifest embeddings.
- **Parallel tool execution.** When Ollama returns multiple tool calls in a single response, execute them concurrently instead of sequentially.
- **OpenAI-compatible endpoint.** An `/v1/chat/completions` endpoint that speaks the OpenAI API format, so any OpenAI-compatible client gets OAP tool discovery for free.

---

*This document accompanies the [Open Application Protocol specification](SPEC.md), [reference architecture](ARCHITECTURE.md), [trust overlay](TRUST.md), [manifesto](MANIFESTO.md), [A2A integration](A2A.md), [robotics](ROBOTICS.md), and [OpenClaw integration](OPENCLAW.md). OAP is released under CC0 1.0 Universal — no rights reserved.*
