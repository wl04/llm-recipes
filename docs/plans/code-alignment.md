# Plan: remaining AGENTS.md alignment work

Checked locally with `bash scripts/check.sh`; each entry is a concrete unit of work with the files
that have to change.

## Split responsibilities in large units

- [ ] `scripts/baseline/runner.py` — `Runner` holds 33 methods across four levels of detail: server
      lifecycle, phase and workload execution, functional checks, and teardown reporting. Split by
      collaborator when an upcoming change makes the boundary worth having; the split moves state
      (`self._phases`, `self._cases`, `self._warnings`) between the pieces, so it needs a design
      step rather than a mechanical move.
- [ ] `scripts/doctor.py:check_prepared` and `check_configuration` (16 branches each) — report one
      group of problems per function: model preparation, then container and GPU configuration.
      `check_model` already shows the shape.
- [ ] `scripts/baseline/aggregate.py:build_results` (80 lines, 13 branches) and `_resource_metrics`
      (84 lines) — build each `results.json` section in its own function; `schema.validate_results`
      is already one check per section, and the two files should mirror each other.

## Decide on `shfmt`

- [ ] `AGENTS.md` names `shfmt -d` "if configured" while `scripts/check.sh` runs ShellCheck only.
      Either add `shfmt -d` for the shell entry points to `scripts/check.sh`, or drop the mention of
      `shfmt` from the rules. The repository currently formats shell by hand.
