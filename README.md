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

| Model | Software | Hardware | Recipe |
|---|---|---|---|
| Qwen3.8-27B · IQ3_XXS GGUF | LM Studio Bionic · llama.cpp · Vulkan · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Open recipe](recipes/qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram/recipe.md) |
| Qwen3.8-27B · 3 bpw EXL3 | TabbyAPI · ExLlamaV3 · ROCm · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Open recipe](recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/recipe.md) |
| Qwen3.8-Flash-Next · IQ3_XXS GGUF | Strata · ROCm · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Open recipe](recipes/qwen3.8-flash-next-gguf-rx-9070-xt-16-gb-vram/recipe.md) |

## Structure

Each recipe groups dated experiments for a model, format, and hardware combination:

```text
recipes/<model-format-hardware-memory>/
  recipe.md            # Overview and links to experiments
  NNN-YYYY-MM-DD-description/
    profile.yaml       # Hardware, software, model, and settings
    configuration.md   # Generated from this experiment's profile
    summary.md         # Workload, statistics, and observations
    assets/            # Optional screenshots used in the report
```

Container recipes also keep build and serving files at the recipe level. Native configuration filenames depend on the serving software:

```text
recipes/<model-format-hardware-memory>/
  setup.md             # Build, model preparation, and run instructions
  implementation.md    # Optional current implementation details
  config/
    launch.json        # API-server adapter, image, and launch defaults
    <server-config>    # Native serving settings
    models.lock.json   # Model revisions, files, and draft conversion options
  container/           # Dockerfile, pinned dependencies, and build helpers
  scripts/             # Model preparation, serving, and generation checks
  NNN-YYYY-MM-DD-description/          # Configuration snapshot and measured results
```

---

[Adding recipes and results](docs/authoring.md) · [Launcher guide](docs/launcher.md) · [Pi setup](docs/clients/pi.md) · [Development](docs/project-instructions.md)
