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

# Install all three services
pip install -e reference/oap_discovery
pip install -e reference/oap_trust
pip install -e reference/oap_dashboard
```

### 3. Configure and Start Services

The setup script generates a backend secret, creates all four launchd plist files, loads them, and runs health checks:

```bash
cd ~/oap-dev
./scripts/setup-mac-mini.sh
```

This creates:
- `~/Library/LaunchAgents/com.oap.discovery.plist` — Discovery API (:8300)
- `~/Library/LaunchAgents/com.oap.trust.plist` — Trust API (:8301)
- `~/Library/LaunchAgents/com.oap.dashboard.plist` — Dashboard API (:8302)
- `~/Library/LaunchAgents/com.oap.crawler.plist` — Crawler (hourly cron)
- `~/.oap-secret` — Backend secret (chmod 600)

The script is idempotent — re-running it will unload existing services, regenerate plists (reusing the existing secret from `~/.oap-secret`), and reload.

**Ollama** — runs automatically after install, but verify:
```bash
ollama serve  # or check launchctl list | grep ollama
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
SECRET=$(cat ~/.oap-secret)
curl -H "X-Backend-Token: $SECRET" http://localhost:8300/health    # Discovery
curl -H "X-Backend-Token: $SECRET" http://localhost:8301/health    # Trust
curl -H "X-Backend-Token: $SECRET" http://localhost:8302/health    # Dashboard
```

### Service ports:
| Service | Port |
|---------|------|
| Discovery API | 8300 |
| Trust API | 8301 |
| Dashboard API | 8302 |
| Ollama | 11434 |
