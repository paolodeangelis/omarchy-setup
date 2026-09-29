from __future__ import annotations

import io
import unittest
from pathlib import Path

from omarchy_setup.modules.programs import Program, ProgramError, ProgramPaths, run_install


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
        self.defaults: list[str] = []
        self.logins: list[str] = []

    def check_environment(self) -> str:
        return "4.0.4"

    def is_installed(self, program: Program, paths: ProgramPaths) -> bool:
        return program.name in self.installed

    def install(self, program: Program, paths: ProgramPaths, *, quiet: bool) -> None:
        self.installs.append(program.name)
        if program.name != self.fail_verification:
            self.installed.add(program.name)

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
        )
        return result, output.getvalue()

    def test_all_installs_every_missing_program_without_onboarding(self) -> None:
        backend = FakeBackend(installed={"whatsapp"})

        result, output = self.execute("all", backend)

        self.assertEqual(result, 0)
        self.assertEqual(
            backend.installs,
            ["mamba", "zen", "1password", "dropbox", "spotify", "telegram"],
        )
        self.assertEqual(backend.defaults, [])
        self.assertEqual(backend.logins, [])
        self.assertIn("[3/10] Installing Mamba", output)

    def test_login_and_default_hooks_run_for_installed_program(self) -> None:
        backend = FakeBackend(installed={"zen"})

        self.execute("zen", backend, login=True, set_defaults=True)

        self.assertEqual(backend.installs, [])
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
                "whatsapp",
                "telegram",
            }
        )

        self.execute("all", backend, login=True, set_defaults=True)

        self.assertEqual(backend.defaults, ["zen"])
        self.assertEqual(
            backend.logins,
            ["zen", "1password", "dropbox", "spotify", "whatsapp", "telegram"],
        )

    def test_dry_run_only_inspects(self) -> None:
        backend = FakeBackend()

        result, output = self.execute(
            "all", backend, login=True, set_defaults=True, dry_run=True
        )

        self.assertEqual(result, 0)
        self.assertEqual(backend.installs, [])
        self.assertEqual(backend.defaults, [])
        self.assertEqual(backend.logins, [])
        self.assertIn("Dry run complete", output)

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

    def test_failed_verification_stops_before_login(self) -> None:
        backend = FakeBackend(fail_verification="spotify")

        with self.assertRaisesRegex(ProgramError, "could not be verified"):
            self.execute("spotify", backend, login=True)

        self.assertEqual(backend.logins, [])


if __name__ == "__main__":
    unittest.main()
