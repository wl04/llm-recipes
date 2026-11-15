# 002 · 2026-11-15 — Baseline

<!-- BEGIN GENERATED RESULTS -->

## Baseline results

Suite v2 · run complete · model `qwen3.8-flash-next-ud-iq3_xxs` · configured context 131,072 tokens

### Functional checks

| Check | Status | Details |
|---|---|---|
| text | pass | 500 characters |
| tools | pass | forced call and fixed result handled |
| vision | pass | identity 2/2, detail 7/7 |

### Boot state

| Measurement | Value |
|---|---|
| Uptime | 3 min |
| RAM used / total (GiB) | 2.3 / 59.2 |
| Swap used / total (GiB) | 0.0 / 8.0 |
| GPU busy (%) | 1 |
| VRAM used / total (GiB) | 0.2 / 15.9 |
| GPU power (W) | 10.00 |
| GPU temperature (°C) | 32 |

Warmup: 2 requests, converged, 2.52 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output / visible (s) | Prefill (tok/s) | Decode (tok/s) | Draft acceptance | Finish |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,111 | 1,024 | 0 | 2.70 | 3,041.60 | 89.27 | 63.8% | length (3), stop (2) |
| sustained-lru-cache | ok | 1 | 65 | 2,048 | 0 | 0.551 | 122.87 | 109.60 | 76.7% | length |
| sustained-tokenizer | ok | 1 | 62 | 2,048 | 0 | 0.570 | 112.93 | 115.39 | 79.6% | length |
| sustained-event-store | ok | 1 | 57 | 2,048 | 0 | 0.535 | 110.89 | 107.43 | 78.5% | length |
| context-32k | ok | 1 | 32,538 | 1,024 | 0 | 10.16 | 3,213.95 | 87.53 | 64.0% | length |
| context-64k | ok | 1 | 65,187 | 1,024 | 0 | 19.91 | 3,281.67 | 86.61 | 63.8% | length |
| context-120k | ok | 2 | 119,492 | 1,024 | 0 | 37.10 | 3,227.11 | 85.83 | 64.8% | length |
| conversation-fresh | ok | 1 | 1,146 | 54 | 0 | 0.960 | 1,220.45 | 81.46 | 70.3% | stop |
| conversation-reuse-1 | ok | 1 | 425 | 41 | 0 | 0.614 | 713.09 | 112.71 | 90.6% | stop |
| conversation-reuse-2 | ok | 1 | 778 | 64 | 418 | 0.629 | 589.20 | 78.66 | 68.2% | stop |
| conversation-reuse-3 | ok | 1 | 1,146 | 51 | 1,139 | 0.124 | 66.04 | 89.60 | 73.0% | stop |
| reasoning-medium | ok | 1 | 117 | 307 | 0 | 0.400 / 3.57 | 307.09 | 88.61 | 65.6% | stop |

- Noise floor, context-8k (5 runs): first output 3.2%, decode rate 10.6% (range over median).
- Noise floor, context-120k (2 runs): first output 0.1%, decode rate 5.1% (range over median).

### Conversation reuse

- conversation-fresh, 0.960 s first output, 0 of 1,146 tokens reported cached (full history, cold)
- conversation-reuse-1, 0.614 s first output, 0 of 425 tokens reported cached
- conversation-reuse-2, 0.629 s first output, 418 of 778 tokens reported cached
- conversation-reuse-3, 0.124 s first output, 1,139 of 1,146 tokens reported cached

Cache reuse: observed — up to 99% of prompt tokens reported cached on the replay ladder.

### Resources

| Case | Server CPU (cores) | System CPU busy (%) | RAM peak / total (GiB) | VRAM peak / total (GiB) | GPU busy (%) | GPU power (W) | GPU temp (°C) | Swap in / out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.78 | 42.45 | 54.8 / 59.2 | 15.3 / 15.9 | 96.36 | 257.37 | 53 | 0 / 0 | 67 | 1.00 |
| sustained-lru-cache | 8.06 | 50.54 | 54.6 / 59.2 | 15.3 / 15.9 | 100 | 274.11 | 54 | 0 / 0 | 19 | 1.00 |
| sustained-tokenizer | 8.08 | 50.58 | 54.8 / 59.2 | 15.3 / 15.9 | 98.69 | 271.37 | 54 | 0 / 0 | 19 | 1.00 |
| sustained-event-store | 8.01 | 50.14 | 54.7 / 59.2 | 15.3 / 15.9 | 100 | 270.87 | 54 | 0 / 0 | 19 | 1.00 |
| context-32k | 4.93 | 30.76 | 54.8 / 59.2 | 15.3 / 15.9 | 97.39 | 266.41 | 54 | 0 / 0 | 22 | 1.00 |
| context-64k | 3.83 | 23.98 | 55.0 / 59.2 | 15.3 / 15.9 | 100 | 276.23 | 54 | 0 / 0 | 32 | 1.00 |
| context-120k | 2.96 | 18.62 | 55.4 / 59.2 | 15.3 / 15.9 | 99.52 | 280.88 | 55 | 0 / 0 | 97 | 1.00 |
| conversation-fresh | 7.81 | 48.98 | 54.7 / 59.2 | 15.3 / 15.9 | 100 | 250.23 | 55 | 0 / 0 | 2 | 1.00 |
| conversation-reuse-1 | 7.91 | 49.77 | 54.5 / 59.2 | 15.3 / 15.9 | 96.17 | 251.21 | 55 | 0 / 0 | 1 | 1.00 |
| conversation-reuse-2 | 7.67 | 48.47 | 54.6 / 59.2 | 15.3 / 15.9 | 85.74 | 259.74 | 55 | 0 / 0 | 1 | 1.00 |
| conversation-reuse-3 | 7.98 | 50.18 | 54.8 / 59.2 | 15.3 / 15.9 | 97.23 | 219.16 | 54 | 0 / 0 | 1 | 1.00 |
| reasoning-medium | 7.62 | 48.02 | 54.8 / 59.2 | 15.3 / 15.9 | 98.97 | 252.64 | 55 | 0 / 0 | 4 | 1.00 |

Decode is a client estimate: (output tokens - 1) / (last - first output). Prefill is reported by the engine and is empty when the server reports none.

<!-- END GENERATED RESULTS -->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
