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

The image name and API-server/engine pairing live in [`runtime.json`](../../runtimes/exllamav3-tabbyapi/runtime.json). Reuse the image while its lock matches; rebuild after changing build inputs or pins. Serving and draft conversion compare the image's build lock with the runtime lock.

## Preparation

The recipe's setup guide supplies the `prepare-models.sh` commands for `download` and `quantize-draft`. Its model lock defines downloads, directory names, and conversion arguments.

An optional third argument selects the host models directory; its default is `~/Models/llm-recipes`. Both commands run as the host UID and mount the recipe and runtime read-only. Quantization also receives GPU access. Downloads verify file sizes and Git/LFS hashes, then save checksum manifests. Converted drafts record source metadata, build pins, conversion arguments, and output checksums. Preparation is locked against another writer in the same model directory.

Interrupted downloads can be rerun. Conversion requires fresh output and work directories: move failed outputs aside before retrying. Paths are declared by the model lock.

## Serving

The [launcher](../launcher.md#shared-runtimes) provides mounts and invokes the serving helper.

The helper validates `config/tabby.yml` against the pinned TabbyAPI schema, verifies model preparation metadata and image pins, selects the GPU before HIP initialization, and starts TabbyAPI in a temporary writable directory. That directory's `logs` entry points to `/logs`. TabbyAPI rotates file logs at 20 MB, compresses them, and retains them for one week by default; native logging settings control retention.

`--vision on|off` selects GPU-resident vision, `--draft on|off` controls the configured draft, and `--context` sets sequence and cache capacity. Native sampling values remain in the recipe. Entries with `force: false` supply defaults; explicit request values take precedence. The default host API port is 5000; the UI is `/ui/` and status is `/ui/status`.

## Checks and clients

The recipe setup guide supplies short and long generation commands with an explicit `--model`.

`--base-url` defaults to `http://127.0.0.1:5000/v1`. The short check sends a coding prompt with greedy sampling and 128 output tokens. The long check uses the server tokenizer for approximately 130k input tokens and verifies the reported count; its fresh identifier avoids reuse of the previous prompt prefix. Default long-check context is 131,072. Use `--prompt-tokens`, `--context`, and `--output-tokens` to change it.

Record cached tokens alongside prefill measurements. First requests can include compilation overhead. Both checks print output, timing, and usage. The long timeout is one hour; a timed-out server request may still be running.

Use [Pi setup](../clients/pi.md) and the recipe's provider configuration.

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
