# 001 · 2026-11-14 — Baseline

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

suite 1 · schema 1 · run complete · model `qwen3.8-flash-next-ud-iq3_xxs` · context 131,072 tokens

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 500 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime (s) | 817 |
| Load average (1 min) | 0.26 |
| Swap used / total (GB) | 0.0 / — |
| GPU busy (%) | 1 |
| VRAM used / total (GB) | 0.2 / — |
| GPU power (W) | 10.00 |
| GPU temperature (°C) | 32 |

Warmup: 3 requests, converged, 3.48 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,011 | 1,024 | 0 | 2.67 | 3,026.31 | 87.66 | 60.8% | length |
| sustained-lru-cache | ok | 1 | 61 | 2,048 | 0 | 0.554 | 114.66 | 115.46 | 81.9% | length |
| sustained-tokenizer | ok | 1 | 58 | 2,048 | 0 | 0.543 | 111.11 | 111.09 | 78.0% | length |
| sustained-event-store | ok | 1 | 53 | 2,048 | 0 | 0.520 | 106.64 | 119.28 | 84.2% | length |
| context-32k | ok | 1 | 31,892 | 1,024 | 0 | 10.03 | 3,189.84 | 82.53 | 61.1% | length |
| context-64k | ok | 1 | 64,503 | 1,014 | 0 | 19.76 | 3,271.61 | 87.10 | 64.2% | stop |
| context-120k | ok | 1 | 116,536 | 1,024 | 0 | 36.42 | 3,205.77 | 87.65 | 65.5% | length |

- Noise floor, context-8k (5 runs): first output 2.5%, decode rate 4.9% (range over median).

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GB) | VRAM peak / total (GB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.86 | 42.97 | 55.1 / — | 15.3 / — | 98.76 | 264.20 | 54 | 0 / 0 | 143 | 0.500 |
| sustained-lru-cache | 8.07 | 50.59 | 54.9 / — | 15.3 / — | 99.64 | 272.64 | 54 | 0 / 0 | 36 | 0.500 |
| sustained-tokenizer | 8.06 | 50.55 | 55.1 / — | 15.3 / — | 99.74 | 273.47 | 54 | 0 / 0 | 38 | 0.500 |
| sustained-event-store | 8.04 | 50.40 | 55.0 / — | 15.3 / — | 97.51 | 269.05 | 55 | 0 / 0 | 36 | 0.500 |
| context-32k | 5.08 | 31.79 | 55.1 / — | 15.3 / — | 98.60 | 270.76 | 54 | 0 / 0 | 45 | 0.500 |
| context-64k | 3.83 | 23.92 | 55.3 / — | 15.3 / — | 98.52 | 276.30 | 55 | 0 / 0 | 63 | 0.500 |
| context-120k | 2.94 | 18.31 | 55.5 / — | 15.3 / — | 98.99 | 278.79 | 55 | 0 / 0 | 96 | 0.500 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
