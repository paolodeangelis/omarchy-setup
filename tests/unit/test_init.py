from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omarchy_setup.cli import main
from omarchy_setup.modules.init import InitError, InitPaths, run_init


class FakeBackend:
    def __init__(self) -> None:
        self.uv_installs = 0
        self.environment_builds = 0

    def uv_is_current(self, uv_path: Path) -> bool:
        return uv_path.is_file()

    def install_uv(self, uv_path: Path) -> None:
        self.uv_installs += 1
        uv_path.parent.mkdir(parents=True, exist_ok=True)
        uv_path.write_text("fake uv\n")
        uv_path.chmod(0o755)

    def build_environment(self, paths: InitPaths, destination: Path) -> None:
        self.environment_builds += 1
        command = destination / "bin" / "omarchy-setup"
        command.parent.mkdir(parents=True)
        command.write_text("#!/bin/sh\necho 'omarchy-setup 0.1.0'\n")
        command.chmod(0o755)

    def verify_environment(self, environment: Path) -> None:
        command = environment / "bin" / "omarchy-setup"
        if not command.is_file() or not os.access(command, os.X_OK):
            raise InitError("fake environment verification failed")


class FailingBackend(FakeBackend):
    def build_environment(self, paths: InitPaths, destination: Path) -> None:
        super().build_environment(paths, destination)
        raise InitError("simulated build failure")


class InitTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        repo = root / "repo"
        (repo / "src" / "example").mkdir(parents=True)
        (repo / "src" / "example" / "module.py").write_text("VALUE = 1\n")
        (repo / "pyproject.toml").write_text("[project]\nname='example'\nversion='1'\n")
        (repo / "uv.lock").write_text("version = 1\n")
        (repo / "omarchy-setup").write_text("#!/bin/sh\n")
        self.paths = InitPaths(
            repo_root=repo,
            state_root=root / "state" / "omarchy-setup",
            bin_dir=root / "bin",
        )

    def execute(self, backend: FakeBackend, *, dry_run: bool = False) -> tuple[int, str]:
        output = io.StringIO()
        result = run_init(
            self.paths,
            backend=backend,
            assume_yes=True,
            dry_run=dry_run,
            quiet=False,
            stdin=io.StringIO(""),
            stdout=output,
        )
        return result, output.getvalue()

    def test_initializes_environment_and_launcher(self) -> None:
        backend = FakeBackend()

        result, output = self.execute(backend)

        self.assertEqual(result, 0)
        self.assertEqual(backend.uv_installs, 1)
        self.assertEqual(backend.environment_builds, 1)
        self.assertTrue(self.paths.environment.is_dir())
        self.assertEqual(self.paths.launcher.resolve(), self.paths.source_launcher.resolve())
        self.assertIn("Ready. Run:", output)

    def test_second_init_is_idempotent(self) -> None:
        backend = FakeBackend()
        self.execute(backend)

        result, output = self.execute(backend)

        self.assertEqual(result, 0)
        self.assertEqual(backend.uv_installs, 1)
        self.assertEqual(backend.environment_builds, 1)
        self.assertIn("already initialized", output)

    def test_dry_run_writes_nothing(self) -> None:
        backend = FakeBackend()

        result, output = self.execute(backend, dry_run=True)

        self.assertEqual(result, 0)
        self.assertEqual(backend.uv_installs, 0)
        self.assertEqual(backend.environment_builds, 0)
        self.assertFalse(self.paths.state_root.exists())
        self.assertIn("Dry run complete", output)

    def test_cli_init_does_not_forward_install_only_state(self) -> None:
        output = io.StringIO()
        with patch("omarchy_setup.cli.InitPaths.for_user", return_value=self.paths):
            result = main(
                ["init", "-y", "--dry-run", "--no-progress"],
                backend=FakeBackend(),
                stdin=io.StringIO(""),
                stdout=output,
            )

        self.assertEqual(result, 0)
        self.assertIn("Dry run complete", output.getvalue())

    def test_refuses_unrelated_launcher_before_changes(self) -> None:
        self.paths.bin_dir.mkdir(parents=True)
        self.paths.launcher.write_text("unrelated\n")
        backend = FakeBackend()

        with self.assertRaisesRegex(InitError, "unrelated launcher"):
            self.execute(backend)

        self.assertEqual(backend.uv_installs, 0)
        self.assertEqual(backend.environment_builds, 0)

    def test_failed_update_preserves_active_environment(self) -> None:
        initial_backend = FakeBackend()
        self.execute(initial_backend)
        active_command = self.paths.environment / "bin" / "omarchy-setup"
        original = active_command.read_text()
        (self.paths.repo_root / "src" / "example" / "module.py").write_text("VALUE = 2\n")

        with self.assertRaisesRegex(InitError, "simulated build failure"):
            self.execute(FailingBackend())

        self.assertEqual(active_command.read_text(), original)
        self.assertEqual(len(list(self.paths.environments.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
