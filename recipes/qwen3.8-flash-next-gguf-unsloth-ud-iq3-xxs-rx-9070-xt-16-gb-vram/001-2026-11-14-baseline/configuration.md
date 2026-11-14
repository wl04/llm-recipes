<!-- Optional: add an Overview section here to describe how you use this setup. -->

<!-- The generator adds Build and run to the footer when ../setup.md exists. -->

<!-- BEGIN GENERATED CONFIGURATIONS -->

# Qwen3.8-Flash-Next / GGUF Unsloth UD-IQ3_XXS / RX 9070 XT / 16 GB VRAM


## Hardware


| Setting | Value |
|---|---|
| GPU | AMD Radeon RX 9070 XT (gfx1201) |
| CPU | AMD Ryzen 7 9800X3D |
| Memory architecture | discrete |
| Dedicated VRAM (GB) | 16 |
| System RAM (GB) | 64 |
| RAM speed (MT/s) | 5800 |


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
| Harness | llm-recipes baseline runner |
| Harness revision | [f1abc9d3](https://github.com/wl04/llm-recipes/commit/f1abc9d3406b0f0baf3515775841c23f35380941) |
| API server | Strata serve.server |
| Engine | Strata |
| Engine version | 0.1.59.1 |
| Strata revision | [dbb2d168](https://github.com/Niko1221/Strata/commit/dbb2d168cffa8cf793d9325358809d5263c7c6b0) |
| Compute backend | ROCm / HIP |
| Base image tag at preparation | [rocm/dev-ubuntu-24.04:10.1.0-full](https://hub.docker.com/r/rocm/dev-ubuntu-24.04/tags?name=10.1.0-full) |
| Pinned base image | rocm/dev-ubuntu-24.04@sha256:5ed1362ea542a928651e4c710b44024ebe98870f74159cb70f0265aec8ef0abe |
| Vision engine | llama.cpp mtmd (CPU) |
| Vision engine release | [b11062](https://github.com/ggml-org/llama.cpp/releases/tag/b11062) |
| Vision revision | [3cf03257](https://github.com/ggml-org/llama.cpp/commit/3cf03257f219afbe7334045ff7c6a06ac68c627d) |
| Host Python | 3.14.8 |
| Running image ID | sha256:afe7c1bff2f14085879a86bfcdc5729996a66beac14edee40207c08e255feca6 |
| Software configuration basis | Repository runtime and model locks; the running image ID and the engine startup log were captured by the baseline run |


## Model


| Setting | Value |
|---|---|
| Model name | Qwen3.8-Flash-Next |
| Format | GGUF |
| Weight quantization | Unsloth Dynamic v3.1 UD-IQ3_XXS |
| Model repository | [https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF) |
| Model revision | [084c631a](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/commit/084c631ac221016019d6e0a863afe92d90edd3b0) |
| Draft repository | Qwen/Qwen3.8-Flash-Next |
| Draft revision | [de4b8e4d](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/commit/de4b8e4d43b917e7706784d8bb445c9af86a3540) |
| Draft quantization | Q2_0 experts; Q8_0, BF16 and FP32 dense weights |
| Vision projector | mmproj-Qwen3.8-Flash-Next-BF16.gguf |
| Preparation | compat-bf16 for small tensors; native experts and PLE |


## Inference settings


| Setting | Value |
|---|---|
| Context length (tokens) | 131072 |
| KV cache | INT8 K and V |
| GPU resident KV cells | 32768 |
| Expert cache | auto; 4628 slots / 8.82 GiB at startup |
| Prefill | auto; 8192-token chunks selected at runtime |
| Speculative decoding | MTP enabled |
| Maximum draft tokens | 4 |
| Minimum draft probability | 0.5 |
| Draft vocabulary | draft_vocab.bin; 106299 tokens in the loaded draft head |
| Vision | CPU; 8 threads |
| Expert pool | 7 workers plus host thread |
| Conversation cache | 1280 MiB; up to 4 parked conversations |
| Hyper connection projections | Q8_0 (upstream default) |
| Route tail skip | 7 |
| Temperature | 1.0 |
| Top k | 20 |
| Top p | 0.95 |
| Min p | 0 |
| Repetition penalty | 1 |
| Presence penalty | 0 |
| Workload suite | 1 |
| Request policy | Performance cases: temperature 1, top-k 20, top-p 0.95, min-p 0, repetition penalty 1, presence penalty 0, thinking disabled, concurrency 1. Functional checks: temperature 0. Output caps: 1,024 tokens for the 8K and context cases, 2,048 for sustained generation, 256 for text and tools, 512 for vision. Streamed /v1/chat/completions; prompts sized with /v1/messages/count_tokens. |
| Minimum image tokens | 1024 |
| Maximum image tokens | 1024 |

---

[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)

<!-- END GENERATED CONFIGURATIONS -->
