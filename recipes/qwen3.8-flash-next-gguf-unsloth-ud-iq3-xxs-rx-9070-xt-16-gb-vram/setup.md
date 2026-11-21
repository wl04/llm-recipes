# Qwen3.8-Flash-Next / Unsloth Dynamic v3.1 UD-IQ3_XXS

## Runtime and capacity

Allow 110 GiB of free disk space for model preparation. The tested system had 16 GB VRAM and 64 GB RAM. From the repository root, build the pinned image and check GPU access:

```bash
recipe=qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
python3 scripts/build_runtime.py strata --recipe "$recipe" --check
```

## Prepare models

```bash
python3 runtimes/strata/scripts/prepare_models.py --recipe "recipes/$recipe" --models "${LLM_RECIPES_HOME:-$HOME/llm-recipes}"
```

The [model lock](config/models.lock.json) selects four target shards, a BF16 CPU projector and Q2_0 MTP. See [prepared files and shared weights](../../docs/runtimes/strata.md#preparation).

## Launch

With the [launcher installed](../../README.md#quick-start) and the GPU free:

```bash
llm-recipes doctor "$recipe"
llm-recipes start "$recipe" --detach
curl --retry 90 --retry-delay 2 --retry-all-errors -fsS http://127.0.0.1:8080/health
```

The [launch defaults](config/launch.json) are 131,072 context tokens, MTP on and CPU vision. The OpenAI-compatible API is at `http://127.0.0.1:8080/v1`. See [native settings](config/strata.json) and [launch overrides](../../docs/launcher.md#launch-options).

Unsloth uses BF16 conversion for small tensors and keeps experts in their published formats. With `STRATA_ROUTE_TAIL_SKIP=0`, Strata includes all routed experts during draft verification, even on a GPU cache miss.

## Baseline

Run with the installed command:

```bash
llm-recipes-baseline run "$recipe"
```

## Pi

For Pi, follow [client setup](../../docs/clients/pi.md#configure-a-recipe) with [this recipe’s model entry](config/pi.models.json) and select `strata-unsloth` with `/model`.

## Logs and stopping

```bash
llm-recipes logs "$recipe" --follow
# Press Ctrl+C to leave the log viewer.
llm-recipes stop "$recipe"
```

See [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and [Strata file logs](../../docs/runtimes/strata.md#serving).

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/strata.md)
