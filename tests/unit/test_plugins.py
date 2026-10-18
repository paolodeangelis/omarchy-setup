from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from omarchy_setup.cli import build_parser
from omarchy_setup.modules.plugins.core import (
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

        self.assertEqual((radar.section, radar.after), ("center", "omarchy.weather"))
        self.assertEqual(radar.replaces, ("com.omastorm.radar",))
        self.assertEqual((battery.section, battery.after), ("right", "omarchy.tray"))
        self.assertEqual(battery.replaces, ())
        self.assertEqual((monitors.section, monitors.after), ("right", "omarchy.audio"))
        self.assertEqual(monitors.replaces, ("omarchy.monitor",))
        self.assertEqual(monitors.requires, ("hyprmoncfg",))
        self.assertEqual(monitors.aur_packages, ("hyprmoncfg-bin",))
        self.assertEqual(monitors.user_services, ("hyprmoncfgd.service",))
        self.assertTrue(media.builtin)
        self.assertIsNone(media.url)
        self.assertEqual((media.section, media.after), ("left", "tornikegomareli.spaces"))

    def test_apply_is_idempotent_and_disables_only_after_enable(self) -> None:
        old_radar = self.paths.installed_root / "com.omastorm.radar"
        old_radar.mkdir(parents=True)
        old_radar.joinpath("manifest.json").write_text('{"id":"com.omastorm.radar"}\n')
        output = io.StringIO()

        for _ in range(2):
            self.assertEqual(run_plugins(
                "apply", "all", paths=self.paths, backend=self.backend,
                assume_yes=True, dry_run=False, stdin=io.StringIO(),
                stdout=output, progress=False,
            ), 0)

        installs = [call for call in self.backend.calls if call[0] == "install"]
        self.assertEqual(len(installs), 5)
        first_radar_enable = self.backend.calls.index(
            ("enable", "eduardodallecort.weather-radar", "center", "omarchy.weather")
        )
        first_radar_disable = self.backend.calls.index(("disable", "com.omastorm.radar"))
        self.assertLess(first_radar_enable, first_radar_disable)
        self.assertNotIn(("disable", "omarchy.power"), self.backend.calls)
        self.assertIn(("disable", "omarchy.monitor"), self.backend.calls)

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
        self.assertIn(("enable", target, "right", "omarchy.tray"), self.backend.calls)
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
        status = build_parser().parse_args(["plugin", "status"])
        upgrade = build_parser().parse_args([
            "plugin", "upgrade", "eduardodallecort.weather-radar", "-y"
        ])

        self.assertEqual((apply.plugin_action, apply.yes), ("apply", True))
        self.assertEqual(status.plugin_action, "status")
        self.assertEqual(upgrade.target, "eduardodallecort.weather-radar")

if __name__ == "__main__":
    unittest.main()
