"""Small statistics with explicit behavior for missing or degenerate input."""

import statistics


def client_decode_rate(
    completion_tokens: int | None, first_output_s: float | None, last_output_s: float | None
) -> float | None:
    """Estimate decode speed as ``(tokens - 1) / (last output - first output)``.

    This does not assume one streamed chunk is one token. Returns ``None`` when a count or
    timing is missing, fewer than two tokens were produced, or no time elapsed.
    """
    if completion_tokens is None or first_output_s is None or last_output_s is None:
        return None
    elapsed = last_output_s - first_output_s
    if completion_tokens < 2 or elapsed <= 0:
        return None
    return (completion_tokens - 1) / elapsed


def relative_spread(values: list[float]) -> float | None:
    """Return ``(max - min) / median``, or ``None`` for fewer than two values or a zero median."""
    if len(values) < 2:
        return None
    median = statistics.median(values)
    if median == 0:
        return None
    return (max(values) - min(values)) / median
