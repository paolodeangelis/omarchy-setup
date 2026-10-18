from __future__ import annotations

import io
import unittest
from pathlib import Path

from omarchy_setup.modules.programs import (
    Program,
    ProgramError,
    ProgramPaths,
    run_install,
    run_uninstall,
)


class FakeBackend:
    def __init__(
        self,
        installed: set[str] | None = None,
        *,
        fail_verification: str | None = None,
    ):
        self.installed = set(installed or ())
        self.fail_verification = fail_verification
        self.installs: list[str] = []
        self.package_preparations = 0
        self.defaults: list[str] = []
        self.logins: list[str] = []
        self.configured: list[str] = []
        self.uninstalls: list[str] = []

    def check_environment(self) -> str:
        return "4.0.4"

    def is_installed(self, program: Program, paths: ProgramPaths) -> bool:
        return program.name in self.installed

    def prepare_system_packages(self) -> None:
        self.package_preparations += 1

    def install(self, program: Program, paths: ProgramPaths, *, quiet: bool) -> None:
        self.installs.append(program.name)
        if program.name != self.fail_verification:
            self.installed.add(program.name)

    def configure(self, program: Program, paths: ProgramPaths) -> None:
        self.configured.append(program.name)

    def uninstall(self, program: Program, paths: ProgramPaths, *, quiet: bool) -> None:
        self.uninstalls.append(program.name)
        self.installed.discard(program.name)

    def set_default(self, program: Program) -> None:
        self.defaults.append(program.name)

    def launch_login(self, program: Program) -> None:
        self.logins.append(program.name)


class ProgramInstallWorkflowTests(unittest.TestCase):
    paths = ProgramPaths(data_home=Path("/unused"), shell_rc=Path("/unused/.bashrc"))

    def execute(
        self,
        selection: str,
        backend: FakeBackend,
        *,
        assume_yes: bool = True,
        login: bool = False,
        set_defaults: bool = False,
        dry_run: bool = False,
        install_only: bool = False,
    ) -> tuple[int, str]:
        output = io.StringIO()
        result = run_install(
            selection,
            paths=self.paths,
            backend=backend,
            assume_yes=assume_yes,
            login=login,
            set_defaults=set_defaults,
            dry_run=dry_run,
            quiet=False,
            stdin=io.StringIO(""),
            stdout=output,
            install_only=install_only,
        )
        return result, output.getvalue()

    def test_all_installs_every_missing_program_without_onboarding(self) -> None:
        backend = FakeBackend(installed={"whatsapp"})

        result, output = self.execute("all", backend)

        self.assertEqual(result, 0)
        self.assertEqual(
            backend.installs,
            [
                "mamba",
                "zen",
                "1password",
                "dropbox",
                "spotify",
                "outlook",
                "zoom",
                "telegram",
            ],
        )
        self.assertEqual(backend.defaults, [])
        self.assertEqual(backend.logins, [])
        self.assertEqual(backend.package_preparations, 1)
        self.assertIn("[3/12] Installing Mamba", output)

    def test_login_and_default_hooks_run_for_installed_program(self) -> None:
        backend = FakeBackend(installed={"zen"})

        self.execute("zen", backend, login=True, set_defaults=True)

        self.assertEqual(backend.installs, [])
        self.assertEqual(backend.package_preparations, 0)
        self.assertEqual(backend.defaults, ["zen"])
        self.assertEqual(backend.logins, ["zen"])

    def test_all_with_flags_runs_every_available_hook(self) -> None:
        backend = FakeBackend(
            installed={
                "zen",
                "mamba",
                "1password",
                "dropbox",
                "spotify",
                "outlook",
                "zoom",
                "whatsapp",
                "telegram",
            }
        )

        self.execute("all", backend, login=True, set_defaults=True)

        self.assertEqual(backend.defaults, ["zen"])
        self.assertEqual(
            backend.logins,
            [
                "zen",
                "1password",
                "dropbox",
                "spotify",
                "outlook",
                "zoom",
                "whatsapp",
                "telegram",
            ],
        )

    def test_outlook_webapp_installs_without_package_preparation_and_opens_login(self) -> None:
        backend = FakeBackend()

        self.execute("outlook", backend, login=True)

        self.assertEqual(backend.installs, ["outlook"])
        self.assertEqual(backend.package_preparations, 0)
        self.assertEqual(backend.logins, ["outlook"])

    def test_native_zoom_installs_with_package_preparation_and_opens_login(self) -> None:
        backend = FakeBackend()

        self.execute("zoom", backend, login=True)

        self.assertEqual(backend.installs, ["zoom"])
        self.assertEqual(backend.package_preparations, 1)
        self.assertEqual(backend.logins, ["zoom"])

    def test_zoom_web_is_separate_and_excluded_from_all(self) -> None:
        backend = FakeBackend()

        self.execute("zoom-web", backend, login=True)

        self.assertEqual(backend.installs, ["zoom-web"])
        self.assertEqual(backend.package_preparations, 0)
        self.assertEqual(backend.logins, ["zoom-web"])

        backend = FakeBackend()
        self.execute("all", backend)
        self.assertNotIn("zoom-web", backend.installs)

    def test_dry_run_only_inspects(self) -> None:
        backend = FakeBackend()

        result, output = self.execute(
            "all", backend, login=True, set_defaults=True, dry_run=True
        )

        self.assertEqual(result, 0)
        self.assertEqual(backend.installs, [])
        self.assertEqual(backend.package_preparations, 0)
        self.assertEqual(backend.defaults, [])
        self.assertEqual(backend.logins, [])
        self.assertIn("Dry run complete", output)

    def test_mamba_only_does_not_prepare_system_package_databases(self) -> None:
        backend = FakeBackend()

        self.execute("mamba", backend)

        self.assertEqual(backend.installs, ["mamba"])
        self.assertEqual(backend.package_preparations, 0)

    def test_install_only_suppresses_login_and_default_hooks(self) -> None:
        backend = FakeBackend(installed={"zen"})

        self.execute(
            "zen",
            backend,
            login=True,
            set_defaults=True,
            install_only=True,
        )

        self.assertEqual(backend.defaults, [])
        self.assertEqual(backend.logins, [])
        self.assertEqual(backend.configured, [])

    def test_winapps_is_explicitly_excluded_from_unattended_all(self) -> None:
        backend = FakeBackend()

        self.execute("all", backend)

        self.assertNotIn("winapps", backend.installs)

    def test_declined_plan_changes_nothing(self) -> None:
        backend = FakeBackend()
        output = io.StringIO()

        result = run_install(
            "zen",
            paths=self.paths,
            backend=backend,
            assume_yes=False,
            login=False,
            set_defaults=False,
            dry_run=False,
            quiet=False,
            stdin=io.StringIO("no\n"),
            stdout=output,
        )

        self.assertEqual(result, 0)
        self.assertEqual(backend.installs, [])
        self.assertEqual(backend.package_preparations, 0)

    def test_failed_verification_stops_before_login(self) -> None:
        backend = FakeBackend(fail_verification="spotify")

        with self.assertRaisesRegex(ProgramError, "could not be verified"):
            self.execute("spotify", backend, login=True)

        self.assertEqual(backend.logins, [])

    def test_uninstall_removes_one_program_and_preserves_user_data_contract(self) -> None:
        backend = FakeBackend(installed={"spotify"})
        output = io.StringIO()

        result = run_uninstall(
            "spotify",
            paths=self.paths,
            backend=backend,
            assume_yes=True,
            dry_run=False,
            quiet=False,
            stdin=io.StringIO(""),
            stdout=output,
        )

        self.assertEqual(result, 0)
        self.assertEqual(backend.uninstalls, ["spotify"])
        self.assertIn("user data was preserved", output.getvalue())

    def test_uninstall_all_is_rejected_without_changes(self) -> None:
        backend = FakeBackend(installed={"spotify"})

        with self.assertRaisesRegex(ProgramError, "one explicit program"):
            run_uninstall(
                "all",
                paths=self.paths,
                backend=backend,
                assume_yes=True,
                dry_run=False,
                quiet=False,
                stdin=io.StringIO(""),
                stdout=io.StringIO(),
            )

        self.assertEqual(backend.uninstalls, [])


if __name__ == "__main__":
    unittest.main()
