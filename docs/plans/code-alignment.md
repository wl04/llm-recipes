# Plan: AGENTS.md alignment follow-ups

Scope: gaps found while checking the repository against `../AGENTS.md` rules for commands and
queries, boundaries and errors, tests, Python, shell, and documentation. CPU validation is green
(`bash scripts/check.sh`: Ruff, mypy strict on both runtime trees, 739 tests, generated-document
check, ShellCheck), so every item below is a contract, consistency, or maintainability fix rather
than a broken build.

Rules that are already satisfied and need no work: typed public boundaries under strict mypy,
specific `except` clauses with `raise ... from` on every translated error, no bare `except`,
no mutable default arguments, file handles only through `with`, no commented-out code or
`TODO`/`FIXME`, no credentials in code, `Operation_Behavior_Context` test names across 565 tests,
condition-based waits with timeouts in the sampler suite, and shell scripts with bash shebangs,
`set -euo pipefail`, quoted expansions, `usage` exits, and stderr diagnostics.

## P1 — isolation and environment contracts

- [ ] `tests/test_launcher.py` and `tests/test_setup_units.py` are the only test modules written as
      `unittest.TestCase`; the other 35 use pytest functions. Convert them: `self.assertEqual` to
      `assert`, `assertRaises`/`assertRaisesRegex` to `pytest.raises(..., match=...)`,
      `contextlib.redirect_stdout` to `capsys`, `unittest.mock.patch` to `monkeypatch`, and drop
      `if __name__ == "__main__": unittest.main()`.
- [ ] In the same file, pass arguments through the existing contract instead of patching process
      globals: `launch.main(["stop", "exl3"])` takes an `argv` list, so replace every
      `patch.object(sys, "argv", ...)`; assert the exit status, not only the mocked call.
- [ ] `tests/test_launcher.py` reads a real recipe folder into a module-level `RECIPE`. Build the
      recipe in a fixture (`tmp_path` + the `write_recipe` helper style already used by
      `tests/test_recipe_discovery.py`), so a recipe rename cannot break unrelated cases.
- [ ] `tests/test_baseline_cli.py:103` asserts `(Path.home() / "llm-recipes")`, which fails whenever
      the documented `LLM_RECIPES_HOME` override is exported. Set the variable explicitly through
      `monkeypatch.setenv(paths.DATA_HOME_ENV, ...)` and assert the derived path from it.
- [ ] Remove the duplicated `sys.path.insert` for `scripts/` in `tests/test_launcher.py`,
      `tests/test_recipe_discovery.py`, `tests/test_doctor.py`, `tests/test_strata.py`,
      `tests/test_serve_validation.py`, and `tests/test_preparation_lock.py`; `tests/conftest.py`
      adds that entry for the whole suite. Keep inserts that point at runtime helper trees.
- [ ] `.github/workflows/check.yml` validates one interpreter while `pyproject.toml` allows
      `>=3.12` and the development virtualenv runs a newer release. Test a version matrix
      (`3.12` and the interpreter used locally) or narrow `requires-python` to the validated range.
      Add `timeout-minutes` and a `concurrency` group that cancels superseded runs.

Verification for this section: `bash scripts/check.sh`, plus `LLM_RECIPES_HOME=/tmp/llm-recipes-home
bash scripts/check.sh` passing with the override set.

## P2 — make the conventions enforceable

- [ ] Extend `[tool.ruff.lint] select` with the rule families that encode the AGENTS.md rules, so
      drift is caught by CI instead of review:
      `PT` (pytest style; currently flags 25 unittest-style assertions and 2 `assertRaises`),
      `BLE` (blind `except Exception`; currently 7 sites that need a justification comment),
      `TRY` (error translation; currently zero findings, so free to keep clean),
      `ERA`, `RET`, `C4`, `PIE` (small cleanups), `ARG002` (unused method arguments),
      `PLW1510` (explicit `check=` on `subprocess.run`).
      Measure first with `ruff check . --select <codes> --statistics`; adopt the families with
      zero or small counts and land the mechanical fixes (`--fix`) in a formatting-only commit,
      separate from behavior changes as the project instructions require.
- [ ] Add `ANN401` (explicit `Any`) as a tracked rule once the 13 production occurrences are typed
      precisely: the metric builders in `scripts/baseline/aggregate.py:259-284` return
      `dict[str, Any]`-shaped records that a shared alias or `TypedDict` describes, and
      `scripts/baseline/functional.py:29`, `scripts/baseline/report.py:376`,
      `scripts/baseline/importer.py:124-133` narrow to `dict[str, object]` where callers only read
      fields. Keep `Any` for raw JSON at parse boundaries and note the reason in the ignore comment.
- [ ] Add `scripts/host_facts.py` to `[tool.mypy].files`; today it is analyzed only because tests
      import it, so a direct CLI call would be unchecked.
- [ ] Decide on `shfmt`: `AGENTS.md` names it "if configured" while `scripts/check.sh` runs
      ShellCheck only. Either add a `shfmt -d` step (with the version pinned in
      `dev-requirements.txt` and installed in CI) or state in the project instructions that
      ShellCheck is the shell gate.
- [ ] Register pytest markers (`[tool.pytest.ini_options] markers`) and mark the subprocess-spawning
      cases in `tests/test_launcher.py` so the fastest unit subset stays selectable.

## P3 — remove duplicated host rules

- [ ] `runtimes/exllamav3-tabbyapi/scripts/prepare-models.sh` defaults the data root to
      `$HOME/llm-recipes`, ignoring `LLM_RECIPES_HOME` and therefore `scripts/paths.py`. Resolve the
      default once, for example `python3 "$runtime_dir/../../scripts/paths.py" --data-home` or an
      exported variable from the caller, and keep the container mount derived from it.
- [ ] The same script rebuilds the GPU device-group arguments (`stat -c %g /dev/kfd`,
      `/dev/dri/renderD*`) that `gpu_groups()` in `scripts/launcher.py:245` already owns. Extract
      the group list into one host-side helper and have the preparation script consume it, so
      container launches share a single rule.
- [ ] Two host modules implement the same AMD selection rule: scan `/sys/bus/pci/devices` for
      vendor `0x1002`, read `mem_info_vram_total`, and sort by size descending —
      `scripts/host_facts.py:_amd_devices` and `scripts/baseline/sources.py:find_gpu`. Keep one
      implementation with the injected filesystem root that both already accept; the differing
      exception types (`HostFactsError`, `SourceError`) stay in the callers.

## P4 — split responsibilities in large units

Refactor only while touching these files for another reason; the tests below define the behavior to
preserve. `launch.main(argv) -> int`, `RunWriter`, `RawRun`, and `ServerControl` stay as they are.

- [ ] `scripts/baseline/runner.py` — `Runner` holds 32 methods in 636 lines across three
      responsibilities: run orchestration (`run`, `_start_server`, `_settle`, `_shutdown`), request
      primitives (`_payload`, `_post`, `_stream_call`, `_stream_request`, `_prompt_request`,
      `_count_tokens`), and per-case checks (`_check_text`, `_check_tools`, `_check_vision`,
      `_warmup`, `_probe`, `_sustained`, `_conversation`, `_reasoning`, `_contexts`). Move the
      request primitives into a small collaborator built from `config` plus `api`, keeping
      `Runner` as the coordinator; `tests/test_baseline_runner.py` guards the observable records.
      Then replace the 9-parameter `_prompt_request` and 7-parameter `_stream_request` with one
      request-spec parameter object.
- [ ] `scripts/baseline/cli.py:_run_command` (134 lines, 20 branches) — split into validation,
      plan and `RunConfig` assembly, and execution-plus-reporting; keep `--yes` and desktop-recipe
      argument checks in the validation step so a bad invocation never reaches the host. Covered by
      `tests/test_baseline_cli.py`.
- [ ] `scripts/launch.py:main` (115 lines) — one small function per action (`ps`, `status`,
      `list`, `doctor`, `start`) plus the shared `ValueError`/`OSError` handling, keeping JSON and
      table rendering in the presentation layer as `docs/launcher.md` describes. Covered by
      `tests/test_launcher.py` after the P1 conversion.
- [ ] `scripts/install.py:migrate_data` (85 lines, 20 branches) — separate the preflight checks,
      the move plan with journal updates, and the reporting of leftovers, so the dry run and
      `--apply` paths share one plan builder. Covered by `tests/test_install.py`.
- [ ] `scripts/baseline/schema.py:validate_results` and `validate_session_results` — extract the
      repeated metric and case-entry checks into helpers; these are the contract gate for
      `results.json`, so each rule keeps its own message. Covered by `tests/test_baseline_schema.py`.

## P5 — test-quality polish

- [ ] `tests/test_baseline_runner.py:415` waits a fixed 50 ms before re-reading the run directory;
      use a bounded condition wait like the helper in `tests/test_baseline_sampler.py:29` so the
      case cannot pass by timing luck.
- [ ] Type that helper: `wait_until(condition: Any, ...)` accepts `Callable[[], bool]`.
- [ ] `tests/test_recipe_discovery.py:92` asserts `pytest.raises(ValueError)` without `match=`
      while the neighbouring cases match the message; state the expected reason.
- [ ] `pytest.mark.parametrize` names should be tuples: `tests/test_recipe_discovery.py:84`,
      `tests/test_recipe_discovery.py:169`, `tests/test_strata.py:63`.
- [ ] Add `check=False` where `subprocess.run` deliberately inspects a non-zero exit code
      (`tests/test_launcher.py:78`, `:97`, `:118`).
- [ ] `scripts/record_fixtures.sh` picks an engine-log file with `find ... | sort | head -1`;
      read NUL-delimited paths (`find -print0` with `read -r -d ''`) so unusual names cannot shift
      the selection.
