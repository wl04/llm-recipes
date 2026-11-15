# Plan: deterministic experiment capture

## Problem

Dated experiments (`recipes/<recipe>/NNN-YYYY-MM-DD-description/`) mix generated and free-form content:

- `configuration.md` is generated between markers, but only from `profile.yaml`, which is hand-filled for every experiment — including baselines whose data the runner already knows.
- The `settings:` section of `profile.yaml` is a schema-free flat map with human-keyed entries; every key needs a `labels:` entry that is almost always an identity duplicate of the key itself.
- Sampling parameters are captured inconsistently (verified across the seven checked-in experiments):
  - baseline profiles put them into one prose row `Request policy: "Performance: temperature 1, top-k 20, top-p 0.95, min-p 0, …"` although `results.json` already stores them machine-readable under `policy.*`;
  - the flash-next profiles carry sampling twice: a nested `Server sampling` map and the `Request policy` prose;
  - custom experiments use dedicated rows but with drifting names: `Top K` vs `top-k`, `Repeat penalty` vs `repetition penalty`, `Thinking enabled: true` vs `Enable Thinking: On`.
- The same key renders under different labels between sibling experiments: “Context length” vs “Context length (tokens)”; “System recurrent cache MB” vs “System recurrent cache budget (MB)”; “Vision offload” vs “Vision weight offload to system RAM”. Key order differs too.
- `Workload suite` in a profile duplicates `suite_version` from `results.json`.
- A long live coding session (the `002-*` experiments) is reported entirely by hand from console logs: request counts, throughput, context buckets, draft acceptance — although the repo already parses the same per-completion lines in `scripts/baseline/engine_log.py`.
- The launcher records no durable record of an instance it started: effective context/draft/vision overrides, image ID, and host identity are lost once the terminal scrolls away.
- Sudo handling is split: the launcher prompts interactively per Docker call, while the baseline deliberately uses `sudo -n` and tells users to run `sudo -v` first.
- The machine data root `~/Models/llm-recipes` has drifted: per-recipe folders for the two Strata recipes, root-level folders for ExLlamaV3 (its `data_directory: "."`), plus shared `.cache/`, `logs/`, `baselines/`, and conversion work mixed at one level. The repo working tree also doubles as the runtime used for serving, so editing the repo can break a live serve.

## Goals

1. Sampling and thinking parameters always get dedicated rows, with one canonical name each.
2. `configuration.md` is fully deterministic; no experiment requires hand-written table rows.
3. `profile.yaml` stays the single source of truth; zero manual typing for container-recipe baselines, minimal for custom experiments.
4. The launcher is a first-class citizen: every instance leaves a durable machine-readable facts record on disk; host facts need no extra privileges (only Docker does).
5. A coding session on a launcher instance produces a deterministic statistics report from the server's own logs, using the same parser as the baseline suite. LM Studio log support is a later, explicitly scoped stage.
6. One sudo model for both CLIs; the manual `sudo -v` step disappears from the docs.
7. A strict single layout: `$HOME/llm-recipes` as the only data root, `$HOME/.llm-recipes` as a private runtime prefix; the installed runtime is decoupled from the development checkout.
8. Everything stays scriptable and CLI-first so a TUI can wrap the same operations later without changing architecture.
9. All existing experiments are migrated; CI keeps everything current (`scripts/check.sh` already runs `generate_configurations.py --check`).

## Data availability (verified in code)

| Needed fact | Source today |
|---|---|
| Sampling, thinking controls, context, `suite_version`, served model, run id | `results.json` (`policy.*`, `server.*`) — baseline runs only |
| Container image ID, engine/server revisions, repo commit | `meta.json` (`container`, `target`) + `git` (`host.repository_revision`) — baseline runs only |
| Base image digest, torch/python versions, gfx arch, engine/server revisions | `runtimes/<runtime>/container/versions.lock.json` — always |
| Port, default context/draft/vision, native serving settings, model/draft repos + revisions | `recipes/<recipe>/config/launch.json`, `tabby.yml` / `strata.json`, `models.lock.json` — always, but defaults not effective overrides |
| **Effective** launch options of a live instance, container ID/digest, host OS/kernel/driver/GPU/CPU/RAM | **nowhere** — Phase 2 writes them into a facts file at `start` |
| Per-completion prompt/reused/generated tokens, rates, draft counters | `engine_log.py` parses them from `<log-dir>/` file logs (TabbyAPI `*.log`, Strata `engine.log`) — but timestamps and request numbers are dropped today |
| LM Studio per-request log | `~/.lmstudio/server-logs/`, monthly `.log` files (web-verified; re-verify on this workstation before implementation) |
| Repository revision when running from an installed copy (no `.git`) | **nowhere** — Phase 7 writes a `VERSION` stamp and `host.repository_revision` falls back to it |

Notes verified in code:
- The launcher mounts, per `start_command` (`scripts/launcher.py`): `recipe.directory → /recipes/<recipe-id>` (ro), `runtimes/<runtime> → /runtime` (ro), `models → /models` (ro), `models/.cache → /cache` (rw, so `.cache` is a shared cache by design), `logs → /logs`. The instance log dir defaults to `${XDG_STATE_HOME:-~/.local/state}/llm-recipes/<instance>` (`scripts/launch.py:95`), but the recipe `setup.md` files already direct long-lived coding instances to `--logs "$HOME/Models/llm-recipes/logs/<name>"` (physical dirs exist there).
- Baseline default output is `<models>/baselines/<recipe>/<date-time>/` (`scripts/baseline/cli.py`), and `render` reads `templates/recipe/baseline-summary.md` at render time (`cli.py:105`).
- `~/Models/llm-recipes` today: `baselines/`, `.cache/` (comgr, exllamav3, huggingface, triton), `draft-conversion-work/`, `logs/` (strata-coding, strata-unsloth), root-level `qwen3.8-27b-{exl3-3bpw, dflash2-exl3-3bpw, dflash2-source}` (ExLlamaV3 recipe, `data_directory: "."`, its `conversion.work_directory: "draft-conversion-work"`), `strata/` and `strata-unsloth/` (the two Strata recipes' `data_directory` values). The LM Studio recipe has no `config/` at all — its model lives in LM Studio's own model directory and is unaffected.
- `--models` default `Path.home() / "Models/llm-recipes"` appears in: `scripts/launch.py:32,42`, `scripts/baseline/cli.py:45`, `runtimes/strata/scripts/prepare_models.py:170`, `runtimes/exllamav3-tabbyapi/scripts/prepare-models.sh:11`; plus 23 prose references across 7 Markdown files (`docs/launcher.md`, `docs/baseline.md`, `docs/runtimes/exllamav3-tabbyapi.md`, three `setup.md`, `templates/container/setup.md`) and one assertion in `tests/test_baseline_cli.py`.
- pyproject: `requires-python >=3.12`, no runtime dependencies declared; host code imports PyYAML (pinned 6.0.3 in dev-requirements only).

## Phase 1 — Profile schema v2 (structured settings, built-in labels)

Change `scripts/generate_configurations.py` and `templates/recipe/NNN-YYYY-MM-DD-description/profile.yaml`.

- Replace the free-form `settings:` map with fixed groups, each with a canonical key set:
  - `serving:` — engine keys in `snake_case` (`context_length_tokens`, `cache_size_tokens`, `target_cache`, `draft_cache`, `chunk_size`, `max_batch_size`, `vision`, `vision_offload`, `tensor_parallel`, `gpu_selection`, `recurrent_state`, `sysmem_recurrent_cache_mib`, plus engine-specific keys for Strata/LM Studio). Engine-specific keys are allowed here; a shared registry names the common ones.
  - `sampling:` — `temperature`, `top_k`, `top_p`, `min_p`, `repetition_penalty`, `presence_penalty`, `seed`. Whitelisted: an unknown key is a hard error listing the valid keys.
  - `thinking:` — `enabled` (bool/null), `control` (mechanism string), `budget`.
  - `requests:` — `endpoint`, `streaming`, `max_output_tokens`, `token_counting`, `concurrency`.
  - `notes:` — the only free-text field; exactly one string, always rendered last. Replaces “Configuration notes”, the residual prose of “Request policy”, and “Software configuration basis”.
- Delete the `labels:` block from profiles. The generator owns a display-label registry keyed by dotted path (`sampling.top_k` → “Top K”, `serving.context_length_tokens` → “Context length (tokens)”, …), renders sections and rows in registry order (YAML key order stops mattering), and auto-derives Title Case from `snake_case` for engine-specific keys not in the registry. Profiles keep a small optional `labels:` only for genuine per-experiment overrides.
- `Workload suite` and the results-file footer link derive from `results.json` when present; profiles must not repeat `suite_version`.
- Validation: unknown whitelisted key → error; leftover prose keys (`Request policy`, `Server sampling`, `Configuration notes`) → error; same sampling value present in profile while `results.json` has `policy.*` → warning.

Tests: `test_render_uses_registry_labels_for_canonical_sampling_keys`, `test_render_orders_sections_independently_of_yaml_key_order`, `test_render_rejects_unknown_key_in_sampling_section`, `test_render_rejects_request_policy_prose_key`, `test_render_derives_title_case_label_for_engine_specific_serving_key`, `test_render_warns_when_profile_sampling_duplicates_results_json_policy`, `test_render_renders_notes_section_last`.

## Phase 2 — Launcher facts file + unified sudo

Make the launcher record what it actually started, so every later tool reads one durable record instead of guessing or re-probing.

- New shared module `scripts/host_facts.py` (used by launcher, baseline, session tool): hostname, OS name/version, kernel, kernel driver, GPU model + gfx arch + VRAM (sysfs readers from `baseline/sources.py`), CPU model, system RAM. Pure host reads, no sudo.
- On `launch.py start`, after the container is up, write `<instance-log-dir>/facts.json`:
  - instance, recipe, runtime, adapter, engine, started_at;
  - **effective** options after overrides (`port`, `context`, `draft`, `vision`, `models`, `logs`);
  - image reference from `runtime.json` plus `ImageID`/`ImageDigest` from `sudo docker inspect` (the launcher already runs Docker with sudo);
  - mounts and `sha256` of recipe config files (`launch.json`, `tabby.yml`/`strata.json`, `models.lock.json`) so the exact served configuration is pinned even after the repo changes;
  - the `host_facts` block.
  Written atomically per start. Facts describe the latest start; an experiment folder records the snapshot at import time.
- Unified sudo: both `launch.py` and `run_baseline.py` validate/refresh credentials once at CLI start via interactive `sudo -v` with a clear abort message; all internal Docker calls keep `sudo -n` so nothing prompts mid-suite (the current `lifecycle.py`/`host.py` convention). Remove `sudo -v` from `docs/baseline.md`; “run sudo -v and retry” becomes “restart after the credential timeout”. `doctor.py` stays noninteractive by design. This also makes the future TUI safe: a password prompt never appears inside piped subprocess output.

Tests: `test_start_writes_facts_json_with_effective_options_in_instance_logs`, `test_facts_json_pins_image_digest_and_recipe_hashes`, `test_host_facts_reads_os_kernel_gpu_cpu_and_ram_without_privileges`, `test_run_baseline_refreshes_sudo_ticket_once_before_noninteractive_calls`, `test_facts_json_last_start_wins_on_restart`.

## Phase 3 — Zero-edit baseline capture (`import` command)

- Extend `meta.json` with the `host` block (from `host_facts.py`) and the launcher `facts.json` contents when the run is launcher-managed; add to the `schema.py` contract and `docs/baseline.md`. Recorded at run start so the profile describes the measured machine even when imported later or elsewhere.
- Add `python3 scripts/run_baseline.py import <run-dir>` creating the experiment folder inside the repository:
  - name `NNN-date-baseline[-suffix]` (next number per recipe, date from the run),
  - copy `results.json`, seed `summary.md` from `templates/recipe/baseline-summary.md`,
  - write a complete `profile.yaml`: `results.json` (`policy.*` → `sampling`/`thinking`; `server.context_tokens` → `serving.context_length_tokens`) → `meta.json` (`host`, `container`, `target`) → `facts.json` (effective options, image digests, config hashes) → repository (`git rev-parse HEAD` → harness, `versions.lock.json` → engine/server/torch/python/base image, `models.lock.json` → model identities, native serving settings → remaining `serving` rows). Run-time values win over static recipe config; static config only fills fields the run never recorded.
  - run the generator and print the folder. Manual edits for a container baseline: zero.
- Desktop/LM Studio runs (no launcher, no `facts.json`): `import` fills every field `meta.json` provides and leaves the rest `null`.

Tests: `test_import_creates_experiment_folder_with_complete_profile_from_run_directory`, `test_import_prefers_facts_effective_context_over_static_launch_json`, `test_import_falls_back_to_recipe_config_when_meta_lacks_field`, `test_import_desktop_run_leaves_unobserved_fields_null`.

## Phase 4 — Deterministic coding-session report from instance logs

Turn experiments like `002-2026-11-07-coding-gpu-switcher` (today: hand-counted statistics over a console log) into a generated report.

- Extend `engine_log.py` (parser stays shared with the baseline suite):
  - `EngineRequest` gains `sequence` (TabbyAPI `#N` id) and `timestamp` when the line carries one; alignment keeps working on timestampless fixtures;
  - aggregation helpers needing no client: request count, generated tokens, aggregate/median generation rate, fresh-prefill totals, prompt reuse, context-size buckets, draft acceptance totals, time span — the statistics the 002 report states by hand.
- New command `python3 scripts/run_baseline.py session <instance|--logs DIR> [--since --until]`:
  - reads `<log-dir>/facts.json` for the serving configuration and `<log-dir>/*.log` for completions (TabbyAPI file logs; Strata `engine.log`/`server.log`);
  - emits a versioned `session-results.json` (schema in `schema.py`) and renders Markdown tables into a marked block of the experiment's `summary.md` through `report.py` — same marker discipline as baseline summaries;
  - generates the matching `profile.yaml` from `facts.json`, so a session experiment needs hand-written text only in narrative sections outside the markers, if any.
- Cancellation accounting (002 counts a cancelled request): compare started `#N` ids against completed ids in the TabbyAPI log.

**Spikes before implementing (no guessing):**
1. Do real TabbyAPI file-log lines carry a usable per-line timestamp prefix? Checked-in fixtures strip timestamps on purpose (`tests/fixtures/README.md`); extend `scripts/record_fixtures.sh` to also capture `completions.timestamped.log`.
2. Same question for Strata `engine.log` line prefixes.
3. Does the TabbyAPI log distinguish cancelled/disconnected requests from completed ones?
4. Which columns each server's log can provide — report unavailable metrics as unavailable, matching the existing baseline convention.

Tests: `test_parse_tabbyapi_extracts_sequence_and_timestamp_from_timestamped_lines`, `test_session_report_aggregates_generated_tokens_and_rates_over_log`, `test_session_report_buckets_requests_by_context_range`, `test_session_report_reports_draft_acceptance_totals`, `test_session_report_marks_unavailable_metrics_as_unavailable`, `test_session_profile_rows_derive_from_facts_json`.

## Phase 5 — LM Studio instance support (later stage)

Deferred to a later stage; the launcher keeps first-class support for its two container runtimes. Prerequisite is a verified log format, not a guess:

- Web-verified location: `~/.lmstudio/server-logs/`, monthly `.log` files (LMStats analysis tool and an LM Studio file-map article). Re-verify on this Ubuntu workstation (LM Studio Bionic 1.2.0) and check `LMSTUDIO_ENV_STORAGE` overrides before implementing.
- Deliverable: an LM Studio reader in the log-source layer producing the same `EngineRequest` stream, so `session` works unchanged. Columns LM Studio cannot provide (e.g. draft acceptance — engine metrics are already known unavailable there per `docs/baseline.md`) render as unavailable, never estimated.

## Phase 6 — Migrate all experiments, enforce, document

- `scripts/migrate_profiles.py` (reviewed once, kept in repo): map old flat keys to the canonical schema (`Top K` → `sampling.top_k`, `Enable Thinking: On` → `thinking.enabled: true`, engine keys → `serving.*`); split each `Request policy` string once into structured rows, residual nuance (per-case output caps, performance-vs-functional temperature) to `notes`; merge duplicated `Server sampling` maps into `sampling`; drop covered `labels:` and `Workload suite`.
- Regenerate all `configuration.md`; review the diff manually once — it must show only canonical rows, labels, and ordering.
- Golden render test for one canonical profile; cross-experiment consistency test (identical canonical values render to identical rows).
- Docs: `authoring.md`, `baseline.md`, `launcher.md`, `project-instructions.md`; replace experiment templates with schema v2 skeletons.

## Phase 7 — Machine home `$HOME/llm-recipes` (literal rename of the data root), strict model layout, install step

Decouple the development checkout from what actually serves, and give the data root a strict layout. `~/llm-recipes` replaces `~/Models/llm-recipes` one-to-one — it *is* the data root, not a wrapper around it. All facts cited below are verified against code.

### Layout (single default, overridable by env/flags)

New `scripts/paths.py`: two roots, both env-overridable — `LLM_RECIPES_HOME` (data, default `$HOME/llm-recipes`) and `LLM_RECIPES_RUNTIME` (app prefix, default `$HOME/.llm-recipes`). `LLM_RECIPES_HOME` is the data root itself: `--models` defaults to it directly; `--logs` to `<home>/logs/<instance>`; baseline `--output` to `<home>/baselines/<recipe>/<date-time>`; cache to `<home>/.cache`:

```text
~/llm-recipes/                  # data root only — /models mounts here, nothing but data ever
  recipes/
    qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/
      qwen3.8-27b-exl3-3bpw/
      qwen3.8-27b-dflash2-exl3-3bpw/
      qwen3.8-27b-dflash2-source/
      draft-conversion-work/
    qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram/
    qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/
  .cache/             # shared HF/triton/comgr cache → mounted at /cache
  baselines/          # baseline run dirs
  logs/<instance>/    # instance logs + facts.json (Phase 2)

~/.llm-recipes/                 # app-owned private prefix, LM Studio/Ollama style
  app/                # installed runtime snapshot (not a git checkout)
    scripts/ recipes/ runtimes/ assets/ templates/
    .venv/            # runtime-only deps: PyYAML 6.0.3
  VERSION             # {repo commit, installed_at, version} stamp
  bin/                # llm-recipes, llm-recipes-baseline shims (→ app venv)
                      # symlinked into ~/.local/bin, already on PATH per docs/launcher.md
```

- `recipes/<recipe-id>/` mirrors the repository's `recipes/` tree, so a data folder and its recipe config always share a name. It replaces both conventions today: ExLlamaV3's `data_directory: "."` (root-level dirs) and Strata's hand-named `strata` / `strata-unsloth`. Deprecate the `data_directory` field: the launcher derives the data subfolder as `<models>/recipes/<recipe-id>`, so it cannot drift and cannot be set to `.`; `test_recipe_matches_preparation_and_client_with_native_configuration` and the native configs (`tabby.yml` `model_dir`, `strata.json` paths, `models.lock.json` `work_directory`) move under the recipe folder accordingly.
- The data root contains no code: `/models` is pure data forever, model-discovery scans can never walk into a venv, and no data tooling (rsync/borg/find) needs code exclusions.
- **Rename first, move second:** a dedicated Phase-7 commit updates every mention — the five code/shell default locations, the `tests/test_baseline_cli.py` assertion, and the 23 Markdown references listed above — to the new defaults; after that commit the string `~/Models/llm-recipes` no longer exists in the repository. Until the cutover runs, launching requires an explicit `--models "$HOME/Models/llm-recipes"`, which is fine because the cutover follows in the same session. No compatibility symlinks anywhere.

### Install command (decoupling mechanism)

- `scripts/install.py` in the repo: builds `~/.llm-recipes/app.new` by copying the runtime include-list (`scripts/`, `recipes/`, `runtimes/`, `assets/`, `templates/` — exactly what `start_command` mounts and `run_baseline render` reads), writes `VERSION` with the source commit, creates `.venv` with the pinned runtime dependency, then atomically renames `app.new → app` (previous `app` kept as `app.prev` for one rollback step). Refuses to swap while launcher instances run (`sudo docker ps` with labels) unless `--force`.
- `host.repository_revision` gains a fallback: no `.git` → read `VERSION`. Baseline `software.harness_version` records the installed commit identically.
- `~/.llm-recipes/bin/llm-recipes` shim runs `app/.venv/bin/python app/scripts/launch.py "$@"`, symlinked into `~/.local/bin` (already on PATH per `docs/launcher.md`); the dev checkout keeps working the classic way (`bash scripts/check.sh`, explicit `--models`), so serving uses the snapshot and the checkout can stay dirty — the whole point of untying.

### Cutover: `install.py migrate-data` (the last step of the whole plan, fully scripted)

The physical move is performed by `scripts/install.py migrate-data --apply` — a single scripted stop → move → start flow: the operator stops the server from a system terminal, runs the script, and starts instances again from `llm-recipes` (on PATH via `~/.local/bin`) with the new defaults. No compatibility symlinks are created anywhere; the script performs every move itself (the coding agent must not run it — today **strata-unsloth** is the agent's model backend and it dies with the move, which is fine since the server is stopped anyway).

Behavior:
- **Dry-run by default**: prints the exact move manifest; `--apply` executes it. Re-runnable: completed moves are skipped, so a partial cutover finishes on the next run.
- Preconditions (all hard errors): no launcher-managed containers (`sudo docker ps` on the label), no held `.prepare.lock` at the old data root, source and destination of every move on the same filesystem device (`st_dev` — never silently copy 47 GB), destination absent (never overwrite).
- Move manifest (journal written before the first move; each completed `mv` appended, enabling reverse-`mv` rollback documentation; the installer must have run first so `~/.llm-recipes/app` exists — `migrate-data` refuses otherwise):
  1. `.cache`, `baselines`, `logs` → the identically named directories under `~/llm-recipes/`;
  2. `qwen3.8-27b-exl3-3bpw`, `qwen3.8-27b-dflash2-exl3-3bpw`, `qwen3.8-27b-dflash2-source`, `draft-conversion-work` → `~/llm-recipes/recipes/qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram/`;
  3. `strata` → `~/llm-recipes/recipes/qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram/`;
  4. `strata-unsloth` → `~/llm-recipes/recipes/qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram/`;
  5. the old `~/Models/llm-recipes` is now empty — the script removes it (and `~/Models` too only if empty); nothing is created there afterwards;
  6. run `doctor` for every container recipe and print the result.
- Post-checks per move: expected tree exists, `models.lock.json`/`strata.json`-referenced paths resolve under the new location; on failure the script stops and prints the journal for reverse application.
- `docs/project-instructions.md` documents only: stop all instances from a system terminal, run `migrate-data` (dry-run then `--apply`), start instances again from `llm-recipes`.

Tests: `test_paths_default_to_home_llm_recipes_and_runtime_prefix`, `test_recipe_data_directory_derives_from_recipe_identifier`, `test_no_reference_to_old_models_path_remains`, `test_models_mount_contains_no_code_directories`, `test_install_copies_runtime_subset_and_writes_version_stamp`, `test_install_refuses_swap_with_running_instances`, `test_repository_revision_falls_back_to_version_stamp_without_git`, `test_launcher_mounts_recipes_recipe_folder`, `test_migrate_data_refuses_when_instance_running_or_prepare_lock_held`, `test_migrate_data_refuses_cross_device_move`, `test_migrate_data_refuses_without_installed_app`, `test_migrate_data_dry_run_prints_manifest_without_changes`, `test_migrate_data_resumes_after_partial_completion`, `test_migrate_data_never_overwrites_existing_destination`.

## Phase 8 — TUI wrapper (last; architecture-ready only until then)

Use **Textual** (8.2.8, MIT license, Python `>=3.9,<4.0`) as an **optional extra**, never a hard dependency: `[project.optional-dependencies] tui = ["textual>=8.2,<9"]`; `check.sh` and CI stay offline and dependency-free. See Risks for its maintenance caveat.

What the architecture must already guarantee — mostly delivered by Phases 1–7; points 2–4 need no extra work, point 1 is the only remaining increment (`--json` flags) and belongs with the Phase-7 CLI changes:

1. Machine-readable output: add `--json` to `list`, `ps`, `status` (today `ps` prints only a Docker-formatted table from `running_command`). The TUI must consume JSON, never parse prose tables.
2. Operations callable in-process: keep the existing pure builders (`start_command`, `lifecycle_command`) and exit-status `run_command`; the TUI imports `launcher.py` and never shells out to `launch.py`. Keep `launch.py` a thin argparse presentation with no import-time side effects.
3. No interactive prompts inside library functions — the guided interview already injects `_ask`/`_progress` callables (`guided.guide(...)`), the TUI supplies widget-backed callables; the upfront `sudo -v` model (Phase 2) keeps subprocesses prompt-free.
4. Long-running output (`logs --follow`, baseline runs) must be consumable from worker threads via streamed stdout, which the subprocess-returning API already supports.

Scope of the eventual TUI (all sugar over existing commands): recipe list with doctor badges, instance dashboard (`ps`/`start`/`stop`/`logs`), baseline run launcher with the guided interview as forms, and a recent-runs view feeding `run_baseline.py import`/`session`.

## Sequencing

Phases 1 → 2 → 3 → 4 → 6 in separate commits, each keeping `bash scripts/check.sh` green. Phase 7 (code + installer + cutover tooling) lands after 6, with **`install.py migrate-data --apply` as the final step of the entire plan**: stop instances from a system terminal (the coding agent's backend is a launcher instance, so no agent session performs or witnesses the move), run the script, start instances again via `llm-recipes`. The Phase-7 commit and the cutover belong to the same session — there are no compatibility symlinks in the data tree, so the switch is atomic by procedure. Phase 5 (LM Studio) and Phase 8 (TUI) land independently once their prerequisites are met.

## Risks

- Prose carries nuance the schema cannot express. Resolution: exact numbers become structured rows where logs provide them; residual nuance survives in one `notes` line, the only free text.
- Log-line formats change with server updates: parsers already stop matching instead of guessing; session reports degrade to “metric unavailable”; fixtures pin current behavior.
- Facts files describe the latest start only: experiment folders snapshot them at import time.
- Layout move is destructive if interrupted: same-filesystem-only (`st_dev` check), journal with reverse-`mv` documentation, resumable dry-run, never overwrites a destination; `.cache` may be wiped and re-prepared if anything goes wrong.
- The cutover terminates the agent's own model backend (strata-unsloth serves this coding session today): hard precondition on running managed containers, system-terminal-only procedure, documented in `docs/project-instructions.md`.
- Textual maintenance rests with one maintainer after the company wind-down: optional extra only; the CLI contract is the product, the TUI is replaceable.
- Install swap could serve a half-written tree: copy-then-atomic-rename plus refusal while instances run; one-step rollback to `app.prev`.
