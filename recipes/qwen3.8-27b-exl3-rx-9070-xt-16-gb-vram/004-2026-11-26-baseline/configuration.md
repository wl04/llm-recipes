<!-- Optional: add an Overview section here to describe how you use this setup. -->

<!-- The generator adds Build and run to the footer when ../setup.md exists. -->

<!-- BEGIN GENERATED CONFIGURATIONS -->

# Qwen3.8-27B / EXL3 / RX 9070 XT / 16 GB VRAM


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
| Harness version | https://github.com/wl04/llm-recipes/commit/49d32e281bfdc155dfa8d8ea5448da14427ea9bc (dirty) |
| Inference engine | ExLlamaV3 |
| Engine version | 1.6.7 |
| Engine source version | v1.6.7 |
| Engine source revision | [8c593e4e](https://github.com/turboderp-org/exllamav3/commit/8c593e4e5c88da76a4aaf8f1b1838bb7c1fce4e0) |
| ROCm version | 10.2.0 |
| Compute backend | ROCm / HIP |
| GPU driver | amdgpu |
| PyTorch | 2.15.0+rocm10.2.0 |
| Python | 3.12 |
| Base image tag at preparation | [rocm/pytorch:rocm10.2.0_ubuntu24.04_py3.12_pytorch_release_2.15.0](https://hub.docker.com/r/rocm/pytorch/tags?name=rocm10.2.0_ubuntu24.04_py3.12_pytorch_release_2.15.0) |
| Pinned base image | rocm/pytorch@sha256:fe66c7b7b2d746d028471685eab44b399c8a31b89a66bf5ca6c6473cd5432fb1 |
| API server | TabbyAPI |
| API server version / revision | [8f92fac5](https://github.com/theroyallab/tabbyAPI/commit/8f92fac5d9307bf1e09668c3715b32ff46ad0333) |
| Host Python | 3.14.8 |
| Running image ID | sha256:19db105c74ec1378bebbcad682b88682abf4f447962275ba99f19df7f81a8a4c |


## Model


| Setting | Value |
|---|---|
| Model name | Qwen3.8-27B EXL3 |
| Model format | EXL3 |
| Model repository | [https://huggingface.co/turboderp/Qwen3.8-27B-exl3](https://huggingface.co/turboderp/Qwen3.8-27B-exl3) |
| Model revision | [86b95530](https://huggingface.co/turboderp/Qwen3.8-27B-exl3/commit/86b95530f9d365d90dd24d01a997a8de0cdf6c55) |
| Draft repository | [https://huggingface.co/z-lab/Qwen3.8-27B-DFlash2](https://huggingface.co/z-lab/Qwen3.8-27B-DFlash2) |
| Draft revision | [50307d4c](https://huggingface.co/z-lab/Qwen3.8-27B-DFlash2/commit/50307d4c4cde6860d4eee73e2547cd786fe8e8a4) |
| Draft quantization | -b 3.0 --out_scales always -cb mul1 |


## Serving

| Setting | Value |
|---|---|
| Served model id | qwen3.8-27b-exl3-3bpw |
| Speculative decoding | True |
| Context length (tokens) | 131072 |
| Cache capacity | 131072 |
| Target cache | Q4 |
| Draft cache | Q4 |
| Chunk size | 1024 |
| Maximum batch size | 1 |
| Vision | True |
| Tensor parallel | False |
| System recurrent cache budget (MB) | 4096 |


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
| Thinking control | chat_template_kwargs.enable_thinking=false |


## Requests

| Setting | Value |
|---|---|
| Workload suite | 3 |
| Request endpoint | /v1/chat/completions |
| Streaming | Performance requests streamed |
| Concurrency | 1 |
| Token counting | /v1/token/encode |

---

[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml) · [Results data](results.json)

<!-- END GENERATED CONFIGURATIONS -->
