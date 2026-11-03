from __future__ import annotations

import curses
import io
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from omarchy_setup.modules.programs import PROGRAMS, ProgramError, ProgramPaths
from omarchy_setup.modules.programs.upgrade import (
    OmarchyUpgradeBackend,
    UpgradeStatus,
    _curses_selector,
    _package_versions,
    _parse_package_updates,
    format_upgrade_status,
    run_upgrade,
)


def program(name: str):
    return next(item for item in PROGRAMS if item.name == name)


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class FakeScreen:
    def __init__(self, keys):
        self.keys = iter(keys)

    def keypad(self, enabled):
        self.keypad_enabled = enabled

    def erase(self):
        pass

    def getmaxyx(self):
        return 24, 120

    def addnstr(self, *args):
        pass

    def getch(self):
        return next(self.keys)


class FakeUpgradeBackend:
    def __init__(self, statuses: list[UpgradeStatus]):
        self.statuses = {status.program.name: status for status in statuses}
        self.flatpak_calls: list[tuple[str, ...]] = []
        self.system_calls: list[bool] = []

    def check_environment(self) -> str:
        return "4.0.6"

    def inspect(self, programs, paths):
        return [self.statuses[item.name] for item in programs]

    def upgrade_flatpaks(self, app_ids):
        self.flatpak_calls.append(tuple(app_ids))
        for status in self.statuses.values():
            if status.program.flatpak_id in app_ids and status.state == "update":
                self.statuses[status.program.name] = UpgradeStatus(
                    status.program, True, status.candidate, "—", "current"
                )

    def upgrade_system(self, *, assume_yes):
        self.system_calls.append(assume_yes)
        for name, status in tuple(self.statuses.items()):
            if status.program.upgrade_policy == "system" and status.state == "update":
                self.statuses[name] = UpgradeStatus(
                    status.program, True, status.candidate, "—", "current"
                )


class ProgramUpgradeTests(unittest.TestCase):
    paths = ProgramPaths(data_home=Path("/unused"), shell_rc=Path("/unused/.bashrc"))

    def test_package_output_parsers_ignore_unrelated_lines(self) -> None:
        self.assertEqual(
            _parse_package_updates("foo 1.0 -> 1.1\nwarning: ignored\n"),
            {"foo": ("1.0", "1.1")},
        )
        self.assertEqual(_package_versions("foo 1.0\nbar 2.0-1\n"), {"foo": "1.0", "bar": "2.0-1"})

    def test_check_only_reports_without_mutating(self) -> None:
        backend = FakeUpgradeBackend([
            UpgradeStatus(program("bluebubbles"), True, "2.1", "2.2", "update")
        ])
        output = io.StringIO()

        result = run_upgrade(
            "bluebubbles", paths=self.paths, backend=backend, assume_yes=False,
            check_only=True, show_source=True, stdin=io.StringIO(), stdout=output,
        )

        self.assertEqual(result, 0)
        self.assertEqual(backend.flatpak_calls, [])
        self.assertEqual(backend.system_calls, [])
        self.assertIn("bluebubbles", output.getvalue())
        self.assertIn("2.1", output.getvalue())
        self.assertIn("2.2", output.getvalue())
        self.assertIn("flatpak", output.getvalue())

    def test_single_flatpak_upgrade_and_verification(self) -> None:
        backend = FakeUpgradeBackend([
            UpgradeStatus(program("bluebubbles"), True, "2.1", "2.2", "update")
        ])

        run_upgrade(
            "bluebubbles", paths=self.paths, backend=backend, assume_yes=True,
            check_only=False, show_source=False, stdin=io.StringIO(), stdout=io.StringIO(),
        )

        self.assertEqual(backend.flatpak_calls, [("app.bluebubbles.BlueBubbles",)])
        self.assertEqual(backend.system_calls, [])

    def test_known_update_must_disappear_after_upgrade(self) -> None:
        backend = FakeUpgradeBackend([
            UpgradeStatus(program("bluebubbles"), True, "2.1", "2.2", "update")
        ])
        backend.upgrade_flatpaks = lambda app_ids: None

        with self.assertRaisesRegex(ProgramError, "still detected"):
            run_upgrade(
                "bluebubbles", paths=self.paths, backend=backend, assume_yes=True,
                check_only=False, show_source=False, stdin=io.StringIO(),
                stdout=io.StringIO(),
            )

    def test_all_coalesces_system_programs_into_one_omarchy_update(self) -> None:
        statuses = []
        for item in PROGRAMS:
            installed = item.name in {"spotify", "thunderbird"}
            statuses.append(UpgradeStatus(item, installed, state="update" if installed else "absent"))
        backend = FakeUpgradeBackend(statuses)

        run_upgrade(
            "all", paths=self.paths, backend=backend, assume_yes=True,
            check_only=False, show_source=False, stdin=io.StringIO(), stdout=io.StringIO(),
        )

        self.assertEqual(backend.system_calls, [True])
        self.assertEqual(backend.flatpak_calls, [])

    def test_named_upgrade_can_be_cancelled_before_changes(self) -> None:
        backend = FakeUpgradeBackend([
            UpgradeStatus(program("bluebubbles"), True, "2.1", "2.2", "update")
        ])

        run_upgrade(
            "bluebubbles", paths=self.paths, backend=backend, assume_yes=False,
            check_only=False, show_source=False, stdin=io.StringIO("no\n"), stdout=io.StringIO(),
        )

        self.assertEqual(backend.flatpak_calls, [])

    def test_interactive_selector_controls_exact_programs(self) -> None:
        statuses = [
            UpgradeStatus(item, item.name in {"bluebubbles", "spotify"}, state="update")
            for item in PROGRAMS
        ]
        backend = FakeUpgradeBackend(statuses)

        run_upgrade(
            None, paths=self.paths, backend=backend, assume_yes=False,
            check_only=False, show_source=False, stdin=TtyBuffer(), stdout=TtyBuffer(),
            selector=lambda _: ["bluebubbles"],
        )

        self.assertEqual(backend.flatpak_calls, [("app.bluebubbles.BlueBubbles",)])
        self.assertEqual(backend.system_calls, [])

    @patch("omarchy_setup.modules.programs.upgrade.curses.curs_set")
    def test_curses_selector_uses_arrows_space_and_enter(self, _cursor) -> None:
        statuses = [
            UpgradeStatus(program("bluebubbles"), True, state="update"),
            UpgradeStatus(program("spotify"), True, state="update"),
        ]
        screen = FakeScreen([ord(" "), curses.KEY_DOWN, ord(" "), 10])

        self.assertEqual(_curses_selector(screen, statuses), ["bluebubbles", "spotify"])
        self.assertTrue(screen.keypad_enabled)

    def test_interactive_mode_requires_tty(self) -> None:
        backend = FakeUpgradeBackend([
            UpgradeStatus(item, False, state="absent") for item in PROGRAMS
        ])
        with self.assertRaisesRegex(ProgramError, "interactive terminal"):
            run_upgrade(
                None, paths=self.paths, backend=backend, assume_yes=False,
                check_only=False, show_source=False, stdin=io.StringIO(), stdout=io.StringIO(),
            )

    def test_manual_and_web_sources_are_reported_not_selectable(self) -> None:
        statuses = [
            UpgradeStatus(program("mamba"), True, state="manual"),
            UpgradeStatus(program("outlook"), True, state="no payload"),
        ]
        self.assertFalse(statuses[0].selectable)
        self.assertFalse(statuses[1].selectable)
        report = format_upgrade_status(statuses, show_source=True)
        self.assertIn("No automatically upgradable", report)

    def test_report_is_a_compact_source_table(self) -> None:
        report = format_upgrade_status([
            UpgradeStatus(program("bluebubbles"), True, "2.1", "2.2", "update"),
            UpgradeStatus(program("mamba"), True, "unknown", "unknown", "manual"),
        ], show_source=True)

        self.assertIn("PROGRAM", report)
        self.assertIn("INSTALLED", report)
        self.assertIn("AVAILABLE", report)
        self.assertIn("SOURCE", report)
        self.assertIn("bluebubbles", report)
        self.assertIn("2.1", report)
        self.assertIn("2.2", report)
        self.assertNotIn("app.bluebubbles.BlueBubbles", report)
        self.assertNotIn("mamba", report)

    @patch("omarchy_setup.modules.programs.upgrade.curses.curs_set")
    def test_selector_hides_installed_programs_without_known_updates(self, _cursor) -> None:
        statuses = [
            UpgradeStatus(program("bluebubbles"), True, "2.1", "2.2", "update"),
            UpgradeStatus(program("spotify"), True, "1.0", "—", "current"),
            UpgradeStatus(program("mamba"), True, state="manual"),
        ]
        screen = FakeScreen([ord(" "), 10])

        self.assertEqual(_curses_selector(screen, statuses), ["bluebubbles"])

    def test_concrete_backend_uses_supported_update_commands(self) -> None:
        backend = OmarchyUpgradeBackend()
        with patch.object(backend.programs, "_run") as run:
            backend.upgrade_flatpaks(["app.bluebubbles.BlueBubbles"])
            backend.upgrade_system(assume_yes=True)
            backend.upgrade_system(assume_yes=False)

        self.assertEqual(run.call_args_list[0].args[0], (
            "flatpak", "update", "--noninteractive", "app.bluebubbles.BlueBubbles"
        ))
        self.assertEqual(run.call_args_list[1].args[0], ("omarchy", "update", "-y"))
        self.assertEqual(run.call_args_list[2].args[0], ("omarchy", "update"))

    @patch("omarchy_setup.modules.programs.upgrade.subprocess.run")
    def test_network_probe_times_out_as_unknown_instead_of_hanging(self, run) -> None:
        run.side_effect = subprocess.TimeoutExpired(("checkupdates",), 30)

        result = OmarchyUpgradeBackend._run_probe(("checkupdates",))

        self.assertEqual(result.returncode, 124)
        self.assertIn("timed out", result.stderr)


if __name__ == "__main__":
    unittest.main()
