# Qwen3.8-Flash-Next / GGUF ISTA IQ3_XXS / RX 9070 XT / 16 GB VRAM

Strata HIP container build and launch configuration for ISTA-DASLab GSQ-RCO IQ3_XXS, MTP drafting, INT8 K/V cache, and CPU vision. The serving defaults are 131,072 context tokens and 32,768 GPU-resident KV cells.

A baseline recorded with the baseline runner and a long Pi coding session are listed below. The coding session completed 846 requests with 599,207 generated tokens at an aggregate 93.8 tok/s.

[**Build and run this recipe**](setup.md)

<!-- BEGIN GENERATED EXPERIMENTS -->

## Experiments

| Experiment | Configuration | Results |
|---|---|---|
| 003 · 2026-11-12 — Long coding session in Pi | [Configuration](003-2026-11-12-coding-medium/configuration.md) | [Results](003-2026-11-12-coding-medium/summary.md) |
| 001 · 2026-11-14 — Baseline | [Configuration](001-2026-11-14-baseline/configuration.md) | [Results](001-2026-11-14-baseline/summary.md) |

<!-- END GENERATED EXPERIMENTS -->

---

[All recipes](../../README.md) · [Runtime](../../docs/runtimes/strata.md)
