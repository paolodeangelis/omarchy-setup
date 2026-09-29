from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omarchy_setup.cli import build_parser
from omarchy_setup.modules.theme import host_integration

from omarchy_setup.modules.theme.core import (
    NOTIFICATION_CENTER_ID,
    OMASTORM_ID,
    SPACES_ID,
    OmarchyThemeBackend,
    ThemeError,
    ThemePaths,
    apply_theme,
    configure_theme,
    restore_theme,
    theme_status,
    _validate_theme_toml,
    _resolve_palette_references,
)


class FakeBackend:
    def __init__(self) -> None:
        self.active: Path | None = None
        self.builds = 0
        self.switches: list[tuple[Path, Path]] = []
        self.restarts: list[Path] = []
        self.themes: list[str] = []
        self.hyprland_validations = 0

    def build_blobs(self, paths: ThemePaths, destination: Path) -> None:
        self.builds += 1
        destination.mkdir(parents=True)
        (destination / "qmldir").write_text("module Caelestia.Blobs\n")
        (destination / "libcaelestia-blobsplugin.so").write_text("fake\n")

    def validate_overlay(self, overlay_shell: Path) -> None:
        if not (overlay_shell / "Ui" / "KeyboardPanel.qml").is_file():
            raise ThemeError("missing KeyboardPanel")

    def switch_shell(self, target_root: Path, previous_root: Path) -> None:
        self.switches.append((target_root, previous_root))
        self.active = target_root

    def restart_shell(self, target_root: Path) -> None:
        self.restarts.append(target_root)
        self.active = target_root

    def active_omarchy_path(self) -> Path | None:
        return self.active

    def validate_bar_plugin(self, source: Path) -> None:
        if not source.joinpath("manifest.json").is_file():
            raise ThemeError("missing bar manifest")

    def set_theme(self, name: str, *, preserve_background: bool = False) -> None:
        self.themes.append(f"{name}:{'preserve' if preserve_background else 'select'}")

    def validate_hyprland(self) -> None:
        self.hyprland_validations += 1

    def ensure_companion_plugins(self, paths: ThemePaths) -> None:
        return None


class ThemeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        repo = Path(__file__).resolve().parents[2]
        system = root / "system-omarchy"
        ui = system / "shell" / "Ui"
        ui.mkdir(parents=True)
        (ui / "KeyboardPanel.qml").write_text("stock keyboard panel\n")
        (ui / "PluginBarApi.qml").write_text(
            "import QtQuick\nQtObject {\n"
            "  property int barSize: 0\n"
            "}\n"
        )
        host_files = {
            "shell.qml": 'import "services"\n      _barEntryShellLookup: function(ownerId, moduleName) {\n',
            "services/PluginShellApi.qml": "  property var _barEntryShellLookup: null\n  function serviceFor(id) {\n",
            "plugins/notifications/Service.qml": (
                "      readonly property var popupPlacement: NotificationLogic.popupPlacement(\n"
                "        service.barPosition, service.barClearance, Style.gapsOut)"
            ),
        }
        for name, content in host_files.items():
            target = system / "shell" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        supported = {name: __import__("hashlib").sha256(content.encode()).hexdigest()
                     for name, content in host_files.items()}
        for target, value in (
            ("omarchy_setup.modules.theme.host_integration.SUPPORTED", supported),
            ("omarchy_setup.modules.theme.core.SUPPORTED_PLUGIN_BAR_API_SHA256",
             {__import__("hashlib").sha256((ui / "PluginBarApi.qml").read_bytes()).hexdigest()}),
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        (ui / "qmldir").write_text("module qs.Ui\nKeyboardPanel 1.0 KeyboardPanel.qml\n")
        (system / "config").mkdir()
        self.paths = ThemePaths(
            repo_root=repo,
            state_root=root / "state" / "omarchy-setup",
            home=root / "home",
            system_omarchy=system,
        )
        self.backend = FakeBackend()
        self.digest = __import__("hashlib").sha256(
            (ui / "KeyboardPanel.qml").read_bytes()
        ).hexdigest()

    def test_invalid_theme_toml_is_rejected_before_activation(self) -> None:
        invalid = self.paths.state_root / "invalid-shell.toml"
        invalid.parent.mkdir(parents=True)
        invalid.write_text("background-alpha = .85\n")

        with self.assertRaisesRegex(ThemeError, "invalid theme TOML"):
            _validate_theme_toml(invalid)

    def test_shell_palette_references_are_resolved_and_validated(self) -> None:
        rendered = _resolve_palette_references(
            '[bar]\nbackground = "palette.dark_background"\ntext = "palette.foreground"\n',
            'dark_background = "#0C1224"\nforeground = "#cdd6f4"\n',
        )
        self.assertEqual(
            __import__("tomllib").loads(rendered)["bar"],
            {"background": "#0C1224", "text": "#cdd6f4"},
        )
        with self.assertRaisesRegex(ThemeError, "palette.missing"):
            _resolve_palette_references(
                '[bar]\nbackground = "palette.missing"\n',
                'background = "#111932"\n',
            )

    def test_apply_is_idempotent_and_restore_is_reversible(self) -> None:
        with patch(
            "omarchy_setup.modules.theme.core.SUPPORTED_KEYBOARD_PANEL_SHA256",
            {self.digest},
        ):
            self.assertEqual(apply_theme(self.paths, self.backend), "applied")
            self.assertEqual(theme_status(self.paths, self.backend), "fixed bar active and compatible")
            self.assertTrue((self.paths.overlay_shell / "Ui" / "KeyboardPanel.qml").is_file())
            self.assertIn(
                "property var barMargins:",
                (self.paths.overlay_shell / "Ui" / "PluginBarApi.qml").read_text(),
            )
            self.assertIn(
                'export PATH="$OMARCHY_PATH/bin:$PATH"',
                self.paths.uwsm_override.read_text(),
            )

            self.assertEqual(apply_theme(self.paths, self.backend), "already applied")
            self.assertEqual(self.backend.builds, 1)

            state = __import__("json").loads(self.paths.state_file.read_text())
            state["overlay_input_sha256"] = "stale"
            self.paths.state_file.write_text(__import__("json").dumps(state))
            self.assertEqual(apply_theme(self.paths, self.backend), "applied")
            self.assertEqual(self.backend.builds, 2)

            self.assertEqual(restore_theme(self.paths, self.backend), "restored")
            self.assertEqual(self.backend.active, self.paths.system_omarchy)
            self.assertFalse(self.paths.uwsm_override.exists())

    def test_unknown_keyboard_panel_is_rejected_before_activation(self) -> None:
        with self.assertRaisesRegex(ThemeError, "not a validated Omarchy version"):
            apply_theme(self.paths, self.backend)
        self.assertEqual(self.backend.switches, [])
        self.assertFalse(self.paths.uwsm_override.exists())

    def test_host_change_is_rejected_even_when_overlay_would_be_reused(self) -> None:
        with patch("omarchy_setup.modules.theme.core.SUPPORTED_KEYBOARD_PANEL_SHA256", {self.digest}):
            apply_theme(self.paths, self.backend)
            before = self.paths.state_file.read_bytes()
            old_shell = (self.paths.overlay_shell / "shell.qml").read_bytes()
            source = self.paths.system_omarchy / "shell" / "services" / "PluginShellApi.qml"
            source.write_text(source.read_text() + "// upstream changed\n")
            with self.assertRaisesRegex(ThemeError, "unvalidated Omarchy host interface"):
                apply_theme(self.paths, self.backend)
            self.assertEqual(self.paths.state_file.read_bytes(), before)
            self.assertEqual((self.paths.overlay_shell / "shell.qml").read_bytes(), old_shell)
            self.assertEqual(self.backend.builds, 1)
            self.assertEqual(len(self.backend.switches), 1)

    def test_host_patch_is_scoped_and_keeps_stock_toast_fallback(self) -> None:
        with patch("omarchy_setup.modules.theme.core.SUPPORTED_KEYBOARD_PANEL_SHA256", {self.digest}):
            apply_theme(self.paths, self.backend)
        overlay = self.paths.overlay_shell
        host = (overlay / "shell.qml").read_text()
        self.assertIn("hasCurrentBarCapabilities()", host)
        self.assertIn("OlioHostedWidgets.create(shell, key, moduleName, parent, barApi)", host)
        service = (overlay / "plugins/notifications/Service.qml").read_text()
        self.assertIn("notificationPlacement !== undefined", service)
        self.assertIn(": NotificationLogic.popupPlacement(", service)
        self.assertNotIn("notificationPlacement", (self.paths.system_omarchy / "shell/plugins/notifications/Service.qml").read_text())

    def test_empty_uwsm_placeholder_is_reclaimed_but_foreign_content_is_not(self) -> None:
        self.paths.uwsm_override.parent.mkdir(parents=True)
        self.paths.uwsm_override.write_text("")
        with patch(
            "omarchy_setup.modules.theme.core.SUPPORTED_KEYBOARD_PANEL_SHA256",
            {self.digest},
        ):
            self.assertEqual(apply_theme(self.paths, self.backend), "applied")

        restore_theme(self.paths, self.backend)
        self.paths.uwsm_override.write_text("export UNRELATED=value\n")
        with self.assertRaisesRegex(ThemeError, "refusing to replace unrelated UWSM file"):
            apply_theme(self.paths, self.backend)

    def test_bar_styles_install_managed_sources_and_switch_shells(self) -> None:
        shell_config = self.paths.shell_config
        shell_config.parent.mkdir(parents=True)
        shell_config.write_text('{"idle": {"lock": 300}, "bar": {"transparent": false}}\n')

        with patch(
            "omarchy_setup.modules.theme.core.SUPPORTED_KEYBOARD_PANEL_SHA256",
            {self.digest},
        ):
            result = configure_theme(self.paths, self.backend, "floating")
        self.assertIn("floating bar configured", result)
        self.assertEqual(self.paths.user_theme.resolve(), self.paths.rendered_theme_assets.resolve())
        floating_shell = __import__("tomllib").loads(
            self.paths.user_theme.joinpath("shell.toml").read_text()
        )
        source_shell = __import__("tomllib").loads(
            self.paths.theme_assets.joinpath("shell.toml").read_text()
        )
        palette = __import__("tomllib").loads(
            self.paths.theme_assets.joinpath("colors.toml").read_text()
        )
        self.assertEqual(floating_shell["bar"]["background-alpha"], source_shell["bar"]["background-alpha"])
        self.assertEqual(floating_shell["popups"]["background-alpha"], source_shell["popups"]["background-alpha"])
        self.assertEqual(floating_shell["bar"]["background"], palette["dark_background"])
        self.assertEqual(floating_shell["popups"]["background"], palette["dark_background"])
        self.assertEqual(self.paths.user_bar_plugin.resolve(), self.paths.bar_plugin_source.resolve())
        self.assertEqual(self.paths.user_hypr_looknfeel.resolve(), self.paths.hypr_looknfeel_source.resolve())
        config = __import__("json").loads(shell_config.read_text())
        self.assertEqual(config["idle"]["lock"], 300)
        self.assertEqual(config["bar"]["id"], "olio.bar")
        self.assertEqual(config["bar"]["position"], "top")
        self.assertEqual(config["bar"]["style"], "floating")
        self.assertEqual(self.backend.active, self.paths.overlay_root)

        with patch(
            "omarchy_setup.modules.theme.core.SUPPORTED_KEYBOARD_PANEL_SHA256",
            {self.digest},
        ):
            result = configure_theme(self.paths, self.backend, "fixed")
        self.assertIn("fixed bar configured", result)
        self.assertEqual(self.backend.active, self.paths.overlay_root)
        fixed_shell = __import__("tomllib").loads(
            self.paths.user_theme.joinpath("shell.toml").read_text()
        )
        fixed_override = __import__("tomllib").loads(
            self.paths.theme_assets.joinpath("shell-fixed.toml").read_text()
        )
        self.assertEqual(fixed_shell["bar"]["background-alpha"], fixed_override["bar"]["background-alpha"])
        self.assertEqual(fixed_shell["popups"]["background-alpha"], fixed_override["popups"]["background-alpha"])
        self.assertEqual(len(self.backend.themes), 2)
        self.assertEqual(self.backend.restarts, [self.paths.overlay_root])
        config = __import__("json").loads(shell_config.read_text())
        self.assertEqual(config["bar"]["style"], "fixed")
        self.assertGreaterEqual(self.backend.hyprland_validations, 2)

    def test_same_mode_theme_change_restarts_existing_overlay(self) -> None:
        self.paths.shell_config.parent.mkdir(parents=True)
        self.paths.shell_config.write_text('{"bar": {"transparent": false}}\n')

        with patch(
            "omarchy_setup.modules.theme.core.SUPPORTED_KEYBOARD_PANEL_SHA256",
            {self.digest},
        ):
            configure_theme(self.paths, self.backend, "fixed")
            state = __import__("json").loads(self.paths.state_file.read_text())
            state["theme_assets_sha256"] = "stale"
            self.paths.state_file.write_text(__import__("json").dumps(state))

            result = configure_theme(self.paths, self.backend, "fixed")

        self.assertIn("shell restarted", result)
        self.assertEqual(self.backend.restarts, [self.paths.overlay_root])
        self.assertEqual(len(self.backend.themes), 2)

    def test_theme_defaults_to_fixed_and_accepts_floating(self) -> None:
        fixed = build_parser().parse_args(["theme", "-y"])
        floating = build_parser().parse_args(["theme", "bar-floating", "-y"])

        self.assertEqual(fixed.action, "bar-fixed")
        self.assertEqual(floating.action, "bar-floating")

    def test_companion_plugins_replace_workspaces_only_after_spaces_is_enabled(self) -> None:
        plugins = self.paths.home / ".config" / "omarchy" / "plugins"
        for plugin_id in (OMASTORM_ID, NOTIFICATION_CENTER_ID):
            target = plugins / plugin_id
            target.mkdir(parents=True)
            target.joinpath("manifest.json").write_text("{}\n")

        commands: list[tuple[str, ...]] = []

        def record(command: tuple[str, ...], **_kwargs: object) -> str:
            commands.append(command)
            return ""

        with patch("omarchy_setup.modules.theme.core._run", side_effect=record):
            OmarchyThemeBackend().ensure_companion_plugins(self.paths)

        spaces_add = next(i for i, command in enumerate(commands) if command[:3] == ("omarchy", "plugin", "add"))
        spaces_enable = commands.index(
            (
                "omarchy", "plugin", "enable", SPACES_ID,
                "--section", "left", "--after", "omarchy.menu",
            )
        )
        stock_disable = commands.index(("omarchy", "plugin", "disable", "omarchy.workspaces"))
        self.assertLess(spaces_add, spaces_enable)
        self.assertLess(spaces_enable, stock_disable)
        self.assertFalse(any(command[:3] == ("omarchy", "plugin", "add") and OMASTORM_ID in command for command in commands))
        self.assertFalse(any(command[:3] == ("omarchy", "plugin", "add") and NOTIFICATION_CENTER_ID in command for command in commands))

    def test_companion_failure_does_not_disable_stock_workspaces(self) -> None:
        commands: list[tuple[str, ...]] = []

        def fail_spaces(command: tuple[str, ...], **_kwargs: object) -> str:
            commands.append(command)
            if command[:3] == ("omarchy", "plugin", "add"):
                raise ThemeError("plugin install failed")
            return ""

        with patch("omarchy_setup.modules.theme.core._run", side_effect=fail_spaces):
            with self.assertRaisesRegex(ThemeError, "plugin install failed"):
                OmarchyThemeBackend().ensure_companion_plugins(self.paths)

        self.assertNotIn(("omarchy", "plugin", "disable", "omarchy.workspaces"), commands)

    def test_failed_activation_restores_existing_user_files(self) -> None:
        self.paths.user_theme.mkdir(parents=True)
        self.paths.user_theme.joinpath("original-theme").write_text("keep\n")
        self.paths.user_bar_plugin.mkdir(parents=True)
        self.paths.user_bar_plugin.joinpath("original-plugin").write_text("keep\n")
        self.paths.user_hypr_looknfeel.parent.mkdir(parents=True)
        self.paths.user_hypr_looknfeel.write_text("original look and feel\n")
        self.paths.shell_config.parent.mkdir(parents=True, exist_ok=True)
        original_shell = '{"bar": {"id": "original.bar"}}\n'
        self.paths.shell_config.write_text(original_shell)

        def fail_theme(_name: str, *, preserve_background: bool = False) -> None:
            raise ThemeError("theme activation failed")

        self.backend.set_theme = fail_theme  # type: ignore[method-assign]
        with self.assertRaisesRegex(ThemeError, "activation failed"):
            configure_theme(self.paths, self.backend, "floating")

        self.assertFalse(self.paths.user_theme.is_symlink())
        self.assertTrue(self.paths.user_theme.joinpath("original-theme").is_file())
        self.assertFalse(self.paths.user_bar_plugin.is_symlink())
        self.assertTrue(self.paths.user_bar_plugin.joinpath("original-plugin").is_file())
        self.assertEqual(self.paths.user_hypr_looknfeel.read_text(), "original look and feel\n")
        self.assertEqual(self.paths.shell_config.read_text(), original_shell)


if __name__ == "__main__":
    unittest.main()
