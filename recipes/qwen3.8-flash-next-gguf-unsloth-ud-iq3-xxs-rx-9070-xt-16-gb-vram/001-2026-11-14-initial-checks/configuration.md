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
| Kernel driver | amdgpu |


## Software


| Setting | Value |
|---|---|
| Check client | Recipe check_generation.py (text, tools, vision, long) |
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
| Software configuration basis | Repository runtime and model locks; build identities were not included in the check outputs |


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
| KV cache | INT8 K and V |
| GPU resident KV cells | 32768 |
| Expert cache | auto |
| Prefill | auto |
| Speculative decoding | MTP enabled |
| Maximum draft tokens | 4 |
| Minimum draft probability | 0.5 |
| Draft vocabulary | draft_vocab.bin |
| Vision | CPU (recipe configuration) |
| Temperature | 1.0 |
| Top k | 20 |
| Top p | 0.95 |
| Min p | 0 |
| Repetition penalty | 1 |
| Presence penalty | 0 |
| Temperature | 0 |
| Thinking during checks | disabled |
| Maximum output tokens | 256 for text/tools/vision; 128 for long context |
| Concurrency | 1 |
| Endpoints | Streamed /v1/chat/completions for text; non-streamed chat for tools/vision; /v1/messages for long context |
| Maximum image tokens | 1024 |
| Configured context length (tokens) | 131072 |
| Configuration basis | Recipe defaults; launch command and engine startup log were not captured |
| Minimum image tokens | 1024 |

---

[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)

<!-- END GENERATED CONFIGURATIONS -->
