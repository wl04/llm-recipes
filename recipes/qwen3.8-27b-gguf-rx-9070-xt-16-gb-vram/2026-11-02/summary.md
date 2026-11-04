# 2026-11-02 — Coding workload

## Workload

Development of [gpu-switcher](https://github.com/wl04/gpu-switcher), with growing context, repeated tool calls, and context compaction.

## Statistics

| Sessions | Requests | Generated tokens | Aggregate generation tok/s | Aggregate prefill tok/s |
|---:|---:|---:|---:|---:|
| 5 | 915 | 1,218,469 | 48.92 | 612.92 |

| Session | Requests | Aggregate generation tok/s |
|---|---:|---:|
| #1 | 130 | 52.47 tok/s |
| #2 | 3 | 45.66 tok/s |
| #3 | 518 | 47.06 tok/s |
| #4 | 96 | 49.15 tok/s |
| #5 | 168 | 51.46 tok/s |

Sessions 2 and 3 started after computer reboots, so the conversation context had to be processed again: the initial prefills took **108 seconds for 81.4K tokens** and **114 seconds for 83.9K tokens**, respectively.

Across 14 large prefills, **121–125K input tokens took 197–218 seconds** (570–628 tok/s). Overall MTP acceptance was **64.99%**.

Medians across all five sessions, grouped by context at the end of each request (1K = 1024 tokens):

| Context range | Requests | Median generation tok/s | Median prefill tok/s |
|---|---:|---:|---:|
| Below 32K | 125 | 70.12 tok/s | 756.79 tok/s |
| 32–64K | 252 | 57.54 tok/s | 448.43 tok/s |
| 64–96K | 253 | 50.32 tok/s | 336.06 tok/s |
| 96K and above | 230 | 44.09 tok/s | 272.23 tok/s |

The context table includes 860 responses of at least 128 tokens; output lengths and MTP acceptance vary. Aggregate rates are total tokens divided by the corresponding server processing time. Decode excludes prefill and tool execution. Prefill counts newly processed input tokens, excluding the reused prefix; its medians mix short incremental inputs and large prefills.

## Memory

Snapshot from `amdgpu_top` during GPU activity:

| Metric | Snapshot value |
|---|---:|
| Total VRAM used / available | 16027 / 16304 MiB |
| VRAM remaining | 277 MiB |
| llama-server VRAM | 15856 MiB |
| Total GTT usage | 1768 MiB |
| llama-server GTT | 1659 MiB |

VRAM occupancy is **98.3%**. GTT is GPU-accessible system RAM; its usage alone does not establish that model weights were evicted. These values describe a single snapshot, not peak memory usage.

## Observations

No repetitive loops were observed. Overall experience with LM Studio Bionic was positive.

No OOM or crash was recorded. One request reached 131071 context tokens with `truncated=1`; subsequent processing continued with a shorter context. Some prompt states exceeded the separate 8 GiB prompt-cache limit and were not cached.

---

[Profile YAML](profile.yaml)
