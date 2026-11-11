# ExLlamaV3 / ROCm implementation

## Image and dependencies

[container/versions.lock.json](container/versions.lock.json) pins the AMD ROCm/PyTorch base image digest and upstream ExLlamaV3 and TabbyAPI revisions with archive hashes. [container/requirements.lock](container/requirements.lock) pins and hashes Python dependencies.

The base image supplies Torch, the ROCm SDK, and Triton. The Dockerfile compiles upstream ExLlamaV3 against that Torch with build isolation disabled, targeting `gfx1201`, and installs TabbyAPI's core dependencies and source. Source licenses are retained under `/opt/src`. The image's default command checks engine imports and GPU matrix multiplication.

## Model preparation

[config/models.lock.json](config/models.lock.json) records the target and original draft revisions. The download helper verifies file sizes and Git/LFS hashes and saves a local checksum manifest. The target is already quantized. The draft converter uses a 3.0-bit target, `mul1` codebook, and output scales enabled, and saves conversion settings and checksums beside the output.

| External directory | Contents |
| --- | --- |
| `qwen3.8-27b-exl3-3bpw` | Target model |
| `qwen3.8-27b-dflash2-source` | Original draft weights |
| `draft-conversion-work` | Converter working files |
| `qwen3.8-27b-dflash2-exl3-3bpw` | Converted draft and preparation metadata |
| `.cache` | Runtime and compiler caches |

## Serving and storage

The shared [`scripts/launch.py`](../../scripts/launch.py) handles Docker startup, status, console logs, and stopping. The recipe’s `serve.sh` forwards options to the recipe selected by its directory name. `config/launch.json` declares the API-server adapter (`tabbyapi`), inference engine (`exllamav3`), image, and launch defaults. `scripts/launcher.py` handles discovery, validated command planning, and process execution; `scripts/launch.py` provides the command-line interface. Docker labels identify each instance, recipe, adapter, and engine. The launcher creates a container running as the host user's UID/GID with access to the GPU devices. It publishes port 5000 on host loopback. `serve.py` validates the native settings against the pinned TabbyAPI schema, selects the RX 9070 XT by name, checks preparation metadata and image pins, and starts TabbyAPI in a writable temporary directory.

| Host data | Container path | Access |
| --- | --- | --- |
| Recipe directory | `/recipe` | Read-only |
| Model directory | `/models` | Read-only |
| Model directory's `.cache` | `/cache` | Writable |
| Selected log directory | `/logs` | Writable |

The temporary runtime's `logs` directory points to `/logs`. TabbyAPI handles file rotation, compression, and retention. The container is removed when it exits; mounted files remain on the host.

[config/tabby.yml](config/tabby.yml) holds native server defaults. Launch arguments select drafting, vision, sequence length, and cache capacity. Vision weights stay GPU-resident. Sampling entries use `force: false`, allowing explicit request values to take precedence. Thinking is enabled by default; clients control effort and can supply a reasoning budget. Pi connects through the OpenAI-compatible chat API.

## Measurement helpers

Run these from the repository root against a running server:

```bash
python3 recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/check_generation.py
python3 recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/scripts/check_long_context.py
```

`check_generation.py` sends a fixed coding prompt with greedy sampling and a 128-token output limit. Initial requests can include compilation costs; repeated prompts can reuse cached context.

`check_long_context.py` uses the server tokenizer to construct approximately 130K input tokens, reserves output headroom, and checks the reported input count for truncation. It uses a fresh run identifier to avoid reuse of an earlier prompt's prefix cache. Start the server with `--context 131072` for the default workload. Use `--prompt-tokens 32768` or `--prompt-tokens 65536` for smaller inputs.

Both helpers print generated output, token usage, server timings, and request duration. Record cached tokens with prefill measurements and observe VRAM/GTT with `amdgpu_top`. The long-context request timeout is one hour; stop the container before retrying a timed-out request that may still be running.

---

[Recipe](recipe.md) · [Setup](setup.md) · [Text results](2026-11-05/summary.md) · [Vision results](2026-11-05-vision/summary.md)
