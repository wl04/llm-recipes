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

The optional third argument selects an external model directory, defaulting to `~/Models/llm-recipes`. Use that same directory with the launcher's `--models`. The [model lock](config/models.lock.json) specifies source revisions and conversion options: a 3.0-bit draft target, `mul1` codebook, and output scales enabled.

| External directory | Contents |
|---|---|
| `qwen3.8-27b-exl3-3bpw` | Prepared target |
| `qwen3.8-27b-dflash2-source` | Original draft |
| `draft-conversion-work` | Conversion working files |
| `qwen3.8-27b-dflash2-exl3-3bpw` | Converted draft and metadata |

See [preparation and retry behavior](../../docs/runtimes/exllamav3-tabbyapi.md#preparation).

## Launch and check

```bash
python3 scripts/launch.py start qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram \
  --name coding --detach --draft on --vision on --context 131072 \
  --models "$HOME/Models/llm-recipes"
python3 scripts/launch.py logs coding --follow
```

API: `http://127.0.0.1:5000/v1`; browser chat: `/ui/`; model status: `/ui/status`. Wait for model readiness, then run:

```bash
python3 runtimes/exllamav3-tabbyapi/scripts/check_generation.py --model qwen3.8-27b-exl3-3bpw
python3 runtimes/exllamav3-tabbyapi/scripts/check_long_context.py --model qwen3.8-27b-exl3-3bpw
```

The manifest defaults to a 4,096-token context, drafting on and vision off; the launch command above overrides context and vision. Edit [tabby.yml](config/tabby.yml) for sampling and other native defaults. Thinking is enabled by default, and clients control effort and reasoning budget.

## Pi

Follow [Pi setup](../../docs/clients/pi.md#configure-a-recipe) using [`config/pi.models.json`](config/pi.models.json). Select `tabby-local` / `qwen3.8-27b-exl3-3bpw`. The example matches the launch command above: 131,072 context tokens and text/image input.

## Logs and stopping

```bash
python3 scripts/launch.py logs coding --follow
python3 scripts/launch.py stop coding
```

See [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and [TabbyAPI file logs](../../docs/runtimes/exllamav3-tabbyapi.md#serving).

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/exllamav3-tabbyapi.md)
