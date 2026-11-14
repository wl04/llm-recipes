# Response fixtures

Each directory holds one server's responses for the baseline request handling tests.

| Directory | Status |
|---|---|
| `synthetic-openai/` | Hand-built from the OpenAI chat-completions format. It exercises the parser; it is not a capture of any real server. |
| `tabbyapi/` | Captured completion log summaries from ExLlamaV3 1.6.6 / TabbyAPI revision `8f92fac5d9307bf1e09668c3715b32ff46ad0333`. Startup paths and timestamps removed. HTTP response captures remain pending. |
| `strata/`, `lmstudio/` | Not recorded yet. Record them during the workstation pilot (stage 3). |

`test_baseline_fixtures.py` parses every `*/stream.sse`, so a recorded capture named `stream.sse` is tested without changing code. Keep recorded files small (a few output tokens) and remove anything personal.

## Recording a server

Run the server with the recipe's settings, then capture with `curl`. Replace the port and model:

```bash
base=http://127.0.0.1:8080
model=<served-model-id>
out=tests/fixtures/<server>
mkdir -p "$out"
curl -sN "$base/v1/chat/completions" -H 'Content-Type: application/json' \
  -d "{\"model\":\"$model\",\"stream\":true,\"stream_options\":{\"include_usage\":true},\"max_tokens\":8,\"messages\":[{\"role\":\"user\",\"content\":\"Say hi.\"}]}" > "$out/stream.sse"
curl -s "$base/v1/models" > "$out/models.json"
curl -s "$base/v1/chat/completions" -H 'Content-Type: application/json' \
  -d '{"model":"missing-model","messages":[{"role":"user","content":"x"}]}' > "$out/error.json"
```

Also capture the server's token-count route where it has one (Strata `POST /v1/messages/count_tokens`; TabbyAPI and LM Studio to be confirmed) and a forced tool-call stream. Note the server version beside the files.
