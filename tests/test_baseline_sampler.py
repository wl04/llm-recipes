"""Concurrent sampling: start before requests, keep running while the caller blocks."""

import threading
import time
from typing import Any

import pytest
from baseline.sampler import Sampler, Source
from baseline.sources import Reading


class Counter:
    """A source whose value rises with every read."""

    def __init__(self) -> None:
        self.reads = 0

    def __call__(self) -> Reading:
        self.reads += 1
        return Reading(values={"counter": float(self.reads)})


def collect(
    sources: list[Source], interval_s: float = 0.01
) -> tuple[Sampler, list[dict[str, Any]]]:
    samples: list[dict[str, Any]] = []
    return Sampler(sources, interval_s, samples.append), samples


def wait_until(condition: Any, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.005)
    raise AssertionError("condition not met in time")


def test_start_takes_first_sample_before_returning() -> None:
    sampler, samples = collect([Source("c", Counter(), ("counter",))], interval_s=60)

    sampler.start()
    sampler.stop()

    assert len(samples) == 2
    assert samples[0]["values"] == {"counter": 1.0}


def test_stop_takes_final_sample_after_the_last_tick() -> None:
    sampler, samples = collect([Source("c", Counter(), ("counter",))])
    sampler.start()
    wait_until(lambda: len(samples) >= 3)

    sampler.stop()

    assert samples[-1]["t"] >= samples[-2]["t"]
    assert samples[-1]["values"]["counter"] == len(samples)


def test_sampling_continues_while_the_caller_is_blocked() -> None:
    sampler, samples = collect([Source("c", Counter(), ("counter",))])
    sampler.start()
    release = threading.Event()
    before = len(samples)

    release.wait(0.1)
    during = len(samples)
    sampler.stop()

    assert during - before >= 3


def test_source_failure_is_recorded_per_key_and_sampling_continues() -> None:
    def broken() -> Reading:
        raise RuntimeError("sensor offline")

    sampler, samples = collect(
        [Source("gpu", broken, ("vram_bytes", "gtt_bytes")), Source("c", Counter(), ("counter",))],
        interval_s=60,
    )

    sampler.start()
    sampler.stop()

    assert "sensor offline" in samples[0]["errors"]["vram_bytes"]
    assert "gtt_bytes" in samples[0]["errors"]
    assert samples[0]["values"] == {"counter": 1.0}


def test_partial_reading_errors_are_passed_through() -> None:
    def partial() -> Reading:
        return Reading(values={"a": 1.0}, errors={"b": "permission denied"})

    sampler, samples = collect([Source("s", partial, ("a", "b"))], interval_s=60)

    sampler.start()
    sampler.stop()

    assert samples[0]["values"] == {"a": 1.0}
    assert samples[0]["errors"] == {"b": "permission denied"}


def test_slower_source_is_read_every_nth_tick() -> None:
    fast, slow = Counter(), Counter()
    sampler, _ = collect(
        [Source("f", fast, ("counter",)), Source("s", slow, ("slow",), every=3)], interval_s=60
    )
    sampler.start()
    for _ in range(5):
        sampler.sample_once()
    sampler.stop()

    assert fast.reads == 7
    assert slow.reads == 3


def test_sink_failure_does_not_stop_sampling_and_is_reported() -> None:
    calls: list[int] = []

    def sink(sample: dict[str, Any]) -> None:
        calls.append(1)
        if len(calls) == 2:
            raise OSError("disk full")

    sampler = Sampler([Source("c", Counter(), ("counter",))], 0.01, sink)
    sampler.start()
    wait_until(lambda: len(calls) >= 4)
    sampler.stop()

    assert sampler.failures == 1
    assert "disk full" in (sampler.last_failure or "")


def test_start_twice_is_rejected() -> None:
    sampler, _ = collect([Source("c", Counter(), ("counter",))], interval_s=60)
    sampler.start()
    try:
        with pytest.raises(ValueError, match="already started"):
            sampler.start()
    finally:
        sampler.stop()


def test_sources_added_while_running_are_polled_from_the_next_sample() -> None:
    sampler, samples = collect([Source("c", Counter(), ("counter",))], interval_s=60)
    sampler.start()
    sampler.add_sources([Source("late", lambda: Reading(values={"late": 1.0}), ("late",))])

    sampler.sample_once()
    sampler.stop()

    assert "late" not in samples[0]["values"]
    assert samples[1]["values"]["late"] == 1.0


def test_recent_returns_only_samples_within_the_window_before_the_latest() -> None:
    times = iter([0.0, 5.0, 9.0, 10.0])
    sampler = Sampler(
        [Source("c", Counter(), ("counter",))], 60, lambda sample: None, lambda: next(times)
    )
    for _ in range(4):
        sampler.sample_once()

    window = sampler.recent(5.0)

    assert [sample["t"] for sample in window] == [5.0, 9.0, 10.0]


def test_recent_is_empty_before_any_sample() -> None:
    sampler = Sampler([], 60, lambda sample: None)

    assert sampler.recent(5.0) == []
