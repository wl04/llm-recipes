# Qwen3.8-Flash-Next / GGUF / RX 9070 XT / 16 GB VRAM

Strata HIP container build and launch configuration for ISTA-DASLab GSQ-RCO IQ3_XXS, MTP drafting, INT8 K/V cache, and CPU vision. The serving defaults are 131,072 context tokens and 32,768 GPU-resident KV cells.

The RX 9070 XT workstation completed image validation, model preparation, streamed text, a tool-call round trip, CPU vision, and a 119,999-token prompt. Initial measurements are recorded below.

[**Build and run this recipe**](setup.md)

<!-- BEGIN GENERATED EXPERIMENTS -->

## Experiments

| Experiment | Configuration | Results |
|---|---|---|
| 2026-11-12 — CPU vision with 1,024 image tokens | [Configuration](2026-11-12-vision-1024/configuration.md) | [Results](2026-11-12-vision-1024/summary.md) |
| 2026-11-12 — Initial text, tool, vision, and long-context checks | [Configuration](2026-11-12/configuration.md) | [Results](2026-11-12/summary.md) |

<!-- END GENERATED EXPERIMENTS -->

---

[All recipes](../../README.md) · [Implementation](implementation.md)
