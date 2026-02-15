---
name: oap-discover
description: Discover external capabilities via the Open Application Protocol (OAP). When you need a tool or service that isn't available as a built-in tool — data processing, domain-specific APIs, file conversion, search, or any specialized capability — query the OAP discovery API to find a matching manifest and invoke it directly.
metadata: {"openclaw":{"emoji":"🔍","requires":{"env":["OAP_DISCOVERY_URL"],"anyBins":["curl"]}}}
---

# OAP Discovery Skill

You have access to a local OAP discovery service that indexes capability manifests from across the internet. Use it when the user asks you to do something and you don't have a built-in tool for it.

## When to use this skill

- The user asks for something that requires an external service (API, data source, processing pipeline)
- You need a capability that wasn't in your training data
- The user explicitly asks you to "find a service" or "discover a capability"
- You need domain-specific functionality (legal data, government records, media processing, etc.)

Do NOT use this skill when you already have a built-in tool that handles the task.

## Step 1: Query the discovery API

Send a POST request to the discovery API with a natural language description of what you need:

```bash
curl -s -X POST "${OAP_DISCOVERY_URL}/v1/discover" \
  -H "Content-Type: application/json" \
  -d '{"task": "<describe what you need in plain English>", "top_k": 5}'
```

The response looks like this:

```json
{
  "task": "summarize a long document",
  "match": {
    "domain": "summarize.example.com",
    "name": "Text Summarizer",
    "description": "Accepts plain text (max 10,000 words) and returns a concise summary.",
    "invoke": {
      "method": "POST",
      "url": "https://summarize.example.com/api/summarize",
      "auth": "api_key",
      "auth_in": "header",
      "auth_name": "X-API-Key"
    },
    "score": 0.231,
    "reason": "This capability directly handles text summarization with plain text input and structured JSON output."
  },
  "candidates": [ ... ]
}
```

- `match` is the best result (may be `null` if nothing fits)
- `candidates` is the full ranked list
- `score` is vector distance (lower = better match)
- `reason` is the small LLM's explanation for why this manifest was chosen

## Step 2: Evaluate the match

Before invoking, read the manifest description carefully. Check:

1. Does the description actually match what the user needs?
2. Does the input format match what you have?
3. Does the output format match what you need?
4. If `match` is null or the reason is weak, tell the user no matching capability was found.

If the `score` is above 1.0, the match is likely poor — tell the user what you found and ask if they want to proceed.

## Step 3: Invoke the capability

Use the `invoke` field from the match to call the capability:

**For HTTP endpoints (method is GET or POST):**

```bash
# POST with JSON body
curl -s -X POST "<invoke.url>" \
  -H "Content-Type: application/json" \
  -d '<input data>'

# POST with plain text
curl -s -X POST "<invoke.url>" \
  -H "Content-Type: text/plain" \
  -d '<input text>'

# GET request
curl -s "<invoke.url>?<query params>"
```

**Handling authentication:**

If `invoke.auth` is present, the capability requires authentication:

- `auth: "none"` — no authentication needed
- `auth: "api_key"` — send an API key
  - Check `auth_in` (default: `header`) and `auth_name` (default: `X-API-Key`)
  - Ask the user for the API key if you don't have it
  - Example: `-H "X-API-Key: <key>"`
- `auth: "bearer"` — send a bearer token
  - Example: `-H "Authorization: Bearer <token>"`
- `auth: "oauth2"` — OAuth2 flow required
  - Check `auth_url` for the token endpoint
  - Ask the user for credentials

If `invoke.headers` is present, include those headers in the request.

**For stdio commands (method is "stdio"):**

The `invoke.url` is a command path. Pipe input to it:

```bash
echo '<input>' | <invoke.url>
```

## Step 4: Present the result

Parse the response according to the manifest's output format and present it to the user. If the invocation fails, tell the user what went wrong and suggest alternatives from the `candidates` list.

## Other useful endpoints

```bash
# Check if the discovery service is running
curl -s "${OAP_DISCOVERY_URL}/health"

# List all indexed manifests
curl -s "${OAP_DISCOVERY_URL}/v1/manifests"

# Get a specific manifest by domain
curl -s "${OAP_DISCOVERY_URL}/v1/manifests/<domain>"
```

## Important

- Always tell the user what capability you found and why before invoking it
- Never send sensitive user data to an external service without asking first
- If a capability requires authentication, ask the user for credentials
- Prefer capabilities with lower scores (better semantic match)
- If multiple candidates look relevant, briefly describe the top 2-3 and let the user choose
