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
