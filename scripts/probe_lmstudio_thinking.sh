#!/usr/bin/env bash
# Probe a running LM Studio for a per-request thinking control that actually works.
#
# Usage: scripts/probe_lmstudio_thinking.sh [base_url] [model]
#   base_url defaults to http://127.0.0.1:1234; the model defaults to the single
#   served model, or set MODEL=.
#
# LM Studio Bionic 1.2.0 measured 2026-11-15: reasoning_effort "none" disables thinking,
# "off" answers HTTP 400, and chat_template_kwargs, enable_thinking, and reasoning are all
# accepted but inert. This script re-checks every candidate after an LM Studio update: it
# streams the same short prompt once per candidate field and prints which variants produced
# visible output without any reasoning content. Exits 0 if at least one control worked.
# Measured thinking is on by default; a working "none" makes "high" worth checking too.
set -euo pipefail

base=${1:-http://127.0.0.1:1234}
base=${base%/}
model=${2:-${MODEL:-}}

python3 - "$base" "$model" <<'PY'
import json
import sys
import urllib.request

base, model = sys.argv[1], sys.argv[2]


def open_request(path, body, timeout=180):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    return urllib.request.urlopen(request, timeout=timeout)


if not model:
    with open_request("/v1/models", None, 10) as response:
        listed = json.load(response)["data"]

    def is_served(entry):
        status = entry.get("status")
        return (
            isinstance(status, dict) and status.get("value") == "loaded"
            or "max_model_len" in entry
            or entry.get("n_ctx") is not None
        )

    ids = [entry["id"] for entry in listed if is_served(entry)]
    if len(ids) != 1:
        sys.exit(
            "could not determine the served model ("
            + ", ".join(entry["id"] for entry in listed)
            + "); pass it as the second argument or set MODEL="
        )
    model = ids[0]

VARIANTS = [
    ("control (no thinking field)", {}),
    ('reasoning_effort "none"', {"reasoning_effort": "none"}),
    ('reasoning_effort "off"', {"reasoning_effort": "off"}),
    ('reasoning_effort "high"', {"reasoning_effort": "high"}),
    ("top-level enable_thinking false", {"enable_thinking": False}),
    ("chat_template_kwargs enable_thinking false", {"chat_template_kwargs": {"enable_thinking": False}}),
    ("chat_template_kwargs reasoning_effort none", {"chat_template_kwargs": {"reasoning_effort": "none"}}),
    ("chat_template_kwargs thinking_turn false", {"chat_template_kwargs": {"thinking_turn": False}}),
    ("chat_template_kwargs reasoning false", {"chat_template_kwargs": {"reasoning": False}}),
    ('top-level reasoning "off"', {"reasoning": "off"}),
]


def stream_counts(extra):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
        "max_tokens": 48,
        "temperature": 0.0,
        "stream": True,
        **extra,
    }
    reasoning = visible = 0
    with open_request("/v1/chat/completions", body) as response:
        for raw in response:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[len("data:"):].strip()
            if chunk == "[DONE]":
                break
            try:
                delta = json.loads(chunk)["choices"][0].get("delta", {})
            except (KeyError, IndexError, ValueError):
                continue
            reasoning += len(delta.get("reasoning_content") or "")
            visible += len(delta.get("content") or "")
    return reasoning, visible


print(f"probing {base} model {model}")
working: list[tuple[str, dict]] = []
for name, extra in VARIANTS:
    try:
        reasoning, visible = stream_counts(extra)
    except Exception as error:  # variants must not abort the probe
        print(f"  {name:52s} request failed: {error}")
        continue
    if reasoning and not visible:
        verdict = f"thinking still ON ({reasoning} reasoning chars, no visible text)"
    elif reasoning and visible:
        verdict = f"thinking ON, late answer ({reasoning} reasoning, {visible} visible chars)"
    elif visible:
        verdict = f"thinking OFF candidate ({visible} visible chars, no reasoning content)"
        working.append((name, extra))
    else:
        verdict = "no output at all"
    print(f"  {name:52s} {verdict}")

pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="  # 1x1 opaque red PNG
vision_extra = working[0][1] if working else {}
vision_body = {
    "model": model,
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "What color is this single-pixel image? Answer in one word."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{pixel}"}},
        ],
    }],
    "max_tokens": 32,
    "temperature": 0.0,
    **vision_extra,
}
try:
    with open_request("/v1/chat/completions", vision_body) as response:
        message = json.load(response)["choices"][0]["message"]
    answer = message.get("content")
    note = f" (with {working[0][0]} applied)" if working else ""
    if answer:
        print(f"\nvision: answered {str(answer)[:80]!r}{note} — the image is one opaque red pixel")
    else:
        print(f"\nvision: empty visible answer{note} — vision may be unsupported")
except Exception as error:
    print(f"\nvision: request failed: {error}")

if working:
    print("\nworking per-request controls (add one to --request-extra and record it in the recipe):")
    for name, _ in working:
        print(f"  {name}")
else:
    print("\nno per-request control disabled thinking on this build; use the app's model settings and update this probe after an LM Studio update")
sys.exit(0 if working else 1)
PY
