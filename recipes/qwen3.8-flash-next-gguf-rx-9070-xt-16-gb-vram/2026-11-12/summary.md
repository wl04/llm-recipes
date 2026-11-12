# 2026-11-12 — Initial text, tool, vision, and long-context checks

## Workload

Five sequential requests through the recipe's `check_generation.py`: streamed Python code generation, a forced function call followed by a fixed tool result, an image description of an `amdgpu_top` screenshot, and a synthetic service-record prompt near 120K tokens. MTP and CPU vision were enabled throughout, with a 131,072-token context allocation.

Requests used temperature 0 and disabled thinking. Text, tools, and vision allowed up to 256 output tokens; the long-context request allowed 128. The tool check supplied a fixed temperature of 17°C for Belgrade, and the answer reported that value. The long prompt was counted through Strata's Anthropic token-count endpoint and generated through `/v1/messages`.

## Results

| Request | Workload | Input tokens | Output tokens | Prefill time (s) | Prefill tok/s | Generation time (s) | Generation tok/s | Accepted / proposed drafts |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| #1 | Streamed text | 24 | 122 | 0.292 | 82.2 | 1.241 | 98.3 | 88 / 94 (93.6%) |
| #2 | Tool call | 286 | 19 | 0.908 | 314.9 | 0.275 | 69.1 | 13 / 17 (76.5%) |
| #3 | Tool result follow-up | 81 | 13 | 0.414 | 195.8 | 0.175 | 74.4 | 8 / 11 (72.7%) |
| #4 | Screenshot description | 309 | 256 | 0.491 | 629.1 | 2.881 | 88.9 | 135 / 209 (64.6%) |
| #5 | Synthetic service records | 119,999 | 128 | 37.569 | 3,194.1 | 1.266 | 101.1 | 87 / 108 (80.6%) |

Times and rates are engine-reported, with times converted from milliseconds. Input counts are at request start. Every request reported zero reused prompt tokens. Draft acceptance is accepted proposals divided by proposed drafts. Total generated output was 538 tokens.

The long generation HTTP request took 38.88 seconds; the complete check, including token counting, took 39.76 seconds. Its usage reported 1 input token plus 119,998 cache-creation tokens, and zero cache-read tokens. All 119,999 input tokens were processed for this request.

The vision request took 4.75 seconds end to end. Its engine prefill and generation times sum to 3.37 seconds; image processing and other request overhead are included in the remaining time. Both vision and long-context replies stopped at their requested output limits.

## Memory

| Measurement | Observed value | Scope |
|---|---|---|
| Device VRAM after short text/tool checks | 15,737 / 16,304 MiB | `amdgpu_top` snapshot; 567 MiB free |
| Strata process VRAM after short checks | 15,419 MiB | `amdgpu_top` process row |
| Device GTT after short checks | 116 MiB | `amdgpu_top` snapshot |
| System RAM shown with long-context result | 56.60 / 63.60 GB (89%) | System-wide Resources snapshot, units as displayed |
| Swap occupied | 60.04 MB / 8.59 GB | Same snapshot; occupancy, not swap activity |
| Expert arena loaded in RAM | 39.97 GiB | Engine startup |
| GPU expert cache | 9.53 GiB / 5,886 slots | Engine startup |
| KV backing in pinned RAM | 1.55 GiB | 32,768 of 131,072 KV cells per QSA layer resident in VRAM |
| MTP draft layer | 835 MiB VRAM | Engine startup; draft head subsequently reported another 178.4 MiB |

The RAM and VRAM readings come from separate snapshots taken alongside the initial checks. They are point-in-time observations, not peak measurements or readings from the later coding session. System RAM and device VRAM include other applications; the Strata process row isolates its reported VRAM allocation. Swap occupancy does not establish whether swapping occurred during inference.

Strata keeps the expert arena in system RAM and a subset of experts in its GPU cache, with KV backing also in RAM. Both memory pools contribute to this configuration. The engine selected 8,192-token prompt chunks after evaluating the RAM cost of larger chunks. During the long request, 94.74% of KV block reads hit VRAM and 202.5 MiB was read from RAM. Decode expert-cache hit rate was 78.0%, with another 8.6% of routed experts read over PCIe.

## Observations

- Image build, API imports, HIP kernel execution, model preparation, streamed text, tool-call round trip, CPU vision, and the 119,999-token prompt completed successfully.
- The vision response recognized `amdgpu_top` but misread panel names, including “GPU12” and “IdleGPU”. It reached its output cap during the description. The [1,024-token follow-up](../2026-11-12-vision-1024/summary.md) read several visible labels correctly, with end-to-end time increasing from 4.75 to 9.72 seconds. Both descriptions reached the 256-output-token cap.
- Strata's runtime defaults included Q8_0 hyper-connection projections, fused INT8 prompt experts, and route-tail skipping at rank 7. The engine reports that some enabled optimizations can change answers. These settings are part of this measurement.
- The short synthetic outputs establish initial functionality and observed throughput. Sustained coding behavior and accuracy require a representative workload.

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)
