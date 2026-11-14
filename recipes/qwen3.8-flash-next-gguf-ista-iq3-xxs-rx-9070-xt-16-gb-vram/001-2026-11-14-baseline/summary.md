# 001 · 2026-11-14 — Baseline

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

Suite v1 · run complete · model `qwen3.8-flash-next-iq3_xxs` · context 131,072 tokens

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 504 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 1 min |
| RAM used / total (GB) | 2.4 / 59.2 |
| Swap used / total (GB) | 0.0 / 8.0 |
| GPU busy (%) | 1 |
| VRAM used / total (GB) | 0.2 / 15.9 |
| GPU power (W) | 10.00 |
| GPU temperature (°C) | 29 |

Warmup: 3 requests, converged, 3.28 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,013 | 1,024 | 0 | 2.82 | 2,873.04 | 93.89 | 63.0% | length |
| sustained-lru-cache | ok | 1 | 65 | 1,706 | 0 | 0.532 | 127.20 | 111.07 | 73.9% | stop |
| sustained-tokenizer | ok | 1 | 62 | 2,048 | 0 | 0.545 | 118.10 | 122.39 | 80.0% | length |
| sustained-event-store | ok | 1 | 57 | 2,048 | 0 | 0.512 | 115.85 | 117.07 | 79.1% | length |
| context-32k | ok | 1 | 31,889 | 1,024 | 0 | 9.75 | 3,283.13 | 92.03 | 63.3% | length |
| context-64k | ok | 1 | 64,504 | 1,024 | 0 | 18.73 | 3,452.55 | 93.70 | 67.3% | length |
| context-120k | ok | 1 | 116,535 | 1,024 | 0 | 34.51 | 3,383.61 | 95.11 | 70.2% | length |

- Noise floor, context-8k (5 runs): first output 2.8%, decode rate 5.8% (range over median).

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GB) | VRAM peak / total (GB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.74 | 42.15 | 48.4 / 59.2 | 15.3 / 15.9 | 97.76 | 257.91 | 53 | 0 / 0 | 135 | 0.500 |
| sustained-lru-cache | 8.07 | 50.56 | 48.4 / 59.2 | 15.3 / 15.9 | 99.91 | 270.31 | 54 | 0 / 0 | 32 | 0.500 |
| sustained-tokenizer | 8.07 | 50.55 | 48.3 / 59.2 | 15.3 / 15.9 | 99.91 | 276.14 | 54 | 0 / 0 | 34 | 0.500 |
| sustained-event-store | 8.07 | 50.55 | 48.2 / 59.2 | 15.3 / 15.9 | 99.14 | 270.95 | 54 | 0 / 0 | 36 | 0.500 |
| context-32k | 4.85 | 30.19 | 48.2 / 59.2 | 15.3 / 15.9 | 96.38 | 266.93 | 55 | 0 / 0 | 42 | 0.500 |
| context-64k | 3.71 | 23.74 | 49.0 / 59.2 | 15.3 / 15.9 | 96.51 | 269.28 | 54 | 0 / 0 | 60 | 0.500 |
| context-120k | 2.78 | 17.25 | 50.4 / 59.2 | 15.3 / 15.9 | 97.89 | 275.46 | 55 | 0 / 0 | 90 | 0.500 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
