<!-- Optional: add an Overview section here to describe how you use this setup. -->

<!-- The generator adds Build and run to the footer when ../setup.md exists. -->

<!-- BEGIN GENERATED CONFIGURATIONS -->

# Qwen3.8-Flash-Next / GGUF Unsloth UD-IQ3_XXS / RX 9070 XT / 16 GB VRAM


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
| Inference engine | Strata |
| Engine version | 0.1.64 |
| Engine source version | v0.2.18 |
| Engine source revision | [6e38f588](https://github.com/Niko1221/Strata/commit/6e38f588a646c0ee6948a74afbe670eb75896106) |
| ROCm version | 10.2.0 |
| Compute backend | ROCm / HIP |
| GPU driver | amdgpu |
| Base image tag at preparation | [rocm/dev-ubuntu-24.04:10.2.0-full](https://hub.docker.com/r/rocm/dev-ubuntu-24.04/tags?name=10.2.0-full) |
| Pinned base image | rocm/dev-ubuntu-24.04@sha256:21801c0ba1bc4aba31f81ab11fe576c43daa7f2c7f42bac7baaa4d2f75273f86 |
| API server | Strata |
| API server version / revision | [6e38f588](https://github.com/Niko1221/Strata/commit/6e38f588a646c0ee6948a74afbe670eb75896106) |
| Host Python | 3.14.8 |
| Running image ID | sha256:3802d63e9bae0c08a027ea336952d5313b987f576baf1ed90c7218bdca22f2ce |


## Model


| Setting | Value |
|---|---|
| Model name | Qwen3.8-Flash-Next UD-IQ3_XXS · Strata |
| Model format | GGUF Unsloth UD IQ3 XXS |
| Weight quantization | UD-IQ3_XXS |
| Model repository | [https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF) |
| Model files | UD-IQ3_XXS/Qwen3.8-Flash-Next-UD-IQ3_XXS-00001-of-00004.gguf<br>UD-IQ3_XXS/Qwen3.8-Flash-Next-UD-IQ3_XXS-00002-of-00004.gguf<br>UD-IQ3_XXS/Qwen3.8-Flash-Next-UD-IQ3_XXS-00003-of-00004.gguf<br>UD-IQ3_XXS/Qwen3.8-Flash-Next-UD-IQ3_XXS-00004-of-00004.gguf<br>mmproj-Qwen3.8-Flash-Next-BF16.gguf |
| Model revision | [084c631a](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/commit/084c631ac221016019d6e0a863afe92d90edd3b0) |
| Draft repository | [https://huggingface.co/Qwen/Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) |
| Draft revision | [de4b8e4d](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/commit/de4b8e4d43b917e7706784d8bb445c9af86a3540) |
| Draft quantization | q2_0 |


## Serving

| Setting | Value |
|---|---|
| Served model id | qwen3.8-flash-next-ud-iq3_xxs |
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


## Experiment notes

Route tail skipping was off (the Strata v0.2.18 default).

---

[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)

<!-- END GENERATED CONFIGURATIONS -->
