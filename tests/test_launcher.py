"""Contract checks for the host launcher; no Docker or GPU required."""

import contextlib
import io
import json
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
        self.assertEqual(
            command[-8:],
            ["--draft", "on", "--vision", "on", "--context", "131072", "--recipe", "/recipe"],
        )

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

    def test_instances_command_emits_machine_readable_fields(self) -> None:
        command = launcher.instances_command()

        format_argument = command[command.index("--format") + 1]

        self.assertNotIn("table ", format_argument)
        self.assertIn('{{.Label "io.llm-recipes.instance"}}', format_argument)

    def test_parse_instances_reads_tab_separated_records(self) -> None:
        output = (
            "alpha\texl3\tUp 2 minutes\t0.0.0.0:5000->5000/tcp\n"
            "beta\tstrata\tUp 9 seconds\t\n"
            "\n"
        )

        records = launcher.parse_instances(output)

        self.assertEqual(
            records[0],
            {
                "instance": "alpha",
                "recipe": "exl3",
                "status": "Up 2 minutes",
                "ports": "0.0.0.0:5000->5000/tcp",
            },
        )
        self.assertEqual(records[1]["ports"], "")

    def test_parse_instances_rejects_malformed_line(self) -> None:
        with self.assertRaises(ValueError):
            launcher.parse_instances("alpha\texl3\n")

    def test_list_json_emits_recipe_records(self) -> None:
        buffer = io.StringIO()
        with (
            patch.object(sys, "argv", ["launch.py", "list", "--json"]),
            patch("launch.discover_recipes", return_value={RECIPE.name: RECIPE}),
            contextlib.redirect_stdout(buffer),
        ):
            code = launch.main()

        data = json.loads(buffer.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(data[0]["name"], RECIPE.name)
        self.assertEqual(data[0]["port"], RECIPE.port)

    def test_ps_json_parses_instance_listing(self) -> None:
        completed = subprocess.CompletedProcess(
            launcher.instances_command(),
            0,
            "alpha\texl3\tUp 2 minutes\t0.0.0.0:5000->5000/tcp\n",
            "",
        )
        buffer = io.StringIO()
        with (
            patch.object(sys, "argv", ["launch.py", "ps", "--json"]),
            patch("launch.capture", return_value=completed),
            contextlib.redirect_stdout(buffer),
        ):
            code = launch.main()

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buffer.getvalue())[0]["instance"], "alpha")

    def test_status_json_reports_missing_instances_as_not_found(self) -> None:
        completed = subprocess.CompletedProcess(
            launcher.lifecycle_command("status", "gone"), 1, "", "Error: No such object"
        )
        buffer = io.StringIO()
        with (
            patch.object(sys, "argv", ["launch.py", "status", "gone", "--json"]),
            patch("launch.capture", return_value=completed),
            contextlib.redirect_stdout(buffer),
        ):
            code = launch.main()

        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(buffer.getvalue()), {"instance": "gone", "status": "not-found"}
        )


if __name__ == "__main__":
    unittest.main()
