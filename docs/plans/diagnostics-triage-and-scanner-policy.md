# Plan: validate diagnostics policy on the Pi workstation

## Goal and current state

Make the tracked scanner policy understandable and reproducible while retaining useful
coverage. The [diagnostics inventory](../diagnostics-inventory.md) holds the evidence,
rule-level verdicts, limitations, and corrections. Use it as the handoff reference.

- [x] Validate landed production fixes and the repository checks at `ea37cf7`.
- [x] Independently reproduce Pyright 1.1.414: 86 files, zero diagnostics with the configured exceptions.
- [x] Separate verified code behavior from reported workstation observations.
- [x] Probe Pyright exception boundaries in a disposable checkout, including an unsuppressed
      control and unrelated type errors; see the inventory’s verified boundary table.
- [x] Validate both source extractors with CPU-only archive tests: checksum rejection,
      traversal, escaping links, and cleanup without publishing rejected sources.
- [ ] Confirm the actual Pi scanner processes, configurations, and local dispositions.
- [ ] Verify tracked policy independently of machine-local dispositions.
- [ ] Resolve unnecessarily broad or ineffective suppressions.
- [ ] Record a concise current-state result in the inventory and project instructions.

No checker migration is planned. mypy owns strict CI validation; Pyright supplies editor
feedback. The task is to align configuration and evidence, not force identical answers from
both tools. No GPU access is needed for the host investigation; a HIP build is separate validation.

## 1. Establish the machine and checkout

Before changing configuration:

- Record the repository commit, branch, and dirty status. Preserve local edits.
- Identify whether this is the original Pi workstation or a fresh-machine reproduction.
  A different machine cannot validate an unavailable original disposition store.
- Record Pi and pi-lens versions, actual scanner executable paths and versions, the Python
  interpreter, and which repository configuration each process loads. Inspect process or
  startup information; `PATH` alone is not evidence of the launched executable.
- Locate the effective pi-lens configuration layers and disposition store. Record the
  relevant rule IDs, scope, and whether entries are machine-local. Do not copy the entire
  user configuration, private paths, or unrelated diagnostic content into Git.

Relevant tracked files: `pyproject.toml`, `pyrightconfig.json`, `.pi-lens.json`, `.typos.toml`,
and `runtimes/strata/container/.clangd`. The inventory identifies current exceptions.

## 2. Measure coverage and enforcement

Use a fresh Pi session and the installed scanner's supported interface. The reported starting
query is `lens_diagnostics(source=lsp, mode=full, scope=workspace, severity=all,
waitMs=10000)`. Confirm those parameters against the available tool version.

- Capture per-rule findings and per-lane coverage, including timeouts, unavailable servers,
  and demotion notices. Save raw output locally for comparison; summarize the relevant results
  in the inventory. Record the commit, tool versions, and query with the summary.
- Repeat once after initialization to investigate reported cold/warm differences. Do not
  repeat indefinitely until a favorable total appears; unanswered lanes remain unconfirmed.
- Separate findings suppressed by tracked policy from findings cleared by stored dispositions.
  If supported, use an isolated session/configuration to test without the store. Preserve the
  user's active store. Otherwise state that fresh-clone enforcement remains unverified.
- Check `.typos.toml` and `.clangd` after a fresh server start. A missing finding counts only
  when the responsible lane confirms coverage.
- Recover the exact opengrep path-traversal and deserialization findings, including file,
  rule ID and message. Compare the cited operation with its actual input trust boundary.

Do not compare the reported 18-, 99-, and 115-finding totals as if they share the same coverage.
Use matching rule IDs and scanned paths. Differences in Python environments also affect import results.

## 3. Resolve policy gaps from evidence

### Typing

Keep the verified config-relative mypy search path and Python 3.12 target. Confirm the editor
uses `pyrightconfig.json` and the project interpreter. Review unused-ignore disagreements
individually; “unused in Pyright” does not imply “unused in mypy”.

The disposable-checkout probe confirms that the three missing-import exceptions hide both
external and first-party import errors recursively within their roots, while unrelated type
errors remain visible. The inventory records the tested boundaries and control. Narrow them if the local tooling supports a practical, maintainable
alternative; do not install the GPU stack solely to satisfy the host editor.

### Rule dispositions

- Verify exact opengrep IDs and the documented suppression mechanism for the installed version.
  The existing Strata `.pi-lens.json` entries are reported ineffective. Remove redundant entries
  only after establishing which tracked mechanism works, or retain an explicit unresolved finding.
- Confirm the doctor suppression against caller-level error handling. Keep the runtime
  throwing-call exceptions limited to reviewed files and acknowledge their future coverage gap.
- Narrow clangd exceptions to the HIP probe where practical. Ensure a machine with a configured
  HIP toolchain can receive ordinary missing-header/type/identifier diagnostics.
- Confirm the fixture spelling exceptions without editing fixture data or excluding all tests.
- Retain numeric-parse warnings as advisory. Reason from input contracts and callers rather
  than treating `isdigit()`, record-prefix checks, or `max()` as universal parsing guarantees.

For an enforcement probe, use a disposable fixture or checkout with a known finding and its
intended suppression. Verify both that the intended finding clears and that an unrelated
finding still reports. Do not add intentionally broken probe code to the main checkout.

### Downloads and extraction

Keep the confirmed SHA-256 checks and `filter="data"`. Shared regression coverage lives in
`tests/test_source_extraction.py`; the repository checks pass with 836 tests. ShellCheck was
unavailable for this validation. Scanner suppression enforcement still needs the Pi checks above.
The inventory's distinction between
initial URLs, redirects, byte limits, and integrity is the review baseline. Decide separately
whether source-archive byte limits or redirect restrictions have a concrete benefit; neither
is an automatic requirement of an audit warning. Preserve legitimate Hugging Face redirects.

## 4. Finish and validate

- Update the inventory with confirmed, unresolved, and accepted-trade-off states. Remove
  unsupported clean-state claims and obsolete counts; keep one current measurement summary.
- Keep durable operating policy in `docs/project-instructions.md` and investigation detail in
  the inventory. Avoid duplicating rule-by-rule explanations in both files.
- For Python/configuration changes, run `bash scripts/check.sh`. Re-run the affected scanner
  with its identified executable, version, interpreter, and configuration.
- For documentation-only changes, check links, referenced symbols, and consistency with the
  tracked configuration. Do not claim a scanner rerun when only prose changed.

Completion means another developer can distinguish tracked behavior from workstation-local
state, and each exception has a verified mechanism or an explicit unresolved status. Zero
warnings is not the acceptance criterion.
