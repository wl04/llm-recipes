# NNN · YYYY-MM-DD — Workload / variant

Fill in the information available and remove unused sections.

## Workload

Describe what you were doing: project, conversations, test suite, or benchmark. Include relevant harness options, tool use, concurrency, and context compaction.

## Statistics

| Sessions | Requests | Generated tokens | Aggregate generation tok/s | Aggregate prefill tok/s |
|---:|---:|---:|---:|---:|
| | | | | |

| Session | Requests | Aggregate generation tok/s |
|---|---:|---:|
| #1 | | |

| Context range | Requests | Median generation tok/s | Median prefill tok/s |
|---|---:|---:|---:|
| | | | |

Define context (at request start or response end), units, and any response filtering. Aggregate speed is total tokens divided by their total processing time. Note whether generated-token counts include reasoning tokens when known. Describe fresh prompt processing and prefix reuse when relevant.

## Memory

Record device/process VRAM, process/system RAM, GTT or unified memory, and swap when available. Include the measurement tool and whether each figure is a snapshot or an observed peak; note context length when known.

## Observations

Describe responsiveness, useful results, tool behavior, repetitive output, truncation, interruptions, and adjustments. Include speculative acceptance, time to first token, power, or temperatures when useful.

<!-- If ../setup.md exists, use this footer instead:
[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)
-->

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Profile YAML](profile.yaml)

<!-- BEGIN GENERATED SESSION -->

### Session activity

Engine: `strata` · logs: engine.log, server.log
Timestamps: unavailable — this engine logs no per-line times; wall-clock span and window filtering are not applicable.

| Metric | Value |
|---|---|
| Requests completed | 1,926 |
| Cancelled | 0 |
| Started without result | unavailable |
| Wall-clock span | unavailable |
| Prompt tokens | 137,750,552 |
| Reused prompt tokens | 133,646,462 |
| Fresh prefill tokens | 4,104,090 |
| Generated tokens | 1,195,540 |
| Aggregate prefill (tok/s) | 1,944.4 |
| Aggregate decode (tok/s) | 87.5 |
| Median decode (tok/s) | 86.0 |
| Draft acceptance | 70.0% (722,779 / 983,273) |

### Request size distribution

| Prompt context | Requests | Prompt tokens | Generated tokens |
|---|---|---|---|
| under 2,048 tokens | 33 | 12,967 | 17,016 |
| 2,048-8,191 tokens | 9 | 54,228 | 8,066 |
| 8,192-32,767 tokens | 58 | 1,110,647 | 35,728 |
| 32,768-131,071 tokens | 1,826 | 136,572,710 | 1,134,730 |
<!-- END GENERATED SESSION -->
