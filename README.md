```text
██╗     ██╗     ███╗   ███╗    ██████╗ ███████╗ ██████╗██╗██████╗ ███████╗███████╗
██║     ██║     ████╗ ████║    ██╔══██╗██╔════╝██╔════╝██║██╔══██╗██╔════╝██╔════╝
██║     ██║     ██╔████╔██║    ██████╔╝█████╗  ██║     ██║██████╔╝█████╗  ███████╗
██║     ██║     ██║╚██╔╝██║    ██╔══██╗██╔══╝  ██║     ██║██╔═══╝ ██╔══╝  ╚════██║
███████╗███████╗██║ ╚═╝ ██║    ██║  ██║███████╗╚██████╗██║██║     ███████╗███████║
╚══════╝╚══════╝╚═╝     ╚═╝    ╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝╚═╝     ╚══════╝╚══════╝
```

Configurations and results from running language models on my own hardware. Each experiment records the model, inference settings, hardware and software, performance, memory usage, and practical observations.

## Recipes

| Model | Software | Hardware | Configuration | Results |
|---|---|---|---|---|
| Qwen3.8-27B · IQ3_XXS GGUF | LM Studio Bionic · llama.cpp · Vulkan · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Configuration](recipes/qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram/2026-11-02/configuration.md) | [Coding workload](recipes/qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram/2026-11-02/summary.md) |

## Structure

```text
recipes/<model-format-hardware-memory>/
  YYYY-MM-DD/
    profile.yaml       # Hardware, software, model, and settings
    configuration.md   # Generated from this experiment's profile
    summary.md         # Workload, statistics, and observations
```

[Adding or updating experiments →](templates/usage.md)
