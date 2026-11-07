# ExLlamaV3 / ROCm setup

Build the ROCm image, prepare the model weights, and serve Qwen3.8-27B through TabbyAPI. See [measured results](2026-11-05/summary.md) for throughput and memory usage.

## Build on the workstation

After syncing these files to your checkout:

```bash
cd ~/Dev/llm-recipes
sudo docker build --progress=plain --build-arg MAX_JOBS=4 \
  -t llm-recipes/exl3-rdna4:probe \
  recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/container
```

Four compilation jobs are the starting limit for the 64 GB workstation. Lower `MAX_JOBS` if compiler memory use becomes excessive. The first build downloads locked dependencies and compiles the extension; later builds reuse Docker's cache. GPU devices are only required for the run check.

## Check the engine and GPU

```bash
sudo docker run --rm \
  --device=/dev/kfd --device=/dev/dri \
  llm-recipes/exl3-rdna4:probe
```

The checker selects the RX 9070 XT, checks engine imports, and runs a GPU matrix multiplication.

## Build inputs

`container/versions.lock.json` records the tested base digest and exact upstream revisions/archive hashes. `container/requirements.lock` pins and hashes the Python dependencies. The original Torch, ROCm SDK, and Triton remain supplied by the base image. ExLlamaV3 is compiled with build isolation disabled against that Torch, targeting gfx1201.

TabbyAPI's ROCm extra at the selected revision pins Torch 2.13/ROCm 10.0. This build installs its core dependencies and source instead, preserving the tested Torch 2.14/ROCm 10.1 stack. Required source licenses remain in `/opt/src`. No RDNA4 patch set is applied.

The build context contains only recipe build files. Source archives are fetched from upstream with SHA-256 verification. Weights are prepared separately and mounted for serving in the next step. The image currently defaults to the check command; no API service is started.

## Prepare the models

Run from the repository root using the image built above:

```bash
bash recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/prepare-models.sh download
bash recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/prepare-models.sh quantize-draft
```

Both commands accept an optional model directory as their second argument; the default is `~/Models/llm-recipes`. Files are owned by your host user. The helpers are mounted from the checkout, so updating them requires no image rebuild.

`models.lock.json` pins the target EXL3 model and original DFlash2 draft to the revisions inspected on the workstation. Downloading retrieves approximately 17.3 GB, verifies file sizes and upstream Git/LFS hashes, and saves a local checksum manifest. Interrupted downloads can be rerun. Existing completed downloads are verified before reuse.

The second command selects the RX 9070 XT by name and runs the pinned upstream ExLlamaV3 converter with a 3.0-bit target, `mul1` codebook, and output scales enabled. It keeps three separate directories:

| Directory | Contents |
| --- | --- |
| `qwen3.8-27b-dflash2-source` | Original draft weights |
| `draft-conversion-work` | Converter working files |
| `qwen3.8-27b-dflash2-exl3-3bpw` | Converted draft and completion metadata |

The target model is already quantized and stays in `qwen3.8-27b-exl3-3bpw`. Conversion refuses to overwrite existing output or work directories. If conversion fails, retain the error output and move those directories aside before starting a fresh attempt. Allow additional disk space for converted weights and working files.

The helper prints the draft weight size and saves conversion settings and checksums alongside the external weights.

## Serve and check generation

`tabby.yml` contains the native serving settings: a 4096-token context, Q4 target and draft caches, one request at a time, and text input. The launcher selects the RX 9070 XT by name before starting TabbyAPI, mounts model files read-only, and exposes the API at `http://127.0.0.1:5000/v1`. Local API calls use no key; browser cross-origin requests are disabled. TabbyAPI runs in a temporary writable directory owned by your host user. Its file logs live there for the container lifetime; console output remains available through `sudo docker logs llm-recipes-exl3` while the container exists.

The launcher accepts `--draft on|off`, `--vision on|off`, `--context TOKENS`, and `--models DIRECTORY` in any order. Defaults are drafting on, vision off, and a 4096-token context. These options override the corresponding values in `tabby.yml`; `--help` lists them.

Start the target-only check in one terminal:

```bash
cd ~/Dev/llm-recipes
recipe=recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram
bash "$recipe/scripts/serve.sh" --draft off --vision off --context 4096
```

Wait for the server to finish loading. In another terminal, run:

```bash
cd ~/Dev/llm-recipes
python3 recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/check_generation.py
```

The check sends a fixed coding prompt with greedy sampling and a 128-token output limit. It prints the generated text, token usage, available server timings, and total request time. The first request includes any lazy compilation costs; run it again to check warm behavior. Repeated prompts can reuse cached context, so these checks establish generation behavior rather than comparable prefill measurements.

Stop the server with `sudo docker stop llm-recipes-exl3`. Start it again with drafting enabled, then run the same generation check:

```bash
bash "$recipe/scripts/serve.sh" --draft on --vision off --context 4096
```

Confirm the startup output identifies the converted draft as loaded. Keep the startup output and any errors available while checking both modes. Watch `amdgpu_top` for dedicated VRAM and GTT usage; the generator response and server logs provide performance statistics.

After both modes generate successfully, increase the context in steps, restarting between runs: `16384`, `32768`, `65536`, `98304`, then `131072`. For example:

```bash
bash "$recipe/scripts/serve.sh" --draft on --vision off --context 16384
```

The context argument sets both maximum sequence length and cache capacity. A short generation at a larger allocation checks loading and basic execution; measuring performance at that context requires a prompt that actually fills it. The recorded long-context checks processed approximately 130K input tokens at this allocation in both modes; see the results for measured speeds.

Use `--models` to select the external model directory. The existing image is reused:

```bash
bash "$recipe/scripts/serve.sh" --draft on --vision off --context 4096 --models "$HOME/Models/llm-recipes"
```

## Exercise the full context

With the server running at 131072 tokens, send a synthetic prompt close to 130000 tokens:

```bash
python3 recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/check_long_context.py
```

The helper counts tokens using TabbyAPI, reserves space for 128 output tokens plus headroom, and checks the reported input count for truncation. Each invocation starts with a fresh run identifier to avoid reusing an earlier prompt's prefix cache. It prints the response, usage, server timings, and request duration. Watch `amdgpu_top` during prefill and generation for peak VRAM and GTT usage. Requests allow up to one hour; a client timeout can leave server work running, so stop the container before retrying after a timeout.

The synthetic records exercise context capacity and throughput. The final coding task provides a basic output check; it does not measure retrieval accuracy across the records. Keep the reported cached-token count alongside prefill measurements. Smaller inputs can be selected with `--prompt-tokens 32768` or `--prompt-tokens 65536` while retaining the same server allocation.

## GPU-resident vision

The [vision result](2026-11-05-vision/summary.md) records successful screenshot reading with DFlash2 and a 131072-token allocation. Start it with named options:

```bash
bash recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/serve.sh \
  --draft on --vision on --context 131072
```

The launcher sets `vision_offload: false`, keeping vision weights GPU-resident.

## Pi coding agent

Run [Pi](https://github.com/badlogic/pi-mono) on the Ubuntu host, in the project you want it to work on. It connects to TabbyAPI at `http://127.0.0.1:5000/v1`; Pi handles files, shell commands, and conversation history on the host.

### Install

Install [nvm using its official instructions](https://github.com/nvm-sh/nvm#installing-and-updating), then open a new terminal. Use Node.js LTS and the latest stable Pi release:

```bash
nvm install --lts
nvm alias default 'lts/*'
nvm use default
npm install -g --ignore-scripts @earendil-works/pi-coding-agent@latest
node --version
pi --version
```

Run npm as your regular user. Repeat the install command to update Pi or after switching Node versions. Record Pi and Node versions with experiment results.

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
          "samplingParams": {
            "temperature": 1,
            "top_k": 20,
            "top_p": 0.95,
            "min_p": 0,
            "repetition_penalty": 1,
            "presence_penalty": 0,
            "reasoning_budget_tokens": 8192
          },
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

Start TabbyAPI from the repository root in one terminal:

```bash
bash recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/serve.sh \
  --draft on --vision on --context 131072
```

Once the server is ready, launch Pi from your working project in another terminal:

```bash
cd /path/to/your/project
pi
```

The model's `contextWindow` must match the serving allocation. For text-only serving, use `--vision off` and set `input` to `["text"]` in `models.json`. Open `/model` to reload model configuration and select the local model; `/thinking` changes the thinking setting.

Upstream references: [model configuration](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/models-configuration.md), [agent directory](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/configuration.md), and [settings](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/settings.md).
