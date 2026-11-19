# 001 · 2026-11-14 — Baseline

<!-- BEGIN GENERATED RUN CONFIGURATION -->

## Run configuration

| Setting | Value |
|---|---|
| Runtime | Strata 0.1.59.1 (v0.2.13 + 95 commits) |
| GPU stack | ROCm 10.1.0 · AMD Radeon RX 9070 XT (gfx1201) |
| Model | Qwen3.8-Flash-Next · Unsloth Dynamic v3.1 UD-IQ3_XXS |
| Context and cache | 131,072 tokens · INT8 K AND V KV · 32,768 GPU-resident cells |
| Drafting and vision | MTP enabled · 4 draft tokens · CPU; 8 threads · 1,024 image tokens |
| Thinking | Off |

<!-- END GENERATED RUN CONFIGURATION -->

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

Suite v1 · run complete · model `qwen3.8-flash-next-ud-iq3_xxs` · configured context 131,072 tokens

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 500 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 56 s |
| RAM used / total (GiB) | 2.3 / 59.2 |
| Swap used / total (GiB) | 0.0 / 8.0 |
| GPU busy (%) | 2 |
| VRAM used / total (GiB) | 0.2 / 15.9 |
| GPU power (W) | 9.00 |
| GPU temperature (°C) | 33 |

Warmup: 2 requests, converged, 2.55 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,111 | 1,024 | 0 | 2.69 | 3,041.83 | 89.24 | 63.5% | length |
| sustained-lru-cache | ok | 1 | 64 | 2,048 | 0 | 0.582 | 114.29 | 111.22 | 79.1% | length |
| sustained-tokenizer | ok | 1 | 61 | 2,048 | 0 | 0.498 | 127.62 | 117.40 | 80.0% | length |
| sustained-event-store | ok | 1 | 56 | 2,048 | 0 | 0.546 | 106.87 | 112.98 | 78.3% | length |
| context-32k | ok | 1 | 32,536 | 1,024 | 0 | 10.14 | 3,218.20 | 86.26 | 63.5% | length |
| context-64k | ok | 1 | 65,186 | 1,024 | 0 | 19.90 | 3,282.94 | 83.37 | 59.5% | length |
| context-120k | ok | 2 | 119,492 | 1,024 | 0 | 37.06 | 3,230.21 | 84.56 | 63.6% | length |

- Noise floor, context-8k (5 runs): first output 2.3%, decode rate 12.5% (range over median).
- Noise floor, context-120k (2 runs): first output 0.1%, decode rate 8.2% (range over median).

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GiB) | VRAM peak / total (GiB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.83 | 42.58 | 54.9 / 59.2 | 15.3 / 15.9 | 98.45 | 263.37 | 54 | 0 / 0 | 141 | 0.500 |
| sustained-lru-cache | 8.06 | 50.35 | 54.8 / 59.2 | 15.3 / 15.9 | 99.66 | 273.11 | 54 | 0 / 0 | 38 | 0.500 |
| sustained-tokenizer | 8.06 | 50.37 | 54.7 / 59.2 | 15.3 / 15.9 | 99.75 | 276.72 | 54 | 0 / 0 | 36 | 0.500 |
| sustained-event-store | 8.03 | 50.16 | 55.0 / 59.2 | 15.3 / 15.9 | 99.76 | 274.99 | 54 | 0 / 0 | 37 | 0.500 |
| context-32k | 4.98 | 30.96 | 55.0 / 59.2 | 15.3 / 15.9 | 98.27 | 271.42 | 54 | 0 / 0 | 44 | 0.500 |
| context-64k | 3.90 | 24.17 | 55.2 / 59.2 | 15.3 / 15.9 | 98.34 | 274.93 | 54 | 0 / 0 | 65 | 0.500 |
| context-120k | 2.96 | 18.25 | 55.5 / 59.2 | 15.3 / 15.9 | 98.83 | 278.56 | 56 | 0 / 0 | 196 | 0.500 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
