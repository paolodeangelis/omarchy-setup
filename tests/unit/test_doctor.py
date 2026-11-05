from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from omarchy_setup.modules.doctor.core import collect_checks, shell_log_findings


class DoctorTests(unittest.TestCase):
    def test_shell_log_only_excepts_exact_known_panel_null_style_warnings(self) -> None:
        known = (
            "WARN file:///usr/share/omarchy/shell/plugins/panels/network/Panel.qml[12:-1]: "
            "TypeError: Cannot read property 'foreground' of null"
        )
        custom = (
            "WARN @services/OlioHostedBarWidget.qml[12:-1]: "
            "TypeError: Cannot read property 'sourceBar' of null"
        )
        battery = (
            "WARN file:///home/omarchy/.config/omarchy/plugins/"
            "aabulkhairov.battery-insights/Widget.qml[12:-1]: "
            "TypeError: Cannot read property 'fontFamily' of null"
        )
        media = (
            "WARN qs:///usr/share/omarchy/shell/plugins/services/media/BarWidget.qml[39:-1]: "
            "TypeError: Cannot read property 'barForeground' of null"
        )
        delayed_bar_reload = (
            "WARN scene: @plugins/bar/Bar.qml[2020:-1]: TypeError: Cannot read property "
            "'pluginBarApiFor' of undefined (exception occurred during delayed function evaluation)"
        )
        popup_card_startup = "WARN scene: @Ui/PopupCard.qml[35:3]: Unable to assign [undefined] to double"

        suspicious, known_stock = shell_log_findings(
            f"{known}\n{custom}\n{battery}\n{media}\n{delayed_bar_reload}\n"
            f"{popup_card_startup}\n"
        )

        self.assertEqual(suspicious, [custom])
        self.assertEqual(known_stock, [
            known, battery, media, delayed_bar_reload, popup_card_startup,
        ])

    def test_checks_accept_45_structured_menu_and_precise_media_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            bindings = home / ".config/omarchy/default/hypr/bindings"
            bindings.mkdir(parents=True)
            (bindings / "utilities.lua").write_text(
                'o.bind("SUPER + ESCAPE", "System menu", { menu = "system" })\n'
            )
            (bindings / "media.lua").write_text(
                'o.bind("ALT + XF86AudioRaiseVolume", "Volume", "omarchy-audio-output-volume +1")\n'
                'o.bind("ALT + XF86MonBrightnessUp", "Brightness", "omarchy-brightness-display +1%")\n'
            )

            def runner(command, environment=None):
                if command == ("quickshell", "list", "--all"):
                    return 1, "not running"
                if command[0] == "journalctl":
                    return 0, "normal startup"
                return 1, "unavailable"

            checks = {check.name: check for check in collect_checks(runner=runner, home=home)}
            self.assertTrue(checks["system menu binding"].ok)
            self.assertTrue(checks["media bindings"].ok)

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
