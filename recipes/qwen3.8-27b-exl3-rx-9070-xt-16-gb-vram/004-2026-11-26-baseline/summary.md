# 004 · 2026-11-26 — Baseline

<!-- BEGIN GENERATED RUN CONFIGURATION -->

## Run configuration

| Setting | Value |
|---|---|
| Runtime | ExLlamaV3 1.6.7 (v1.6.7) |
| GPU stack | ROCm 10.2.0 · Radeon RX 9070/9070 XT/9070 GRE (gfx1201) |
| Model | Qwen3.8-27B EXL3 |
| Context and cache | 131,072 tokens · Q4 KV |
| Drafting and vision | Drafting on · Vision on |
| Thinking | Off |

<!-- END GENERATED RUN CONFIGURATION -->

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

Suite v3 · run complete · model `qwen3.8-27b-exl3-3bpw` · configured context 131,072 tokens

### Performance at a glance

| Case | Status | OK / tried | Input | Output | Cached input | First output (s) | First visible text (s) | Decode (tok/s) |
|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5/5 | 8,145 | 1,024 | 0 | 5.51 (5.42 to 13.13) | 5.51 (5.42 to 13.13) | 69.20 (68.66 to 70.95) |
| context-120k | ok | 2/2 | 119,541 | 1,024 | 0 | 112.46 (110.91 to 114.00) | 112.46 (110.91 to 114.00) | 36.91 (36.74 to 37.09) |
| context-64k | ok | 1/1 | 65,226 | 1,024 | 0 | 51.53 | 51.53 | 43.65 |
| conversation-64k-replay | ok | 1/1 | 65,226 | 1,024 | 65,024 | 1.29 | 1.29 | 48.71 |
| conversation-64k-followup | ok | 2/2 | 65,261 | 256 | 65,024 | 5.20 (1.31 to 9.09) | 5.20 (1.31 to 9.09) | 45.85 (45.10 to 46.59) |

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 452 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 3 h 6 min |
| RAM used / total (GiB) | 6.3 / 59.2 |
| Swap used / total (GiB) | 0.0 / 8.0 |
| GPU busy (%) | 12 |
| VRAM used / total (GiB) | 0.1 / 15.9 |
| GPU power (W) | 39.00 |
| GPU temperature (°C) | 32 |

- GPU is 12% busy at start

Warmup: 4 requests, did not converge, 12.93 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output / visible (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,145 | 1,024 | 0 | 5.51 / 5.51 | 1,173.00 | 69.20 | 28.5% | length |
| sustained-lru-cache | ok | 1 | 65 | 2,048 | 0 | 0.973 / 0.973 | 73.03 | 145.90 | 69.3% | length |
| sustained-tokenizer | insufficient_sample | 1 | 62 | 104 | 0 | 0.748 / 0.748 | 93.94 | 103.83 | 40.7% | tool_calls |
| sustained-event-store | insufficient_sample | 1 | 57 | 68 | 0 | 0.744 / 0.744 | 86.36 | 60.38 | 18.1% | stop |
| context-32k | ok | 1 | 32,590 | 1,024 | 0 | 32.28 / 32.28 | 1,015.26 | 57.61 | 27.4% | length |
| context-64k | ok | 1 | 65,226 | 1,024 | 0 | 51.53 / 51.53 | 1,271.46 | 43.65 | 26.1% | length |
| conversation-64k-replay | ok | 1 | 65,226 | 1,024 | 65,024 | 1.29 / 1.29 | 181.98 | 48.71 | 30.9% | length |
| conversation-64k-followup | ok | 2 | 65,261 | 256 | 65,024 | 5.20 / 5.20 | 47.40 | 45.85 | 27.8% | length |
| context-120k | ok | 2 | 119,541 | 1,024 | 0 | 112.46 / 112.46 | 1,065.90 | 36.91 | 29.3% | length |
| reasoning-medium | ok | 1 | 117 | 833 | 0 | 1.58 / 10.82 | 78.52 | 86.69 | 35.9% | stop |

- Noise floor, context-8k (5 runs): first output 139.9%, decode rate 3.3% (range over median).
- Noise floor, context-120k (2 runs): first output 2.7%, decode rate 1.0% (range over median).
- sustained-tokenizer: Median output 104 tokens is below the 512-token minimum
- sustained-event-store: Median output 68 tokens is below the 512-token minimum

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GiB) | VRAM peak / total (GiB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 12.14 | 76.62 | 12.8 / 59.2 | 15.9 / 15.9 | 90.85 | 265.86 | 55 | 0 / 0 | 109 | 1.00 |
| sustained-lru-cache | 15.23 | 95.70 | 12.9 / 59.2 | 15.9 / 15.9 | 96.13 | 275.87 | 53 | 0 / 0 | 16 | 1.00 |
| sustained-tokenizer | 11.63 | 73.45 | 12.9 / 59.2 | 15.9 / 15.9 | 95.13 | 252.39 | 53 | 0 / 0 | 1 | 1.000 |
| sustained-event-store | 12.15 | 76.21 | 12.9 / 59.2 | 15.9 / 15.9 | 97.78 | 248.27 | 53 | 0 / 0 | 2 | 1.00 |
| context-32k | 8.21 | 51.91 | 13.2 / 59.2 | 15.9 / 15.9 | 82.41 | 240.77 | 54 | 0 / 0 | 50 | 1.00 |
| context-64k | 8.17 | 51.67 | 13.7 / 59.2 | 15.9 / 15.9 | 99.19 | 283.66 | 55 | 0 / 0 | 75 | 1.00 |
| conversation-64k-replay | 15.27 | 95.81 | 13.6 / 59.2 | 15.9 / 15.9 | 97.62 | 280.70 | 55 | 0 / 0 | 23 | 1.00 |
| conversation-64k-followup | 9.17 | 57.68 | 13.6 / 59.2 | 15.9 / 15.9 | 62.25 | 192.98 | 54 | 0 / 0 | 21 | 1.00 |
| context-120k | 6.35 | 40.58 | 14.3 / 59.2 | 15.9 / 15.9 | 97.48 | 279.08 | 57 | 0 / 0 | 281 | 1.00 |
| reasoning-medium | 13.91 | 87.97 | 14.0 / 59.2 | 15.9 / 15.9 | 96.54 | 266.59 | 56 | 0 / 0 | 11 | 1.00 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
