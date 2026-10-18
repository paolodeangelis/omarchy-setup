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
    ZEN_BINDING_END,
    ZEN_BINDING_START,
    _install_mamba_shell_block,
    _install_zen_binding,
    _remove_zen_binding,
)


class ProgramBackendTests(unittest.TestCase):
    @patch("omarchy_setup.modules.programs.core.subprocess.run")
    def test_package_preflight_is_noop_when_sync_database_is_available(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            ("pacman",), 0, "core acl 2.3.2-1\n", ""
        )
        backend = OmarchyProgramBackend()

        backend.prepare_system_packages()

        run.assert_called_once_with(
            ("pacman", "-Sl", "core"),
            text=True,
            capture_output=True,
        )

    @patch("omarchy_setup.modules.programs.core.subprocess.run")
    def test_package_preflight_refreshes_and_rechecks_missing_sync_database(self, run) -> None:
        run.side_effect = (
            subprocess.CompletedProcess(("pacman",), 1, "", ""),
            subprocess.CompletedProcess(("sudo", "pacman"), 0, "", ""),
            subprocess.CompletedProcess(("pacman",), 0, "core acl 2.3.2-1\n", ""),
        )
        backend = OmarchyProgramBackend()

        backend.prepare_system_packages()

        self.assertEqual(
            run.call_args_list[1].args[0],
            ("sudo", "pacman", "-Sy", "--noconfirm"),
        )

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

    def test_zen_binding_is_idempotent_preserves_user_content_and_is_removable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = ProgramPaths(
                data_home=root / "data",
                shell_rc=root / ".bashrc",
                config_home=root / "config",
            )
            bindings = root / "config" / "hypr" / "bindings.lua"
            bindings.parent.mkdir(parents=True)
            bindings.write_text('-- personal\no.bind("SUPER + R", "Run", "wofi")\n')

            _install_zen_binding(paths)
            first = bindings.read_text()
            _install_zen_binding(paths)

            self.assertEqual(bindings.read_text(), first)
            self.assertIn('-- personal', first)
            self.assertIn(ZEN_BINDING_START, first)
            self.assertIn('hl.unbind("SUPER + SHIFT + B")', first)
            self.assertIn('zen-browser --blank-window about:newtab', first)

            _remove_zen_binding(paths)
            restored = bindings.read_text()
            self.assertIn('-- personal', restored)
            self.assertNotIn(ZEN_BINDING_START, restored)
            self.assertNotIn(ZEN_BINDING_END, restored)

    def test_zen_uninstall_refuses_to_remove_active_default_browser(self) -> None:
        backend = OmarchyProgramBackend()
        program = next(program for program in PROGRAMS if program.name == "zen")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = ProgramPaths(data_home=root / "data", shell_rc=root / ".bashrc")
            with patch.object(
                backend,
                "_run",
                return_value=subprocess.CompletedProcess(
                    ("omarchy", "default", "browser"), 0, "zen\n", ""
                ),
            ):
                with self.assertRaisesRegex(ProgramError, "default browser"):
                    backend.uninstall(program, paths, quiet=True)

    @patch("omarchy_setup.modules.programs.core.subprocess.run")
    def test_package_uninstall_removes_only_declared_installed_packages(self, run) -> None:
        backend = OmarchyProgramBackend()
        program = next(program for program in PROGRAMS if program.name == "spotify")
        paths = ProgramPaths(data_home=Path("/unused"), shell_rc=Path("/unused/.bashrc"))
        run.return_value = subprocess.CompletedProcess(("pacman",), 0, "spotify\n", "")

        with patch.object(backend, "_run") as backend_run:
            backend.uninstall(program, paths, quiet=True)

        backend_run.assert_called_once_with(
            ("sudo", "pacman", "-Rns", "--noconfirm", "--", "spotify"),
            capture=True,
        )

    def test_webapp_uninstall_uses_supported_omarchy_command(self) -> None:
        backend = OmarchyProgramBackend()
        program = next(program for program in PROGRAMS if program.name == "outlook")
        paths = ProgramPaths(data_home=Path("/unused"), shell_rc=Path("/unused/.bashrc"))

        with patch.object(backend, "_run") as backend_run:
            backend.uninstall(program, paths, quiet=False)

        backend_run.assert_called_once_with(
            ("omarchy", "webapp", "remove", "Outlook"), capture=False
        )

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

    def test_outlook_uses_supported_webapp_installer_and_launcher(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "outlook")

        self.assertEqual(program.desktop_file, "Outlook.desktop")
        self.assertEqual(program.install_command, (
            "omarchy", "webapp", "install", "Outlook",
            "https://outlook.office.com/mail/", "application-msoutlook",
        ))
        self.assertEqual(program.login_command, (
            "omarchy", "launch", "webapp", "https://outlook.office.com/mail/",
        ))

    def test_zoom_uses_native_package_and_web_fallback_is_separate(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "zoom")
        web = next(program for program in PROGRAMS if program.name == "zoom-web")

        self.assertEqual(program.desktop_file, "Zoom.desktop")
        self.assertEqual(program.packages, ("zoom",))
        self.assertEqual(
            program.install_command, ("omarchy", "pkg", "aur", "add", "zoom")
        )
        self.assertEqual(program.login_command, ("uwsm-app", "--", "zoom"))
        self.assertEqual(program.kind, "zoom-native")

        self.assertFalse(web.include_in_all)
        self.assertEqual(web.desktop_file, "Zoom Web.desktop")
        self.assertEqual(web.install_command, (
            "omarchy", "webapp", "install", "Zoom Web",
            "https://app.zoom.us/wc/home", "zoom",
            "omarchy-webapp-handler-zoom %u",
            "x-scheme-handler/zoommtg;x-scheme-handler/zoomus",
        ))
        self.assertEqual(web.login_command, (
            "omarchy", "launch", "webapp", "https://app.zoom.us/wc/home",
        ))

    def test_native_zoom_preserves_web_launcher_and_becomes_protocol_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system = root / "system-applications"
            data = root / "data"
            applications = data / "applications"
            system.mkdir()
            applications.mkdir(parents=True)
            native = system / "Zoom.desktop"
            native.write_text(
                "[Desktop Entry]\nName=Zoom\nExec=/usr/bin/zoom %U\n"
                "MimeType=x-scheme-handler/zoommtg;x-scheme-handler/zoomus\n"
            )
            stock_web = applications / "Zoom.desktop"
            stock_web.write_text(
                "[Desktop Entry]\nName=Zoom\n"
                "Exec=omarchy-webapp-handler-zoom %u\n"
            )
            paths = ProgramPaths(data_home=data, shell_rc=root / ".bashrc")
            backend = OmarchyProgramBackend(system_applications=system)
            responses = (
                subprocess.CompletedProcess(("update-desktop-database",), 0, "", ""),
                subprocess.CompletedProcess(("xdg-mime", "default"), 0, "", ""),
                subprocess.CompletedProcess(("xdg-mime", "query"), 0, "Zoom.desktop\n", ""),
                subprocess.CompletedProcess(("xdg-mime", "default"), 0, "", ""),
                subprocess.CompletedProcess(("xdg-mime", "query"), 0, "Zoom.desktop\n", ""),
            )

            with patch.object(backend, "_run", side_effect=responses):
                backend._configure_zoom_native(paths)

            self.assertEqual((applications / "Zoom.desktop").read_text(), native.read_text())
            web_contents = (applications / "Zoom Web.desktop").read_text()
            self.assertIn("Name=Zoom Web", web_contents)
            self.assertIn("omarchy-webapp-handler-zoom", web_contents)

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
