import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
import upgrade_strata as upgrade


def test_candidate_reuses_worktree_and_preserves_local_edits(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=a@b",
            "-c",
            "user.name=T",
            "commit",
            "--allow-empty",
            "-qm",
            "initial",
        ],
        check=True,
    )
    candidate = upgrade.worktree(root, "v1.2.3")
    (candidate / "notes").write_text("keep")

    assert upgrade.worktree(root, "v1.2.3") == candidate
    assert (candidate / "notes").read_text() == "keep"
    assert not (root / "notes").exists()


def test_release_preflight_reports_missing_prepare_tool() -> None:
    with pytest.raises(ValueError, match=r"mtp_fetch\.py"):
        upgrade.inspect_source({}, "rev", "draft_vocab.bin")


@pytest.mark.parametrize("conflict", [False, True])
def test_existing_image_is_checked_by_id_only_when_lock_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conflict: bool
) -> None:
    image = "llm-recipes/strata-rdna4:v1.2.3"
    digest = "sha256:" + "f" * 64
    query = Mock(side_effect=[digest, json.dumps({"pin": "other" if conflict else "expected"})])
    run = Mock()
    monkeypatch.setattr(upgrade, "output", query)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(upgrade, "gpu_groups", list)
    monkeypatch.setattr(upgrade, "gpu_access_args", lambda groups: [])

    if conflict:
        with pytest.raises(ValueError, match="image_suffix"):
            upgrade.build_or_check(tmp_path, image, {"pin": "expected"}, 4)
        run.assert_not_called()
    else:
        upgrade.build_or_check(tmp_path, image, {"pin": "expected"}, 4)
        run.assert_called_once_with(["sudo", "docker", "run", "--rm", digest], check=True)
