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
| Qwen3.8-Flash-Next · ISTA IQ3_XXS GGUF | Strata · ROCm · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Open recipe](recipes/qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram/recipe.md) |

| Qwen3.8-Flash-Next · Unsloth UD-IQ3_XXS GGUF | Strata · ROCm · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Open recipe](recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/recipe.md) |

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

Container recipes select a shared runtime and keep their model-specific configuration:

```text
recipes/<model-format-hardware-memory>/
  setup.md             # Model preparation, launch, and client configuration
  config/
    launch.json        # Shared runtime, data directory, and launch defaults
    <server-config>    # Native serving settings
    models.lock.json   # Model revisions and preparation options
    pi.models.json     # Pi provider metadata
  NNN-YYYY-MM-DD-description/

runtimes/<runtime>/
  runtime.json         # API server, engine, and image reference
  container/           # Dockerfile, dependency locks, build helpers
  scripts/             # Shared preparation, serving, and API checks

docs/runtimes/         # Shared build and operation guides
```

Different models or independently maintained quantizations have separate recipes. Context, sampling, and vision changes are recorded as experiments within the same recipe.

---

[Adding recipes and results](docs/authoring.md) · [Launcher guide](docs/launcher.md) · [Pi setup](docs/clients/pi.md) · [Development](docs/project-instructions.md)
