# Inference experiments

My model configurations and observations from using them. Each dated experiment contains a configuration snapshot and its results.

## Experiments

| Date | Model | Software | Hardware | Configuration | Results |
|---|---|---|---|---|---|
| 2026-11-02 | Qwen3.8-27B · IQ3_XXS GGUF | LM Studio Bionic · llama.cpp · Vulkan · Ubuntu 26.10 | RX 9070 XT · 16 GB VRAM · Ryzen 7 9800X3D · 64 GB RAM | [Configuration](recipes/qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram/2026-11-02/configuration.md) | [Coding workload](recipes/qwen3.8-27b-gguf-rx-9070-xt-16-gb-vram/2026-11-02/summary.md) |

## Structure

```text
recipes/<model-format-hardware-memory>/
  YYYY-MM-DD/
    profile.yaml       # Hardware, software, model, and settings
    configuration.md   # Generated from this experiment's profile
    summary.md         # Workload, statistics, and observations
```

Each row in the catalog links to one experiment. Related experiments share a recipe folder; configurations recorded on the same date use descriptive folder suffixes.

## Adding or updating experiments

Follow the [template instructions and naming rules](templates/usage.md). Edit the experiment's `profile.yaml` and `summary.md`, then run [the generator](scripts/generate_configurations.py) to refresh its `configuration.md`. Add a catalog row for each new experiment.

See [setup and generation commands](templates/usage.md#generate-configuration-guides). Commit the profile and generated Markdown together.
