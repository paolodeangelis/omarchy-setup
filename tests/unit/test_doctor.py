from pathlib import Path
import tempfile
import unittest

from omarchy_setup.modules.doctor.core import collect_checks


class DoctorTests(unittest.TestCase):
    def test_checks_live_shell_and_critical_interfaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            calls = []

            def runner(command, environment=None):
                calls.append((command, environment))
                if command == ("quickshell", "list", "--all"):
                    return 0, "Config path: /tmp/omarchy/shell/shell.qml"
                if command == ("journalctl", "--user", "-t", "omarchy-shell", "--since", "15 minutes ago", "--no-pager"):
                    return 0, "normal startup"
                if command[:2] == ("omarchy-shell", "shell"):
                    return 0, "ok"
                if command[:2] == ("omarchy-shell", "osd"):
                    return 0, "ok"
                return 0, ""

            checks = collect_checks(runner=runner, home=home)
            by_name = {check.name: check for check in checks}
            self.assertTrue(by_name["shell IPC"].ok)
            self.assertTrue(by_name["menu IPC"].ok)
            self.assertTrue(by_name["OSD IPC"].ok)
            self.assertTrue(by_name["system menu binding"].ok)
            self.assertTrue(by_name["media bindings"].ok)
            self.assertEqual(calls[1][1]["OMARCHY_PATH"], "/tmp/omarchy")


if __name__ == "__main__":
    unittest.main()
