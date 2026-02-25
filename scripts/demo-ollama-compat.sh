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
ok()     { printf "${GREEN}  ✓ %s${RESET}\n" "$1"; ((pass++)); }
err()    { printf "${RED}  ✗ %s${RESET}\n" "$1"; ((fail++)); }
note()   { printf "${YELLOW}  → %s${RESET}\n" "$1"; }

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
if tags=$(curl -sf "$OAP/api/tags" 2>/dev/null); then
    models=$(echo "$tags" | python3 -c "import sys,json; [print(m['name']) for m in json.loads(sys.stdin.read()).get('models',[])]" 2>/dev/null || echo "(parse error)")
    if [ -n "$models" ]; then
        ok "Models found:"
        echo "$models" | head -5 | while read -r m; do printf "    %s\n" "$m"; done
        total=$(echo "$models" | wc -l | tr -d ' ')
        [ "$total" -gt 5 ] && note "...and $((total - 5)) more"
    else
        err "No models returned"
    fi
else
    err "/api/tags failed"
fi

# -------------------------------------------------------------------
header "3. GET /api/ps — Loaded models"
step "Check which models are currently loaded in memory"
cmd "curl -s $OAP/api/ps | jq '.models[].name'"
if ps=$(curl -sf "$OAP/api/ps" 2>/dev/null); then
    loaded=$(echo "$ps" | python3 -c "import sys,json; [print(m['name']) for m in json.loads(sys.stdin.read()).get('models',[])]" 2>/dev/null || echo "")
    if [ -n "$loaded" ]; then
        ok "Loaded models:"
        echo "$loaded" | while read -r m; do printf "    %s\n" "$m"; done
    else
        ok "No models currently loaded (they load on first request)"
    fi
else
    err "/api/ps failed"
fi

# -------------------------------------------------------------------
header "4. POST /api/show — Model info"
step "Get details about a specific model"
cmd "curl -s $OAP/api/show -d '{\"name\":\"qwen3:8b\"}' | jq '.details'"
if show=$(curl -sf "$OAP/api/show" -d '{"name":"qwen3:8b"}' 2>/dev/null); then
    family=$(echo "$show" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()).get('details',{}); print(f\"{d.get('family','?')} {d.get('parameter_size','?')}\")" 2>/dev/null || echo "")
    if [ -n "$family" ]; then
        ok "Model info: $family"
    else
        ok "Response received (model may not be pulled)"
    fi
else
    err "/api/show failed (is qwen3:8b pulled?)"
fi

# -------------------------------------------------------------------
header "5. POST /api/chat (non-streaming) — Tool bridge"
step "Send a task through /api/chat — OAP discovers tools and executes"
cmd "curl -s $OAP/api/chat -d '{\"model\":\"qwen3:8b\",\"messages\":[{\"role\":\"user\",\"content\":\"what is 42 * 17?\"}],\"stream\":false}'"
if chat=$(curl -sf "$OAP/api/chat" -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"what is 42 * 17?"}],"stream":false}' --max-time 120 2>/dev/null); then
    content=$(echo "$chat" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('message',{}).get('content','(empty)'))" 2>/dev/null || echo "(parse error)")
    tools_injected=$(echo "$chat" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('oap_tools_injected','?'))" 2>/dev/null || echo "?")
    rounds=$(echo "$chat" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('oap_round','?'))" 2>/dev/null || echo "?")
    ok "Response: $content"
    note "Tools injected: $tools_injected, rounds: $rounds"
else
    err "/api/chat non-streaming failed"
fi

# -------------------------------------------------------------------
header "6. POST /api/chat (streaming) — NDJSON format"
step "Same request with stream=true — returns NDJSON like standard Ollama"
cmd "curl -s $OAP/api/chat -d '{\"model\":\"qwen3:8b\",\"messages\":[{\"role\":\"user\",\"content\":\"what is 6 + 7?\"}],\"stream\":true}'"
if stream_out=$(curl -sf "$OAP/api/chat" -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"what is 6 + 7?"}],"stream":true}' --max-time 120 2>/dev/null); then
    line_count=$(echo "$stream_out" | wc -l | tr -d ' ')
    has_done=$(echo "$stream_out" | python3 -c "
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
        echo "$stream_out" | head -2 | while read -r line; do
            printf "    %s\n" "$(echo "$line" | python3 -c "import sys; print(sys.stdin.read()[:120])" 2>/dev/null)"
        done
    else
        err "Streaming response missing done sentinel"
    fi
else
    err "/api/chat streaming failed"
fi

# -------------------------------------------------------------------
header "7. POST /api/generate — Pass-through"
step "Text generation passes through to Ollama directly (no tool bridge)"
cmd "curl -s $OAP/api/generate -d '{\"model\":\"qwen3:8b\",\"prompt\":\"Say hello in one word.\",\"stream\":false,\"options\":{\"num_ctx\":512}}'"
if gen=$(curl -sf "$OAP/api/generate" -d '{"model":"qwen3:8b","prompt":"Say hello in one word.","stream":false,"options":{"num_ctx":512}}' --max-time 60 2>/dev/null); then
    gen_resp=$(echo "$gen" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('response','(empty)')[:100])" 2>/dev/null || echo "(parse error)")
    ok "Generate response: $gen_resp"
else
    err "/api/generate failed"
fi

# -------------------------------------------------------------------
header "8. Ollama CLI integration"
step "The ollama CLI uses OLLAMA_HOST to connect to a custom server"
note "OLLAMA_HOST=$OAP ollama run qwen3:8b \"what is 2+2?\""
note "OLLAMA_HOST=$OAP ollama list"
note "(Not run automatically — requires interactive terminal)"

# -------------------------------------------------------------------
header "Summary"
printf "  ${GREEN}Passed: %d${RESET}  ${RED}Failed: %d${RESET}\n\n" "$pass" "$fail"

if [ "$fail" -eq 0 ]; then
    printf "${GREEN}All tests passed!${RESET} The OAP server is a working drop-in Ollama replacement.\n\n"
    printf "To use with any Ollama client:\n"
    printf "  ${BOLD}OLLAMA_HOST=%s ollama run qwen3:8b${RESET}\n" "$OAP"
    printf "  ${BOLD}OLLAMA_BASE_URL=%s  # Open WebUI${RESET}\n" "$OAP"
    printf "  ${BOLD}OLLAMA_API_BASE_URL=%s  # chatbot-ui${RESET}\n\n" "$OAP"
else
    printf "${YELLOW}Some tests failed.${RESET} Check that OAP and Ollama are both running.\n\n"
fi
