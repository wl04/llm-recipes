# 003 · 2026-11-15 — Coding

<!-- BEGIN GENERATED RUN CONFIGURATION -->

## Run configuration

| Setting | Value |
|---|---|
| Runtime | Strata 0.1.59.1 |
| GPU stack | ROCm 10.1.0 · Radeon RX 9070/9070 XT/9070 GRE (gfx1201) |
| Model | Qwen3.8-Flash-Next UD-IQ3_XXS · Strata |
| Context and cache | 131,072 tokens · INT8 KV · 32,768 GPU-resident cells |
| Drafting and vision | Drafting on · 4 draft tokens · CPU vision · 1,024 image tokens |

<!-- END GENERATED RUN CONFIGURATION -->

<!-- `run_baseline.py session --create` replaces the title line; if you copy this
template by hand, replace the placeholder so it matches the folder. -->

## Workload

The Pi coding session developing this exact repository scripts and documentation

## Observations

There were some mistakes in tool calling and using the todo plugin in Pi, besides this was smooth.

<!-- BEGIN GENERATED SESSION -->

### Session activity

Engine: `strata` · logs: engine.log, server.log
Timestamps: unavailable — this engine logs no per-line times; wall-clock span and window filtering are not applicable.

| Metric | Value |
|---|---|
| Requests completed | 1,947 |
| Cancelled | 0 |
| Started without result | unavailable |
| Wall-clock span | unavailable |
| Prompt tokens | 138,951,134 |
| Reused prompt tokens | 134,747,931 |
| Fresh prefill tokens | 4,203,203 |
| Generated tokens | 1,214,563 |
| Aggregate prefill (tok/s) | 1,954.5 |
| Aggregate decode (tok/s) | 87.5 |
| Median decode (tok/s) | 86.1 |
| Draft acceptance | 70.0% (734,837 / 999,117) |

### Request size distribution

| Prompt context | Requests | Prompt tokens | Generated tokens |
|---|---|---|---|
| under 2,048 tokens | 34 | 13,943 | 17,615 |
| 2,048-8,191 tokens | 9 | 54,228 | 8,066 |
| 8,192-32,767 tokens | 58 | 1,110,647 | 35,728 |
| 32,768-131,071 tokens | 1,846 | 137,772,316 | 1,153,154 |
<!-- END GENERATED SESSION -->

<!-- If ../setup.md exists, use this footer instead:
[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)
-->
---
[Recipe](../recipe.md) · [Configuration](configuration.md) · [Profile YAML](profile.yaml)
