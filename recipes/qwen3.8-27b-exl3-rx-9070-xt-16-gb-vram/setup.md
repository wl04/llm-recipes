# ExLlamaV3 / ROCm setup

The base image passed a PyTorch matrix multiplication on the RX 9070 XT. It contains Python 3.12.3, Torch 2.14.0+rocm10.1.0, and HIP 7.16.26385. The Dockerfile builds pinned upstream ExLlamaV3 and prepares TabbyAPI sources. The workstation also passed extension compilation, ExLlamaV3/DFlash2 and TabbyAPI schema imports, and the image’s GPU matrix multiplication check. Model conversion, loading, and generation are the next validation steps.

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

The checker selects the RX 9070 XT by name, imports the precompiled extension and DFlash2 architecture, imports TabbyAPI's configuration schema, and runs a GPU matrix multiplication. A successful result prepares us for model loading; it does not exercise model kernels or speculative generation.

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

The helper prints the resulting draft weight size and records conversion arguments, build pins, and output checksums alongside the external weights. The next workstation check is model loading and generation with drafting disabled and enabled, followed by measuring context capacity and VRAM use.

## Serve and check generation

The workstation converted the draft successfully: 0.932 GB of weights. `tabby.yml` contains the native serving settings: a 4096-token context, Q4 target and draft caches, one request at a time, and text input. The launcher selects the RX 9070 XT by name before starting TabbyAPI, mounts model files read-only, and exposes the API at `http://127.0.0.1:5000/v1`. Local API calls use no key; browser cross-origin requests are disabled. TabbyAPI runs in a temporary writable directory owned by your host user. Its file logs live there for the container lifetime; console output remains available through `sudo docker logs llm-recipes-exl3` while the container exists.

Start the target-only check in one terminal:

```bash
cd ~/Dev/llm-recipes
recipe=recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram
bash "$recipe/scripts/serve.sh" off 4096
```

Wait for the server to finish loading. In another terminal, run:

```bash
cd ~/Dev/llm-recipes
python3 recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/check_generation.py
```

The check sends a fixed coding prompt with greedy sampling and a 128-token output limit. It prints the generated text, token usage, available server timings, and total request time. The first request includes any lazy compilation costs; run it again to check warm behavior. Repeated prompts can reuse cached context, so these checks establish generation behavior rather than comparable prefill measurements.

Stop the server with `sudo docker stop llm-recipes-exl3`. Start it again with drafting enabled, then run the same generation check:

```bash
bash "$recipe/scripts/serve.sh" on 4096
```

Confirm the startup output identifies the converted draft as loaded. Keep the startup output and any errors available while checking both modes. Watch `amdgpu_top` for dedicated VRAM and GTT usage; the generator response and server logs provide performance statistics.

After both modes generate successfully, increase the context in steps, restarting between runs: `16384`, `32768`, `65536`, `98304`, then `131072`. For example:

```bash
bash "$recipe/scripts/serve.sh" on 16384
```

The context argument sets both maximum sequence length and cache capacity. A short generation at a larger allocation checks loading and basic execution; measuring performance at that context requires a prompt that actually fills it. Maximum working context and DFlash2 speedup remain to be measured on the workstation.

An optional third argument selects the external model directory. The existing image is reused:

```bash
bash "$recipe/scripts/serve.sh" on 4096 "$HOME/Models/llm-recipes"
```

## Exercise the full context

With the server running at 131072 tokens, send a synthetic prompt close to 130000 tokens:

```bash
python3 recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/check_long_context.py
```

The helper counts tokens using TabbyAPI, reserves space for 128 output tokens plus headroom, and checks the reported input count for truncation. Each invocation starts with a fresh run identifier to avoid reusing an earlier prompt's prefix cache. It prints the response, usage, server timings, and request duration. Watch `amdgpu_top` during prefill and generation for peak VRAM and GTT usage. Requests allow up to one hour; a client timeout can leave server work running, so stop the container before retrying after a timeout.

The synthetic records exercise context capacity and throughput. The final coding task provides a basic output check; it does not measure retrieval accuracy across the records. Keep the reported cached-token count alongside prefill measurements. Smaller inputs can be selected with `--prompt-tokens 32768` or `--prompt-tokens 65536` while retaining the same server allocation.
