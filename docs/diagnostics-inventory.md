# Diagnostics inventory

Every diagnostic type the workspace scanner reports, with the evidence behind each verdict and the
upstream mechanism for disposition. This is the reference the plan at
[plans/diagnostics-triage-and-scanner-policy.md](plans/diagnostics-triage-and-scanner-policy.md)
acts on; the plan changes code, this file explains findings.

## Measurement

Command: `lens_diagnostics` with `mode: "full"`, `source: "lsp"`, `severity: "all"`, `waitMs: 10000`,
over the workspace root. The numbers below are that run.

| | |
| --- | --- |
| Files scanned | 86 |
| Files with findings | 25 |
| Files confirmed clean | 52 |
| Lanes that did not answer (push-only, no verdict) | 9 |
| Findings | 115 across 10 rule types |

Two facts about a `full` sweep, because they change what the numbers mean:

- **A lane that did not answer is not a clean lane.** Nine LSP servers are push-only. The
  `opengrep` rule family answered on some runs and timed out on others: the two `Semgrep`-lane rule
  ids listed under *Observed on push surfaces only* fired in a turn-end advisory and were absent
  from the sweep that timed out. Treat "no findings from lane X" as unmeasured unless the lane
  reported coverage.
- **A cold lane reports fewer findings than a warm one.** `ast-grep` produced nothing under
  `runtimes/` in the first sweep of the session and 22 findings in a later one, with no change to
  those files.

## Inventory

| Severity | Lane | Rule | Findings | Files |
| --- | --- | --- | --- | --- |
| error | Pyright | `reportMissingImports` | 12 | 5 |
| error | Semgrep (opengrep) | `tarfile-extractall-traversal` | 2 | 2 |
| error | ast-grep | `unchecked-throwing-call-python` | 27 | 11 |
| warning | Semgrep (opengrep) | `dynamic-urllib-use-detected` | 3 | 3 |
| warning | ast-grep | `unchecked-numeric-parse-python` | 48 | 13 |
| warning | ast-grep | `no-ellipsis-body` | 4 | 1 |
| warning | ast-grep | `no-yield-from-non-iterable` | 1 | 1 |
| information | typos | `typos` | 2 | 2 |
| error | clangd | `pp_file_not_found`, `unknown_typename`, `undeclared_var_use` | 15 | 1 |
| warning | ast-grep | `cpp-no-printf` | 1 | 1 |

`gitleaks`, `jscpd`, `madge`, `dead-code`/`vulture`, `ruff`, `shellcheck` and the container lanes
reported no findings in this workspace. The toolchain pi-lens installs is real and present:
`~/.pi-lens/bin` holds `opengrep`, `gitleaks`, `typos-lsp`, `zizmor`, `taplo` and `marksman`, and
`~/.pi-lens/tools/clangd/bin/clangd` is the C++ language server. `check_hip.cpp` was therefore
measured after the first sweep, which is what raised the totals above.

---

## `reportMissingImports` — Pyright, error

**Checks:** an import target that cannot be resolved on the configured search path.

**Here:** all 12 are modules that exist only inside a built container image.
`check_image.py` (5) and `fetch_sources.py` (1) import the image's own dependencies; `serve.py` (2)
reaches `common.config_models` and `common.sampling` after `sys.path.insert(0, "/opt/src/tabbyAPI")`
inside `validate_sections`; `prepare_models.py` (3) imports image-only packages. None of these files
runs outside the image, and CI does not import them.

**Verdict:** correctly reported, environment-dependent by design. Not a defect.

**Disposition (implemented):** `pyrightconfig.json` pins `pythonVersion` to the supported floor and
carries `extraPaths` for the workspace modules, an environment rooted at `tests/`, and one environment
per image-only root that sets `reportMissingImports: "none"`. Measured with the pyright CLI against
the project interpreter: 86 files, 0 errors, 0 warnings, 0 notes. The carve-out is scoped to those
roots, so a first-party rename in `scripts/`, `tests/` or the repository tooling still fails the
sweep. A stub package would satisfy the import and then annotate those symbols as `Any`-shaped fakes;
a single `mypy_path` across both runtime directories would let one runtime's sibling module resolve
against the other runtime's identically named helper. `reportMissingImports: "none"` at the top level
is rejected for the same reason a blanket `# pyright: ignore` is: it hides a real rename.

**Alignment:** consistent with *Separate business rules from HTTP, databases, files* — the unresolvable
imports are the container boundary, and the code states it explicitly with a `sys.path.insert` inside
the function that needs it.

## `tarfile-extractall-traversal` — Semgrep family (opengrep), error

**Checks:** `TarFile.extractall()` without a traversal guard.

**Here:** `runtimes/exllamav3-tabbyapi/container/fetch_sources.py:41` and
`runtimes/strata/container/fetch_sources.py:20`. Both call
`extractall(extract_dir, filter="data")`. The `filter` argument is the guard the rule asks for, and it
is load-bearing: the `tar` filter would not, and the default filter warns in 3.12 and changes in 3.14.

**Verdict:** false positive. The rule predates the `filter="data"` API.

**Disposition (implemented):** both sites carry `# pi-lens-ignore:
trailofbits.python.tarfile-extractall-traversal`, and the strata site also carries a `false-positive`
disposition in the store because the `opengrep` lane does not apply inline directives uniformly (see
*Disposition mechanisms*). The upstream definition
([`tarfile-extractall-traversal.yaml`](https://github.com/trailofbits/semgrep-rules/blob/main/python/tarfile-extractall-traversal.yaml))
excludes only `extractall(..., members=$MEMBERS)` — the pre-3.12 idiom — so a `filter=` argument is
outside the rule's model entirely; `subcategory: [vuln]` with `severity: ERROR` is why the finding
arrives as a blocker rather than a hint. A `# type: ignore` is not available here:
`warn_unused_ignores = true` makes an unused mypy suppression a CI failure.

**Alignment:** the repo's rule is *Do not ignore errors; add context*. A bare `nosemgrep` would violate
it; the disposition therefore carries the reason in the store and, for any suppression kept in source,
names the guard (`filter="data"`) rather than muting the rule.

## `unchecked-throwing-call-python` — ast-grep, error

**Checks:** a call lexically outside a `try` block, matched by argument shape.

**Here (27 findings, 11 files):**

| Site class | Count | Evidence |
| --- | --- | --- |
| Module entry point where handling is the documented contract | 3 | `install.py:119,176,214` — inside `main()`, which `install_and_run` wraps in `except Exception` (line 417) to report and exit non-zero |
| Helper whose callers all handle | 1 | `doctor.py:26` — `read_json` is called at 77, 78, 95, 115, 152, 181 and 221, every one inside a `try` whose handler catches `OSError` and `ValueError` (lines 76/85, 150/173, 259/268) |
| Container/image module, CLI entry point | 23 | `prepare_models.py` (12), `serve.py` (4), `fetch_sources.py` (3), `check_image.py` (2), `recipe_config.py` (1), `importer.py` (1) |

The rule tracks the shape of the call, not whether it raises: it flags
`json.loads((recipe / "launch.json").read_text())` in `serve.py:100` while `serve.py:100`'s sibling
`json.loads((recipe / "adapter-registry.json").read_text())` is inside `_load_json`, whose caller
catches `OSError` and `json.JSONDecodeError`. It fired at `serve.py:152` before the `launch_runtime()`
helper was extracted and went silent there afterwards, with identical behaviour — the helper moved the
call inside a function the rule's pattern does not match.

**Verdict:** no defect in the family. The `install.py` sites disappeared with the earlier CLI fix, and
the `importer.py` site became an explicit error with the file named in it. What is left is
by-design-at-boundary or pattern-shaped. Wrapping every call is rejected: it would add ~23 handlers to
satisfy a lexical matcher, against *Preserve public contracts* (these modules' documented contract is
caller-level handling) and the *caller catches `OSError`, `json.JSONDecodeError`* convention in
[project-instructions.md](project-instructions.md).

**Disposition (implemented):** [`ast-grep-ignore: <rule-id>`](https://ast-grep.github.io/guide/rule-config.html)
for the one host-code site (`scripts/doctor.py`, which documents that its callers report read failures
as findings), and a per-file rule carve in `.pi-lens.json` for the eight runtime modules, listed by
name so that a new module under `runtimes/` still reports and is decided on its own merits. A bare
`ast-grep-ignore` would mute every rule on the line, so the rule id is always written out. Measured
outcome: `scripts/` and both `runtimes/*/scripts/` trees report 0 errors across 38 files; `runtimes/`
reports 0 findings with 25 dropped by policy. Rule-level gating of the pattern itself (top-level
functions only) remains the durable upstream change; the carve is the repository-side equivalent.

**Alignment — conflict to resolve, not paper over:** the rule's premise is *every throwing call needs
a local handler*. AGENTS.md says the opposite for this codebase: *Validate inputs at system boundaries*
and *Distinguish missing data from failure* — validation and translation at the boundary, propagation
between. Do not add `try` blocks to satisfy the rule.

## `dynamic-urllib-use-detected` — Semgrep family (opengrep), warning

**Checks:** `urllib.request.urlopen` on a URL whose scheme is not statically constrained.

**Here:** `runtimes/exllamav3-tabbyapi/container/fetch_sources.py:32`,
`runtimes/strata/container/fetch_sources.py:34`, `runtimes/strata/scripts/prepare_models.py:47`. All
three take the URL from a pinned `manifest.json` in the repo.

**Verdict (revised by measurement):** misfire, not a gap. All four network call lines build their URL
from a literal `https://` and a literal host — `codeload.github.com` in both `fetch_sources.py` files,
`huggingface.co` in `prepare_models.py` — and only path segments come from data, so no manifest value
can move the scheme or the authority. `HF_ENDPOINT` is assigned a literal in a child environment and
never read as input. Every download is size-bounded and checked against a pinned SHA-256, so a hostile
response cannot reach the filesystem as valid content. A scheme/host allowlist over a value that cannot
vary in scheme or host would restate the line above it, so plan item 3 closed on evidence instead of
code.

**Disposition (implemented):** the publisher classifies this as an *audit* rule — "a rule to use for
auditors to audit a code-base ... It is not recommended to use this type of rules in CICD, or show the
results" ([semgrep contributing docs](https://docs.semgrep.dev/contributing/contributing-to-semgrep-rules-repository)) —
and the identifier carries that classification: `python.lang.security.audit.dynamic-urllib-use-detected`.
The exllama site carries an inline `# pi-lens-ignore:` directive, which the lane honours there; the two
strata sites are recorded as `false-positive` dispositions, which the lane applies everywhere (see
*Disposition mechanisms*).

**Alignment:** *Never hardcode secrets* is unaffected; *Validate inputs at system boundaries* supports
the fix. `# nosemgrep:` is available if the fix is deferred.

## `pp_file_not_found`, `unknown_typename`, `undeclared_var_use` — clangd, error

**Checks:** clang parses the translation unit. A missing header makes every symbol it declared unknown,
so one root cause reports fifteen times.

**Here:** `runtimes/strata/container/check_hip.cpp:1` includes `hip/hip_runtime.h`, which exists only in
the ROCm build image that `COPY`s the file into `/opt/build/`. This workstation has no ROCm: `/opt/rocm`,
`/usr/lib/hip*` and `/usr/include/hip` are all absent. The family is the C++ twin of the image-only
Python imports.

**Verdict:** environment-dependent by design. Not a defect, and installing a ROCm toolchain to analyze a
build-time smoke check is out of proportion to the file.

**Disposition (implemented):** `runtimes/strata/container/.clangd` suppresses those three codes for that
directory alone, per
[clangd's project configuration](https://clangd.llvm.org/config): clangd reads `.clangd` from every
parent directory and project configuration applies to the tree below it. A warm clangd does not reload
the file — the suppression measured clean only after the server restarted. `Suppress: ['*']` is rejected:
it would also hide diagnostics unrelated to the missing header.

**Alignment:** *Determine tool versions, check commands, and architectural constraints from local
instructions* — the image pins the toolchain, and the carve-out states that boundary rather than
pretending the file is host-compilable.

## `cpp-no-printf` — ast-grep, warning

**Checks:** `printf` in C++, preferring `std::cout` or `std::format` for type-safe formatting.

**Here:** `runtimes/strata/container/check_hip.cpp:35`, the host side of the HIP smoke check, emitting
one JSON line for the Python side to parse. The conversions match: `%d` with `int`, `%zu` with `size_t`.

**Verdict:** style preference, no defect. Rewriting it with streams would be unverifiable here — the
file compiles only inside the ROCm image — trading a working build-time check for a lint the build never
runs.

**Disposition (implemented):** `// ast-grep-ignore: cpp-no-printf` above the statement, measured to
clear the finding. The rule stays active everywhere else.

## `unchecked-numeric-parse-python` — ast-grep, warning

**Checks:** `int()` / `float()` outside a `try` block.

**Here (48 findings, 45 distinct sites, 13 files; three sites reported twice):** the family splits by
what the argument actually is.

| Class | Example | Can it raise? |
| --- | --- | --- |
| Parse of a value that cannot be non-numeric | `launch.py:177` `int(any(...))`, `aggregate.py:24` `int(rounded)` where `float(rounded).is_integer()` was just tested | No |
| Parse of a regex capture the module matched | `engine_log.py:70-77`, `cli.py:167`, `importer.py:582` — the pattern anchors `\d+` | Only if the module's own regex changed |
| Parse of OS or engine text behind an explicit guard | `host_facts.py:84` after `line.startswith("MemTotal:")`, `guided.py:39` after `entry.name.isdigit()`, `sources.py:142` behind an `isdigit()` check | Guarded |
| Parse of computed floats | `workloads.py:462` | `int(nan)` raises; inputs are bounded by `max(..., 1)` |

**Verdict:** no defect found. The family is noise here, and the `×2` reports at `aggregate.py:24`,
`engine_log.py:183` and `engine_log.py:192` are the same call reported twice.

**Disposition:** rule-level scoping beats 48 inline comments. [`.sgconfig.yml`](https://ast-grep.github.io/reference/sgconfig.html)
is read from the project directory by the ast-grep runner, which is the place to narrow the rule or
scope it to directories where unvalidated parsing is plausible. Per-directory
`rules.unchecked-numeric-parse-python.ignorePaths` in `.pi-lens.json` is the pi-lens-native form and
carries gitignore semantics, including `!` re-inclusion.

**Decision (plan item 10):** the rule stays enabled and unscoped. Every finding is either un-failable or
guarded, warnings do not block, and the family is the only thing that notices a future unguarded
`int(user_text)` anywhere in the tree. Scoping it away trades that coverage for a quieter widget.

**Alignment:** a 48-comment suppression set would collide with *KISS* and with the zero-fluff comment
rule; path-scoping keeps the signal for new code.

## `no-ellipsis-body` — ast-grep, warning

**Checks:** a function whose body is a bare `...`, described by the rule as "function was scaffolded
but never completed".

**Here:** `scripts/baseline/runner.py:36,38,40,42` — the four members of
`class ServerControl(Protocol)`. A `Protocol` body is required to be a stub, and `...` is the
idiomatic spelling.

**Verdict:** false positive; the rule cannot distinguish `Protocol`, ABC and `@overload` stubs from
unfinished scaffolding.

**Disposition:** rule-level exclusion of classes whose bases include `Protocol`, `ABC`, or of members
under `@overload`/`@abstractmethod` is the durable fix — the pi-lens
`rules/ast-grep-rules/rules/` in the pi-lens package
is upstream, so an exclusion belongs there. `.pi-lens.json` with
`rules.no-ellipsis-body.ignorePaths: ["scripts/baseline/**"]` is the repo-local alternative and loses
the real signal for unfinished functions in the same directory, so it is the fallback, not the choice.

**Alignment:** *Preserve public contracts* — the `Protocol` is the seam between the baseline runner and
the server implementations; stub bodies are the contract.

## `no-yield-from-non-iterable` — ast-grep, warning

**Checks:** `yield from` on a value the rule cannot see as iterable.

**Here:** `scripts/generate_configurations.py:260`, `yield from rows(value, labels, path)`, where
`rows` is annotated `-> Generator[str, None, None]`. A `Generator` is an `Iterable`.

**Verdict:** false positive, provable from the signature on line 252-254.

**Disposition:** the rule is lexical and cannot see annotations. Same options as above; because there
is exactly one instance, an `ast-grep-ignore: no-yield-from-non-iterable` line is cheap — but only
after the annotation is confirmed present, since the finding's value is precisely that the callee's
return type is visible.

## `typos` — typos, information

**Checks:** known misspellings in any tracked file, including comments and fixtures.

**Here:** `tests/test_baseline_api.py:24`, a three-letter token used as generated event content, and
`tests/test_baseline_engine_log.py:218`, a truncated `available` keyword inside a verbatim llama.cpp
log line.

**Verdict:** both are intentional payloads. The engine-log fixture must stay byte-faithful to the
engine output the parser is tested against; renaming it would weaken the test.

**Disposition:** typos reads [`.typos.toml`](https://github.com/crate-ci/typos). The repo-root file
declares both tokens as identity mappings under `[default.extend-words]`, the documented way to mark a
word intentional; `[default.extend-ignore-re]` is the alternative when the flagged span is generated
text. typos resolves the file from the working directory, so it governs a manual `typos` run. The
pi-lens lane is a per-session server that resolves that configuration once, which is why the two
findings kept reporting after the file was added mid-session; a fresh session still has to confirm
the lane picks it up.

**Alignment:** renaming the tokens would damage the engine-log fixture's fidelity to the real engine
output the parser is tested against, so the exception lives in configuration where a reviewer sees it.

## Observed on push surfaces only (opengrep)

Two rule ids have appeared in turn-end advisories on `serve.py` and are **not** in the sweep table
above, because `opengrep` timed out during it. Confirm before acting:

| Rule | Where seen | Reading |
| --- | --- | --- |
| `python-insecure-deserialization` | `serve.py` YAML load of `sections.yaml` | The loader is `YAML(typ="safe")` (ruamel), whose constructor refuses object tags. Deserialization of arbitrary objects is not reachable. Misfire. |
| `python-path-traversal` | `serve.py` recipe/config path handling | Paths come from the operator's own CLI arguments (`--recipe`, `--instance`), not from a request. A local operator naming their own file is not traversal. By design. |

Both are the same shape as the `tarfile` pair: the rule sees a dangerous function name and has no
visibility of the safe loader or the trust boundary.

## Disposition mechanisms

Three layers, checked in this order, with what each one measured to do in this repository:

1. **Inline suppression comment.** `# pi-lens-ignore: <rule-id>` is the portable spelling; each lane also
   accepts its own — `# pyright: ignore` (Pyright), `# nosemgrep: ns.rule-id` (opengrep),
   `// ast-grep-ignore: <rule-id>` (ast-grep), `jscpd:ignore-start/end` (jscpd). Measured: the ast-grep
   form cleared `cpp-no-printf` on the first probe; the `pi-lens-ignore` form cleared `tarfile` and
   `dynamic-urllib` inside a single scan of
   `runtimes/exllamav3-tabbyapi/container/fetch_sources.py` — that same scan still reported the
   undisposed finding beside it — while identical directives in the two `strata` files did nothing. For
   the `opengrep` lane the directive is a hint, not an enforcement. A rule id is mandatory: a bare
   `ast-grep-ignore` mutes every rule on the line.
2. **Stored dispositions** — `false-positive`, `defer`, `flagged`. `false-positive` anchors to rule +
   message + a hash of the flagged line, so rewriting the line re-arms the rule, and it is the only
   disposition that clears a blocking finding. Measured: the three findings that survived layer 1 in the
   `opengrep` lane were gone on the next probe and `runtimes/` reported 0 findings. The store lives in
   the project's pi-lens data directory rather than in git, which is why a source-carried directive is
   still written beside each site for portability to another machine.
3. **`.pi-lens.json`** — `rules.<id>.disable` / `select` / `ignorePaths` / `threshold`, resolved per file
   from the nearest `.pi-lens.json` at or above it; nested files add carve-outs and never lift one.
   Measured: `rules.unchecked-throwing-call-python.ignorePaths` with eight explicit runtime paths took
   effect at once and is what holds the tree quiet. Two spellings of a `Semgrep`-lane rule id were tried
   there — the three-segment form and the four-segment form the probe prints — and neither suppressed
   that lane, which is why layer 2 carries those three sites.

Two operational hazards, both measured here: an invalid `.pi-lens.json` drops the *entire* policy rather
than the broken entry — one missing brace sent every carved-out finding back — and a warm server keeps
the configuration it read at start-up, which is how `.typos.toml` and `.clangd` behaved until their lane
restarted. `dispatch.disabledRunners` is a union across tiers: a project can add a denial and never
remove one.

`# type: ignore` is not a diagnostics tool in this repo: `warn_unused_ignores = true` makes an unused
mypy suppression a CI failure, which is why an editor-driven suppression must be a `pyright` or
`pi-lens-ignore` comment.

## Alignment summary

| Rule | AGENTS.md / project rule it should support | Where it over- or under-reaches |
| --- | --- | --- |
| `unchecked-throwing-call-python` | *Validate inputs at system boundaries* | Over-reaches: demands local `try` inside functions whose contract is to raise. The repo convention is caller-level `except OSError, json.JSONDecodeError` |
| `tarfile-extractall-traversal`, `python-insecure-deserialization`, `python-path-traversal` | *Never hardcode secrets*, *Validate inputs at boundaries* | Over-reaches on the trust boundary: cannot see `filter="data"`, `YAML(typ="safe")`, or that paths are operator-supplied |
| `unchecked-numeric-parse-python` | *Distinguish missing data from failure* | Over-reaches: fires on parses that are guarded by the adjacent expression |
| `dynamic-urllib-use-detected` | *Validate inputs at system boundaries* | Correctly placed as a review aid, but the audit classification is explicit and the URLs keep a literal scheme and host |
| `no-ellipsis-body`, `no-yield-from-non-iterable` | — (style heuristics) | Both misfire on typing constructs (`Protocol` stubs, annotated `Generator`) |
| `reportMissingImports` | *Determine tool versions ... from local instructions* | Correct, but unfixable by config for image-only modules; `extraPaths` would create wrong-module binding between runtimes |
| `typos` | *English names should convey meaning* | Correct, but must not edit test payloads that mirror real engine output |
