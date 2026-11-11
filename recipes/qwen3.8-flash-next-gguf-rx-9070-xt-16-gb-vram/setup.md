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

This is the current workstation checkpoint. Model artifact locking and preparation follow successful image validation.

## Serving configuration

[`config/strata.json`](config/strata.json) defines native Strata settings and the prepared file layout under the external model mount. Once those artifacts exist, the shared launcher supports:

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

## Logs

`server.log` retains API console output; `engine.log` retains engine and vision output. Both append under the selected host log directory and remain after the container exits. Rotate or archive these files while the server is stopped.

```bash
python3 scripts/launch.py logs strata-coding --follow
python3 scripts/launch.py stop strata-coding
```

Ctrl+C exits the log viewer. The detached server continues running.

---

[Recipe](recipe.md) · [Implementation](implementation.md) · [Launcher](../../docs/launcher.md)
