# Qwen3.8-27B EXL3 setup

Run the 3 bpw target with a 3 bpw DFlash2 draft, optional GPU vision, and TabbyAPI. Tested on RX 9070 XT (16 GB VRAM), Ryzen 7 9800X3D, and 64 GB RAM.

## Runtime and capacity

Build the image selected by this recipe and run the GPU check:

```bash
python3 scripts/build_runtime.py exllamav3-tabbyapi --recipe qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram --check
```

See the shared [ExLlamaV3 / TabbyAPI runtime](../../docs/runtimes/exllamav3-tabbyapi.md#build-and-check).

## Prepare models

Allow approximately 16 GiB for downloads, plus space for converted weights, conversion working files, and the image/build cache. From the repository root:

```bash
recipe=recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram
bash runtimes/exllamav3-tabbyapi/scripts/prepare-models.sh "$recipe" download
bash runtimes/exllamav3-tabbyapi/scripts/prepare-models.sh "$recipe" quantize-draft
```

The optional third argument selects an external model directory, defaulting to the data root (`~/llm-recipes`, overridable with `LLM_RECIPES_HOME`). The launcher's `--models` uses the same default. The [model lock](config/models.lock.json) specifies source revisions and conversion options: a 3.0-bit draft target, `mul1` codebook, and output scales enabled.

Prepared folders under `~/llm-recipes/recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/`:

| Folder | Contents |
|---|---|
| `qwen3.8-27b-exl3-3bpw` | Prepared target |
| `qwen3.8-27b-dflash2-source` | Original draft |
| `prepared/v1.6.6-tabby-8f92fac5/draft-conversion-work` | Conversion working files |
| `prepared/v1.6.6-tabby-8f92fac5/qwen3.8-27b-dflash2-exl3-3bpw` | Converted draft and metadata |

See [preparation and retry behavior](../../docs/runtimes/exllamav3-tabbyapi.md#preparation).

## Launch

```bash
sudo -v
llm-recipes doctor qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram
llm-recipes start qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram --detach
```

The instance name defaults to the recipe identifier; file logs land in `<models root>/logs/<instance>`.

API: `http://127.0.0.1:5000/v1`; browser chat: `/ui/`; model status: `/ui/status`; the API serves `qwen3.8-27b-exl3-3bpw`.

The [launch defaults](config/launch.json) use a 131,072-token context, DFlash2 drafting, and GPU-resident vision. Use `--context`, `--draft`, or `--vision` to [override them for one launch](../../docs/launcher.md#launch-options). Edit [tabby.yml](config/tabby.yml) for sampling and other native defaults. Thinking is enabled by default, and clients control effort and reasoning budget.

## Baseline

Run with the installed command:

```bash
llm-recipes-baseline run qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram
```

Results and the server logs go to `~/llm-recipes/baselines/<recipe>/<date-time>/`. See the [baseline guide](../../docs/baseline.md) for preconditions, the phases, and how to publish a result.

## Pi

Follow [Pi setup](../../docs/clients/pi.md#configure-a-recipe) using [`config/pi.models.json`](config/pi.models.json). Select `tabby-local` / `qwen3.8-27b-exl3-3bpw`. The provider matches the recipe defaults for context and image input.

## Logs and stopping

```bash
llm-recipes logs qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram --follow
llm-recipes stop qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram
```

See [launcher controls](../../docs/launcher.md#foreground-and-background-execution) and [TabbyAPI file logs](../../docs/runtimes/exllamav3-tabbyapi.md#serving).

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/exllamav3-tabbyapi.md)
