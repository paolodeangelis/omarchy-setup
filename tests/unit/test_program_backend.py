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
    ZEN_PREF_START,
    _install_mamba_shell_block,
    _install_zen_binding,
    _install_zen_profile_config,
    _remove_zen_binding,
    _remove_zen_profile_config,
    _install_thunderbird_binding,
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
            ("omarchy", "update", "-y"),
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
            profile = root / "config" / "zen" / "profile.default"
            profile.mkdir(parents=True)
            (profile.parent / "profiles.ini").write_text(
                "[InstallABC]\nDefault=profile.default\nLocked=1\n"
            )
            (profile / "user.js").write_text("// personal\n")

            _install_zen_binding(paths)
            _install_zen_profile_config(paths)
            first = bindings.read_text()
            _install_zen_binding(paths)
            _install_zen_profile_config(paths)

            self.assertEqual(bindings.read_text(), first)
            self.assertIn('-- personal', first)
            self.assertIn(ZEN_BINDING_START, first)
            self.assertIn('hl.unbind("SUPER + SHIFT + B")', first)
            self.assertIn('zen-browser --new-window about:newtab', first)
            self.assertIn(ZEN_PREF_START, (profile / "user.js").read_text())
            self.assertIn(
                'user_pref("zen.window-sync.enabled", false);',
                (profile / "user.js").read_text(),
            )

            _remove_zen_binding(paths)
            _remove_zen_profile_config(paths)
            restored = bindings.read_text()
            self.assertIn('-- personal', restored)
            self.assertNotIn(ZEN_BINDING_START, restored)
            self.assertNotIn(ZEN_BINDING_END, restored)
            self.assertEqual((profile / "user.js").read_text(), "// personal\n")

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

    @patch("omarchy_setup.modules.programs.core.shutil.which", return_value=None)
    def test_bluebubbles_requires_existing_flatpak(self, _which) -> None:
        backend = OmarchyProgramBackend()
        program = next(program for program in PROGRAMS if program.name == "bluebubbles")
        paths = ProgramPaths(data_home=Path("/unused"), shell_rc=Path("/unused/.bashrc"))

        with self.assertRaisesRegex(ProgramError, "requires Flatpak"):
            backend.is_installed(program, paths)

    @patch("omarchy_setup.modules.programs.core.shutil.which", return_value="/usr/bin/flatpak")
    @patch("omarchy_setup.modules.programs.core.subprocess.run")
    def test_bluebubbles_is_detected_through_flatpak(self, run, _which) -> None:
        backend = OmarchyProgramBackend()
        program = next(program for program in PROGRAMS if program.name == "bluebubbles")
        paths = ProgramPaths(data_home=Path("/unused"), shell_rc=Path("/unused/.bashrc"))
        run.return_value = subprocess.CompletedProcess(("flatpak", "info"), 0, "", "")

        self.assertTrue(backend.is_installed(program, paths))
        run.assert_called_once_with(
            ("flatpak", "info", "app.bluebubbles.BlueBubbles"),
            text=True,
            capture_output=True,
        )

    def test_bluebubbles_registry_uses_flathub_and_preserves_data_on_uninstall(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "bluebubbles")

        self.assertEqual(program.flatpak_id, "app.bluebubbles.BlueBubbles")
        self.assertEqual(program.install_command, (
            "flatpak", "install", "--noninteractive", "flathub",
            "app.bluebubbles.BlueBubbles",
        ))
        self.assertEqual(program.uninstall_command, (
            "flatpak", "uninstall", "--noninteractive",
            "app.bluebubbles.BlueBubbles",
        ))
        self.assertNotIn("--delete-data", program.uninstall_command)

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

    def test_1password_uses_supported_service_installer_and_login(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "1password")

        self.assertEqual(program.packages, ("1password", "1password-cli"))
        self.assertEqual(
            program.install_command,
            ("omarchy", "install", "service", "1password"),
        )
        self.assertEqual(
            program.login_command,
            ("omarchy", "launch", "1password"),
        )

    def test_proton_vpn_uses_official_cli_package_and_interactive_login(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "proton-vpn")

        self.assertEqual(program.packages, ("proton-vpn-cli",))
        self.assertEqual(
            program.install_command,
            ("omarchy", "pkg", "add", "proton-vpn-cli"),
        )
        self.assertEqual(program.login_command[0], "omarchy-launch-floating-terminal-with-presentation")
        self.assertIn("protonvpn signin", program.login_command[1])
        self.assertIn("Proton sign-in failed; review the error above", program.login_command[1])

    def test_proton_vpn_login_keeps_cli_failure_visible(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "proton-vpn")
        with tempfile.TemporaryDirectory() as directory:
            protonvpn = Path(directory) / "protonvpn"
            protonvpn.write_text("#!/bin/sh\nexit 7\n")
            protonvpn.chmod(0o755)
            result = subprocess.run(
                ("bash", "-c", program.login_command[1]),
                input="person\nx",
                text=True,
                capture_output=True,
                env={"PATH": f"{directory}:/usr/bin"},
            )

        self.assertEqual(result.returncode, 7)
        self.assertIn("Proton sign-in failed; review the error above", result.stdout)

    def test_libreoffice_installs_language_tools(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "libreoffice")

        self.assertEqual(
            program.packages,
            ("libreoffice-fresh", "hunspell-en_us", "hunspell-it", "hyphen-en"),
        )
        self.assertEqual(
            program.install_command,
            (
                "omarchy", "pkg", "add",
                "libreoffice-fresh", "hunspell-en_us", "hunspell-it", "hyphen-en",
            ),
        )

    def test_onlyoffice_uses_current_aur_desktop_package(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "onlyoffice")

        self.assertEqual(program.packages, ("onlyoffice-bin",))
        self.assertEqual(
            program.install_command,
            ("omarchy", "pkg", "aur", "add", "onlyoffice-bin"),
        )
        self.assertIsNone(program.login_command)

    def test_zotero_uses_aur_binary_and_opens_account_onboarding(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "zotero")

        self.assertEqual(program.packages, ("zotero-bin",))
        self.assertEqual(
            program.install_command,
            ("omarchy", "pkg", "aur", "add", "zotero-bin"),
        )
        self.assertEqual(program.login_command, ("uwsm-app", "--", "zotero"))

    def test_thunderbird_installs_language_packs_and_opens_onboarding(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "thunderbird")

        self.assertEqual(
            program.packages,
            ("thunderbird", "thunderbird-i18n-en-us", "thunderbird-i18n-it"),
        )
        self.assertEqual(program.login_command, ("uwsm-app", "--", "thunderbird"))
        self.assertEqual(program.kind, "thunderbird")
        self.assertEqual(
            program.default_command,
            ("xdg-mime", "default", "org.mozilla.Thunderbird.desktop", "x-scheme-handler/mailto"),
        )

    def test_telegram_login_uses_the_arch_package_executable(self) -> None:
        program = next(program for program in PROGRAMS if program.name == "telegram")

        self.assertEqual(program.login_command, ("uwsm-app", "--", "Telegram"))

    def test_thunderbird_binding_replaces_managed_omamail_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = ProgramPaths(
                data_home=root / "data", shell_rc=root / ".bashrc",
                config_home=root / "config",
            )
            bindings = root / "config" / "hypr" / "bindings.lua"
            bindings.parent.mkdir(parents=True)
            bindings.write_text(
                '-- personal\n-- >>> omarchy-setup mail\nold\n-- <<< omarchy-setup mail\n'
            )
            _install_thunderbird_binding(paths)
            contents = bindings.read_text()
            self.assertIn("-- personal", contents)
            self.assertNotIn("\nold\n", contents)
            self.assertIn("uwsm-app -- thunderbird -compose", contents)

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
