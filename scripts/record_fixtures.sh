#!/usr/bin/env bash
# Record real HTTP response fixtures for one API server into tests/fixtures/<server>/.
#
# Run exactly one server at a time; only one model fits on the GPU. Start the
# server first, then run this script. It needs only curl and python3.
#
#   scripts/record_fixtures.sh strata      # default http://127.0.0.1:8080
#   scripts/record_fixtures.sh tabbyapi    # default http://127.0.0.1:5000
#   scripts/record_fixtures.sh lmstudio    # default http://127.0.0.1:1234
#   scripts/record_fixtures.sh <server> <base-url>   # custom port
#
# Container recipes (run from a terminal; Strata loads for 1-3 minutes):
#   sudo python3 scripts/launch.py start qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram
#   sudo python3 scripts/launch.py start qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
#   python3 scripts/launch.py ps                      # instance names
#   sudo python3 scripts/launch.py stop <instance>    # free the GPU before the next server
# LM Studio: open the app, load the recipe's model, start the developer server.
#
# The served model id comes from /v1/models; override with MODEL=<id>.
# If the server requires an API key, export API_KEY=<token> first.
# Captures overwrite files in tests/fixtures/<server>/. Before committing,
# review `git diff` and remove anything personal; keep files small.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

die() {
    echo "error: $*" >&2
    exit 1
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "usage: $0 <strata|tabbyapi|lmstudio> [base-url]" >&2
    exit 2
fi
kind=$1
case $kind in
    strata) base=${2:-http://127.0.0.1:8080} ;;
    tabbyapi) base=${2:-http://127.0.0.1:5000} ;;
    lmstudio) base=${2:-http://127.0.0.1:1234} ;;
    *) die "unknown server '$kind' (expected strata, tabbyapi, or lmstudio)" ;;
esac
base=${base%/}
out=tests/fixtures/$kind
mkdir -p "$out"

auth=()
if [[ -n ${API_KEY:-} ]]; then
    auth=(-H "Authorization: Bearer $API_KEY")
fi

warnings=()
warn() {
    warnings+=("$*")
    echo "warn: $*" >&2
}

# Send a request and echo the HTTP status code; the body is always saved.
# Usage: status=$(send <body-file> <method> <path> <body> [stream])
send() {
    local file=$1 method=$2 path=$3 body=$4 stream=${5:-}
    local args=(-sS -o "$file" -w '%{http_code}' -X "$method"
        -H "Content-Type: application/json" "${auth[@]}" "$base$path")
    if [[ -n $body ]]; then
        args+=(-d "$body")
    fi
    if [[ -n $stream ]]; then
        args+=(-N --max-time 300)
    else
        args+=(--max-time 30)
    fi
    curl "${args[@]}"
}

echo "== $kind fixtures: $base =="

# 1. models.json — also the reachability preflight and the source of the model id.
headers=$(mktemp)
trap 'rm -f "$headers"' EXIT
if ! status=$(curl -sS -o "$out/models.json" -D "$headers" -w '%{http_code}' \
    --max-time 30 "${auth[@]}" "$base/v1/models"); then
    die "cannot reach $base — is the $kind server running? For containers see scripts/launch.py"
fi
[[ $status == 2* ]] || die "GET /v1/models returned $status; see $out/models.json"
model=${MODEL:-}
if [[ -z $model ]]; then
    model=$(python3 - "$out/models.json" <<'PY'
import json, sys

def is_served(entry):
    """A loaded model reports a runtime context; draft or catalog entries report nulls."""
    if (entry.get("status") or {}).get("value") == "loaded":
        return True
    meta = entry.get("meta") or {}
    parameters = entry.get("parameters") or {}
    return any(v is not None for v in (entry.get("max_model_len"), meta.get("n_ctx"),
                                       parameters.get("n_ctx")))

served = [m["id"] for m in json.load(open(sys.argv[1])).get("data", [])
          if m.get("id") and is_served(m)]
if len(served) != 1:
    sys.exit(f"{len(served)} served candidates: {served or 'none'}")
print(served[0])
PY
) || die "could not determine the served model uniquely from $out/models.json; set MODEL=<id> and rerun. LM Studio lists every downloaded model without a loaded flag, so it needs MODEL= explicitly."
fi
[[ -n $model ]] || die "empty model id; set MODEL=<id> and rerun"
echo "model: $model"
if [[ -n ${MODEL:-} ]]; then
    echo "(using MODEL override; verify /v1/models lists it)"
fi

# The same request fields the baseline runner sends (workloads.request_payload
# with the FUNCTIONAL policy), so fixtures exercise the real request shape.
samplers='"temperature":0.0,"top_k":20,"top_p":0.95,"min_p":0.0,"repetition_penalty":1.0,"presence_penalty":0.0'
if [[ $kind == strata ]]; then
    limit_field=max_completion_tokens
    thinking=',"reasoning_effort":"none"'
else
    limit_field=max_tokens
    thinking=
fi

# 2. stream.sse — small streamed completion with usage in the final chunk.
stream_body="{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hi.\"}],\"$limit_field\":8,$samplers$thinking,\"stream\":true,\"stream_options\":{\"include_usage\":true}}"
status=$(send "$out/stream.sse" POST /v1/chat/completions "$stream_body" stream) ||
    die "the streaming request to $base failed to complete"
[[ $status == 2* ]] || die "POST /v1/chat/completions (stream) returned $status; see $out/stream.sse"
[[ -s "$out/stream.sse" ]] || die "$out/stream.sse is empty"
grep -q '^data:' "$out/stream.sse" || die "$out/stream.sse has no SSE 'data:' lines; is $kind streaming?"
grep -qi 'data: *\[' "$out/stream.sse" || warn "stream.sse has no terminal 'data: [DONE]' frame; record the server's end-of-stream framing in the README"

# 3. tools.sse — forced tool-call stream (functional.TOOLS / TOOL_CHOICE), with a
# non-streamed fallback because streaming tool-call support varies by server.
tools_schema='"tools":[{"type":"function","function":{"name":"get_temperature","description":"Read a city temperature.","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"],"additionalProperties":false}}}]'
tools_choice='"tool_choice":{"type":"function","function":{"name":"get_temperature"}}'
tools_messages='"messages":[{"role":"user","content":"Use get_temperature for Belgrade, then report its returned temperature."}]'
# LM Studio accepts only the string tool_choice values none, auto, and required.
if [[ $kind == lmstudio ]]; then
    tools_choice='"tool_choice":"required"'
else
    tools_choice='"tool_choice":{"type":"function","function":{"name":"get_temperature"}}'
fi
tools_base="{\"model\":\"$model\",$tools_messages,\"$limit_field\":256,$samplers$thinking,$tools_schema,$tools_choice"
tools_body="$tools_base,\"stream\":true,\"stream_options\":{\"include_usage\":true}}"
status=$(send "$out/tools.sse" POST /v1/chat/completions "$tools_body" stream) ||
    warn "the forced tool-call stream request failed to complete"
if [[ ${status:-0} != 2* ]]; then
    warn "tool-call stream returned ${status:-curl error}"
fi
if [[ ${status:-0} == 2* ]] && ! grep -q '"tool_calls"' "$out/tools.sse"; then
    warn "tools.sse carries no tool_calls frame; capturing the non-streamed variant too"
    status=$(send "$out/tools.json" POST /v1/chat/completions "$tools_base}") ||
        warn "the non-streamed tool-call request failed too"
    if [[ ${status:-0} != 2* ]] || ! grep -q '"tool_calls"' "$out/tools.json"; then
        warn "this server did not produce a forced tool call; record it as a capability gap"
    fi
fi

# 4. error.json + error.status — unknown model must be rejected, not answered.
error_body='{"model":"missing-model","messages":[{"role":"user","content":"x"}]}'
status=$(send "$out/error.json" POST /v1/chat/completions "$error_body") ||
    die "the unknown-model request failed to complete; a server error page was expected, not a curl failure"
echo "$status" > "$out/error.status"
if [[ $status == 2* ]]; then
    warn "the server ACCEPTED an unknown model (HTTP $status); capture is saved anyway as evidence"
fi

# 5. Token-count route, where the server has one.
count_text='Hello, how are you?'
case $kind in
    strata)
        body="{\"model\":\"$model\",\"max_tokens\":1,\"messages\":[{\"role\":\"user\",\"content\":\"$count_text\"}]}"
        status=$(send "$out/count_tokens.json" POST /v1/messages/count_tokens "$body") ||
            die "POST /v1/messages/count_tokens failed to complete"
        if [[ $status != 2* ]] || ! grep -Eq '"input_tokens"[[:space:]]*:[[:space:]]*[0-9]' "$out/count_tokens.json"; then
            warn "count_tokens.json status $status has no integer input_tokens; check the route manually"
        fi
        token_note="/v1/messages/count_tokens -> $status"
        ;;
    tabbyapi)
        body="{\"text\":[{\"role\":\"user\",\"content\":\"$count_text\"}],\"template_vars\":{}}"
        status=$(send "$out/token_encode.json" POST /v1/token/encode "$body") ||
            die "POST /v1/token/encode failed to complete"
        if [[ $status != 2* ]] || ! grep -Eq '"length"[[:space:]]*:[[:space:]]*[0-9]' "$out/token_encode.json"; then
            warn "token_encode.json status $status has no integer length; check the route manually"
        fi
        token_note="/v1/token/encode -> $status"
        ;;
    lmstudio)
        # No documented tokenize route; probe plausible ones and record the outcome.
        attempts=()
        body_text="{\"text\":[{\"role\":\"user\",\"content\":\"$count_text\"}],\"template_vars\":{}}"
        body_count="{\"model\":\"$model\",\"max_tokens\":1,\"messages\":[{\"role\":\"user\",\"content\":\"$count_text\"}]}"
        body_v0="{\"model\":\"$model\",\"text\":\"$count_text\"}"
        for route_body in "/v1/token/encode:$body_text" "/v1/messages/count_tokens:$body_count" "/api/v0/tokenize:$body_v0"; do
            route=${route_body%%:*}
            body=${route_body#*:}
            if status=$(send "$out/.probe" POST "$route" "$body"); then
                if [[ $status == 2* ]] && ! grep -qiE '"(error|not found)"' "$out/.probe"; then
                    mv "$out/.probe" "$out/token_count.json"
                    token_note="$route -> $status (saved as token_count.json)"
                    break
                fi
                attempts+=("$route -> $status; body: $(head -c 160 "$out/.probe" | tr -d '\r\n')")
            else
                attempts+=("$route -> curl error")
            fi
        done
        rm -f "$out/.probe"
        if [[ ! -e "$out/token_count.json" ]]; then
            printf 'No token-count route answered with a usable response.\nAttempts:\n%s\n' "$(printf '  %s\n' "${attempts[@]}")" \
                > "$out/token_count.unavailable.txt"
            token_note="unavailable (${attempts[*]})"
        fi
        ;;
esac

# 6. capture.txt — the server identity note required beside recorded fixtures.
{
    echo "server kind: $kind"
    echo "base url: $base"
    echo "model id: $model"
    echo "captured (UTC): $(date -u '+%Y-%m-%d %H:%M:%S')"
    echo "client: $(curl --version | head -1)"
    echo "token-count route: ${token_note:-not recorded}"
    echo
    echo "GET /v1/models response headers:"
    cat "$headers"
    echo
    echo "Add here: engine and server version, image digest or app build."
} > "$out/capture.txt"

echo
printf 'captured into %s/:\n' "$out"
find "$out" -maxdepth 1 -type f -printf '  %s  %f\n' | sort -k2
if ((${#warnings[@]})); then
    echo
    echo "ATTENTION (${#warnings[@]} warning(s) above); the run still saved partial captures." >&2
    exit 1
fi
echo
echo "Next: 1) review 'git diff -- $out' and delete anything personal"
echo "      2) bash scripts/check.sh"
echo "      3) note the server/engine version in tests/fixtures/README.md and commit"
