# Qwen3.8-Flash-Next / Unsloth Dynamic v3.1 UD-IQ3_XXS

## Runtime and capacity

Build and check the shared [Strata runtime](../../docs/runtimes/strata.md#build-and-check).

Allow at least **110 GB additional free disk space** for 83.63 GB of target shards, the projector, MTP preparation, and pack outputs. Expert weights total **46.84 GiB**, about **7.38 GB more RAM** than the ISTA setup. With 64 GB RAM, close memory-heavy applications and watch RAM, swap, and VRAM during loading and long-context checks.

## Prepare models

Run from the repository root with the serving instance stopped:

```bash
python3 runtimes/strata/scripts/prepare_models.py \
  --recipe recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
```

The [model lock](config/models.lock.json) selects four target shards, a BF16 CPU projector, Q2_0 MTP, and `--compat-bf16` conversion for small tensors. Experts and the PLE table retain their published formats. Files are prepared under `$HOME/llm-recipes/recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/`.

## Launch

Run one model instance at a time on the RX 9070 XT workstation. Stop the other recipe's instance before switching, then:

```bash
llm-recipes doctor qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
llm-recipes start qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram --detach
llm-recipes logs qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram --follow
```

The instance name defaults to the recipe identifier; file logs land in `$HOME/llm-recipes/logs/<instance>`. The manifest already holds the tested configuration, so the command passes no capacity options.

Readiness: `curl -f http://127.0.0.1:8080/health`. The API is `http://127.0.0.1:8080/v1` and serves `qwen3.8-flash-next-ud-iq3_xxs`.

[Launch defaults](config/launch.json): 131,072 context tokens, MTP on, CPU vision. To change them for one launch, pass the matching options to `start`; edit the manifest to change them persistently ([launch options](../../docs/launcher.md#launch-options)). [Native settings](config/strata.json) contain sampling, cache, and image-token settings; restart the instance after editing them.

## Baseline

Run from the repository root:

```bash
sudo -v
python3 scripts/run_baseline.py run qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
```

Results and the server logs go to `~/llm-recipes/baselines/<recipe>/<date-time>/`. See the [baseline guide](../../docs/baseline.md) for preconditions, the phases, and how to publish a result.

## Pi

Follow [Pi setup](../../docs/clients/pi.md#configure-a-recipe) using [`config/pi.models.json`](config/pi.models.json). Select `strata-unsloth` with `/model`. The example uses 131,072 context tokens and text/image input.

## Logs and stopping

```bash
llm-recipes logs qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram --follow
llm-recipes stop qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
```

See [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and [Strata file logs](../../docs/runtimes/strata.md#serving).

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/strata.md)
