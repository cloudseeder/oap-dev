# oap-email

Read-only IMAP email scanner for OAP agents. Fetches messages from any IMAP server, caches them in SQLite, and exposes sanitized plain text via a local API. No HTML, no raw MIME, no prompt injection reaches the LLM.

## Quick Start

```bash
pip install -e reference/oap_email
cp reference/oap_email/config.yaml.example reference/oap_email/config.yaml
# Edit config.yaml with your IMAP credentials (app password, not login password)
oap-email-api
```

Service runs on `http://localhost:8305`.

## Configuration

Copy `config.yaml.example` to `config.yaml`. Password can also be set via `OAP_EMAIL_PASSWORD` env var.

```yaml
imap:
  host: "imap.gmail.com"
  port: 993
  username: "you@gmail.com"
  password: "your-app-password"
  use_ssl: true
  folders: ["INBOX"]

database:
  path: "oap_email.db"

api:
  host: "127.0.0.1"
  port: 8305
```

### App Passwords

Most providers require an app password for IMAP, not your login password:
- **Gmail**: [Google App Passwords](https://myaccount.google.com/apppasswords) (requires 2FA)
- **iCloud**: [Apple App-Specific Passwords](https://support.apple.com/en-us/102654)
- **Fastmail**: Settings > Privacy & Security > App Passwords

## Architecture

Two-phase design: scan then read.

1. **Scan** (`POST /scan`) — connects to IMAP, fetches messages newer than the last cached UID, parses MIME, sanitizes, and caches to SQLite
2. **Read** (`GET /messages`, `GET /summary`, etc.) — queries the local cache, never touches IMAP

This means the agent task calls scan + summary together. Between scans, reads are instant (local SQLite).

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/scan` | Fetch new messages from IMAP, cache locally |
| `GET` | `/messages` | List cached messages (query params: `folder`, `since`, `unread`, `query`, `category`, `limit`) |
| `GET` | `/messages/{id}` | Get a single message |
| `GET` | `/threads/{thread_id}` | Get all messages in a thread |
| `GET` | `/summary` | Activity overview: counts, senders, subjects (query param: `since`) |
| `POST` | `/classify` | Manually trigger LLM classification of uncategorized messages |
| `POST` | `/api` | Dispatch endpoint for OAP tool bridge (action-based routing) |
| `GET` | `/health` | Health check |

### Dispatch Actions

The `/api` endpoint accepts `{"action": "..."}` for the OAP tool bridge:

- `scan` — fetch new messages from IMAP
- `list` — list cached messages (supports `since`, `unread`, `query`, `category`, `folder`, `limit`)
- `get` — fetch single message by `id`
- `thread` — fetch thread by `thread_id`
- `summary` — activity overview
- `classify` — trigger LLM classification of uncategorized messages

## Email Classifier

Messages are automatically categorized using a local LLM via Ollama. Classification runs in the background after each scan and stores the result in the database — each message is only classified once.

### Categories

| Category | Description |
|----------|-------------|
| `inbox` | Real human correspondence — anything that doesn't clearly fit the other categories |
| `marketing` | Newsletters, promotional offers, sales, subscriptions |
| `transactional` | Receipts, shipping notifications, account alerts, auth codes |
| `spam` | Junk, phishing, unsolicited messages |

### Configuration

Add to `config.yaml`:

```yaml
classifier:
  enabled: true
  model: "qwen3:14b"
  ollama_url: "http://localhost:11434"
  timeout: 30
```

### How It Works

1. `POST /scan` fetches new messages from IMAP and caches them
2. If `classifier.enabled`, a background task classifies uncategorized messages
3. Each message's subject, sender, and snippet are sent to the LLM with a short system prompt (~100 tokens)
4. The LLM returns a single category word, stored in the `category` column
5. Subsequent queries can filter by category: `{"action": "list", "category": "inbox"}`

### Manual Classification

To classify existing uncategorized messages:

```bash
curl -X POST http://localhost:8305/classify
```

Processes up to 50 messages per call. Run repeatedly until `{"classified": 0}`.

### Query Filtering

Filter by category in list queries:

```bash
# Only real correspondence
curl 'http://localhost:8305/messages?category=inbox'

# Via dispatch
curl -X POST http://localhost:8305/api \
  -H 'Content-Type: application/json' \
  -d '{"action": "list", "category": "inbox"}'
```

## Query Parser

The `query` parameter supports boolean `OR` and field prefixes for targeted searches.

### Field Prefixes

| Prefix | Searches |
|--------|----------|
| `from:` / `sender:` | `from_name`, `from_email` |
| `to:` | `to_addrs` |
| `subject:` | `subject` |
| `body:` | `body_text` |
| *(none)* | All fields |

### Examples

```
from:amy@netgate.net                    # Sender email
from:Amy OR from:Keric                  # Multiple senders
from:Amy subject:PTO                    # Sender AND subject
subject:invoice                         # Subject only
Amy Brooks OR Keric Brooks              # Names across all fields
```

Both colon style (`from:Amy`) and space style (`FROM Amy Brooks`) are supported.

## Security

### Sanitization Pipeline

1. **MIME parsing** — stdlib `email` module, handles multipart, quoted-printable, base64
2. **HTML → plain text** — custom stripper, removes scripts/styles/head
3. **Prompt injection filtering** — pattern-based removal of common injection vectors (instruction override, role manipulation, delimiter attacks, payload markers)
4. **Truncation** — bodies capped at 10,000 chars
5. **Attachment metadata only** — filenames and sizes exposed, never raw content

### What's NOT Exposed

- Raw MIME or email headers (beyond from/to/cc/subject/date)
- Attachment content
- IMAP credentials
- OAuth tokens or server IPs

## Manifest

The OAP manifest is at `reference/oap_discovery/manifests/oap-email.json`. It's auto-indexed by the discovery service on startup.

## Agent Task Example

Create a scheduled task in the agent UI:

- **Name**: Daily email scan
- **Prompt**: Scan my email and summarize any new messages
- **Schedule**: `0 7 * * *` (daily at 7 AM)
- **Model**: qwen3:14b

The task results appear in the morning greeting briefing automatically.

## Files

| File | Purpose |
|------|---------|
| `config.py` | YAML config loader, IMAP/DB/API/classifier settings |
| `models.py` | Pydantic types for messages, threads, summaries, dispatch |
| `sanitize.py` | HTML→text, prompt injection filtering |
| `imap.py` | Async IMAP scanner via stdlib imaplib, MIME parsing |
| `db.py` | SQLite message cache with threading, query parser, category support |
| `classifier.py` | LLM email categorization via Ollama |
| `api.py` | FastAPI service, REST + dispatch + background classification |
