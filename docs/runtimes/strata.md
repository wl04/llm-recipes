# Strata runtime

The shared runtime uses Strata's HIP engine and its own API server, with a CPU vision encoder. It targets `gfx1201`, including the RX 9070 XT. Recipes provide the model lock, native `strata.json`, Pi metadata, and a data directory derived from the recipe folder name.

[Upgrade Strata on the RX 9070 XT](#upgrade-strata-on-the-rx-9070-xt)

## Build and check

From the repository root, on Ubuntu x86_64 with Docker and AMD `/dev/kfd` and `/dev/dri` devices:

```bash
python3 scripts/build_runtime.py strata --check
```

Lower `--max-jobs` if compiler memory use is excessive. The image check exercises binary startup, API imports, and a HIP kernel on the selected GPU. Success ends with `Strata binaries, API imports, and HIP kernel: PASS`.

[`versions.lock.json`](../../runtimes/strata/container/versions.lock.json) pins AMD's ROCm development image and exact Strata and llama.cpp revisions. Source archives are verified before extraction. Python dependencies use hashes; Ubuntu dependencies use a dated snapshot. The CPU vision build uses a portable AVX2 baseline.

The builder, preparation helper, launcher and baseline runner read the checkout’s default image tag from [runtime.json](../../runtimes/strata/runtime.json). Reuse your existing image for this checkout. Rebuild when its inputs change. Preparation and serving verify the runtime lock embedded in the image.

## Preparation

With the serving instance stopped, run these commands from the repository root. Use the same models root for preparation and serving.

```bash
recipe=qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
models_root="${LLM_RECIPES_HOME:-$HOME/llm-recipes}"
python3 runtimes/strata/scripts/prepare_models.py --recipe "recipes/$recipe" --models "$models_root"
```

Preparation resumes partial downloads, verifies the locked hashes, builds the pack and Q2_0 MTP draft, and writes a receipt matching the model and runtime locks. For Unsloth, `pack.compat_bf16` records converted tensors in `packs/iq3_xxs/conversions.json`; experts retain their published formats.

Prepared files under the recipe's data folder:

```text
models/              # Published GGUF shards and projector
packs/iq3_xxs/       # Native pack, tokenizer, optional conversion report
mtp/                 # Verified source, converted GGUF and rt/ runtime
prepared.json        # Completion record matching model and runtime locks
```

## Serving

The [launcher](../launcher.md#shared-runtimes) provides the mounts and entry point. The Strata adapter adds unlimited memory locking, 2 GiB shared memory, and a 120-second stop timeout.

The serving helper checks the completion receipt against the selected model and runtime locks, checks all shard sizes and required artifacts, selects a single visible `gfx1201` device, and creates a temporary native configuration. `--context`, `--draft`, and `--vision cpu|off` override that recipe's defaults. The GPU-resident KV setting is capped at 32,768 cells by this integration. The API is published on host loopback; offline mode disables external fetching. Check startup and follow the logs from the checkout used for serving (Ctrl+C leaves a detached server running):

```bash
python3 scripts/launch.py start "$recipe" --models "$models_root" --detach
curl --retry 90 --retry-delay 2 --retry-all-errors -fsS http://127.0.0.1:8080/health
python3 scripts/launch.py logs "$recipe" --follow
python3 scripts/launch.py stop "$recipe"
```

`server.log` retains API console output; `engine.log` contains engine and vision messages. Both append in the selected host log directory and survive container removal. Rotate them while the server is stopped. A baseline run points them at its own output directory. The wrapper forwards stop signals and preserves the server exit status.

## Baseline and clients

The [baseline runner](../baseline.md) checks the served model at `/v1/models`, sizes prompts through `/v1/messages/count_tokens`, and reads cached tokens from streamed usage. It matches `engine.log` completion records to requests for prefill, decode and draft acceptance.

With the instance stopped, run the baseline from a checkout with the development dependencies installed:

```bash
.venv/bin/python scripts/run_baseline.py run "$recipe" --models "$models_root"
```

Pi uses OpenAI-compatible chat completions. The frontend supports streaming, tool calls/results, embedded images, and `max_completion_tokens`. `low` and `medium` reasoning map directly; `high` and `xhigh` map to the model's `xhigh`. `off: none` disables thinking; `minimal` also disables it in this revision. See [Pi setup](../clients/pi.md) for installation and client configuration.

## Upgrade Strata on the RX 9070 XT

From your reference checkout on the workstation, run the following with Python 3.14+, Git, Docker and access to GitHub and Docker Hub:

```bash
python3 scripts/upgrade_strata.py v0.2.18
```

Use the new upstream tag on subsequent runs. The command resolves the exact commit, hashes its source archive, checks the engine and CPU vision targets, server and preparation files, and compares the upstream MTP revision to the Unsloth model lock. It resolves the ROCm tag to a Linux amd64 manifest digest and prints the versions before building. For v0.2.18 the expected engine is 0.1.64.

The command creates or reuses a sibling worktree named `<checkout>-strata-<tag>` on branch `strata-<tag>`. It writes the runtime descriptor and lock there, builds the version-tagged image and runs the HIP smoke check. On a repeat run it checks the existing image against the candidate lock and reruns the probe. Your reference checkout, installed launcher and prepared weights remain available throughout. To inspect the candidate inputs before using Docker:

```bash
python3 scripts/upgrade_strata.py v0.2.18 --prepare-only
```

The [upgrade configuration](../../runtimes/strata/upgrade.json) selects the ROCm tag, build parallelism, optional image suffix and additional Boolean Strata engine CMake options. The default is ROCm 10.2.0-full, four compiler jobs and upstream engine defaults for gfx1201. For a second build of the same release, give it a suffix so the worktree, data root and image tag are separate:

```bash
python3 - <<'PYCONFIG'
import json
from pathlib import Path
config = json.loads(Path("runtimes/strata/upgrade.json").read_text())
config.update(image_suffix="-trial", max_jobs=2)
Path("/tmp/strata-trial.json").write_text(json.dumps(config, indent=2))
PYCONFIG
python3 scripts/upgrade_strata.py v0.2.18 --config /tmp/strata-trial.json
```

### Try the candidate

After the image check passes, run the printed commands to copy the reference GGUFs, prepare the candidate pack, run doctor and start the Unsloth recipe. Stop any instance using the card first (`llm-recipes ps`, then `llm-recipes stop <instance>`). The trial uses the recipe’s model, MTP, CPU vision, and 131,072-token context. Allow about 78 GiB for the GGUF copy on filesystems without reflinks, plus room for the image and pack.

For the default v0.2.18 trial, the following commands run suite v3 on the candidate. Run them from the reference checkout after stopping the interactive candidate:

```bash
tag=v0.2.18
recipe=qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram
reference=$(git rev-parse --show-toplevel)
candidate="${reference}-strata-$tag"
models_root="${LLM_RECIPES_HOME:-$HOME/llm-recipes}"
trial_root="${models_root}-strata-$tag"
cd "$candidate"
python3 scripts/launch.py stop "$recipe"
uv venv --python 3.14 .venv
uv pip install -p .venv -r dev-requirements.txt
.venv/bin/python scripts/run_baseline.py run "$recipe" --models "$trial_root"
```

Compare returning-turn latency, prefill, decode, and peak RAM/VRAM against the same suite run on the reference checkout. The 62 tok/s figure in the v0.2.18 release notes applies to Tencent Hy4-Flash. [Baseline measurements and import](../baseline.md) · [v0.2.18 release](https://github.com/Niko1221/Strata/releases/tag/v0.2.18)

### Adopt or roll back

To adopt after validation, commit the generated inputs, fast-forward the reference and reinstall. Import any baseline from the matching candidate checkout first.

```bash
cd "$candidate"
git add -- runtimes/strata/runtime.json runtimes/strata/container/versions.lock.json
git commit -m "Use Strata $tag on gfx1201"
cd "$reference"
git merge --ff-only "strata-$tag"
python3 scripts/install.py install
llm-recipes start "$recipe" --models "$trial_root" --detach
```

To return to the reference during the trial, stop any active candidate and use the installed launcher with the reference data:

```bash
cd "$reference"
llm-recipes start "$recipe" --models "$models_root" --detach
```

For a discarded trial, review `git -C "$candidate" status --short` and save any results first. The following removes the two generated inputs’ changes, then removes the worktree and the candidate image. Git stops worktree removal if it finds other pending changes.

```bash
(
  set -eu
  cd "${reference:?}"
  test "$(git -C "${candidate:?}" branch --show-current)" = "strata-${tag:?}"
  git -C "$candidate" restore -- runtimes/strata/runtime.json runtimes/strata/container/versions.lock.json
  git worktree remove "$candidate"
  git branch -d "strata-$tag"
  sudo docker image rm "llm-recipes/strata-rdna4:$tag"
)
```

To reclaim the separate candidate model data after rollback, check its size and confirm interactive removal:

```bash
if [[ -n ${models_root:-} && -n ${tag:-} && ${trial_root:-} == "${models_root}-strata-$tag" ]]; then
  du -sh -- "$trial_root" && rm -rI -- "$trial_root"
fi
```

---

[All recipes](../../README.md) · [Launcher](../launcher.md) · [Authoring](../authoring.md)
