# OAP as an OpenAPI Tool Server

OAP exposes all discovered manifests as a standard OpenAPI 3.1 specification. Any OpenAPI-aware client — Open WebUI, LangChain, custom agents — gets access to every indexed capability without knowing OAP exists. Point the client at `/v1/openapi.json`, and it sees a normal tool server with typed endpoints.

## Two paths to the same tools

OAP offers two ways to use discovered manifests. Choose based on who controls the LLM.

```
┌────────────────────────────────────────────────────────────────────┐
│                     Tool Bridge (/v1/chat)                         │
│                                                                    │
│  OAP is the LLM backend. It discovers tools, injects them into    │
│  Ollama, executes tool calls, and loops until done. The client     │
│  sends a chat message and gets a final answer.                     │
│                                                                    │
│  Best for: Ollama CLI, Open WebUI (chat mode), apps that want      │
│  zero tool management.                                             │
├────────────────────────────────────────────────────────────────────┤
│               OpenAPI Tool Server (/v1/openapi.json)               │
│                                                                    │
│  OAP provides tools only. An external model (GPT-4, Claude,       │
│  Gemini, or a different Ollama instance) discovers the spec,       │
│  decides which tools to call, and invokes them via standard        │
│  OpenAPI POST requests. OAP executes and returns the result.       │
│                                                                    │
│  Best for: Open WebUI (Tools feature), LangChain, custom agents,  │
│  any client that already manages its own LLM conversation.         │
└────────────────────────────────────────────────────────────────────┘
```

| | Tool Bridge | OpenAPI Tool Server |
|---|---|---|
| **LLM** | OAP manages Ollama | External (your choice) |
| **Discovery** | Automatic per request | Client reads the spec once |
| **Execution** | OAP loops internally | Client calls endpoints |
| **Protocol** | Ollama API | OpenAPI 3.1 |
| **Endpoint** | `POST /v1/chat` | `GET /v1/openapi.json` + `POST /v1/tools/call/*` |

## Endpoints

### `GET /v1/openapi.json` — the spec

Returns a dynamically generated OpenAPI 3.1.0 specification. Every indexed manifest becomes a POST endpoint under `/v1/tools/call/{tool_name}`, with a JSON Schema request body derived from the manifest's input spec.

```bash
curl http://localhost:8300/v1/openapi.json | jq .
```

**Response** (trimmed):

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "OAP Tool Server",
    "description": "OpenAPI tool server backed by OAP manifest discovery. Each endpoint corresponds to an OAP-discovered capability.",
    "version": "1.0.0"
  },
  "paths": {
    "/v1/tools/call/oap_exec": {
      "post": {
        "operationId": "oap_exec",
        "summary": "oap_exec",
        "description": "Execute a shell command directly...",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "command": { "type": "string", "description": "Full CLI command..." },
                  "stdin": { "type": "string", "description": "Text to pipe..." }
                },
                "required": ["command"]
              }
            }
          }
        }
      }
    },
    "/v1/tools/call/oap_grep": {
      "post": {
        "operationId": "oap_grep",
        "summary": "grep",
        "description": "Search for lines matching a regular expression pattern...",
        "requestBody": { "..." : "..." }
      }
    }
  }
}
```

Each path entry includes:
- `operationId` — the tool name (same `oap_` prefix convention as the tool bridge)
- `summary` — from the manifest's `name` field
- `description` — from the manifest's `description` field
- `requestBody` — JSON Schema with typed parameters

### `POST /v1/tools/call/{tool_name}` — execute a tool

Invoke a tool by name. The request body is a JSON object matching the tool's parameter schema.

**Named tool** (stdio manifest):

```bash
curl -X POST http://localhost:8300/v1/tools/call/oap_wc \
  -H "Content-Type: application/json" \
  -d '{"stdin": "one\ntwo\nthree", "args": "-l"}'
```

```json
{"result": "3"}
```

**oap_exec** (direct CLI command):

```bash
curl -X POST http://localhost:8300/v1/tools/call/oap_exec \
  -H "Content-Type: application/json" \
  -d '{"command": "date +%Y-%m-%d"}'
```

```json
{"result": "2026-02-25"}
```

**oap_exec with stdin**:

```bash
curl -X POST http://localhost:8300/v1/tools/call/oap_exec \
  -H "Content-Type: application/json" \
  -d '{"command": "grep -E \"[0-9]+\"", "stdin": "abc\n123\ndef\n456"}'
```

```json
{"result": "123\n456"}
```

**Error response**:

```json
{"error": "Error executing oap_grep: Command timed out after 10s"}
```

## Open WebUI setup

Open WebUI's [Tools feature](https://docs.openwebui.com/features/plugin/tools/) can import any OpenAPI-compatible server. This is separate from the Ollama integration described in the [OAP + Ollama doc](OLLAMA.md) — the Tools feature lets any model (including OpenAI, Claude, etc.) use OAP capabilities.

### Steps

1. Open **Settings** (gear icon, bottom-left)
2. Go to **Tools**
3. Click **Add Tool** → **Import from URL**
4. Enter your OAP server URL: `http://localhost:8300/v1/openapi.json`
5. Click **Save**

Open WebUI fetches the spec, registers all tools, and shows them in the tool list. When you chat with any model, you can enable OAP tools and the model will call them as needed.

### Docker note

If Open WebUI runs in Docker and OAP runs on the host, use `host.docker.internal` instead of `localhost`:

```
http://host.docker.internal:8300/v1/openapi.json
```

### What you see

After importing, each OAP manifest appears as a named tool in Open WebUI's tool panel. The tool descriptions come from the manifest's `description` field — the same text that helps small LLMs pick the right tool during discovery. When a model calls a tool, Open WebUI sends a POST to `/v1/tools/call/{tool_name}` and displays the result inline in the conversation.

## What gets exposed

Unlike the tool bridge (which suppresses stdio tools and forces everything through `oap_exec`), the OpenAPI tool server exposes **all** indexed manifests:

- **Stdio tools**: grep, wc, jq, date, bc, sed, awk, cut, tr, and all factory-generated manifests
- **HTTP tools**: any crawled manifest with a remote invoke URL
- **oap_exec**: always included as a built-in tool

The suppression logic in the tool bridge exists because small LLMs (qwen3:8b) prefer "named" tools over the generic `oap_exec`, even when `oap_exec` produces better results. The OpenAPI tool server doesn't have this problem — the consuming client's model handles tool selection, and larger models (GPT-4, Claude) are better at choosing the right tool from a larger set.

Parameter schemas follow the same heuristic conversion as the tool bridge:

| Manifest input | Generated schema |
|----------------|-----------------|
| `text/plain` | `{input: string}` |
| `application/json` with quoted field names | Extracted fields, each as `string` |
| `application/json` without parseable fields | `{data: string}` |
| `stdio` invoke method | `{stdin: string, args: string}` |
| No input spec | `{input: string}` |

## Security

The OpenAPI tool server endpoints are **local-only**:

- **No authentication** — no backend token required
- **Not exposed via Cloudflare Tunnel** — the tunnel only routes `/v1/discover`, `/v1/manifests`, and `/health`
- **Same execution security as the tool bridge** — PATH allowlist for stdio commands, SSRF protection for HTTP invocations, no `shell=True`, output size limits

If you need remote access, put these endpoints behind your own auth layer. The OAP server assumes they're only reachable from `localhost`.

---

*This document accompanies the [Open Application Protocol specification](SPEC.md), [reference architecture](ARCHITECTURE.md), [trust overlay](TRUST.md), [OAP + Ollama tool bridge](OLLAMA.md), and [manifesto](MANIFESTO.md). OAP is released under CC0 1.0 Universal — no rights reserved.*
