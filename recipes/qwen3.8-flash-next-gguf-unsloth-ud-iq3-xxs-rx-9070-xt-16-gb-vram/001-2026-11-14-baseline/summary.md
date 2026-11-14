# 001 · 2026-11-14 — Baseline

Baseline recorded by the llm-recipes baseline runner (suite 1) with the recipe's launch defaults: 131,072-token context, MTP drafting on, CPU vision at 1,024 image tokens, thinking disabled. The runner started the container itself on a machine 817 s after boot with no model loaded (the second load of this model since boot), ran the suite, and stopped it. The server's startup log was captured; the configuration reflects what it reported.

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
| uptime_s | 817.34 s |
| load_1m | 0.260 load |
| mem_available_gib | 56.69 GiB |
| swap_used_gib | 0.000 GiB |
| gpu_busy_percent | 1.00 % |
| gpu_vram_used_gib | 0.167 GiB |
| gpu_power_w | 10.00 W |
| gpu_temp_c | 32.00 C |


### Phases

| Phase | Status | Duration (s) | System CPU busy (%) | Server CPU (cores) | Server RAM peak (GiB) | System available min (GiB) | VRAM peak (GiB) | GPU power avg (W) |
|---|---|---|---|---|---|---|---|---|
| idle | ok | 30.00 | 0.344 | — | — | 56.65 | 0.167 | 7.10 |
| load | ok | 24.30 | 3.14 | 0.462 | 53.75 | 5.59 | 15.30 | 39.73 |
| settle | ok | 4.00 | 0.324 | 0.003 | 53.67 | 5.58 | 15.30 | 43 |
| loaded_idle | ok | 10.00 | 0.670 | 0.063 | 53.67 | 5.60 | 15.30 | 42.63 |
| unload | ok | 1.10 | 9.35 | — | — | 3.69 | 15.34 | 102.43 |
| after_unload | ok | 10.00 | 0.465 | — | — | 56.69 | 0.167 | 13.18 |

- load: time to ready 24.16 s
- unload: time to stop 1.10 s
- after_unload: vram vs idle 0 GiB
- after_unload: available ram vs idle -0.041 GiB

Warmup: 3 requests, converged, 3.48 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output (s) | Decode, client (tok/s) | Prefill, engine (tok/s) | Decode, engine (tok/s) | Draft acceptance | Finish | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,011 | 1,024 | 0 | 2.67 | 87.66 | 3,026.31 | 86.43 | 60.8% | length |  |
| sustained-lru-cache | ok | 1 | 61 | 2,048 | 0 | 0.554 | 115.46 | 114.66 | 115.39 | 81.9% | length |  |
| sustained-tokenizer | ok | 1 | 58 | 2,048 | 0 | 0.543 | 111.09 | 111.11 | 111.03 | 78.0% | length |  |
| sustained-event-store | ok | 1 | 53 | 2,048 | 0 | 0.520 | 119.28 | 106.64 | 119.19 | 84.2% | length |  |
| context-32k | ok | 1 | 31,892 | 1,024 | 0 | 10.03 | 82.53 | 3,189.84 | 82.46 | 61.1% | length |  |
| context-64k | ok | 1 | 64,503 | 1,014 | 0 | 19.76 | 87.10 | 3,271.61 | 87.02 | 64.2% | stop |  |
| context-120k | ok | 1 | 116,536 | 1,024 | 0 | 36.42 | 87.65 | 3,205.77 | 87.57 | 65.5% | length |  |

- Noise floor, context-8k (5 runs): first output 2.5%, decode rate 4.9% (range over median).

### Resources

| Case | CPU (cores) | System CPU busy (%) | Peak RAM (GiB) | Peak anon RAM (GiB) | Peak file cache (GiB) | Min available RAM (GiB) | Peak VRAM (GiB) | Peak GTT (GiB) | Peak process VRAM (GiB) | GPU busy avg (%) | GPU power avg (W) | GPU temp max (°C) | Swap in (pages) | Swap out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.86 | 42.97 | 53.67 | 49.83 | 3.72 | 4.15 | 15.34 | 0.118 | 15.03 | 98.76 | 264.20 | 54 | 0 | 0 | 143 | 0.500 |
| sustained-lru-cache | 8.07 | 50.59 | 53.45 | 49.61 | 3.72 | 4.38 | 15.34 | 0.118 | 15.03 | 99.64 | 272.64 | 54 | 0 | 0 | 36 | 0.500 |
| sustained-tokenizer | 8.06 | 50.55 | 53.70 | 49.86 | 3.72 | 4.13 | 15.34 | 0.118 | 15.03 | 99.74 | 273.47 | 54 | 0 | 0 | 38 | 0.500 |
| sustained-event-store | 8.04 | 50.40 | 53.60 | 49.76 | 3.72 | 4.23 | 15.34 | 0.118 | 15.03 | 97.51 | 269.05 | 55 | 0 | 0 | 36 | 0.500 |
| context-32k | 5.08 | 31.79 | 53.72 | 49.88 | 3.72 | 4.13 | 15.34 | 0.118 | 15.03 | 98.60 | 270.76 | 54 | 0 | 0 | 45 | 0.500 |
| context-64k | 3.83 | 23.92 | 53.72 | 50.06 | 3.72 | 3.93 | 15.34 | 0.118 | 15.03 | 98.52 | 276.30 | 55 | 0 | 0 | 63 | 0.500 |
| context-120k | 2.94 | 18.31 | 53.65 | 50.29 | 3.54 | 3.70 | 15.34 | 0.118 | 15.03 | 98.99 | 278.79 | 55 | 0 | 0 | 96 | 0.500 |

<!-- END GENERATED RESULTS -->

## Observations

- **Load and footprint.** The load took 24 s to ready. The model files had already been read once since boot, so the page cache may have been warm; a load right after boot in an earlier run of the same configuration took about 26 s. Loading the model removed about 51 GiB from the system's available RAM and held 15.0 GiB of VRAM on the 16 GB card (15.3 GiB device-wide). The idle GPU drew 7.1 W without the model and about 43 W with it loaded and idle.
- **Memory headroom is small.** During the suite the server's cgroup held 53.5–53.7 GiB (49.6–50.3 GiB anonymous, the rest file cache), and system available RAM fell to 3.7 GiB of 64 GiB at its lowest, in the 120K case. No swap activity was observed.
- **Prefill and decode.** First output took 2.7 s at 8,011 input tokens and 36.4 s at 116,536. The engine log reports prompt processing of 3,026–3,272 tokens/s across those cases. Decode ran at 83–88 tokens/s from 8K to 120K input, so long context cost first-output time but little decode speed. The engine's own decode figures agree with the client estimate to within 1.5%.
- **Sustained generation.** The three coding tasks decoded at 111–119 tokens/s and each ran to the 2,048-token output cap, so every reply was long enough to count. The 64K context reply stopped on its own after 1,014 tokens, before its 1,024-token cap, so its decode figure rests on a shorter sample. Draft acceptance was 78–84% on code generation and 61–65% on the code-review prompts.
- **Noise.** Over five runs of the 8K case, first-output latency varied by 2.5% and decode rate by 4.9% (range over median). Differences smaller than about 5% in decode rate between runs are not distinguishable. All other cases are single observations.
- **Functional checks.** Streamed text, the forced tool call with a fixed result, and the shared screenshot all passed. The vision answer matched all nine expected fields; the image-token setting was 1,024.
- **Stopping.** The server stopped in 1.1 s. Afterwards device VRAM was back at the idle level and available RAM within 0.04 GiB of it, so no memory was retained.
- **Limits.** Thresholds for the idle, settle, and warmup phases are provisional. Token counts are the server's reported usage; its tokenizer route counted about 40 more per prompt. The run's raw records and server logs are kept outside the repository.

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
