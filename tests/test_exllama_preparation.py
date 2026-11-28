"""Check model download integrity without the Hub or model weights."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

RECIPE_SCRIPTS = Path(__file__).resolve().parents[1] / "runtimes" / "exllamav3-tabbyapi" / "scripts"

ARTIFACT = "model.safetensors"
PAYLOAD = b"tiny model fixture"
CHECKSUM = hashlib.sha256(PAYLOAD).hexdigest()


@pytest.fixture
def preparation(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(RECIPE_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "exllama_preparation", RECIPE_SCRIPTS / "prepare_models.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("action", "manifest", "message"),
    [
        ("download", "[]", "must contain a JSON object"),
        ("quantize-draft", "null", "must contain a JSON object"),
        ("download", "{\n  invalid", "invalid JSON at line 2"),
    ],
)
def test_cli_rejects_invalid_launch_manifest_before_preparing_models(
    tmp_path: Path,
    preparation: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
    manifest: str,
    message: str,
) -> None:
    recipe = tmp_path / "recipe"
    config = recipe / "config"
    config.mkdir(parents=True)
    launch = config / "launch.json"
    launch.write_text(manifest)
    models = tmp_path / "models"
    monkeypatch.setattr(
        sys, "argv", ["prepare_models.py", "--recipe", str(recipe), "--models", str(models), action]
    )

    with pytest.raises(SystemExit) as error:
        preparation.cli()

    assert error.value.code == 2
    diagnostic = capsys.readouterr().err
    assert str(launch) in diagnostic
    assert message in diagnostic
    assert not models.exists()


@pytest.fixture
def model_spec() -> dict[str, str | list[str]]:
    return {
        "repo_id": "example/model",
        "revision": "locked",
        "directory": "model",
        "files": [ARTIFACT],
    }


@pytest.fixture
def hub(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    def unexpected_request(*args: object, **kwargs: object) -> None:
        pytest.fail("Unexpected remote request")

    module = ModuleType("huggingface_hub")
    module.__dict__.update(HfApi=unexpected_request, hf_hub_download=unexpected_request)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module


def stage_download(hub: ModuleType, *, checksum: str, revision: str = "locked") -> None:
    artifact = SimpleNamespace(
        rfilename=ARTIFACT, size=len(PAYLOAD), lfs=SimpleNamespace(sha256=checksum)
    )
    hub.__dict__["HfApi"] = lambda: SimpleNamespace(
        model_info=lambda *args, **kwargs: SimpleNamespace(sha=revision, siblings=[artifact])
    )

    def copy_artifact(repo_id: str, filename: str, *, revision: str, local_dir: Path) -> str:
        assert (repo_id, filename, revision) == ("example/model", ARTIFACT, "locked")
        path = local_dir / filename
        path.write_bytes(PAYLOAD)
        return str(path)

    hub.__dict__["hf_hub_download"] = copy_artifact


def test_download_publishes_receipt_when_artifact_matches_lock(
    tmp_path: Path,
    model_spec: dict[str, str | list[str]],
    preparation: ModuleType,
    hub: ModuleType,
) -> None:
    stage_download(hub, checksum=CHECKSUM)

    preparation.download(tmp_path, model_spec)

    destination = tmp_path / "model"
    assert (destination / ARTIFACT).read_bytes() == PAYLOAD
    assert json.loads((destination / "prepared.json").read_text()) == {
        "source": model_spec,
        "sha256": {ARTIFACT: CHECKSUM},
    }


def test_download_reuses_verified_artifact_without_contacting_hub(
    tmp_path: Path,
    model_spec: dict[str, str | list[str]],
    preparation: ModuleType,
    hub: ModuleType,
) -> None:
    destination = tmp_path / "model"
    destination.mkdir()
    (destination / "source.json").write_text(json.dumps(model_spec))
    (destination / ARTIFACT).write_bytes(PAYLOAD)
    receipt = json.dumps({"source": model_spec, "sha256": {ARTIFACT: CHECKSUM}})
    (destination / "prepared.json").write_text(receipt)

    preparation.download(tmp_path, model_spec)

    assert (destination / ARTIFACT).read_bytes() == PAYLOAD
    assert (destination / "prepared.json").read_text() == receipt


def test_download_rejects_unlocked_revision_without_publishing_receipt(
    tmp_path: Path,
    model_spec: dict[str, str | list[str]],
    preparation: ModuleType,
    hub: ModuleType,
) -> None:
    hub.__dict__["HfApi"] = lambda: SimpleNamespace(
        model_info=lambda *args, **kwargs: SimpleNamespace(sha="different")
    )

    with pytest.raises(RuntimeError, match="different model revision"):
        preparation.download(tmp_path, model_spec)

    assert not (tmp_path / "model/prepared.json").exists()


def test_download_rejects_corrupt_artifact_without_publishing_receipt(
    tmp_path: Path,
    model_spec: dict[str, str | list[str]],
    preparation: ModuleType,
    hub: ModuleType,
) -> None:
    stage_download(hub, checksum="0" * 64)

    with pytest.raises(RuntimeError, match="LFS checksum mismatch"):
        preparation.download(tmp_path, model_spec)

    assert not (tmp_path / "model/prepared.json").exists()


def test_local_upgrade_reuses_converted_draft_without_original_weights(
    tmp_path: Path, preparation: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = {"directory": "target", "files": ["config.json", ARTIFACT]}
    source = {"directory": "original", "files": ["config.json", ARTIFACT]}
    draft = {"directory": "converted", "work_directory": "work", "arguments": ["-b", "3.0"]}
    lock = {"target": target, "draft": source, "conversion": draft}
    old_build = {"torch_version": "old"}
    new_build = {"torch_version": "new"}
    donor = tmp_path / "prepared/v1.0.0/converted"
    for folder in (tmp_path / "target", donor):
        folder.mkdir(parents=True)
        (folder / "config.json").write_text("{}")
        (folder / ARTIFACT).write_bytes(PAYLOAD)
    sums = {"config.json": hashlib.sha256(b"{}").hexdigest(), ARTIFACT: CHECKSUM}
    (tmp_path / "target/prepared.json").write_text(json.dumps({"source": target, "sha256": sums}))
    old_receipt = {
        "source": source,
        "build": old_build,
        "arguments": ["-d", "0", "-b", "3.0"],
        "sha256": sums,
    }
    (donor / "prepared.json").write_text(json.dumps(old_receipt))
    monkeypatch.setattr(preparation, "quantize", lambda *args: pytest.fail("unexpected converter"))

    preparation.prepare_local(tmp_path, tmp_path / "prepared/v1.0.1", "v1.0.0", lock, new_build)

    output = tmp_path / "prepared/v1.0.1/converted"
    assert (output / ARTIFACT).samefile(donor / ARTIFACT)
    assert not (output / "config.json").samefile(donor / "config.json")
    new_receipt = json.loads((output / "prepared.json").read_text())
    assert new_receipt["build"] == new_build
    assert new_receipt["producer"] == old_build
    assert json.loads((donor / "prepared.json").read_text()) == old_receipt
    assert not (tmp_path / "original").exists()


def test_local_upgrade_rebuilds_only_draft_when_quantization_changes(
    tmp_path: Path, preparation: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = {"directory": "target", "files": ["config.json", ARTIFACT]}
    source = {"directory": "original", "files": ["config.json", ARTIFACT]}
    conversion = {"directory": "converted", "work_directory": "work", "arguments": ["-b", "4.0"]}
    lock = {"target": target, "draft": source, "conversion": conversion}
    manifest = {
        "source": source,
        "build": {"engine": "old"},
        "arguments": ["-b", "3.0"],
        "sha256": {"config.json": hashlib.sha256(b"{}").hexdigest(), ARTIFACT: CHECKSUM},
    }
    target_manifest = {"source": target, "sha256": manifest["sha256"]}
    donor = tmp_path / "prepared/v1.0.0/converted"
    for folder, receipt in ((tmp_path / "target", target_manifest), (donor, manifest)):
        folder.mkdir(parents=True)
        (folder / "config.json").write_text("{}")
        (folder / ARTIFACT).write_bytes(PAYLOAD)
        (folder / "prepared.json").write_text(json.dumps(receipt))
    build = {"engine": "new"}

    def quantize(root: Path, stage: Path, inputs: object, image: object) -> None:
        assert (root, inputs, image) == (tmp_path, lock, build)
        output = stage / "converted"
        output.mkdir()
        (output / "config.json").write_text("{}")
        (output / ARTIFACT).write_bytes(b"converted anew")
        checksums = {
            "config.json": hashlib.sha256(b"{}").hexdigest(),
            ARTIFACT: hashlib.sha256(b"converted anew").hexdigest(),
        }
        (output / "prepared.json").write_text(
            json.dumps(
                {
                    **manifest,
                    "build": build,
                    "arguments": conversion["arguments"],
                    "sha256": checksums,
                }
            )
        )

    monkeypatch.setattr(preparation, "quantize", quantize)

    preparation.prepare_local(tmp_path, tmp_path / "prepared/v1.0.1", "v1.0.0", lock, build)

    assert (tmp_path / "prepared/v1.0.1/converted" / ARTIFACT).read_bytes() == b"converted anew"
    assert (tmp_path / "target" / ARTIFACT).read_bytes() == PAYLOAD
    assert (donor / ARTIFACT).read_bytes() == PAYLOAD
