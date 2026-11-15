# 001 · 2026-11-15 — Baseline

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

Suite v2 · run complete · model `qwen3.8-27b-gsq-rco` · configured context 131,072 tokens

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 474 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 30 min |
| RAM used / total (GB) | 4.4 / 59.2 |
| Swap used / total (GB) | 0.3 / 8.0 |
| GPU busy (%) | 0 |
| VRAM used / total (GB) | 0.2 / 15.9 |
| GPU power (W) | 5.00 |
| GPU temperature (°C) | 35 |

Warmup: 4 requests, converged, 4.77 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output (s) | Prefill (tok/s) | Decode (tok/s) | First visible (s) | Reasoning chars | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 7,926 | 1,024 | — | 7.05 | — | 63.98 | — | — | — | length (3), stop (2) |
| sustained-lru-cache | insufficient_sample | 1 | 63 | 138 | — | 0.262 | — | 77.53 | — | — | — | stop |
| sustained-tokenizer | ok | 1 | 60 | 2,048 | — | 0.194 | — | 82.66 | — | — | — | length |
| sustained-event-store | ok | 1 | 55 | 2,048 | — | 0.207 | — | 85.10 | — | — | — | length |
| context-32k | ok | 1 | 25,619 | 1,024 | — | 24.65 | — | 56.35 | — | — | — | length |
| context-64k | ok | 1 | 67,238 | 1,024 | — | 80.35 | — | 46.93 | — | — | — | length |
| context-120k | ok | 2 | 118,963 | 1,024 | — | 183.33 | — | 40.58 | — | — | — | length |
| conversation-fresh | ok | 1 | 1,146 | 71 | — | 2.11 | — | 90.03 | — | — | — | stop |
| conversation-reuse-1 | ok | 1 | 425 | 36 | — | 0.528 | — | 95.28 | — | — | — | stop |
| conversation-reuse-2 | ok | 1 | 778 | 256 | — | 0.448 | — | 78.74 | — | — | — | length |
| conversation-reuse-3 | ok | 1 | 1,146 | 97 | — | 0.469 | — | 49.28 | — | — | — | stop |
| reasoning-medium | ok | 1 | 117 | 709 | — | 0.361 | — | 61.88 | 11.23 | 1,880 | — | stop |

- Noise floor, context-8k (5 runs): first output 95.7%, decode rate 12.1% (range over median).
- Noise floor, context-120k (2 runs): first output 0.8%, decode rate 2.7% (range over median).
- sustained-lru-cache: Median output 138 tokens is below the 512-token minimum

### Conversation reuse

- conversation-fresh, 2.11 s first output (full history, cold)
- conversation-reuse-1, 0.528 s first output
- conversation-reuse-2, 0.448 s first output
- conversation-reuse-3, 0.469 s first output

Cache reuse: unknown — the server reports no cached-token counts. Replaying the identical prompt reached first output in 0.47 s versus 2.11 s cold — consistent with KV-cache reuse across requests.

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GB) | VRAM peak / total (GB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 0.314 | 2.23 | 13.2 / 59.2 | 15.7 / 15.9 | 97.66 | 282.80 | 54 | 29 / 0 | 114 | 1.00 |
| sustained-lru-cache | 0.380 | 2.84 | 13.8 / 59.2 | 15.7 / 15.9 | 88.34 | 260.37 | 53 | 0 / 0 | 2 | 1.00 |
| sustained-tokenizer | 0.376 | 2.57 | 14.1 / 59.2 | 15.7 / 15.9 | 97.54 | 283.62 | 54 | 1.95 / 0 | 25 | 1.00 |
| sustained-event-store | 0.381 | 2.63 | 14.4 / 59.2 | 15.7 / 15.9 | 97.77 | 284.47 | 54 | 1.05 / 0 | 24 | 1.00 |
| context-32k | 0.285 | 2.08 | 14.9 / 59.2 | 15.7 / 15.9 | 97.79 | 283.10 | 55 | 9 / 0 | 43 | 1.00 |
| context-64k | 0.255 | 1.92 | 14.9 / 59.2 | 15.9 / 15.9 | 96.98 | 278.50 | 56 | 3 / 0 | 103 | 1.00 |
| context-120k | 0.232 | 1.80 | 15.5 / 59.2 | 15.9 / 15.9 | 97.65 | 280.63 | 58 | 30 / 0 | 417 | 1.00 |
| conversation-fresh | 0.430 | 3.18 | 12.6 / 59.2 | 15.6 / 15.9 | 64.52 | 222.36 | 55 | 0 / 0 | 3 | 1.00 |
| conversation-reuse-1 | 0.280 | 2.23 | 12.8 / 59.2 | 15.6 / 15.9 | 92.70 | 271.19 | 56 | 0 / 0 | 1 | 1.00 |
| conversation-reuse-2 | 0.359 | 2.57 | 13.1 / 59.2 | 15.6 / 15.9 | 95.32 | 279.17 | 56 | 0 / 0 | 4 | 1.00 |
| conversation-reuse-3 | 0.342 | 2.55 | 13.3 / 59.2 | 15.6 / 15.9 | 93.04 | 273.53 | 56 | 0 / 0 | 2 | 1.00 |
| reasoning-medium | 0.371 | 2.62 | 13.8 / 59.2 | 15.6 / 15.9 | 97.41 | 282.35 | 56 | 0 / 0 | 12 | 1.00 |

### Unavailable measurements

- cached_input_tokens: server reports no cached-token counts (context-8k, sustained-lru-cache, sustained-tokenizer, sustained-event-store, context-32k, context-64k, context-120k, conversation-fresh, conversation-reuse-1, conversation-reuse-2, conversation-reuse-3, reasoning-medium)
- engine_prefill_tok_s: engine timings are not parsed for lmstudio (context-8k, sustained-lru-cache, sustained-tokenizer, sustained-event-store, context-32k, context-64k, context-120k, conversation-fresh, conversation-reuse-1, conversation-reuse-2, conversation-reuse-3, reasoning-medium)
- draft_acceptance: engine timings are not parsed for lmstudio (context-8k, sustained-lru-cache, sustained-tokenizer, sustained-event-store, context-32k, context-64k, context-120k, conversation-fresh, conversation-reuse-1, conversation-reuse-2, conversation-reuse-3, reasoning-medium)

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
