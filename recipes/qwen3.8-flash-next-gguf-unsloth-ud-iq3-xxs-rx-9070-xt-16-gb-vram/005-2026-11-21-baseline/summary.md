# 005 · 2026-11-21 — Baseline

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
| context-8k | ok | 5/5 | 8,110 | 1,024 | 0 | 2.74 (2.70 to 2.81) | 2.74 (2.70 to 2.81) | 89.32 (88.88 to 90.33) |
| context-120k | ok | 2/2 | 119,492 | 1,024 | 0 | 37.00 (37.00 to 37.00) | 37.00 (37.00 to 37.00) | 82.28 (81.96 to 82.60) |
| context-64k | ok | 1/1 | 65,184 | 1,024 | 0 | 19.98 | 19.98 | 83.59 |
| conversation-64k-replay | ok | 1/1 | 65,184 | 1,024 | 65,177 | 0.080 | 0.080 | 91.28 |
| conversation-64k-followup | ok | 2/2 | 65,219 | 256 | 65,177 | 0.336 (0.314 to 0.358) | 0.336 (0.314 to 0.358) | 81.86 (80.24 to 83.48) |

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 500 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 1 min |
| RAM used / total (GiB) | 2.4 / 59.2 |
| Swap used / total (GiB) | 0.0 / 8.0 |
| GPU busy (%) | 1 |
| VRAM used / total (GiB) | 0.2 / 15.9 |
| GPU power (W) | 8.00 |
| GPU temperature (°C) | 29 |

Warmup: 2 requests, converged, 2.43 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output / visible (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,110 | 1,024 | 0 | 2.74 / 2.74 | 2,973.91 | 89.32 | 63.0% | length |
| sustained-lru-cache | ok | 1 | 63 | 1,587 | 0 | 0.528 / 0.528 | 124.26 | 102.33 | 75.9% | stop |
| sustained-tokenizer | ok | 1 | 60 | 2,048 | 0 | 0.509 / 0.509 | 123.20 | 120.47 | 81.1% | length |
| sustained-event-store | ok | 1 | 55 | 2,048 | 0 | 0.498 / 0.498 | 115.55 | 116.79 | 80.1% | length |
| context-32k | ok | 1 | 32,536 | 967 | 0 | 10.26 / 10.26 | 3,182.94 | 83.42 | 59.9% | stop |
| context-64k | ok | 1 | 65,184 | 1,024 | 0 | 19.98 / 19.98 | 3,269.99 | 83.59 | 62.5% | length |
| conversation-64k-replay | ok | 1 | 65,184 | 1,024 | 65,177 | 0.080 / 0.080 | 145.83 | 91.28 | 66.3% | length |
| conversation-64k-followup | ok | 2 | 65,219 | 256 | 65,177 | 0.336 / 0.336 | 137.93 | 81.86 | 58.2% | length |
| context-120k | ok | 2 | 119,492 | 1,024 | 0 | 37.00 / 37.00 | 3,235.43 | 82.28 | 60.6% | length |
| reasoning-medium | ok | 1 | 117 | 269 | 0 | 0.424 / 3.40 | 292.50 | 82.17 | 63.1% | stop |

- Noise floor, context-8k (5 runs): first output 3.8%, decode rate 1.6% (range over median).
- Noise floor, context-120k (2 runs): first output 0.0%, decode rate 0.8% (range over median).

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GiB) | VRAM peak / total (GiB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.82 | 42.63 | 54.8 / 59.2 | 15.3 / 15.9 | 98.15 | 260.95 | 53 | 0 / 0 | 71 | 1.00 |
| sustained-lru-cache | 8.00 | 50.12 | 54.7 / 59.2 | 15.3 / 15.9 | 100 | 261.96 | 53 | 0 / 0 | 16 | 1.00 |
| sustained-tokenizer | 8.07 | 50.56 | 54.7 / 59.2 | 15.3 / 15.9 | 100 | 280.76 | 54 | 0 / 0 | 17 | 1.00 |
| sustained-event-store | 8.06 | 50.54 | 54.9 / 59.2 | 15.3 / 15.9 | 100 | 274.71 | 54 | 0 / 0 | 18 | 1.00 |
| context-32k | 4.89 | 30.47 | 55.0 / 59.2 | 15.3 / 15.9 | 98.90 | 273.83 | 54 | 0 / 0 | 22 | 1.00 |
| context-64k | 3.92 | 24.35 | 55.0 / 59.2 | 15.3 / 15.9 | 97.11 | 270.73 | 54 | 0 / 0 | 33 | 1.00 |
| conversation-64k-replay | 8.06 | 50.44 | 55.0 / 59.2 | 15.3 / 15.9 | 100 | 275.34 | 55 | 0 / 0 | 11 | 1.00 |
| conversation-64k-followup | 7.87 | 49.12 | 55.1 / 59.2 | 15.3 / 15.9 | 99.28 | 268.53 | 55 | 0 / 0 | 7 | 1.00 |
| context-120k | 3.02 | 18.77 | 55.4 / 59.2 | 15.3 / 15.9 | 98.63 | 278.81 | 56 | 0 / 0 | 99 | 1.00 |
| reasoning-medium | 8.07 | 48.63 | 54.8 / 59.2 | 15.3 / 15.9 | 98.93 | 253.18 | 55 | 0 / 0 | 4 | 1.00 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
