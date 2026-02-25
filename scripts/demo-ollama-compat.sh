#!/usr/bin/env bash
# demo-ollama-compat.sh — Demonstrate OAP as a drop-in Ollama replacement
#
# Shows that standard Ollama API endpoints work through the OAP server,
# with /api/chat getting automatic tool discovery + execution.
#
# Prerequisites:
#   - OAP discovery service running on :8300
#   - Ollama running on :11434
#
# Usage:
#   ./scripts/demo-ollama-compat.sh --token <secret> [oap_url]
#
# Default oap_url: http://localhost:8300

set -euo pipefail

TOKEN=""
OAP="http://localhost:8300"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --token) TOKEN="$2"; shift 2 ;;
        *) OAP="$1"; shift ;;
    esac
done

if [ -z "$TOKEN" ]; then
    TOKEN="${OAP_BACKEND_TOKEN:-}"
fi
if [ -z "$TOKEN" ]; then
    printf "Error: --token <secret> or OAP_BACKEND_TOKEN env var required\n" >&2
    exit 1
fi
BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[32m'
CYAN='\033[36m'
YELLOW='\033[33m'
RED='\033[31m'
RESET='\033[0m'

pass=0
fail=0

header() { printf "\n${BOLD}${CYAN}=== %s ===${RESET}\n\n" "$1"; }
step()   { printf "${BOLD}%s${RESET}\n" "$1"; }
cmd()    { printf "${DIM}  \$ %s${RESET}\n" "$1"; }
ok()     { printf "${GREEN}  ✓ %s${RESET}\n" "$1"; pass=$((pass + 1)); }
err()    { printf "${RED}  ✗ %s${RESET}\n" "$1"; fail=$((fail + 1)); }
note()   { printf "${YELLOW}  → %s${RESET}\n" "$1"; }

# Helper: run curl and capture both response body and HTTP status code.
# Usage: run_curl <args...>
# Sets: CURL_BODY, CURL_CODE
run_curl() {
    local tmp
    tmp=$(mktemp)
    CURL_CODE=$(curl -s -o "$tmp" -w '%{http_code}' "$@" 2>/dev/null) || CURL_CODE="000"
    CURL_BODY=$(cat "$tmp")
    rm -f "$tmp"
}

# Helper: check if last run_curl succeeded (2xx status)
curl_ok() { [[ "$CURL_CODE" == 2* ]]; }

# -------------------------------------------------------------------
header "OAP Ollama Compatibility Demo"
printf "OAP server: ${BOLD}%s${RESET}\n" "$OAP"
printf "Testing that standard Ollama API endpoints work through OAP,\n"
printf "with /api/chat adding automatic tool discovery + execution.\n"

# -------------------------------------------------------------------
header "1. Health check"
step "Verify OAP server is running"
cmd "curl -sf $OAP/health -H 'X-Backend-Token: ***'"
if health=$(curl -sf "$OAP/health" -H "X-Backend-Token: $TOKEN" 2>/dev/null); then
    ok "Server is up: $health"
else
    err "Server not reachable at $OAP (check URL and token)"
    printf "\nStart the OAP discovery service first:\n"
    printf "  source .venv/bin/activate && oap-api\n"
    exit 1
fi

# -------------------------------------------------------------------
header "2. GET /api/tags — List models"
step "Standard Ollama endpoint to list available models"
cmd "curl -s $OAP/api/tags | jq '.models[].name'"
run_curl "$OAP/api/tags"
if curl_ok; then
    models=$(echo "$CURL_BODY" | python3 -c "import sys,json; [print(m['name']) for m in json.loads(sys.stdin.read()).get('models',[])]" 2>/dev/null || echo "(parse error)")
    if [ -n "$models" ]; then
        ok "Models found:"
        echo "$models" | head -5 | while read -r m; do printf "    %s\n" "$m"; done
        total=$(echo "$models" | wc -l | tr -d ' ')
        [ "$total" -gt 5 ] && note "...and $((total - 5)) more"
    else
        err "No models returned"
    fi
else
    err "/api/tags failed (HTTP $CURL_CODE): $CURL_BODY"
fi

# -------------------------------------------------------------------
header "3. GET /api/ps — Loaded models"
step "Check which models are currently loaded in memory"
cmd "curl -s $OAP/api/ps | jq '.models[].name'"
run_curl "$OAP/api/ps"
if curl_ok; then
    loaded=$(echo "$CURL_BODY" | python3 -c "import sys,json; [print(m['name']) for m in json.loads(sys.stdin.read()).get('models',[])]" 2>/dev/null || echo "")
    if [ -n "$loaded" ]; then
        ok "Loaded models:"
        echo "$loaded" | while read -r m; do printf "    %s\n" "$m"; done
    else
        ok "No models currently loaded (they load on first request)"
    fi
else
    err "/api/ps failed (HTTP $CURL_CODE): $CURL_BODY"
fi

# -------------------------------------------------------------------
header "4. POST /api/show — Model info"
step "Get details about a specific model"
cmd "curl -s $OAP/api/show -d '{\"model\":\"qwen3:8b\"}' | jq '.details'"
run_curl "$OAP/api/show" -d '{"model":"qwen3:8b"}'
if curl_ok; then
    family=$(echo "$CURL_BODY" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()).get('details',{}); print(f\"{d.get('family','?')} {d.get('parameter_size','?')}\")" 2>/dev/null || echo "")
    if [ -n "$family" ]; then
        ok "Model info: $family"
    else
        ok "Response received (model may not be pulled)"
    fi
else
    err "/api/show failed (HTTP $CURL_CODE): $(echo "$CURL_BODY" | head -c 200)"
fi

# -------------------------------------------------------------------
header "5. POST /api/chat (non-streaming) — Tool bridge"
step "Send a task through /api/chat — OAP discovers tools and executes"
cmd "curl -s $OAP/api/chat -d '{\"model\":\"qwen3:8b\",\"messages\":[{\"role\":\"user\",\"content\":\"what is 42 * 17?\"}],\"stream\":false}'"
run_curl --max-time 120 "$OAP/api/chat" -H 'Content-Type: application/json' -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"what is 42 * 17?"}],"stream":false}'
if curl_ok; then
    content=$(echo "$CURL_BODY" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('message',{}).get('content','(empty)'))" 2>/dev/null || echo "(parse error)")
    tools_injected=$(echo "$CURL_BODY" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('oap_tools_injected','?'))" 2>/dev/null || echo "?")
    rounds=$(echo "$CURL_BODY" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('oap_round','?'))" 2>/dev/null || echo "?")
    ok "Response: $content"
    note "Tools injected: $tools_injected, rounds: $rounds"
else
    err "/api/chat non-streaming failed (HTTP $CURL_CODE): $(echo "$CURL_BODY" | head -c 200)"
fi

# -------------------------------------------------------------------
header "6. POST /api/chat (streaming) — NDJSON format"
step "Same request with stream=true — returns NDJSON like standard Ollama"
cmd "curl -s $OAP/api/chat -d '{\"model\":\"qwen3:8b\",\"messages\":[{\"role\":\"user\",\"content\":\"what is 6 + 7?\"}],\"stream\":true}'"
run_curl --max-time 120 "$OAP/api/chat" -H 'Content-Type: application/json' -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"what is 6 + 7?"}],"stream":true}'
if curl_ok; then
    line_count=$(echo "$CURL_BODY" | wc -l | tr -d ' ')
    has_done=$(echo "$CURL_BODY" | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    obj = json.loads(line)
    if obj.get('done'):
        print('yes')
        break
" 2>/dev/null || echo "no")
    if [ "$has_done" = "yes" ]; then
        ok "Streaming response: $line_count NDJSON lines with done sentinel"
        echo "$CURL_BODY" | head -2 | while read -r line; do
            printf "    %s\n" "$(echo "$line" | python3 -c "import sys; print(sys.stdin.read()[:120])" 2>/dev/null)"
        done
    else
        err "Streaming response missing done sentinel"
        note "Response: $(echo "$CURL_BODY" | head -c 200)"
    fi
else
    err "/api/chat streaming failed (HTTP $CURL_CODE): $(echo "$CURL_BODY" | head -c 200)"
fi

# -------------------------------------------------------------------
header "7. POST /api/generate — Pass-through"
step "Text generation passes through to Ollama directly (no tool bridge)"
cmd "curl -s $OAP/api/generate -d '{\"model\":\"qwen3:8b\",\"prompt\":\"Say hello in one word.\",\"stream\":false,\"options\":{\"num_ctx\":512}}'"
run_curl --max-time 60 "$OAP/api/generate" -d '{"model":"qwen3:8b","prompt":"Say hello in one word.","stream":false,"options":{"num_ctx":512}}'
if curl_ok; then
    gen_resp=$(echo "$CURL_BODY" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('response','(empty)')[:100])" 2>/dev/null || echo "(parse error)")
    ok "Generate response: $gen_resp"
else
    err "/api/generate failed (HTTP $CURL_CODE): $(echo "$CURL_BODY" | head -c 200)"
fi

# -------------------------------------------------------------------
header "8. Client integration"
step "Point any HTTP-based Ollama client at the OAP server"
note "Open WebUI:  OLLAMA_BASE_URL=$OAP"
note "LangChain:   ChatOllama(base_url=\"$OAP\")"
note "LlamaIndex:  Ollama(base_url=\"$OAP\")"
note "curl:        curl $OAP/api/chat -H 'Content-Type: application/json' -d '{...}'"
note ""
note "macOS: the ollama CLI talks to the desktop app via local socket,"
note "ignoring OLLAMA_HOST. Use HTTP clients instead."
note "Linux: OLLAMA_HOST=$OAP ollama run qwen3:8b"

# -------------------------------------------------------------------
header "Summary"
printf "  ${GREEN}Passed: %d${RESET}  ${RED}Failed: %d${RESET}\n\n" "$pass" "$fail"

if [ "$fail" -eq 0 ]; then
    printf "${GREEN}All tests passed!${RESET} The OAP server is a working drop-in Ollama replacement.\n\n"
    printf "To use with any HTTP-based Ollama client:\n"
    printf "  ${BOLD}OLLAMA_BASE_URL=%s${RESET}  # Open WebUI\n" "$OAP"
    printf "  ${BOLD}ChatOllama(base_url=\"%s\")${RESET}  # LangChain\n" "$OAP"
    printf "  ${BOLD}OLLAMA_HOST=%s ollama run qwen3:8b${RESET}  # Linux only\n\n" "$OAP"
else
    printf "${YELLOW}Some tests failed.${RESET} Check that OAP and Ollama are both running.\n\n"
fi
