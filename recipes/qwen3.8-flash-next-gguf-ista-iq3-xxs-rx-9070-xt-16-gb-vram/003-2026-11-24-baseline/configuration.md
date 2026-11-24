<!-- Optional: add an Overview section here to describe how you use this setup. -->

<!-- The generator adds Build and run to the footer when ../setup.md exists. -->

<!-- BEGIN GENERATED CONFIGURATIONS -->

# Qwen3.8-Flash-Next / GGUF ISTA IQ3_XXS / RX 9070 XT / 16 GB VRAM


## Hardware


| Setting | Value |
|---|---|
| GPU | Radeon RX 9070/9070 XT/9070 GRE (gfx1201) |
| CPU | AMD Ryzen 7 9800X3D 8-Core Processor |
| Memory architecture | discrete |
| Dedicated VRAM (GiB) | 16 |
| System RAM (GiB) | 59 |


## Operating system


| Setting | Value |
|---|---|
| Operating system | Ubuntu |
| OS version | 26.10 |
| Kernel version | 7.3.0-11-generic |
| Kernel driver | amdgpu |


## Software


| Setting | Value |
|---|---|
| Agent / harness | llm-recipes baseline suite |
| Harness version | [a1ade8d1](https://github.com/wl04/llm-recipes/commit/a1ade8d1f8d945e5afd67265f7fb1c38707926c5) |
| Inference engine | Strata |
| Engine version | 0.1.67 |
| Engine source version | v0.2.21 |
| Engine source revision | [d46f5f26](https://github.com/Niko1221/Strata/commit/d46f5f268f8ed797e83a5c63a69bffbd7a581cf6) |
| ROCm version | 10.2.0 |
| Compute backend | ROCm / HIP |
| GPU driver | amdgpu |
| Base image tag at preparation | [rocm/dev-ubuntu-24.04:10.2.0-full](https://hub.docker.com/r/rocm/dev-ubuntu-24.04/tags?name=10.2.0-full) |
| Pinned base image | rocm/dev-ubuntu-24.04@sha256:21801c0ba1bc4aba31f81ab11fe576c43daa7f2c7f42bac7baaa4d2f75273f86 |
| API server | Strata |
| API server version / revision | [d46f5f26](https://github.com/Niko1221/Strata/commit/d46f5f268f8ed797e83a5c63a69bffbd7a581cf6) |
| Host Python | 3.14.8 |
| Running image ID | sha256:df7b3ef6d4f55a2951383a29c6eb322f8e5c8f2b1e3caf94e557576ed5029c4b |


## Model


| Setting | Value |
|---|---|
| Model name | Qwen3.8-Flash-Next IQ3_XXS · Strata |
| Model format | GGUF ISTA IQ3 XXS |
| Weight quantization | IQ3_XXS |
| Model repository | [https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF) |
| Model files | IQ3_XXS/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf<br>IQ3_XXS/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00002-of-00002.gguf<br>mmproj-Qwen3.8-Flash-Next-BF16.gguf |
| Model revision | [ed59f920](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/commit/ed59f92082b1e93c0e96d60a8b11aab089b52f09) |
| Draft repository | [https://huggingface.co/Qwen/Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) |
| Draft revision | [de4b8e4d](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/commit/de4b8e4d43b917e7706784d8bb445c9af86a3540) |
| Draft quantization | q2_0 |


## Serving

| Setting | Value |
|---|---|
| Served model id | qwen3.8-flash-next-iq3_xxs |
| Speculative decoding | True |
| Draft method | MTP |
| Context length (tokens) | 131072 |
| KV cache | int8 |
| GPU resident KV cells | 32768 |
| Expert cache | auto |
| Prefill | auto |
| Maximum draft tokens | 4 |
| Minimum draft probability | 0.5 |
| Vision | cpu |
| Minimum image tokens | 1024 |
| Maximum image tokens | 1024 |


## Sampling

| Setting | Value |
|---|---|
| Temperature | 1 |
| Top K | 20 |
| Top P | 0.95 |
| Min P | 0 |
| Repetition penalty | 1 |
| Presence penalty | 0 |


## Thinking

| Setting | Value |
|---|---|
| Thinking enabled | False |
| Thinking control | reasoning_effort=none |


## Requests

| Setting | Value |
|---|---|
| Workload suite | 3 |
| Request endpoint | /v1/chat/completions |
| Streaming | Performance requests streamed |
| Concurrency | 1 |
| Token counting | /v1/messages/count_tokens |

---

[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)

<!-- END GENERATED CONFIGURATIONS -->
