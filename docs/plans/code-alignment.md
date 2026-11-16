# Plan: remaining AGENTS.md alignment work

Checked locally with `bash scripts/check.sh`; each entry is a concrete unit of work with the files
that have to change.

## Split responsibilities in large units

- [ ] `scripts/baseline/runner.py` — `Runner` holds 33 methods across four levels of detail: server
      lifecycle, phase and workload execution, functional checks, and teardown reporting. Split by
      collaborator when an upcoming change makes the boundary worth having; the split moves state
      (`self._phases`, `self._cases`, `self._warnings`) between the pieces, so it needs a design
      step rather than a mechanical move.
- [ ] `scripts/baseline/aggregate.py:build_results` (80 lines, 13 branches) — build each
      `results.json` section in its own function; `schema.validate_results` is already one check per
      section, and the two files should mirror each other.
