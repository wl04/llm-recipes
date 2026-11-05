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
| Harness version | 1.1.10 (build 8) |
| Inference engine | llama.cpp |
| Engine version | 2.67 |
| Engine version notes | LM Studio-specific version; upstream llama.cpp version unknown |
| Compute backend | Vulkan |
| Backend API version | 1.4.354 |
| GPU driver | Mesa RADV |
| GPU driver version | 26.2.4-1ubuntu1 |


## Model


| Setting | Value |
|---|---|
| Model name | Qwen3.8-27B |
| Model format | GGUF |
| Weight quantization | IQ3_XXS |
| Model repository | https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF |
| Model files | Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf<br>mmproj-Qwen3.8-27B-BF16.gguf |


## Inference settings


| Setting | Value |
|---|---|
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
| Temperature | 1 |
| Top K | 20 |
| Top P | 0.95 |
| Min P | 0 |
| Repeat penalty | 1 |
| Presence penalty | 0 |
| Seed | Random |
| Enable Thinking | On |
| Reasoning budget | 8192 |
| Limit response length | Off |
| Context overflow | Truncate Middle |
| On-demand tensor loading | Auto |

---

[Results](summary.md) · [Profile YAML](profile.yaml)

<!-- END GENERATED CONFIGURATIONS -->
