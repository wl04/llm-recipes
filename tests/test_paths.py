"""Data root entry point that shell entry points read and the VERSION stamp reader."""

import os
import subprocess
import sys
from pathlib import Path

import paths
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "paths.py"


@pytest.mark.subprocess
def test_entry_point_prints_the_data_home_for_shell_callers(tmp_path: Path) -> None:
    environment = {**os.environ, paths.DATA_HOME_ENV: str(tmp_path / "data")}

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        check=False,
        text=True,
        env=environment,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == str(tmp_path / "data")


@pytest.mark.parametrize("payload", ["[]", "null", "5", '"commit-hash"'])
def test_version_stamp_returns_none_when_file_is_not_a_json_object(
    tmp_path: Path, payload: str
) -> None:
    (tmp_path / "VERSION").write_text(payload)

    assert paths.version_stamp(tmp_path) is None
