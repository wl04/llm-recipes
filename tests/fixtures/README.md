# Response fixtures

Each directory holds one server's responses for the baseline request handling tests.

| Directory | Status |
|---|---|
| `synthetic-openai/` | Hand-built from the OpenAI chat-completions format. It exercises the parser; it is not a capture of any real server. |
| `tabbyapi/` | Captured completion log summaries from ExLlamaV3 1.6.6 / TabbyAPI revision `8f92fac5d9307bf1e09668c3715b32ff46ad0333`. In `completions.log` startup paths and timestamps are removed; `completions.timestamped.log` is the same summaries rebuilt with synthetic even-spaced line timestamps plus one start/cancel pair, for the session-report parser. A real snapshot is possible with `LOG=<path> scripts/record_fixtures.sh tabbyapi`. HTTP responses captured 2026-11-15 by `scripts/record_fixtures.sh` from the loaded target `qwen3.8-27b-exl3-3bpw`: streamed text and forced tool calls, `/v1/models`, `token/encode` (chat-template ids and `length`). `/v1/models` lists the draft directories too, but only the loaded target reports a runtime context and a nonzero size. This server also accepts unknown model ids with HTTP 200. |
| `strata/` | Captured 2026-11-14 with `scripts/record_fixtures.sh` from `llm-recipes/strata-rdna4:probe` / Strata engine 0.1.59.1, revision `dbb2d168`. Includes streamed text, forced tool-call stream, `/v1/models`, and `count_tokens`. See `strata/capture.txt`: this server accepts unknown model ids with HTTP 200, and `models.json` confirms `n_ctx` 131072 with text+image input. |
| `lmstudio/` | Captured 2026-11-15 with `scripts/record_fixtures.sh` from LM Studio Bionic 1.2.0 (build 2), model `qwen3.8-27b-gsq-rco`. Streamed text, `/v1/models`, unknown model accepted with HTTP 200. No token-count route: `/v1/token/encode`, `/v1/messages/count_tokens`, and `/api/v0/tokenize` all answer HTTP 200 with error bodies (see `lmstudio/token_count.unavailable.txt`). Object `tool_choice` is rejected (`Invalid tool_choice type`; only `none`, `auto`, `required` are supported); with `tool_choice: "required"` the forced tool-call stream captured correctly. Live probe 2026-11-15: `reasoning_effort: "none"` disables the template's default thinking (`"off"` answers HTTP 400; `chat_template_kwargs`, `enable_thinking`, and `reasoning` are accepted but inert), `"high"` produces reasoning, and with the adapter `mmproj-Qwen3.8-27B-BF16.gguf` loaded the API answers a 1×1 red-pixel vision question correctly. Captured 2026-11-15 13:32 UTC with `reasoning_effort: none`: streams carry visible `content` and the usage chunk reports `reasoning_tokens: 0`. Re-check candidates with `scripts/probe_lmstudio_thinking.sh` after app updates. |

`test_baseline_fixtures.py` parses every `*/stream.sse`, so a recorded capture named `stream.sse` is tested without changing code. Keep recorded files small (a few output tokens) and remove anything personal. Qwen-based servers can spend a small output budget entirely on reasoning: in the `tabbyapi/` capture `content` is empty while `reasoning` is non-empty, and the reader exposes them separately. The reader accepts either channel.

## Recording a server

Start one server at a time (only one model fits on the GPU), then run the
recording script. It needs only `curl` and `python3`; server start and stop
commands are in its header:

```bash
scripts/record_fixtures.sh tabbyapi    # ExLlamaV3 container, port 5000
scripts/record_fixtures.sh strata      # Strata container, port 8080
MODEL=qwen3.8-27b-gsq-rco scripts/record_fixtures.sh lmstudio   # developer server, port 1234
scripts/record_fixtures.sh <server> <base-url>   # custom port; MODEL/API_KEY env override
```

The script discovers the served model through `/v1/models`: the single entry
that reports a runtime context (`status.value: loaded`, `max_model_len`, or a
non-null `n_ctx`). TabbyAPI lists the draft directories too, but only the
loaded target carries a context and size. LM Studio lists every downloaded
model with no loaded flag, so it needs `MODEL=<id>` explicitly. The script
records `models.json`, `stream.sse`, `tools.sse` (the runner's forced tool-call
stream — LM Studio only accepts the string `tool_choice` values, so the script
sends `"required"` there — with a non-streamed `tools.json` fallback),
`error.json` plus `error.status`, the token-count response where the server has
one, and `capture.txt` with the date, model id, and response headers for the
version note. It uses the runner's
request shape (`max_completion_tokens` and `reasoning_effort` for Strata) and
verifies every capture: SSE framing, a terminal `data: [DONE]`, a present tool
call, the unknown-model probe result, and an integer token count. Unexpected
behavior is saved as evidence and reported as a warning (non-zero exit).
Review `git diff`, add the version to `capture.txt` and the table above, then
run `bash scripts/check.sh`. A rerun rewrites `capture.txt`, so restate the
version and behavior notes after each recapture (the table above keeps a
summary).
