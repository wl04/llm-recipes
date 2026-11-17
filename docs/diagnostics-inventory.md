# Diagnostics inventory

This file states the diagnostic contract the repository enforces, the coverage each checker
actually provides, and how the remaining findings should be read. The
[validation plan](plans/diagnostics-triage-and-scanner-policy.md) holds the work that remains.

## Gates the repository enforces

- `bash scripts/check.sh` runs Ruff lint and formatting checks, mypy for the default target and a
  separate `runtimes/strata` invocation, CPU-only pytest, the generated-document check, and
  ShellCheck when it is installed. CI runs the same script on the oldest supported interpreter and
  the newest validated one.
- [pyrightconfig.json](../pyrightconfig.json) governs editor analysis: Python 3.12, `scripts` on
  the search path, separate test search paths, and `reportMissingImports` disabled in three
  image-only roots. Any editor that loads the project resolves this file on its own; the
  assistant harness is not part of the contract.
- [.typos.toml](../.typos.toml) configures the `typos` CLI, and
  [.clangd](../runtimes/strata/container/.clangd) configures clangd. Each applies on any machine
  that runs the corresponding tool.

mypy is the strict CI checker; Pyright supplies editor feedback. Both report unused suppressions,
and their answers can differ, because a suppression one checker needs can be redundant for the
other. Review disagreements instead of enforcing diagnostic parity. Typed stubs can describe real
interfaces; they are not inherently `Any` placeholders. Pyright supports per-environment diagnostic
overrides, and `pyrightconfig.json` takes precedence over `[tool.pyright]`.

Behavior with regression coverage in `scripts/check.sh`:

- non-object `VERSION` data is rejected;
- invalid recipe launch settings surface as an argparse error from the ExLlama
  `launch_runtime()` helper, which changes error behavior deliberately;
- importer failures name the native settings path;
- `doctor.read_json` failures reach `check_configuration` and `check_prepared` as findings, and
  invalid nested configuration does not abort collection of the other checks;
- both source extractors reject a checksum mismatch before opening the archive, reject traversal
  entries and links that escape the destination, and leave a rejected destination unpublished.

## Coverage the configuration trades away

`pyrightconfig.json` disables missing-import diagnostics in three roots:

- `runtimes/exllamav3-tabbyapi/container`
- `runtimes/exllamav3-tabbyapi/scripts`
- `runtimes/strata/container`

Those roots hold image-only packages: Torch, ExLlamaV3, TabbyAPI's `common` modules, and Strata's
server dependencies. Installing them into the host environment for editor analysis is unnecessary.

The exceptions are directory-bounded and recursive, and they hide first-party import failures
alongside image dependencies, so they are a traded coverage gap rather than evidence that imports
in those roots resolve. Every other location - the repository root, `scripts/`, `tests/`,
`runtimes/strata/scripts/`, and sibling directories of the exempted roots - reports both an
unresolvable external import and a misspelled first-party import, while reporting type errors such
as an `int` assigned to a `str` annotation everywhere. Those overrides are the only thing
suppressing the import diagnostics: without them the same files report both imports inside the
three roots, and the type errors stay reported in every location.

To reproduce, place a file containing one nonexistent external import, one misspelled first-party
import, and a wrong-type assignment in each location, with a correctly named helper beside it, then
run `pyright --project <checkout>/pyrightconfig.json --pythonpath <checkout>/.venv/bin/python
<file>` and compare per file. Start from an unmodified checkout and confirm it reports nothing:
where the checker cannot query the selected interpreter, missing host dependencies change the
import result and the comparison proves nothing.

## Reading scanner output

Rule findings from lexical and pattern scanners carry no repository gate, so read them as
prompts rather than verdicts:

- Files and analysis lanes are different units; totals over them cannot be added into a coverage
  figure. Report files scanned, which lanes answered, and which timed out or were unavailable or
  demoted. A lane that did not answer leaves its files unconfirmed, not clean.
- Two runs with different lane coverage or a different Python environment are different
  observations. Match rule ids and scanned paths across runs; do not treat differing totals as a
  before-and-after measurement.
- Auxiliary lanes can replay cached results while a live lane times out. Confirm freshness from
  cache timestamps rather than from a reported total.
- Some tools read configuration only at startup, so a configuration change can require a server
  restart before it takes effect.
- A scanner's stored dispositions live outside the repository. A fresh clone shows those findings
  again, which is the expected state and not a regression. Keep local stores intact during
  investigation; do not delete them to manufacture a clean baseline, and do not edit tracked
  sources to silence a finding that only a local store would hide.

## Where each suppression lives and whether anything gates it

| Suppression | Location | Gated by |
| --- | --- | --- |
| `reportMissingImports` off in three roots | `pyrightconfig.json`, tracked | the editor's Pyright; `check.sh` does not run Pyright |
| mypy exemptions for image-only modules | `pyproject.toml`, tracked | `check.sh` through mypy |
| inline directives naming scanner rules | `scripts/doctor.py`, `runtimes/strata/container/check_hip.cpp`, `runtimes/exllamav3-tabbyapi/container/fetch_sources.py`, `runtimes/strata/container/fetch_sources.py`, and `runtimes/strata/scripts/prepare_models.py`; tracked | no repository gate; only a scanner that recognizes the directive |
| word exclusions for fixture payloads | `.typos.toml`, tracked | the `typos` CLI; `check.sh` does not run it |
| suppressed clangd diagnostic codes | `runtimes/strata/container/.clangd`, tracked | clangd on any machine that runs it |
| stored dispositions for individual findings | machine-local, outside Git | nothing portable |

A directive whose rule id differs from the id the scanner reports suppresses nothing, so a
directive that appears to have no effect needs its id compared with the reported one before it is
credited or widened. A file-wide exception also hides matching findings added to that file later.

## Findings and policy

### Imports and typing

Keep the config-relative mypy search path and the Python 3.12 target, and keep
`mypy_path` pointed at `scripts` so a single-file mypy invocation resolves first-party modules.
Review each unused-ignore disagreement individually, since an ignore unused by one checker can be
required by the other. Narrow the missing-import exceptions where a maintainable alternative
exists; do not install the GPU stack to satisfy a host editor.

### Exceptions and numeric conversions

`doctor.read_json` propagates failures to `check_configuration` and `check_prepared`, which turn
them into diagnostic findings. `tests/test_doctor.py` covers missing files, denied reads, invalid
JSON, non-object documents, and invalid UTF-8 through `diagnose`, confirming that both checks
report failures without aborting collection. Invalid Pi `providers` and Strata `args`/`vision`
container types also produce configuration findings.

Installer filesystem operations propagate to `install.main`, which catches `OSError`,
`RuntimeError`, and `subprocess.SubprocessError`.

Do not add local handlers merely because a lexical scanner flags a throwing call. Check the callers
and the intended boundary first. The `unchecked-throwing-call-python` rule matches syntactically
and has no type or call-graph model, so it cannot separate a caught-from-enclosing-scope handler
from a missing one, and it cannot see a process exit that terminates every handler. Its findings
are a starting point for reading a boundary, not evidence that the boundary is wrong.

The numeric-parse warnings remain enabled. Some conversions are intrinsically safe, such as
`int(bool_value)`; others depend on trusted OS output, validated inputs, or caller handling.
`startswith("MemTotal:")` identifies a record but does not validate its number. `isdigit()` is not
a general proof that `int()` succeeds: both `"²".isdigit()` and `"--1".lstrip("-").isdigit()` are
true, while conversion raises. `max(value, 1)` is not a finite-number validator. None of these
observations establish a reachable failure with normal kernel data, and none make a conversion
site automatically safe.

### Source extraction and network downloads

Both source downloaders verify SHA-256 and then extract with `filter="data"`. The upstream
`tarfile-extractall-traversal` rule excludes the `members=` idiom and does not recognize
`filter="data"`, so those two sites read as false positives for that rule while the rule stays
valuable for unguarded extraction. CPU-only tests in `tests/test_source_extraction.py` exercise
both downloaders with local archives: valid extraction, checksum rejection before the archive is
opened, traversal entries, and escaping symbolic and hard links. Rejection leaves the destination
unpublished, preserves the file outside the destination, and removes temporary extraction
directories. `filter="data"` is not a general resource-exhaustion defense.

The initial source URLs use literal `https://codeload.github.com`; Strata model URLs use literal
`https://huggingface.co`. Lock values supply path components, never the initial authority. Python's
default URL opener follows redirects, so a fixed initial host is not an allowlist of final
destinations, and Hugging Face legitimately redirects downloads.

The two `container/fetch_sources.py` scripts stream archives with `shutil.copyfileobj` and have no
byte cap; their hashes are checked after downloading. Strata's `download()` compares received bytes
against the locked size and verifies SHA-256 before publishing the file. Size bounding is therefore
a property of that path alone, and hash verification protects content integrity, not download size
or network destination. Locks are trusted repository inputs: a party able to replace a lock can
also replace its checksum.

The `dynamic-urllib-use-detected` rule is an audit prompt. No allowlist follows from the scanner
message. Any redirect or size policy needs an explicit threat and must preserve the legitimate
download paths.

### C++ smoke check

The HIP probe needs the image toolchain, because ROCm and the HIP headers exist only inside the
image. Its `printf` conversions match the argument types, so the inline style directive there is a
reasonable narrow exception; a formatting finding there is a false positive on its own merits.

[.clangd](../runtimes/strata/container/.clangd) suppresses `pp_file_not_found`,
`unknown_typename`, and `undeclared_var_use` throughout the container directory. Those codes also
describe genuine missing headers and real coding errors, and the suppression applies even on a
machine where HIP is available, so narrowing it to the probe file and keeping full diagnostics in
a configured GPU environment stays open work. A suppressed editor result is not a successful
build.

### Other advisory rules

- `...` is valid in the four `ServerControl` protocol methods. Protocols can also provide default
  implementations; stub bodies are not universally required.
- `yield from rows(...)` is valid, because `rows` returns an annotated generator.
- `.typos.toml` marks two fixture tokens as intentional. The exclusions apply globally to those
  words, and no repository gate runs `typos`, so they take effect when the CLI is run. Preserve
  the fixtures rather than skipping the tests that carry them.
- Configuration loading stays on safe loaders. `scripts/doctor.py` uses `yaml.safe_load`, and
  `runtimes/exllamav3-tabbyapi/scripts/serve.py` reads `config/tabby.yml` with `YAML(typ="safe")`
  and writes settings with a round-trip `YAML()` dump. Neither path enables arbitrary object
  construction, so a deserialization finding naming them is a false positive unless it identifies
  another construction path.
- A traversal finding on operator-selected input paths is a different question from an identifier
  used to build an output path under a fixed root. The latter require containment checks, as the
  report importer enforces.
- The ExLlama serving module has no `adapter-registry.json` read and no `_load_json` helper, so
  neither supports a throwing-call finding there.
- Container build contexts stay self-contained on purpose. Code similarity alone is not a shared
  abstraction requirement, and a duplication refactor needs its own justification.

## References

- [Pyright configuration](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)
- [mypy configuration](https://mypy.readthedocs.io/en/stable/config_file.html)
- [Upstream tar extraction rule](https://github.com/trailofbits/semgrep-rules/blob/main/python/tarfile-extractall-traversal.yaml)
- [Python extraction filters](https://docs.python.org/3/library/tarfile.html#extraction-filters)
- [Python 3.12 redirect implementation](https://github.com/python/cpython/blob/3.12/Lib/urllib/request.py)
- [clangd configuration](https://clangd.llvm.org/config)
- [typos configuration](https://github.com/crate-ci/typos)
