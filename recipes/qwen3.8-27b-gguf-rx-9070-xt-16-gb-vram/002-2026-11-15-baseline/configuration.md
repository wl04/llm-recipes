<!-- Optional: add an Overview section here to describe how you use this setup. -->

<!-- The generator adds Build and run to the footer when ../setup.md exists. -->

<!-- BEGIN GENERATED CONFIGURATIONS -->

# Qwen3.8-27B / GGUF / RX 9070 XT / 16 GB VRAM


## Hardware


| Setting | Value |
|---|---|
| GPU | AMD Radeon RX 9070 XT |
| CPU | AMD Ryzen 7 9800X3D |
| Memory architecture | discrete |
| Dedicated VRAM (GB) | 16 |
| System RAM (GB) | 64 |


## Operating system


| Setting | Value |
|---|---|
| Operating system | Ubuntu |
| OS version | 26.10 |
| Kernel version | 7.3.0-10-generic |
| Kernel driver | amdgpu |


## Software


| Setting | Value |
|---|---|
| Agent / harness | LM Studio Bionic |
| Harness version | 1.2.0 (build 2) |
| Inference engine | llama.cpp |
| Engine version | 2.67.0 to 2.73.0 |
| Engine version notes | LM Studio-specific llama.cpp backends; the exact build Bionic 1.2.0 selected for the Vulkan server was not recorded during the run, and installed Vulkan backends range from 2.67.0 to 2.73.0 |
| Compute backend | Vulkan |
| Backend API version | 1.4.354 |
| GPU driver | Mesa RADV |
| GPU driver version | 26.2.4-1ubuntu1 |
| Software configuration basis | Model, context length, suite v2 request policy, corpus hash, and runner commit f78d3db recorded by the baseline run; application and host rows transcribed from the 001-2026-11-02-coding record and the 2026-11-15 capture notes |


## Model


| Setting | Value |
|---|---|
| Model name | Qwen3.8-27B |
| Model format | GGUF |
| Weight quantization | IQ3_XXS |
| Model repository | [https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF](https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF) |
| Model files | Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf<br>mmproj-Qwen3.8-27B-BF16.gguf |


## Inference settings


| Setting | Value |
|---|---|
| Served model id | qwen3.8-27b-gsq-rco |
| Automatic hardware optimization | Off |
| Context length | 131072 |
| GPU offload | 65 (maximum in the UI) |
| CPU thread pool | 6 |
| Evaluation batch size | 2048 |
| Physical batch size | 512 |
| Concurrent predictions | 1 |
| Flash Attention | On |
| K / V cache quantization | Q8_0 / Q8_0 |
| KV cache GPU offload / Unified KV cache | Both on |
| Context checkpoints | 32 |
| Keep model in memory / mmap | Both on |
| Speculative decoding | MTP |
| Max / min draft tokens / draft probability | 3 / 0 / 0 |
| Application UI settings | Carried over from the 001-2026-11-02-coding record; only the context length was reconfirmed by the baseline run |
| Workload suite | 2 |
| Request policy | Performance: temperature 1, top-k 20, top-p 0.95, min-p 0, repetition penalty 1, presence penalty 0. Functional checks: temperature 0. Concurrency 1. Output caps: 1,024 for context cases, 2,048 for sustained generation, 1,536 for reasoning, 512 for vision, 256 for text and conversation. |
| Thinking control | Per request, verified by live probe 2026-11-15: reasoning_effort none for performance and functional requests, reasoning_effort high for the reasoning case. chat_template_kwargs, enable_thinking, and reasoning are accepted but inert on this build; reasoning_effort off answers HTTP 400. |
| Forced tool call | tool_choice required (string form; the object form is rejected with HTTP 400) |
| Request endpoint | /v1/chat/completions; streamed performance requests |
| Token counting | Unavailable — LM Studio exposes no usable tokenize route (tests/fixtures/lmstudio/token_count.unavailable.txt) |
| Cache reuse | Server reports no cached-token counts; the identical warm replay reached first output in 0.47 s versus 2.11 s cold |
| Vision | true — functional check passed (identity 2/2, detail 7/7) with the mmproj adapter loaded |

---

[Recipe](../recipe.md) · [Results](summary.md) · [Profile YAML](profile.yaml) · [Results data](results.json)

<!-- END GENERATED CONFIGURATIONS -->
