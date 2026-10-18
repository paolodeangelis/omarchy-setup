from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

from omarchy_setup.progress import ProgressDisplay


SPACES_ID = "tornikegomareli.spaces"


class PluginError(RuntimeError):
    """A managed-plugin configuration or lifecycle failure."""


@dataclass(frozen=True)
class Plugin:
    id: str
    url: str | None
    section: str
    after: str
    builtin: bool = False
    replaces: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    aur_packages: tuple[str, ...] = ()
    user_services: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginPaths:
    repo_root: Path
    state_root: Path
    home: Path
    system_omarchy: Path = Path("/usr/share/omarchy")

    @classmethod
    def for_user(cls) -> "PluginPaths":
        configured_root = os.environ.get("OMARCHY_SETUP_ROOT")
        repo_root = (
            Path(configured_root).resolve()
            if configured_root
            else Path(__file__).resolve().parents[4]
        )
        state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        return cls(repo_root, state_home / "omarchy-setup", Path.home())

    @property
    def config(self) -> Path:
        return self.repo_root / "plugins" / "plugins.toml"

    @property
    def installed_root(self) -> Path:
        return self.home / ".config" / "omarchy" / "plugins"

    @property
    def shell_config(self) -> Path:
        return self.home / ".config" / "omarchy" / "shell.json"

    @property
    def spaces_agent_template(self) -> Path:
        return self.repo_root / "plugins" / "bin" / "omarchy-spaces-agent"

    @property
    def spaces_agent_command(self) -> Path:
        return self.state_root / "bin" / "omarchy-spaces-agent"

    @property
    def codex_hooks(self) -> Path:
        return self.home / ".codex" / "hooks.json"

    @property
    def claude_settings(self) -> Path:
        return self.home / ".claude" / "settings.json"


def load_plugins(path: Path) -> tuple[Plugin, ...]:
    try:
        document = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise PluginError(f"cannot read plugin configuration {path}: {error}") from error

    rows = document.get("plugin")
    if not isinstance(rows, list) or not rows:
        raise PluginError(f"plugin configuration has no [[plugin]] entries: {path}")

    plugins: list[Plugin] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise PluginError("each [[plugin]] entry must be a TOML table")
        plugin_id, url = row.get("id"), row.get("url")
        section, after = row.get("section"), row.get("after")
        builtin = row.get("builtin", False)
        if not all(isinstance(value, str) and value for value in (plugin_id, section, after)):
            raise PluginError("plugin entries require non-empty id, section and after strings")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", plugin_id) or ".." in plugin_id:
            raise PluginError(f"invalid plugin id: {plugin_id!r}")
        if not isinstance(builtin, bool):
            raise PluginError(f"builtin for {plugin_id} must be true or false")
        if builtin:
            if not plugin_id.startswith("omarchy.") or url is not None:
                raise PluginError(
                    f"built-in plugin {plugin_id} must use an omarchy.* ID and omit url"
                )
        elif not (
            isinstance(url, str)
            and url.startswith("https://github.com/")
            and url.endswith(".git")
        ):
            raise PluginError(f"plugin URL must be an HTTPS GitHub .git URL: {url!r}")
        if section not in {"left", "center", "right"}:
            raise PluginError(f"invalid bar section for {plugin_id}: {section!r}")
        if plugin_id in seen:
            raise PluginError(f"duplicate plugin id: {plugin_id}")
        seen.add(plugin_id)
        replacements = row.get("replaces", [])
        if not isinstance(replacements, list) or not all(
            isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", item)
            and ".." not in item
            for item in replacements
        ):
            raise PluginError(f"replaces for {plugin_id} must be a list of plugin IDs")
        requirements = row.get("requires", [])
        if not isinstance(requirements, list) or not all(
            isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", item)
            for item in requirements
        ):
            raise PluginError(f"requires for {plugin_id} must be a list of command names")
        aur_packages = row.get("aur_packages", [])
        if not isinstance(aur_packages, list) or not all(
            isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9@._+-]*", item)
            for item in aur_packages
        ):
            raise PluginError(f"aur_packages for {plugin_id} must be a list of package names")
        user_services = row.get("user_services", [])
        if not isinstance(user_services, list) or not all(
            isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9@._-]*\.service", item)
            for item in user_services
        ):
            raise PluginError(f"user_services for {plugin_id} must be a list of service names")
        plugins.append(
            Plugin(
                id=plugin_id,
                url=url,
                section=section,
                after=after,
                builtin=builtin,
                replaces=tuple(replacements),
                requires=tuple(requirements),
                aur_packages=tuple(aur_packages),
                user_services=tuple(user_services),
            )
        )
    return tuple(plugins)


class PluginBackend(Protocol):
    def install(self, plugin: Plugin) -> None: ...
    def validate(self, directory: Path) -> None: ...
    def enable(self, plugin: Plugin) -> None: ...
    def disable(self, plugin_id: str) -> None: ...
    def upgrade(self, plugin_id: str, *, assume_yes: bool) -> None: ...
    def command_available(self, command: str) -> bool: ...
    def install_requirements(self, plugin: Plugin) -> None: ...
    def enable_user_services(self, plugin: Plugin) -> None: ...
    def user_service_active(self, service: str) -> bool: ...


class OmarchyPluginBackend:
    def __init__(self, paths: PluginPaths) -> None:
        self.paths = paths

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        result = subprocess.run(
            ("systemctl", "--user", "show-environment"),
            text=True,
            capture_output=True,
            check=False,
        )
        active = ""
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("OMARCHY_PATH="):
                    active = line.partition("=")[2]
        root = Path(active) if active and Path(active, "shell", "shell.qml").is_file() else self.paths.system_omarchy
        environment["OMARCHY_PATH"] = str(root)
        environment["QML2_IMPORT_PATH"] = str(root / "shell")
        return environment

    def _run(self, command: tuple[str, ...], *, interactive: bool = False, attempts: int = 4) -> None:
        for attempt in range(attempts):
            try:
                result = subprocess.run(
                    command,
                    check=True,
                    text=True,
                    capture_output=not interactive,
                    env=self._environment(),
                )
                if not interactive and result.stdout:
                    print(result.stdout.rstrip())
                return
            except OSError as error:
                raise PluginError(f"{' '.join(command)}: {error}") from error
            except subprocess.CalledProcessError as error:
                output = ((error.stderr or "") + "\n" + (error.stdout or "")).strip()
                if "omarchy-shell is not responding" in output and attempt < attempts - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                details = output.splitlines()
                raise PluginError(
                    f"{' '.join(command)}: {details[-1] if details else 'command failed'}"
                ) from error
        raise AssertionError("unreachable")

    def install(self, plugin: Plugin) -> None:
        if plugin.url is None:
            raise PluginError(f"cannot install built-in plugin as third-party: {plugin.id}")
        self._run(("omarchy", "plugin", "add", plugin.url, "--enable", "--yes"))

    def validate(self, directory: Path) -> None:
        self._run(("omarchy", "plugin", "validate", str(directory)))

    def enable(self, plugin: Plugin) -> None:
        self._run((
            "omarchy", "plugin", "enable", plugin.id,
            "--section", plugin.section, "--after", plugin.after,
        ))

    def disable(self, plugin_id: str) -> None:
        self._run(("omarchy", "plugin", "disable", plugin_id))

    def upgrade(self, plugin_id: str, *, assume_yes: bool) -> None:
        command = ["omarchy", "plugin", "update", plugin_id]
        if assume_yes:
            command.append("--yes")
        self._run(tuple(command), interactive=not assume_yes)

    def command_available(self, command: str) -> bool:
        return shutil.which(command) is not None

    def install_requirements(self, plugin: Plugin) -> None:
        if plugin.aur_packages:
            self._run(
                ("omarchy", "pkg", "aur", "add", *plugin.aur_packages),
                interactive=True,
            )

    def enable_user_services(self, plugin: Plugin) -> None:
        if plugin.user_services:
            self._run(("systemctl", "--user", "enable", "--now", *plugin.user_services))

    def user_service_active(self, service: str) -> bool:
        result = subprocess.run(
            ("systemctl", "--user", "is-active", "--quiet", service),
            check=False,
            env=self._environment(),
        )
        return result.returncode == 0


def _manifest_id(path: Path, expected: str) -> str:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PluginError(f"plugin {expected} has no readable manifest: {error}") from error
    plugin_id = value.get("id") if isinstance(value, dict) else None
    if plugin_id != expected:
        raise PluginError(
            f"configured plugin ID {expected!r} does not match installed manifest {plugin_id!r}"
        )
    return plugin_id


def _replacement_available(paths: PluginPaths, plugin_id: str) -> bool:
    return plugin_id.startswith("omarchy.") or (paths.installed_root / plugin_id / "manifest.json").is_file()


def _reconcile_one(
    paths: PluginPaths,
    backend: PluginBackend,
    plugin: Plugin,
) -> tuple[str, ...]:
    missing = tuple(
        command for command in plugin.requires if not backend.command_available(command)
    )
    if missing and plugin.aur_packages:
        backend.install_requirements(plugin)
        missing = tuple(
            command for command in plugin.requires if not backend.command_available(command)
        )
    if missing:
        raise PluginError(
            f"{plugin.id} requirements are unavailable after installation: "
            f"{', '.join(missing)}"
        )
    inactive = tuple(
        service for service in plugin.user_services
        if not backend.user_service_active(service)
    )
    if inactive:
        backend.enable_user_services(plugin)
        inactive = tuple(
            service for service in plugin.user_services
            if not backend.user_service_active(service)
        )
    if inactive:
        raise PluginError(
            f"{plugin.id} user services are inactive after setup: "
            f"{', '.join(inactive)}"
        )

    if not plugin.builtin:
        directory = paths.installed_root / plugin.id
        manifest = directory / "manifest.json"
        if not manifest.is_file():
            backend.install(plugin)
        _manifest_id(manifest, plugin.id)
        backend.validate(directory)
    backend.enable(plugin)
    for replaced in plugin.replaces:
        if _replacement_available(paths, replaced):
            backend.disable(replaced)
    return ()


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
        raise PluginError(f"invalid {label} configuration: {path}") from error
    if not isinstance(value, dict):
        raise PluginError(f"{label} configuration must be an object: {path}")
    return value


def _append_command_hook(config: dict[str, object], event: str, command: str) -> None:
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise PluginError("agent hooks configuration must be an object")
    groups = hooks.setdefault(event, [])
    if not isinstance(groups, list):
        raise PluginError(f"agent hook event {event} must be a list")
    for group in groups:
        if not isinstance(group, dict):
            continue
        handlers = group.get("hooks", [])
        if isinstance(handlers, list):
            for handler in handlers:
                if isinstance(handler, dict) and handler.get("type") == "command" and handler.get("command") == command:
                    handler.update({"async": False, "timeout": 3})
                    return
    groups.append({"hooks": [{"type": "command", "command": command, "async": False, "timeout": 3}]})


def _remove_command_hook(config: dict[str, object], event: str, command: str) -> None:
    hooks = config.get("hooks")
    if not isinstance(hooks, dict) or not isinstance(hooks.get(event), list):
        return
    kept: list[object] = []
    for group in hooks[event]:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            kept.append(group)
            continue
        handlers = [
            handler for handler in group["hooks"]
            if not (isinstance(handler, dict) and handler.get("type") == "command" and handler.get("command") == command)
        ]
        if handlers:
            next_group = dict(group)
            next_group["hooks"] = handlers
            kept.append(next_group)
    hooks[event] = kept


def ensure_spaces_agent_hooks(paths: PluginPaths) -> None:
    reporter = paths.installed_root / SPACES_ID / "hooks" / "claude-hook"
    if not reporter.is_file():
        raise PluginError(f"Spaces agent integration is missing: {reporter}")
    if not paths.spaces_agent_template.is_file():
        raise PluginError(f"Spaces agent wrapper is missing: {paths.spaces_agent_template}")
    _write_atomic(paths.spaces_agent_command, paths.spaces_agent_template.read_text())
    paths.spaces_agent_command.chmod(0o755)

    base = shlex.quote(str(reporter))
    wrapper = shlex.quote(str(paths.spaces_agent_command))
    configurations = (
        (paths.codex_hooks, "Codex hooks", (
            ("UserPromptSubmit", "working"), ("PostToolUse", "working"),
            ("PermissionRequest", "waiting"), ("Stop", "done"),
            ("Interrupt", "end"), ("SessionEnd", "end"),
        )),
        (paths.claude_settings, "Claude", (
            ("UserPromptSubmit", "working"), ("PostToolUse", "working"),
            ("Notification", "waiting"), ("Stop", "done"), ("SessionEnd", "end"),
        )),
    )
    for path, label, events in configurations:
        config = _read_json_object(path, label)
        for event, state in events:
            for old in (f"{base} {state}", f"{wrapper} {base} {state}"):
                _remove_command_hook(config, event, old)
            _append_command_hook(config, event, f"{wrapper} {state}")
        _write_atomic(path, json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def _layout_positions(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text())
        layout = document.get("bar", {}).get("layout", {})
    except (OSError, json.JSONDecodeError, AttributeError) as error:
        raise PluginError(f"cannot read shell layout {path}: {error}") from error
    positions: dict[str, str] = {}
    for section in ("left", "center", "right"):
        entries = layout.get(section, []) if isinstance(layout, dict) else []
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            plugin_id = entry.get("id") if isinstance(entry, dict) else entry
            if isinstance(plugin_id, str):
                positions[plugin_id] = f"{section}:{index}"
    return positions


def format_plugin_status(paths: PluginPaths) -> str:
    positions = _layout_positions(paths.shell_config)
    lines = [f"{'ID':38} {'STATE':10} {'POSITION':12} REPLACES"]
    for plugin in load_plugins(paths.config):
        manifest = paths.installed_root / plugin.id / "manifest.json"
        if plugin.builtin:
            state = "enabled" if plugin.id in positions else "disabled"
        elif not manifest.is_file():
            state = "missing"
        else:
            _manifest_id(manifest, plugin.id)
            state = "enabled" if plugin.id in positions else "disabled"
            if state == "enabled" and any(shutil.which(command) is None for command in plugin.requires):
                state = "setup"
        lines.append(
            f"{plugin.id:38} {state:10} {positions.get(plugin.id, '-'):12} "
            f"{','.join(plugin.replaces) or '-'}"
        )
    return "\n".join(lines)


def _select_plugins(plugins: tuple[Plugin, ...], target: str) -> tuple[Plugin, ...]:
    if target == "all":
        return plugins
    selected = tuple(plugin for plugin in plugins if plugin.id == target)
    if not selected:
        raise PluginError(f"unknown managed plugin: {target}")
    return selected


def run_plugins(
    action: str,
    target: str,
    *,
    paths: PluginPaths,
    backend: PluginBackend,
    assume_yes: bool,
    dry_run: bool,
    stdin: TextIO,
    stdout: TextIO,
    progress: bool = True,
) -> int:
    plugins = load_plugins(paths.config)
    selected = _select_plugins(plugins, target)
    if action == "status":
        print(format_plugin_status(paths), file=stdout)
        return 0
    if dry_run:
        verb = "upgrade and reconcile" if action == "upgrade" else "install and reconcile"
        print(f"Would {verb}: {', '.join(plugin.id for plugin in selected)}", file=stdout)
        return 0
    if action == "apply" and not assume_yes:
        print("Install and reconcile managed Omarchy plugins? [y/N] ", end="", file=stdout)
        stdout.flush()
        if stdin.readline().strip().lower() not in {"y", "yes"}:
            print("Cancelled.", file=stdout)
            return 1

    display = ProgressDisplay(stdout, enabled=progress, quiet=False, total=len(selected) + 1)
    for index, plugin in enumerate(selected, start=1):
        display.stage(index, f"{'Upgrading' if action == 'upgrade' else 'Reconciling'} {plugin.id}")
        if action == "upgrade":
            if not plugin.builtin:
                manifest = paths.installed_root / plugin.id / "manifest.json"
                if not manifest.is_file():
                    raise PluginError(f"managed plugin {plugin.id} is not installed; run plugin apply first")
                backend.upgrade(plugin.id, assume_yes=assume_yes)
        _reconcile_one(paths, backend, plugin)

    if any(plugin.id == SPACES_ID for plugin in selected):
        ensure_spaces_agent_hooks(paths)
    display.stage(len(selected) + 1, "Managed plugin state verified")
    print(f"Plugins {action} complete.", file=stdout)
    return 0
