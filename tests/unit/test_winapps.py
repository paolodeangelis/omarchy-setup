from __future__ import annotations

import subprocess
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
