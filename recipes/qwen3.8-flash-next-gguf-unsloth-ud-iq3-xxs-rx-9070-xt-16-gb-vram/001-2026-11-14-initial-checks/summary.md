# 001 · 2026-11-14 — Initial text, tool, vision, and long-context checks

## Workload

Four sequential `check_generation.py` modes produced five generation requests: streamed Python code, a forced tool call and its follow-up, a screenshot description, and synthetic service records near 120K input tokens. The server identified the model as `qwen3.8-flash-next-ud-iq3_xxs` in the non-streamed responses.

Requests used temperature 0 and disabled thinking. Text, tools, and vision allowed 256 output tokens; long context allowed 128. These are check-request settings. The profile records the recipe's configured software and serving defaults; the actual launch context and build identities were not included in these outputs.

## Results

| Request | Workload | Input tokens | Output tokens | Prefill time (s) | Prefill tok/s | Generation time (s) | Generation tok/s | Accepted / proposed drafts |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| #1 | Streamed text | 24 | 120 | — | — | — | — | — |
| #2 | Tool call | 286 | 19 | 0.7742 | 369.4 | 0.2511 | 75.7 | 13 / 17 (76.5%) |
| #3 | Tool result follow-up | 81 | 12 | 0.3410 | 237.5 | 0.2088 | 57.5 | 6 / 15 (40.0%) |
| #4 | Screenshot description | 1,079 | 256 | 0.8878 | 1,215.4 | 2.5551 | 100.2 | 172 / 222 (77.5%) |
| #5 | Synthetic service records | 119,986 | 128 | — | — | — | — | — |

Times and rates in the table are server-reported; milliseconds were converted to seconds. Missing entries were not returned by the streamed text collector or the long check's Anthropic response. Total generated output was **535 tokens**. Every request reported zero reused input tokens.

| Check | Client elapsed time (s) | Scope |
|---|---:|---|
| Text | 1.547 | Streamed request |
| Tools | 1.581 | Both requests in the round trip |
| Vision | 10.253 | Image request, including encoding and other overhead |
| Long context | 38.394 | Generation HTTP request |
| Long context, including token counting | 39.282 | Complete check |

The long request's usage was 1 input token plus 119,985 cache-creation tokens and zero cache-read tokens, matching the tokenizer's 119,986-token count. Its HTTP duration includes both prefill and generation; separate speeds cannot be derived from this response.

## Observations

- Streamed text completed and returned an order-preserving deduplication function using a set. The function accepts hashable elements; generated code was not executed by the check.
- The tool check returned `get_temperature` with `city: Belgrade`, then correctly reported the supplied 17°C result. Tool selection was forced by the request.
- The vision response described a `gpu-switcher` window and transcribed GPU options and a status message. The description and transcribed text were manually checked against the input screenshot and confirmed accurate. The answer stopped at the 256-token limit.
- The long request completed with 119,986 input tokens. Its 128-token output cap truncated the function before completion. This demonstrates long-input processing, rather than retrieval accuracy or completed-code correctness.
- Draft counters confirm speculative decoding on the tool and vision requests. Their combined acceptance was 191 / 254 proposals (75.2%); individual rates are listed above.

## Comparison with ISTA

The [ISTA initial check](../../qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram/001-2026-11-12-initial-checks/summary.md) processed 119,999 input tokens with the same 128-token output cap in 38.88 seconds. This Unsloth request took 38.39 seconds, about 1.2% less. These are single requests with slightly different prompts, not evidence of a sustained speed improvement.

The vision input differs from ISTA's screenshot, so those request times and answer quality are not directly comparable. These checks establish initial functionality; a representative coding workload is needed to compare practical quality.

## Memory

RAM, VRAM, and swap measurements were not captured with these outputs. The recipe's capacity estimates are not measurements from this run.

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)
