# 001 · 2026-11-14 — Baseline

Baseline recorded by the llm-recipes baseline runner (suite 1) with the recipe's launch defaults: 131,072-token context, MTP drafting on, CPU vision at 1,024 image tokens, thinking disabled. The runner started the container itself on a machine 8,483 s after boot with no model loaded, ran the suite, and stopped it. The server's startup log was captured; the configuration reflects what it reported.

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
| uptime_s | 8,483.00 s |
| load_1m | 0.170 load |
| mem_available_gib | 56.02 GiB |
| swap_used_gib | 0.000 GiB |
| gpu_busy_percent | 1.00 % |
| gpu_vram_used_gib | 0.167 GiB |
| gpu_power_w | 8.00 W |
| gpu_temp_c | 28.00 C |


### Phases

| Phase | Status | Duration (s) | System CPU busy (%) | Server CPU (cores) | Server RAM peak (GiB) | System available min (GiB) | VRAM peak (GiB) | GPU power avg (W) |
|---|---|---|---|---|---|---|---|---|
| idle | ok | 30.00 | 0.389 | — | — | 56.02 | 0.167 | 9.30 |
| load | ok | 36.40 | 2.19 | 0.306 | 52.95 | 12.18 | 15.30 | 37.75 |
| settle | ok | 0.000 | — | — | — | — | — | — |
| loaded_idle | ok | 10.00 | 0.526 | 0.037 | 52.95 | 12.18 | 15.30 | 43.40 |
| unload | ok | 0.871 | 11.10 | — | — | 11.27 | 15.23 | 185.46 |
| after_unload | ok | 10.00 | 0.379 | — | — | 56.36 | 0.167 | 11.66 |

- load: time to ready 36.27 s
- unload: time to stop 0.871 s
- after_unload: vram vs idle 0 GiB
- after_unload: available ram vs idle -0.342 GiB

Warmup: 2 requests, converged, 2.29 s.

### Cases

| Case | Status | Runs | Input tokens | Output tokens | Cached input | First output (s) | Decode, client (tok/s) | Prefill, engine (tok/s) | Decode, engine (tok/s) | Draft acceptance | Finish | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | ok | 5 | 8,012 | 968 | 0 | 2.82 | 91.38 | 2,868.77 | 92.31 | 61.0% | stop |  |
| sustained-lru-cache | ok | 1 | 63 | 2,048 | 0 | 0.538 | 117.33 | 121.86 | 117.26 | 79.2% | length |  |
| sustained-tokenizer | ok | 1 | 60 | 2,048 | 0 | 0.543 | 120.38 | 114.72 | 120.31 | 78.9% | length |  |
| sustained-event-store | ok | 1 | 55 | 2,048 | 0 | 0.489 | 110.65 | 117.02 | 110.60 | 73.4% | length |  |
| context-32k | ok | 1 | 31,888 | 1,024 | 0 | 9.78 | 93.46 | 3,271.57 | 93.37 | 67.4% | length |  |
| context-64k | ok | 1 | 64,502 | 1,024 | 0 | 18.78 | 93.12 | 3,443.78 | 93.03 | 66.1% | length |  |
| context-120k | ok | 1 | 116,536 | 1,024 | 0 | 34.57 | 83.57 | 3,377.46 | 83.52 | 57.3% | length |  |

- Noise floor, context-8k (5 runs): first output 2.8%, decode rate 4.6% (range over median).

### Resources

| Case | CPU (cores) | System CPU busy (%) | Peak RAM (GiB) | Peak anon RAM (GiB) | Peak file cache (GiB) | Min available RAM (GiB) | Peak VRAM (GiB) | Peak GTT (GiB) | Peak process VRAM (GiB) | GPU busy avg (%) | GPU power avg (W) | GPU temp max (°C) | Swap in (pages) | Swap out (pages) | Samples | Max sample gap (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context-8k | 6.71 | 42.02 | 53.09 | 43.50 | 9.96 | 10.35 | 15.33 | 0.118 | 15.02 | 97.09 | 257.83 | 53 | 0 | 0 | 133 | 0.500 |
| sustained-lru-cache | 8.07 | 50.58 | 53.03 | 43.49 | 9.42 | 10.28 | 15.33 | 0.118 | 15.02 | 99.72 | 270.92 | 54 | 0 | 0 | 36 | 0.500 |
| sustained-tokenizer | 8.07 | 50.59 | 52.85 | 43.49 | 9.23 | 10.28 | 15.33 | 0.118 | 15.02 | 99.77 | 274.20 | 54 | 0 | 0 | 35 | 0.500 |
| sustained-event-store | 8.01 | 50.28 | 52.74 | 43.38 | 9.23 | 10.40 | 15.33 | 0.118 | 15.02 | 99.92 | 270.81 | 54 | 0 | 0 | 38 | 0.500 |
| context-32k | 4.86 | 30.47 | 52.76 | 43.41 | 9.23 | 10.37 | 15.34 | 0.118 | 15.03 | 96.12 | 264.48 | 54 | 0 | 0 | 41 | 0.500 |
| context-64k | 3.69 | 23.12 | 52.99 | 44.04 | 9.23 | 9.73 | 15.34 | 0.118 | 15.03 | 97.40 | 273.65 | 54 | 0 | 0 | 60 | 0.500 |
| context-120k | 2.94 | 18.31 | 53.02 | 45.50 | 8.32 | 8.17 | 15.34 | 0.118 | 15.03 | 97.48 | 272.89 | 54 | 0 | 0 | 94 | 0.500 |

<!-- END GENERATED RESULTS -->

## Observations

- **Load and footprint.** The server took 36 s to become ready; its log reports the expert weights read at 1.54 GiB/s. The machine was not freshly booted, so this is not a cold-boot figure. Loading removed about 44 GiB from the system's available RAM and held 15.0 GiB of VRAM on the 16 GB card (15.3 GiB device-wide). The idle GPU drew 9.3 W without the model and about 43 W with it loaded and idle. The settle phase took no time: the server was already quiet when it became ready.
- **Memory headroom.** During the suite the server's cgroup held 52.7–53.1 GiB (43.4–45.5 GiB anonymous, the rest file cache). System available RAM fell to 8.2 GiB of 64 GiB at its lowest, in the 120K case, and it shrank as the input grew. No swap activity was observed.
- **Prefill and decode.** First output took 2.8 s at 8,012 input tokens and 34.6 s at 116,536. The engine log reports prompt processing of 2,869–3,444 tokens/s across those cases. Decode ran at 84–93 tokens/s from 8K to 120K input, lowest at 120K. The engine's own decode figures agree with the client estimate to within 1.0%.
- **Sustained generation.** The three coding tasks decoded at 111–120 tokens/s and each ran to the 2,048-token output cap. Draft acceptance was 73–79% on code generation and 57–67% on the code-review prompts.
- **8K probe.** The five runs produced a median of 968 output tokens, below the 1,024-token cap, because three of the five replies ended on their own (892–968 tokens) at temperature 1. Over those runs first-output latency varied by 2.8% and decode rate by 4.6% (range over median), so differences smaller than about 5% in decode rate between runs are not distinguishable. All other cases are single observations.
- **Functional checks.** Streamed text, the forced tool call with a fixed result, and the shared screenshot all passed. The vision answer matched all nine expected fields at 1,024 image tokens.
- **Stopping.** The server stopped in 0.9 s. Afterwards device VRAM was back at the idle level and available RAM within 0.34 GiB of it.
- **Limits.** Thresholds for the idle, settle, and warmup phases are provisional. Token counts are the server's reported usage; its tokenizer route counted about 40 more per prompt. The run's raw records and server logs are kept outside the repository.

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)
