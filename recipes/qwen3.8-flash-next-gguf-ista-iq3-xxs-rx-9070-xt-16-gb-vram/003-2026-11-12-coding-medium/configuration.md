<!-- BEGIN GENERATED CONFIGURATIONS -->

# Qwen3.8-Flash-Next / GGUF ISTA IQ3_XXS / RX 9070 XT / 16 GB VRAM


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
| Harness | Pi |
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


## Model


| Setting | Value |
|---|---|
| Model name | Qwen3.8-Flash-Next |
| Format | GGUF |
| Weight quantization | GSQ-RCO IQ3_XXS |
| Model repository | ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF |
| Model revision | [ed59f920](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/commit/ed59f92082b1e93c0e96d60a8b11aab089b52f09) |
| Draft repository | Qwen/Qwen3.8-Flash-Next |
| Draft revision | [de4b8e4d](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/commit/de4b8e4d43b917e7706784d8bb445c9af86a3540) |
| Draft quantization | Q2_0 experts; Q8_0, BF16 and FP32 dense weights |
| Vision projector | mmproj-Qwen3.8-Flash-Next-BF16.gguf |


## Inference settings


| Setting | Value |
|---|---|
| Context length (tokens) | 131072 |
| KV cache | INT8 K and V |
| GPU resident KV cells | 32768 |
| Expert cache | auto |
| Prefill | auto |
| Speculative decoding | MTP enabled |
| Maximum draft tokens | 4 |
| Minimum draft probability | 0.5 |
| Draft vocabulary | draft_vocab.bin |
| Vision | CPU |
| Expert pool | automatic |
| Conversation cache | automatic |
| Hyper connection projections | Q8_0 (upstream default) |
| Route tail skip | 7 |
| Temperature | 1.0 |
| Top k | 20 |
| Top p | 0.95 |
| Min p | 0 |
| Repetition penalty | 1 |
| Presence penalty | 0 |
| Maximum image tokens | 1024 |
| Minimum image tokens | 1024 |
| Thinking during coding session | enabled |
| Pi reasoning effort | medium |
| Output allowance | Usually 16384 tokens; varies by request |
| Reasoning allowance | Automatic answer room; usually 12288 tokens within the output allowance |

---

[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)

<!-- END GENERATED CONFIGURATIONS -->
