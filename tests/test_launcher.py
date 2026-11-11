"""Contract checks for the host launcher; no Docker or GPU required."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import launch  # noqa: E402
import launcher  # noqa: E402

RECIPE = launcher.discover_recipes(ROOT / "recipes")["qwen3.8-27b-exl3-rx-9070-xt-16-gb-vram"]


class LauncherTests(unittest.TestCase):
    def test_stop_propagates_docker_invocation(self) -> None:
        with (
            patch.object(sys, "argv", ["launch.py", "stop", "exl3"]),
            patch("launch.run_command", return_value=0) as execute,
        ):
            launch.main()

        execute.assert_called_once_with(
            ["sudo", "docker", "stop", "llm-recipes-exl3"],
        )

    def test_logs_follows_console_when_requested(self) -> None:
        with (
            patch.object(sys, "argv", ["launch.py", "logs", "exl3", "--follow"]),
            patch("launch.run_command", return_value=0) as execute,
        ):
            launch.main()

        execute.assert_called_once_with(
            ["sudo", "docker", "logs", "--follow", "llm-recipes-exl3"],
        )

    def test_mount_rejects_delimiters_in_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "comma or newline"):
            launcher.mount(Path("/models,readonly"), "/models")

    def test_start_preserves_mount_boundaries_with_spaces(self) -> None:
        command = launcher.start_command(
            RECIPE,
            launcher.LaunchOptions(
                "coding", Path("/models with spaces"), Path("/logs"), 131072, "on", "on", 5001
            ),
            groups=[109],
            uid=1000,
            gid=1000,
        )
        self.assertIn("type=bind,src=/models with spaces,dst=/models,readonly", command)
        self.assertIn("type=bind,src=/logs,dst=/logs", command)
        self.assertIn("127.0.0.1:5001:5000", command)
        self.assertEqual(command[-6:], ["--draft", "on", "--vision", "on", "--context", "131072"])

    def test_start_rejects_invalid_context_before_execution(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/launch.py"),
                "start",
                RECIPE.name,
                "--context",
                "1025",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("multiple of 256", result.stderr)

    def test_start_dry_run_leaves_directories_absent_without_gpu(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            models = Path(folder) / "models"
            logs = Path(folder) / "logs"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/launch.py"),
                    "start",
                    RECIPE.name,
                    "--models",
                    str(models),
                    "--logs",
                    str(logs),
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("sudo docker run", result.stdout)
            self.assertFalse(models.exists())
            self.assertFalse(logs.exists())

    def test_start_rejects_unsupported_vision_before_execution(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/launch.py"),
                "start",
                RECIPE.name,
                "--vision",
                "cpu",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)

    def test_wrapper_preserves_options_outside_repository(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(RECIPE.directory / "scripts/serve.sh"),
                "--draft",
                "off",
                "--vision",
                "on",
                "--context",
                "131072",
                "--dry-run",
            ],
            cwd="/tmp",
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--draft off --vision on --context 131072", result.stdout)


if __name__ == "__main__":
    unittest.main()
