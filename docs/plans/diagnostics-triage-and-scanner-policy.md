# Plan: portable diagnostics policy

## Current state

The repository's diagnostic contract is reproducible from a fresh clone using only the checkers
the repository defines:

- `bash scripts/check.sh` gates Ruff lint and formatting, the `typos` spell checker, mypy for the
  default target and the separate `runtimes/strata` invocation, CPU-only pytest, the
  generated-document check, and ShellCheck when installed.
- `pyrightconfig.json` governs editor analysis: Python 3.14 target, `scripts` and test search
  paths. Import statements naming image-only packages carry a
  `# pyright: ignore[reportMissingImports]` directive. Pyright resolves this file from the project
  root in any editor, with or without an assistant harness.
- `.typos.toml` and `runtimes/strata/container/.clangd` are tool-native configuration for the
  `typos` CLI and clangd, portable to any machine that runs those tools.

Established properties:

- `pyright --project pyrightconfig.json --pythonpath .venv/bin/python` reports no diagnostics for
  the tracked Python files. The interpreter selection belongs to the measurement: the same run
  without a working interpreter reports missing imports for the development dependencies. mypy is
  the strict gate and covers the same files under a different type model. Both report unused
  suppressions and can disagree about which ones are needed.
- Missing-import exemptions sit on individual import statements, so a misspelled first-party import
  beside one is reported, and `reportUnnecessaryTypeIgnoreComment` set to `error` makes an exemption
  whose import has become resolvable a failure. Unrelated type errors stay visible everywhere.
- The repository carries no scanner-harness configuration file, and no repository gate depends on
  one. A tracked exception belongs to a checker that some documented workflow actually runs;
  configuration for a checker nobody runs is decoration rather than policy.
- ROCm and the HIP headers exist only inside the Strata image, so a host clangd has no HIP headers
  in its search path. Missing-header diagnostics and the symbol errors that follow from them in the
  probe are that gap in the editor's view, not a defect in the probe.
- Tracked sources carry no scanner-rule directive. The download, extraction, and probe sites state
  their invariants in ordinary comments and rest on portable guarantees: SHA-256 verification with
  `filter="data"` under CPU-only tests for the downloaders, finding propagation under tests for
  `doctor.read_json`, and the image build that compiles and runs the HIP probe.

No checker migration is planned. The aim is aligned configuration and evidence, not identical
answers from both Python type checkers.

## Remaining work

- [ ] Review the unused-ignore disagreements between mypy and Pyright one by one.
- [ ] Confirm the editor loads `pyrightconfig.json` with the project interpreter.
- [ ] Record HIP toolchain validation for the probe as container output, then narrow `.clangd`.
- [ ] Decide whether archive streaming needs a byte limit or redirect restriction, based on an
      explicit threat rather than a scanner message.
- [ ] Keep durable policy in `docs/project-instructions.md` and detail in the
      [diagnostics inventory](../diagnostics-inventory.md), without duplicating rule-by-rule
      explanations across the two.

## 1. The tracked contract

`pyproject.toml` defines the mypy targets and the image-only exemptions; the config-relative
`mypy_path` pointing at `scripts` keeps a single-file mypy invocation able to resolve first-party
modules, while runtime directories stay off the search path because each is checked in its own
invocation. Keep the Python 3.14 target. Prefer a checker-specific suppression where only one
checker needs it, naming the rule and the reason.

A missing-import exemption belongs on the import statement that names a module available only
inside a container image: Pyright scopes a rule by line, file, or directory prefix and has no
per-module form, so the statement-level directive is the narrowest one it supports, while the mypy
overrides in `pyproject.toml` name the exempted modules because mypy is the gate. A directory-level
exception would hide first-party import errors throughout the subtree, and installing the GPU stack
to satisfy a host editor is not an option.

Directives that only a specific harness reads are outside the contract, and tracked sources carry
none. Where one is proposed and appears to have no effect, compare its rule id with the id the
scanner reports before crediting or widening it; a mismatched id suppresses nothing.

## 2. Workstation observations

Analysis tooling that exists only on one workstation - an assistant harness, the scanner
executables it bundles, and their disposition stores - produces observations and nothing else.

- Record a measurement with the commit, the executable and version, the interpreter, the query or
  command, and its coverage limits. Keep raw output outside the repository.
- Report coverage beside counts: files scanned, lanes that answered, timeouts, unavailable
  servers, demotion notices. An unanswered lane leaves its files unconfirmed. Match rule ids and
  scanned paths when comparing two runs, since lane coverage and the Python environment both move
  the totals; files and lanes are different units and cannot be summed.
- Auxiliary lanes can replay cached results while reporting a live timeout, so take freshness from
  cache timestamps rather than from a reported total. Configuration read only at startup needs a
  server restart to take effect.
- Machine-local dispositions do not travel with a clone, so a fresh checkout shows those findings
  again. That is the expected state. Never edit tracked sources or configuration to make such a
  finding disappear, and never delete or rewrite a local store to obtain a convenient baseline.
- Probe suppression behavior in a disposable copy of the checkout, pairing a known finding with
  its intended suppression, and confirm that the intended finding clears while an unrelated finding
  still reports. Keep probe code, probe configuration, and editor-only settings out of the main
  checkout.

## 3. Extraction and downloads

Keep the SHA-256 checks and `filter="data"`; the shared regression coverage lives in
`tests/test_source_extraction.py`. The initial authority in every downloader is a literal
constant, lock values supply only path components, Python's default opener follows redirects, and
the archive streams in `container/fetch_sources.py` have no byte cap. A size limit or redirect
restriction needs a concrete threat and must keep legitimate Hugging Face redirects working;
neither follows automatically from an audit warning.

## 4. HIP probe

Validate inside the image, where the toolchain exists:

- build the image, which compiles `check_hip.cpp` with `hipcc --offload-arch=gfx1201`;
- run the resulting `check_hip` with `/dev/kfd` and `/dev/dri` passed through, and keep its JSON
  line as evidence of a working build on the device;
- run `clangd --check` on the probe inside the container, once with the tracked `.clangd` and once
  with its `Suppress:` list removed in a disposable copy, and compare the diagnostics.

Then narrow `Suppress:` toward the probe file where practical, so a machine with a configured HIP
toolchain still receives ordinary missing-header, type, and identifier diagnostics elsewhere in the
directory. Only the container run is a build result; a suppressed editor result is not.

## 5. Definition of done

A fresh clone on a machine without the workstation's assistant tooling reproduces the same gate
results. Every tracked exception maps to a checker that a documented workflow runs. Each remaining
finding is either resolved by a portable check or recorded in the inventory as an advisory rule
family with its limits, marked confirmed, unresolved, or an accepted trade-off, with one current
measurement summary rather than several totals from different coverage. Zero warnings is not the
acceptance criterion.
