# 004 · 2026-11-21 — Baseline tail skip off

<!-- BEGIN GENERATED RUN CONFIGURATION -->

## Run configuration

| Setting | Value |
|---|---|
| Runtime | Strata 0.1.64 (v0.2.18) |
| GPU stack | ROCm 10.2.0 · Radeon RX 9070/9070 XT/9070 GRE (gfx1201) |
| Model | Qwen3.8-Flash-Next UD-IQ3_XXS · Strata |
| Context and cache | 131,072 tokens · INT8 KV · 32,768 GPU-resident cells |
| Drafting and vision | MTP · 4 draft tokens · CPU vision · 1,024 image tokens |
| Thinking | Off |

<!-- END GENERATED RUN CONFIGURATION -->

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

Suite v3 · run complete · model `qwen3.8-flash-next-ud-iq3_xxs` · configured context 131,072 tokens

### Performance at a glance

| Case | Status | OK / tried | Input | Output | Cached input | First output (s) | First visible text (s) | Decode (tok/s) |
|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5/5 | 8,110 | 1,015 | 0 | 2.75 (2.72 to 2.82) | 2.75 (2.72 to 2.82) | 80.03 (79.22 to 86.17) |
| context-120k | ok | 2/2 | 119,492 | 1,024 | 0 | 37.04 (37.03 to 37.05) | 37.04 (37.03 to 37.05) | 76.56 (73.30 to 79.83) |
| context-64k | ok | 1/1 | 65,184 | 1,024 | 0 | 19.99 | 19.99 | 81.38 |
| conversation-64k-replay | ok | 1/1 | 65,184 | 1,024 | 65,177 | 0.086 | 0.086 | 89.31 |
| conversation-64k-followup | ok | 2/2 | 65,219 | 256 | 65,177 | 0.380 (0.360 to 0.399) | 0.380 (0.360 to 0.399) | 76.76 (75.47 to 78.05) |

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 491 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 1 min |
| RAM used / total (GiB) | 2.3 / 59.2 |
| Swap used / total (GiB) | 0.0 / 8.0 |
| GPU busy (%) | 1 |
| VRAM used / total (GiB) | 0.2 / 15.9 |
| GPU power (W) | 9.00 |
| GPU temperature (°C) | 29 |

Warmup: 3 requests, converged, 3.69 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output / visible (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,110 | 1,015 | 0 | 2.75 / 2.75 | 2,965.43 | 80.03 | 63.7% | length (2), stop (3) |
| sustained-lru-cache | ok | 1 | 63 | 2,048 | 0 | 0.592 / 0.592 | 110.92 | 102.03 | 81.6% | length |
| sustained-tokenizer | ok | 1 | 60 | 2,048 | 0 | 0.613 / 0.613 | 102.04 | 97.28 | 73.6% | length |
| sustained-event-store | ok | 1 | 55 | 2,048 | 0 | 0.573 / 0.573 | 100.36 | 105.33 | 82.2% | length |
| context-32k | ok | 1 | 32,536 | 1,024 | 0 | 10.27 / 10.27 | 3,179.21 | 80.63 | 65.3% | length |
| context-64k | ok | 1 | 65,184 | 1,024 | 0 | 19.99 / 19.99 | 3,269.83 | 81.38 | 65.3% | length |
| conversation-64k-replay | ok | 1 | 65,184 | 1,024 | 65,177 | 0.086 / 0.086 | 134.62 | 89.31 | 74.1% | length |
| conversation-64k-followup | ok | 2 | 65,219 | 256 | 65,177 | 0.380 / 0.380 | 121.39 | 76.76 | 61.9% | length |
| context-120k | ok | 2 | 119,492 | 1,024 | 0 | 37.04 / 37.04 | 3,232.24 | 76.56 | 60.8% | length |
| reasoning-medium | ok | 1 | 117 | 379 | 0 | 0.429 / 4.94 | 289.60 | 78.87 | 65.9% | stop |

- Noise floor, context-8k (5 runs): first output 3.7%, decode rate 8.7% (range over median).
- Noise floor, context-120k (2 runs): first output 0.0%, decode rate 8.5% (range over median).

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GiB) | VRAM peak / total (GiB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.88 | 43.04 | 54.8 / 59.2 | 15.3 / 15.9 | 99.44 | 259.84 | 53 | 0 / 0 | 75 | 1.00 |
| sustained-lru-cache | 8.07 | 50.59 | 54.7 / 59.2 | 15.3 / 15.9 | 99.95 | 257.10 | 53 | 0 / 0 | 21 | 1.00 |
| sustained-tokenizer | 8.06 | 50.54 | 54.7 / 59.2 | 15.3 / 15.9 | 100 | 269.37 | 54 | 0 / 0 | 21 | 1.00 |
| sustained-event-store | 8.00 | 50.13 | 54.9 / 59.2 | 15.3 / 15.9 | 100 | 268.30 | 54 | 0 / 0 | 20 | 1.00 |
| context-32k | 5.08 | 31.57 | 55.0 / 59.2 | 15.3 / 15.9 | 95.69 | 260.54 | 54 | 0 / 0 | 23 | 1.00 |
| context-64k | 3.99 | 24.72 | 55.0 / 59.2 | 15.3 / 15.9 | 98.65 | 271.70 | 54 | 0 / 0 | 33 | 1.00 |
| conversation-64k-replay | 8.06 | 50.47 | 55.0 / 59.2 | 15.3 / 15.9 | 100 | 268.23 | 55 | 0 / 0 | 11 | 1.00 |
| conversation-64k-followup | 7.89 | 49.34 | 55.1 / 59.2 | 15.3 / 15.9 | 99.59 | 262.10 | 55 | 0 / 0 | 8 | 1.00 |
| context-120k | 3.12 | 19.37 | 55.4 / 59.2 | 15.3 / 15.9 | 98.98 | 277.47 | 56 | 0 / 0 | 101 | 1.00 |
| reasoning-medium | 7.77 | 48.79 | 54.8 / 59.2 | 15.3 / 15.9 | 99.05 | 247.99 | 55 | 0 / 0 | 5 | 1.00 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
