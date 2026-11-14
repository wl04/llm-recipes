# Qwen3.8-Flash-Next / Unsloth Dynamic v3.1 UD-IQ3_XXS

## Runtime and capacity

Build and check the shared [Strata runtime](../../docs/runtimes/strata.md#build-and-check).

Allow at least **110 GB additional free disk space** for 83.63 GB of target shards, the projector, MTP preparation, and pack outputs. Expert weights total **46.84 GiB**, about **7.38 GB more RAM** than the ISTA setup. With 64 GB RAM, close memory-heavy applications and watch RAM, swap, and VRAM during loading and long-context checks. Workstation loading and generation remain to be validated for this recipe.

## Prepare models

Run from the repository root with the serving instance stopped:

```bash
python3 runtimes/strata/scripts/prepare_models.py \
  --recipe recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram \
  --models "$HOME/Models/llm-recipes"
```

The [model lock](config/models.lock.json) selects four target shards, a BF16 CPU projector, Q2_0 MTP, and `--compat-bf16` conversion for small tensors. Experts and the PLE table retain their published formats. Files are prepared separately under `$HOME/Models/llm-recipes/strata-unsloth`.

## Launch

Run one model instance at a time on the RX 9070 XT workstation. Stop the other recipe's instance before switching, then:

```bash
python3 scripts/launch.py doctor qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram \
  --models "$HOME/Models/llm-recipes"
python3 scripts/launch.py start qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram \
  --name strata-unsloth --detach \
  --draft on --vision cpu --context 131072 \
  --models "$HOME/Models/llm-recipes" \
  --logs "$HOME/Models/llm-recipes/logs/strata-unsloth"
python3 scripts/launch.py logs strata-unsloth --follow
```

Readiness: `curl -f http://127.0.0.1:8080/health`. The API is `http://127.0.0.1:8080/v1` and serves `qwen3.8-flash-next-ud-iq3_xxs`.

[Launch defaults](config/launch.json): 131,072 context tokens, MTP on, CPU vision. [Native settings](config/strata.json) contain sampling, cache, and image-token settings; restart after editing them.

## Checks

After readiness:

```bash
check=runtimes/strata/scripts/check_generation.py
python3 "$check" text --model qwen3.8-flash-next-ud-iq3_xxs
python3 "$check" tools --model qwen3.8-flash-next-ud-iq3_xxs
python3 "$check" vision --model qwen3.8-flash-next-ud-iq3_xxs --image /path/to/screenshot.png
python3 "$check" long --model qwen3.8-flash-next-ud-iq3_xxs --input-tokens 120000
```

See [check behavior](../../docs/runtimes/strata.md#checks-and-clients) for sampling, token limits, and interpreting the output.

## Pi

Follow [Pi setup](../../docs/clients/pi.md#configure-a-recipe) using [`config/pi.models.json`](config/pi.models.json). Select `strata-unsloth` with `/model`. The example uses 131,072 context tokens and text/image input.

## Logs and stopping

```bash
python3 scripts/launch.py logs strata-unsloth --follow
python3 scripts/launch.py stop strata-unsloth
```

See [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and [Strata file logs](../../docs/runtimes/strata.md#serving).

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/strata.md)
