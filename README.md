```text
██╗     ██╗     ███╗   ███╗    ██████╗ ███████╗ ██████╗██╗██████╗ ███████╗███████╗
██║     ██║     ████╗ ████║    ██╔══██╗██╔════╝██╔════╝██║██╔══██╗██╔════╝██╔════╝
██║     ██║     ██╔████╔██║    ██████╔╝█████╗  ██║     ██║██████╔╝█████╗  ███████╗
██║     ██║     ██║╚██╔╝██║    ██╔══██╗██╔══╝  ██║     ██║██╔═══╝ ██╔══╝  ╚════██║
███████╗███████╗██║ ╚═╝ ██║    ██║  ██║███████╗╚██████╗██║██║     ███████╗███████║
╚══════╝╚══════╝╚═╝     ╚═╝    ╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝╚═╝     ╚══════╝╚══════╝
```

Configurations and results from running language models on my own hardware. Each experiment records the model, inference settings, hardware and software, performance, memory usage, and practical observations.

[![Static and unit checks](https://github.com/wl04/llm-recipes/actions/workflows/check.yml/badge.svg)](https://github.com/wl04/llm-recipes/actions/workflows/check.yml)
[![Python: 3.14+](https://img.shields.io/badge/python-3.14+-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Quick start

Serving needs an AMD Radeon GPU with ROCm support, Docker, Python 3.14 or later, and `sudo` for container access. It runs entirely on your machine.

1. Install the `llm-recipes` command from a checkout. It copies a runtime snapshot to `~/.llm-recipes` and symlinks shims into `~/.local/bin`; keep that directory on `PATH`. The installer requests sudo credentials to check for running containers; file installation runs as your regular user. Re-run the same command after updating the repository.

   ```bash
   git clone https://github.com/wl04/llm-recipes.git && cd llm-recipes
   python3 scripts/install.py install
   llm-recipes list
   ```

2. Open the chosen recipe's `setup.md` (table below). It covers building the container image and preparing model weights — multi-gigabyte downloads with tens of gigabytes of free disk. Prepared models live under `~/llm-recipes/recipes/<recipe-id>/`. The Qwen3.8-27B GGUF recipe has no `setup.md`: it is served by LM Studio on the desktop, so its model comes from the app rather than the launcher.

3. Serve the model on localhost and check it:

   ```bash
   llm-recipes doctor <recipe-id>
   llm-recipes start <recipe-id> --detach
   llm-recipes logs <recipe-id> --follow
   llm-recipes stop <recipe-id>
   ```

   The API is OpenAI-compatible at `http://127.0.0.1:<port>/v1` (port per recipe: 8080 Strata, 5000 TabbyAPI). Connect [Pi](docs/clients/pi.md) from the recipe's `config/pi.models.json` or any OpenAI client.

4. Measure a baseline from the checkout: `sudo -v && python3 scripts/run_baseline.py run <recipe-id>`. For a recipe served by a desktop app, start the app and its API server first — the same command opens a guided interview instead. Published measurements live in each recipe's dated experiment folders.

More detail: [launcher guide](docs/launcher.md) · [machine roots](docs/project-instructions.md#machine-roots) · [baseline contract](docs/baseline.md)

## Recipes

| Model | Software | Hardware | Recipe |
|---|---|---|---|
| Qwen3.8-27B · IQ3_XXS GGUF | LM Studio Bionic · llama.cpp · Vulkan · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Open recipe](recipes/qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram/recipe.md) |
| Qwen3.8-27B · 3 bpw EXL3 | TabbyAPI · ExLlamaV3 · ROCm · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Open recipe](recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/recipe.md) |
| Qwen3.8-Flash-Next · ISTA IQ3_XXS GGUF | Strata · ROCm · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Open recipe](recipes/qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram/recipe.md) |
| Qwen3.8-Flash-Next · Unsloth UD-IQ3_XXS GGUF | Strata · ROCm · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Open recipe](recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/recipe.md) |

## Structure

The repository holds the recipes with their results, the shared container runtimes, and the tooling that serves and measures them:

```text
recipes/            # Experiments grouped by model, format, and hardware
runtimes/           # Shared container runtimes: Dockerfiles, locks, serving scripts
scripts/            # Launcher, baseline harness, installer, and generators
docs/               # Launcher, runtime, baseline, and client guides
templates/          # Scaffolds for new recipes, experiments, and runtimes
assets/             # Screenshots referenced by the guides
tests/              # Repository test suite, run by scripts/check.sh
```

Each recipe groups dated experiments for a model, format, and hardware combination:

```text
recipes/<model-format-hardware-memory>/
  recipe.md            # Overview and links to experiments
  NNN-YYYY-MM-DD-description/
    profile.yaml       # Hardware, software, model, and settings
    configuration.md   # Generated from this experiment's profile
    summary.md         # Workload, statistics, and observations
    results.json       # Optional: baseline measurements rendered into summary.md
    session-results.json # Optional: aggregated coding-session activity
    assets/            # Optional screenshots used in the report
```

Container recipes add a setup guide and keep their model-specific configuration; experiments follow the layout above:

```text
recipes/<model-format-hardware-memory>/
  setup.md             # Model preparation, launch, and client configuration
  config/
    launch.json        # Shared runtime, port, context, drafting, and vision defaults
    <server-config>    # Native serving settings, such as tabby.yml or strata.json
    models.lock.json   # Model revisions, file sizes, and preparation options
    pi.models.json     # Pi provider metadata

runtimes/<runtime>/
  runtime.json         # Adapter, engine, and image reference
  container/           # Dockerfile, dependency locks, build helpers
  scripts/             # Shared preparation, serving, and API checks

docs/runtimes/         # Shared build and operation guides
```

The installed launcher keeps code and machine data outside this checkout:

```text
~/.llm-recipes/        # App snapshot: scripts, runtimes, virtualenv, VERSION
~/llm-recipes/         # Data root: prepared recipes/, baselines/, logs/, .cache/
```

Different models or independently maintained quantizations have separate recipes. Context, sampling, and vision changes are recorded as experiments within the same recipe.

The installed terminal dashboard is available with `llm-recipes tui`; see the [launcher guide](docs/launcher.md#terminal-dashboard).

---

[Adding recipes and results](docs/authoring.md) · [Launcher guide](docs/launcher.md) · [Baseline contract](docs/baseline.md) · [Pi setup](docs/clients/pi.md) · [Development](docs/project-instructions.md)
