# 2026-11-05 — Coding generation and near-128K context

Qwen3.8-27B EXL3 generated successfully on the RX 9070 XT with a 131,072-token allocation, processing approximately 130,000 fresh input tokens with DFlash2 enabled and disabled. The converted DFlash2 draft weighs 0.932 GB.

## Workload

TabbyAPI served sequential, non-streaming completion requests through the recipe's Python helpers. Each request used temperature 0, seed 42, and a 128-token output limit. Every response reached that limit. All reported cached-token counts were zero.

The short check supplied a 24-token prompt asking for an order-preserving Python deduplication function. The long check supplied synthetic service records followed by a request for a Python function counting records by service. It sized the prompt with the server tokenizer and verified the server's input count. Each long request had a fresh identifier at the start, so the workload pattern was shared while the exact prompts differed.

## Statistics

Sessions group requests by context allocation and drafting mode. Context allocation is the configured maximum and cache capacity; input tokens are the actual prompt length. Speeds below are the server's `usage` values, with minor rounding differences from its `timings` fields. Request duration is measured by the client.

| Session | Context allocation | Drafting | Request | Input tokens | Output tokens | Prefill tokens/s | Generation tokens/s | Request seconds |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| #1 | 4,096 | Disabled | 1 | 24 | 128 | 1.32 | 35.95 | 21.747 |
| #1 | 4,096 | Disabled | 2 | 24 | 128 | 72.73 | 43.85 | 3.263 |
| #2 | 4,096 | DFlash2 | 1 | 24 | 128 | 41.38 | 71.47 | 2.373 |
| #2 | 4,096 | DFlash2 | 2 | 24 | 128 | 72.73 | 167.08 | 1.099 |
| #3 | 131,072 | DFlash2 | 1 | 24 | 128 | 70.59 | 155.64 | 1.169 |
| #3 | 131,072 | DFlash2 | 2 | 24 | 128 | 72.73 | 167.29 | 1.105 |
| #4 | 131,072 | DFlash2 | 1 | 129,978 | 128 | 952.50 | 72.21 | 138.304 |
| #4 | 131,072 | DFlash2 | 2 | 129,978 | 128 | 1,015.37 | 83.99 | 129.629 |
| #5 | 131,072 | Disabled | 1 | 129,978 | 128 | 1,064.17 | 22.41 | 127.908 |
| #5 | 131,072 | Disabled | 2 | 129,979 | 128 | 1,062.53 | 22.60 | 128.075 |

Total: 10 requests and 1,280 generated tokens. The initial short request spent 18.17 seconds in prompt processing, consistent with first-use compilation; the second spent 0.33 seconds. Short-prompt rates include substantial fixed overhead.

| Session | Request | Accepted draft tokens | Rejected draft tokens | Acceptance |
|---|---:|---:|---:|---:|
| #2 | 1 / 2 | 108 each | 32 each | 77.1% |
| #3 | 1 / 2 | 108 each | 32 each | 77.1% |
| #4 | 1 | 107 | 40 | 72.8% |
| #4 | 2 | 110 | 16 | 87.3% |

Acceptance is accepted / (accepted + rejected) proposed tokens. Disabled runs reported zero accepted and rejected draft tokens.

## Memory

`amdgpu_top` 0.11.5 reported these snapshots. Device VRAM includes other processes. Python GTT was 8 MiB and total device GTT was 116 MiB in each snapshot. Process/system RAM was not measured.

| Session / phase | Device VRAM (MiB) | Python VRAM (MiB) | Free device VRAM (MiB) |
|---|---:|---:|---:|
| #2 — idle after short requests | 12,143 | 11,825 | 4,161 |
| #3 — idle after short requests | 14,289 | 13,971 | 2,015 |
| #4 — processing long prompt | 14,822 | 14,504 | 1,482 |
| #5 — processing long prompt | 15,065 | 14,747 | 1,239 |

Total reported VRAM capacity was 16,304 MiB. Processing snapshots showed 100% GPU activity and 289–290 W power. These are point-in-time observations, not measured peaks; their difference does not establish relative peak memory requirements for the two modes.

The engine used one visible GPU. Vision was disabled. Upstream ExLlamaV3 normally places unquantized token embeddings in CPU RAM; ordinary CPU allocations are distinct from GTT. Download size therefore differs from resident GPU memory.

## Observations

- Warm short-prompt generation reached 167.08 tokens/s with DFlash2 versus 43.85 tokens/s disabled: approximately 3.81× faster. The short outputs were identical across modes.
- Near 130K input tokens, DFlash2 generated at 72.21–83.99 tokens/s versus 22.41–22.60 tokens/s disabled: approximately 3.2–3.7× faster across these runs.
- Long-prompt prefill took 128.01–136.46 seconds with DFlash2 and 122.14–122.33 seconds disabled. For only 128 output tokens, the baseline finished the whole request sooner in both observed runs.
- The server processed every counted long-prompt token, then generated 128 tokens, within the 131,072-token allocation. Both modes completed twice.
- Some long responses repeated the function in both modes. The task checks execution and throughput; it does not establish retrieval accuracy throughout the context. Fresh identifiers also make exact-output comparisons between long requests inconclusive.
- Two requests per case provide initial observations. Longer outputs and representative interactive workloads would clarify the practical benefit of faster decoding.

[Build and run this recipe](../setup.md)

---

[Configuration](configuration.md) · [Profile YAML](profile.yaml)
