# Qwen3.8-Flash-Next / GGUF / RX 9070 XT / 16 GB VRAM

Strata HIP container build and launch configuration for ISTA-DASLab GSQ-RCO IQ3_XXS, MTP drafting, INT8 K/V cache, and CPU vision. The serving defaults are 131,072 context tokens and 32,768 GPU-resident KV cells.

The RX 9070 XT workstation completed image validation, model preparation, streamed text, a tool-call round trip, CPU vision, and a 119,999-token prompt. A long Pi coding session completed 846 requests with 599,207 generated tokens at an aggregate 93.8 tok/s. Measurements are recorded below.

[**Build and run this recipe**](setup.md)

<!-- BEGIN GENERATED EXPERIMENTS -->

## Experiments

| Experiment | Configuration | Results |
|---|---|---|
| 003 · 2026-11-12 — Long coding session in Pi | [Configuration](003-2026-11-12-coding-medium/configuration.md) | [Results](003-2026-11-12-coding-medium/summary.md) |
| 002 · 2026-11-12 — CPU vision with 1,024 image tokens | [Configuration](002-2026-11-12-vision-1024/configuration.md) | [Results](002-2026-11-12-vision-1024/summary.md) |
| 001 · 2026-11-12 — Initial text, tool, vision, and long-context checks | [Configuration](001-2026-11-12-initial-checks/configuration.md) | [Results](001-2026-11-12-initial-checks/summary.md) |

<!-- END GENERATED EXPERIMENTS -->

---

[All recipes](../../README.md) · [Implementation](implementation.md)
