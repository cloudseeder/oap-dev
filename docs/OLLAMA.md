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
  http_timeout: 30      # Timeout (seconds) for HTTP tool execution
  stdio_timeout: 10     # Timeout (seconds) for stdio tool execution
```

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `true` | Master switch. Set to `false` to disable both endpoints. |
| `default_top_k` | `3` | How many manifests to discover when `top_k` isn't specified in the request. |
| `max_rounds` | `3` | Cap on tool-call rounds per chat request. The per-request `oap_max_rounds` is clamped to this value. |
| `http_timeout` | `30` | Seconds to wait for HTTP-based tool invocations. |
| `stdio_timeout` | `10` | Seconds to wait for stdio-based tool invocations. |

### Environment variable overrides

Every config field can be overridden with an environment variable following the pattern `OAP_TOOL_BRIDGE_<KEY>`:

| Variable | Example |
|----------|---------|
| `OAP_TOOL_BRIDGE_ENABLED` | `true` / `false` |
| `OAP_TOOL_BRIDGE_DEFAULT_TOP_K` | `5` |
| `OAP_TOOL_BRIDGE_MAX_ROUNDS` | `5` |
| `OAP_TOOL_BRIDGE_HTTP_TIMEOUT` | `60` |
| `OAP_TOOL_BRIDGE_STDIO_TIMEOUT` | `15` |

Environment variables take precedence over `config.yaml` values.

## What's next

The tool bridge is functional but minimal. Planned improvements:

- **Streaming support.** The `/v1/chat` proxy currently requires `stream: false`. Streaming proxying with interleaved tool execution is the next priority.
- **LLM-generated schemas at crawl time.** Instead of heuristic parameter extraction at request time, use the LLM during crawling to generate richer JSON Schema from manifest descriptions. Cache the schemas alongside the manifest embeddings.
- **Auth credential management.** Manifests declare auth requirements (`api_key`, `bearer`, `oauth2`) but the bridge doesn't yet manage credentials. A local credential store keyed by domain would let the bridge authenticate tool calls automatically.
- **Parallel tool execution.** When Ollama returns multiple tool calls in a single response, execute them concurrently instead of sequentially.
- **OpenAI-compatible endpoint.** An `/v1/chat/completions` endpoint that speaks the OpenAI API format, so any OpenAI-compatible client gets OAP tool discovery for free.

---

*This document accompanies the [Open Application Protocol specification](SPEC.md), [reference architecture](ARCHITECTURE.md), [trust overlay](TRUST.md), [manifesto](MANIFESTO.md), [A2A integration](A2A.md), [robotics](ROBOTICS.md), and [OpenClaw integration](OPENCLAW.md). OAP is released under CC0 1.0 Universal — no rights reserved.*
