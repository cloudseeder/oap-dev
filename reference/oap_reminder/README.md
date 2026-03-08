# OAP Reminder Service

SQLite-backed reminder service designed for AI agents via OAP manifest discovery.

## Install

```bash
pip install -e reference/oap_reminder
```

## Run

```bash
oap-reminder-api                    # starts on :8304
oap-reminder-api --port 9000        # custom port
oap-reminder-api --config path.yaml # custom config
```

## Config

Optional `config.yaml` (resolved relative to config file directory):

```yaml
database:
  path: oap_reminder.db
api:
  host: 127.0.0.1
  port: 8304
```

Without a config file, the database defaults to `$HOME/oap_reminder.db`.

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/reminders` | Create a reminder |
| `GET` | `/reminders` | List reminders (`?status=pending\|completed`, `?limit=`, `?offset=`) |
| `GET` | `/reminders/due` | Due/overdue reminders (`?before=YYYY-MM-DD`, default today) |
| `GET` | `/reminders/{id}` | Get a single reminder |
| `PATCH` | `/reminders/{id}` | Update fields |
| `POST` | `/reminders/{id}/complete` | Mark complete (auto-creates next if recurring) |
| `DELETE` | `/reminders/{id}` | Delete |
| `POST` | `/reminders/cleanup` | Purge old completed reminders (`?older_than_days=30`) |
| `GET` | `/health` | Health check |

## Schema

```
id, title, notes, created_at, due_date, due_time, recurring, status, completed_at
```

- `due_date`: `YYYY-MM-DD`
- `due_time`: `HH:MM` (24-hour), nullable for all-day
- `recurring`: `daily`, `weekly`, `monthly`, `yearly`, or null
- `status`: `pending` or `completed`

## Example

```bash
# Create
curl -X POST http://localhost:8304/reminders \
  -H 'Content-Type: application/json' \
  -d '{"title": "Call dentist", "due_date": "2026-03-10", "due_time": "09:00"}'

# List due today
curl http://localhost:8304/reminders/due

# Complete
curl -X POST http://localhost:8304/reminders/1/complete
```

## Cleanup

Purge completed reminders older than N days:

```bash
# Via CLI (for cron)
oap-reminder-api --cleanup 30

# Via API
curl -X POST 'http://localhost:8304/reminders/cleanup?older_than_days=30'
```

## OAP Manifest

The service is auto-discovered via `manifests/oap-reminder.json` when running alongside the discovery service. Agents can create, list, and complete reminders through natural language.

## License

CC0 1.0 Universal.
