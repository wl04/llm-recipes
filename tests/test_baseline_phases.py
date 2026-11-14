"""Deciding when a freshly loaded server has settled."""

from typing import Any

from baseline import phases


def sample(t: float, cpu_usec: float, busy: float, total: float) -> dict[str, Any]:
    values = {"cpu_usec": cpu_usec, "cpu_busy_ticks": busy, "cpu_total_ticks": total}
    return {"t": t, "values": values, "errors": {}}


def quiet(start: float, end: float) -> list[dict[str, Any]]:
    """Server at 0.05 cores and the system 2% busy, sampled every second."""
    return [
        sample(t, 50_000 * (t - start), 2 * (t - start), 100 * (t - start))
        for t in range(int(start), int(end) + 1)
    ]


def settled(samples: list[dict[str, Any]], window_s: float = 10.0) -> bool | None:
    return phases.settled(samples, window_s=window_s, system_cpu_max=15.0, server_cpu_max=0.25)


def test_settled_is_true_when_system_and_server_stay_below_the_limits() -> None:
    assert settled(quiet(0, 12)) is True


def test_settled_is_none_until_the_window_has_been_observed() -> None:
    assert settled(quiet(0, 5)) is None


def test_settled_is_false_while_the_server_is_busy() -> None:
    busy = [sample(t, 2_000_000 * t, 2 * t, 100 * t) for t in range(0, 13)]

    assert settled(busy) is False


def test_settled_is_false_while_the_system_is_busy() -> None:
    busy = [sample(t, 50_000 * t, 60 * t, 100 * t) for t in range(0, 13)]

    assert settled(busy) is False


def test_settled_only_considers_the_most_recent_window() -> None:
    loading = [sample(t, 3_000_000 * t, 50 * t, 100 * t) for t in range(0, 10)]
    base = loading[-1]
    resting = [
        sample(
            9 + k,
            base["values"]["cpu_usec"] + 10_000 * k,
            base["values"]["cpu_busy_ticks"] + 1 * k,
            base["values"]["cpu_total_ticks"] + 100 * k,
        )
        for k in range(1, 13)
    ]

    assert settled(loading + resting) is True


def test_settled_ignores_a_criterion_that_cannot_be_measured() -> None:
    samples = [{"t": float(t), "values": {}, "errors": {}} for t in range(0, 13)]

    assert settled(samples) is True


def test_settled_ignores_counter_resets() -> None:
    samples = quiet(0, 12)
    samples[6]["values"]["cpu_usec"] = 0

    assert settled(samples) is True
