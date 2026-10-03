from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

from omarchy_setup.progress import ProgressDisplay
from omarchy_setup.modules.theme import host_integration


THEME_NAME = "olio-su-silicio"
OMASTORM_ID = "com.omastorm.radar"
OMASTORM_URL = "https://github.com/wesleygrimes/omastorm.git"
NOTIFICATION_CENTER_ID = "jankeesvw.notification-center"
NOTIFICATION_CENTER_URL = "https://github.com/jankeesvw/omarchy-notification-center.git"
SPACES_ID = "tornikegomareli.spaces"
SPACES_URL = "https://github.com/tornikegomareli/omarchy-spaces.git"
CARD_MARKER = "  // --- card ----------------------------------------------------------------"
UWSM_MARKER = "# Managed by omarchy-setup theme"
SUPPORTED_KEYBOARD_PANEL_SHA256 = {
    "96245f2da8d38baa0017caa285d596c485bd19a3a4d2cd1675bee9d84ffba42d",
}
SUPPORTED_PLUGIN_BAR_API_SHA256 = {
    "91964a42b92c58476a4f961df35148d4c94071344ef1a69eab1563d1496705a7",
}


class ThemeError(RuntimeError):
    """A user-facing theme compatibility or activation failure."""


def _validate_theme_toml(path: Path) -> None:
    try:
        tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ThemeError(f"invalid theme TOML {path}: {error}") from error


def _toml_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise ThemeError(f"unsupported mode-specific theme value: {value!r}")


def _merge_toml_override(base: str, override: str) -> str:
    base_values = tomllib.loads(base)
    override_values = tomllib.loads(override)
    replacements: dict[tuple[str, str], object] = {}
    for section, values in override_values.items():
        if not isinstance(values, dict) or not isinstance(base_values.get(section), dict):
            raise ThemeError(f"unknown shell theme section in mode override: {section}")
        for key, value in values.items():
            if key not in base_values[section]:
                raise ThemeError(f"unknown shell theme key in mode override: {section}.{key}")
            replacements[(section, key)] = value

    lines = base.splitlines()
    section = ""
    replaced: set[tuple[str, str]] = set()
    for index, line in enumerate(lines):
        section_match = re.match(r"^\s*\[([A-Za-z0-9_-]+)\]\s*$", line)
        if section_match:
            section = section_match.group(1)
            continue
        key_match = re.match(r"^(\s*)([A-Za-z0-9_-]+)\s*=", line)
        if not key_match:
            continue
        pair = (section, key_match.group(2))
        if pair in replacements:
            lines[index] = f"{key_match.group(1)}{pair[1]} = {_toml_literal(replacements[pair])}"
            replaced.add(pair)

    missing = sorted(set(replacements) - replaced)
    if missing:
        names = ", ".join(f"{section}.{key}" for section, key in missing)
        raise ThemeError(f"shell theme override keys were not found in source text: {names}")
    merged = "\n".join(lines) + "\n"
    tomllib.loads(merged)
    return merged


def _resolve_palette_references(shell: str, colors: str) -> str:
    """Resolve quoted ``palette.<key>`` values from the native colors.toml."""
    palette = tomllib.loads(colors)
    pattern = re.compile(
        r'^(?P<prefix>\s*[A-Za-z0-9_-]+\s*=\s*)["\']palette\.(?P<key>[A-Za-z0-9_-]+)["\']'
        r'(?P<suffix>\s*(?:#.*)?)$',
        re.MULTILINE,
    )

    def replace(match: re.Match[str]) -> str:
        key = match.group("key")
        value = palette.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?", value):
            raise ThemeError(f"unknown or non-color palette reference in shell theme: palette.{key}")
        return f'{match.group("prefix")}{json.dumps(value)}{match.group("suffix")}'

    rendered = pattern.sub(replace, shell)
    unresolved = re.findall(r'["\']palette\.([A-Za-z0-9_-]+)["\']', rendered)
    if unresolved:
        raise ThemeError(f"unresolved palette reference in shell theme: palette.{unresolved[0]}")
    tomllib.loads(rendered)
    return rendered


@dataclass(frozen=True)
class ThemePaths:
    repo_root: Path
    state_root: Path
    home: Path
    system_omarchy: Path = Path("/usr/share/omarchy")

    @classmethod
    def for_user(cls) -> "ThemePaths":
        configured_root = os.environ.get("OMARCHY_SETUP_ROOT")
        repo_root = (
            Path(configured_root).resolve()
            if configured_root
            else Path(__file__).resolve().parents[4]
        )
        state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        return cls(repo_root, state_home / "omarchy-setup", Path.home())

    @property
    def theme_root(self) -> Path:
        return self.state_root / "themes" / THEME_NAME

    @property
    def overlay_root(self) -> Path:
        return self.theme_root / "omarchy"

    @property
    def overlay_shell(self) -> Path:
        return self.overlay_root / "shell"

    @property
    def state_file(self) -> Path:
        return self.theme_root / "state.json"

    @property
    def uv(self) -> Path:
        return self.state_root / "bin" / "uv"

    @property
    def keyboard_panel_template(self) -> Path:
        return self.repo_root / "themes" / THEME_NAME / "shell" / "KeyboardPanel.qml"

    @property
    def launcher_template(self) -> Path:
        return self.repo_root / "themes" / THEME_NAME / "bin" / "omarchy-launch-shell"

    @property
    def theme_assets(self) -> Path:
        return self.repo_root / "themes" / THEME_NAME / "omarchy-theme"

    @property
    def rendered_theme_assets(self) -> Path:
        return self.theme_root / "rendered-theme"

    @property
    def bar_plugin_source(self) -> Path:
        return self.repo_root / "themes" / THEME_NAME / "plugins" / "olio.bar"

    @property
    def user_theme(self) -> Path:
        return self.home / ".config" / "omarchy" / "themes" / THEME_NAME

    @property
    def user_bar_plugin(self) -> Path:
        return self.home / ".config" / "omarchy" / "plugins" / "olio.bar"

    @property
    def legacy_user_bar_plugin(self) -> Path:
        return self.home / ".config" / "omarchy" / "plugins" / "paolo.bar"

    @property
    def bar_config(self) -> Path:
        return self.bar_plugin_source / "bar.toml"

    @property
    def shell_config(self) -> Path:
        return self.home / ".config" / "omarchy" / "shell.json"

    @property
    def codex_hooks(self) -> Path:
        return self.home / ".codex" / "hooks.json"

    @property
    def claude_settings(self) -> Path:
        return self.home / ".claude" / "settings.json"

    @property
    def current_theme_name(self) -> Path:
        return self.home / ".local" / "state" / "omarchy" / "current" / "theme.name"

    @property
    def current_theme(self) -> Path:
        return self.home / ".local" / "state" / "omarchy" / "current" / "theme"

    @property
    def current_background(self) -> Path:
        return self.home / ".local" / "state" / "omarchy" / "current" / "background"

    @property
    def backups_root(self) -> Path:
        return self.theme_root / "backups"

    @property
    def hypr_looknfeel_source(self) -> Path:
        return self.repo_root / "dotfiles" / "hypr" / "looknfeel.lua"

    @property
    def user_hypr_looknfeel(self) -> Path:
        return self.home / ".config" / "hypr" / "looknfeel.lua"

    @property
    def blobs_source(self) -> Path:
        return self.repo_root / "vendor" / "caelestia-blobs"

    @property
    def uwsm_override(self) -> Path:
        return self.home / ".config" / "uwsm" / "env.d" / "90-omarchy-setup-theme"


class ThemeBackend(Protocol):
    def build_blobs(self, paths: ThemePaths, destination: Path) -> None: ...

    def validate_overlay(self, overlay_shell: Path) -> None: ...

    def switch_shell(self, target_root: Path, previous_root: Path) -> None: ...

    def restart_shell(self, target_root: Path) -> None: ...

    def active_omarchy_path(self) -> Path | None: ...

    def validate_bar_plugin(self, source: Path) -> None: ...

    def set_theme(self, name: str, *, preserve_background: bool = False) -> None: ...

    def validate_hyprland(self) -> None: ...

    def ensure_companion_plugins(self, paths: ThemePaths) -> None: ...


def _run(command: tuple[str, ...], *, environment: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            details = (error.stderr or error.stdout or "command failed").strip().splitlines()
            message = details[-1] if details else "command failed"
        else:
            message = str(error)
        raise ThemeError(f"{' '.join(command)}: {message}") from error
    return result.stdout.strip()


def _run_plugin_command(
    command: tuple[str, ...], *, environment: dict[str, str], attempts: int = 4
) -> str:
    """Retry only transient shell-startup failures from Omarchy plugin IPC."""
    for attempt in range(attempts):
        try:
            return _run(command, environment=environment)
        except ThemeError as error:
            if "omarchy-shell is not responding" not in str(error) or attempt == attempts - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise AssertionError("unreachable")


class OmarchyThemeBackend:
    def build_blobs(self, paths: ThemePaths, destination: Path) -> None:
        if not paths.uv.is_file():
            raise ThemeError("uv is not initialized; run 'omarchy-setup init' first")
        if not paths.blobs_source.joinpath("CMakeLists.txt").is_file():
            raise ThemeError(f"missing vendored Caelestia Blobs source: {paths.blobs_source}")

        paths.theme_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="blobs-build-", dir=paths.theme_root) as temporary:
            build = Path(temporary) / "build"
            environment = os.environ.copy()
            environment.update(
                {
                    "UV_CACHE_DIR": str(paths.state_root / "uv-cache"),
                    "UV_TOOL_DIR": str(paths.state_root / "uv-tools"),
                    "UV_TOOL_BIN_DIR": str(paths.state_root / "uv-tool-bin"),
                }
            )
            base = (str(paths.uv), "tool", "run", "cmake")
            _run(
                base
                + (
                    "-S",
                    str(paths.blobs_source),
                    "-B",
                    str(build),
                    "-G",
                    "Unix Makefiles",
                    "-DCMAKE_BUILD_TYPE=Release",
                ),
                environment=environment,
            )
            _run(base + ("--build", str(build), "--parallel", "4"), environment=environment)
            module = build / "qml" / "Caelestia" / "Blobs"
            if not module.joinpath("libcaelestia-blobsplugin.so").is_file():
                raise ThemeError("Caelestia Blobs build did not produce its QML plugin")
            shutil.copytree(module, destination)

    def validate_overlay(self, overlay_shell: Path) -> None:
        keyboard_panel = overlay_shell / "Ui" / "KeyboardPanel.qml"
        qmllint = Path("/usr/lib/qt6/bin/qmllint")
        if not qmllint.is_file():
            raise ThemeError("Qt qmllint is unavailable")
        _run((str(qmllint), "-I", str(overlay_shell), str(keyboard_panel)))
        _run((str(qmllint), "-I", str(overlay_shell),
              str(overlay_shell / "services" / "OlioHostedBarWidget.qml")))
        plugin = overlay_shell / "Caelestia" / "Blobs" / "libcaelestia-blobsplugin.so"
        dependencies = _run(("ldd", str(plugin)))
        if "not found" in dependencies:
            raise ThemeError("Caelestia Blobs has unresolved shared-library dependencies")

    def validate_bar_plugin(self, source: Path) -> None:
        _run(("omarchy", "plugin", "validate", str(source)))

    def ensure_companion_plugins(self, paths: ThemePaths) -> None:
        """Install the theme's managed bar widgets once, then keep placement stable."""
        active = self.active_omarchy_path() or paths.system_omarchy
        environment = os.environ.copy()
        environment["OMARCHY_PATH"] = str(active)
        environment["QML2_IMPORT_PATH"] = str(active / "shell")
        plugins_root = paths.home / ".config" / "omarchy" / "plugins"
        companions = (
            (SPACES_ID, SPACES_URL, ("--section", "left", "--after", "omarchy.menu")),
            (OMASTORM_ID, OMASTORM_URL, ("--section", "center", "--after", "omarchy.weather")),
            (NOTIFICATION_CENTER_ID, NOTIFICATION_CENTER_URL, ("--section", "right", "--after", "omarchy.power")),
        )
        for plugin_id, url, placement in companions:
            manifest = plugins_root / plugin_id / "manifest.json"
            if not manifest.is_file():
                _run_plugin_command(
                    ("omarchy", "plugin", "add", url, "--enable", "--yes"),
                    environment=environment,
                )
            _run_plugin_command(
                ("omarchy", "plugin", "enable", plugin_id, *placement),
                environment=environment,
            )

        _ensure_spaces_agent_hooks(paths)

        # Do this only after Spaces is installed and enabled. If any earlier
        # step fails, Omarchy's built-in workspace switcher remains available.
        _run_plugin_command(
            ("omarchy", "plugin", "disable", "omarchy.workspaces"),
            environment=environment,
        )

    def set_theme(self, name: str, *, preserve_background: bool = False) -> None:
        environment = os.environ.copy()
        if preserve_background:
            environment["OMARCHY_THEME_SKIP_BACKGROUND"] = "1"
        _run(("omarchy", "theme", "set", name), environment=environment)

    def validate_hyprland(self) -> None:
        _run(("hyprctl", "reload"))
        errors = _run(("hyprctl", "configerrors"))
        if errors:
            raise ThemeError(f"Hyprland configuration errors:\n{errors}")

    @staticmethod
    def _set_environment(target_root: Path) -> None:
        shell = target_root / "shell"
        current_path = os.environ.get("PATH", "/usr/local/bin:/usr/bin")
        target_bin = str(target_root / "bin")
        entries = [entry for entry in current_path.split(":") if entry and entry != target_bin]
        path = ":".join([target_bin, *entries])
        _run(
            (
                "systemctl",
                "--user",
                "set-environment",
                f"OMARCHY_PATH={target_root}",
                f"QML2_IMPORT_PATH={shell}",
                f"PATH={path}",
            )
        )
        # Current Omarchy uses Hyprland's Lua environment API.  `keyword env`
        # is rejected by the non-legacy parser and, more importantly, does not
        # update the environment inherited by keybind dispatchers.  Keep the
        # legacy command as a fallback for older Omarchy releases.
        env_code = "; ".join(
            f"hl.env({json.dumps(name)}, {json.dumps(value)})"
            for name, value in (("OMARCHY_PATH", str(target_root)), ("QML2_IMPORT_PATH", str(shell)), ("PATH", path))
        )
        try:
            _run(("hyprctl", "eval", env_code))
        except ThemeError:
            _run(("hyprctl", "keyword", "env", f"OMARCHY_PATH,{target_root}"))
            _run(("hyprctl", "keyword", "env", f"QML2_IMPORT_PATH,{shell}"))
            _run(("hyprctl", "keyword", "env", f"PATH,{path}"))

    @staticmethod
    def _kill_shell(root: Path) -> None:
        subprocess.run(
            ("quickshell", "kill", "-p", str(root / "shell"), "--any-display"),
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def _launch_shell(target_root: Path) -> None:
        shell = target_root / "shell"
        launcher = "/usr/share/omarchy/bin/omarchy-launch-shell"
        command = (
            f"env OMARCHY_PATH={shlex.quote(str(target_root))} "
            f"QML2_IMPORT_PATH={shlex.quote(str(shell))} {launcher}"
        )
        _run(("hyprctl", "dispatch", f"hl.dsp.exec_cmd({json.dumps(command)})"))

        environment = os.environ.copy()
        environment["OMARCHY_PATH"] = str(target_root)
        environment["QML2_IMPORT_PATH"] = str(shell)
        last_error: ThemeError | None = None
        for _ in range(50):
            try:
                _run(("omarchy-shell", "shell", "ping"), environment=environment)
                return
            except ThemeError as error:
                last_error = error
                time.sleep(0.1)
        raise last_error or ThemeError("Omarchy shell did not become ready")

    def switch_shell(self, target_root: Path, previous_root: Path) -> None:
        try:
            self._kill_shell(previous_root)
            self._kill_shell(target_root)
            self._set_environment(target_root)
            self._launch_shell(target_root)
        except ThemeError:
            self._set_environment(previous_root)
            self._kill_shell(target_root)
            self._kill_shell(previous_root)
            try:
                self._launch_shell(previous_root)
            except ThemeError:
                pass
            raise

    def restart_shell(self, target_root: Path) -> None:
        # Theme IPC updates do not reliably refresh colors already captured by
        # long-lived bar objects. Recreate the shell after an effective theme
        # change so the bar and newly opened panels use one configuration
        # generation.
        self.switch_shell(target_root, target_root)

    def active_omarchy_path(self) -> Path | None:
        try:
            output = _run(("quickshell", "list", "--all"))
            matches = re.findall(r"^\s*Config path:\s*(.+?)/shell/shell\.qml\s*$", output, re.MULTILINE)
            if matches:
                return Path(matches[-1])
        except ThemeError:
            pass
        try:
            output = _run(("systemctl", "--user", "show-environment"))
        except ThemeError:
            return None
        for line in output.splitlines():
            if line.startswith("OMARCHY_PATH="):
                return Path(line.partition("=")[2])
        return None


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.is_dir():
        return ""
    for path in sorted((path for path in root.rglob("*") if path.is_file()), key=lambda value: str(value)):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _render_theme_assets(paths: ThemePaths, style: str) -> None:
    paths.theme_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="theme-render-", dir=paths.theme_root) as temporary:
        staged = Path(temporary) / "theme"
        shutil.copytree(paths.theme_assets, staged)
        rendered_shell = _resolve_palette_references(
            (paths.theme_assets / "shell.toml").read_text(),
            (paths.theme_assets / "colors.toml").read_text(),
        )
        if style == "fixed":
            override = paths.theme_assets / "shell-fixed.toml"
            if not override.is_file():
                raise ThemeError(f"fixed shell theme override is missing: {override}")
            rendered_shell = _merge_toml_override(rendered_shell, override.read_text())
        (staged / "shell.toml").write_text(rendered_shell)

        rendered = paths.rendered_theme_assets
        previous = rendered.with_name(rendered.name + ".previous")
        if previous.exists():
            shutil.rmtree(previous)
        if rendered.exists():
            rendered.rename(previous)
        try:
            staged.rename(rendered)
        except Exception:
            if previous.exists():
                previous.rename(rendered)
            raise
        if previous.exists():
            shutil.rmtree(previous)


@dataclass(frozen=True)
class ManagedLinkChange:
    target: Path
    backup: Path | None


def _ensure_managed_link(source: Path, target: Path, backups_root: Path) -> ManagedLinkChange | None:
    if not source.exists():
        raise ThemeError(f"managed source is missing: {source}")
    if target.is_symlink() and target.resolve() == source.resolve():
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    backups_root.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if target.exists() or target.is_symlink():
        backup = backups_root / f"{target.name}.{time.time_ns()}"
        shutil.move(str(target), str(backup))
    try:
        target.symlink_to(source.resolve(), target_is_directory=source.is_dir())
    except OSError as error:
        if backup is not None and backup.exists():
            shutil.move(str(backup), str(target))
        raise ThemeError(f"could not link {target} to {source}: {error}") from error
    return ManagedLinkChange(target, backup)


def _rollback_managed_link(change: ManagedLinkChange) -> None:
    if change.target.is_symlink():
        change.target.unlink()
    if change.backup is not None and change.backup.exists():
        shutil.move(str(change.backup), str(change.target))


def _configure_bar(paths: ThemePaths, style: str) -> bytes | None:
    previous = paths.shell_config.read_bytes() if paths.shell_config.is_file() else None
    try:
        config = json.loads(previous.decode() if previous is not None else "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ThemeError(f"invalid Omarchy shell configuration: {paths.shell_config}") from error
    if not isinstance(config, dict):
        raise ThemeError(f"Omarchy shell configuration must be an object: {paths.shell_config}")
    bar = config.setdefault("bar", {})
    if not isinstance(bar, dict):
        raise ThemeError("Omarchy shell 'bar' configuration must be an object")
    bar["id"] = "olio.bar"
    bar["position"] = "top"
    bar["style"] = style
    content = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    if previous is not None and previous.decode() == content:
        return previous
    _write_atomic(paths.shell_config, content)
    return previous


def _restore_file(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".rollback")
    temporary.write_bytes(previous)
    os.replace(temporary, path)


def _overlay_input_digest(paths: ThemePaths) -> str:
    digest = hashlib.sha256()
    inputs = [Path(__file__), Path(host_integration.__file__), paths.launcher_template]
    inputs.extend(path for path in paths.keyboard_panel_template.parent.iterdir() if path.is_file())
    inputs.extend(path for path in paths.blobs_source.rglob("*") if path.is_file())
    for path in sorted(inputs, key=lambda value: str(value)):
        digest.update(str(path.relative_to(paths.repo_root) if path.is_relative_to(paths.repo_root) else path).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".next")
    temporary.write_text(content)
    os.replace(temporary, path)


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ThemeError(f"invalid {label} configuration: {path}") from error
    if not isinstance(value, dict):
        raise ThemeError(f"{label} configuration must be an object: {path}")
    return value


def _append_command_hook(
    config: dict[str, object], event: str, command: str, *, timeout: int = 3
) -> None:
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ThemeError("agent hooks configuration must be an object")
    groups = hooks.setdefault(event, [])
    if not isinstance(groups, list):
        raise ThemeError(f"agent hook event {event} must be a list")

    for group in groups:
        if not isinstance(group, dict):
            continue
        handlers = group.get("hooks", [])
        if isinstance(handlers, list) and any(
            isinstance(handler, dict)
            and handler.get("type") == "command"
            and handler.get("command") == command
            for handler in handlers
        ):
            return

    groups.append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "async": True,
                    "timeout": timeout,
                }
            ]
        }
    )


def _ensure_spaces_agent_hooks(paths: ThemePaths) -> None:
    reporter = (
        paths.home
        / ".config"
        / "omarchy"
        / "plugins"
        / SPACES_ID
        / "hooks"
        / "claude-hook"
    )
    if not reporter.is_file():
        raise ThemeError(f"Spaces agent reporter is missing: {reporter}")

    base = shlex.quote(str(reporter))
    codex = _read_json_object(paths.codex_hooks, "Codex hooks")
    for event, state in (
        ("UserPromptSubmit", "working"),
        ("PostToolUse", "working"),
        ("PermissionRequest", "waiting"),
        # Codex has no general Notification hook. A stopped turn needs the
        # user's attention, whether it ended with a question or an answer.
        ("Stop", "waiting"),
        ("SessionEnd", "end"),
    ):
        _append_command_hook(codex, event, f"{base} {state}")

    claude = _read_json_object(paths.claude_settings, "Claude")
    for event, state in (
        ("UserPromptSubmit", "working"),
        ("PostToolUse", "working"),
        ("Notification", "waiting"),
        ("Stop", "done"),
        ("SessionEnd", "end"),
    ):
        _append_command_hook(claude, event, f"{base} {state}")

    _write_atomic(paths.codex_hooks, json.dumps(codex, indent=2, ensure_ascii=False) + "\n")
    _write_atomic(paths.claude_settings, json.dumps(claude, indent=2, ensure_ascii=False) + "\n")


def _install_liquid_ui(paths: ThemePaths, source: Path, ui_directory: Path) -> None:
    digest = _digest(source)
    if digest not in SUPPORTED_KEYBOARD_PANEL_SHA256:
        raise ThemeError(
            "installed KeyboardPanel is not a validated Omarchy version; "
            "restore stock or update the omarchy-setup compatibility template"
        )
    if not paths.keyboard_panel_template.is_file():
        raise ThemeError("liquid KeyboardPanel template is missing")
    shutil.copy2(paths.keyboard_panel_template, ui_directory / "KeyboardPanel.qml")

    plugin_api = ui_directory / "PluginBarApi.qml"
    plugin_api_text = plugin_api.read_text()
    if "property var barMargins:" not in plugin_api_text:
        if _digest(plugin_api) not in SUPPORTED_PLUGIN_BAR_API_SHA256:
            raise ThemeError("installed PluginBarApi is not a validated Omarchy version")
        marker = "  property int barSize: 0\n"
        if marker not in plugin_api_text:
            raise ThemeError("installed PluginBarApi has no barSize compatibility marker")
        plugin_api.write_text(
            plugin_api_text.replace(
                marker,
                marker + "  property var barMargins: ({ top: 0, right: 0, bottom: 0, left: 0 })\n",
                1,
            )
        )
        plugin_api_text = plugin_api.read_text()
    if "function reportPopoutGeometry(" not in plugin_api_text:
        markers = {
            "  property var _releasePopout: null\n": (
                "  property var _releasePopout: null\n"
                "  property var _reportPopoutGeometry: null\n"
                "  property var _popoutTransitionFor: null\n"
            ),
            "  function switchPanelFrom(owner, direction) {\n": (
                "  function reportPopoutGeometry(owner, geometry) {\n"
                "    if (_reportPopoutGeometry) _reportPopoutGeometry(owner, geometry)\n"
                "  }\n\n"
                "  function popoutTransitionFor(screenName) {\n"
                "    return _popoutTransitionFor ? _popoutTransitionFor(String(screenName || \"\")) : null\n"
                "  }\n\n"
                "  function switchPanelFrom(owner, direction) {\n"
            ),
        }
        for marker, replacement in markers.items():
            if plugin_api_text.count(marker) != 1:
                raise ThemeError("installed PluginBarApi has no popup transition compatibility marker")
            plugin_api_text = plugin_api_text.replace(marker, replacement, 1)
        plugin_api.write_text(plugin_api_text)


def _build_overlay(paths: ThemePaths, backend: ThemeBackend, staging: Path) -> str:
    system_shell = paths.system_omarchy / "shell"
    source_panel = system_shell / "Ui" / "KeyboardPanel.qml"
    if not source_panel.is_file():
        raise ThemeError(f"Omarchy KeyboardPanel not found: {source_panel}")
    staging.mkdir(parents=True)
    for child in paths.system_omarchy.iterdir():
        if child.name == "shell":
            continue
        if child.name == "bin":
            overlay_bin = staging / "bin"
            overlay_bin.mkdir()
            for command in child.iterdir():
                if command.name != "omarchy-launch-shell":
                    (overlay_bin / command.name).symlink_to(command)
            if not paths.launcher_template.is_file():
                raise ThemeError(f"overlay launcher template not found: {paths.launcher_template}")
            launcher = overlay_bin / "omarchy-launch-shell"
            shutil.copy2(paths.launcher_template, launcher)
            launcher.chmod(0o755)
        else:
            (staging / child.name).symlink_to(child, target_is_directory=child.is_dir())
    shutil.copytree(system_shell, staging / "shell")
    _install_liquid_ui(paths, source_panel, staging / "shell" / "Ui")
    try:
        host_integration.install(staging / "shell", paths.keyboard_panel_template.parent)
    except ValueError as error:
        raise ThemeError(str(error)) from error
    module = staging / "shell" / "Caelestia" / "Blobs"
    module.parent.mkdir(parents=True, exist_ok=True)
    backend.build_blobs(paths, module)
    backend.validate_overlay(staging / "shell")
    return _digest(source_panel)


def _managed_override(paths: ThemePaths) -> str:
    return (
        f"{UWSM_MARKER}\n"
        f"export OMARCHY_PATH={json.dumps(str(paths.overlay_root))}\n"
        f"export QML2_IMPORT_PATH={json.dumps(str(paths.overlay_shell))}\n"
        'export PATH="$OMARCHY_PATH/bin:$PATH"\n'
    )


def _check_override(paths: ThemePaths) -> None:
    if not paths.uwsm_override.exists():
        return
    content = paths.uwsm_override.read_text()
    # UWSM may recreate a removed environment fragment as an empty no-op file.
    # The filename is private to this module, so an empty placeholder is safe
    # to reclaim; non-empty foreign content remains protected.
    if content and not content.startswith(UWSM_MARKER):
        raise ThemeError(f"refusing to replace unrelated UWSM file: {paths.uwsm_override}")


def apply_theme(paths: ThemePaths, backend: ThemeBackend) -> str:
    _check_override(paths)
    try:
        host_integration.validate_sources(paths.system_omarchy / "shell")
    except ValueError as error:
        raise ThemeError(str(error)) from error
    source_panel = paths.system_omarchy / "shell" / "Ui" / "KeyboardPanel.qml"
    source_digest = _digest(source_panel) if source_panel.is_file() else ""
    overlay_input_digest = _overlay_input_digest(paths)
    if paths.state_file.is_file() and paths.overlay_shell.is_dir():
        state = json.loads(paths.state_file.read_text())
        if (
            state.get("active") is True
            and state.get("source_keyboard_panel_sha256") == source_digest
            and state.get("overlay_input_sha256") == overlay_input_digest
            and paths.uwsm_override.is_file()
            and paths.uwsm_override.read_text() == _managed_override(paths)
            and backend.active_omarchy_path() == paths.overlay_root
        ):
            backend.validate_overlay(paths.overlay_shell)
            return "already applied"

    paths.theme_root.mkdir(parents=True, exist_ok=True)
    staging = paths.theme_root / "omarchy.next"
    previous = paths.theme_root / "omarchy.previous"
    shutil.rmtree(staging, ignore_errors=True)
    built_digest = _build_overlay(paths, backend, staging)

    if previous.exists():
        shutil.rmtree(previous)
    if paths.overlay_root.exists():
        os.replace(paths.overlay_root, previous)
    os.replace(staging, paths.overlay_root)
    _write_atomic(paths.uwsm_override, _managed_override(paths))

    try:
        backend.switch_shell(paths.overlay_root, paths.system_omarchy)
    except ThemeError:
        paths.uwsm_override.unlink(missing_ok=True)
        if paths.overlay_root.exists():
            shutil.rmtree(paths.overlay_root)
        if previous.exists():
            os.replace(previous, paths.overlay_root)
        raise

    state = json.loads(paths.state_file.read_text()) if paths.state_file.is_file() else {}
    state.update({
        "active": True,
        "theme": THEME_NAME,
        "source_keyboard_panel_sha256": built_digest,
        "overlay_input_sha256": overlay_input_digest,
        "overlay_root": str(paths.overlay_root),
    })
    _write_atomic(paths.state_file, json.dumps(state, indent=2, sort_keys=True) + "\n")
    shutil.rmtree(previous, ignore_errors=True)
    return "applied"


def restore_theme(paths: ThemePaths, backend: ThemeBackend) -> str:
    _check_override(paths)
    active = backend.active_omarchy_path()
    if active != paths.overlay_root and not paths.uwsm_override.exists():
        return "already restored"
    backend.switch_shell(paths.system_omarchy, paths.overlay_root)
    paths.uwsm_override.unlink(missing_ok=True)
    if paths.state_file.exists():
        state = json.loads(paths.state_file.read_text())
        state["active"] = False
        _write_atomic(paths.state_file, json.dumps(state, indent=2, sort_keys=True) + "\n")
    return "restored"


def theme_status(paths: ThemePaths, backend: ThemeBackend) -> str:
    active = backend.active_omarchy_path()
    if active != paths.overlay_root:
        if paths.state_file.is_file():
            state = json.loads(paths.state_file.read_text())
            if state.get("bar_style") == "floating":
                return "floating bar active on stock Omarchy shell"
        return "inactive (stock Omarchy shell)"
    source_panel = paths.system_omarchy / "shell" / "Ui" / "KeyboardPanel.qml"
    if not paths.state_file.is_file() or not source_panel.is_file():
        return "active, but state is incomplete"
    state = json.loads(paths.state_file.read_text())
    if state.get("source_keyboard_panel_sha256") != _digest(source_panel):
        return "active, but Omarchy changed; run 'omarchy-setup theme apply'"
    state = json.loads(paths.state_file.read_text())
    style = state.get("bar_style", "fixed")
    return f"{style} bar active and compatible"


def _validate_bar_config(path: Path) -> None:
    try:
        with path.open("rb") as config_file:
            data = tomllib.load(config_file)
    except FileNotFoundError as error:
        raise ThemeError(f"bar configuration is missing: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ThemeError(f"invalid TOML in {path}: {error}") from error

    if data.get("schema_version") != 1:
        raise ThemeError("unsupported bar.toml schema_version; expected 1")
    expected = {
        ("bar", "height"): (16, 96),
        ("bar", "vertical_width"): (16, 96),
        ("floating", "edge_margin"): (0, 64),
        ("floating", "side_margin"): (0, 64),
        ("floating", "popup_gap"): (0, 64),
    }
    for (section, key), (minimum, maximum) in expected.items():
        table = data.get(section)
        value = table.get(key) if isinstance(table, dict) else None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ThemeError(f"bar.toml {section}.{key} must be an integer")
        if not minimum <= value <= maximum:
            raise ThemeError(
                f"bar.toml {section}.{key} must be between {minimum} and {maximum}"
            )


def _current_background_survives_refresh(paths: ThemePaths) -> bool:
    if not paths.current_background.is_symlink():
        return False
    current = paths.current_background.resolve(strict=False)
    try:
        relative = current.relative_to(paths.current_theme)
    except ValueError:
        return current.is_file()
    return paths.theme_assets.joinpath(relative).is_file()


def _retire_legacy_bar_link(paths: ThemePaths) -> None:
    legacy = paths.legacy_user_bar_plugin
    if not legacy.is_symlink():
        return
    target = legacy.resolve(strict=False)
    legacy_source = paths.bar_plugin_source.parent / "paolo.bar"
    if target in {legacy_source.resolve(strict=False), paths.bar_plugin_source.resolve()}:
        legacy.unlink()


def configure_theme(
    paths: ThemePaths,
    backend: ThemeBackend,
    style: str,
    *,
    display: ProgressDisplay | None = None,
) -> str:
    def stage(step: int, text: str) -> None:
        if display is not None:
            display.stage(step, text)

    stage(1, "Validating theme and bar configuration")
    if style not in {"floating", "fixed"}:
        raise ThemeError(f"unknown bar style: {style}")
    colors_config = paths.theme_assets / "colors.toml"
    shell_theme_config = paths.theme_assets / "shell.toml"
    fixed_shell_theme_config = paths.theme_assets / "shell-fixed.toml"
    if not colors_config.is_file():
        raise ThemeError(f"Olio su Silicio theme assets are incomplete: {paths.theme_assets}")
    _validate_theme_toml(colors_config)
    if shell_theme_config.is_file():
        _validate_theme_toml(shell_theme_config)
    if fixed_shell_theme_config.is_file():
        _validate_theme_toml(fixed_shell_theme_config)
    if not paths.bar_plugin_source.joinpath("manifest.json").is_file():
        raise ThemeError(f"olio.bar source is incomplete: {paths.bar_plugin_source}")
    if not paths.hypr_looknfeel_source.is_file():
        raise ThemeError(f"Hyprland look-and-feel source is missing: {paths.hypr_looknfeel_source}")
    _validate_bar_config(paths.bar_config)

    backend.validate_bar_plugin(paths.bar_plugin_source)
    previous_active = backend.active_omarchy_path()
    previous_theme = (
        paths.current_theme_name.read_text().strip()
        if paths.current_theme_name.is_file()
        else ""
    )
    previous_shell_config = paths.shell_config.read_bytes() if paths.shell_config.is_file() else None
    changes: list[ManagedLinkChange] = []
    theme_changed = False

    try:
        _render_theme_assets(paths, style)
        stage(2, "Linking repository-managed theme files")
        for source, target in (
            (paths.rendered_theme_assets, paths.user_theme),
            (paths.bar_plugin_source, paths.user_bar_plugin),
            (paths.hypr_looknfeel_source, paths.user_hypr_looknfeel),
        ):
            change = _ensure_managed_link(source, target, paths.backups_root)
            if change is not None:
                changes.append(change)

        _configure_bar(paths, style)
        old_state = json.loads(paths.state_file.read_text()) if paths.state_file.is_file() else {}
        assets_digest = _tree_digest(paths.theme_assets)
        theme_link_changed = any(change.target == paths.user_theme for change in changes)
        stage(3, "Refreshing theme assets and preserving the wallpaper when possible")
        if (
            previous_theme != THEME_NAME
            or theme_link_changed
            or old_state.get("theme_assets_sha256") != assets_digest
            or old_state.get("bar_style") != style
        ):
            backend.set_theme(
                THEME_NAME,
                preserve_background=(
                    previous_theme == THEME_NAME
                    and _current_background_survives_refresh(paths)
                ),
            )
            theme_changed = True

        stage(4, f"Activating {style} bar mode")
        # Keep the validated user-owned shell overlay active for both styles.
        # Floating mode disables the liquid renderer in Olio.bar, but retaining
        # the shared host preserves Omarchy popup anchoring for third-party
        # widgets. A failed overlay still rolls back through the existing
        # exception path; `theme restore` remains the explicit stock reset.
        overlay_result = apply_theme(paths, backend)
        if theme_changed and overlay_result == "already applied":
            backend.restart_shell(paths.overlay_root)
            overlay_result = "restarted"
        stage(5, "Checking companion bar plugins")
        backend.ensure_companion_plugins(paths)
        stage(6, "Reloading and validating Hyprland")
        backend.validate_hyprland()

        state = json.loads(paths.state_file.read_text()) if paths.state_file.is_file() else {}
        backups = list(state.get("preserved_paths", []))
        backups.extend(str(change.backup) for change in changes if change.backup is not None)
        state.update(
            {
                "bar_style": style,
                "theme_assets_sha256": assets_digest,
                "bar_plugin_sha256": _tree_digest(paths.bar_plugin_source),
                "preserved_paths": sorted(set(backups)),
            }
        )
        _write_atomic(paths.state_file, json.dumps(state, indent=2, sort_keys=True) + "\n")
        _retire_legacy_bar_link(paths)
        stage(7, "Theme setup verified")
        return f"{style} bar configured; shell {overlay_result}"
    except Exception:
        try:
            if previous_active == paths.overlay_root:
                apply_theme(paths, backend)
            elif backend.active_omarchy_path() == paths.overlay_root:
                restore_theme(paths, backend)
        except ThemeError:
            pass
        _restore_file(paths.shell_config, previous_shell_config)
        for change in reversed(changes):
            _rollback_managed_link(change)
        if theme_changed and previous_theme and previous_theme != THEME_NAME:
            try:
                backend.set_theme(previous_theme)
            except ThemeError:
                pass
        raise


def run_theme(
    action: str,
    *,
    paths: ThemePaths,
    backend: ThemeBackend,
    assume_yes: bool,
    dry_run: bool,
    stdin: TextIO,
    stdout: TextIO,
    progress: bool = True,
) -> int:
    if action == "status":
        print(theme_status(paths, backend), file=stdout)
        return 0
    normalized = "bar-fixed" if action == "apply" else action
    if dry_run:
        if normalized in {"bar-fixed", "bar-floating"}:
            print(f"Would install {THEME_NAME} and configure the {normalized.removeprefix('bar-')} bar.", file=stdout)
        else:
            print(f"Would {normalized} the {THEME_NAME} liquid shell overlay.", file=stdout)
        return 0
    if not assume_yes:
        if normalized in {"bar-fixed", "bar-floating"}:
            prompt = f"Install {THEME_NAME} and configure the {normalized.removeprefix('bar-')} bar?"
        else:
            prompt = f"{normalized.capitalize()} the {THEME_NAME} liquid shell overlay?"
        print(f"{prompt} [y/N] ", end="", file=stdout)
        stdout.flush()
        if stdin.readline().strip().lower() not in {"y", "yes"}:
            print("Cancelled.", file=stdout)
            return 1
    if normalized in {"bar-fixed", "bar-floating"}:
        display = ProgressDisplay(stdout, enabled=progress, quiet=False, total=7)
        result = configure_theme(
            paths,
            backend,
            normalized.removeprefix("bar-"),
            display=display,
        )
    else:
        display = ProgressDisplay(stdout, enabled=progress, quiet=False, total=2)
        display.stage(1, "Restoring stock Omarchy shell")
        result = restore_theme(paths, backend)
        display.stage(2, "Stock shell restore verified")
    print(f"Theme {result}.", file=stdout)
    return 0
