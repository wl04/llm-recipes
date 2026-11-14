# Response fixtures

Each directory holds one server's responses for the baseline request handling tests.

| Directory | Status |
|---|---|
| `synthetic-openai/` | Hand-built from the OpenAI chat-completions format. It exercises the parser; it is not a capture of any real server. |
| `tabbyapi/` | Captured completion log summaries from ExLlamaV3 1.6.6 / TabbyAPI revision `8f92fac5d9307bf1e09668c3715b32ff46ad0333`. Startup paths and timestamps removed. HTTP responses captured 2026-11-15 by `scripts/record_fixtures.sh` (served model `qwen3.8-27b-dflash2-exl3-3bpw`; note the image tag in `tabbyapi/capture.txt`): streamed text and forced tool calls, `/v1/models`, `token/encode` (chat-template ids and `length`). This server also accepts unknown model ids with HTTP 200. |
| `strata/` | Captured 2026-11-14 with `scripts/record_fixtures.sh` from `llm-recipes/strata-rdna4:probe` / Strata engine 0.1.59.1, revision `dbb2d168`. Includes streamed text, forced tool-call stream, `/v1/models`, and `count_tokens`. See `strata/capture.txt`: this server accepts unknown model ids with HTTP 200, and `models.json` confirms `n_ctx` 131072 with text+image input. |
| `lmstudio/` | Captured 2026-11-15 with `scripts/record_fixtures.sh` (model `qwen3.8-27b-gsq-rco`). Streamed text, `/v1/models`, unknown model accepted with HTTP 200. No token-count route: `/v1/token/encode`, `/v1/messages/count_tokens`, and `/api/v0/tokenize` all answer HTTP 200 with error bodies (see `lmstudio/token_count.unavailable.txt`). Object `tool_choice` is rejected (`Invalid tool_choice type`; only `none`, `auto`, `required` are supported), so the tool-call capture needs a rerun with the current script. |

`test_baseline_fixtures.py` parses every `*/stream.sse`, so a recorded capture named `stream.sse` is tested without changing code. Keep recorded files small (a few output tokens) and remove anything personal. Qwen-based servers can spend a small output budget entirely on reasoning: in the `tabbyapi/` and `lmstudio/` captures `content` is empty while `reasoning` is non-empty, and the reader exposes them separately.

## Recording a server

Start one server at a time (only one model fits on the GPU), then run the
recording script. It needs only `curl` and `python3`; server start and stop
commands are in its header:

```bash
scripts/record_fixtures.sh tabbyapi    # ExLlamaV3 container, port 5000
scripts/record_fixtures.sh strata      # Strata container, port 8080
scripts/record_fixtures.sh lmstudio    # LM Studio developer server, port 1234
scripts/record_fixtures.sh <server> <base-url>   # custom port; MODEL/API_KEY env override
```

The script discovers the served model through `/v1/models` and records
`models.json`, `stream.sse`, `tools.sse` (the runner's forced tool-call stream,
with a non-streamed `tools.json` fallback), `error.json` plus `error.status`,
the token-count response where the server has one, and `capture.txt` with the
date, model id, and response headers for the version note. It uses the runner's
request shape (`max_completion_tokens` and `reasoning_effort` for Strata) and
verifies every capture: SSE framing, a terminal `data: [DONE]`, a present tool
call, rejection of the unknown model, and an integer token count. Unexpected
behavior is saved as evidence and reported as a warning (non-zero exit).
Review `git diff`, add the version to `capture.txt` and the table above, then
run `bash scripts/check.sh`.
