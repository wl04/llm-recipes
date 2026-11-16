"""Concurrent resource sampling on the monotonic clock."""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from baseline.sources import Reading

Sink = Callable[[dict[str, Any]], None]
RECENT_SAMPLES = 4096


@dataclass(frozen=True)
class Source:
    """A reader polled every ``every`` ticks; ``keys`` name what it provides for error reporting."""

    name: str
    read: Callable[[], Reading]
    keys: tuple[str, ...]
    every: int = 1


class Sampler:
    """Poll sources at a fixed interval on a background thread.

    ``start`` takes the first sample before returning and ``stop`` takes a last one, so every
    interval between the two calls is bracketed by samples. A failing source or sink is recorded
    and never ends sampling.
    """

    def __init__(
        self,
        sources: list[Source],
        interval_s: float,
        sink: Sink,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sources = list(sources)
        self._lock = threading.Lock()
        self._recent: deque[dict[str, Any]] = deque(maxlen=RECENT_SAMPLES)
        self._interval = interval_s
        self._sink = sink
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tick = 0
        self.failures = 0
        self.last_failure: str | None = None

    def sample_once(self) -> None:
        """Take one sample now; used by the sampling thread and by start and stop."""
        values: dict[str, float] = {}
        errors: dict[str, str] = {}
        taken = self._clock()
        with self._lock:
            current = list(self._sources)
        for source in current:
            if self._tick % source.every:
                continue
            try:
                reading = source.read()
            except Exception as error:  # noqa: BLE001 - a source must never end monitoring
                for key in source.keys:
                    errors[key] = f"{source.name}: {error!r}"
                continue
            values.update(reading.values)
            errors.update(reading.errors)
        self._tick += 1
        sample = {"t": taken, "values": values, "errors": errors}
        with self._lock:
            self._recent.append(sample)
        try:
            self._sink(sample)
        except Exception as error:  # noqa: BLE001 - a full disk must not end monitoring
            self.failures += 1
            self.last_failure = repr(error)

    def recent(self, seconds: float) -> list[dict[str, Any]]:
        """Samples from the last ``seconds`` before the newest one, oldest first."""
        with self._lock:
            samples = list(self._recent)
        if not samples:
            return []
        cutoff = samples[-1]["t"] - seconds
        return [sample for sample in samples if sample["t"] >= cutoff]

    def add_sources(self, sources: list[Source]) -> None:
        """Poll more sources from the next sample on, for example once the server exists."""
        with self._lock:
            self._sources.extend(sources)

    def start(self) -> None:
        """Take the first sample, then sample in the background."""
        if self._thread is not None:
            raise ValueError("Sampler already started")
        self.sample_once()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        due = self._clock() + self._interval
        while not self._stop.wait(max(0.0, due - self._clock())):
            self.sample_once()
            due = max(due + self._interval, self._clock())

    def stop(self) -> None:
        """Stop the thread and take a last sample; safe to call without ``start``."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
            self.sample_once()

    @property
    def running(self) -> bool:
        """Whether the sampling thread is alive; ``stop`` ends it before returning."""
        thread = self._thread
        return thread is not None and thread.is_alive()
