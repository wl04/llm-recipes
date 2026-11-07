# 2026-11-05 — Screenshot reading with GPU-resident vision

Qwen3.8-27B EXL3 correctly read the GPU model and VRAM usage from an `amdgpu_top` screenshot with vision and DFlash2 enabled at a 131,072-token context allocation. Vision weight offload to system RAM was disabled (`vision_offload: false`).

## Workload

One non-streaming chat completion contained a text instruction and a PNG screenshot embedded as a base64 image URL. The instruction asked for the GPU model, used VRAM, and total VRAM. The request used temperature 0, a 256-token output limit, and `enable_thinking: false` in the chat template arguments.

The input was the [GPU snapshot](../2026-11-05/assets/amdgpu-top-dflash2-128k.png) from the earlier text-only DFlash2 run. Its displayed memory figures describe that earlier run. Memory for this vision request is recorded separately below.

## Statistics

| Session | Requests | Input tokens including image | Cached tokens | Generated tokens | Prompt processing seconds | Prefill tokens/s | Generation seconds | Generation tokens/s | Server total seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| #1 | 1 | 5,835 | 0 | 62 | 9.13 | 639.10 | 0.54 | 114.38 | 9.68 |

Values are from the response's `usage` fields. The server also reported 50 accepted and 34 rejected draft tokens: 59.5% acceptance. The response ended naturally at `<|im_end|>` before the output limit, with no reasoning text or tool calls. Image encoding time was not reported separately; the prompt timing is retained as reported by the server.

## Memory

An `amdgpu_top` snapshot after the image request showed:

| Measurement | MiB |
|---|---:|
| Device VRAM used | 16,158 |
| Device VRAM capacity | 16,304 |
| Free device VRAM | 146 |
| Python VRAM | 15,840 |
| Python GTT | 8 |
| Total device GTT | 116 |

These are point-in-time values, not measured peaks. GPU activity was 9% at capture. The snapshot leaves little free device memory; it includes runtime allocations and allocator reservations. Process/system RAM and the vision component's separate resident size were not measured.

## Observations

The model correctly returned all three requested values:

- GPU: AMD Radeon RX 9070 XT
- Used VRAM in the input screenshot: 14,822 MiB
- Total VRAM in the input screenshot: 16,304 MiB

The confirmed context allocation was 131,072 tokens; this request used 5,835 input tokens and 62 output tokens. The result establishes successful screenshot reading with GPU-resident vision and DFlash2 at that allocation. Near-full-context processing was measured separately in the [text-only results](../2026-11-05/summary.md), where vision was disabled.

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)
