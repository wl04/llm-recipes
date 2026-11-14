"""Sample baseline result document shared by the schema, report, and generator tests."""

from typing import Any

from baseline import schema


def sample_results() -> dict[str, Any]:
    """A complete document with measured, unavailable, and skipped values."""
    return {
        "schema_version": 1,
        "suite_version": "1",
        "recipe": "test-recipe",
        "run": {"id": "run-1", "status": "complete"},
        "server": {"kind": "strata", "model": "test-model", "context_tokens": 131072},
        "boot": {
            "metrics": {"uptime_s": schema.measured(540, "s", "/proc/uptime")},
            "warnings": ["Another process was using the GPU at start"],
        },
        "functional": [
            {"id": "text", "status": "pass"},
            {
                "id": "vision",
                "status": "pass",
                "scores": {
                    "identity": {"match": 2, "mismatch": 0, "missing": 0},
                    "detail": {"match": 5, "mismatch": 1, "missing": 3},
                },
            },
        ],
        "warmup": {
            "requests": 2,
            "converged": True,
            "metrics": {"duration_s": schema.measured(14.2, "s", "client monotonic clock")},
        },
        "cases": [
            {
                "id": "context-8k",
                "status": "ok",
                "runs": 5,
                "finish_reason": "stop",
                "metrics": {
                    "input_tokens": schema.measured(8012, "tokens", "server usage"),
                    "output_tokens": schema.measured(1024, "tokens", "server usage"),
                    "first_output_s": schema.measured(2.5, "s", "client monotonic clock"),
                    "client_decode_tok_s": schema.measured(81.5, "tokens/s", "client estimate"),
                    "engine_decode_tok_s": schema.unavailable("server reports no timings"),
                    "noise_first_output_spread": schema.measured(0.04, "ratio", "5 runs"),
                    "noise_decode_spread": schema.measured(0.03, "ratio", "5 runs"),
                },
            },
            {
                "id": "context-120k",
                "status": "skipped",
                "runs": 0,
                "note": "Input plus output exceeds the 65,536-token context",
                "metrics": {},
            },
        ],
        "resources": [
            {
                "case": "context-8k",
                "metrics": {
                    "cpu_cores_avg": schema.measured(1.5, "cores", "cgroup cpu.stat"),
                    "vram_peak_gib": schema.measured(15.1, "GiB", "sysfs mem_info_vram_used"),
                    "swap_out_pages": schema.unavailable("/proc/vmstat not readable"),
                },
            }
        ],
    }
