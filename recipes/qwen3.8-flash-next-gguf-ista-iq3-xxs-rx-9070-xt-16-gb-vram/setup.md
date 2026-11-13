# Qwen3.8-Flash-Next / ISTA GSQ-RCO IQ3_XXS

## Runtime and capacity

Build and check the shared [Strata runtime](../../docs/runtimes/strata.md#build-and-check). The [launch manifest](config/launch.json) selects that runtime. An existing image with the same runtime lock can be reused.

Allow at least **100 GB free disk space** for approximately 82 GB of downloads and preparation outputs. The tested configuration uses 16 GB VRAM and 64 GB RAM; its expert arena is 39.97 GiB. The [initial results](001-2026-11-12-initial-checks/summary.md) record workstation validation.

## Prepare models

Stop a serving instance before preparing its files. From the repository root:

```bash
python3 runtimes/strata/scripts/prepare_models.py \
  --recipe recipes/qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram \
  --models "$HOME/Models/llm-recipes"
```

The [model lock](config/models.lock.json) pins model artifacts and the BF16 CPU projector. Both published shards are verified. The target retains its native formats. The packer extracts the tokenizer and creates the native index. MTP uses the pinned original checkpoint and Q2_0 expert conversion. Downloads resume on rerun; hashes are verified before completed files are published.

Files live under `$HOME/Models/llm-recipes/strata`:

```text
models/              # Published GGUF shards and projector
packs/iq3_xxs/       # Native pack, tokenizer, conversion report
mtp/                 # Verified source, converted GGUF and rt/ runtime
prepared.json        # Completion record matching model and runtime locks
```

## Launch

Run one model instance at a time on the RX 9070 XT workstation. Stop the other recipe's instance before switching, then:

```bash
python3 scripts/launch.py start qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram \
  --name strata-coding --detach \
  --draft on --vision cpu --context 131072 \
  --models "$HOME/Models/llm-recipes" \
  --logs "$HOME/Models/llm-recipes/logs/strata-coding"
python3 scripts/launch.py logs strata-coding --follow
```

Readiness: `curl -f http://127.0.0.1:8080/health`. The API is `http://127.0.0.1:8080/v1` and serves `qwen3.8-flash-next-iq3_xxs`. Use `--draft off` to disable MTP and `--vision off` for text-only serving.

[Native settings](config/strata.json) use INT8 K/V, 32,768 GPU-resident KV cells, automatic expert cache/prefill, and four speculative tokens. Sampling defaults are temperature 1, top-k 20, top-p 0.95, min-p 0, repetition penalty 1, and presence penalty 0. Requests can override them. CPU vision uses 1,024 image tokens. Restart after editing settings.

## Checks

After readiness:

```bash
check=runtimes/strata/scripts/check_generation.py
python3 "$check" text --model qwen3.8-flash-next-iq3_xxs
python3 "$check" tools --model qwen3.8-flash-next-iq3_xxs
python3 "$check" vision --model qwen3.8-flash-next-iq3_xxs --image /path/to/screenshot.png
python3 "$check" long --model qwen3.8-flash-next-iq3_xxs --input-tokens 120000
```

The checks use temperature zero and disable thinking. Inspect the image answer against its input. The long check reserves 128 output tokens; keep input plus output below server context. Record measured results in a new numbered experiment folder.

## Pi

Follow [Pi installation](../../docs/clients/pi.md), then merge `strata-local` from [`config/pi.models.json`](config/pi.models.json) into `~/.pi/agent/models.json`. Select it with `/model` and choose effort with `/thinking`.

The example uses 131,072 context and text/image input. Keep Pi's `contextWindow` and API URL aligned with the server. With vision off, set `input: ["text"]`. Use the same effort and workload when comparing recipes.

## Logs and stopping

```bash
python3 scripts/launch.py logs strata-coding --follow
python3 scripts/launch.py stop strata-coding
```

Ctrl+C exits log following while the detached server continues. `server.log` and `engine.log` append in the selected log directory and survive container removal. See the [launcher guide](../../docs/launcher.md) for lifecycle commands and port overrides.

---

[Recipe](recipe.md) · [Runtime](../../docs/runtimes/strata.md)
