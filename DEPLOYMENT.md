# OAP Deployment Guide — Mac Mini + Vercel

This repo deploys the OAP website (Vercel) and its two backend services: Trust and Dashboard.

Discovery, Agent, Reminder, and Email have moved to the [manifest repo](https://github.com/cloudseeder/manifest).

---

## Mac Mini Setup (Trust + Dashboard)

### 0. Prerequisites (Homebrew + Python 3.12)

```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Follow the instructions Homebrew prints to add it to your PATH, then:
brew install python@3.12
```

### 1. Python Services

```bash
$(brew --prefix python@3.12)/bin/python3.12 -m venv ~/.oap-venv
source ~/.oap-venv/bin/activate
pip install --upgrade pip setuptools

git clone https://github.com/cloudseeder/oap-dev.git ~/oap-dev
cd ~/oap-dev

pip install -e reference/oap_trust
pip install -e reference/oap_dashboard
```

### 2. Start Services

```bash
cd ~/oap-dev
./scripts/setup-mac-mini.sh
```

This creates:
- `~/Library/LaunchAgents/com.oap.trust.plist` — Trust API (:8301)
- `~/Library/LaunchAgents/com.oap.dashboard.plist` — Dashboard API (:8302)
- `~/.oap-secret` — Backend secret (chmod 600)

The script is idempotent — re-running it will unload existing services, regenerate plists (reusing the existing secret from `~/.oap-secret`), and reload.

### 3. Cloudflare Tunnel

```bash
brew install cloudflared
cloudflared tunnel login
cloudflared tunnel create oap
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
  - hostname: api.oap.dev
    service: http_status:403
  # Trust & Dashboard
  - hostname: trust.oap.dev
    service: http://localhost:8301
  - hostname: dashboard.oap.dev
    service: http://localhost:8302
  - service: http_status:404
```

Create DNS routes:
```bash
cloudflared tunnel route dns oap api.oap.dev
cloudflared tunnel route dns oap trust.oap.dev
cloudflared tunnel route dns oap dashboard.oap.dev
```

### 4. Persist Tunnel as launchd Service

```bash
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/config.yml /etc/cloudflared/config.yml
sudo cp ~/.cloudflared/*.json /etc/cloudflared/
sudo cloudflared service install
```

**Note:** If the tunnel doesn't start, replace `/Library/LaunchDaemons/com.cloudflare.cloudflared.plist` with:
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

Then:
```bash
sudo launchctl bootout system/com.cloudflare.cloudflared
sudo launchctl bootstrap system /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
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

### 2. Deploy

```bash
git push  # Vercel auto-builds from git push
```

---

## End-to-End Verification

- `oap.dev/playground` — paste JSON, validate, preview
- `oap.dev/discover` — type a task, get manifest match
- `oap.dev/trust` — enter domain, see attestation flow
- `oap.dev/dashboard` — see adoption stats

### Health checks (from Mac Mini):
```bash
SECRET=$(cat ~/.oap-secret)
curl -H "X-Backend-Token: $SECRET" http://localhost:8301/health        # Trust
curl -H "X-Backend-Token: $SECRET" http://localhost:8302/health        # Dashboard
```

### Service ports:
| Service | Port | Tunnel-exposed |
|---------|------|----------------|
| Trust API | 8301 | Yes |
| Dashboard API | 8302 | Yes |
