# 001 · 2026-11-14 — Baseline

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

Suite v1 · run complete · model `qwen3.8-27b-exl3-3bpw` · configured context 131,072 tokens

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 452 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 6 min |
| RAM used / total (GB) | 3.8 / 59.2 |
| Swap used / total (GB) | 0.0 / 8.0 |
| GPU busy (%) | 1 |
| VRAM used / total (GB) | 0.1 / 15.9 |
| GPU power (W) | 6.00 |
| GPU temperature (°C) | 35 |

Warmup: 4 requests, did not converge, 4.48 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,145 | 1,024 | 0 | 5.63 | 1,477.63 | 68.71 | 27.9% | length (4), stop (1) |
| sustained-lru-cache | ok | 1 | 64 | 2,048 | 0 | 0.719 | 100 | 123.59 | 55.4% | length |
| sustained-tokenizer | ok | 1 | 61 | 2,048 | 0 | 0.715 | 96.83 | 128.82 | 58.3% | length |
| sustained-event-store | ok | 1 | 56 | 2,048 | 0 | 0.713 | 88.89 | 122.69 | 54.9% | length |
| context-32k | ok | 1 | 32,592 | 1,024 | 0 | 24.76 | 1,324.88 | 57.28 | 26.9% | length |
| context-64k | ok | 1 | 65,225 | 1,024 | 0 | 53.91 | 1,214.62 | 42.70 | 24.9% | length |
| context-120k | ok | 2 | 119,542 | 1,024 | 0 | 115.45 | 1,037.70 | 36.43 | 28.9% | length |

- Noise floor, context-8k (5 runs): first output 1.2%, decode rate 12.9% (range over median).
- Noise floor, context-120k (2 runs): first output 0.6%, decode rate 6.7% (range over median).

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GB) | VRAM peak / total (GB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 1.03 | 6.59 | 9.2 / 59.2 | 15.9 / 15.9 | 99.08 | 284.08 | 54 | 0 / 0 | 199 | 0.500 |
| sustained-lru-cache | 1.05 | 6.62 | 9.3 / 59.2 | 15.9 / 15.9 | 99.01 | 280.50 | 54 | 0 / 0 | 34 | 0.500 |
| sustained-tokenizer | 1.04 | 6.64 | 9.4 / 59.2 | 15.9 / 15.9 | 98.96 | 280.25 | 54 | 0 / 0 | 34 | 0.500 |
| sustained-event-store | 1.05 | 6.66 | 9.5 / 59.2 | 15.9 / 15.9 | 98.98 | 281.48 | 55 | 0 / 0 | 34 | 0.500 |
| context-32k | 1.02 | 6.53 | 9.9 / 59.2 | 15.9 / 15.9 | 99.45 | 282.59 | 55 | 0 / 0 | 86 | 0.500 |
| context-64k | 1.01 | 6.56 | 10.2 / 59.2 | 15.9 / 15.9 | 99.68 | 284.44 | 56 | 0 / 0 | 156 | 0.500 |
| context-120k | 1.01 | 6.53 | 10.7 / 59.2 | 15.9 / 15.9 | 99.72 | 284.17 | 57 | 0 / 0 | 574 | 0.500 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
