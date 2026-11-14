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
            "metrics": {
                "uptime_s": schema.measured(540, "s", "/proc/uptime"),
                "load_1m": schema.measured(0.25, "load", "/proc/loadavg"),
                "mem_used_gib": schema.measured(6.5, "GiB", "/proc/meminfo"),
                "mem_total_gib": schema.measured(62.6, "GiB", "/proc/meminfo"),
                "swap_used_gib": schema.measured(0, "GiB", "/proc/meminfo"),
                "swap_total_gib": schema.measured(8.0, "GiB", "/proc/meminfo"),
                "gpu_busy_percent": schema.measured(2, "%", "amdgpu sysfs"),
                "gpu_vram_used_gib": schema.measured(0.17, "GiB", "amdgpu sysfs"),
                "gpu_vram_total_gib": schema.measured(15.9, "GiB", "amdgpu sysfs"),
                "gpu_power_w": schema.measured(9.3, "W", "amdgpu sysfs"),
                "gpu_temp_c": schema.measured(29, "C", "amdgpu sysfs"),
            },
            "warnings": ["Another process was using the GPU at start"],
        },
        "phases": [
            {
                "id": "idle",
                "status": "ok",
                "metrics": {
                    "duration_s": schema.measured(30, "s", "client monotonic clock"),
                    "system_cpu_busy_percent": schema.measured(2.5, "%", "/proc/stat"),
                    "vram_peak_gib": schema.measured(0.17, "GiB", "amdgpu sysfs"),
                },
            },
            {
                "id": "load",
                "status": "ok",
                "metrics": {
                    "duration_s": schema.measured(96.5, "s", "client monotonic clock"),
                    "time_to_ready_s": schema.measured(94.2, "s", "client monotonic clock"),
                    "cpu_cores_avg": schema.unavailable("cpu_usec was not reported"),
                },
            },
        ],
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
                    "engine_prefill_tok_s": schema.measured(3100.4, "tokens/s", "engine log"),
                    "engine_decode_tok_s": schema.unavailable("server reports no timings"),
                    "draft_acceptance": schema.measured(0.62, "ratio", "engine log"),
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
                    "system_cpu_busy_percent": schema.measured(18.5, "%", "/proc/stat"),
                    "ram_used_peak_gib": schema.measured(53.2, "GiB", "/proc/meminfo"),
                    "ram_anon_peak_gib": schema.measured(49.0, "GiB", "cgroup memory.stat"),
                    "gtt_peak_gib": schema.measured(0.11, "GiB", "sysfs mem_info_gtt_used"),
                    "gpu_power_avg_w": schema.measured(264.2, "W", "sysfs hwmon"),
                    "swap_in_pages": schema.measured(0, "pages", "/proc/vmstat"),
                    "sample_count": schema.measured(139, "samples", "sampler"),
                    "sample_max_gap_s": schema.measured(0.5, "s", "sampler"),
                    "vram_peak_gib": schema.measured(15.1, "GiB", "sysfs mem_info_vram_used"),
                    "swap_out_pages": schema.unavailable("/proc/vmstat not readable"),
                },
            }
        ],
    }
