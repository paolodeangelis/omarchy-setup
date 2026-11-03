from __future__ import annotations

import curses
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence, TextIO

from .core import PROGRAMS, OmarchyProgramBackend, Program, ProgramError, ProgramPaths, resolve_programs


@dataclass(frozen=True)
class UpgradeStatus:
    program: Program
    installed: bool
    current: str = "unknown"
    candidate: str = "unknown"
    state: str = "unknown"

    @property
    def automatic(self) -> bool:
        return self.installed and self.program.upgrade_policy in {"flatpak", "system"}

    @property
    def selectable(self) -> bool:
        return self.automatic and self.state == "update"


class UpgradeBackend(Protocol):
    def check_environment(self) -> str: ...

    def inspect(self, programs: Sequence[Program], paths: ProgramPaths) -> list[UpgradeStatus]: ...

    def upgrade_flatpaks(self, app_ids: Sequence[str]) -> None: ...

    def upgrade_system(self, *, assume_yes: bool) -> None: ...


def _parse_package_updates(output: str) -> dict[str, tuple[str, str]]:
    updates: dict[str, tuple[str, str]] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[-2] == "->":
            updates[fields[0]] = (fields[-3], fields[-1])
    return updates


def _package_versions(output: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) == 2:
            versions[fields[0]] = fields[1]
    return versions


class OmarchyUpgradeBackend:
    def __init__(self, programs: OmarchyProgramBackend | None = None):
        self.programs = programs or OmarchyProgramBackend()

    def check_environment(self) -> str:
        return self.programs.check_environment()

    @staticmethod
    def _run_probe(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(command, text=True, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired as error:
            return subprocess.CompletedProcess(
                command, 124, error.stdout or "", error.stderr or "upgrade check timed out"
            )

    def inspect(self, programs: Sequence[Program], paths: ProgramPaths) -> list[UpgradeStatus]:
        package_names = sorted({package for program in programs for package in program.packages})
        installed_versions: dict[str, str] = {}
        package_updates: dict[str, tuple[str, str]] = {}
        pacman_check_known = True
        aur_check_known = True

        if package_names:
            installed_versions = _package_versions(
                self._run_probe(("pacman", "-Q", "--", *package_names)).stdout
            )
            if shutil.which("checkupdates") is None:
                pacman_check_known = False
            else:
                result = self._run_probe(("checkupdates", "--nocolor"))
                pacman_check_known = result.returncode in {0, 2}
                if pacman_check_known:
                    package_updates.update(_parse_package_updates(result.stdout))
            if shutil.which("yay") is None:
                aur_check_known = False
            else:
                result = self._run_probe(("yay", "-Qua", "--color", "never"))
                if result.returncode == 0:
                    package_updates.update(_parse_package_updates(result.stdout))
                else:
                    aur_check_known = False

        flatpak_versions: dict[str, str] = {}
        flatpak_updates: dict[str, str] = {}
        flatpak_check_known = shutil.which("flatpak") is not None
        flatpak_programs = [program for program in programs if program.flatpak_id]
        if flatpak_programs and flatpak_check_known:
            listing = self._run_probe(
                ("flatpak", "list", "--app", "--columns=application,version")
            )
            flatpak_check_known = listing.returncode == 0
            if flatpak_check_known:
                for line in listing.stdout.splitlines():
                    fields = line.split("\t", 1)
                    if len(fields) == 2:
                        flatpak_versions[fields[0]] = fields[1]
                for scope in ("--system", "--user"):
                    updates = self._run_probe((
                        "flatpak", "remote-ls", scope, "--app", "--updates",
                        "--columns=application,version",
                    ))
                    if updates.returncode != 0:
                        flatpak_check_known = False
                        continue
                    for line in updates.stdout.splitlines():
                        fields = line.split("\t", 1)
                        if len(fields) == 2:
                            flatpak_updates[fields[0]] = fields[1]

        statuses: list[UpgradeStatus] = []
        for program in programs:
            if program.upgrade_policy in {"manual", "none"}:
                installed = self.programs.is_installed(program, paths)
                state = "manual" if program.upgrade_policy == "manual" else "no payload"
                statuses.append(UpgradeStatus(program, installed, state=state if installed else "absent"))
                continue
            if program.flatpak_id:
                installed = program.flatpak_id in flatpak_versions
                candidate = flatpak_updates.get(program.flatpak_id)
                state = "update" if candidate else "current" if flatpak_check_known else "unknown"
                statuses.append(UpgradeStatus(
                    program, installed, flatpak_versions.get(program.flatpak_id, "unknown"),
                    candidate or "—", "absent" if not installed else state,
                ))
                continue

            if program.packages:
                installed = all(package in installed_versions for package in program.packages)
                primary = program.packages[0]
                update = package_updates.get(primary)
                current = installed_versions.get(primary, "unknown")
                candidate = update[1] if update else "—"
                check_known = (
                    pacman_check_known if program.source == "Pacman"
                    else aur_check_known if program.source == "AUR"
                    else pacman_check_known and aur_check_known
                )
                state = "update" if update else "current" if check_known else "unknown"
                statuses.append(UpgradeStatus(
                    program, installed, current, candidate,
                    "absent" if not installed else state,
                ))
                continue

            installed = self.programs.is_installed(program, paths)
            statuses.append(UpgradeStatus(program, installed, state="unknown" if installed else "absent"))
        return statuses

    def upgrade_flatpaks(self, app_ids: Sequence[str]) -> None:
        if not app_ids:
            return
        self.programs._run(
            ("flatpak", "update", "--noninteractive", *app_ids), capture=False
        )

    def upgrade_system(self, *, assume_yes: bool) -> None:
        command = ("omarchy", "update", "-y") if assume_yes else ("omarchy", "update")
        self.programs._run(command, capture=False)


def _source_name(program: Program) -> str:
    return {
        "Pinned Miniforge": "manual",
        "Pinned Git/image": "manual",
        "Omarchy system packages": "omarchy",
        "Pacman": "pacman",
        "AUR": "aur",
        "Flatpak/Flathub": "flatpak",
        "Omarchy web app": "webapp",
    }.get(program.source, program.source.casefold())


def format_upgrade_status(statuses: Sequence[UpgradeStatus], *, show_source: bool) -> str:
    installed = [status for status in statuses if status.automatic]
    if not installed:
        return "No automatically upgradable managed programs are installed."
    columns = [("PROGRAM", 16), ("INSTALLED", 22), ("AVAILABLE", 22)]
    if show_source:
        columns.append(("SOURCE", 10))
    header = "  ".join(label.ljust(width) for label, width in columns).rstrip()
    rows = [header, "  ".join("-" * width for _, width in columns).rstrip()]
    for status in installed:
        available = status.candidate if status.state == "update" else status.state
        values = [status.program.name, status.current, available]
        if show_source:
            values.append(_source_name(status.program))
        rows.append(
            "  ".join(value[:width].ljust(width) for value, (_, width) in zip(values, columns)).rstrip()
        )
    return "\n".join(rows)


def _curses_selector(screen, statuses: Sequence[UpgradeStatus]) -> list[str]:
    items = [status for status in statuses if status.selectable]
    if not items:
        return []
    selected: set[str] = set()
    cursor = 0
    curses.curs_set(0)
    screen.keypad(True)
    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        if height < 4 or width < 40:
            raise ProgramError("terminal is too small for the upgrade selector")
        screen.addnstr(0, 0, "Upgrade managed programs", max(1, width - 1), curses.A_BOLD)
        visible = height - 3
        start = max(0, min(cursor - visible + 1, len(items) - visible))
        for row, status in enumerate(items[start : start + visible], start=1):
            index = start + row - 1
            marker = "x" if status.program.name in selected else " "
            pointer = ">" if index == cursor else " "
            text = (
                f"{pointer} [{marker}] {status.program.name}  "
                f"{status.current} -> {status.candidate}"
            )
            screen.addnstr(row, 0, text, max(1, width - 1), curses.A_REVERSE if index == cursor else 0)
        screen.addnstr(height - 1, 0, "↑/↓ navigate  Space select  Enter continue  Q cancel", max(1, width - 1))
        key = screen.getch()
        if key in (ord("q"), ord("Q"), 27):
            return []
        if key in (curses.KEY_UP, ord("k")):
            cursor = (cursor - 1) % len(items)
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = (cursor + 1) % len(items)
        elif key == ord(" "):
            name = items[cursor].program.name
            selected.symmetric_difference_update({name})
        elif key in (10, 13, curses.KEY_ENTER):
            return [status.program.name for status in items if status.program.name in selected]


def select_upgrades(statuses: Sequence[UpgradeStatus]) -> list[str]:
    return curses.wrapper(_curses_selector, statuses)


def _confirm(stdin: TextIO, stdout: TextIO) -> bool:
    print("Continue with this upgrade plan? [y/N] ", end="", flush=True, file=stdout)
    return stdin.readline().strip().lower() in {"y", "yes"}


def run_upgrade(
    selection: str | None,
    *,
    paths: ProgramPaths,
    backend: UpgradeBackend,
    assume_yes: bool,
    check_only: bool,
    show_source: bool,
    stdin: TextIO,
    stdout: TextIO,
    selector: Callable[[Sequence[UpgradeStatus]], list[str]] = select_upgrades,
) -> int:
    programs = list(PROGRAMS) if selection in {None, "all"} else resolve_programs(selection)
    version = backend.check_environment()
    statuses = backend.inspect(programs, paths)
    print(f"Omarchy {version}", file=stdout)
    print(format_upgrade_status(statuses, show_source=show_source), file=stdout)
    if check_only:
        return 0

    if selection is None:
        if not stdin.isatty() or not stdout.isatty():
            raise ProgramError("upgrade without a target requires an interactive terminal")
        selected_names = selector(statuses)
    else:
        selected_names = [status.program.name for status in statuses if status.automatic]

    selected = [status for status in statuses if status.program.name in selected_names]
    if not selected:
        print("No upgradeable installed programs selected.", file=stdout)
        return 0
    if selection is not None and not assume_yes and not _confirm(stdin, stdout):
        print("Cancelled. No programs changed.", file=stdout)
        return 0

    flatpak_ids = [status.program.flatpak_id for status in selected if status.program.upgrade_policy == "flatpak"]
    system = [status for status in selected if status.program.upgrade_policy == "system"]
    if flatpak_ids:
        print("------------ FLATPAK UPDATE START ------------", file=stdout)
        backend.upgrade_flatpaks([app_id for app_id in flatpak_ids if app_id])
        print("------------ FLATPAK UPDATE COMPLETE ---------", file=stdout)
    if system:
        print("------------ OMARCHY SYSTEM UPDATE START ------------", file=stdout)
        print("Selected managed programs: " + ", ".join(status.program.label for status in system), file=stdout)
        print("The supported updater may update other system packages and creates a Snapper checkpoint when configured.", file=stdout)
        backend.upgrade_system(assume_yes=assume_yes)
        print("------------ OMARCHY SYSTEM UPDATE COMPLETE ---------", file=stdout)

    verified = backend.inspect([status.program for status in selected], paths)
    if any(not status.installed for status in verified):
        raise ProgramError("an upgraded program is no longer detected as installed")
    verified_by_name = {status.program.name: status for status in verified}
    unresolved = [
        status.program.name
        for status in selected
        if status.state == "update"
        and verified_by_name[status.program.name].state != "current"
    ]
    if unresolved:
        raise ProgramError(
            "available update still detected after upgrade: " + ", ".join(unresolved)
        )
    print("Upgrade completed and selected program versions were rechecked.", file=stdout)
    return 0
