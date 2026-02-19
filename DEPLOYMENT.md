# OAP Deployment Guide — Mac Mini + Vercel

Saved from session planning (Phase 7). Use this when setting up the new Mac Mini.

---

## Mac Mini Setup

### 1. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

### 2. Python Services

```bash
python3 -m venv ~/.oap-venv
source ~/.oap-venv/bin/activate

# Clone the repo
git clone https://github.com/cloudseeder/oap-dev.git
cd oap-dev

# Install all three services
pip install -e reference/oap_discovery
pip install -e reference/oap_trust
pip install -e reference/oap_dashboard
```

### 3. Configure launchd Services

Create plist files in `~/Library/LaunchAgents/` for each service:

**Ollama** — runs automatically after install, but verify:
```bash
ollama serve  # or check launchctl list | grep ollama
```

**Discovery API** (`com.oap.discovery.plist`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.oap.discovery</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/.oap-venv/bin/oap-api</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USER/oap-dev/reference/oap_discovery</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>OAP_BACKEND_SECRET</key>
        <string>YOUR_SECRET_HERE</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/oap-discovery.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/oap-discovery.err</string>
</dict>
</plist>
```

**Trust API** (`com.oap.trust.plist`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.oap.trust</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/.oap-venv/bin/oap-trust-api</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USER/oap-dev/reference/oap_trust</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>OAP_BACKEND_SECRET</key>
        <string>YOUR_SECRET_HERE</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/oap-trust.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/oap-trust.err</string>
</dict>
</plist>
```

**Dashboard API** (`com.oap.dashboard.plist`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.oap.dashboard</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/.oap-venv/bin/oap-dashboard-api</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USER/oap-dev/reference/oap_dashboard</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>OAP_BACKEND_SECRET</key>
        <string>YOUR_SECRET_HERE</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/oap-dashboard.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/oap-dashboard.err</string>
</dict>
</plist>
```

**Crawler (cron)** (`com.oap.crawler.plist`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.oap.crawler</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/.oap-venv/bin/oap-crawl</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USER/oap-dev/reference/oap_discovery</string>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>StandardOutPath</key>
    <string>/tmp/oap-crawler.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/oap-crawler.err</string>
</dict>
</plist>
```

Load all services:
```bash
launchctl load ~/Library/LaunchAgents/com.oap.discovery.plist
launchctl load ~/Library/LaunchAgents/com.oap.trust.plist
launchctl load ~/Library/LaunchAgents/com.oap.dashboard.plist
launchctl load ~/Library/LaunchAgents/com.oap.crawler.plist
```

### 4. Cloudflare Tunnel

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
  - hostname: api.oap.dev
    service: http://localhost:8300
  - hostname: trust.oap.dev
    service: http://localhost:8301
  - hostname: dashboard.oap.dev
    service: http://localhost:8302
  - service: http_status:404
```

Run tunnel:
```bash
cloudflared tunnel run oap
```

Or create a launchd service for it (`com.oap.tunnel.plist`).

### 5. DNS

Add CNAME records in Cloudflare DNS:
- `api.oap.dev` → `YOUR_TUNNEL_ID.cfargotunnel.com`
- `trust.oap.dev` → `YOUR_TUNNEL_ID.cfargotunnel.com`
- `dashboard.oap.dev` → `YOUR_TUNNEL_ID.cfargotunnel.com`

Or use a single hostname and route by path in the Next.js proxy layer.

### 6. Backend Secret

Generate a strong random token:
```bash
openssl rand -hex 32
```

Set `OAP_BACKEND_SECRET` in all three service plist files (see above). This is the shared secret that Python backend services check on incoming requests via the `X-Backend-Token` header (added in S8). Without it, anyone who discovers the tunnel URL can hit the APIs directly. If the env var is not set, the check is skipped (local dev mode).

---

## Vercel Setup

### 1. Environment Variables

Set in Vercel dashboard (Settings → Environment Variables):

| Variable | Value |
|----------|-------|
| `BACKEND_URL` | Cloudflare Tunnel hostname (e.g., `https://api.oap.dev`) |
| `BACKEND_SECRET` | Same token as `OAP_BACKEND_SECRET` on Mac Mini |

The Next.js proxy (`lib/proxy.ts`) attaches the secret as the `X-Backend-Token` header on every proxied request.

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
curl http://localhost:8300/health    # Discovery
curl http://localhost:8301/health    # Trust
curl http://localhost:8302/health    # Dashboard
```

### Service ports:
| Service | Port |
|---------|------|
| Discovery API | 8300 |
| Trust API | 8301 |
| Dashboard API | 8302 |
| Ollama | 11434 |
