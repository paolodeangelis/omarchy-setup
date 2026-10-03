from __future__ import annotations

import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from types import ModuleType
from pathlib import Path
from unittest.mock import patch

from omarchy_setup.modules.programs.winapps import (
    WINDOWS_IMAGE,
    WINAPPS_REVISION,
    WinAppsError,
    WinAppsInstaller,
    WinAppsPaths,
)


class WinAppsInstallerTests(unittest.TestCase):
    def paths(self, root: Path) -> WinAppsPaths:
        return WinAppsPaths(
            config_root=root / "config",
            state_root=root / "state",
            bin_root=root / "bin",
            data_root=root / "data",
            templates=Path(__file__).resolve().parents[2]
            / "programs"
            / "winapps"
            / "templates",
        )

    def seed_source(self, paths: WinAppsPaths) -> None:
        (paths.source / "bin").mkdir(parents=True)
        (paths.source / "bin" / "winapps").write_text("#!/bin/bash\n")
        (paths.source / "oem").mkdir()
        (paths.source / "oem" / "install.bat").write_text("rem fixture\n")
        (paths.source / ".git").mkdir()

    def test_prepare_is_idempotent_and_never_creates_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.paths(Path(directory))
            self.seed_source(paths)
            installer = WinAppsInstaller(paths)
            with (
                patch.object(installer, "_check_host"),
                patch.object(installer, "_git_head", return_value=WINAPPS_REVISION),
            ):
                installer.prepare()
                first = (paths.config_root / "compose.yaml").read_text()
                installer.prepare()
                self.assertTrue(installer.is_prepared())

            self.assertEqual((paths.config_root / "compose.yaml").read_text(), first)
            self.assertFalse((paths.config_root / "credentials.env").exists())
            self.assertEqual(
                (paths.bin_root / "winapps-clean-ghost").resolve(),
                paths.ghost_cleaner_source.resolve(),
            )
            self.assertEqual(
                (paths.config_root / "winapps.conf").stat().st_mode & 0o777,
                0o600,
            )
            metadata = (paths.state_root / "managed.json").read_text()
            self.assertIn(WINAPPS_REVISION, metadata)
            self.assertIn(WINDOWS_IMAGE, metadata)

    def test_existing_native_config_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.paths(Path(directory))
            self.seed_source(paths)
            paths.config_root.mkdir()
            compose = paths.config_root / "compose.yaml"
            compose.write_text("user configuration\n")
            installer = WinAppsInstaller(paths)
            with (
                patch.object(installer, "_check_host"),
                patch.object(installer, "_git_head", return_value=WINAPPS_REVISION),
            ):
                installer.prepare()
            self.assertEqual(compose.read_text(), "user configuration\n")

    def test_unreviewed_existing_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.paths(Path(directory))
            self.seed_source(paths)
            installer = WinAppsInstaller(paths)
            with self.assertRaisesRegex(WinAppsError, "unreviewed WinApps source"):
                with patch.object(installer, "_git_head", return_value="other"):
                    installer._prepare_source()

    def test_failed_source_download_leaves_no_partial_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.paths(Path(directory))
            installer = WinAppsInstaller(paths)
            with patch(
                "omarchy_setup.modules.programs.winapps.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, ("git", "clone")),
            ):
                with self.assertRaisesRegex(WinAppsError, "failed to prepare"):
                    installer._prepare_source()
            self.assertFalse(paths.source.exists())

    def test_templates_are_secret_free_and_syntactically_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.paths(Path(directory))
            compose = (paths.templates / "compose.yaml").read_text()
            credentials = (paths.templates / "credentials.env.example").read_text()
            self.assertIn(WINDOWS_IMAGE, compose)
            self.assertNotIn("PASSWORD:", compose)
            self.assertIn("replace-with-a-strong-local-password", credentials)
            syntax = subprocess.run(
                ("bash", "-n", str(paths.templates / "winapps.conf")),
                text=True,
                capture_output=True,
            )
            self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_ghost_cleaner_selects_only_tracked_marker_only_freerdp(self) -> None:
        script = (
            Path(__file__).resolve().parents[2]
            / "programs"
            / "winapps"
            / "bin"
            / "winapps-clean-ghost"
        )
        module = ModuleType("winapps_clean_ghost")
        SourceFileLoader("winapps_clean_ghost", str(script)).exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for pid, name, children in (
                (100, "podman", "101 102"),
                (101, "xfreerdp3", ""),
                (102, "xfreerdp3", ""),
                (200, "xfreerdp3", ""),
            ):
                process = root / str(pid)
                (process / "task" / str(pid)).mkdir(parents=True)
                (process / "comm").write_text(name + "\n")
                (process / "task" / str(pid) / "children").write_text(children)
                parent = {100: 1, 101: 100, 102: 100, 200: 1}[pid]
                (process / "status").write_text(f"Name:\t{name}\nPPid:\t{parent}\n")

            candidates = module.freerdp_candidates(root, {100})
            self.assertEqual(candidates, {101, 102})
            selected = module.marker_only_pids(
                candidates,
                [
                    {"pid": 101, "title": "", "size": [13, 13]},
                    {"pid": 102, "title": module.MARKER_TITLE, "size": [13, 13]},
                    {"pid": 102, "title": "Microsoft PowerPoint", "size": [900, 700]},
                    {"pid": 200, "title": module.MARKER_TITLE, "size": [13, 13]},
                ],
            )
            self.assertEqual(selected, {101})

    def test_ghost_cleaner_does_not_treat_arbitrary_empty_window_as_marker(self) -> None:
        script = (
            Path(__file__).resolve().parents[2]
            / "programs"
            / "winapps"
            / "bin"
            / "winapps-clean-ghost"
        )
        module = ModuleType("winapps_clean_ghost")
        SourceFileLoader("winapps_clean_ghost", str(script)).exec_module(module)

        self.assertFalse(module.is_marker({"title": "", "size": [800, 600]}))
        self.assertFalse(module.is_marker({"title": "", "size": [0, 0]}))

    def test_ghost_cleaner_script_has_valid_python_syntax(self) -> None:
        script = (
            Path(__file__).resolve().parents[2]
            / "programs"
            / "winapps"
            / "bin"
            / "winapps-clean-ghost"
        )
        compile(script.read_text(), str(script), "exec")


if __name__ == "__main__":
    unittest.main()
