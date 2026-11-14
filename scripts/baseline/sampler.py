"""Concurrent resource sampling on the monotonic clock."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from baseline.sources import Reading

Sink = Callable[[dict[str, Any]], None]


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
        self._sources = sources
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
        for source in self._sources:
            if self._tick % source.every:
                continue
            try:
                reading = source.read()
            except Exception as error:  # a source must never end monitoring
                for key in source.keys:
                    errors[key] = f"{source.name}: {error!r}"
                continue
            values.update(reading.values)
            errors.update(reading.errors)
        self._tick += 1
        try:
            self._sink({"t": taken, "values": values, "errors": errors})
        except Exception as error:  # a full disk must not silently end monitoring either
            self.failures += 1
            self.last_failure = repr(error)

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
