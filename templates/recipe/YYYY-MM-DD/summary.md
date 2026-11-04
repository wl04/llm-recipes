# YYYY-MM-DD — configuration / workload

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

---

[Profile YAML](profile.yaml)
