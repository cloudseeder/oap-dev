# oap-email

IMAP email scanner with LLM-powered classification and auto-filing. Fetches messages from any IMAP server, caches them in SQLite, classifies them using a local LLM, and optionally files them into IMAP folders by category. No HTML, no raw MIME, no prompt injection reaches the LLM.

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

classifier:
  enabled: true
  model: "qwen3.5:latest"
  ollama_url: "http://localhost:11434"
  timeout: 30

auto_file:
  enabled: true
  folders:
    personal: Personal
    machine: Machine
    mailing-list: Mailing-List
    spam: Spam
    offers: Offers
```

### App Passwords

Most providers require an app password for IMAP, not your login password:
- **Gmail**: [Google App Passwords](https://myaccount.google.com/apppasswords) (requires 2FA)
- **iCloud**: [Apple App-Specific Passwords](https://support.apple.com/en-us/102654)
- **Fastmail**: Settings > Privacy & Security > App Passwords

## Architecture

Three-phase pipeline: scan, classify, file.

1. **Scan** (`POST /scan`) — connects to IMAP, fetches messages newer than the last cached UID, parses MIME, sanitizes, and caches to SQLite. Timestamps normalized to UTC.
2. **Classify** (automatic after scan) — sends subject, sender, and snippet to a local LLM which returns a single category word. Stored in the `category` column.
3. **File** (`POST /file`) — moves classified messages to IMAP folders based on category mapping. Creates folders if they don't exist. Marks messages as filed to prevent re-processing.

Between scans, reads are instant (local SQLite). The full pipeline runs well as a cron job:

```bash
# Every 15 minutes: scan IMAP, then file classified messages
*/15 * * * * curl -s -X POST http://localhost:8305/scan && curl -s -X POST http://localhost:8305/file > /dev/null 2>&1
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/scan` | Fetch new messages from IMAP, cache locally |
| `GET` | `/messages` | List cached messages (query params: `folder`, `since`, `unread`, `query`, `category`, `limit`) |
| `GET` | `/messages/{id}` | Get a single message |
| `GET` | `/threads/{thread_id}` | Get all messages in a thread |
| `GET` | `/summary` | Activity overview: counts, senders, subjects (query param: `since`) |
| `POST` | `/classify` | Manually trigger LLM classification of uncategorized messages |
| `POST` | `/reclassify` | Reset all categories and reclassify every message |
| `POST` | `/file` | Move classified messages to IMAP folders by category |
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
- `reclassify` — reset all categories and reclassify
- `file` — move classified messages to IMAP folders

## Email Classifier

Messages are automatically categorized using a local LLM via Ollama. Classification runs in the background after each scan and stores the result in the database — each message is only classified once.

### Categories

| Category | Description |
|----------|-------------|
| `personal` | Written by or about a real person: colleagues, friends, family, clients, community members. Social media notifications about people you know (Facebook comments, tags). HOA/community group emails. |
| `machine` | Automated/system-generated with no human author: server alerts, cron output, cPanel, disk space warnings, security scans, WordPress updates, CI/CD, monitoring, auth codes |
| `mailing-list` | Informational newsletters, news digests, editorial content, industry bulletins (CISA advisories, tech newsletters, curated content) |
| `spam` | Junk, phishing, unsolicited bulk email |
| `offers` | Selling something: sales, promotions, deals, coupons, discounts, event tickets, subscription renewals, product launches, service upgrades |

### Manual Classification

```bash
# Classify uncategorized messages (up to 50 per call)
curl -X POST http://localhost:8305/classify

# Reset all categories and reclassify everything
curl -X POST http://localhost:8305/reclassify
```

### Query Filtering

```bash
# Only personal correspondence
curl -X POST http://localhost:8305/api \
  -H 'Content-Type: application/json' \
  -d '{"action": "list", "category": "personal"}'

# Machine alerts from today
curl -X POST http://localhost:8305/api \
  -H 'Content-Type: application/json' \
  -d '{"action": "list", "category": "machine", "since": "2026-03-12T00:00:00Z"}'
```

## Auto-Filing

When enabled, `POST /file` moves classified messages from INBOX to category-specific IMAP folders via COPY + DELETE. Target folders are created automatically if they don't exist.

### How It Works

1. Queries the DB for classified but unfiled messages
2. Maps each message's category to an IMAP folder name (configurable)
3. Opens a writable IMAP connection, copies messages to target folders
4. Deletes originals from source folder (IMAP expunge)
5. Marks messages as `filed` in the DB

### Configuration

```yaml
auto_file:
  enabled: true
  folders:
    personal: Personal        # category → IMAP folder name
    machine: Machine
    mailing-list: Mailing-List
    spam: Spam
    offers: Offers
```

Override any folder name to match your mail server's conventions (e.g., `spam: Junk` for servers that use "Junk" instead of "Spam").

### Standalone Use

The scanner works independently of OAP. Point it at any IMAP mailbox with an Ollama instance available, and it becomes a self-hosted email classifier and filer:

```bash
# Minimal config — just IMAP + classifier + auto-file
oap-email-api --config my-mailbox.yaml

# Cron: scan, classify (automatic), file
*/15 * * * * curl -s -X POST http://localhost:8305/scan && curl -s -X POST http://localhost:8305/file
```

No agent, no discovery service, no manifests required.

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
- **Model**: qwen3.5:9b

The task results appear in the morning greeting briefing automatically.

## Files

| File | Purpose |
|------|---------|
| `config.py` | YAML config loader: IMAP, DB, API, classifier, auto-file settings |
| `models.py` | Pydantic types for messages, threads, summaries, dispatch |
| `sanitize.py` | HTML→text, prompt injection filtering |
| `imap.py` | Async IMAP scanner + message mover via stdlib imaplib |
| `db.py` | SQLite message cache with threading, query parser, category + filed tracking |
| `classifier.py` | LLM email categorization via Ollama |
| `api.py` | FastAPI service: REST + dispatch + background classification + auto-filing |
