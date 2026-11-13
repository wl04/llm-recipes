# Qwen3.8-27B EXL3 setup

Run the 3 bpw target with a 3 bpw DFlash2 draft, optional GPU vision, and TabbyAPI. Tested on RX 9070 XT (16 GB VRAM), Ryzen 7 9800X3D, and 64 GB RAM.

## Runtime

Build and check the shared [ExLlamaV3 / TabbyAPI runtime](../../docs/runtimes/exllamav3-tabbyapi.md#build-and-check). The [launch manifest](config/launch.json) selects it. An existing image with the same runtime lock can be reused.

## Prepare models

Allow disk space for approximately 17.3 GB of downloads, converted weights, conversion working files, and the image/build cache. From the repository root:

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

Downloads resume on rerun. After a failed conversion, move its output and work directories aside before retrying. The preparation helper refuses to overwrite them.

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

The manifest defaults to a 4,096-token context, drafting on and vision off; the launch command above overrides context and vision. Edit [tabby.yml](config/tabby.yml) for sampling and other native defaults. Sampling entries use `force: false`; explicit client values take precedence. Thinking is enabled by default, and clients control effort and reasoning budget.

## Pi

Follow [Pi installation](../../docs/clients/pi.md), then merge [`config/pi.models.json`](config/pi.models.json) into `~/.pi/agent/models.json`. Select `tabby-local` / `qwen3.8-27b-exl3-3bpw` through `/model`, and choose effort with `/thinking`.

The example's context is 131,072 and input supports text/images. Match `contextWindow` to the running server; use `input: ["text"]` with vision off. Optional startup settings are `defaultProvider: tabby-local`, `defaultModel: qwen3.8-27b-exl3-3bpw`, and `defaultThinkingLevel: xhigh` in `settings.json`.

For the optional focused-reasoning instruction:

```bash
pi --append-system-prompt "Reason carefully and avoid repeating analysis that has already been resolved. Revisit a conclusion when new evidence contradicts it. When uncertainty remains, prefer a targeted check or test over repeated speculation."
```

This instruction has not been measured on the recipe's coding workload.

## Logs and stopping

```bash
python3 scripts/launch.py logs coding --follow
python3 scripts/launch.py stop coding
```

Ctrl+C exits log following while the detached server continues. TabbyAPI rotates file logs at 20 MB, compresses them, and retains them for one week. Use `--logs` to choose a host directory; the [launcher guide](../../docs/launcher.md) describes default paths and instance management.

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/exllamav3-tabbyapi.md)
