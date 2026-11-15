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
| Engine version | 2.73.0 |
| Engine version notes | LM Studio-specific version; upstream llama.cpp version unknown |
| Compute backend | Vulkan |
| Backend API version | 1.4.354 |
| GPU driver | Mesa RADV |
| GPU driver version | 26.2.4-1ubuntu1 |
| Software configuration basis | Model, context length, request policy, corpus hash, and runner commit f78d3db recorded by the baseline run; application settings carried over from the 002-2026-11-02-coding record |


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
| Application UI settings | Carried over from the 002-2026-11-02-coding record |
| Workload suite | 2 |
| Request policy | Performance: temperature 1, top-k 20, top-p 0.95, min-p 0, repetition penalty 1, presence penalty 0. Functional checks: temperature 0. Concurrency 1. Output caps: 1,024 for context cases, 2,048 for sustained generation, 1,536 for reasoning, 512 for vision, 256 for text and conversation. |
| Thinking control | Per request: reasoning_effort none for performance and functional requests, reasoning_effort high for the reasoning case |
| Forced tool call | tool_choice required (string form) |
| Request endpoint | /v1/chat/completions; streamed performance requests |
| Token counting | Unavailable — LM Studio exposes no usable tokenize route |
| Vision | true — vision adapter mmproj-Qwen3.8-27B-BF16.gguf loaded |

---

[Recipe](../recipe.md) · [Results](summary.md) · [Profile YAML](profile.yaml) · [Results data](results.json)

<!-- END GENERATED CONFIGURATIONS -->
