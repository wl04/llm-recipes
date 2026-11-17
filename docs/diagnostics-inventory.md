# Diagnostics inventory

Review baseline: `ea37cf7`, checked on 2026-11-17. This document separates independently
verified behavior from observations that require the Pi workstation. The
[validation plan](plans/diagnostics-triage-and-scanner-policy.md) describes how to resume.

## Verified in the cloud checkout

- `bash scripts/check.sh`: 828 tests passed, Ruff lint/format, both mypy targets, and
  generated-document checks passed. ShellCheck was unavailable and skipped.
- Pyright 1.1.414 with the repository configuration and `.venv/bin/python`: 86 files,
  zero errors, warnings, or information diagnostics. This is the configured result,
  including its suppressions; it does not establish coverage equivalent to strict mypy.
- The landed fixes validate non-object `VERSION` data, report invalid recipe launch
  settings through argparse, and include the native settings path in importer errors.
  Their regression tests pass.
- Official Pyright configuration supports diagnostic overrides in execution environments
  and gives `pyrightconfig.json` precedence over `[tool.pyright]`.
- The upstream tar extraction rule excludes the `members=` idiom but does not recognize
  `filter="data"`. Both repository source extractors use that filter after hash verification.

The Pi/pi-lens installation and its disposition store were not available for this validation.
No claim below about their enforcement is independently confirmed by the cloud checks.

## Reported workstation observations

The investigation identifies pi-lens 4.5.1 and an editor server at
`~/.pi-lens/tools/node_modules/pyright/`, reported as Pyright 1.1.414. Confirm the actual
process executable, version, interpreter, and configuration when connecting to that machine.
The absence of a command on `PATH` does not establish which server an editor launches.

The reported full sweep used `lens_diagnostics`, `source=lsp`, `mode=full`,
`scope=workspace`, `severity=all`, `waitMs=10000`. It describes 86 scanned files,
25 with findings, 52 confirmed clean, and nine non-answering lanes. Files and lanes are
different units; those figures must not be added together as a coverage calculation.

| Producer / rule family | Reported findings | Status of interpretation |
| --- | ---: | --- |
| Pyright `reportMissingImports` | 12 | Image dependencies; configured Pyright is independently clean |
| opengrep `tarfile-extractall-traversal` | 2 | Traversal guard confirmed; suppression enforcement needs verification |
| ast-grep `unchecked-throwing-call-python` | 27 | Lexical findings; assess exception propagation at the boundary |
| opengrep `dynamic-urllib-use-detected` | 3 | Audit findings; distinguish URL construction, redirects, and integrity |
| ast-grep `unchecked-numeric-parse-python` | 48 | Reported at 45 distinct sites; input contracts need site-level reasoning |
| ast-grep `no-ellipsis-body` | 4 | Valid `ServerControl(Protocol)` method stubs |
| ast-grep `no-yield-from-non-iterable` | 1 | `rows()` returns an annotated generator |
| typos | 2 | Intentional fixture payloads |
| clangd missing-header and dependent-symbol diagnostics | 15 | HIP headers unavailable on the reported workstation |
| ast-grep `cpp-no-printf` | 1 | Valid formatting in the HIP smoke check |

These rows total 115 findings. The reported 99-finding sweep omits the 16 C++ findings;
the 18-finding error-only sweep has different coverage. They are separate observations,
not interchangeable before/after measurements. Raw scanner output is not attached here.

The workstation investigation reports that cold and warm sweeps differed, some lanes timed
out or were demoted, and some configuration changes required a server restart. These are
observations to reproduce, not guarantees about all scanners. An unanswered lane is unconfirmed.

## Findings and current policy

### Python imports and typing

[pyrightconfig.json](../pyrightconfig.json) targets Python 3.12, adds `scripts` to search
paths, and gives tests their own search paths. It suppresses missing imports in three roots:

- `runtimes/exllamav3-tabbyapi/container`
- `runtimes/exllamav3-tabbyapi/scripts`
- `runtimes/strata/container`

Image-only packages include Torch, ExLlamaV3, TabbyAPI's `common` modules, and Strata's
server dependencies. Installing these into the host venv solely for editor analysis is
unnecessary. The path exceptions also hide missing first-party imports within those roots;
they are a coverage trade-off, not proof that every import there is correct.

mypy remains the strict CI checker. Pyright provides editor feedback. Both check unused
suppressions, but their answers can differ: a suppression needed by one can be redundant
for the other. Review disagreements rather than enforcing diagnostic parity. Typed stubs
can describe real interfaces; they are not inherently `Any` placeholders.

### Verified Pyright exception boundaries

Probe baseline: `e7fc9c4`, 2026-11-17, Pyright 1.1.414 and the repository venv.
A disposable copy of tracked files was checked from outside its root with explicit
`--project <copy>/pyrightconfig.json --pythonpath <repository>/.venv/bin/python`.
The unmodified copy reported 86 files and zero diagnostics.

Each location below received a probe with two unresolved imports (a nonexistent external
package and a misspelled first-party helper) and `value: str = 123`. A correctly named
helper was present beside each probe. Counts are per probe file.

| Location | Missing-import diagnostics | Assignment-type diagnostics |
| --- | ---: | ---: |
| Repository root | 2 | 1 |
| `scripts/` | 2 | 1 |
| `tests/` | 2 | 1 |
| `runtimes/strata/scripts/` | 2 | 1 |
| `runtimes/exllamav3-tabbyapi/container/` | 0 | 1 |
| `runtimes/exllamav3-tabbyapi/scripts/` | 0 | 1 |
| `runtimes/strata/container/` | 0 | 1 |
| Nested directory inside `runtimes/strata/container/` | 0 | 1 |
| Sibling `runtimes/strata/container_extra_probe/` | 2 | 1 |

Control: removing only the three environment-level `reportMissingImports` overrides
restored both import diagnostics in all nine locations; every assignment error remained.
This confirms recursive, directory-bounded suppression rather than skipped analysis.
It also confirms that first-party typos are hidden alongside missing image packages.
The probe files and modified configuration were confined to the disposable copy.

To repeat, use the same two imports and assignment at each location, run the explicit
project/interpreter command, then remove only the overrides in the copy and compare
`reportMissingImports` and `reportAssignmentType` per file. Verify the clean baseline first:
if the checker cannot query the selected interpreter, missing host dependencies invalidate
the comparison. This checks Pyright configuration, not Pi's choice of server or interpreter.

### Exceptions and numeric conversions

`doctor.read_json` propagates failures to callers that turn them into diagnostic findings.
Installer filesystem operations propagate to `install.main`, which catches
`OSError`, `RuntimeError`, and `subprocess.SubprocessError`. There is no `install_and_run`
wrapper in this checkout or the originally cited review commit.

The ExLlama `launch_runtime()` helper translates invalid launch settings into an argparse
error. It changes error behavior deliberately. The serving file has no `adapter-registry.json`
read or `_load_json` helper; those are not evidence for this rule's behavior.

Do not add local handlers merely because a lexical scanner flags a throwing call. Check the
callers and the intended boundary first. The doctor's inline rule suppression and eight
runtime file exceptions in [.pi-lens.json](../.pi-lens.json) are the current policy.
File-wide exceptions also hide future findings within those files.

The numeric-parse warnings remain enabled. Some conversions are intrinsically safe, such as
`int(bool_value)`; others depend on trusted OS output, validated inputs, or caller handling.
`startswith("MemTotal:")` identifies a record but does not validate its number. `isdigit()`
is not a general proof that `int()` succeeds: both `"²".isdigit()` and
`"--1".lstrip("-").isdigit()` are true, while conversion raises. `max(value, 1)` is not a
finite-number validator. These examples correct the reasoning; they do not establish a
reachable failure with normal kernel data. Do not classify all 48 findings as infallible.

### Source extraction and network downloads

Both source downloaders verify SHA-256 before extracting with `filter="data"`. That supports
dismissing the reported tar traversal pattern, while retaining the rule for unguarded sites.
The filter is not a general resource-exhaustion defense.

The initial source URLs use literal `https://codeload.github.com`; Strata model URLs use
literal `https://huggingface.co`. Lock values supply path components, not the initial authority.
However, Python's default URL opener follows redirects. A fixed initial host is not an
allowlist of final destinations; Hugging Face legitimately redirects downloads.

The two `container/fetch_sources.py` scripts stream archives with `shutil.copyfileobj` and
have no byte cap. Their hashes are checked after downloading. Strata's `download()` checks
received bytes against the locked size and verifies SHA-256 before publishing the file.
Consequently, “every download is size-bounded” is not supported by the code. Hash verification
protects content integrity, not download size or network destination. Locks are trusted
repository inputs; a party able to replace a lock can also replace its checksum.

The dynamic-URL findings are audit prompts. No additional allowlist is justified solely by
the scanner message. Any proposed redirect or size policy should address an explicit threat
and preserve the legitimate download paths.

### C++ smoke check

The HIP probe needs the image toolchain. Its `printf` conversions match the argument types;
the named inline style suppression is reasonable.

[.clangd](../runtimes/strata/container/.clangd) suppresses `pp_file_not_found`,
`unknown_typename`, and `undeclared_var_use` throughout the container directory. These codes
also describe genuine missing headers and coding errors, and the policy applies even when
HIP is available. Narrowing to the probe file and retaining full diagnostics in a configured
GPU environment remain review tasks. A clean suppressed editor result is not a successful build.

### Other advisory rules

- `...` is valid in the four `ServerControl` protocol methods. Protocols can also provide
  default implementations; stub bodies are not universally required.
- `yield from rows(...)` is valid because `rows` returns a generator.
- [.typos.toml](../.typos.toml) marks two fixture tokens as intentional. It applies globally
  to those words; fresh-session pi-lens enforcement is still unconfirmed. Preserve the fixtures.
- The reported YAML deserialization finding targets `YAML(typ="safe")`; arbitrary object
  construction is not enabled by that loader.
- The reported path-traversal finding needs its exact site recovered. Operator-selected
  input paths differ from identifiers used to construct output paths under a fixed root.
  The latter still require containment checks, as the report importer already enforces.
- No duplication refactor is justified by an unconfirmed scanner report. Container build
  contexts remain self-contained; code similarity alone is not a shared abstraction requirement.

## Suppression enforcement to verify locally

| Mechanism | Repository state | Evidence limit |
| --- | --- | --- |
| Pyright configuration | Tracked and independently exercised | Editor process/config selection still needs local confirmation |
| ast-grep inline directives and file exceptions | Tracked | Reported effective on the workstation; not rerun in cloud |
| opengrep inline directives | Present beside the source/download sites | Reported effective for ExLlama but ineffective for Strata |
| opengrep rule entries in `.pi-lens.json` | Present for Strata sites | Investigation reports the attempted entries did not suppress those findings |
| pi-lens stored dispositions | Outside Git | Reportedly cleared three remaining opengrep findings; not portable through a clone |
| `.typos.toml` and `.clangd` | Tracked | Restart-sensitive behavior reported; fresh-session coverage needs confirmation |

A stored disposition can survive a session without surviving a machine change. Do not call the
fresh-clone state clean until the tracked configuration alone has been tested. Keep local stores
intact while investigating; do not delete them to obtain an artificial baseline.

## References

- [Pyright configuration](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)
- [mypy configuration](https://mypy.readthedocs.io/en/stable/config_file.html)
- [Upstream tar extraction rule](https://github.com/trailofbits/semgrep-rules/blob/main/python/tarfile-extractall-traversal.yaml)
- [Python extraction filters](https://docs.python.org/3/library/tarfile.html#extraction-filters)
- [Python 3.12 redirect implementation](https://github.com/python/cpython/blob/3.12/Lib/urllib/request.py)
- [clangd configuration](https://clangd.llvm.org/config)
- [typos configuration](https://github.com/crate-ci/typos)
