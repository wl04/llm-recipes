# Qwen3.8-27B EXL3 setup

Run the 3 bpw target with a 3 bpw DFlash2 draft, optional GPU vision, and TabbyAPI. Tested on RX 9070 XT (16 GB VRAM), Ryzen 7 9800X3D, and 64 GB RAM.

## Runtime

Build and check the shared [ExLlamaV3 / TabbyAPI runtime](../../docs/runtimes/exllamav3-tabbyapi.md#build-and-check).

## Prepare models

Allow approximately 17.3 GB for downloads, plus space for converted weights, conversion working files, and the image/build cache. From the repository root:

```bash
recipe=recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram
bash runtimes/exllamav3-tabbyapi/scripts/prepare-models.sh "$recipe" download
bash runtimes/exllamav3-tabbyapi/scripts/prepare-models.sh "$recipe" quantize-draft
```

The optional third argument selects an external model directory, defaulting to the data root `~/llm-recipes`. The launcher's `--models` uses the same default. The [model lock](config/models.lock.json) specifies source revisions and conversion options: a 3.0-bit draft target, `mul1` codebook, and output scales enabled.

Prepared folders under `~/llm-recipes/recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/`:

| Folder | Contents |
|---|---|
| `qwen3.8-27b-exl3-3bpw` | Prepared target |
| `qwen3.8-27b-dflash2-source` | Original draft |
| `draft-conversion-work` | Conversion working files |
| `qwen3.8-27b-dflash2-exl3-3bpw` | Converted draft and metadata |

See [preparation and retry behavior](../../docs/runtimes/exllamav3-tabbyapi.md#preparation).

## Launch

```bash
llm-recipes doctor qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram
llm-recipes start qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram \
  --detach --vision on --context 131072
llm-recipes logs qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram --follow
```

The instance name defaults to the recipe identifier; file logs land in `$HOME/llm-recipes/logs/<instance>`.

API: `http://127.0.0.1:5000/v1`; browser chat: `/ui/`; model status: `/ui/status`; the API serves `qwen3.8-27b-exl3-3bpw`.

The manifest defaults to a 4,096-token context, drafting on and vision off; the launch command above overrides context and vision for the tested coding configuration. Override any launch default per start with the matching option ([launch options](../../docs/launcher.md#launch-options)). Edit [tabby.yml](config/tabby.yml) for sampling and other native defaults. Thinking is enabled by default, and clients control effort and reasoning budget.

## Baseline

Run from the repository root:

```bash
sudo -v
python3 scripts/run_baseline.py run qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram \
  --model qwen3.8-27b-exl3-3bpw \
  --context 131072 \
  --vision on \
  --request-extra '{"chat_template_kwargs":{"enable_thinking":false}}'
```

The options match the launch command above, because the manifest defaults to a 4,096-token context with vision off. The explicit model selects the target from TabbyAPI's available models. The request override disables thinking for the baseline. Results and the server logs go to `~/llm-recipes/baselines/<recipe>/<date-time>/`. See the [baseline guide](../../docs/baseline.md) for preconditions, the phases, and how to publish a result.

## Pi

Follow [Pi setup](../../docs/clients/pi.md#configure-a-recipe) using [`config/pi.models.json`](config/pi.models.json). Select `tabby-local` / `qwen3.8-27b-exl3-3bpw`. The example matches the launch command above: 131,072 context tokens and text/image input.

## Logs and stopping

```bash
llm-recipes logs qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram --follow
llm-recipes stop qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram
```

See [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and [TabbyAPI file logs](../../docs/runtimes/exllamav3-tabbyapi.md#serving).

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/exllamav3-tabbyapi.md)
