# Baseline contract

This page defines the baseline runner's result format and measurement rules and how to run it. The runner is implemented in `scripts/baseline/`; the [implementation plan](../plans/unified-baseline.md) tracks the remaining workstation validation.

One execution per recipe produces one baseline. For a container recipe the runner owns the server for the duration: it records the machine at rest, starts the server through the launcher, measures the load, runs the suite, and stops the server, so every baseline starts from a known state.

## Running

Reboot if you can, stop other servers (`python3 scripts/launch.py ps`, then `stop <instance>`), and close applications that use the GPU. Then, from the repository root:

```bash
sudo -v
python3 scripts/run_baseline.py run <recipe>
```

The launcher uses `sudo docker`, so authenticate first. The runner starts the container as instance `baseline`, with the recipe's launch defaults; `--context`, `--draft`, `--vision`, `--port`, and `--models` override them. It refuses to start when diagnostics fail, when another launcher instance is running, or when the GPU already holds more than 2 GiB.

Results go to `~/Models/llm-recipes/baselines/<recipe>/<date-time>/` (under `--models`, or `--output` for any new directory outside the repository), and the server's logs go to `server-logs/` inside it. Progress goes to stderr and a one-line result to stdout. Ctrl+C or SIGTERM stops the suite, stops the server the runner started, and keeps what was recorded. `--keep-running` leaves the server running afterwards, for debugging.

The run directory holds `meta.json`, `requests.jsonl`, `samples.jsonl`, the server logs, and the rendered `results.json` and draft `summary.md`. `python3 scripts/run_baseline.py render <run-dir>` rebuilds the rendered files from the raw ones, for example after an interrupted run, and keeps the text you wrote in `summary.md`. To publish, create the numbered experiment folder, copy `summary.md` and `results.json` into it, fill in `profile.yaml`, and run the generator.

### Phases

Each phase is sampled and reported separately:

| Phase | What happens |
|---|---|
| idle | Nothing loaded; 30 s of system-wide readings: CPU, memory, swap, GPU memory, power, temperature. A busy system here (more than 10% CPU) adds a warning. |
| load | The server starts and is polled until it serves a model, with a 30-minute timeout. Records time to ready and the load's peaks, including the cold-cache cost after a reboot. |
| settle | Waits until system CPU (under 15%) and server CPU (under 0.25 cores) stay low for 10 s, for at most 120 s. A note is added if it does not settle. |
| loaded idle | 10 s with the model loaded and the server quiet: the model's resting footprint. |
| suite | Functional checks (text, forced tool call, vision), an adaptive warmup of up to four requests, the 8K case repeated five times, three sustained-generation tasks, then 32K, 64K, and 120K contexts. The 120K case runs twice, with distinct content each time, and the report shows the spread between the two runs; the 32K and 64K cases and the sustained tasks are single observations. Cases whose input plus output cannot fit the context are skipped. |
| unload | The server is stopped. Records time to stop. |
| after unload | 10 s of observation once the server has stopped. Records whether VRAM and available RAM returned to the idle level, which exposes leaks. |

Every request has distinct content. Prompts are sized with the server's tokenizer route before they are sent (Strata: `/v1/messages/count_tokens`), because characters per token varied from 2.5 to 4.5 across the corpus in the first pilot. Servers without a known route fall back to calibrating from the previous request's reported token count, which is less exact; the run records which method was used. The thresholds above are provisional until the workstation pilot.

### Desktop apps

Desktop apps such as LM Studio are not started by the runner yet; a guided mode with confirmations is planned. Until then, start the app, load the model with the settings in the recipe's `configuration.md`, start its server, and run:

```bash
python3 scripts/run_baseline.py run <recipe> --base-url http://127.0.0.1:<port>/v1 \
  --model <served-model-id> --context <tokens> --pid <server-pid>
```

Only the settle, loaded-idle, and suite phases are recorded in this mode, because the idle machine and the load were not observed. `--pid` can be any process of the app: the runner measures its whole systemd scope (GNOME gives each application its own, such as `app-<name>-<pid>.scope`), lists the processes in it, and warns when the scope is shared, for example when the app was started from a terminal. Other options: `--gpu-pci` (default: the AMD GPU with the most VRAM), `--no-gpu`, `--image`, `--server-kind`, and `--request-extra` (a JSON object merged into every request).

### Current limits

- Thinking is disabled by default only for Strata (`reasoning_effort: none`). For other servers set the server's own field with `--request-extra`; the result records whether the default applied.
- Engine-reported timings come from the server's own log, which the runner keeps in `server-logs/engine.log`. Only the Strata log format is parsed (prefill and decode speed, draft acceptance), matched to the requests in order; a mismatch stops the matching and says why. For TabbyAPI and LM Studio those columns are unavailable. Client timings are measured for every server. Engine prefill speed is only meaningful for long prompts.
- The long contexts are built from the interpreter's standard-library source (PSF-licensed code), so comparisons assume the same Python version.
- The image-token setting is not detected; note it yourself when it matters for the vision scores.
- Thresholds are provisional until the workstation pilot: GPU more than 5% busy at start, system CPU more than 10% busy during the idle phase, the settle limits above, and a 10% warmup tolerance. Load average is recorded but does not warn.
- The tokenizer route and the server's reported usage can differ by a few tens of tokens (about 0.5% at 8K on Strata); the table shows the server-reported count.

## Result document

`results.json` is machine-written JSON with a fixed key order, two-space indent, and a trailing newline. [`scripts/baseline/schema.py`](../scripts/baseline/schema.py) validates it, and `scripts/generate_configurations.py` renders it into the marked results block of the experiment's `summary.md`.

| Key | Content |
|---|---|
| `schema_version`, `suite_version` | Format version, and the version of the workload suite (prompts, expectations, and case list). Runs from different suites are not compared silently. |
| `recipe` | Recipe folder name. |
| `run` | `status` (`complete`, `interrupted`, `failed`); optional run identity and repository revision. |
| `server` | `kind` (`strata`, `tabbyapi`, `lmstudio`), served `model`, actual `context_tokens`. |
| `boot` | Optional boot-state metrics (uptime, idle readings) and warnings. |
| `functional` | One entry per check with `status` (`pass`, `fail`, `unparsed`, `skipped`). |
| `warmup` | Request count, whether it converged, and duration. |
| `cases` | One entry per workload case: `id`, `status`, `runs`, `finish_reason`, optional `note`, and `metrics`. |
| `resources` | One entry per case with resource `metrics`. |

### Metrics

Every metric is either measured or unavailable:

```json
{"value": 81.5, "unit": "tokens/s", "source": "client estimate"}
{"value": null, "unavailable": "server reports no timings"}
```

An unavailable measurement is never zero and never omitted. Units are part of the metric. Client timings and engine timings are separate metrics with their own sources. Case metrics the table shows: `input_tokens`, `output_tokens`, `cached_input_tokens`, `first_output_s`, `client_decode_tok_s`, `engine_prefill_tok_s`, `engine_decode_tok_s`, and `noise_first_output_spread` / `noise_decode_spread` for the repeated 8K case. Resource metrics: `cpu_cores_avg`, `ram_peak_gib`, `system_available_min_gib`, `vram_peak_gib`, `gtt_peak_gib`, `swap_in_pages`, `swap_out_pages`.

The client decode rate is `(completion_tokens - 1) / (last output - first output)`, using reported token counts. It does not assume one streamed chunk is one token. The noise floor is the range over the median of the repeated 8K case.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Run completed and the report was written. |
| 1 | Run completed with failed functional checks or requests, or the server could not be stopped. |
| 2 | Invalid arguments or configuration. |
| 3 | Preflight or start-up failed: diagnostics, another running instance, a busy GPU, a server that did not start or become ready, a model mismatch, or no non-interactive `sudo`. |
| 130 | Interrupted. Partial output is kept. |

## Server capabilities

Servers differ in what they report. Capabilities are discovered by probing the running server and recorded; they are not assumed. A capability that was not probed is recorded as unknown, and the metric that depends on it is unavailable. This covers streaming usage, cached-token counts, engine timings, token-count routes, and cache controls. The Strata helpers use `POST /v1/messages/count_tokens` and streamed usage; TabbyAPI and LM Studio still need to be recorded against real servers (see [fixtures](../tests/fixtures/README.md)).

## Telemetry sources

Verified on the target workstation (RX 9070 XT at `0000:03:00.0`, plus an iGPU at `0000:12:00.0`, so devices are selected by PCI address):

| Metric | Source |
|---|---|
| GPU busy, VRAM, GTT | `/sys/bus/pci/devices/<address>/gpu_busy_percent`, `mem_info_vram_used`, `mem_info_gtt_used` |
| GPU power, temperature | `hwmon` in the same device directory (`power1_average`, `temp1_input`) |
| Container CPU, memory, swap | cgroup v2 files, readable without privileges once the container's cgroup path is known |
| System memory, swap activity | `/proc/meminfo`, `/proc/vmstat` |
| Process allocations | DRM fdinfo (`drm-memory-vram`) of the processes in the server's cgroup, one value per DRM client on the target GPU. Read at every sample. |

The launcher's `sudo docker` commands run non-interactively (`sudo -n`), so an expired `sudo` timestamp fails the run at start instead of prompting mid-run. Device memory is device-wide and is not added to cgroup or process figures.

## Desktop recipes

Desktop recipes (for example LM Studio) have no launch manifest. The runner resolves the recipe by folder name for identity and output naming, and requires the endpoint and context; `--pid` selects the app's cgroup.

## Experiment profile

`profile.yaml` stays hand-curated. The runner records what it verified (served model, context, request policy) in `results.json`; transfer those into the profile. Set `software.harness` to the llm-recipes baseline runner, `software.harness_version` to the repository commit URL, and `settings.Workload suite` to the suite version.

## Vision check

All recipes use `assets/checks/amdgpu-top.png`. [`assets/checks/amdgpu-top.expected.json`](../assets/checks/amdgpu-top.expected.json) lists the expected fields in two tiers. The prompt is built from that file and asks for a JSON object. Each field scores `match`, `mismatch`, or `missing`. The check passes when every `identity` field matches; `detail` fields are informational because small text depends on the image-token budget. Record the image-token setting beside the scores. The values in the screenshot (the VRAM figures and the `strata-host` process) belong to the capture, not to the server being measured. The scores are a text-matching check on one screenshot, not a general claim of image understanding.

---

[All recipes](../README.md) · [Authoring](authoring.md) · [Launcher](launcher.md)
