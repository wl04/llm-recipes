# Qwen3.8-Flash-Next / ISTA GSQ-RCO IQ3_XXS

## Runtime and capacity

Build and check the shared [Strata runtime](../../docs/runtimes/strata.md#build-and-check).

Allow at least **100 GiB free disk space** for approximately 79 GiB of downloads and preparation outputs. The tested configuration uses 16 GB VRAM and 64 GB RAM; its expert arena is 39.97 GiB.

## Prepare models

Run from the repository root with the serving instance stopped:

```bash
python3 runtimes/strata/scripts/prepare_models.py \
  --recipe recipes/qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram
```

The [model lock](config/models.lock.json) selects two target shards, a BF16 CPU projector, and Q2_0 MTP. Target tensors retain their native formats. Files are prepared under `$HOME/llm-recipes/recipes/qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram/`.

## Launch

Run one model instance at a time on the RX 9070 XT workstation. Stop the other recipe's instance before switching, then:

```bash
llm-recipes doctor qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram
llm-recipes start qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram --detach
```

The instance name defaults to the recipe identifier; file logs land in `$HOME/llm-recipes/logs/<instance>`. The manifest already holds the tested configuration, so the command passes no capacity options.

Readiness: `curl -f http://127.0.0.1:8080/health`. The API is `http://127.0.0.1:8080/v1` and serves `qwen3.8-flash-next-iq3_xxs`.

[Launch defaults](config/launch.json): 131,072 context tokens, MTP on, CPU vision. To change them for one launch, pass the matching options to `start`; edit the manifest to change them persistently ([launch options](../../docs/launcher.md#launch-options)). [Native settings](config/strata.json) contain sampling, cache, and image-token settings; restart the instance after editing them.

## Baseline

Run with the installed command:

```bash
llm-recipes-baseline run qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram
```

Results and the server logs go to `~/llm-recipes/baselines/<recipe>/<date-time>/`. See the [baseline guide](../../docs/baseline.md) for preconditions, the phases, and how to publish a result.

## Pi

Follow [Pi setup](../../docs/clients/pi.md#configure-a-recipe) using [`config/pi.models.json`](config/pi.models.json). Select `strata-local` with `/model`. The entry mirrors the launch defaults: 131,072 context tokens, text/image input.

## Logs and stopping

```bash
llm-recipes logs qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram --follow
llm-recipes stop qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram
```

See [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and [Strata file logs](../../docs/runtimes/strata.md#serving).

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/strata.md)
