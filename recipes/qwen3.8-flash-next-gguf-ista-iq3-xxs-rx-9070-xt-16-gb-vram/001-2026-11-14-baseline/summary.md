# 001 · 2026-11-14 — Baseline

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

Suite v1 · run complete · model `qwen3.8-flash-next-iq3_xxs` · configured context 131,072 tokens

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 504 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 53 s |
| RAM used / total (GB) | 2.3 / 59.2 |
| Swap used / total (GB) | 0.0 / 8.0 |
| GPU busy (%) | 1 |
| VRAM used / total (GB) | 0.2 / 15.9 |
| GPU power (W) | 9.00 |
| GPU temperature (°C) | 33 |

Warmup: 3 requests, converged, 3.44 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,111 | 1,024 | 0 | 2.85 | 2,878.07 | 94.62 | 63.6% | length |
| sustained-lru-cache | ok | 1 | 65 | 2,048 | 0 | 0.533 | 126.71 | 114.50 | 75.7% | length |
| sustained-tokenizer | ok | 1 | 62 | 2,048 | 0 | 0.531 | 121.09 | 116.13 | 75.7% | length |
| sustained-event-store | ok | 1 | 57 | 2,048 | 0 | 0.514 | 115.62 | 121.54 | 82.1% | length |
| context-32k | ok | 1 | 32,538 | 1,024 | 0 | 9.91 | 3,293.65 | 91.39 | 65.9% | length |
| context-64k | ok | 1 | 65,187 | 1,024 | 0 | 18.90 | 3,457.65 | 90.06 | 63.6% | length |
| context-120k | ok | 2 | 119,492 | 1,024 | 0 | 35.29 | 3,392.78 | 91.19 | 65.4% | length |

- Noise floor, context-8k (5 runs): first output 3.5%, decode rate 4.6% (range over median).
- Noise floor, context-120k (2 runs): first output 0.7%, decode rate 0.3% (range over median).

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GB) | VRAM peak / total (GB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.71 | 41.82 | 48.3 / 59.2 | 15.3 / 15.9 | 97.61 | 261.23 | 53 | 0 / 0 | 135 | 0.500 |
| sustained-lru-cache | 8.07 | 50.40 | 48.3 / 59.2 | 15.3 / 15.9 | 99.65 | 271.18 | 54 | 0 / 0 | 37 | 0.500 |
| sustained-tokenizer | 8.07 | 50.36 | 48.2 / 59.2 | 15.3 / 15.9 | 99.75 | 274.18 | 54 | 0 / 0 | 36 | 0.500 |
| sustained-event-store | 8.04 | 50.18 | 48.1 / 59.2 | 15.3 / 15.9 | 99.71 | 273.03 | 54 | 0 / 0 | 35 | 0.500 |
| context-32k | 4.88 | 30.26 | 48.1 / 59.2 | 15.3 / 15.9 | 97.09 | 265.27 | 54 | 0 / 0 | 42 | 0.500 |
| context-64k | 3.73 | 23.11 | 48.8 / 59.2 | 15.3 / 15.9 | 97.33 | 271.44 | 54 | 0 / 0 | 60 | 0.500 |
| context-120k | 2.80 | 17.22 | 51.6 / 59.2 | 15.3 / 15.9 | 97.61 | 275.27 | 55 | 0 / 0 | 187 | 0.500 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
