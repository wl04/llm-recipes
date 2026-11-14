"""Incremental run storage: JSON Lines appended as the run proceeds, plus an atomic meta file.

Each line is complete when written, so an interrupted run leaves usable data; only a final
partially written line can be damaged, and readers ignore it.
"""

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

META = "meta.json"
REQUESTS = "requests.jsonl"
SAMPLES = "samples.jsonl"
ENGINE_LOG = "server-logs/engine.log"


class RunWriter:
    """Create a new run directory and append records to it from any thread."""

    def __init__(self, directory: Path) -> None:
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise ValueError(f"Run directory already exists: {directory}") from error
        self._directory = directory
        self._lock = threading.Lock()

    @property
    def directory(self) -> Path:
        return self._directory

    def write_meta(self, meta: dict[str, Any]) -> None:
        """Replace the meta file atomically."""
        target = self._directory / META
        temporary = target.with_suffix(".tmp")
        with self._lock:
            temporary.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
            os.replace(temporary, target)

    def _append(self, name: str, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock, (self._directory / name).open("a") as handle:
            handle.write(line)

    def append_request(self, record: dict[str, Any]) -> None:
        self._append(REQUESTS, record)

    def append_sample(self, record: dict[str, Any]) -> None:
        self._append(SAMPLES, record)


@dataclass(frozen=True)
class RawRun:
    """Everything recorded by one run."""

    meta: dict[str, Any]
    requests: list[dict[str, Any]]
    samples: list[dict[str, Any]]
    engine_log: str | None = None


def _read_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    lines = path.read_text().splitlines()
    records = []
    for number, line in enumerate(lines, start=1):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            if number == len(lines):
                break
            raise ValueError(f"{path.name} line {number} is not valid JSON") from error
    return records


def read_run(directory: Path) -> RawRun:
    """Read a completed or interrupted run.

    Raises:
        ValueError: the meta file is missing or invalid, or a line other than the last is damaged.
    """
    try:
        meta = json.loads((directory / META).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{directory} has no readable {META}") from error
    log = directory / ENGINE_LOG
    logs = [log] if log.is_file() else []
    if meta.get("server", {}).get("kind") == "tabbyapi":
        logs = sorted((directory / "server-logs").glob("*.log"))
    return RawRun(
        meta=meta,
        requests=_read_lines(directory / REQUESTS),
        samples=_read_lines(directory / SAMPLES),
        engine_log="\n".join(p.read_text(errors="replace") for p in logs) if logs else None,
    )
