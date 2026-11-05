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

| Model | Software | Hardware | Setup | Configuration | Results |
|---|---|---|---|---|---|
| Qwen3.8-27B · IQ3_XXS GGUF | LM Studio Bionic · llama.cpp · Vulkan · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | — | [Configuration](recipes/qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram/2026-11-02/configuration.md) | [Summary](recipes/qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram/2026-11-02/summary.md) |
| Qwen3.8-27B · 3 bpw EXL3 | TabbyAPI · ExLlamaV3 · ROCm · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Build and run](recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/setup.md) | [Configuration](recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/2026-11-05/configuration.md) | [Summary](recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/2026-11-05/summary.md) |

## Structure

Each recipe groups dated experiments for a model, format, and hardware combination:

```text
recipes/<model-format-hardware-memory>/
  YYYY-MM-DD/
    profile.yaml       # Hardware, software, model, and settings
    configuration.md   # Generated from this experiment's profile
    summary.md         # Workload, statistics, and observations
    assets/            # Optional screenshots used in the report
```

The ExLlamaV3 container recipe also keeps its build and serving files at the recipe level:

```text
recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/
  setup.md             # Build, model preparation, and run instructions
  tabby.yml            # Native TabbyAPI serving settings
  models.lock.json     # Model revisions, files, and draft conversion options
  container/           # Dockerfile, pinned dependencies, and build helpers
  scripts/             # Model preparation, serving, and generation checks
  YYYY-MM-DD/          # Configuration snapshot and measured results
```

Model weights and conversion working files live outside the repository and are mounted into the container. Shared experiment templates and documentation are in `templates/`; `scripts/generate_configurations.py` generates configuration guides from profiles.

[Adding or updating experiments →](templates/usage.md)
