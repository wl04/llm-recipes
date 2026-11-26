# 003 · 2026-11-26 — Baseline

<!-- BEGIN GENERATED RUN CONFIGURATION -->

## Run configuration

| Setting | Value |
|---|---|
| Runtime | ExLlamaV3 1.6.6 |
| GPU stack | ROCm 10.1.0 · Radeon RX 9070/9070 XT/9070 GRE (gfx1201) |
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
| context-8k | ok | 5/5 | 8,145 | 1,024 | 0 | 5.67 (5.60 to 5.67) | 5.67 (5.60 to 5.67) | 71.08 (66.40 to 80.30) |
| context-120k | ok | 2/2 | 119,542 | 1,024 | 0 | 116.24 (115.76 to 116.73) | 116.24 (115.76 to 116.73) | 38.28 (37.64 to 38.91) |
| context-64k | ok | 1/1 | 65,225 | 1,024 | 0 | 54.32 | 54.32 | 44.50 |
| conversation-64k-replay | ok | 1/1 | 65,225 | 1,024 | 65,024 | 0.806 | 0.806 | 44.67 |
| conversation-64k-followup | ok | 2/2 | 65,260 | 256 | 65,024 | 3.36 (0.837 to 5.89) | 3.36 (0.837 to 5.89) | 42.75 (40.05 to 45.45) |

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 452 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 1 h 50 min |
| RAM used / total (GiB) | 7.7 / 59.2 |
| Swap used / total (GiB) | 0.0 / 8.0 |
| GPU busy (%) | 3 |
| VRAM used / total (GiB) | 0.2 / 15.9 |
| GPU power (W) | 14.00 |
| GPU temperature (°C) | 31 |

Warmup: 4 requests, converged, 4.62 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output / visible (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,145 | 1,024 | 0 | 5.67 / 5.67 | 1,469.11 | 71.08 | 29.9% | length (4), stop (1) |
| sustained-lru-cache | ok | 1 | 64 | 2,048 | 0 | 0.718 / 0.718 | 100 | 135.72 | 62.3% | length |
| sustained-tokenizer | insufficient_sample | 1 | 61 | 96 | 0 | 0.716 / 0.716 | 95.31 | 135.59 | 54.3% | tool_calls |
| sustained-event-store | insufficient_sample | 1 | 56 | 105 | 0 | 0.725 / 0.725 | 86.15 | 140.12 | 57.1% | tool_calls |
| context-32k | ok | 1 | 32,592 | 1,024 | 0 | 24.99 / 24.99 | 1,308.92 | 56.33 | 26.5% | length |
| context-64k | ok | 1 | 65,225 | 1,024 | 0 | 54.32 / 54.32 | 1,205.64 | 44.50 | 26.7% | length |
| conversation-64k-replay | ok | 1 | 65,225 | 1,024 | 65,024 | 0.806 / 0.806 | 314.06 | 44.67 | 27.0% | length |
| conversation-64k-followup | ok | 2 | 65,260 | 256 | 65,024 | 3.36 / 3.36 | 73.98 | 42.75 | 24.8% | length |
| context-120k | ok | 2 | 119,542 | 1,024 | 0 | 116.24 / 116.24 | 1,030.54 | 38.28 | 31.4% | length |
| reasoning-medium | ok | 1 | 117 | 323 | 0 | 1.40 / 4.24 | 88.64 | 97.36 | 41.3% | stop |

- Noise floor, context-8k (5 runs): first output 1.4%, decode rate 19.6% (range over median).
- Noise floor, context-120k (2 runs): first output 0.8%, decode rate 3.3% (range over median).
- sustained-tokenizer: Median output 96 tokens is below the 512-token minimum
- sustained-event-store: Median output 105 tokens is below the 512-token minimum

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GiB) | VRAM peak / total (GiB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 1.04 | 6.68 | 12.4 / 59.2 | 15.8 / 15.9 | 99.03 | 283.71 | 54 | 0 / 0 | 97 | 1.00 |
| sustained-lru-cache | 1.05 | 6.72 | 11.2 / 59.2 | 15.8 / 15.9 | 99 | 281.39 | 54 | 0 / 0 | 16 | 1.00 |
| sustained-tokenizer | 1.04 | 6.90 | 11.3 / 59.2 | 15.8 / 15.9 | 98.29 | 255.96 | 54 | 0 / 0 | 2 | 1.00 |
| sustained-event-store | 1.05 | 6.76 | 11.3 / 59.2 | 15.8 / 15.9 | 99 | 256.98 | 54 | 0 / 0 | 1 | 1.00 |
| context-32k | 1.02 | 7.02 | 11.6 / 59.2 | 15.8 / 15.9 | 99.30 | 281.86 | 55 | 0 / 0 | 43 | 1.00 |
| context-64k | 1.02 | 7.47 | 13.3 / 59.2 | 15.8 / 15.9 | 99.56 | 284.23 | 57 | 0 / 0 | 78 | 1.00 |
| conversation-64k-replay | 1.04 | 7.04 | 13.4 / 59.2 | 15.8 / 15.9 | 98.46 | 282.97 | 57 | 0 / 0 | 23 | 1.00 |
| conversation-64k-followup | 1.03 | 8.55 | 13.8 / 59.2 | 15.8 / 15.9 | 72.27 | 218.15 | 56 | 0 / 0 | 19 | 1.00 |
| context-120k | 1.01 | 7.25 | 13.9 / 59.2 | 15.9 / 15.9 | 99.50 | 283.70 | 57 | 0 / 0 | 286 | 1.00 |
| reasoning-medium | 0.969 | 7.38 | 13.8 / 59.2 | 15.8 / 15.9 | 87.52 | 232.44 | 57 | 0 / 0 | 5 | 1.00 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
