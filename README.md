# Inference experiments

My model configurations and observations from using them.

## Recipes

| Model | Software | Hardware | Results |
|---|---|---|---|
| [Qwen3.8-27B · IQ3_XXS GGUF](recipes/qwen3.8-27b-lmstudio-gguf/configuration.md) | LM Studio Bionic · llama.cpp · Vulkan · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM | [Coding workload](recipes/qwen3.8-27b-lmstudio-gguf/results/2026-11-02/summary.md) |

## Templates

[Template instructions and folder layout](templates/usage.md)

## Updating configurations

Edit the result's `profile.yaml`, then run [the generator](scripts/generate_configurations.py) to refresh the configuration guide. See [setup and generation commands](templates/usage.md#generate-configuration-guides). Commit the profile and generated Markdown together.
