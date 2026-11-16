"""The host entry point that gives shell entry points the GPU access arguments."""

import gpu_access
import pytest


def test_main_prints_each_argument_on_its_own_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gpu_access, "gpu_groups", lambda: [989, 988, 989])

    assert gpu_access.main() == 0

    assert capsys.readouterr().out.splitlines() == [
        "--group-add",
        "988",
        "--group-add",
        "989",
        "--device=/dev/kfd",
        "--device=/dev/dri",
    ]


def test_main_fails_with_a_reason_when_devices_are_absent(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing_groups() -> list[int]:
        raise ValueError("AMD devices missing: /dev/kfd and /dev/dri/renderD* are required")

    monkeypatch.setattr(gpu_access, "gpu_groups", missing_groups)

    assert gpu_access.main() == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "AMD devices missing" in captured.err
