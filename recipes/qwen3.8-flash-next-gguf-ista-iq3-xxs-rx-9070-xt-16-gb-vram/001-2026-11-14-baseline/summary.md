# 001 · 2026-11-14 — Baseline

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

suite 1 · schema 1 · run complete · model `qwen3.8-flash-next-iq3_xxs` · context 131,072 tokens

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 504 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 2 h 21 min |
| Swap used / total (GB) | 0.0 / — |
| GPU busy (%) | 1 |
| VRAM used / total (GB) | 0.2 / — |
| GPU power (W) | 8.00 |
| GPU temperature (°C) | 28 |

Warmup: 2 requests, converged, 2.29 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,012 | 968 | 0 | 2.82 | 2,868.77 | 91.38 | 61.0% | stop |
| sustained-lru-cache | ok | 1 | 63 | 2,048 | 0 | 0.538 | 121.86 | 117.33 | 79.2% | length |
| sustained-tokenizer | ok | 1 | 60 | 2,048 | 0 | 0.543 | 114.72 | 120.38 | 78.9% | length |
| sustained-event-store | ok | 1 | 55 | 2,048 | 0 | 0.489 | 117.02 | 110.65 | 73.4% | length |
| context-32k | ok | 1 | 31,888 | 1,024 | 0 | 9.78 | 3,271.57 | 93.46 | 67.4% | length |
| context-64k | ok | 1 | 64,502 | 1,024 | 0 | 18.78 | 3,443.78 | 93.12 | 66.1% | length |
| context-120k | ok | 1 | 116,536 | 1,024 | 0 | 34.57 | 3,377.46 | 83.57 | 57.3% | length |

- Noise floor, context-8k (5 runs): first output 2.8%, decode rate 4.6% (range over median).

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GB) | VRAM peak / total (GB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.71 | 42.02 | 48.9 / — | 15.3 / — | 97.09 | 257.83 | 53 | 0 / 0 | 133 | 0.500 |
| sustained-lru-cache | 8.07 | 50.58 | 49.0 / — | 15.3 / — | 99.72 | 270.92 | 54 | 0 / 0 | 36 | 0.500 |
| sustained-tokenizer | 8.07 | 50.59 | 49.0 / — | 15.3 / — | 99.77 | 274.20 | 54 | 0 / 0 | 35 | 0.500 |
| sustained-event-store | 8.01 | 50.28 | 48.8 / — | 15.3 / — | 99.92 | 270.81 | 54 | 0 / 0 | 38 | 0.500 |
| context-32k | 4.86 | 30.47 | 48.9 / — | 15.3 / — | 96.12 | 264.48 | 54 | 0 / 0 | 41 | 0.500 |
| context-64k | 3.69 | 23.12 | 49.5 / — | 15.3 / — | 97.40 | 273.65 | 54 | 0 / 0 | 60 | 0.500 |
| context-120k | 2.94 | 18.31 | 51.1 / — | 15.3 / — | 97.48 | 272.89 | 54 | 0 / 0 | 94 | 0.500 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
