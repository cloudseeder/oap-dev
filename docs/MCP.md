# OAP MCP Server

OAP exposes manifest discovery to Claude Desktop, Claude Code, and any MCP client via a lightweight MCP server. Three tools — discover, call, exec — give the LLM access to 500+ manifests without flooding its context window.

## The problem

MCP servers typically register a fixed set of tools. With 500+ OAP manifests, registering each one as an MCP tool would overwhelm the LLM's context and degrade tool selection quality. The OAP MCP server solves this with a two-step pattern: discover first, then call.

## How it works

```
┌─────────────────────────────────────────────────────────────────┐
│  Claude Desktop / Claude Code / MCP Client                       │
│                                                                   │
│  1. oap_discover("extract emails from text")                     │
│     → Best match: oap_grep [STDIO], score: 0.42                 │
│                                                                   │
│  2. oap_call("oap_grep", {"args": "-E '[a-z]+@[a-z.]+'",...})   │
│     → result: "alice@example.com\nbob@test.org"                  │
│                                                                   │
│  Or skip discovery when you know the command:                     │
│                                                                   │
│  3. oap_exec("grep -E '[a-z]+@[a-z.]+' /tmp/contacts.txt")     │
│     → result: "alice@example.com\nbob@test.org"                  │
└─────────────────────────────────────────────────────────────────┘
          │              │              │
          ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│  OAP Discovery Service (:8300)                                   │
│                                                                   │
│  POST /v1/discover          — vector search + LLM ranking        │
│  POST /v1/tools/call/*      — execute any manifest               │
│  GET  /v1/manifests         — list all indexed manifests          │
└─────────────────────────────────────────────────────────────────┘
```

## Three tools

| Tool | Purpose | OAP endpoint |
|------|---------|-------------|
| `oap_discover(task, top_k)` | Natural language → best matching manifests | `POST /v1/discover` |
| `oap_call(tool_name, arguments)` | Execute any tool by name | `POST /v1/tools/call/{tool_name}` |
| `oap_exec(command, stdin)` | Direct CLI execution | `POST /v1/tools/call/oap_exec` |

**`oap_discover`** returns tool names, descriptions, invoke methods, and scores. The LLM reads this to decide which tool to call and how to construct arguments.

**`oap_call`** executes any discovered tool. Arguments depend on the tool type:
- Stdio tools: `{"stdin": "input text", "args": "-flags pattern"}`
- HTTP tools: `{"field": "value", ...}` matching the API schema

**`oap_exec`** is the fast path — when the LLM already knows the command, it skips discovery entirely. Supports pipes: `"grep -E pattern file | sort -u"`.

## Setup

### Install

```bash
pip install -e reference/oap_mcp
```

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "oap": {
      "command": "oap-mcp",
      "env": {
        "OAP_URL": "http://localhost:8300",
        "OAP_TOKEN": "your-token"
      }
    }
  }
}
```

### Claude Code

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "oap": {
      "command": "oap-mcp",
      "args": ["--url", "http://localhost:8300", "--token", "your-token"]
    }
  }
}
```

### CLI

```bash
oap-mcp --help
oap-mcp --url http://localhost:8300 --token your-token
```

## Configuration

| Setting | CLI flag | Env var | Default |
|---------|----------|---------|---------|
| OAP service URL | `--url` | `OAP_URL` | `http://localhost:8300` |
| Auth token | `--token` | `OAP_TOKEN` | (none) |
| HTTP timeout | `--timeout` | `OAP_TIMEOUT` | `120` seconds |

CLI flags override environment variables.

## Example session

A typical Claude Desktop interaction:

```
User: "What's the word count of /tmp/notes.txt?"

Claude calls: oap_exec("wc -w /tmp/notes.txt")
→ "42 /tmp/notes.txt"

Claude: "The file has 42 words."
```

A discovery-first interaction:

```
User: "I need to extract all dates from this text: Meeting on 2025-01-15,
       followup 2025-02-01, deadline 2025-03-30"

Claude calls: oap_discover("extract dates from text")
→ Best match: oap_grep [STDIO]
  Candidates: oap_grep, oap_date, oap_jq

Claude calls: oap_call("oap_grep", {
  "args": "-oE '[0-9]{4}-[0-9]{2}-[0-9]{2}'",
  "stdin": "Meeting on 2025-01-15, followup 2025-02-01, deadline 2025-03-30"
})
→ "2025-01-15\n2025-02-01\n2025-03-30"

Claude: "The dates are: 2025-01-15, 2025-02-01, and 2025-03-30."
```

## Auth

The MCP server sends the auth token only on protected OAP routes:

| Route | Auth required |
|-------|--------------|
| `POST /v1/discover` | Yes |
| `GET /v1/manifests` | Yes |
| `GET /health` | Yes |
| `POST /v1/tools/call/*` | No (local-only) |

Tool execution endpoints have no auth — they're secured at the infrastructure layer by Cloudflare Tunnel path filtering (the tunnel only exposes `/v1/discover`, `/v1/manifests`, `/health`).

## Comparison with other integrations

| | MCP Server | Tool Bridge | OpenAPI Tool Server |
|---|---|---|---|
| **Client** | Claude Desktop, Claude Code, any MCP client | Ollama CLI, Open WebUI | Open WebUI Tools, LangChain |
| **LLM** | External (Claude, etc.) | OAP manages Ollama | External (your choice) |
| **Protocol** | MCP (JSON-RPC over stdio) | Ollama API | OpenAPI 3.1 |
| **Discovery** | Explicit (`oap_discover`) | Automatic per request | Client reads spec once |
| **Tool selection** | LLM chooses from discover results | Small LLM picks from top candidates | Client's LLM picks from spec |
| **Best for** | Claude Desktop/Code users wanting OAP capabilities | Ollama CLI users, zero-config | Multi-model setups, framework integrations |

## Architecture

The MCP server is a thin client — no Ollama, no ChromaDB, no vector search. It connects to a running OAP discovery service via HTTP and translates between MCP's JSON-RPC protocol and OAP's REST API.

```
Claude Desktop ←→ oap-mcp (stdio) ←→ OAP Discovery (:8300) ←→ Ollama + ChromaDB
```

Dependencies: `mcp` (MCP SDK) and `httpx` (HTTP client). That's it.

---

*This document accompanies the [Open Application Protocol specification](SPEC.md), [reference architecture](ARCHITECTURE.md), [trust overlay](TRUST.md), [OAP + Ollama tool bridge](OLLAMA.md), [OpenAPI tool server](OPENAPI-TOOL-SERVER.md), and [manifesto](MANIFESTO.md). OAP is released under CC0 1.0 Universal — no rights reserved.*
