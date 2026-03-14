#!/usr/bin/env bash
set -euo pipefail

# OAP Mac Mini Setup Script — Trust + Dashboard only
# Discovery, Agent, Reminder, and Email now live in the manifest repo.
# Run from the repo root: ./scripts/setup-mac-mini.sh

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$HOME/.oap-venv"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
USER_NAME="$(whoami)"

echo "=== OAP Mac Mini Service Setup (Trust + Dashboard) ==="
echo "Repo:  $REPO_DIR"
echo "Venv:  $VENV_DIR"
echo "User:  $USER_NAME"
echo ""

# --- Verify prerequisites ---

if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: Virtual environment not found at $VENV_DIR"
    echo "Create it first: \$(brew --prefix python@3.12)/bin/python3.12 -m venv $VENV_DIR"
    exit 1
fi

for cmd in oap-trust-api oap-dashboard-api; do
    if [ ! -f "$VENV_DIR/bin/$cmd" ]; then
        echo "ERROR: $cmd not found in $VENV_DIR/bin/"
        echo "Install services first:"
        echo "  source $VENV_DIR/bin/activate"
        echo "  pip install -e reference/oap_trust"
        echo "  pip install -e reference/oap_dashboard"
        exit 1
    fi
done

# --- Generate or prompt for backend secret ---

if [ -n "${OAP_BACKEND_SECRET:-}" ]; then
    SECRET="$OAP_BACKEND_SECRET"
    echo "Using OAP_BACKEND_SECRET from environment."
elif [ -f "$HOME/.oap-secret" ]; then
    SECRET="$(cat "$HOME/.oap-secret")"
    echo "Using existing secret from ~/.oap-secret"
else
    SECRET="$(openssl rand -hex 32)"
    echo "$SECRET" > "$HOME/.oap-secret"
    chmod 600 "$HOME/.oap-secret"
    echo "Generated new secret, saved to ~/.oap-secret (chmod 600)"
fi

echo ""

# --- Create LaunchAgents directory if needed ---

mkdir -p "$LAUNCH_DIR"

# --- Helper to write a plist ---

write_plist() {
    local label="$1"
    local program="$2"
    local workdir="$3"
    local include_secret="$4"
    local interval="${5:-}"
    if [ $# -ge 5 ]; then
        shift 5
        local extra_args=("$@")
    else
        local extra_args=()
    fi
    local plist_path="$LAUNCH_DIR/$label.plist"

    # Unload if already loaded
    launchctl list "$label" &>/dev/null && launchctl unload "$plist_path" 2>/dev/null || true

    local env_block=""
    if [ "$include_secret" = "yes" ]; then
        env_block="    <key>EnvironmentVariables</key>
    <dict>
        <key>OAP_BACKEND_SECRET</key>
        <string>$SECRET</string>
    </dict>"
    fi

    local schedule_block=""
    if [ -n "$interval" ]; then
        schedule_block="    <key>StartInterval</key>
    <integer>$interval</integer>"
    else
        schedule_block="    <key>KeepAlive</key>
    <true/>"
    fi

    local args_block="        <string>$program</string>"
    if [ ${#extra_args[@]} -gt 0 ]; then
        for arg in "${extra_args[@]}"; do
            args_block="$args_block
        <string>$arg</string>"
        done
    fi

    cat > "$plist_path" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>ProgramArguments</key>
    <array>
$args_block
    </array>
    <key>WorkingDirectory</key>
    <string>$workdir</string>
$env_block
$schedule_block
    <key>StandardOutPath</key>
    <string>/tmp/$label.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/$label.err</string>
</dict>
</plist>
PLIST

    echo "  Created $plist_path"
}

# --- Write all plist files ---

echo "Creating launchd plist files..."

write_plist "com.oap.trust" \
    "$VENV_DIR/bin/oap-trust-api" \
    "$REPO_DIR/reference/oap_trust" \
    "yes"

write_plist "com.oap.dashboard" \
    "$VENV_DIR/bin/oap-dashboard-api" \
    "$REPO_DIR/reference/oap_dashboard" \
    "yes"

echo ""

# --- Load all services ---

echo "Loading services..."
for label in com.oap.trust com.oap.dashboard; do
    launchctl load "$LAUNCH_DIR/$label.plist"
    echo "  Loaded $label"
done

echo ""

# --- Wait for services to start ---

echo "Waiting for services to start (up to 30s)..."

OK=0
FAIL=0
MAX_WAIT=30
INTERVAL=5
ELAPSED=0

REMAINING="8301:Trust:trust:/health 8302:Dashboard:dashboard:/health"

while [ $ELAPSED -lt $MAX_WAIT ] && [ -n "$REMAINING" ]; do
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
    STILL_WAITING=""
    for port_name in $REMAINING; do
        port="$(echo "$port_name" | cut -d: -f1)"
        name="$(echo "$port_name" | cut -d: -f2)"
        path="$(echo "$port_name" | cut -d: -f4)"
        if curl -sf -H "X-Backend-Token: $SECRET" "http://localhost:$port$path" >/dev/null 2>&1; then
            echo "  $name (:$port) — OK (${ELAPSED}s)"
            OK=$((OK + 1))
        else
            STILL_WAITING="$STILL_WAITING $port_name"
        fi
    done
    REMAINING="$(echo "$STILL_WAITING" | xargs)"
done

for port_name in $REMAINING; do
    port="$(echo "$port_name" | cut -d: -f1)"
    name="$(echo "$port_name" | cut -d: -f2)"
    label="$(echo "$port_name" | cut -d: -f3)"
    echo "  $name (:$port) — FAILED after ${MAX_WAIT}s (check /tmp/com.oap.$label.err)"
    FAIL=$((FAIL + 1))
done

echo ""
echo "=== Setup complete: $OK healthy, $FAIL failed ==="
echo ""
echo "Backend secret: saved in ~/.oap-secret"
echo "Set this same value as BACKEND_SECRET in Vercel environment variables."
echo ""
echo "NOTE: Discovery, Agent, Reminder, and Email are now in the manifest repo."
echo "See https://github.com/cloudseeder/manifest for setup."
echo ""
echo "Logs:"
echo "  tail -f /tmp/com.oap.trust.log"
echo "  tail -f /tmp/com.oap.dashboard.log"
