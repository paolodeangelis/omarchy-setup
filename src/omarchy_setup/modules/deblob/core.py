from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence, TextIO

from omarchy_setup.progress import ProgressDisplay


PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9@._+:-]*$")


class DeblobError(RuntimeError):
    """A user-facing safety or execution failure."""


@dataclass(frozen=True)
class DeblobConfig:
    remove: tuple[str, ...]
    protected: frozenset[str]


class Backend(Protocol):
    def check_environment(self) -> str: ...

    def installed_packages(self) -> set[str]: ...

    def plan_removal(self, packages: Sequence[str]) -> tuple[str, ...]: ...

    def default_browser(self) -> str | None: ...

    def acquire_privileges(self) -> None: ...

    def remove(self, packages: Sequence[str], *, quiet: bool) -> None: ...


def default_config_path() -> Path:
    configured_root = os.environ.get("OMARCHY_SETUP_ROOT")
    if configured_root:
        return Path(configured_root) / "config" / "deblob.toml"
    return Path(__file__).resolve().parents[4] / "config" / "deblob.toml"


def _package_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DeblobError(f"{field} must be a TOML array of package names")

    packages = tuple(value)
    invalid = sorted({package for package in packages if not PACKAGE_NAME.fullmatch(package)})
    if invalid:
        raise DeblobError(f"invalid package names in {field}: {', '.join(invalid)}")
    if len(packages) != len(set(packages)):
        raise DeblobError(f"duplicate package name in {field}")
    return packages


def load_config(path: Path) -> DeblobConfig:
    try:
        with path.open("rb") as config_file:
            data = tomllib.load(config_file)
    except FileNotFoundError as error:
        raise DeblobError(f"deblob configuration not found: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise DeblobError(f"invalid TOML in {path}: {error}") from error

    if data.get("schema_version") != 1:
        raise DeblobError("unsupported deblob schema_version; expected 1")
    packages = data.get("packages")
    if not isinstance(packages, dict):
        raise DeblobError("missing [packages] table")

    remove = _package_list(packages.get("remove"), "packages.remove")
    protected = frozenset(_package_list(packages.get("protected"), "packages.protected"))
    overlap = sorted(set(remove) & protected)
    if overlap:
        raise DeblobError(f"packages cannot be both removed and protected: {', '.join(overlap)}")
    return DeblobConfig(remove=remove, protected=protected)


class OmarchyBackend:
    def _run(
        self,
        command: Sequence[str],
        *,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                check=True,
                text=True,
                capture_output=capture,
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "command failed").strip().splitlines()
            message = detail[-1] if detail else "command failed"
            raise DeblobError(f"{' '.join(command)}: {message}") from error

    def check_environment(self) -> str:
        missing = [command for command in ("omarchy", "pacman") if shutil.which(command) is None]
        if missing:
            raise DeblobError(f"required commands not found: {', '.join(missing)}")
        result = self._run(("omarchy", "version"))
        version = result.stdout.strip()
        if not version:
            raise DeblobError("could not determine Omarchy version")
        return version

    def installed_packages(self) -> set[str]:
        result = self._run(("pacman", "-Qq"))
        return {line for line in result.stdout.splitlines() if line}

    def plan_removal(self, packages: Sequence[str]) -> tuple[str, ...]:
        result = self._run(("pacman", "-Rs", "--print-format", "%n", *packages))
        return tuple(sorted({line for line in result.stdout.splitlines() if line}))

    def default_browser(self) -> str | None:
        if shutil.which("xdg-settings") is None:
            return None
        try:
            result = self._run(("xdg-settings", "get", "default-web-browser"))
        except DeblobError:
            return None
        return result.stdout.strip() or None

    def acquire_privileges(self) -> None:
        if os.geteuid() == 0:
            raise DeblobError("do not run omarchy-setup as root; run it as your normal user")
        if shutil.which("sudo") is None:
            raise DeblobError("sudo is required for package removal")
        self._run(("sudo", "-v"), capture=False)

    def remove(self, packages: Sequence[str], *, quiet: bool) -> None:
        self._run(("omarchy", "pkg", "drop", *packages), capture=quiet)


def _show_plan(
    *,
    configured: Sequence[str],
    targets: Sequence[str],
    transaction: Sequence[str],
    version: str,
    stream: TextIO,
    display: ProgressDisplay | None = None,
) -> None:
    skipped = sorted(set(configured) - set(targets))
    dependencies = sorted(set(transaction) - set(targets))
    width = max(60, min(shutil.get_terminal_size(fallback=(100, 24)).columns, 120))

    def package_block(label: str, packages: Sequence[str]) -> None:
        emit(f"{label} ({len(packages)}):")
        emit(
            textwrap.fill(
                ", ".join(packages),
                width=width,
                initial_indent="  ",
                subsequent_indent="  ",
                break_long_words=False,
                break_on_hyphens=False,
            )
        )

    def emit(text: str) -> None:
        if display is not None:
            display.message(text)
        else:
            print(text, file=stream)

    emit(f"Omarchy {version}")
    emit(f"Configured removals: {len(configured)}")
    emit(f"Installed targets: {len(targets)}")
    emit(f"Complete transaction: {len(transaction)} packages")
    package_block("Targets", targets)
    if dependencies:
        package_block("Unused dependencies", dependencies)
    if skipped:
        package_block("Already absent", skipped)


def _confirm(stdin: TextIO, stdout: TextIO) -> bool:
    print("Remove this package transaction? [y/N] ", end="", flush=True, file=stdout)
    answer = stdin.readline().strip().lower()
    return answer in {"y", "yes"}


def run_deblob(
    config: DeblobConfig,
    *,
    backend: Backend,
    assume_yes: bool,
    dry_run: bool,
    quiet: bool,
    progress: bool,
    stdin: TextIO,
    stdout: TextIO,
) -> int:
    display = ProgressDisplay(stdout, enabled=progress, quiet=quiet, total=5)

    display.stage(1, "Checking Omarchy compatibility")
    version = backend.check_environment()

    display.stage(2, "Inspecting installed packages")
    installed_before = backend.installed_packages()
    targets = tuple(package for package in config.remove if package in installed_before)
    if not targets:
        if not quiet:
            print("Nothing to remove. Configured packages are already absent.", file=stdout)
        display.stage(5, "Deblob state verified")
        return 0

    display.stage(3, "Planning complete Pacman transaction")
    transaction = backend.plan_removal(targets)
    if not transaction:
        raise DeblobError("Pacman returned an empty removal transaction")

    protected_affected = sorted(set(transaction) & config.protected)
    if protected_affected:
        raise DeblobError(
            "removal transaction touches protected packages: " + ", ".join(protected_affected)
        )

    if "chromium" in targets:
        browser = backend.default_browser()
        if browser is None:
            raise DeblobError("cannot verify a replacement default browser for Chromium")
        if "chromium" in browser.lower():
            raise DeblobError("Chromium is still the default browser; select a replacement first")

    if not quiet:
        _show_plan(
            configured=config.remove,
            targets=targets,
            transaction=transaction,
            version=version,
            stream=stdout,
            display=display,
        )

    if dry_run:
        display.stage(5, "Dry run complete; no packages changed")
        return 0

    if not assume_yes and not _confirm(stdin, stdout):
        if not quiet:
            print("Cancelled. No packages changed.", file=stdout)
        return 0

    display.stage(4, "Requesting sudo and applying removal")
    backend.acquire_privileges()

    current_installed = backend.installed_packages()
    if set(targets) - current_installed:
        raise DeblobError("package state changed after planning; run deblob again")
    current_transaction = backend.plan_removal(targets)
    if current_transaction != transaction:
        raise DeblobError("removal transaction changed after planning; run deblob again")

    protected_before = config.protected & installed_before
    backend.remove(targets, quiet=quiet)

    display.stage(5, "Verifying resulting package state")
    installed_after = backend.installed_packages()
    remaining = sorted(set(targets) & installed_after)
    missing_protected = sorted(protected_before - installed_after)
    if remaining:
        raise DeblobError(f"packages remain installed after removal: {', '.join(remaining)}")
    if missing_protected:
        raise DeblobError(f"protected packages disappeared: {', '.join(missing_protected)}")

    if not quiet:
        print(f"Removed {len(targets)} configured packages safely.", file=stdout)
    return 0
