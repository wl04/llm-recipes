# Qwen3.8-Flash-Next / ISTA GSQ-RCO IQ3_XXS

## Runtime and capacity

Build and check the shared [Strata runtime](../../docs/runtimes/strata.md#build-and-check).

Allow at least **100 GB free disk space** for approximately 82 GB of downloads and preparation outputs. The tested configuration uses 16 GB VRAM and 64 GB RAM; its expert arena is 39.97 GiB. The [initial results](001-2026-11-12-initial-checks/summary.md) record workstation validation.

## Prepare models

Run from the repository root with the serving instance stopped:

```bash
python3 runtimes/strata/scripts/prepare_models.py \
  --recipe recipes/qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram \
  --models "$HOME/Models/llm-recipes"
```

The [model lock](config/models.lock.json) selects two target shards, a BF16 CPU projector, and Q2_0 MTP. Target tensors retain their native formats. Files are prepared under `$HOME/Models/llm-recipes/strata`.

## Launch

Run one model instance at a time on the RX 9070 XT workstation. Stop the other recipe's instance before switching, then:

```bash
python3 scripts/launch.py doctor qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram \
  --models "$HOME/Models/llm-recipes"
python3 scripts/launch.py start qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram \
  --name strata-coding --detach \
  --draft on --vision cpu --context 131072 \
  --models "$HOME/Models/llm-recipes" \
  --logs "$HOME/Models/llm-recipes/logs/strata-coding"
python3 scripts/launch.py logs strata-coding --follow
```

Readiness: `curl -f http://127.0.0.1:8080/health`. The API is `http://127.0.0.1:8080/v1` and serves `qwen3.8-flash-next-iq3_xxs`.

[Launch defaults](config/launch.json): 131,072 context tokens, MTP on, CPU vision. [Native settings](config/strata.json) contain sampling, cache, and image-token settings; restart after editing them.

## Checks

Run this Bash block from the repository root after startup. Vision uses the shared [amdgpu_top screenshot](../../assets/checks/amdgpu-top.png); use `--image /path/to/image.png` to check another image.

```bash
(
  set -euo pipefail
  out=$(mktemp -d "${TMPDIR:-/tmp}/strata-checks-$(date +%F)-XXXXXX")
  check=runtimes/strata/scripts/check_generation.py
  model=qwen3.8-flash-next-iq3_xxs
  echo "Saving checks to $out"

  curl -fsS http://127.0.0.1:8080/health | tee "$out/health.txt"
  curl -fsS http://127.0.0.1:8080/v1/models | python3 -m json.tool | tee "$out/models.json"
  python3 "$check" text --model "$model" | tee "$out/text.json"
  python3 "$check" tools --model "$model" | tee "$out/tools.json"
  python3 "$check" vision --model "$model" | tee "$out/vision.json"
  python3 "$check" long --model "$model" --input-tokens 120000 | tee "$out/long.json"
)
```

Each helper checks the loaded model ID before generation. The block stops on failure and saves outputs in a fresh temporary directory. Keep any files needed for analysis before clearing temporary storage; summarize results in a numbered experiment. See [check behavior](../../docs/runtimes/strata.md#checks-and-clients) for sampling, token limits, and interpreting the output.

## Pi

Follow [Pi setup](../../docs/clients/pi.md#configure-a-recipe) using [`config/pi.models.json`](config/pi.models.json). Select `strata-local` with `/model`. The example uses 131,072 context tokens and text/image input.

## Logs and stopping

```bash
python3 scripts/launch.py logs strata-coding --follow
python3 scripts/launch.py stop strata-coding
```

See [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and [Strata file logs](../../docs/runtimes/strata.md#serving).

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/strata.md)
