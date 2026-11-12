# ExLlamaV3 / ROCm setup

Run Qwen3.8-27B with DFlash2, optional vision, and a local TabbyAPI endpoint.

## Prerequisites

- Ubuntu with an AMD RDNA4 GPU with at least 16 GB VRAM. Tested on an RX 9070 XT with 64 GB system RAM.
- Docker Engine accessible through `sudo docker`, with `/dev/kfd` and `/dev/dri` available.
- Python 3 on the host for the generation checks.
- Disk space for approximately 17.3 GB of model downloads, plus converted weights, conversion working files, and the Docker image/build cache.
- A checkout of this repository at `~/Dev/llm-recipes`.

The scripts currently select the RX 9070 XT by name. For another RDNA4 GPU, adjust the GPU selection in the image checker, model-preparation helper, and serving launcher.

## Build the image

```bash
cd ~/Dev/llm-recipes
sudo docker build --progress=plain --build-arg MAX_JOBS=4 \
  -t llm-recipes/exl3-rdna4:probe \
  recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/container
```

Lower `MAX_JOBS` if compiler memory use becomes excessive. Verify engine imports and GPU execution:

```bash
sudo docker run --rm \
  --device=/dev/kfd --device=/dev/dri \
  llm-recipes/exl3-rdna4:probe
```

## Prepare the models

From the repository root:

```bash
bash recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/prepare-models.sh download
bash recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/prepare-models.sh quantize-draft
```

The commands download the target and draft models, then convert the draft to EXL3. Files are stored in `~/Models/llm-recipes` and owned by your host user. Both commands accept an alternative directory as their second argument; pass that same directory to `serve.sh --models`.

Interrupted downloads can be rerun. Conversion requires fresh output and working directories; after a failed conversion, move `qwen3.8-27b-dflash2-exl3-3bpw` and `draft-conversion-work` aside before retrying.

## Start the server

```bash
cd ~/Dev/llm-recipes
python3 scripts/launch.py start qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram --name coding \
  --draft on --vision on --context 131072
```

The shared launcher uses Python 3 and `sudo docker`. The image and prepared models from the preceding steps are required. The recipe’s `scripts/serve.sh` selects its own recipe directory and forwards the launch options. `start` takes a recipe identifier; `status`, `logs`, and `stop` take an instance name.

Wait for the model to load and the API to start. The API is available at `http://127.0.0.1:5000/v1`, with a browser chat at `http://127.0.0.1:5000/ui/` and status at `http://127.0.0.1:5000/ui/status`. Local API authentication is disabled.

In another terminal, check generation:

```bash
cd ~/Dev/llm-recipes
python3 recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/check_generation.py
```

The check prints generated text and timings. Run it again to check warm performance after initial compilation.

## Connect Pi

Run [Pi](https://github.com/badlogic/pi-mono) on the Ubuntu host, in the project you want it to work on. It connects to TabbyAPI at `http://127.0.0.1:5000/v1`; Pi handles files, shell commands, and conversation history on the host.

Install Pi using the shared [Pi setup guide](../../docs/clients/pi.md), then configure this recipe below.

### Configure the local model

Use Pi’s standard `~/.pi/agent/` directory. Create it with `mkdir -p ~/.pi/agent` if needed. Merge this provider into `~/.pi/agent/models.json`, preserving any existing providers:

```json
{
  "providers": {
    "tabby-local": {
      "baseUrl": "http://127.0.0.1:5000/v1",
      "api": "openai-completions",
      "apiKey": "local",
      "models": [
        {
          "id": "qwen3.8-27b-exl3-3bpw",
          "name": "Qwen3.8-27B EXL3",
          "reasoning": true,
          "input": ["text", "image"],
          "contextWindow": 131072,
          "thinkingLevelMap": {
            "xhigh": "xhigh"
          },
          "compat": {
            "thinkingFormat": "qwen"
          }
        }
      ]
    }
  }
}
```

To make this model the startup selection, merge these settings into `~/.pi/agent/settings.json`. Keep your existing default provider/model if you prefer selecting this model through `/model`:

```json
{
  "defaultProvider": "tabby-local",
  "defaultModel": "qwen3.8-27b-exl3-3bpw",
  "defaultThinkingLevel": "xhigh"
}
```

### Optional instruction for focused reasoning

To try discouraging repeated reconsideration, launch Pi with an appended system instruction:

```bash
pi --append-system-prompt "Reason carefully and avoid repeating analysis that has already been resolved. Revisit a conclusion when new evidence contradicts it. When uncertainty remains, prefer a targeted check or test over repeated speculation."
```

This optional instruction has not been measured on the recipe’s coding workload.

### Start a session

Once the server is ready, [start Pi in your working project](../../docs/clients/pi.md#start-a-session).

The model's `contextWindow` must match the serving allocation. For text-only serving, use `--vision off` and set `input` to `["text"]` in `models.json`. Open `/model` to reload model configuration and select the local model; `/thinking` changes the thinking setting.

## Manage the server

```bash
python3 scripts/launch.py logs coding --follow
python3 scripts/launch.py stop coding
```

See the [launcher guide](../../docs/launcher.md) for detached startup, Ctrl+C behavior, instance names, ports, and persistent log paths. Add `--detach` to the startup command to run in the background.

The [launch manifest](config/launch.json) defaults to DFlash2 on, GPU vision off, and a 4,096-token context. The startup command above enables vision and sets 131,072 tokens. Pass the model directory selected during preparation with `--models`; use `--logs` to select an existing log directory.

Edit [config/tabby.yml](config/tabby.yml) for sampling and other native server settings, then restart. Clients can override sampling defaults and set `reasoning_budget_tokens` per request. Pi's `/thinking` selects reasoning effort.

TabbyAPI rotates file logs at 20 MB, compresses rotated files, and retains them for one week. For the `coding` instance's default directory:

```bash
ls "${XDG_STATE_HOME:-$HOME/.local/state}/llm-recipes/coding"
less /path/to/selected.log
```

Changes to mounted scripts or serving settings take effect on the next launch. Rebuild the image after changing build inputs or dependency pins.

---

[Recipe](recipe.md) · [Implementation](implementation.md) · [Text results](001-2026-11-05-initial-checks/summary.md) · [Vision results](002-2026-11-05-vision/summary.md)
