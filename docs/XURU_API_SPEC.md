# Xuru Email API Spec — OAP Agent Interface

Lightweight API for OAP agents and LLMs to access email through Xuru's existing security boundary. Xuru handles all IMAP/SMTP, MIME parsing, prompt injection filtering, and HTML sanitization. The API only exposes clean, pre-processed text.

## Design Principles

1. **Xuru is the trust boundary.** Raw email never reaches the agent. All content is sanitized and filtered before API response.
2. **Multi-tenant.** Each tenant (netgate.xuru.ai, etc.) has its own API namespace and credentials.
3. **Read-heavy.** Agents mostly summarize and triage. Send/reply are lower frequency.
4. **Minimal surface.** Only expose what agents need. No folder management, no raw MIME, no attachment downloads.

## Authentication

```
Authorization: Bearer <tenant-api-key>
```

- One API key per tenant, generated in Xuru admin
- Keys are scoped to a single tenant's mailboxes
- Rate limited: 60 requests/minute per key
- HTTPS required (no plaintext)

## Endpoints

### `GET /api/v1/messages`

List recent messages, pre-processed and safe for LLM consumption.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `since` | ISO 8601 | 24h ago | Messages received after this timestamp |
| `limit` | int | 20 | Max messages (1-100) |
| `folder` | string | `inbox` | Folder: `inbox`, `sent`, `flagged` |
| `unread` | bool | `false` | Only unread messages |
| `query` | string | — | Search subject/sender/body text |

**Response:**

```json
{
  "messages": [
    {
      "id": "msg_abc123",
      "thread_id": "thr_def456",
      "from": {"name": "Jane Smith", "email": "jane@example.com"},
      "to": [{"name": "Brooks", "email": "brooks@netgate.com"}],
      "cc": [],
      "subject": "Q1 Budget Review",
      "snippet": "First 200 chars of plain text body...",
      "body_text": "Full plain text body, sanitized. HTML stripped. Prompt injection patterns removed.",
      "received_at": "2026-03-10T08:30:00Z",
      "is_read": false,
      "is_flagged": false,
      "has_attachments": true,
      "attachments": [
        {"filename": "budget.xlsx", "size_bytes": 45200, "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
      ],
      "thread_length": 3,
      "labels": ["work"],
      "xuru_classification": "actionable"
    }
  ],
  "total": 42,
  "has_more": true
}
```

**Notes:**
- `body_text` is always plain text, never HTML. Xuru converts and sanitizes.
- `snippet` is the first 200 chars for quick scanning without reading full body.
- `xuru_classification` is Xuru's existing AI classification (e.g., `actionable`, `informational`, `spam`, `newsletter`).
- Attachment metadata only — no content download endpoint. Agents can reference attachments by name.
- Thread messages are flattened. Use `thread_id` to group.

### `GET /api/v1/messages/{id}`

Fetch a single message by ID.

**Response:** Same message object as above.

### `GET /api/v1/threads/{thread_id}`

Fetch all messages in a thread, ordered chronologically.

**Response:**

```json
{
  "thread_id": "thr_def456",
  "subject": "Q1 Budget Review",
  "participants": [
    {"name": "Jane Smith", "email": "jane@example.com"},
    {"name": "Brooks", "email": "brooks@netgate.com"}
  ],
  "messages": [ /* ordered array of message objects */ ],
  "message_count": 3
}
```

### `POST /api/v1/messages/send`

Compose and send a new email.

**Request:**

```json
{
  "to": ["jane@example.com"],
  "cc": [],
  "subject": "Re: Q1 Budget Review",
  "body": "Plain text message body.",
  "reply_to": "msg_abc123"
}
```

**Notes:**
- `reply_to` is optional. When set, Xuru handles threading headers (`In-Reply-To`, `References`), quoting, and `Re:` prefix.
- `body` is plain text only. Xuru may wrap in a minimal HTML template for delivery if the tenant is configured for it.
- Xuru applies outbound filtering (no credential leaks, no forwarding of sanitized-out content).

**Response:**

```json
{
  "id": "msg_xyz789",
  "status": "sent",
  "sent_at": "2026-03-10T10:30:00Z"
}
```

### `POST /api/v1/messages/{id}/flag`

Flag or unflag a message.

```json
{"flagged": true}
```

### `POST /api/v1/messages/{id}/read`

Mark a message as read or unread.

```json
{"read": true}
```

### `GET /api/v1/summary`

Daily digest — Xuru-generated summary of recent email activity. Designed for morning briefings.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `since` | ISO 8601 | 24h ago | Summarize activity since this time |

**Response:**

```json
{
  "period": {"from": "2026-03-09T10:00:00Z", "to": "2026-03-10T10:00:00Z"},
  "total_received": 15,
  "unread_count": 7,
  "breakdown": {
    "actionable": 3,
    "informational": 8,
    "newsletter": 4
  },
  "highlights": [
    {
      "message_id": "msg_abc123",
      "subject": "Q1 Budget Review",
      "from": "Jane Smith",
      "reason": "Flagged as actionable, awaiting reply"
    }
  ],
  "threads_awaiting_reply": [
    {
      "thread_id": "thr_def456",
      "subject": "Q1 Budget Review",
      "last_from": "Jane Smith",
      "waiting_since": "2026-03-09T08:30:00Z"
    }
  ]
}
```

**Notes:**
- `highlights` is Xuru's pick of what matters most — already filtered and prioritized.
- `threads_awaiting_reply` tracks threads where the last message is from someone else.
- This endpoint is ideal for the OAP agent's daily email briefing task.

### `GET /api/v1/health`

```json
{"status": "ok", "tenant": "netgate", "mailboxes": 2}
```

## Security Model

### What Xuru filters before API response:

1. **Prompt injection** — Xuru's existing detection strips/flags injection attempts in email bodies
2. **HTML → plain text** — No raw HTML reaches the agent
3. **Encoded content** — Base64, quoted-printable decoded before exposure
4. **Attachment content** — Only metadata exposed, never raw bytes
5. **Internal headers** — No raw SMTP headers, no authentication tokens, no server IPs

### What the API does NOT expose:

- Raw MIME
- Email headers (beyond from/to/cc/subject/date)
- Attachment content/downloads
- Account credentials or OAuth tokens
- Folder management or deletion
- Mail rules or filter configuration

### Outbound safety (send/reply):

- Rate limited per tenant (configurable, e.g., 10 sends/hour)
- Xuru scans outbound body for accidental credential/secret leaks
- No forwarding of content that was stripped during inbound sanitization
- Audit log of all API-initiated sends

## OAP Manifest

Once the API is live, the OAP manifest would look like:

```json
{
  "oap": "1.0",
  "name": "xuru-email",
  "description": "Read, search, and send email via Xuru. Use for 'check my email', 'any messages from Jane?', 'reply to the budget thread', 'email summary since yesterday'. Returns sanitized plain text — no HTML, no raw MIME.",
  "input": {
    "format": "application/json",
    "description": "JSON with 'action' and parameters.",
    "parameters": {
      "action": {"type": "string", "description": "Operation: 'list', 'get', 'thread', 'send', 'reply', 'summary', 'flag', 'read'", "required": true},
      "id": {"type": "string", "description": "Message ID (for get, reply, flag, read)"},
      "thread_id": {"type": "string", "description": "Thread ID (for thread action)"},
      "since": {"type": "string", "description": "ISO 8601 timestamp filter"},
      "limit": {"type": "integer", "description": "Max results (1-100)"},
      "unread": {"type": "boolean", "description": "Filter to unread only"},
      "query": {"type": "string", "description": "Search text"},
      "to": {"type": "array", "description": "Recipient emails (for send)"},
      "subject": {"type": "string", "description": "Email subject (for send)"},
      "body": {"type": "string", "description": "Plain text body (for send/reply)"},
      "flagged": {"type": "boolean", "description": "Flag state (for flag action)"},
      "read": {"type": "boolean", "description": "Read state (for read action)"}
    }
  },
  "output": {
    "format": "application/json",
    "description": "Message objects with sanitized plain text bodies, thread info, and Xuru classifications."
  },
  "invoke": {
    "method": "POST",
    "url": "https://netgate.xuru.ai/api/v1/dispatch",
    "auth": "bearer"
  },
  "tags": ["email", "inbox", "communication"]
}
```

**Note:** The manifest uses a single `/dispatch` endpoint that routes by `action` field (same pattern as oap-reminder). Alternatively, the agent can call REST endpoints directly if credential injection maps the bearer token.

## Implementation Notes for Xuru

### Minimal first pass:

1. `GET /api/v1/messages` — list/search inbox
2. `GET /api/v1/summary` — daily digest for briefings
3. `GET /api/v1/health` — health check
4. Auth middleware: bearer token validation against tenant API keys table

That's enough for a read-only "check my email" agent task. Send/reply can come in phase 2.

### Multi-tenant routing:

- Subdomain identifies tenant: `netgate.xuru.ai` → tenant `netgate`
- API key validated against tenant
- All queries scoped to tenant's mailboxes
- No cross-tenant access

### Recommended Xuru DB additions:

```sql
CREATE TABLE api_keys (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    key_hash TEXT NOT NULL,
    name TEXT,          -- e.g., "OAP agent"
    created_at TEXT,
    last_used_at TEXT,
    rate_limit INTEGER DEFAULT 60,  -- requests per minute
    scopes TEXT DEFAULT 'read',     -- 'read', 'read,write', 'read,write,send'
    enabled INTEGER DEFAULT 1
);

CREATE TABLE api_audit_log (
    id TEXT PRIMARY KEY,
    api_key_id TEXT REFERENCES api_keys(id),
    endpoint TEXT,
    method TEXT,
    status_code INTEGER,
    created_at TEXT
);
```
