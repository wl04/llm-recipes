# 003 · 2026-11-24 — Baseline

<!-- BEGIN GENERATED RUN CONFIGURATION -->

## Run configuration

| Setting | Value |
|---|---|
| Runtime | Strata 0.1.67 (v0.2.21) |
| GPU stack | ROCm 10.2.0 · Radeon RX 9070/9070 XT/9070 GRE (gfx1201) |
| Model | Qwen3.8-Flash-Next IQ3_XXS · Strata |
| Context and cache | 131,072 tokens · INT8 KV · 32,768 GPU-resident cells |
| Drafting and vision | MTP · 4 draft tokens · CPU vision · 1,024 image tokens |
| Thinking | Off |

<!-- END GENERATED RUN CONFIGURATION -->

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

Suite v3 · run complete · model `qwen3.8-flash-next-iq3_xxs` · configured context 131,072 tokens

### Performance at a glance

| Case | Status | OK / tried | Input | Output | Cached input | First output (s) | First visible text (s) | Decode (tok/s) |
|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5/5 | 8,109 | 992 | 0 | 3.15 (3.08 to 3.20) | 3.15 (3.08 to 3.20) | 90.16 (85.11 to 93.02) |
| context-120k | ok | 2/2 | 119,493 | 1,024 | 0 | 33.06 (32.88 to 33.23) | 33.06 (32.88 to 33.23) | 85.27 (84.86 to 85.68) |
| context-64k | ok | 1/1 | 65,184 | 1,024 | 0 | 19.67 | 19.67 | 89.01 |
| conversation-64k-replay | ok | 1/1 | 65,184 | 1,024 | 65,177 | 0.085 | 0.085 | 90.28 |
| conversation-64k-followup | ok | 2/2 | 65,219 | 256 | 65,177 | 0.436 (0.360 to 0.513) | 0.436 (0.360 to 0.513) | 84.03 (83.46 to 84.60) |

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 487 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 36 min |
| RAM used / total (GiB) | 4.6 / 59.2 |
| Swap used / total (GiB) | 0.0 / 8.0 |
| GPU busy (%) | 1 |
| VRAM used / total (GiB) | 0.2 / 15.9 |
| GPU power (W) | 8.00 |
| GPU temperature (°C) | 32 |

Warmup: 4 requests, did not converge, 4.20 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output / visible (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,109 | 992 | 0 | 3.15 / 3.15 | 2,598.09 | 90.16 | 63.1% | length (2), stop (3) |
| sustained-lru-cache | ok | 1 | 62 | 2,048 | 0 | 0.541 / 0.541 | 119.46 | 113.51 | 82.3% | length |
| sustained-tokenizer | ok | 1 | 59 | 2,048 | 0 | 0.570 / 0.570 | 107.86 | 116.75 | 80.6% | length |
| sustained-event-store | ok | 1 | 54 | 2,048 | 0 | 0.535 / 0.535 | 105.68 | 110.72 | 78.6% | length |
| context-32k | ok | 1 | 32,537 | 1,024 | 0 | 10.57 / 10.57 | 3,087.88 | 85.10 | 59.8% | length |
| context-64k | ok | 1 | 65,184 | 1,024 | 0 | 19.67 / 19.67 | 3,322.15 | 89.01 | 64.7% | length |
| conversation-64k-replay | ok | 1 | 65,184 | 1,024 | 65,177 | 0.085 / 0.085 | 129.63 | 90.28 | 66.4% | length |
| conversation-64k-followup | ok | 2 | 65,219 | 256 | 65,177 | 0.436 / 0.436 | 103.83 | 84.03 | 58.4% | length |
| context-120k | ok | 2 | 119,493 | 1,024 | 0 | 33.06 / 33.06 | 3,621.99 | 85.27 | 62.2% | length |
| reasoning-medium | ok | 1 | 117 | 487 | 0 | 0.656 / 5.90 | 185.42 | 85.37 | 59.3% | stop |

- Noise floor, context-8k (5 runs): first output 3.7%, decode rate 8.8% (range over median).
- Noise floor, context-120k (2 runs): first output 1.1%, decode rate 1.0% (range over median).

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GiB) | VRAM peak / total (GiB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.61 | 41.20 | 49.3 / 59.2 | 15.3 / 15.9 | 98.11 | 253.56 | 53 | 0 / 0 | 70 | 1.00 |
| sustained-lru-cache | 8.07 | 50.51 | 49.3 / 59.2 | 15.3 / 15.9 | 99.78 | 257.93 | 54 | 0 / 0 | 19 | 1.00 |
| sustained-tokenizer | 8.08 | 50.50 | 49.3 / 59.2 | 15.3 / 15.9 | 100 | 264.29 | 54 | 0 / 0 | 18 | 1.00 |
| sustained-event-store | 8.03 | 50.22 | 49.2 / 59.2 | 15.3 / 15.9 | 100 | 260.11 | 54 | 0 / 0 | 19 | 1.00 |
| context-32k | 4.90 | 30.52 | 49.2 / 59.2 | 15.3 / 15.9 | 96.28 | 260.54 | 54 | 0 / 0 | 22 | 1.00 |
| context-64k | 3.79 | 23.62 | 49.4 / 59.2 | 15.3 / 15.9 | 97.59 | 269.71 | 54 | 0 / 0 | 32 | 1.00 |
| conversation-64k-replay | 8.06 | 50.38 | 49.6 / 59.2 | 15.3 / 15.9 | 100 | 266.95 | 55 | 0 / 0 | 11 | 1.00 |
| conversation-64k-followup | 7.65 | 47.83 | 50.3 / 59.2 | 15.3 / 15.9 | 96.54 | 252.14 | 55 | 0 / 0 | 7 | 1.00 |
| context-120k | 3.05 | 18.95 | 51.5 / 59.2 | 15.3 / 15.9 | 97.13 | 270.85 | 55 | 0 / 0 | 90 | 1.00 |
| reasoning-medium | 7.91 | 48.36 | 50.2 / 59.2 | 15.3 / 15.9 | 94.65 | 239.57 | 55 | 0 / 0 | 7 | 1.00 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
