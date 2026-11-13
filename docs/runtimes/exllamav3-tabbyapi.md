# ExLlamaV3 / TabbyAPI runtime

The shared runtime builds ExLlamaV3 against AMD's ROCm/PyTorch image and serves through TabbyAPI. It targets `gfx1201` and selects the RX 9070 XT by name. Recipes provide target/draft locks, conversion options, native TabbyAPI settings, and Pi metadata.

## Build and check

Use Ubuntu x86_64, Docker, and working AMD `/dev/kfd` and `/dev/dri` devices. From the repository root:

```bash
sudo docker build --progress=plain --build-arg MAX_JOBS=4 \
  -t llm-recipes/exl3-rdna4:probe runtimes/exllamav3-tabbyapi/container
sudo docker run --rm --device=/dev/kfd --device=/dev/dri \
  llm-recipes/exl3-rdna4:probe
```

Lower `MAX_JOBS` if compiler memory use is excessive. The image check verifies engine imports and GPU matrix multiplication.

[`versions.lock.json`](../../runtimes/exllamav3-tabbyapi/container/versions.lock.json) pins the ROCm/PyTorch image digest and upstream ExLlamaV3 and TabbyAPI sources with archive hashes. Python dependencies are pinned with hashes in the same directory. The base supplies Torch, the ROCm SDK, and Triton. ExLlamaV3 is compiled against that Torch with build isolation disabled. Source licenses remain under `/opt/src`.

The image name and API-server/engine pairing live in [`runtime.json`](../../runtimes/exllamav3-tabbyapi/runtime.json). Rebuild after changing build inputs or pins. Serving and draft conversion compare the image's build lock with the runtime lock.

## Preparation

The recipe's model lock defines target/draft downloads, external directory names, and conversion arguments:

```bash
bash runtimes/exllamav3-tabbyapi/scripts/prepare-models.sh recipes/<recipe> download
bash runtimes/exllamav3-tabbyapi/scripts/prepare-models.sh recipes/<recipe> quantize-draft
```

An optional third argument selects the host models directory; its default is `~/Models/llm-recipes`. Both commands run as the host UID and mount the recipe and runtime read-only. Quantization also receives GPU access. Downloads verify file sizes and Git/LFS hashes, then save checksum manifests. Converted drafts record source metadata, build pins, conversion arguments, and output checksums. Preparation is locked against another writer in the same model directory.

Interrupted downloads can be rerun. Conversion requires fresh output and work directories: move failed outputs aside before retrying. Paths are declared by the model lock.

## Serving

The shared launcher mounts the recipe at `/recipe` and this runtime at `/runtime`, both read-only. Prepared models are read-only at `/models`; `/cache` and `/logs` are writable. It invokes `/runtime/scripts/serve.py --recipe /recipe` with context, drafting, and vision options.

The helper validates `config/tabby.yml` against the pinned TabbyAPI schema, verifies model preparation metadata and image pins, selects the GPU before HIP initialization, and starts TabbyAPI in a temporary writable directory. That directory's `logs` entry points to `/logs`. TabbyAPI controls rotation and retention through native settings.

`--vision on|off` selects GPU-resident vision, `--draft on|off` controls the configured draft, and `--context` sets sequence and cache capacity. Native sampling values remain in the recipe. The default host API port is 5000; the UI is `/ui/` and status is `/ui/status`.

## Checks and clients

Both helpers require the served model ID:

```bash
python3 runtimes/exllamav3-tabbyapi/scripts/check_generation.py --model <model-id>
python3 runtimes/exllamav3-tabbyapi/scripts/check_long_context.py --model <model-id>
```

`--base-url` defaults to `http://127.0.0.1:5000/v1`. The short check sends a coding prompt with greedy sampling and 128 output tokens. The long check uses the server tokenizer for approximately 130k input tokens and verifies the reported count; its fresh identifier avoids reuse of the previous prompt prefix. Default long-check context is 131,072. Use `--prompt-tokens`, `--context`, and `--output-tokens` to change it.

Record cached tokens alongside prefill measurements. First requests can include compilation overhead. Both checks print output, timing, and usage. The long timeout is one hour; a timed-out server request may still be running.

Use [Pi setup](../clients/pi.md) and the recipe's provider configuration. Keep Pi's `contextWindow`, served model ID, and API address aligned with the server.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
