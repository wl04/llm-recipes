# Baseline runner

The runner measures functional checks, coding workloads, context scaling, and resource use. Each run produces a standalone report. Its implementation is in `scripts/baseline/`.

## Running

For a container recipe, stop other launcher instances and close GPU-heavy applications. Reboot beforehand if practical, then run from the repository root:

```bash
sudo -v
python3 scripts/run_baseline.py run <recipe>
```

The runner starts the recipe as instance `baseline` and stops it afterwards. It checks host diagnostics and refuses to start while another launcher instance is running or the selected GPU holds more than 2 GiB. Recipe defaults can be overridden with `--models`, `--context`, `--draft`, `--vision`, and `--port`.

Output defaults to `<models>/baselines/<recipe>/<date-time>/`, where `<models>` defaults to `~/Models/llm-recipes`. Use `--output` for another new directory outside the repository. Server logs go into `server-logs/` within the run directory.

Ctrl+C or SIGTERM preserves partial records and stops the server started by the runner. `--keep-running` leaves it running. Docker commands use noninteractive sudo; expired authorization can make a later operation fail, including cleanup.

### Desktop apps

Start the app, load the model using the experiment's configuration guide, and start its API server. Then run the guided interview:

```bash
python3 scripts/run_baseline.py run <recipe>
```

It confirms the server URL, the served model (read live from `/v1/models`), the context length configured in the app, and the app's process id for CPU/RAM and process VRAM measurements — detecting a running LM Studio and offering it as the default. Press Enter to accept a default; a wrong model id or a non-positive context is re-asked. Nothing is recorded until you approve the summary. `--yes` accepts every determinable default and stops instead of guessing when models are ambiguous (pass `--model`); it never asks.

Fully explicit options skip the interview: `--base-url http://127.0.0.1:<port>/v1 --model <served-model-id> --context <tokens> --pid <server-pid>`. The runner attaches without starting or stopping the app. `--pid` selects its cgroup; a shared scope produces a warning. Without it, only system/device telemetry is available. A guided run must match the app's real model and context; changing either in the app mid-run invalidates the run.

Other options include `--gpu-pci` (default: the AMD GPU with most VRAM), `--no-gpu`, `--server-kind` (desktop default: `lmstudio`), `--image`, and `--request-extra` (JSON fields merged into request bodies).

## Phases and workloads

Container runs sample these phases separately in `results.json`; the Markdown summarizes boot state and workload measurements rather than rendering every phase.

| Phase | Default behavior |
|---|---|
| Idle | Observe the machine for 30 s; warn above 10% system CPU use. |
| Load | Start the server and wait for a served model, up to 30 minutes. |
| Settle | Wait for system CPU below 15% and server CPU below 0.25 cores for 10 s, up to 120 s. |
| Loaded idle | Observe the loaded server for 10 s. |
| Suite | Run the checks and workloads below. |
| Unload | Stop the server and record stopping time. |
| After unload | Observe for 10 s and record RAM/VRAM changes relative to idle. These changes alone do not establish a leak. |

Desktop runs record settle, loaded idle, and the suite.

The suite runs at concurrency one, in this order:

1. Brief streaming-text, forced-tool-call, and vision checks.
2. Adaptive warmup, up to four requests.
3. Five distinct approximately 8K-token code-review prompts.
4. Three coding tasks: an LRU cache, a tokenizer, and an event store, each with tests requested.
5. Approximately 32K, 64K, and 120K-token code-review prompts. The largest case runs twice; the others run once. Cases that cannot fit input plus output are skipped.
6. Conversation reuse: one fixed multi-turn coding conversation (task, file read, failing test run, applied patch) is sent cold with its full history, then its three growing prefixes are replayed in order.
7. One reasoning request with a multi-step arithmetic task. Strata requests thinking explicitly with `reasoning_effort: high`; other servers keep template defaults.

Output caps are 1,024 tokens for context cases, 2,048 for sustained coding tasks, 1,536 for the reasoning request, and 256 for conversation turns. Sustained replies shorter than 512 tokens are marked insufficient samples. Generated code is not executed.

Long prompts use the running Python interpreter's standard-library source (PSF-licensed). Strata uses `/v1/messages/count_tokens`; TabbyAPI uses `/v1/token/encode` with chat messages and template variables. TabbyAPI's count excludes the assistant generation prefix, so final usage can differ slightly. Other servers use a calibrated characters-per-token estimate. Results show actual reported token counts. Comparable runs should use the same Python version.

### Request policy

Performance requests use temperature 1, top-k 20, top-p 0.95, min-p 0, repetition penalty 1, and presence penalty 0. Functional checks use temperature 0. Strata requests explicitly disable thinking with `reasoning_effort: none`; other servers need an appropriate control through `--request-extra`.

`policy` records sampling defaults, overrides in `request_extra`, explicit thinking controls after overrides in `thinking_request`, and the reasoning request's controls in `reasoning_request`. An empty thinking mapping means unspecified. These describe requests, not verified server behavior. The context value is likewise the configured limit, not an independently queried server value.

The reasoning case records reasoning and visible text separately: `first_visible_output_s` times the first content delta rather than the first output event, and `reasoning_chars` and `visible_chars` count stream text client-side. A reply of reasoning with no visible text is flagged as a failed run.

### Vision check

The default image is [`assets/checks/amdgpu-top.png`](../assets/checks/amdgpu-top.png), with fields defined in its [expectations file](../assets/checks/amdgpu-top.expected.json). The check requests JSON and scores fields as match, mismatch, or missing. Matching all identity fields passes; detail scores are informational. The answer, image hash, and expectations version are retained.

`--image` supplies a custom image for manual review. Record the encoder's image-token settings in the profile; the runner does not detect them. Screenshot memory figures describe the captured image, not the measured server.

## Measurements

Resources are sampled every 500 ms and summarized over active request intervals, excluding prompt preparation. Polling can miss brief peaks.

| Scope | Sources and measurements |
|---|---|
| Server cgroup | CPU consumption in average cores; charged RAM, anonymous/file-cache breakdown, and swap readings. |
| System | `/proc` CPU, RAM, available memory, and swap activity. |
| GPU device | AMD sysfs VRAM/GTT, GPU utilization, power, and temperature. |
| Server GPU allocations | DRM fdinfo for cgroup members, deduplicated by DRM client on the selected PCI device. |

System, cgroup, and device memory are distinct scopes and must not be added together. The Markdown RAM column shows **system-used RAM**; server RAM and process VRAM are also retained in `results.json`. Sample counts and maximum gaps accompany the resource summaries.

Client first-output latency and decode rate are separate from engine timings. Decode is estimated as `(completion_tokens - 1) / (last output - first output)` using reported token counts, not chunk counts. Repeated 8K and largest-context cases report medians and relative spread (range divided by median); other cases are single observations. Mixed finish reasons show per-reason counts. The cached input token count comes from `usage.prompt_tokens_details.cached_tokens`; servers that omit it are reported as unavailable, and the conversation section then states that cache reuse is unknown rather than assuming it.

Engine timings and draft acceptance come from Strata's `engine.log` or TabbyAPI's timestamped `.log` files in `server-logs/`, matched to requests in order. A mismatch stops matching. TabbyAPI durations/rates are rounded in the log; its aggregate decode rate is derived from reported token counts and rates. LM Studio engine metrics remain unavailable.

Calibration from the twelve recorded workstation runs: warmup converges within the 10% tolerance on Strata (2–3 requests of at most 4); with TabbyAPI's draft model the 64-token warmup output does not converge (the two latest decode rates vary by 21–25% because draft acceptance fluctuates), so such runs report "did not converge" and continue. The quiet-system thresholds are met immediately: settle finishes in 0–4 s. Full-suite duration, including load, is 5–6 min per Strata recipe and about 11 min for TabbyAPI; time-to-ready is 8–36 s. Repeated-case noise floors are comparable across recipes (first-token spread median 0.7–2.8%, decode 4.2–5.8%). The 512-token minimum sustained output never bound (observed minimum 1706 tokens). Monitoring overhead and LM Studio thresholds still need validation on the workstation.

## Saved results

The external run directory contains `meta.json`, `requests.jsonl`, `samples.jsonl`, server logs, `results.json`, and a draft `summary.md`. Rebuild the report without inference with:

```bash
python3 scripts/run_baseline.py render <run-dir>
```

Rendering preserves authored text outside generated markers. [`schema.py`](../scripts/baseline/schema.py) validates the result structure; the documentation generator renders and checks its Markdown.

| Key | Content |
|---|---|
| `schema_version`, `suite_version` | Result format and workload-suite versions. |
| `recipe`, `run` | Recipe identity, run ID, and completion status. |
| `server` | API kind, served model ID, configured context. |
| `policy` | Request sampling and thinking controls. |
| `boot`, `phases` | Boot readings, warnings, and phase measurements. |
| `functional`, `warmup` | Check outcomes and warmup convergence/duration. |
| `cases`, `resources` | Per-case performance and resource measurements. |

Measurements carry a value, unit, and source. Unavailable measurements use `null` with a reason, not zero. Additional metrics vary with the case and available observations.

To add a baseline to the repository, follow the [authoring guide](authoring.md): copy `results.json` and `summary.md` into a numbered experiment folder, fill in `profile.yaml`, and run the generator. The profile holds hardware, software/model identities, and inference settings. Record the runner commit in `software.harness_version` and the suite in `settings.Workload suite`. Raw diagnostic files stay external.

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
