# ExLlamaV3 / ROCm build probe

The base image passed a PyTorch matrix multiplication on the RX 9070 XT. It contains Python 3.12.3, Torch 2.14.0+rocm10.1.0, and HIP 7.16.26385. The Dockerfile builds pinned upstream ExLlamaV3 and prepares TabbyAPI sources. Engine build and model execution on this stack are pending validation.

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
