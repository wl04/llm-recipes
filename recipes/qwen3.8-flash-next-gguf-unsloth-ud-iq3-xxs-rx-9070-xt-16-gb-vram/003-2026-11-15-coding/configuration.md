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
| Kernel version | 7.3.0-10-generic |
| Kernel driver | amdgpu |


## Software


| Setting | Value |
|---|---|
| Agent / harness | llm-recipes baseline suite |
| Harness version | https://github.com/wl04/llm-recipes/commit/2dc098535faaafee44b55ca61fa0e6c077ba5d16 (dirty) |
| Inference engine | Strata |
| Engine version | 0.1.59.1 |
| Engine source revision | [dbb2d168](https://github.com/Niko1221/Strata/commit/dbb2d168cffa8cf793d9325358809d5263c7c6b0) |
| Compute backend | ROCm / HIP |
| ROCm version | 10.1.0 |
| GPU driver | amdgpu |
| Base image tag at preparation | [rocm/dev-ubuntu-24.04:10.1.0-full](https://hub.docker.com/r/rocm/dev-ubuntu-24.04/tags?name=10.1.0-full) |
| Pinned base image | rocm/dev-ubuntu-24.04@sha256:5ed1362ea542a928651e4c710b44024ebe98870f74159cb70f0265aec8ef0abe |
| API server | Strata |
| API server version / revision | [dbb2d168](https://github.com/Niko1221/Strata/commit/dbb2d168cffa8cf793d9325358809d5263c7c6b0) |
| Host Python | 3.14.8 |
| Running image ID | sha256:afe7c1bff2f14085879a86bfcdc5729996a66beac14edee40207c08e255feca6 |


## Model


| Setting | Value |
|---|---|
| Model name | Qwen3.8-Flash-Next UD-IQ3_XXS · Strata |
| Model format | GGUF Unsloth UD IQ3 XXS |


## Serving

| Setting | Value |
|---|---|
| Speculative decoding | True |
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
| Image Digest | llm-recipes/strata-rdna4@sha256:afe7c1bff2f14085879a86bfcdc5729996a66beac14edee40207c08e255feca6 |


## Sampling

| Setting | Value |
|---|---|
| Temperature | 1 |
| Top K | 20 |
| Top P | 0.95 |
| Min P | 0 |
| Repetition penalty | 1 |
| Presence penalty | 0 |


## Requests

| Setting | Value |
|---|---|
| Request endpoint | /v1/chat/completions |

---

[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)

<!-- END GENERATED CONFIGURATIONS -->
