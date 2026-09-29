from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


class DoctorError(RuntimeError):
    pass


Runner = Callable[[tuple[str, ...], dict[str, str] | None], tuple[int, str]]
MENU_ROUTES = ("root", "apps", "capture", "toggle", "hardware", "background", "theme", "system", "setup", "style", "share", "reminder")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _default_runner(command: tuple[str, ...], environment: dict[str, str] | None = None) -> tuple[int, str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False, env=environment)
    return result.returncode, (result.stdout or result.stderr).strip()


def _active_shell_path(output: str) -> Path | None:
    matches = re.findall(r"^\s*Config path:\s*(.+?)/shell/shell\.qml\s*$", output, re.MULTILINE)
    return Path(matches[-1]) if matches else None


def collect_checks(*, runner: Runner = _default_runner, home: Path | None = None) -> list[Check]:
    home = home or Path.home()
    checks: list[Check] = []
    expected = os.environ.get("OMARCHY_PATH")
    code, listing = runner(("quickshell", "list", "--all"), None)
    active = _active_shell_path(listing) if code == 0 else None
    checks.append(Check("shell process", active is not None, str(active or listing or "not running")))

    if active is not None:
        shell_root = active
        environment = os.environ.copy()
        environment["OMARCHY_PATH"] = str(shell_root)
        environment["QML2_IMPORT_PATH"] = str(shell_root / "shell")
        code, detail = runner(("omarchy-shell", "shell", "ping"), environment)
        checks.append(Check("shell IPC", code == 0, detail or "ok"))
        code, detail = runner(("omarchy-shell", "shell", "call", "omarchy.menu", "ping", "{}"), environment)
        checks.append(Check("menu IPC", code == 0 and detail.endswith("ok"), detail or "unavailable"))
        code, detail = runner(("omarchy-shell", "osd", "ping"), environment)
        checks.append(Check("OSD IPC", code == 0 and detail.endswith("ok"), detail or "unavailable"))
        if expected and Path(expected) != shell_root:
            # A terminal opened before a theme switch keeps its old export;
            # Hyprland keybinds use the live compositor environment instead.
            # Report this as an actionable note, not a broken-desktop failure.
            checks.append(Check("caller environment", True, f"stale shell export {expected}; compositor uses {shell_root}"))
        else:
            checks.append(Check("caller environment", True, str(shell_root)))
    else:
        checks.extend([Check("shell IPC", False, "skipped"), Check("menu IPC", False, "skipped"), Check("OSD IPC", False, "skipped")])

    binding_files = [
        home / ".config/omarchy/default/hypr/bindings/utilities.lua",
        Path("/usr/share/omarchy/default/hypr/bindings/utilities.lua"),
    ]
    utility = next((path for path in binding_files if path.is_file()), None)
    utility_text = utility.read_text(errors="replace") if utility else ""
    checks.append(Check("system menu binding", "SUPER + ESCAPE" in utility_text and "omarchy-menu toggle system" in utility_text, str(utility or "missing")))

    media_files = [home / ".config/omarchy/default/hypr/bindings/media.lua", Path("/usr/share/omarchy/default/hypr/bindings/media.lua")]
    media = next((path for path in media_files if path.is_file()), None)
    media_text = media.read_text(errors="replace") if media else ""
    checks.append(Check("media bindings", "omarchy-audio-output-volume raise" in media_text and "omarchy-brightness-display" in media_text, str(media or "missing")))

    for command in ("omarchy-menu", "omarchy-osd", "omarchy-audio-output-volume"):
        checks.append(Check(command, shutil.which(command) is not None, shutil.which(command) or "not found"))

    code, log = runner(("journalctl", "--user", "-t", "omarchy-shell", "--since", "15 minutes ago", "--no-pager"), None)
    errors = sum(1 for line in log.splitlines() if re.search(r"TypeError|segfault|crash|fatal", line, re.IGNORECASE)) if code == 0 else 0
    checks.append(Check("recent shell log", errors == 0, f"{errors} suspicious line(s)" if code == 0 else "unavailable"))
    return checks


def run_doctor(*, quiet: bool = False, ui: bool = False, stdout: TextIO | None = None, runner: Runner = _default_runner) -> int:
    stdout = stdout or __import__("sys").stdout
    checks = collect_checks(runner=runner)
    if ui:
        active_listing = runner(("quickshell", "list", "--all"), None)[1]
        active = _active_shell_path(active_listing)
        if active:
            environment = os.environ.copy()
            environment["OMARCHY_PATH"] = str(active)
            environment["QML2_IMPORT_PATH"] = str(active / "shell")
            route_failures = []
            for route in MENU_ROUTES:
                code, detail = runner(("omarchy-menu", "summon", route), environment)
                runner(("omarchy-menu", "close"), environment)
                if code != 0:
                    route_failures.append(f"{route} ({detail or 'no response'})")
            checks.append(Check("menu route smoke", not route_failures, ", ".join(route_failures) or f"{len(MENU_ROUTES)} routes"))
            code, detail = runner(("omarchy-osd", "-i", "volume-high", "-p", "50", "-d", "400"), environment)
            checks.append(Check("OSD smoke", code == 0, detail or "ok"))
        else:
            checks.append(Check("menu route smoke", False, "shell not running"))
            checks.append(Check("OSD smoke", False, "shell not running"))
    failed = [check for check in checks if not check.ok]
    if not quiet:
        for check in checks:
            marker = "OK" if check.ok else "FAIL"
            print(f"[{marker}] {check.name}: {check.detail}", file=stdout)
    return 1 if failed else 0
