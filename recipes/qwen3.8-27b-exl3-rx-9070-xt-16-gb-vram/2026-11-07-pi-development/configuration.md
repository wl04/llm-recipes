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
| Agent / harness | Pi |
| Harness version | 1.5.0 (reported workstation version) |
| Inference engine | ExLlamaV3 |
| Engine version | 1.6.6 |
| Engine version notes | bd1f519172406a9560bd5c90e61000691bb69a07 |
| Compute backend | ROCm / HIP |
| Backend API version | HIP 7.16.26385 |
| GPU driver | amdgpu |
| PyTorch | 2.14.0+rocm10.1.0 |
| Python | 3.12.3 |
| Docker Engine | 29.9.3 |
| Base image | rocm/pytorch@sha256:099f59a3bee9c436f5cc57db6bc6076fdeda579c57e9e22ae40f856d5905b3e4 |
| API server | TabbyAPI |
| API server revision | 8f92fac5d9307bf1e09668c3715b32ff46ad0333 |


## Model


| Setting | Value |
|---|---|
| Model name | Qwen3.8-27B |
| Model format | EXL3 |
| Weight quantization | SC_3.00bpw_H4 |
| Model repository | turboderp/Qwen3.8-27B-exl3 |
| Target revision | 86b95530f9d365d90dd24d01a997a8de0cdf6c55 |
| Draft repository | z-lab/Qwen3.8-27B-DFlash2 |
| Draft source revision | 50307d4c4cde6860d4eee73e2547cd786fe8e8a4 |
| Draft quantization | 3.0 bpw, mul1 codebook, --out_scales always |
| Converted draft weight size | 0.932 GB (decimal, converted weights) |


## Inference settings


| Setting | Value |
|---|---|
| Speculative decoding | DFlash2 |
| Context length | 131072 |
| Cache capacity | 131072 |
| Target cache | Q4 |
| Draft cache | Q4 |
| Chunk size | 1024 |
| Maximum batch size | 1 |
| Vision | True |
| Vision offload | False |
| Tensor parallel | False |
| GPU selection | RX 9070 XT only (HIP_VISIBLE_DEVICES) |
| Recurrent state | FP16 |
| System recurrent cache MB | 4096 |
| Temperature | 1 |
| Top K | 20 |
| Top P | 0.95 |
| Min P | 0 |
| Repeat penalty | 1 |
| Presence penalty | 0 |
| Thinking enabled | True |
| Server reasoning budget | Unset; client can specify per request |
| Maximum output tokens | 12,297–16,384 per request; 861 of 899 requests use 16,384 |
| Request endpoint | /v1/chat/completions (streaming) |
| Configuration notes | Hardware and build pins follow the existing workstation recipe; startup confirms ExLlamaV3 1.6.6 and the serving settings. Sampling values are server fallbacks; requests explicitly log top-k 20 and top-p 0.95. |

---

[Recipe](../recipe.md) · [Results](summary.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)

<!-- END GENERATED CONFIGURATIONS -->
