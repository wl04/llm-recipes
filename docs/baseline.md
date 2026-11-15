# Baseline runner

The runner measures functional checks, coding workloads, context scaling, and resource use against a running server, and turns runs and engine logs into repository experiments. Implementation: [`scripts/baseline/`](../scripts/baseline/).

## Run a baseline

For a container recipe, close GPU-heavy applications and stop other launcher instances; reboot beforehand if practical. Run from the repository root:

```bash
python3 scripts/run_baseline.py run <recipe>
```

The runner starts the recipe as instance `baseline`, stops it afterwards, and asks for your sudo password once at start (later Docker commands use noninteractive sudo, so expiring credentials can fail a late operation, including cleanup — re-run to refresh). It refuses to start while another instance runs or the selected GPU holds more than 2 GiB. Recipe defaults can be overridden with `--models`, `--context`, `--draft`, `--vision`, and `--port`.

Output defaults to `~/llm-recipes/baselines/<recipe>/<date-time>/` (`--output` for another new directory outside the repository); server logs go to `server-logs/` inside the run directory. Ctrl+C preserves partial records and stops the server; `--keep-running` leaves it running.

**Desktop apps:** start the app, load the model per its configuration guide, start its API server, then run the same command. A guided interview confirms the server URL, the served model (read live from `/v1/models`), the configured context, and the app's process id for CPU/RAM and process VRAM measurements — nothing is recorded until you approve the summary. `--yes` accepts determinable defaults and stops instead of guessing when models are ambiguous (pass `--model`). Fully explicit, no interview: `--base-url http://127.0.0.1:<port>/v1 --model <served-model-id> --context <tokens> --pid <server-pid>`. The runner then attaches without touching the app. Changing model or context in the app mid-run invalidates the run.

Other options: `--gpu-pci` (default: the AMD GPU with most VRAM), `--no-gpu`, `--server-kind` (desktop default: `lmstudio`), `--image`, `--request-extra` (JSON merged into request bodies).

## Import a baseline run

Add a completed run to the repository in four steps, from the development checkout (the experiment lands in the repository that contains the script — running import from an installed snapshot would add it to the snapshot instead):

1. **Find the run directory** — each run is one directory under `~/llm-recipes/baselines/<recipe>/`; the newest holds `results.json`, `meta.json`, request and sample records, and `server-logs/`:

   ```bash
   ls -dt ~/llm-recipes/baselines/<recipe>/*/ | head -1
   ```

2. **Import**:

   ```bash
   python3 scripts/run_baseline.py import <run-dir>
   python3 scripts/run_baseline.py import <run-dir> --suffix <lowercase-hyphen-slug>  # optional folder-name extension
   ```

   The command creates the numbered experiment folder under the recipe, copies `results.json`, writes a complete `profile.yaml` from the run's `meta.json`, `facts.json`, recipe configuration, and runtime locks, and regenerates the configuration and recipe index — no manual `profile.yaml` editing. The profile reuses the identity of the recipe's existing experiments when they have one; folder-derived parts serve only the first experiment.

3. **Optional notes** — record a non-obvious constraint or observation in `settings.notes` of the new `profile.yaml`, then re-run `python3 scripts/generate_configurations.py` so `configuration.md` matches.

4. **Verify and commit**: `scripts/check.sh`, then commit the new experiment folder.

See the [authoring guide](authoring.md) for folder naming.

## Report a coding session

The session command aggregates one instance's coding activity from the engine's own logs — no client list is needed. Adding a session experiment to the repository takes three steps, from the development checkout:

1. **Create and fill the experiment in one command** (the instance must have been started by the launcher at least once, so its log directory with `*.log` files and `facts.json` exists):

   ```bash
   python3 scripts/run_baseline.py session <instance> --create <lowercase-hyphen-slug>
   ```

   This numbers the next experiment folder `NNN-<date>-<slug>` under the recipe, copies the `summary.md` and `configuration.md` scaffold from the template, aggregates the logs into `session-results.json`, writes the generated activity block into `summary.md`, and seeds `profile.yaml` from `facts.json` and the sampler parameters the engine echoed to its log. The folder date comes from the instance's `facts.json`.

2. **Regenerate the recipe index**: `python3 scripts/generate_configurations.py`.

3. **Write the narrative** in `summary.md` — Workload and Observations outside the generated markers — then `scripts/check.sh` and commit.

To read the numbers without creating anything, run the same command without `--create`; it prints the document to stdout. To update an existing experiment instead of creating one, use `--experiment <folder>` — an existing `profile.yaml` is never overwritten, and a missing `summary.md` in that folder is an error (the command updates, never creates files).

```bash
python3 scripts/run_baseline.py session <instance>          # print to stdout
python3 scripts/run_baseline.py session --logs <dir>        # any directory of *.log files
python3 scripts/run_baseline.py session <instance> --experiment recipes/<recipe>/<NNN-...>
```

With `--logs`, `facts.json` may be absent (LM Studio logs are one such case); the profile then seeds from the recipe name and the sampler echo alone. A directory without top-level `*.log` files is searched recursively, which covers LM Studio's dated files rotated into month directories.

| Engine | Timestamps | Cancellation | Unclosed requests |
|---|---|---|---|
| TabbyAPI file logs | per line | `client disconnected` line | started `#N` ids without a summary |
| Strata `engine.log` / `server.log` | none | `cancel=True` in `server.log` | unavailable |
| LM Studio (llama.cpp) server logs | per block | not logged distinctly | unavailable |

`--since`/`--until` (ISO timestamps) filter entries on timestamped logs only; the command fails instead of silently ignoring them. Metrics a log cannot provide appear as `unavailable`, matching the baseline convention.

## Suite versions

| Suite | Workloads | Recorded baselines |
|---|---|---|
| v1 | checks, warmup, 8K/32K/64K/120K context, sustained coding | TabbyAPI/exl3, ISTA GGUF |
| v2 | v1 plus conversation-reuse and reasoning | Unsloth GGUF, 27B GGUF (LM Studio) |

Re-running a v1 recipe with the current suite closes the gap — roughly 6–11 minutes of GPU time.

## What a run measures

Container phases, sampled separately in `results.json`: idle 30 s (warn above 10% system CPU) → load (served model up to 30 min) → settle (CPU quiet for 10 s, up to 120 s) → loaded idle 10 s → suite → unload → after-unload 10 s (RAM/VRAM deltas; these alone do not establish a leak). Desktop runs record settle, loaded idle, and the suite.

The suite runs at concurrency one: functional checks (streaming text, forced tool call, vision) → adaptive warmup (up to 4 requests) → five distinct approximately 8K-token code reviews → three sustained coding tasks (LRU cache, tokenizer, event store; tests requested, code not executed) → approximately 32K/64K/120K-token code reviews (largest runs twice; cases that cannot fit input plus output are skipped) → one fixed multi-turn coding conversation sent cold, then its three growing prefixes replayed → one reasoning request with a multi-step arithmetic task. Output caps: 1,024 tokens (context cases), 2,048 (sustained), 1,536 (reasoning), 256 (conversation turns); sustained replies under 512 tokens are marked insufficient samples.

Long prompts come from the running Python interpreter's standard-library source (PSF-licensed) — comparable runs should use the same Python version. Token pre-counts use each server's endpoint (`/v1/messages/count_tokens` on Strata, `/v1/token/encode` on TabbyAPI, which excludes the assistant prefix) or a calibrated characters-per-token estimate; results show actual reported token counts.

Request policy: performance at temperature 1, top-k 20, top-p 0.95, min-p 0, penalties 0; functional checks at temperature 0. Strata and LM Studio receive explicit `reasoning_effort: none` on all but the reasoning request (`high`) — on LM Studio the Qwen template thinks by default; re-verify the control with [`scripts/probe_lmstudio_thinking.sh`](../scripts/probe_lmstudio_thinking.sh) after app updates. Other servers keep template defaults; use `--request-extra` for an appropriate control. `policy` records these request settings as sent — not verified server behavior — and the configured context, not a queried one. The reasoning case records reasoning and visible text separately (`first_visible_output_s`, character counts); reasoning with no visible text fails the run.

Vision: the default image is [`assets/checks/amdgpu-top.png`](../assets/checks/amdgpu-top.png) with [expectations](../assets/checks/amdgpu-top.expected.json); the JSON-scored answer, image hash, and expectations version are retained. `--image` supplies a custom image for manual review; record encoder image-token settings in the profile — the runner does not detect them.

## Reading results

The run directory holds `meta.json`, `requests.jsonl`, `samples.jsonl`, server logs, `results.json`, and a draft `summary.md`. Rebuild the report without inference (authored text outside markers is preserved):

```bash
python3 scripts/run_baseline.py render <run-dir>
```

[`schema.py`](../scripts/baseline/schema.py) validates the result structure. Every measurement carries value, unit, and source; unavailable ones are `null` with a reason, never zero.

| Key | Content |
|---|---|
| `schema_version`, `suite_version` | Result format and workload-suite versions. |
| `recipe`, `run` | Recipe identity, run ID, and completion status. |
| `server`, `policy` | API kind, served model, configured context; sampling and thinking controls. |
| `boot`, `phases` | Boot readings, warnings, and phase measurements. |
| `functional`, `warmup` | Check outcomes and warmup convergence/duration. |
| `cases`, `resources` | Per-case performance and resource measurements. |

Resources are sampled every 1 s over active request intervals, excluding prompt preparation; polling can miss brief peaks. Server cgroup (CPU cores, charged RAM, swap), system (`/proc`), GPU device (sysfs VRAM/GTT, utilization, power, temperature), and DRM fdinfo server allocations are distinct scopes and must not be added together. The Markdown RAM column shows system-used RAM.

Client first-output latency and decode rate are separate from engine timings; decode is `(completion_tokens - 1) / (last output - first output)` from reported token counts. Repeated cases report medians and relative spread. Cached input tokens come from `usage.prompt_tokens_details.cached_tokens`; when a server omits it, the conversation section compares the identical cold and warm first-output times instead of assuming reuse. Engine timings and draft acceptance come from `server-logs/` matched to requests in order; a mismatch stops matching. LM Studio engine metrics remain unavailable.

What to expect on the current workstation: full suite including load — 5–6 min (Strata), ~11 min (TabbyAPI); TabbyAPI with a draft model legitimately reports warmup "did not converge" because draft acceptance fluctuates; LM Studio first-token spread at mid-range contexts can reach ~96% while decode stays within ~12%, so judge LM Studio first-output noise per case, not by the usual floors.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Run and report completed successfully. |
| 1 | A check/request failed, another run error occurred, or the server could not be stopped. |
| 2 | Invalid arguments or configuration. |
| 3 | Preflight or server startup failed. |
| 130 | Interrupted; partial output kept. |

---

[All recipes](../README.md) · [Authoring](authoring.md) · [Launcher](launcher.md)
