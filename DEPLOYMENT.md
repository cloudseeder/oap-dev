# OAP Deployment Guide — Mac Mini + Vercel

Saved from session planning (Phase 7). Use this when setting up the new Mac Mini.

---

## Mac Mini Setup

### 0. Prerequisites (Homebrew + Python 3.12)

macOS ships with Python 3.9 but OAP requires 3.11+. Install Homebrew first, then Python 3.12.

```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Follow the instructions Homebrew prints to add it to your PATH, then:
brew install python@3.12
```

### 1. Install Ollama

Download from [ollama.com/download](https://ollama.com/download) (macOS version). Drag to Applications and open it — runs as a menu bar app.

```bash
ollama pull qwen3:4b
ollama pull nomic-embed-text

# Verify
curl http://localhost:11434/api/tags
```

### 2. Python Services

```bash
# Use brew --prefix to find the correct path
$(brew --prefix python@3.12)/bin/python3.12 -m venv ~/.oap-venv
source ~/.oap-venv/bin/activate
pip install --upgrade pip setuptools

# Clone the repo
git clone https://github.com/cloudseeder/oap-dev.git ~/oap-dev
cd ~/oap-dev

# Install all services
pip install -e reference/oap_discovery
pip install -e reference/oap_trust
pip install -e reference/oap_dashboard
pip install -e reference/oap_agent
pip install -e reference/oap_reminder
pip install -e reference/oap_email
```

### 3. Configure Services

Each service reads a `config.yaml` from its working directory. Copy the examples and edit:

```bash
cd ~/oap-dev

# Discovery — copy config.yaml.example to config.yaml (already documented elsewhere)
cp reference/oap_discovery/config.yaml.example reference/oap_discovery/config.yaml

# Agent — needs discovery URL
cp reference/oap_agent/config.yaml.example reference/oap_agent/config.yaml
# Edit: set discovery.url, voice paths, etc.

# Reminder — optional config (defaults: 127.0.0.1:8304, ~/oap_reminder.db)
cat > reference/oap_reminder/config.yaml <<'EOF'
database:
  path: "oap_reminder.db"
api:
  host: "127.0.0.1"
  port: 8304
EOF

# Email scanner — needs IMAP credentials
cp reference/oap_email/config.yaml.example reference/oap_email/config.yaml
# Edit: set imap.host, imap.username, imap.password (or OAP_EMAIL_PASSWORD env var)
# Enable classifier: classifier.enabled: true
# Enable auto-filing: auto_file.enabled: true, auto_file.folders mapping
```

### 4. Voice Setup (Agent)

The agent supports local voice input (faster-whisper STT) and output (Piper TTS). Both are optional.

**Piper TTS** — download a voice model:

```bash
mkdir -p ~/oap-dev/reference/oap_agent/piper-voices
cd ~/oap-dev/reference/oap_agent/piper-voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

Then set the path in `reference/oap_agent/config.yaml`:

```yaml
voice:
  tts_enabled: true
  tts_model_path: /Users/YOUR_USER/oap-dev/reference/oap_agent/piper-voices/en_US-lessac-medium.onnx
  tts_models_dir: /Users/YOUR_USER/oap-dev/reference/oap_agent/piper-voices
```

**faster-whisper STT** — installed automatically with `pip install -e reference/oap_agent`. The Whisper model (`base` by default) downloads on first transcription request. Configure via `voice.whisper_model` in `config.yaml` (options: `tiny`, `base`, `small`).

Browse additional voices at: https://rhasspy.github.io/piper-samples/

See `docs/PIPER.md` for full voice setup details.

### 5. Start Services

The setup script generates a backend secret, creates all launchd plist files, loads them, and runs health checks:

```bash
cd ~/oap-dev
./scripts/setup-mac-mini.sh
```

This creates:
- `~/Library/LaunchAgents/com.oap.discovery.plist` — Discovery API (:8300)
- `~/Library/LaunchAgents/com.oap.trust.plist` — Trust API (:8301)
- `~/Library/LaunchAgents/com.oap.dashboard.plist` — Dashboard API (:8302)
- `~/Library/LaunchAgents/com.oap.agent.plist` — Manifest Agent (:8303)
- `~/Library/LaunchAgents/com.oap.crawler.plist` — Crawler (hourly cron)
- `~/.oap-secret` — Backend secret (chmod 600)

The script is idempotent — re-running it will unload existing services, regenerate plists (reusing the existing secret from `~/.oap-secret`), and reload.

**Note:** The setup script does not yet create plists for the reminder and email services. Add them manually:

#### Reminder service plist

Create `~/Library/LaunchAgents/com.oap.reminder.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.oap.reminder</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/.oap-venv/bin/oap-reminder-api</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USER/oap-dev/reference/oap_reminder</string>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/com.oap.reminder.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/com.oap.reminder.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.oap.reminder.plist
```

#### Email scanner plist

Create `~/Library/LaunchAgents/com.oap.email.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.oap.email</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/.oap-venv/bin/oap-email-api</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USER/oap-dev/reference/oap_email</string>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/com.oap.email.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/com.oap.email.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.oap.email.plist
```

**Ollama** — runs automatically after install, but verify:
```bash
ollama serve  # or check launchctl list | grep ollama
```

### 6. Cron Jobs

**Email scan + classify + file** — run periodically to keep the email cache fresh:

```bash
# Every 15 minutes via cron:
*/15 * * * * curl -s -X POST http://localhost:8305/scan && curl -s -X POST http://localhost:8305/file

# Or as a launchd StartInterval plist (900 seconds = 15 minutes)
```

The scan endpoint fetches new messages from IMAP, triggers background classification (if `classifier.enabled: true`), and returns. The file endpoint moves classified messages to IMAP folders (if `auto_file.enabled: true`).

**Reminder cleanup** — purge old completed reminders (optional, monthly):

```bash
0 0 1 * * curl -s -X POST "http://localhost:8304/reminders/cleanup?older_than_days=90"
```

### 7. Cloudflare Tunnel

```bash
brew install cloudflared
cloudflared tunnel login
cloudflared tunnel create oap

# Configure tunnel (config.yml at ~/.cloudflared/config.yml)
```

**`~/.cloudflared/config.yml`:**
```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: /Users/YOUR_USER/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  # Discovery API — only public-facing routes (auth via X-Backend-Token)
  - hostname: api.oap.dev
    path: /v1/discover
    service: http://localhost:8300
  - hostname: api.oap.dev
    path: /v1/manifests
    service: http://localhost:8300
  - hostname: api.oap.dev
    path: /health
    service: http://localhost:8300
  # All other api.oap.dev paths blocked (tool bridge, experience routes are local-only)
  - hostname: api.oap.dev
    service: http_status:403
  # Trust & Dashboard — full access (services have their own auth)
  - hostname: trust.oap.dev
    service: http://localhost:8301
  - hostname: dashboard.oap.dev
    service: http://localhost:8302
  - service: http_status:404
```

The `path` rules use prefix matching — `/v1/manifests` matches both `/v1/manifests` and `/v1/manifests/{domain}`. Routes not explicitly allowed (`/v1/chat`, `/v1/tools`, `/v1/experience/*`) return 403.

**Local-only services:** The Manifest agent (:8303), Reminder (:8304), and Email scanner (:8305) are intentionally not exposed via the tunnel. They run on the local network only — no Cloudflare hostname, no public access.

Create DNS routes (CNAME records pointing to the tunnel):
```bash
cloudflared tunnel route dns oap api.oap.dev
cloudflared tunnel route dns oap trust.oap.dev
cloudflared tunnel route dns oap dashboard.oap.dev
```

Start the tunnel:
```bash
cloudflared tunnel run oap
```

Verify from another terminal:
```bash
# Allowed routes
curl -H "X-Backend-Token: $(cat ~/.oap-secret)" https://api.oap.dev/health
curl -H "X-Backend-Token: $(cat ~/.oap-secret)" https://trust.oap.dev/health
curl -H "X-Backend-Token: $(cat ~/.oap-secret)" https://dashboard.oap.dev/health

# Blocked routes (should return 403)
curl -s -o /dev/null -w "%{http_code}" https://api.oap.dev/v1/chat
curl -s -o /dev/null -w "%{http_code}" https://api.oap.dev/v1/tools
curl -s -o /dev/null -w "%{http_code}" https://api.oap.dev/v1/experience/stats
```

### 8. Persist Tunnel as launchd Service

Copy config and credentials to the system-level directory:
```bash
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/config.yml /etc/cloudflared/config.yml
sudo cp ~/.cloudflared/*.json /etc/cloudflared/
```

Install the service (as root so it runs at boot):
```bash
sudo cloudflared service install
```

**Note:** The default plist created by `cloudflared service install` may be missing the `tunnel run` arguments. If the tunnel doesn't start (check `/Library/Logs/com.cloudflare.cloudflared.err.log`), fix the plist:
```bash
sudo launchctl bootout system/com.cloudflare.cloudflared
```

Then replace `/Library/LaunchDaemons/com.cloudflare.cloudflared.plist` with:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>Label</key>
        <string>com.cloudflare.cloudflared</string>
        <key>ProgramArguments</key>
        <array>
            <string>/opt/homebrew/bin/cloudflared</string>
            <string>tunnel</string>
            <string>--config</string>
            <string>/etc/cloudflared/config.yml</string>
            <string>run</string>
            <string>oap</string>
        </array>
        <key>RunAtLoad</key>
        <true/>
        <key>StandardOutPath</key>
        <string>/Library/Logs/com.cloudflare.cloudflared.out.log</string>
        <key>StandardErrorPath</key>
        <string>/Library/Logs/com.cloudflare.cloudflared.err.log</string>
        <key>KeepAlive</key>
        <dict>
            <key>SuccessfulExit</key>
            <false/>
        </dict>
        <key>ThrottleInterval</key>
        <integer>5</integer>
    </dict>
</plist>
```

Then load it:
```bash
sudo launchctl bootstrap system /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
```

Verify:
```bash
sudo launchctl list | grep cloudflare
curl -H "X-Backend-Token: $(cat ~/.oap-secret)" https://api.oap.dev/health
```

---

## Vercel Setup

### 1. Environment Variables

Set in Vercel dashboard (Settings → Environment Variables):

| Variable | Value |
|----------|-------|
| `BACKEND_URL` | `https://api.oap.dev` (Discovery API) |
| `TRUST_URL` | `https://trust.oap.dev` (Trust API) |
| `DASHBOARD_URL` | `https://dashboard.oap.dev` (Dashboard API) |
| `BACKEND_SECRET` | Same token as `OAP_BACKEND_SECRET` on Mac Mini |

The Next.js proxy (`lib/proxy.ts`) attaches the secret as the `X-Backend-Token` header on every proxied request. In local dev, only `BACKEND_URL` is needed — the proxy falls back to port-swapping for trust (:8301) and dashboard (:8302).

### 2. Deploy

```bash
git push  # Vercel auto-builds from git push
```

---

## End-to-End Verification

After both Vercel and Mac Mini are running:

- `oap.dev/playground` — paste JSON, validate, preview
- `oap.dev/discover` — type a task, get manifest match
- `oap.dev/trust` — enter domain, see attestation flow
- `oap.dev/dashboard` — see adoption stats
- `oap.dev/spec` — spec still renders

### Service health checks (from Mac Mini):
```bash
SECRET=$(cat ~/.oap-secret)
curl -H "X-Backend-Token: $SECRET" http://localhost:8300/health        # Discovery
curl -H "X-Backend-Token: $SECRET" http://localhost:8301/health        # Trust
curl -H "X-Backend-Token: $SECRET" http://localhost:8302/health        # Dashboard
curl http://localhost:8303/v1/agent/health                             # Agent (no auth)
curl http://localhost:8304/reminders                                   # Reminder (no auth)
curl http://localhost:8305/health                                      # Email (no auth)
```

### Service ports:
| Service | Port | Tunnel-exposed |
|---------|------|----------------|
| Discovery API | 8300 | Yes (partial — `/v1/discover`, `/v1/manifests`, `/health` only) |
| Trust API | 8301 | Yes |
| Dashboard API | 8302 | Yes |
| Manifest Agent | 8303 | No (local-only) |
| Reminder API | 8304 | No (local-only) |
| Email Scanner | 8305 | No (local-only) |
| Ollama | 11434 | No (local-only) |
