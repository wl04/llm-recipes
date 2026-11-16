# Plan: diagnostics triage and static analysis policy

Review date: 2026-11-16. Code reviewed: `950d2fd`. Checkers: mypy `2.4.1` in
`scripts/check.sh`; basedpyright over LSP through pi-lens 4.5.1.

## Completion status

- [ ] 1. Reproducible baseline separated by producing checker
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

The editor counter and a full sweep measure different populations. A full workspace sweep with
`severity=all` reports `52 blocking errors, 87 warnings, 4 hint/info` across 51 diagnosed files;
the status line shows the session subset (`25E 58W`). That sweep also states
`ast-grep did not answer for 64 file(s)` and leaves three files unconfirmed
(`runtimes/exllamav3-tabbyapi/container/Dockerfile`, `runtimes/strata/container/Dockerfile`,
`runtimes/strata/container/check_hip.cpp`), so neither total is a queue of defects.

What matters first is which tool produced each finding, because the fix belongs to that tool:

| Producer | Findings in scope | Owner of the fix |
| --- | --- | --- |
| mypy (`check.sh`) | none outstanding | already the build gate |
| `Pyright:reportMissingImports` — `torch` ×3, `huggingface_hub`, `exllamav3`, `serve.server` | ~6 | pyright config, by path scope |
| `ast-grep:unchecked-throwing-call-python` — `install.py:119,176,214`, `doctor.py` ×3, `scripts/serve.py` ×8 | ~14 | no mypy or pyright equivalent exists |
| `opengrep` audits — `dynamic-urllib-use-detected` ×3, `tarfile-extractall-traversal` ×2 | 5 | code, then per-line rule disposition |
| `python-path-traversal`, `jscpd`, `typos`, `dead-code`, `madge` | remainder | per lane, see items 9–10 |

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

**Evidence:** the two counts above differ by scope and by scanner coverage, so no later item can
demonstrate an effect without a fixed procedure.

- [ ] Record the exact procedure: `lens_diagnostics` with `source=lsp`, `mode=full`,
      `severity=all` over the workspace, repeated until `Auxiliary coverage incomplete` names no
      scanner lane.
- [ ] Tabulate per producing checker and per rule id, not a raw total. Family counts stay
      meaningful when coverage changes; totals do not.
- [ ] Confirm no prior triage exists in the baseline: `~/.pi-lens/dispositions.log` holds no
      entries, so every finding below is unjudged.

## 2. Classify the unclassified blocking findings

**Evidence:** `runtimes/exllamav3-tabbyapi/scripts/serve.py` carries 8 blocking findings and
`runtimes/strata/container/Dockerfile` carries 1; no source was read for either. `python-path-traversal`
fires at five sites, one of which the sweep extract did not attribute to a file, while report
import already rejects absolute and parent-traversing recipe identifiers.

- [ ] Read each `serve.py` blocking site and record whether it is a real defect, a call handled by
      its caller, or a rule misfire. A serving entry point validates per request, which no lexical
      rule can see.
- [ ] Read the strata `Dockerfile` finding and `check_hip.cpp`, where no language server confirmed
      the file; fix it or record why the missing server is acceptable.
- [ ] For every `python-path-traversal` site, compare against the containment checks that exist and
      either close a gap or record the existing guard as the reason.
- [ ] Write the one-line verdict per site here before any disposition in items 7–10.

## 3. Constrain outbound model and source fetches

**Evidence:** `runtimes/exllamav3-tabbyapi/container/fetch_sources.py:32` and
`runtimes/strata/container/fetch_sources.py:34` call `urllib.request.urlopen(url, timeout=120)`;
`runtimes/strata/scripts/prepare_models.py:47` calls `urlopen(request, timeout=120)`. The URL is
composed from `versions.lock.json`, and `urllib` accepts `file://` and plain `http://`, so a
modified or mirror-substituted lock can move a build to an arbitrary scheme or host. opengrep
reports these as `dynamic-urllib-use-detected` (CWE-939).

- [ ] Write failing tests first, CPU-only with a patched opener as `tests/test_strata_preparation.py`
      does: `file://`, `http://`, and a host outside the expected domain are rejected with a message
      naming the lock field, and an expected `https://` host still fetches.
- [ ] Accept `https://` only, with the host drawn from the lock's own host field or a literal
      allowlist in the recipe; reject userinfo, ports other than 443, and every other scheme, before
      a byte is transferred.
- [ ] Keep the validation inside each runtime: a container build context cannot import repository
      modules, so no shared helper and no new third-party HTTP dependency.
- [ ] Re-run the lane. The audit rule keys on a dynamic argument rather than on validation, so the
      three findings are expected to survive; disposition them in the commit that adds the
      validation, with the reason naming the scheme and host check.

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

- [ ] Set the search path config-relative:
      `mypy_path = "$MYPY_CONFIG_FILE_DIR/scripts"`. Verify by running mypy from a subdirectory on a
      test module that imports `paths`, `install`, `launcher`, and `baseline`, and confirm it
      resolves the same way as from the root. Keep `bash scripts/check.sh` green.
- [ ] Establish, by experiment in a scratch directory outside the repository, which config file the
      editor checker honours: `pyrightconfig.json`, `[tool.pyright]`, or `[tool.basedpyright]`. Drive
      it with an unresolvable import plus a severity override in one candidate file at a time, and
      record the observed result here.
- [ ] Choose the single location for pyright configuration on that evidence and state it in item 11.
      One file, read by the checker that runs here; do not maintain both.
- [ ] Record the interpreter-version constraint with a measurement rather than a claim: state which
      `pythonVersion` the project intends and confirm that the venv's `site-packages` still resolve
      at that value, since a pinned floor release and a newer workstation venv interact.

## 5. Scope container-only imports with execution environments

**Evidence:** `torch`, `huggingface_hub`, `exllamav3`, and `serve.server` are installed in the
container image and not in the workstation venv, so pyright cannot resolve them there; mypy accepts
them through per-module overrides on the imported name. Pyright's equivalent is a path-scoped
execution environment, which the documentation confirms accepts diagnostic overrides. Its own
guidance for unresolved imports orders the fixes: install the package, select the correct
environment, and use a `# pyright: ignore[reportMissingImports]` comment for optional or
platform-specific imports — the comment is the last resort.

- [ ] Add an execution environment per container tree, with `extraPaths` mirroring the `sys.path`
      insert the code performs at runtime, and `reportMissingImports` scoped to `"none"` there only.
- [ ] State the accepted trade-off here: a path-scoped severity override also hides unresolved
      first-party imports inside those trees, which is wider than mypy's per-module exemption. Judge
      each tree by what it actually imports — the container trees import siblings and image
      packages, nothing else.
- [ ] Where that breadth is unacceptable, narrow it instead of widening it: set the rule per file
      with a file-level pyright directive in the affected module, or per import with
      `# pyright: ignore[reportMissingImports]`. Verify the file-level form against the running
      server before relying on it.
- [ ] Never set `reportMissingImports` off at the top level, and do not install torch or
      huggingface_hub to satisfy editor analysis: a multi-gigabyte dependency in the 3.12/3.14 CI
      matrix buys nothing, since CI never imports them.
- [ ] Confirm after the change which rule actually fires in those files, and distinguish
      `reportMissingImports` (no source and no stub) from `reportMissingModuleSource` (stub found,
      source missing) rather than assuming.
- [ ] Re-measure per item 1: the import family should reach zero outside the container trees, with
      `tests/` first-party imports still resolving through their execution environment.

## 6. Parity between the checkers on stale suppressions

**Evidence:** `warn_unused_ignores = true` makes an unused `# type: ignore` a CI failure, and
`docs/project-instructions.md` directs editor-only suppressions to `# pyright: ignore`. Pyright
honours `# type: ignore` by default — *"This switch enables or disables support for these comments.
The default value for this setting is `true`. This does not affect `# pyright: ignore` comments"* —
and its counterpart to `warn_unused_ignores` is `reportUnnecessaryTypeIgnoreComment`, documented as
*"diagnostics for a `# type: ignore` or `# pyright: ignore` comment that would have no effect if
removed"*, default `"none"`. Today the editor lane has no equivalent guard, so a suppression can go
stale in the exact place a developer reads it.

- [ ] Set `reportUnnecessaryTypeIgnoreComment` to `"error"` in the location chosen by item 4.
- [ ] Run the lane and triage every report it produces. The test suite carries `# type: ignore[arg-type]`
      comments that mypy requires; if pyright considers any of them unnecessary, resolve each one
      individually — correct the annotation, or record why the two checkers legitimately disagree.
- [ ] Confirm the setting does not silence a needed suppression: a real `# pyright: ignore` added in
      items 5 and 7 must stay silent.

## 7. Disposition the mitigated tarfile extraction sites

**Evidence:** `runtimes/exllamav3-tabbyapi/container/fetch_sources.py:42` and
`runtimes/strata/container/fetch_sources.py:21` already pass `filter="data"`, the archive-traversal
mitigation available from Python 3.12, which `requires-python = ">=3.12"` guarantees. The audit rule
matches the call shape regardless of arguments.

- [ ] Put a rule-id suppression comment above each call so the judgement is in the diff and visible
      in review, naming the rule and the `filter="data"` argument that mitigates it.
- [ ] Keep the rule active everywhere else, so extraction added anywhere new is still reported.

## 8. Set policy for the lexically blind throwing-call rule

**Evidence:** the bundled rule is `any(open, json.loads, json.load, os.stat, os.remove, os.rename,
os.mkdir, os.makedirs, os.rmdir, os.listdir, os.access, shutil.copy, shutil.move, shutil.rmtree)`
with one exclusion, `not: inside try_statement`; its fixtures treat a `try`-wrapped call as valid,
which is the full extent of its context awareness. This repository handles those exceptions one
level up, which is the documented contract: `scripts/install.py::main` catches `OSError` and exits
1 with `install: <error>`, `scripts/doctor.py::check_configuration` catches
`(OSError, ValueError, KeyError, TypeError, IndexError)` and returns a `FAIL` finding,
`scripts/launch.py:177` applies `int()` to a `bool`, which cannot raise, and
`scripts/baseline/sources.py:52` parses `int(parts[1])` behind a `parts[1].lstrip("-").isdigit()`
guard. The same rule family concedes the category upstream: `int()` and `float()` were separated
into `unchecked-numeric-parse-python` and shipped at `warning` because raisability is *"undecidable
from syntax alone"*. Neither mypy nor pyright contains an equivalent check, so no change to
`check.sh` or to pyright configuration can affect these findings.

- [ ] Decide the mechanism and record it here, in order of preference: path scoping through the
      lane's own project policy file, limited to the entry points whose contract is caller-level
      handling; a project rule that shadows the bundled rule id at `warning`, following the
      numeric-parse precedent, which keeps the signal for new code and costs a maintained rule fork;
      or per-site dispositions, which are machine-local and expire when the flagged line changes.
- [ ] Keep the rule active for first-party modules that have no catching entry point; a
      repository-wide disable is not acceptable.
- [ ] Add no `try` blocks purely to satisfy this rule at the sites above. It would duplicate handling
      that `main` and `check_configuration` already perform, against the boundary-handling rules in
      `AGENTS.md`.
- [ ] A session-scoped deferral is not an end state: the findings return on the next session.

## 9. Keep fixture literals out of the spell-check lane

**Evidence:** `tests/test_baseline_engine_log.py:218` holds a truncated `available` keyword as
verbatim engine log text that the parser under test consumes, and `tests/test_baseline_api.py:24`
streams a short token as generated text. Correcting either destroys the scenario being asserted.
The lane reads a `.typos.toml` / `typos.toml` configuration file.

- [ ] Add `.typos.toml` with the fixture words under `[default.extend-words]`, each entry naming the
      fixture it belongs to, and confirm by re-running the lane that the configuration is honoured.
- [ ] Do not edit the fixtures and do not exclude the test directory, which would stop checking real
      code in those files.
- [ ] Keep this plan and future ones free of the literal fixture strings, so the policy document does
      not itself report findings in the lane it governs.

## 10. Decide the advisory-runner and coverage-warning policy

**Evidence:** `jscpd` reports an 11-line block shared by the two `container/fetch_sources.py` files
and a 7-line block between `scripts/baseline/importer.py:617` and `:693`. `gitleaks`, `dead-code`,
`madge`, and `jscpd` run every sweep, the last clean sweep fetching `gitleaks (421ms)`,
`opengrep (2068ms)`, `jscpd (49ms)`. Three files sit in an inconclusive language-server lane
because no server covers them.

- [ ] Extract the duplicated 7 lines in `scripts/baseline/importer.py` into one helper, relying on
      the existing coverage around both call sites. This is first-party code and a real duplication
      case.
- [ ] Keep the duplicated block in the two `container/fetch_sources.py` files: project instructions
      make each container build context self-contained, so similar-looking code stays independent.
      Record that reason as the disposition.
- [ ] Decide per runner, in writing: keep it and disposition its output, or turn it off through the
      lane's documented runner policy key. Judge by whether the runner has ever produced an
      actionable finding here; a secrets scan over a measurements repository is cheap and worth
      keeping.
- [ ] For the inconclusive lane, either supply the server (Docker analysis for the Dockerfiles,
      `clangd` for `check_hip.cpp`) or disable those servers for the project so the sweep stops
      reporting an inconclusive result. An inconclusive lane is not a clean verdict, so leaving it
      requires saying so here.
- [ ] Run the sweep twice and compare the coverage footer; a lane that times out consistently is a
      configuration fact, not flakiness.

## 11. Record the analysis policy in project instructions

**Evidence:** `docs/project-instructions.md` defines the mypy contract, states that the pyright
configuration is editor-side only, and notes that unresolvable imports are advisory. It does not
record where the editor lane's rule policy lives, which findings were dispositioned and why, that a
finding can be triaged rather than fixed, or which config file the editor checker reads.

- [ ] Name the single configuration file for each checker and the axis it scopes by: mypy by imported
      module name, pyright by path. State that `scripts/check.sh` remains the only gate that fails a
      build.
- [ ] State the suppression contract for both checkers: a suppression names the rule or diagnostic
      and the reason, sits at the narrowest scope that keeps the rest of the file checked, and is
      reviewed in the diff. Rule configuration is for scope, never for concealing a defect.
- [ ] Keep enforcement out of the editor lane: any check that must fail the build belongs in
      `check.sh`, because a scanner that runs only on developer workstations cannot gate anything.

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
