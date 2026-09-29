from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omarchy_setup.modules.programs import PROGRAMS, OmarchyProgramBackend, ProgramError, ProgramPaths
from omarchy_setup.modules.programs.core import (
    MAMBA_BLOCK_END,
    MAMBA_BLOCK_START,
    _install_mamba_shell_block,
)


class ProgramBackendTests(unittest.TestCase):
    def test_mamba_shell_block_is_idempotent_and_disables_prompt_clobbering(self) -> None:
        with self.subTest("temporary startup file"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                paths = ProgramPaths(data_home=root / "data", shell_rc=root / ".bashrc")
                _install_mamba_shell_block(paths)
                first = paths.shell_rc.read_text()
                _install_mamba_shell_block(paths)

                self.assertEqual(paths.shell_rc.read_text(), first)
                self.assertIn(MAMBA_BLOCK_START, first)
                self.assertIn(MAMBA_BLOCK_END, first)
                self.assertIn("CONDA_CHANGEPS1=false", first)
                syntax = subprocess.run(
                    ("bash", "-n", str(paths.shell_rc)),
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_install_suppresses_omarchy_automatic_app_launch(self) -> None:
        backend = OmarchyProgramBackend()
        program = next(program for program in PROGRAMS if program.name == "spotify")

        def inspect_run(command, *, environment=None, capture=True):
            self.assertEqual(tuple(command), program.install_command)
            self.assertTrue(capture)
            launcher = Path(environment["PATH"].split(":", 1)[0]) / "uwsm-app"
            self.assertTrue(launcher.is_file())
            self.assertIn("exit 0", launcher.read_text())
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            paths = ProgramPaths(
                data_home=Path(directory) / "data",
                shell_rc=Path(directory) / ".bashrc",
            )
            with patch.object(backend, "_run", side_effect=inspect_run):
                backend.install(program, paths, quiet=True)

    def test_default_selection_is_verified(self) -> None:
        backend = OmarchyProgramBackend()
        program = next(program for program in PROGRAMS if program.name == "zen")
        results = (
            subprocess.CompletedProcess(program.default_command, 0, "", ""),
            subprocess.CompletedProcess(("omarchy", "default", "browser"), 0, "firefox\n", ""),
        )

        with patch.object(backend, "_run", side_effect=results):
            with self.assertRaisesRegex(ProgramError, "default could not be verified"):
                backend.set_default(program)


if __name__ == "__main__":
    unittest.main()
