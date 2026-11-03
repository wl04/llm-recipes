# Qwen3.8-27B / LM Studio Bionic

## Overview

Coding work on [gpu-switcher](https://github.com/wl04/gpu-switcher).

<!-- BEGIN GENERATED CONFIGURATIONS -->

## Configurations

Values below are generated from the result profiles. `—` means unspecified.

### 2026-11-02

[Profile](results/2026-11-02/profile.yaml) · [Results](results/2026-11-02/summary.md)

| Field | Value |
|---|---|
| id | rx9070xt-ubuntu-vulkan |
| recipe | qwen3.8-27b-lmstudio-gguf |
| hardware / gpu | AMD Radeon RX 9070 XT |
| hardware / cpu | AMD Ryzen 7 9800X3D |
| hardware / memory / architecture | discrete |
| hardware / memory / dedicated_vram_gib | 16 |
| hardware / memory / system_ram_gib | 64 |
| hardware / memory / unified_memory_gib | — |
| os / name | Ubuntu |
| os / version | 26.10 |
| os / kernel | 7.3.0-10-generic |
| os / kernel_driver | amdgpu |
| software / harness | LM Studio Bionic |
| software / harness_version | 1.1.10 (build 8) |
| software / engine | llama.cpp |
| software / engine_version | 2.67 |
| software / engine_version_note | LM Studio-specific version; upstream llama.cpp version unknown |
| software / backend | Vulkan |
| software / backend_api_version | 1.4.354 |
| software / gpu_driver | Mesa RADV |
| software / gpu_driver_version | 26.2.4-1ubuntu1 |
| speculation | MTP |
| model / name | Qwen3.8-27B |
| model / format | GGUF |
| model / quantization | IQ3_XXS |
| model / repository | https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF |
| model / artifacts | Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf<br>mmproj-Qwen3.8-27B-BF16.gguf |
| settings / Automatic hardware optimization | Off |
| settings / Context length | 131072 |
| settings / GPU offload | 65 (maximum in the UI) |
| settings / CPU thread pool | 6 |
| settings / Evaluation batch size | 2048 |
| settings / Physical batch size | 512 |
| settings / Concurrent predictions | 1 |
| settings / Flash Attention | On |
| settings / K / V cache quantization | Q8_0 / Q8_0 |
| settings / KV cache GPU offload / Unified KV cache | Both on |
| settings / Context checkpoints | 32 |
| settings / Keep model in memory / mmap | Both on |
| settings / Speculative decoding | MTP |
| settings / Max / min draft tokens / draft probability | 3 / 0 / 0 |
| settings / Temperature | 1 |
| settings / Top K | 20 |
| settings / Top P | 0.95 |
| settings / Min P | 0 |
| settings / Repeat penalty | 1 |
| settings / Presence penalty | 0 |
| settings / Seed | Random |
| settings / Enable Thinking | On |
| settings / Reasoning budget | 8192 |
| settings / Limit response length | Off |
| settings / Context overflow | Truncate Middle |
| settings / On-demand tensor loading | Auto |

<!-- END GENERATED CONFIGURATIONS -->
