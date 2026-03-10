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
| `GET` | `/messages` | List cached messages (query params: `folder`, `since`, `unread`, `query`, `limit`) |
| `GET` | `/messages/{id}` | Get a single message |
| `GET` | `/threads/{thread_id}` | Get all messages in a thread |
| `GET` | `/summary` | Activity overview: counts, senders, subjects (query param: `since`) |
| `POST` | `/api` | Dispatch endpoint for OAP tool bridge (action-based routing) |
| `GET` | `/health` | Health check |

### Dispatch Actions

The `/api` endpoint accepts `{"action": "..."}` for the OAP tool bridge:

- `scan` — fetch new messages from IMAP
- `list` — list cached messages (supports `since`, `unread`, `query`, `folder`, `limit`)
- `get` — fetch single message by `id`
- `thread` — fetch thread by `thread_id`
- `summary` — activity overview

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
| `config.py` | YAML config loader, IMAP/DB/API settings |
| `models.py` | Pydantic types for messages, threads, summaries |
| `sanitize.py` | HTML→text, prompt injection filtering |
| `imap.py` | Async IMAP scanner via aioimaplib, MIME parsing |
| `db.py` | SQLite message cache with threading support |
| `api.py` | FastAPI service, REST + dispatch endpoints |
