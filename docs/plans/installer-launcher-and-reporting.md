# Plan: installer, launcher, and reporting reliability

Review date: 2026-11-16. Code reviewed: `b17aa9f`.

## Implementation order

Implement this plan first. Complete items 1–4, then item 5 together with the
[TUI installation and command integration checklist](tui-dashboard.md#installation-and-command-integration),
then items 6–7. Address item 8 alongside the related fixes.

Item 5 delivers the existing dashboard through `llm-recipes tui`; it does not require the
TUI plan's future baseline-launcher or recent-runs screens. Build those features after this
plan's correctness fixes and validation are complete.

## Assessment

The runtime/recipe separation is useful, native engine configuration stays native, and the
baseline modules have substantial CPU coverage. Configuration generation already has a CI
freshness check. Keep these boundaries. The highest-value work is correctness at installation,
launch, and report-import boundaries, followed by documentation consistency.

This plan changes no serving defaults or recorded measurements. Each item below identifies
observed code behavior; workstation-only behavior still needs target-machine validation.

## 1. Correct imported configuration snapshots — high priority

**Evidence:** `scripts/baseline/importer.py`, `settings_block` and `session_profile`, read native
settings from the current recipe and then override only some launch fields. A local probe using
the actual ExLlama recipe and a recorded context of 163,840 produced `context_length_tokens:
163840` and `cache_capacity: 4096`. The serving adapter sets both `max_seq_len` and `cache_size`
to the requested context. Strata similarly derives `--kv-resident` as `min(context, 32768)`.

The importer also reads current model/build locks. Launch facts contain configuration hashes,
but the importer does not compare them. `_facts` checks the mutable instance log directory
before the run's `server-logs/facts.json` when embedded facts are absent.

- [x] Apply effective launch values consistently in baseline and session imports, including
      dependent cache settings. Reuse a small adapter-specific settings transformation where
      practical; do not introduce another generic configuration schema.
- [x] Prefer embedded facts, then run-local facts, then a live log directory fallback. Validate
      recipe identity when selecting facts.
- [x] Check recorded config hashes before treating current recipe files as the run's settings.
      On mismatch, report the affected fields and require review or leave unknown values unset;
      do not silently describe current files as historical configuration. Keep this lightweight.
- [x] Test context overrides for both adapters, conflicting live/run-local facts, and a recipe
      edited between measurement and import. Audit existing imported profiles for the same
      discrepancies; correct only values supported by their run data.

## 2. Make snapshot installation reliable — high priority

**Evidence:** `scripts/install.py` creates the venv inside `app.new` and renames that directory
to `app`. Python's official documentation says virtual environments are not movable because
installed entry points use absolute interpreter paths. A local disposable-venv probe confirmed
that the moved interpreter runs but an entry point with its original shebang fails with
`FileNotFoundError`. The current launcher shims invoke Python directly, so this is not evidence
that the working launcher itself fails.

Installation also performs two renames without rollback, and every invocation shares the same
`app.new` staging path. A second install can delete another install's staging tree. Tests cover
installation with dependencies skipped, not creation and activation of a real venv.

- [x] Give the venv a stable location, such as under the runtime prefix, and keep code staging
      separate. Use the smallest design compatible with the current small dependency set.
- [x] Serialize installs with a prefix-level lock. Preserve the usable snapshot and restore it
      if activation fails; do not describe two separate renames as one atomic transaction.
- [x] Validate shim destinations before swapping; refuse to replace an unrelated regular file
      in `~/.local/bin` silently. Ensure prefix paths are quoted safely in generated shell shims.
- [x] Add CPU tests for real venv entry points after installation, failed activation, concurrent
      installation, and an unrelated existing executable. No GPU or model downloads are needed.

Reference: [Python venv portability](https://docs.python.org/3/library/venv.html#how-venvs-work).

## 3. Fix first-install authentication and error reporting — medium priority

**Evidence:** the README's installation command calls `running_instances`, which uses `sudo -n`
without first obtaining credentials. A fresh sudo session therefore fails instead of following
the documented first-install flow. `main` catches only `RuntimeError`; missing executables,
filesystem failures, and `TimeoutExpired` can escape as tracebacks.

- [ ] Choose one explicit authentication contract: obtain credentials once in the installer
      CLI, or document `sudo -v` immediately before installation. Keep the library noninteractive.
- [ ] Convert expected subprocess/filesystem failures into concise actionable errors and
      nonzero exit codes. Preserve unexpected programming errors for diagnosis.
- [ ] Test expired sudo credentials, missing Docker/sudo, timeout, and unwritable prefix.
- [ ] Align the README and launcher guide. The guide currently says Docker commands prompt at
      startup, while `doctor` deliberately uses noninteractive inspection.

## 4. Preserve failures in machine-readable status — medium priority

**Evidence:** `scripts/launch.py::_status` ignores Docker's return code and stderr. A local
mocked-daemon-failure probe returned `{"status":"not-found"}` with exit code 0. The existing
test covers a missing instance only.

- [ ] Distinguish an absent container from daemon/permission/inspection failures.
- [ ] Keep `not-found` for a genuinely absent instance; return nonzero with an explicit error
      for infrastructure failures. Document the JSON/exit-status contract.
- [ ] Cover absent, running, permission-denied, and daemon-unavailable cases.

## 5. Bring TUI operations into parity with CLI behavior — medium priority

Delivery contract: one `python3 scripts/install.py install` installs both interfaces, including
pinned Textual. `llm-recipes tui` opens the dashboard from the installed snapshot. The detailed
integration checklist is in the [TUI plan](tui-dashboard.md#installation-and-command-integration).

**Evidence:** `scripts/tui.py::start_instance` calls `prepare_start` and executes Docker without
`record_start_facts`. CLI and baseline starts do record facts, which session import relies on.
The log worker blocks while reading `docker logs --follow`; dismissal only cancels the Textual
worker, and the subprocess is terminated only when the read loop exits. Textual's documented
thread cancellation is cooperative, not a mechanism that interrupts a blocking pipe read.

- [ ] Share the small launch-orchestration step responsible for facts and its warning policy
      between CLI and TUI; retain interface-specific presentation and baseline lifecycle control.
- [ ] Give the log screen explicit ownership of its subprocess. On dismissal/unmount, stop and
      reap it so a quiet log stream cannot strand a worker. Bound termination waits.
- [ ] Add a headless UI lifecycle test with a quiet fake log process and a start test verifying
      facts are recorded. Existing tests do not exercise this cancellation lifecycle.
- [ ] Complete the TUI plan's installation and command integration, including installed-command
      smoke coverage and documentation updates. Keep dashboard imports lazy so ordinary CLI
      commands do not initialize Textual.

Reference: [Textual thread workers](https://textual.textualize.io/guide/workers/#thread-workers).

## 6. Validate generated coding-session summaries in CI — medium priority

**Evidence:** `generate_configurations.py::update_summary` renders `results.json` but not
`session-results.json`. Session blocks are written separately by the baseline CLI. Consequently
the standard generation check cannot detect a stale session block. The current checked-in
Unsloth coding-session block was compared with `report.render_session` and matches today.

- [ ] Make the generator render and check session blocks using the existing renderer, retaining
      authored text and generated markers. Define behavior if both result types are present.
- [ ] Test stale content, malformed data, and missing/duplicate markers. Ensure `--check` never
      writes files and a normal generation pass is idempotent.
- [ ] Update the authoring guide and session template instructions to name the same regeneration
      command. Regenerate affected files after the change.

## 7. Make report creation fail cleanly — medium priority

**Evidence:** `import_run` creates a destination and copies files before all rendering succeeds.
The session command writes data and summary before checking whether facts are available to seed
a missing profile. A reported failure can leave a partial experiment. Baseline recipe names are
checked as nonempty strings, then used directly in a filesystem path.

- [ ] Validate required input, destination containment, and profile/renderability before writing.
      Reject absolute or parent-traversing recipe identifiers at the import boundary.
- [ ] Stage new experiments in a temporary sibling and publish after rendering succeeds; clean
      up staging on failure. For existing session updates, validate all replacements first.
- [ ] Test missing facts, renderer failure, invalid recipe paths, and existing destinations.

## 8. Tighten documentation ownership and small contracts — lower priority

- [ ] Resolve the installed-versus-checkout wording: project instructions say serving never
      runs from the checkout, while the launcher guide, TUI, and baseline runner explicitly do.
      Describe installed serving as the normal user flow and checkout execution as development
      and measurement behavior, matching the code.
- [ ] Correct `record_start_facts`' claim that a start cannot proceed without its record; the CLI
      intentionally warns and proceeds. Keep one documented policy shared by interfaces.
- [ ] Validate `VERSION` as a JSON object in `paths.version_stamp`; valid JSON such as `[]` or
      `null` currently reaches `.get` and raises despite the documented fallback behavior.
- [ ] Add a small documentation-link check if maintained: ignore code examples and template
      placeholders. The review's simple relative-link scan found only inline example links in
      the authoring guide, not confirmed broken navigation links.
- [ ] Defer splitting `Runner` or `aggregate.build_results` until a concrete feature or fix
      benefits; extract pure settings/import helpers first. Avoid replacing the current
      architecture or adding another benchmark framework.

## Delivery and validation

Implement items 1–7 as small, reviewable changes with failing regression tests first. Address
item 8 alongside the relevant fixes. Installer reliability and import correctness are the first
two work packages; neither depends on changing inference settings.

For every package run `bash scripts/check.sh`, including generation freshness checks. Run a
clean-home installation smoke test in addition to unit tests for installer work. On the target
machine verify one launch per runtime, one TUI launch, status with Docker unavailable, closing
a quiet log view, and importing a run with a context override. No new performance measurement
is justified by these tooling fixes alone.

Review validation: 739 tests passed, Ruff lint/format checks and both mypy targets passed,
and generated documents are current. ShellCheck was unavailable locally. Additional evidence
comes from disposable local probes, direct comparison of the checked-in session block with
its renderer, and official Python/Textual documentation. GPU execution, actual Docker
lifecycle, and performance were not tested in this review.
