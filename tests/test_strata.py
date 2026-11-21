"""CPU-only checks for the Strata launch adapter and source verification."""

import importlib.util
import json
import os
import select
import signal
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

RECIPE = (
    Path(__file__).resolve().parents[1]
    / "recipes"
    / "qwen3.8-flash-next-gguf-ista-iq3-xxs-rx-9070-xt-16-gb-vram"
)

RUNTIME = Path(__file__).resolve().parents[1] / "runtimes/strata"
UNSLOTH = RECIPE.with_name("qwen3.8-flash-next-gguf-unsloth-ud-iq3-xxs-rx-9070-xt-16-gb-vram")


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(RUNTIME / "scripts"))

serve = load_module("strata_serve", RUNTIME / "scripts/serve.py")


@pytest.fixture
def strata_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    recipe = tmp_path / "recipe"
    config = recipe / "config"
    config.mkdir(parents=True)
    models = tmp_path / "mounted-models"
    prepared = models / "recipes" / recipe.name
    shards = prepared / "models"
    shards.mkdir(parents=True)
    for artifact in ("model.gguf", "ple.gguf", "expert.bin"):
        (shards / artifact).write_bytes(b"x")
    (shards / "tokenizer.json").write_text("{}")
    (config / "launch.json").write_text('{"runtime":"strata"}')
    (config / "strata.json").write_text(
        json.dumps(
            {
                "args": [
                    "--native",
                    str(shards / "model.gguf"),
                    "--ple-gguf",
                    str(shards / "ple.gguf"),
                    "--expert-profile",
                    str(shards / "expert.bin"),
                    "--max-context",
                    "131072",
                    "--kv-resident",
                    "32768",
                ],
                "port": 8080,
                "tokenizer": str(shards),
            }
        )
    )
    lock = {"files": [{"path": "model.gguf", "size_bytes": 1}]}
    (config / "models.lock.json").write_text(json.dumps(lock))
    runtime = tmp_path / "runtime"
    (runtime / "container").mkdir(parents=True)
    image = {"image": "locked"}
    (runtime / "container/versions.lock.json").write_text(json.dumps(image))
    image_lock = tmp_path / "image.lock.json"
    image_lock.write_text(json.dumps(image))
    receipt = prepared / "prepared.json"
    receipt.write_text(json.dumps({"models": lock, "image": image}))
    container_paths = {"/opt/build/versions.lock.json": image_lock, "/models": models}
    monkeypatch.setattr(serve, "Path", lambda path: container_paths.get(path, Path(path)))
    monkeypatch.setattr(serve, "RUNTIME", runtime)
    monkeypatch.setattr(sys, "argv", ["serve.py", "--recipe", str(recipe), "--context", "4096"])
    return image_lock, receipt


def test_serve_passes_validated_settings_to_engine_when_preparation_matches(
    strata_startup: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serve.subprocess, "check_output", lambda *args, **kwargs: '{"device":2}')

    def launch(command: list[str], log: Path, environment: dict[str, str]) -> int:
        config = json.loads(Path(command[command.index("--config") + 1]).read_text())
        assert command[:5] == [sys.executable, "-m", "serve.server", "--engine", "strata"]
        assert command[command.index("--port") + 1] == "8080"
        assert config["args"][config["args"].index("--max-context") + 1] == "4096"
        assert environment["HIP_VISIBLE_DEVICES"] == "2"
        assert log == Path("/logs/server.log")
        return 7

    monkeypatch.setattr(serve, "run_logged", launch)

    assert serve.main() == 7


@pytest.mark.parametrize(
    ("mismatch", "message"),
    [("image", "Image lock differs"), ("receipt", "Prepared model lock differs")],
)
def test_serve_refuses_startup_when_preparation_is_stale(
    strata_startup: tuple[Path, Path],
    mismatch: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    image_lock, receipt = strata_startup
    (image_lock if mismatch == "image" else receipt).write_text("{}")
    probe = Mock(side_effect=AssertionError("Unexpected GPU probe"))
    launch = Mock(side_effect=AssertionError("Unexpected engine launch"))
    monkeypatch.setattr(serve, "probe_device", probe)
    monkeypatch.setattr(serve, "run_logged", launch)

    result = serve.main()

    assert result == 1
    assert message in capsys.readouterr().err
    probe.assert_not_called()
    launch.assert_not_called()


@pytest.mark.parametrize("manifest", ["[]", "null"])
def test_serve_reports_invalid_manifest_when_launch_json_is_not_an_object(
    manifest: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "launch.json").write_text(manifest)
    monkeypatch.setattr(sys, "argv", ["serve.py", "--recipe", str(tmp_path)])

    result = serve.main()

    assert result == 1
    assert "launch.json must contain a JSON object" in capsys.readouterr().err


def test_serve_names_manifest_when_launch_json_has_invalid_syntax(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "launch.json").write_text("{")
    monkeypatch.setattr(sys, "argv", ["serve.py", "--recipe", str(tmp_path)])

    result = serve.main()

    assert result == 1
    assert "launch.json: invalid JSON" in capsys.readouterr().err


@pytest.mark.parametrize("output", ["[]", "{}", '{"device":true}', '{"device":-1}', "{"])
def test_probe_device_rejects_invalid_hip_probe_output(
    output: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serve.subprocess, "check_output", lambda *args, **kwargs: output)

    with pytest.raises(ValueError, match="check_hip"):
        serve.probe_device()


def test_probe_device_returns_visibility_string_when_index_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(serve.subprocess, "check_output", lambda *args, **kwargs: '{"device":0}')

    result = serve.probe_device()

    assert result == "0"


def test_configure_disables_optional_models_without_mutating_defaults() -> None:
    original = json.loads((RECIPE / "config/strata.json").read_text())

    result = serve.configure(original, 4096, "off", "off")

    assert "--vision" not in result["args"]
    assert "vision" not in result
    assert "--mtp" not in result["args"]
    assert result["args"][result["args"].index("--spec") + 1] == "0"
    assert result["args"][result["args"].index("--kv-resident") + 1] == "4096"
    assert "vision" in original
    assert "--mtp" in original["args"]


def test_configure_preserves_cpu_vision_and_resident_cap_for_long_context() -> None:
    original = json.loads((RECIPE / "config/strata.json").read_text())

    result = serve.configure(original, 131072, "on", "cpu")

    assert result["args"].count("--vision") == 1
    assert result["vision"]["gpu"] is False
    assert result["args"][result["args"].index("--kv-resident") + 1] == "32768"
    assert result["args"][result["args"].index("--spec") + 1] == "4"


@pytest.mark.parametrize(
    ("context", "draft", "vision", "message"),
    [
        (1025, "on", "cpu", "multiple of 256"),
        (4096, "on", "on", "vision must be cpu/off"),
    ],
)
def test_configure_rejects_invalid_options(
    context: int, draft: str, vision: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        serve.configure({}, context, draft, vision)


def test_validate_files_reports_missing_artifacts(tmp_path: Path) -> None:
    config = {
        "args": [
            "--native",
            str(tmp_path / "missing.gguf"),
            "--ple-gguf",
            str(tmp_path / "second.gguf"),
            "--expert-profile",
            str(tmp_path / "profile.bin"),
        ],
        "tokenizer": str(tmp_path),
    }

    with pytest.raises(ValueError, match=r"missing\.gguf"):
        serve.validate_files(config)


def test_run_logged_preserves_output_and_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "server.log"
    command = [sys.executable, "-c", "print('API started'); raise SystemExit(7)"]

    result = serve.run_logged(command, log, dict(os.environ))

    assert result == 7
    assert "API started" in capsys.readouterr().out
    assert log.read_text() == "API started\n"


def test_run_logged_forwards_sigterm_and_reaps_child_when_stopped(tmp_path: Path) -> None:
    child = """
import signal
import sys
signal.signal(signal.SIGTERM, lambda *_: sys.exit(23))
print('ready', flush=True)
while True:
    signal.pause()
"""
    wrapper = """
import os
import sys
from pathlib import Path
from serve import run_logged
raise SystemExit(
    run_logged([sys.executable, '-c', sys.argv[2]], Path(sys.argv[1]), dict(os.environ))
)
"""
    log = tmp_path / "server.log"
    with subprocess.Popen(
        [sys.executable, "-c", wrapper, str(log), child],
        cwd=RUNTIME / "scripts",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            assert process.stdout is not None
            ready, _, _ = select.select([process.stdout], [], [], 5)
            assert ready, "Child did not report readiness"
            assert process.stdout.readline().strip() == "ready"

            process.send_signal(signal.SIGTERM)

            process.communicate(timeout=5)
            assert process.returncode == 23
        except BaseException:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            raise
    assert log.read_text() == "ready\n"


def test_recipe_paths_keeps_model_data_separate() -> None:
    recipe_paths = load_module("paths_test", RUNTIME / "scripts/recipe_config.py").recipe_paths
    assert recipe_paths(RECIPE) == (RECIPE / "config", Path("recipes") / RECIPE.name)
    assert recipe_paths(UNSLOTH) == (UNSLOTH / "config", Path("recipes") / UNSLOTH.name)


def test_validate_model_files_rejects_missing_middle_shard(tmp_path: Path) -> None:
    files = [{"path": f"model-{i:05d}-of-00004.gguf", "size_bytes": 1} for i in range(1, 5)]
    (tmp_path / "models").mkdir()
    for item in files:
        if item["path"] != "model-00002-of-00004.gguf":
            (tmp_path / "models" / str(item["path"])).write_bytes(b"x")
    with pytest.raises(ValueError, match="00002"):
        serve.validate_model_files(tmp_path, {"files": files})


@pytest.mark.parametrize(
    ("mode", "context", "resident"), [("on", 131072, "32768"), ("off", 4096, "4096")]
)
def test_configure_sets_native_drafting_and_kv_override_for_modern_engine(
    mode: str, context: int, resident: str
) -> None:
    original = json.loads((RECIPE / "config/strata.json").read_text())
    original["user_args"] = ["--kv-resident", "512"]

    config = serve.configure(original, context, mode, "cpu", modern=True)

    assert config["drafting"] == ("mtp" if mode == "on" else "off")
    assert config["user_args"] == ["--kv-resident", resident]
    assert original["user_args"] == ["--kv-resident", "512"]
