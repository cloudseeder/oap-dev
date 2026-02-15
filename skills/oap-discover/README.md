# oap-discover — OpenClaw Skill

OAP discovery skill for [OpenClaw](https://openclaw.ai). Lets the agent find and invoke capabilities from the OAP manifest index at runtime.

## Install

Copy the skill to your OpenClaw workspace:

```bash
cp -r skills/oap-discover ~/.openclaw/workspace/skills/
```

Set the discovery API URL:

```bash
# In your shell profile or OpenClaw config
export OAP_DISCOVERY_URL=http://localhost:8300
```

The discovery API must be running locally (see [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for setup).

## How it works

1. User asks the agent to do something it doesn't have a built-in tool for
2. Agent queries `POST /v1/discover` with a natural language task description
3. Discovery API searches the local vector index and uses a small LLM to pick the best manifest
4. Agent reads the manifest's invoke spec and calls the endpoint directly
5. Discovery happens entirely on your machine — queries never leave localhost

## Requirements

- OAP discovery API running on the Mac Mini (or localhost)
- `OAP_DISCOVERY_URL` environment variable set
- `curl` available on PATH
