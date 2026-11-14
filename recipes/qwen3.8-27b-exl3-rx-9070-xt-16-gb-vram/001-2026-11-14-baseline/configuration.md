<!-- Optional: add an Overview section here to describe how you use this setup. -->

<!-- The generator adds Build and run to the footer when ../setup.md exists. -->

<!-- BEGIN GENERATED CONFIGURATIONS -->

# Qwen3.8-27B / EXL3 / RX 9070 XT / 16 GB VRAM


## Hardware


| Setting | Value |
|---|---|
| GPU | AMD Radeon RX 9070 XT (gfx1201) |
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
| Agent / harness | llm-recipes baseline runner |
| Harness version | [1a3c7c7a](https://github.com/wl04/llm-recipes/commit/1a3c7c7a934854fb539ccf9beab4a8751818d5b9) |
| Inference engine | ExLlamaV3 |
| Engine version | [v1.6.6](https://github.com/turboderp-org/exllamav3/releases/tag/v1.6.6) |
| Engine commit | [bd1f5191](https://github.com/turboderp-org/exllamav3/commit/bd1f519172406a9560bd5c90e61000691bb69a07) |
| Compute backend | ROCm / HIP |
| Backend API version | HIP 7.16.26385 |
| GPU driver | amdgpu |
| PyTorch | 2.14.0+rocm10.1.0 |
| Python | 3.12.3 |
| Base image tag at preparation | [rocm/pytorch:latest](https://hub.docker.com/r/rocm/pytorch/tags?name=latest) |
| Pinned base image | rocm/pytorch@sha256:099f59a3bee9c436f5cc57db6bc6076fdeda579c57e9e22ae40f856d5905b3e4 |
| API server | TabbyAPI |
| API server revision | [8f92fac5](https://github.com/theroyallab/tabbyAPI/commit/8f92fac5d9307bf1e09668c3715b32ff46ad0333) |
| Host Python | 3.14.8 |
| Running image ID | sha256:118c6aa85e1f40568a0f1023002d321f267ef251b5a6ca7d8678cbf90524c5c6 |
| Software configuration basis | Repository runtime/model locks and native settings; running image ID and engine version recorded by the baseline run |


## Model


| Setting | Value |
|---|---|
| Model name | Qwen3.8-27B |
| Model format | EXL3 |
| Weight quantization | SC_3.00bpw_H4 |
| Model repository | turboderp/Qwen3.8-27B-exl3 |
| Target revision | [86b95530](https://huggingface.co/turboderp/Qwen3.8-27B-exl3/commit/86b95530f9d365d90dd24d01a997a8de0cdf6c55) |
| Draft repository | z-lab/Qwen3.8-27B-DFlash2 |
| Draft source revision | [50307d4c](https://huggingface.co/z-lab/Qwen3.8-27B-DFlash2/commit/50307d4c4cde6860d4eee73e2547cd786fe8e8a4) |
| Draft quantization | 3.0 bpw, mul1 codebook, --out_scales always |
| Converted draft weight size | 0.932 GB (decimal, converted weights) |


## Inference settings


| Setting | Value |
|---|---|
| Speculative decoding | DFlash2 enabled |
| Context length (tokens) | 131072 |
| Cache capacity | Equal to context length |
| Target cache | Q4 |
| Draft cache | Q4 |
| Chunk size | 1024 |
| Maximum batch size | 1 |
| Vision | True |
| Tensor parallel | False |
| Gpu selection | RX 9070 XT only (HIP_VISIBLE_DEVICES) |
| Recurrent state | FP16 |
| System recurrent cache budget (MB) | 4096 |
| Vision weight offload to system RAM | False |
| Workload suite | 1 |
| Request policy | Performance: temperature 1, top-k 20, top-p 0.95, min-p 0, repetition penalty 1, presence penalty 0. Functional checks: temperature 0. Thinking disabled through chat_template_kwargs.enable_thinking=false; concurrency 1. Output caps: 1,024 for context cases, 2,048 for sustained generation, 256 for text/tools, 512 for vision. |
| Request endpoint | /v1/chat/completions; streamed performance requests |
| Token counting | /v1/token/encode |

---

[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)

<!-- END GENERATED CONFIGURATIONS -->
