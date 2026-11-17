# Plan: diagnostics triage and static analysis policy

Review date: 2026-11-16. Code reviewed: `06e45e5`. Checkers: mypy `2.4.1` in
`scripts/check.sh`; basedpyright over LSP through pi-lens 4.5.1.

## Completion status

- [x] 1. Reproducible baseline separated by producing checker
- [ ] 2. Classify the unclassified blocking findings
- [ ] 3. Constrain outbound model and source fetches
- [ ] 4. Make the module search path config-relative and prove which config file each checker reads
- [ ] 5. Scope container-only imports with execution environments
- [ ] 6. Parity between the checkers on stale suppressions
- [ ] 7. Disposition the mitigated tarfile extraction sites
- [ ] 8. Set policy for the lexically blind throwing-call rule
- [ ] 9. Keep fixture literals out of the spell-check lane
- [ ] 10. Decide the advisory-runner and coverage-warning policy
- [ ] 11. Record the analysis policy in project instructions

## Implementation order

Item 1 fixes the measurement, item 2 reads the findings nobody has read, and both precede any
disposition. Items 3 and 7 are security work and independent. Items 4–6 are the checker
configuration and land in that order: the config location must be proven before scoping, and
scoping before the parity flag can be evaluated. Items 8–10 are advisory-lane policy. Item 11
closes the plan.

## Assessment

The editor counter and a workspace sweep measure different populations, and a lane reports fewer
findings cold than warm: the same `ast-grep` rule produced nothing under `runtimes/` in the session's
first sweep and 22 findings in a later one, with no change to those files. A `severity=error` sweep
over 86 scanned files reported 18 blocking findings; a `severity=all` sweep with a longer wait budget
reports **99 findings across 8 rule types, 41 at error severity, over 25 files**, with 9 push-only
lanes not answering. Counts are therefore read per rule id, and an unconfirmed lane is stated rather
than folded into a total.

Evidence per rule id, the verdict on each, and the disposition mechanism each tool documents live in
[../diagnostics-inventory.md](../diagnostics-inventory.md). This plan changes code and configuration.

What matters first is which tool produced each finding, because the fix belongs to that tool:

| Producer | Findings in scope | Owner of the fix |
| --- | --- | --- |
| mypy (`check.sh`) | none outstanding | already the build gate |
| `Pyright:reportMissingImports` — `torch` ×3, `exllamav3` ×3, `exllamav3_ext`, `common.config_models` ×2, `common.sampling`, `huggingface_hub`, `serve.server` | 12 | pyright configuration, by path scope |
| `ast-grep:unchecked-throwing-call-python` — 4 in `scripts/` (`doctor.py:26`, `install.py:119,176,214`), 23 in `runtimes/` | 4 cold, 27 warm | item 8, no mypy or pyright equivalent exists |
| `tarfile-extractall-traversal` (both `container/fetch_sources.py`) | 2 | already mitigated; per-line rule disposition |
| `unchecked-numeric-parse-python` 48, `no-ellipsis-body` 4, `no-yield-from-non-iterable` 1 (ast-grep warnings), `dynamic-urllib-use-detected` 3, `typos` 2 | 57 | items 3, 8, 9, 10 |
| `python-path-traversal`, `python-insecure-deserialization` (opengrep) | seen on the push advisory lane only; the sweep's opengrep lane timed out | item 8 |

`bash scripts/check.sh` reports the Python sources clean, so every blocking finding in the table
except the import class comes from a checker that CI never runs. That distinction decides the
remedy: a pyright diagnostic gets pyright configuration, and a pi-lens lane finding gets either a
code fix or that lane's own documented policy mechanism — never a new rule.

Each checker has one scoping axis, and both are documented:

- mypy scopes by **imported module name**: `[[tool.mypy.overrides]]` with the note that *"If this
  option is used in a per-module section, the module name should match the name of the imported
  module, not the module containing the import statement."* The repository already relies on this
  for `torch`, `huggingface_hub`, `exllamav3`, and the runtime `serve` helper.
- Pyright scopes by **path**: `include`, `exclude`, `ignore`, `strict`, and `executionEnvironments`.
  The execution environment section states, verbatim: *"In addition, any of the type check
  diagnostics settings listed above can be specified. These settings act as overrides for the files
  in this execution environment."* Its sample config shows exactly that shape, with
  `"reportMissingImports": "warning"` inside one environment.

Reference: [pyright configuration](https://github.com/microsoft/pyright/blob/main/docs/configuration.md),
[mypy configuration file](https://mypy.readthedocs.io/en/stable/config_file.html).

## 1. Reproducible baseline separated by producing checker

**Evidence:** the procedure and the baseline it produced are what every later item measures against.

- [x] Procedure: `lens_diagnostics` with `source=lsp`, `mode=full`, `scope=workspace`,
      `severity=error`, `waitMs` of at least 6000, `concurrency=8`. Repeat until no
      `Auxiliary coverage INCOMPLETE` line names a scanner lane: a lane that did not answer for a
      file leaves that file unconfirmed rather than clean.
- [x] Baseline (86 files scanned, 8 with errors): 18 blocking findings, being 12
      `Pyright:reportMissingImports`, 2 `tarfile-extractall-traversal`, and 4
      `unchecked-throwing-call-python`. Count per rule id rather than by total, since totals move
      with scanner coverage while rule rows stay comparable.
- [x] `~/.pi-lens/dispositions.log` holds no entries, so every finding in the table is unjudged.
- [ ] Re-run until the throwing-call lane is confirmed for `runtimes/`: it answered for `scripts/`
      and reported nothing under `runtimes/`, which is an unanswered lane until a run names it.

## 2. Classify the unclassified blocking findings

**Evidence:** every blocking site was read against its callers.

- `scripts/doctor.py:26` loads `json.loads(path.read_text())` inside `read_json`. Every caller
  catches `(OSError, ValueError, KeyError, TypeError, IndexError)` and returns a `FAIL` finding
  (lines 34 to 45, 76 to 85, 150 to 173, 259 to 268). Verdict: caller-level handling by design, so a
  wrapper here would duplicate existing handling.
- `scripts/install.py:119,176,214` remove the stale environment, the previous snapshot, and the
  staging directory with `shutil.rmtree`; all three propagate to `main`'s
  `except (OSError, RuntimeError, subprocess.SubprocessError)` at line 256. At `:119` a swallowed
  failure would leave a half-removed environment, and line 122 would then write the `.ready` marker,
  turning one failure into a success that survives every later run. Verdict: correct as written, and
  swallowing is the one unsafe edit among the three options.
- `runtimes/exllamav3-tabbyapi/scripts/serve.py` holds two blocking findings, both unresolved
  container imports (`common.config_models` at `:35`, `common.sampling` at `:42`) reached after
  `sys.path.insert(0, "/opt/src/tabbyAPI")` inside `validate_sections`; neither is fixable outside the
  image. The file carries no throwing-call finding. Of its six `json.loads` calls, `:54` is guarded by
  `check_manifest_file` with path context, and `:100`, `:101`, `:102`, `:170` are container-startup
  reads that fail fast naming the file, which is what an entry point should do. `:152` differs:
  `json.loads((recipe / "config/launch.json").read_text())["runtime"]` raises before the intended
  `parser.error`, so a wrong `--recipe` path or a missing mount produces a traceback instead of the
  CLI's exit-2 message. Verdict: one real defect, at `:152`.
- `runtimes/strata/container/Dockerfile` reports clean, and the Docker language server answers for
  it, so the file is confirmed rather than unconfirmed.
- One behaviour of the throwing-call rule is worth recording: it flags
  `json.loads(path.read_text())` at `doctor.py:26` and stays silent on the parenthesised argument at
  `serve.py:100`. Same call, same raisability, different output. Its counts therefore track pattern
  shape, not defects.

- [x] Read every blocking site and record the verdict above.
- [x] Confirm the strata `Dockerfile` finding: no finding under the Docker server.
- [ ] Reproduce `python-path-traversal` at `severity=all` and compare each site against the
      containment checks that exist; close a gap or record the guard as the reason.
- [x] Fix the recipe guard in `serve.py` so unreadable, non-object, or keyless launch settings reach
      `parser.error` instead of a traceback; `tests/test_serve_validation.py` now drives `main` through
      each of those cases plus the runtime mismatch and asserts exit code 2.
- [x] Re-check `check_hip.cpp`: `clangd` is installed at `~/.pi-lens/tools/clangd/bin/clangd`, so the
      file was measured rather than assumed absent. It reports fifteen errors, all from the absent
      `hip/hip_runtime.h` (no ROCm on this workstation), and one `cpp-no-printf` warning. Dispositioned
      under items 10 and 11; `runtimes/strata/container/.clangd` now carries the path-scoped carve-out.

## 3. Constrain outbound model and source fetches

**Evidence:** `runtimes/exllamav3-tabbyapi/container/fetch_sources.py:32` and
`runtimes/strata/container/fetch_sources.py:34` call `urllib.request.urlopen(url, timeout=120)`;
`runtimes/strata/scripts/prepare_models.py:47` calls `urlopen(request, timeout=120)`. The URL is
composed from `versions.lock.json`, and `urllib` accepts `file://` and plain `http://`, so a
modified or mirror-substituted lock can move a build to an arbitrary scheme or host. opengrep
reports these as `dynamic-urllib-use-detected` (CWE-939).

- [x] Measured before writing code, and the premise did not hold: all four network call lines build the
      URL from a literal `https://` and a literal host (`codeload.github.com` in both `fetch_sources.py`,
      `huggingface.co` in `prepare_models.py`); the lock supplies path segments only, so no value can
      move the scheme or the authority. `HF_ENDPOINT` is assigned a literal in a child environment and
      never read as input, and every download is size-bounded and checked against a pinned SHA-256.
- [x] Closed on that evidence: a scheme-and-host check over a value that cannot vary in scheme or host
      restates the line above it. The three findings are dispositioned, with the reasoning recorded in
      `docs/diagnostics-inventory.md` and the publisher's own classification of the rule as an audit
      rule quoted there.

## 4. Make the module search path config-relative and prove which config file each checker reads

**Evidence:** `pyproject.toml` sets `mypy_path = "scripts"`. mypy's own documentation states:
*"Relative paths are treated relative to the working directory of the mypy command, not the config
file. Use the `MYPY_CONFIG_FILE_DIR` environment variable to refer to paths relative to the config
file"*, and *"This option may only be set in the global section (`[mypy]`)."* The setting resolves
today because `check.sh` runs mypy from the repository root. On the pyright side, pyright reads
`pyrightconfig.json` or a `[tool.pyright]` table, and states that when either exists *"any pyright
settings in a VS Code settings.json will be ignored"*; basedpyright, which is what the editor lane
here actually launches, is a pyright fork with its own `[tool.basedpyright]` table. Which of those
files the running server reads has not been demonstrated in this repository.

- [x] `mypy_path = "$MYPY_CONFIG_FILE_DIR/scripts"`. Verified by running mypy on a module that imports
      `paths`, `install`, `launcher` and `baseline` from the repository root, from `tests/`, and from
      `scripts/baseline/`; all three resolve identically, and `bash scripts/check.sh` is green.
- [x] Precedence established by experiment on the real editor lane. The running server is pyright
      **1.1.414** at `~/.pi-lens/tools/node_modules/pyright/`, not basedpyright — neither `pyright` nor
      `basedpyright` is on `PATH`, so nothing outside that directory can be what launches. With both a
      `pyrightconfig.json` and a `[tool.pyright]` table present, an unresolvable import that the table
      resolves goes silent when the `pyrightconfig.json` is emptied to `{}`: the standalone file wins and
      the table is not consulted. The headless CLI at that same path needs
      `--pythonpath .venv/bin/python` to reproduce the server's answers, which is why a CLI run without
      it disagreed with the editor.
- [x] Single location chosen on that evidence: `pyrightconfig.json`. `[tool.pyright]` was removed from
      `pyproject.toml` so one file governs; `pyproject.toml` keeps only the mypy table.
- [x] `pythonVersion` pinned to `"3.12"`, the `requires-python` floor the CI matrix tests. Measured at
      that value with the project interpreter: 86 files, 0 errors, 0 warnings, 0 notes, and the venv's
      `site-packages` still resolve — an earlier unversioned run resolved them through auto-detected 3.14.

## 5. Scope container-only imports with execution environments

**Evidence:** the 12 unresolved-import errors name `torch`, `exllamav3`, `exllamav3_ext`,
`huggingface_hub`, `serve.server`, `common.config_models`, `common.sampling`, and
`exllamav3.conversion.convert_model`. Each is installed in the container image and not in the
workstation venv, so pyright cannot resolve them there: `common.*` is reached through
`sys.path.insert(0, "/opt/src/tabbyAPI")` inside `validate_sections`, and `serve.server` through the
image's own search path. mypy accepts them through per-module overrides on the imported name.
Pyright's equivalent is a path-scoped execution environment, which the documentation confirms accepts
diagnostic overrides. Its own guidance for unresolved imports orders the fixes: install the package,
select the correct
platform-specific imports — the comment is the last resort.

- [x] Three execution environments added: one rooted at `tests/` carrying `extraPaths` for the
      first-party modules, and one per container tree with `reportMissingImports: "none"` in that
      environment only.
- [x] Accepted trade-off recorded: a path-scoped severity override also hides unresolved first-party
      imports inside those trees. Each tree was judged by what it imports — the container trees import
      image packages and siblings, nothing that exists on the workstation — and no host path is covered.
- [x] Not narrowed further: the environment scope already excludes `scripts/`, `tests/` and the
      repository tooling, so no file-level or import-level pyright directive was needed. The only
      `# type: ignore` that conflicted with pyright was removed by annotating its value instead
      (item 6), so no directive is relied upon anywhere.
- [x] `reportMissingImports` stays on at the top level, and no heavy dependency was installed for editor
      analysis.
- [x] Re-measured with the headless CLI against the project interpreter: 86 files, 0 errors, 0 warnings.
      Only `reportMissingImports` fired before the change; `reportMissingModuleSource` never appeared, so
      none of these names has a stub in the venv.
- [x] Outside the container trees the import family is zero, and `tests/` first-party imports resolve
      through their own environment — verified by the same run reporting 0 errors over `tests/`.

## 6. Parity between the checkers on stale suppressions

**Evidence:** `warn_unused_ignores = true` makes an unused `# type: ignore` a CI failure, and
`docs/project-instructions.md` directs editor-only suppressions to `# pyright: ignore`. Pyright
honours `# type: ignore` by default — *"This switch enables or disables support for these comments.
The default value for this setting is `true`. This does not affect `# pyright: ignore` comments"* —
and its counterpart to `warn_unused_ignores` is `reportUnnecessaryTypeIgnoreComment`, documented as
*"diagnostics for a `# type: ignore` or `# pyright: ignore` comment that would have no effect if
removed"*, default `"none"`. Today the editor lane has no equivalent guard, so a suppression can go
stale in the exact place a developer reads it.

- [x] `reportUnnecessaryTypeIgnoreComment` set to `"error"` in `pyrightconfig.json`, the location item 4
      proved the lane reads.
- [x] The lane reports nothing at that level. Six `# type: ignore` comments existed; five remain, each one
      required by mypy and accepted by pyright. The sixth was a genuine disagreement:
      `tests/test_baseline_session.py:23` carried `# type: ignore[arg-type]` that mypy needed and pyright
      reported as unnecessary. The annotation, not the suppression, was wrong — the fixture value is a
      `dict[str, Any]` payload passed where the schema widens — so the value is annotated and the comment
      deleted. Both checkers are now silent on all five remaining sites.
- [x] No `# pyright: ignore` exists in the tree, so nothing depends on the setting staying quiet.

## 7. Disposition the mitigated tarfile extraction sites

**Evidence:** `runtimes/exllamav3-tabbyapi/container/fetch_sources.py:42` and
`runtimes/strata/container/fetch_sources.py:21` already pass `filter="data"`, the archive-traversal
mitigation available from Python 3.12, which `requires-python = ">=3.12"` guarantees. The audit rule
matches the call shape regardless of arguments.

- [x] Both sites carry the rule-id directive above the call, naming the rule and, on the exllama side,
      the `filter="data"` argument that mitigates it. The strata site additionally holds a `false-positive`
      disposition, because the `opengrep` lane applies inline directives unevenly there (measured, recorded
      in `docs/diagnostics-inventory.md`).
- [x] The rule stays enabled everywhere else: the carve is two named files, not the tree, so an
      `extractall` without `filter=` in new code is still reported. Measured: the family reports nothing
      outside the two dispositioned sites.

## 8. Set policy for the lexically blind throwing-call rule

**Evidence:** the bundled rule is `any(open, json.loads, json.load, os.stat, os.remove, os.rename,
os.mkdir, os.makedirs, os.rmdir, os.listdir, os.access, shutil.copy, shutil.move, shutil.rmtree)`
with one exclusion, `not: inside try_statement`; its fixtures treat a `try`-wrapped call as valid,
which is the full extent of its context awareness. Its counts also track argument shape rather than
raisability: the identical load is reported at `doctor.py:26` and missed at `serve.py:100`, where the
argument is parenthesised (item 2). This repository handles those exceptions one
level up, which is the documented contract: `scripts/install.py::main` catches `OSError` and exits
1 with `install: <error>`, `scripts/doctor.py::check_configuration` catches
`(OSError, ValueError, KeyError, TypeError, IndexError)` and returns a `FAIL` finding,
`scripts/launch.py:177` applies `int()` to a `bool`, which cannot raise, and
`scripts/baseline/sources.py:52` parses `int(parts[1])` behind a `parts[1].lstrip("-").isdigit()`
guard. The same rule family concedes the category upstream: `int()` and `float()` were separated
into `unchecked-numeric-parse-python` and shipped at `warning` because raisability is *"undecidable
from syntax alone"*. Neither mypy nor pyright contains an equivalent check, so no change to
`check.sh` or to pyright configuration can affect these findings.

- [x] Mechanism chosen: path scoping through the lane's project policy file. `.pi-lens.json` lists the
      eight runtime modules by name under `rules.unchecked-throwing-call-python.ignorePaths`; the second
      option (a shadowing rule at `warning`) was rejected as a maintained rule fork for a rule whose
      counts follow argument punctuation, and blanket per-site dispositions were rejected as machine-local
      and expiring. The one host-code site, `scripts/doctor.py`, keeps an inline
      `# ast-grep-ignore:` because the file's contract is that its callers report read failures.
- [x] Still active for first-party modules with no catching entry point: `scripts/` and `tests/` are not
      in the carve, and measurement found zero findings there after the `importer.py` fix — a new
      uncaught throwing call in host code reports immediately. Nothing was disabled repository-wide.
- [x] No `try` was added to satisfy the rule. The one `try` that appeared (`importer.py`, native settings
      read) exists because the error it raises did not name the file the operator has to fix; a test now
      asserts the path appears, and the finding cleared as a side effect.
- [x] No session-scoped deferral used: every disposition here is a file in git or a content-bound store
      entry, so the result survives the session.

## 9. Keep fixture literals out of the spell-check lane

**Evidence:** `tests/test_baseline_engine_log.py:218` holds a truncated `available` keyword as
verbatim engine log text that the parser under test consumes, and `tests/test_baseline_api.py:24`
streams a short token as generated text. Correcting either destroys the scenario being asserted.
The lane reads a `.typos.toml` / `typos.toml` configuration file.

- [x] Add `.typos.toml` with the fixture words under `[default.extend-words]` as identity mappings.
- [ ] Confirm the lane honours it. Measured: the two findings survive the file within one session.
      The lane is a per-session server and resolves its configuration once
      (`typos config resolved mode=project_config|injected_default`), which is the likely cause; the
      check needs a fresh session. If a fresh session still reports them, the lane is not reading
      project config and the disposition is the inline comment form instead.
- [ ] Do not edit the fixtures and do not exclude the test directory, which would stop checking real
      code in those files.
- [ ] Keep this plan and future ones free of the literal fixture strings, so the policy document does
      not itself report findings in the lane it governs.

## 10. Decide the advisory-runner and coverage-warning policy

**Evidence:** a full `severity=all` sweep reports no `jscpd`, `gitleaks`, `madge` or `dead-code`
findings; an earlier sweep reported an 11-line block shared by the two `container/fetch_sources.py`
files and a 7-line block between `scripts/baseline/importer.py:617` and `:693`. Whether a lane ran at
all shows only in its coverage footer, so a zero-finding lane counts as unconfirmed until it answers,
and the duplication claims are re-checked before any refactor. Three files sit in an inconclusive
language-server lane because no server covers them.

- [x] The duplicated block in `scripts/baseline/importer.py` is not reported by the duplication runner in
      any sweep of this session, so there is nothing to extract; the claim came from an earlier session's
      run. Re-checked before any refactor, as required: `jscpd` answers with zero findings.
- [x] The similar block in the two `container/fetch_sources.py` files stays, and `jscpd` does not report it
      either. The reason is recorded: project instructions make each container build context
      self-contained, so similar-looking code stays independent.
- [x] Per runner, in writing, in `docs/diagnostics-inventory.md`: keep `gitleaks` (a secrets scan over a
      measurements repository is cheap and it answers), keep `opengrep`, `ast-grep`, `typos`, `clangd` and
      the pyright lane with the dispositions recorded there, and keep the advisory runners that report
      nothing rather than turning them off — an empty result from a runner that answers is information.
      Nothing was switched off through `dispatch.disabledRunners`, which is a union across tiers and could
      never be lifted again from project configuration.
- [x] The inconclusive lane was resolved by observation, not by installing anything: `clangd` is already
      present and measures `check_hip.cpp`; the Docker language server answers for both Dockerfiles and
      finds nothing. No server was installed for this purpose, and `check_hip.cpp` is dispositioned by path
      rather than left unmeasured.
- [x] Sweeps were compared, and two behaviours are now treated as facts rather than flakiness: a cold lane
      reports less than a warm one (`ast-grep` gave nothing under `runtimes/` cold and 22 findings warm,
      same files), and a lane that times out repeatedly gets demoted for the rest of the session — its
      coverage footer then says the wait budget cannot override the demotion.

## 11. Record the analysis policy in project instructions

**Evidence:** `docs/project-instructions.md` defines the mypy contract, states that the pyright
configuration is editor-side only, and notes that unresolvable imports are advisory. It does not
record where the editor lane's rule policy lives, which findings were dispositioned and why, that a
finding can be triaged rather than fixed, or which config file the editor checker reads.

- [x] Each checker's file and scoping axis stated in `docs/project-instructions.md`: mypy by imported
      module name, Pyright by path through `pyrightconfig.json`, which is the only file it reads here. The
      same text states that `scripts/check.sh` remains the only gate that fails a build.
- [x] The suppression contract is stated there: a suppression names the rule and the reason, sits at the
      narrowest scope that keeps the rest of the file checked, and is reviewed in the diff; rule
      configuration is for scope, never for concealing a defect.
- [x] Enforcement stays out of the editor lane, with the reason recorded: a scanner that runs only on
      developer workstations cannot gate anything, and a lane that does not answer reports no findings
      rather than a clean result.

## Delivery and validation

Land one item per commit. After each commit, re-measure per item 1 and record the per-rule counts
next to the item, requiring the targeted family to fall by the expected amount while unrelated
families hold steady — a total that drops for the wrong reason is a regression. Every commit
touching Python keeps `bash scripts/check.sh` green, including the generation-freshness checks, and
CI on `main` stays green.

Item 3 is test-first and must not change any recorded measurement or serving default. Items 4–10
change no production behaviour; if one does, that is a defect in the change. Items 4 and 5 depend on
measurements, not assumptions: the config file each checker reads and the rule that fires after
scoping are both recorded from observation. Before item 11, read the accumulated diff for any
suppression without a stated reason, since an unexplained suppression is indistinguishable from a
hidden defect.
