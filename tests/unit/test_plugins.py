from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omarchy_setup.cli import build_parser
from omarchy_setup.modules.plugins.core import (
    OmarchyPluginBackend,
    Plugin,
    PluginError,
    PluginPaths,
    ensure_spaces_agent_hooks,
    format_plugin_status,
    load_plugins,
    run_plugins,
)


class FakeBackend:
    def __init__(self, paths: PluginPaths) -> None:
        self.paths = paths
        self.calls: list[tuple[object, ...]] = []
        self.available_commands: set[str] = set()
        self.active_services: set[str] = set()
        self.satisfy_requirements = True
        self.start_services = True

    def install(self, plugin: Plugin) -> None:
        self.calls.append(("install", plugin.id))
        directory = self.paths.installed_root / plugin.id
        directory.mkdir(parents=True, exist_ok=True)
        directory.joinpath("manifest.json").write_text(json.dumps({"id": plugin.id}))
        if plugin.id == "tornikegomareli.spaces":
            reporter = directory / "hooks" / "claude-hook"
            reporter.parent.mkdir(parents=True)
            reporter.write_text("#!/bin/sh\n")

    def validate(self, directory: Path) -> None:
        self.calls.append(("validate", directory.name))

    def enable(self, plugin: Plugin) -> None:
        self.calls.append(("enable", plugin.id, plugin.section, plugin.after))

    def disable(self, plugin_id: str) -> None:
        self.calls.append(("disable", plugin_id))

    def upgrade(self, plugin_id: str, *, assume_yes: bool) -> None:
        self.calls.append(("upgrade", plugin_id, assume_yes))

    def remove(self, plugin: Plugin, *, assume_yes: bool) -> None:
        self.calls.append(("remove", plugin.id, assume_yes))

    def command_available(self, command: str) -> bool:
        return command in self.available_commands

    def install_requirements(self, plugin: Plugin) -> None:
        self.calls.append(("install_requirements", plugin.id, plugin.aur_packages))
        if self.satisfy_requirements:
            self.available_commands.update(plugin.requires)

    def enable_user_services(self, plugin: Plugin) -> None:
        self.calls.append(("enable_user_services", plugin.id, plugin.user_services))
        if self.start_services:
            self.active_services.update(plugin.user_services)

    def user_service_active(self, service: str) -> bool:
        return service in self.active_services

    def configure_omamail_default(self, plugin_dir: Path, open_key: str, compose_key: str) -> None:
        self.calls.append(("configure_omamail_default", plugin_dir.name, open_key, compose_key))

    def configure_display_binding(self) -> None:
        self.calls.append(("configure_display_binding",))

    def configure_spotlight_binding(self, plugin_dir: Path) -> None:
        self.calls.append(("configure_spotlight_binding", plugin_dir.name))


class PluginTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.paths = PluginPaths(
            repo_root=Path(__file__).resolve().parents[2],
            state_root=root / "state",
            home=root / "home",
            system_omarchy=root / "system",
        )
        self.backend = FakeBackend(self.paths)

    def _install_all(self) -> tuple[Plugin, ...]:
        plugins = load_plugins(self.paths.config)
        for plugin in plugins:
            if not plugin.builtin:
                self.backend.install(plugin)
        self.backend.calls.clear()
        return plugins

    def test_registry_controls_replacements_and_final_positions(self) -> None:
        plugins = {plugin.id: plugin for plugin in load_plugins(self.paths.config)}
        radar = plugins["eduardodallecort.weather-radar"]
        battery = plugins["aabulkhairov.battery-insights"]
        monitors = plugins["crmne.hyprmoncfg"]
        media = plugins["omarchy.media"]
        elsewhen = plugins["omarchy.elsewhen"]
        mail = plugins["omamail"]
        vpn = plugins["io.github.grichard99.omaproton-vpn"]
        alternative_vpn = plugins["jkoestinger.vpn"]
        notifications = plugins["shavanced.notification-center"]
        old_notifications = plugins["jankeesvw.notification-center"]
        tray = plugins["omarchy.tray"]
        old_tray = plugins["io.github.tyrichards.tray"]
        hardware_monitor = plugins["zoltanf.hw-monitor"]
        old_system_monitor = plugins["harshith.system-monitor"]
        github = plugins["robzolkos.github"]
        spotlight = plugins["io.github.maajix.spotlight"]

        self.assertEqual((radar.section, radar.after), ("center", "omarchy.weather"))
        self.assertEqual(radar.replaces, ("com.omastorm.radar",))
        self.assertEqual((battery.section, battery.after), ("right", "omarchy.tray"))
        self.assertEqual(battery.replaces, ())
        self.assertEqual((monitors.section, monitors.after), ("right", "omarchy.audio"))
        self.assertEqual(monitors.replaces, ("omarchy.monitor",))
        self.assertEqual(monitors.requires, ("hyprmoncfg",))
        self.assertEqual(monitors.aur_packages, ("hyprmoncfg-bin",))
        self.assertEqual(monitors.user_services, ("hyprmoncfgd.service",))
        self.assertEqual(
            (notifications.section, notifications.after),
            ("right", "robzolkos.github"),
        )
        self.assertFalse(notifications.enabled)
        self.assertEqual(old_notifications.replaces, ("shavanced.notification-center",))
        self.assertEqual((tray.section, tray.after), ("right", "crmne.hyprmoncfg"))
        self.assertTrue(tray.builtin)
        self.assertEqual(tray.replaces, ("io.github.tyrichards.tray",))
        self.assertFalse(old_tray.enabled)
        self.assertEqual((hardware_monitor.section, hardware_monitor.after), ("right", "omarchy.tray"))
        self.assertEqual(hardware_monitor.replaces, ("harshith.system-monitor",))
        self.assertFalse(old_system_monitor.enabled)
        self.assertEqual((github.section, github.after), ("right", "zoltanf.hw-monitor"))
        self.assertEqual((spotlight.section, spotlight.after), (None, None))
        self.assertTrue(media.builtin)
        self.assertIsNone(media.url)
        self.assertEqual((media.section, media.after), ("left", "tornikegomareli.spaces"))
        self.assertTrue(elsewhen.builtin)
        self.assertIsNone(elsewhen.url)
        self.assertEqual((elsewhen.section, elsewhen.after), ("center", "omarchy.clock"))
        self.assertEqual((mail.section, mail.after), ("right", "omarchy.agents"))
        self.assertFalse(mail.enabled)
        self.assertEqual((vpn.section, vpn.after), (None, None))
        self.assertFalse(vpn.enabled)
        self.assertEqual(vpn.replaces, ())
        self.assertEqual((alternative_vpn.section, alternative_vpn.after), (None, None))
        self.assertFalse(alternative_vpn.enabled)
        self.assertEqual(alternative_vpn.replaces, ())

    def test_apply_all_disables_installed_disabled_plugins(self) -> None:
        directory = self.paths.installed_root / "jkoestinger.vpn"
        directory.mkdir(parents=True)
        directory.joinpath("manifest.json").write_text('{"id":"jkoestinger.vpn"}\n')

        run_plugins(
            "apply", "all", paths=self.paths, backend=self.backend,
            assume_yes=True, dry_run=False, stdin=io.StringIO(),
            stdout=io.StringIO(), progress=False,
        )

        self.assertIn(("disable", "jkoestinger.vpn"), self.backend.calls)

    def test_targeted_apply_can_install_disabled_omamail_without_making_it_default(self) -> None:
        run_plugins(
            "apply", "omamail", paths=self.paths, backend=self.backend,
            assume_yes=True, dry_run=False, stdin=io.StringIO(),
            stdout=io.StringIO(), progress=False,
        )

        self.assertIn(("install", "omamail"), self.backend.calls)
        self.assertFalse(any(call[0] == "configure_omamail_default" for call in self.backend.calls))

    def test_remove_keeps_catalog_entry_and_calls_supported_remover(self) -> None:
        run_plugins(
            "remove", "omamail", paths=self.paths, backend=self.backend,
            assume_yes=True, dry_run=False, stdin=io.StringIO(),
            stdout=io.StringIO(), progress=False,
        )
        self.assertIn(("remove", "omamail", True), self.backend.calls)

    def test_omamail_removal_preserves_replacement_mail_binding(self) -> None:
        bindings = self.paths.home / ".config" / "hypr" / "bindings.lua"
        bindings.parent.mkdir(parents=True)
        replacement = (
            "-- >>> omarchy-setup mail\n"
            'o.bind("SUPER + SHIFT + E", "Email", "uwsm-app -- thunderbird")\n'
            "-- <<< omarchy-setup mail\n"
        )
        bindings.write_text(replacement)
        plugin = next(
            plugin for plugin in load_plugins(self.paths.config) if plugin.id == "omamail"
        )
        backend = OmarchyPluginBackend(self.paths)
        with patch.object(backend, "_run"):
            backend.remove(plugin, assume_yes=True)
        self.assertEqual(bindings.read_text(), replacement)

    def test_display_binding_targets_hyprmoncfg_and_is_idempotent(self) -> None:
        bindings = self.paths.home / ".config" / "hypr" / "bindings.lua"
        bindings.parent.mkdir(parents=True)
        bindings.write_text("-- personal\n")
        backend = OmarchyPluginBackend(self.paths)
        with patch.object(backend, "_run") as run:
            backend.configure_display_binding()
            first = bindings.read_text()
            backend.configure_display_binding()
        self.assertEqual(bindings.read_text(), first)
        self.assertIn("-- personal", first)
        self.assertIn('hl.unbind("SUPER + CTRL + D")', first)
        self.assertIn("omarchy-shell shell summon crmne.hyprmoncfg", first)
        self.assertEqual(run.call_count, 2)

    def test_spotlight_binding_moves_dictation_and_is_idempotent(self) -> None:
        bindings = self.paths.home / ".config" / "hypr" / "bindings.lua"
        bindings.parent.mkdir(parents=True)
        bindings.write_text("-- personal\n")
        plugin_dir = self.paths.installed_root / "io.github.maajix.spotlight"
        helper = plugin_dir / "bin" / "spotlight-helper"
        helper.parent.mkdir(parents=True)
        helper.write_text("#!/bin/sh\n")
        backend = OmarchyPluginBackend(self.paths)
        with patch.object(backend, "_run") as run:
            backend.configure_spotlight_binding(plugin_dir)
            backend.configure_spotlight_binding(plugin_dir)
        result = bindings.read_text()
        self.assertEqual(result.count("-- >>> omarchy-setup dictation-shortcut >>>"), 1)
        self.assertIn('hl.unbind("SUPER + CTRL + X")', result)
        self.assertIn('o.bind("SUPER + ALT + D", "Toggle dictation"', result)
        self.assertEqual(
            run.call_args_list[0].args[0],
            (str(helper), "write-binding", "ALT + SPACE"),
        )

    def test_apply_is_idempotent_and_disables_only_after_enable(self) -> None:
        old_radar = self.paths.installed_root / "com.omastorm.radar"
        old_radar.mkdir(parents=True)
        old_radar.joinpath("manifest.json").write_text('{"id":"com.omastorm.radar"}\n')
        old_notifications = self.paths.installed_root / "shavanced.notification-center"
        old_notifications.mkdir(parents=True)
        old_notifications.joinpath("manifest.json").write_text(
            '{"id":"shavanced.notification-center"}\n'
        )
        old_monitor = self.paths.installed_root / "harshith.system-monitor"
        old_monitor.mkdir(parents=True)
        old_monitor.joinpath("manifest.json").write_text(
            '{"id":"harshith.system-monitor"}\n'
        )
        old_tray = self.paths.installed_root / "io.github.tyrichards.tray"
        old_tray.mkdir(parents=True)
        old_tray.joinpath("manifest.json").write_text(
            '{"id":"io.github.tyrichards.tray"}\n'
        )
        output = io.StringIO()

        for _ in range(2):
            self.assertEqual(run_plugins(
                "apply", "all", paths=self.paths, backend=self.backend,
                assume_yes=True, dry_run=False, stdin=io.StringIO(),
                stdout=output, progress=False,
            ), 0)

        installs = [call for call in self.backend.calls if call[0] == "install"]
        self.assertEqual(len(installs), 8)
        first_radar_enable = self.backend.calls.index(
            ("enable", "eduardodallecort.weather-radar", "center", "omarchy.weather")
        )
        first_radar_disable = self.backend.calls.index(("disable", "com.omastorm.radar"))
        self.assertLess(first_radar_enable, first_radar_disable)
        self.assertNotIn(("disable", "omarchy.power"), self.backend.calls)
        self.assertIn(("disable", "omarchy.monitor"), self.backend.calls)
        tray_enable = self.backend.calls.index(
            ("enable", "omarchy.tray", "right", "crmne.hyprmoncfg")
        )
        self.assertLess(tray_enable, self.backend.calls.index(("disable", "io.github.tyrichards.tray")))
        monitor_enable = self.backend.calls.index(
            ("enable", "zoltanf.hw-monitor", "right", "omarchy.tray")
        )
        self.assertLess(monitor_enable, self.backend.calls.index(("disable", "harshith.system-monitor")))
        notification_enable = self.backend.calls.index(
            ("enable", "jankeesvw.notification-center", "right", "robzolkos.github")
        )
        notification_disable = self.backend.calls.index(
            ("disable", "shavanced.notification-center")
        )
        self.assertLess(notification_enable, notification_disable)
        self.assertIn(("enable", "io.github.maajix.spotlight", None, None), self.backend.calls)
        self.assertIn(
            ("configure_spotlight_binding", "io.github.maajix.spotlight"),
            self.backend.calls,
        )

    def test_overlay_plugin_can_omit_bar_placement(self) -> None:
        path = self.paths.state_root / "overlay-plugin.toml"
        path.parent.mkdir(parents=True)
        path.write_text(
            '[[plugin]]\nid="example.overlay"\nurl="https://github.com/example/overlay.git"\n'
        )
        plugin = load_plugins(path)[0]
        self.assertEqual((plugin.section, plugin.after), (None, None))

    def test_status_detects_enabled_overlay_plugins(self) -> None:
        spotlight = self.paths.installed_root / "io.github.maajix.spotlight"
        spotlight.mkdir(parents=True)
        spotlight.joinpath("manifest.json").write_text(
            '{"id":"io.github.maajix.spotlight"}\n'
        )
        self.paths.shell_config.parent.mkdir(parents=True, exist_ok=True)
        self.paths.shell_config.write_text(
            '{"bar":{"layout":{}},"plugins":[{"id":"io.github.maajix.spotlight"}]}\n'
        )
        status = format_plugin_status(self.paths)
        self.assertRegex(status, r"io\.github\.maajix\.spotlight\s+enabled\s+overlay")

    def test_builtin_media_is_positioned_without_install_or_update(self) -> None:
        run_plugins(
            "upgrade", "omarchy.media", paths=self.paths, backend=self.backend,
            assume_yes=True, dry_run=False, stdin=io.StringIO(),
            stdout=io.StringIO(), progress=False,
        )

        self.assertEqual(
            self.backend.calls,
            [("enable", "omarchy.media", "left", "tornikegomareli.spaces")],
        )

    def test_replacement_installs_backend_before_plugin_and_disables_stock_widget(self) -> None:
        target = "crmne.hyprmoncfg"
        run_plugins(
            "apply", target, paths=self.paths, backend=self.backend,
            assume_yes=True, dry_run=False, stdin=io.StringIO(),
            stdout=io.StringIO(), progress=False,
        )

        requirements = self.backend.calls.index(
            ("install_requirements", target, ("hyprmoncfg-bin",))
        )
        service = self.backend.calls.index(
            ("enable_user_services", target, ("hyprmoncfgd.service",))
        )
        install = self.backend.calls.index(("install", target))
        enable = self.backend.calls.index(
            ("enable", target, "right", "omarchy.audio")
        )
        disable = self.backend.calls.index(("disable", "omarchy.monitor"))
        self.assertLess(requirements, install)
        self.assertLess(requirements, service)
        self.assertLess(service, install)
        self.assertLess(install, enable)
        self.assertLess(enable, disable)
        self.assertGreater(
            self.backend.calls.index(("configure_display_binding",)), disable
        )

    def test_failed_backend_install_preserves_stock_widget_and_skips_plugin(self) -> None:
        self.backend.satisfy_requirements = False

        with self.assertRaisesRegex(PluginError, "requirements are unavailable"):
            run_plugins(
                "apply", "crmne.hyprmoncfg", paths=self.paths, backend=self.backend,
                assume_yes=True, dry_run=False, stdin=io.StringIO(),
                stdout=io.StringIO(), progress=False,
            )

        self.assertFalse(any(call[0] == "install" for call in self.backend.calls))
        self.assertNotIn(("disable", "omarchy.monitor"), self.backend.calls)

    def test_failed_backend_service_preserves_stock_widget_and_skips_plugin(self) -> None:
        self.backend.start_services = False

        with self.assertRaisesRegex(PluginError, "user services are inactive"):
            run_plugins(
                "apply", "crmne.hyprmoncfg", paths=self.paths, backend=self.backend,
                assume_yes=True, dry_run=False, stdin=io.StringIO(),
                stdout=io.StringIO(), progress=False,
            )

        self.assertFalse(any(call[0] == "install" for call in self.backend.calls))
        self.assertNotIn(("disable", "omarchy.monitor"), self.backend.calls)

    def test_upgrade_targets_one_managed_plugin_then_reconciles_it(self) -> None:
        self._install_all()
        target = "aabulkhairov.battery-insights"
        run_plugins(
            "upgrade", target, paths=self.paths, backend=self.backend,
            assume_yes=True, dry_run=False, stdin=io.StringIO(),
            stdout=io.StringIO(), progress=False,
        )

        self.assertEqual(self.backend.calls[0], ("upgrade", target, True))
        self.assertIn(
            ("enable", target, "right", "omarchy.tray"),
            self.backend.calls,
        )
        self.assertFalse(any(call[0] == "upgrade" and call[1] != target for call in self.backend.calls))

    def test_unknown_upgrade_target_fails_without_changes(self) -> None:
        with self.assertRaisesRegex(PluginError, "unknown managed plugin"):
            run_plugins(
                "upgrade", "unknown.plugin", paths=self.paths, backend=self.backend,
                assume_yes=True, dry_run=False, stdin=io.StringIO(),
                stdout=io.StringIO(), progress=False,
            )
        self.assertEqual(self.backend.calls, [])

    def test_status_reports_live_layout_position(self) -> None:
        self._install_all()
        self.paths.shell_config.parent.mkdir(parents=True, exist_ok=True)
        self.paths.shell_config.write_text(json.dumps({
            "bar": {"layout": {"left": [], "center": [], "right": [
                {"id": "omarchy.tray"}, {"id": "aabulkhairov.battery-insights"}
            ]}}
        }))

        status = format_plugin_status(self.paths)
        self.assertIn("aabulkhairov.battery-insights", status)
        self.assertIn("enabled    right:1", status)
        self.assertIn("eduardodallecort.weather-radar", status)
        self.assertIn("disabled", status)

    def test_spaces_hooks_are_owned_by_plugin_module_and_idempotent(self) -> None:
        self._install_all()
        self.paths.codex_hooks.parent.mkdir(parents=True)
        self.paths.codex_hooks.write_text(
            '{"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"keep"}]}]}}\n'
        )

        ensure_spaces_agent_hooks(self.paths)
        ensure_spaces_agent_hooks(self.paths)

        codex = json.loads(self.paths.codex_hooks.read_text())
        self.assertEqual(codex["hooks"]["SessionStart"][0]["hooks"][0]["command"], "keep")
        self.assertEqual(len(codex["hooks"]["PermissionRequest"]), 1)
        handler = codex["hooks"]["PermissionRequest"][0]["hooks"][0]
        self.assertTrue(handler["command"].endswith("omarchy-spaces-agent waiting"))
        self.assertFalse(handler["async"])

    def test_cli_exposes_apply_status_and_upgrade(self) -> None:
        apply = build_parser().parse_args(["plugin", "apply", "-y"])
        targeted = build_parser().parse_args(["plugin", "apply", "omamail", "-y"])
        status = build_parser().parse_args(["plugin", "status"])
        remove = build_parser().parse_args(["plugin", "remove", "omamail", "-y"])
        upgrade = build_parser().parse_args([
            "plugin", "upgrade", "eduardodallecort.weather-radar", "-y"
        ])

        self.assertEqual((apply.plugin_action, apply.yes), ("apply", True))
        self.assertEqual(targeted.target, "omamail")
        self.assertEqual(status.plugin_action, "status")
        self.assertEqual(remove.target, "omamail")
        self.assertEqual(upgrade.target, "eduardodallecort.weather-radar")

if __name__ == "__main__":
    unittest.main()
