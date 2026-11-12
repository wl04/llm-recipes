# Strata image setup

## Build

Use an Ubuntu x86_64 workstation with Docker and working AMD `/dev/kfd` and `/dev/dri` devices. This image targets `gfx1201`, including the RX 9070 XT. The intended model configuration uses 16 GB VRAM and 64 GB system RAM.

From the repository root:

```bash
recipe=recipes/qwen3.8-flash-next-gguf-rx-9070-xt-16-gb-vram
sudo docker build --progress=plain --build-arg MAX_JOBS=4 \
  -t llm-recipes/strata-rdna4:probe "$recipe/container"
```

The build downloads the locked AMD ROCm image, source archives, and Python wheels. Ubuntu packages come from a dated archive snapshot. Both Strata HIP and the CPU vision encoder are compiled in the image. Lower `MAX_JOBS` if compilation exhausts host memory.

## Check the image

```bash
sudo docker run --rm \
  --device=/dev/kfd --device=/dev/dri \
  llm-recipes/strata-rdna4:probe
```

The check prints the source revisions, checks both binaries and API imports, selects the `gfx1201` GPU, and executes a small HIP kernel. Success ends with:

```text
Strata binaries, API imports, and HIP kernel: PASS
```

The image check has passed on the RX 9070 XT workstation. Continue with model preparation.

## Download and prepare the model

Allow at least 100 GB of free disk space for approximately 82 GB of downloads and preparation outputs. Stop any Strata instance using these files before preparing them.

From the repository root, as your regular user:

```bash
python3 recipes/qwen3.8-flash-next-gguf-rx-9070-xt-16-gb-vram/scripts/prepare_models.py \
  --models "$HOME/Models/llm-recipes"
```

The command runs CPU preparation inside the existing image using your host UID. It downloads the two IQ3_XXS shards and BF16 vision projector at the revision in `config/models.lock.json`, checks their SHA-256 hashes, and extracts the native pack and tokenizer. It then downloads only the pinned checkpoint's MTP tensors, verifies them, and creates the Q2_0 draft runtime with Strata's default draft vocabulary.

All files are stored under `$HOME/Models/llm-recipes/strata`:

```text
models/IQ3_XXS/       # Original model shards
models/mmproj-*.gguf  # CPU vision projector
packs/iq3_xxs/        # Native pack and tokenizer
mtp/                 # Verified source tensors, converted GGUF, and rt/ runtime
prepared.json        # Completion record matching the model and image locks
```

Rerun the same command after a connection failure. Completed downloads are verified and reused; partial GGUF downloads resume when the server honors byte ranges. Preparation tools rerun, and a completion record is written after all stages succeed. A checksum failure reports the affected file; move that file aside before retrying.

## Serving configuration

[`config/strata.json`](config/strata.json) defines native Strata settings and the prepared file layout under the external model mount. After preparation succeeds, start the server:

```bash
python3 scripts/launch.py start \
  qwen3.8-flash-next-gguf-rx-9070-xt-16-gb-vram \
  --name strata-coding --detach \
  --draft on --vision cpu --context 131072 \
  --models "$HOME/Models/llm-recipes" \
  --logs "$HOME/Models/llm-recipes/logs/strata-coding"
```

Use `--draft off` for the baseline and `--vision off` to disable image processing. Missing prepared artifacts are reported before engine startup. API address: `http://127.0.0.1:8080/v1`; readiness: `curl -f http://127.0.0.1:8080/health`.

## Sampling

Server defaults in `config/strata.json` are temperature 1, top-k 20, top-p 0.95, min-p 0, repetition penalty 1, and presence penalty 0. Requests can override each value. Strata uses a flat `sampling` object with numeric values.

## Vision detail

CPU vision uses `vision.min_tokens: 1024` and `vision.max_tokens: 1024` in `config/strata.json`. These control image encoding, separately from the response-token limit. Restart the serving instance after changing them. The initial results used Strata’s default CPU image-token maximum of 300; the [1,024-token comparison](002-2026-11-12-vision-1024/summary.md) records improved reading of several labels and increased end-to-end latency on the same screenshot.

## Generation checks

After model preparation and startup, run these checks from the repository root:

```bash
check=recipes/qwen3.8-flash-next-gguf-rx-9070-xt-16-gb-vram/scripts/check_generation.py
python3 "$check" text
python3 "$check" tools
python3 "$check" vision --image /path/to/screenshot.png
python3 "$check" long --input-tokens 120000
```

`text` checks streamed chat output. `tools` checks a function call and a follow-up using a fixed tool result; it executes no model-generated commands. `vision` submits an embedded PNG/JPEG; inspect the answer against the image. `long` uses Strata's Anthropic token-count and generation endpoints to send up to the requested input size, with 128 output tokens. Keep the input target plus output allowance below the server's context capacity. Watch memory during the long check.

Checks use temperature 0 and disable thinking to keep them short. They print API responses and timings; these settings apply only to the checks. The [initial results](001-2026-11-12-initial-checks/summary.md) record these checks on the RX 9070 XT.

## Pi

Follow the shared [Pi installation guide](../../docs/clients/pi.md). Merge the `strata-local` provider from [`config/pi.models.json`](config/pi.models.json) into `~/.pi/agent/models.json`, preserving existing providers. Start Pi in your working project and select the model through `/model`.

The example uses `http://127.0.0.1:8080/v1`, a 131,072-token context, and text/image input. Match the context and port to the running server; use `input: ["text"]` when serving with vision off.

Use `/thinking` to choose the effort. Strata maps `low` and `medium` directly, and both `high` and `xhigh` to the model's `xhigh`. `off` sends `reasoning_effort: none`; `minimal` also disables thinking in this Strata revision. Sampling remains controlled by the server defaults, with Pi's normal output and compaction behavior.

## Logs

`server.log` retains API console output; `engine.log` retains engine and vision output. Both append under the selected host log directory and remain after the container exits. Rotate or archive these files while the server is stopped.

```bash
python3 scripts/launch.py logs strata-coding --follow
python3 scripts/launch.py stop strata-coding
```

Ctrl+C exits the log viewer. The detached server continues running.

---

[Recipe](recipe.md) · [Implementation](implementation.md) · [Launcher](../../docs/launcher.md)
