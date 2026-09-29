from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from omarchy_setup.modules.doctor.core import collect_checks


class DoctorTests(unittest.TestCase):
    def test_checks_live_shell_and_critical_interfaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            bindings = home / ".config/omarchy/default/hypr/bindings"
            bindings.mkdir(parents=True)
            (bindings / "utilities.lua").write_text(
                'o.bind("SUPER + ESCAPE", "System", "omarchy-menu toggle system")\n'
            )
            (bindings / "media.lua").write_text(
                'o.bind("XF86AudioRaiseVolume", "Volume", "omarchy-audio-output-volume raise")\n'
                'o.bind("XF86MonBrightnessUp", "Brightness", "omarchy-brightness-display raise")\n'
            )
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

            with patch("omarchy_setup.modules.doctor.core.shutil.which", side_effect=lambda name: f"/fixture/bin/{name}"):
                checks = collect_checks(runner=runner, home=home)
            by_name = {check.name: check for check in checks}
            self.assertTrue(by_name["shell IPC"].ok)
            self.assertTrue(by_name["menu IPC"].ok)
            self.assertTrue(by_name["OSD IPC"].ok)
            self.assertTrue(by_name["system menu binding"].ok)
            self.assertTrue(by_name["media bindings"].ok)
            self.assertEqual(by_name["system menu binding"].detail, str(bindings / "utilities.lua"))
            self.assertEqual(by_name["media bindings"].detail, str(bindings / "media.lua"))
            self.assertEqual(calls[1][1]["OMARCHY_PATH"], "/tmp/omarchy")


if __name__ == "__main__":
    unittest.main()
