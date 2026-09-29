from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence, TextIO

from omarchy_setup.progress import ProgressDisplay


class ProgramError(RuntimeError):
    """A user-facing program installation failure."""


MINIFORGE_VERSION = "26.7.2-0"
MINIFORGE_RELEASE = (
    f"https://github.com/conda-forge/miniforge/releases/download/{MINIFORGE_VERSION}"
)
MINIFORGE_ARTIFACTS = {
    "x86_64": (
        "Miniforge3-26.7.2-0-Linux-x86_64.sh",
        "281b0ac7d550802efc81af633225a5e6116d29ae72f3ab4eae7168c3931a4c05",
    ),
    "aarch64": (
        "Miniforge3-26.7.2-0-Linux-aarch64.sh",
        "89b786c8d2c8b0fda7553914c1314ae4ddaa094503802f279377b19ac4463cb2",
    ),
}


@dataclass(frozen=True)
class ProgramPaths:
    data_home: Path
    shell_rc: Path

    @classmethod
    def for_user(cls) -> "ProgramPaths":
        return cls(
            data_home=Path(
                os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
            ),
            shell_rc=Path.home() / ".bashrc",
        )

    @property
    def mamba_root(self) -> Path:
        return self.data_home / "omarchy-setup" / "miniforge3"


@dataclass(frozen=True)
class Program:
    name: str
    label: str
    description: str
    packages: tuple[str, ...]
    install_command: tuple[str, ...]
    login_command: tuple[str, ...] | None = None
    default_command: tuple[str, ...] | None = None
    desktop_file: str | None = None
    aliases: tuple[str, ...] = ()
    kind: str = "command"


PROGRAMS = (
    Program(
        name="mamba",
        label="Mamba (Miniforge)",
        description="Install a pinned Miniforge distribution with conda and mamba.",
        packages=(),
        install_command=(),
        aliases=("miniforge",),
        kind="mamba",
    ),
    Program(
        name="zen",
        label="Zen Browser",
        description="Install Zen Browser through Omarchy's supported browser installer.",
        packages=("zen-browser-bin",),
        install_command=("omarchy", "install", "browser", "zen"),
        login_command=("uwsm-app", "--", "zen-browser"),
        default_command=("omarchy", "default", "browser", "zen"),
        aliases=("zen-browser",),
    ),
    Program(
        name="1password",
        label="1Password",
        description="Install the 1Password desktop app and CLI through Omarchy.",
        packages=("1password", "1password-cli"),
        install_command=("omarchy", "install", "service", "1password"),
        login_command=("omarchy", "launch", "1password"),
        aliases=("onepassword",),
    ),
    Program(
        name="dropbox",
        label="Dropbox",
        description="Install Dropbox and its desktop integration through Omarchy.",
        packages=(
            "dropbox",
            "dropbox-cli",
            "libappindicator-gtk3",
            "python-gpgme",
            "nautilus-dropbox",
        ),
        install_command=("omarchy", "install", "service", "dropbox"),
        login_command=("uwsm-app", "--", "dropbox-cli", "start"),
    ),
    Program(
        name="spotify",
        label="Spotify",
        description="Install Spotify through Omarchy's supported service installer.",
        packages=("spotify",),
        install_command=("omarchy", "install", "service", "spotify"),
        login_command=("omarchy", "launch", "spotify"),
    ),
    Program(
        name="whatsapp",
        label="WhatsApp",
        description="Install WhatsApp as an Omarchy web application.",
        packages=(),
        install_command=(
            "omarchy",
            "webapp",
            "install",
            "WhatsApp",
            "https://web.whatsapp.com/",
            "whatsapp",
        ),
        login_command=("omarchy", "launch", "webapp", "https://web.whatsapp.com/"),
        desktop_file="WhatsApp.desktop",
        aliases=("whapp",),
    ),
    Program(
        name="telegram",
        label="Telegram",
        description="Install Telegram Desktop through Omarchy's package helper.",
        packages=("telegram-desktop",),
        install_command=("omarchy", "pkg", "add", "telegram-desktop"),
        login_command=("uwsm-app", "--", "telegram-desktop"),
    ),
)


class Backend(Protocol):
    def check_environment(self) -> str: ...

    def is_installed(self, program: Program, paths: ProgramPaths) -> bool: ...

    def install(self, program: Program, paths: ProgramPaths, *, quiet: bool) -> None: ...

    def set_default(self, program: Program) -> None: ...

    def launch_login(self, program: Program) -> None: ...


class OmarchyProgramBackend:
    def _run(
        self,
        command: Sequence[str],
        *,
        environment: dict[str, str] | None = None,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                check=True,
                text=True,
                capture_output=capture,
                env=environment,
            )
        except subprocess.CalledProcessError as error:
            details = (error.stderr or error.stdout or "command failed").strip().splitlines()
            message = details[-1] if details else "command failed"
            raise ProgramError(f"{' '.join(command)}: {message}") from error

    def check_environment(self) -> str:
        missing = [command for command in ("omarchy", "pacman") if shutil.which(command) is None]
        if missing:
            raise ProgramError(f"required commands not found: {', '.join(missing)}")
        if os.geteuid() == 0:
            raise ProgramError("do not run omarchy-setup as root; run it as your normal user")
        version = self._run(("omarchy", "version")).stdout.strip()
        if not version:
            raise ProgramError("could not determine Omarchy version")
        return version

    def is_installed(self, program: Program, paths: ProgramPaths) -> bool:
        if program.kind == "mamba":
            return (paths.mamba_root / "bin" / "mamba").is_file()
        if program.packages:
            result = subprocess.run(
                ("pacman", "-Q", "--", *program.packages),
                text=True,
                capture_output=True,
            )
            return result.returncode == 0
        if program.desktop_file:
            return any(
                (directory / program.desktop_file).is_file()
                for directory in (paths.data_home / "applications", Path("/usr/share/applications"))
            )
        raise ProgramError(f"{program.name} has no installation detector")

    def install(self, program: Program, paths: ProgramPaths, *, quiet: bool) -> None:
        if program.kind == "mamba":
            self._install_mamba(paths, quiet=quiet)
            return
        # Several supported Omarchy installers launch their application after
        # installing it. Suppress only that launch so onboarding remains owned
        # by the explicit --login flag.
        with tempfile.TemporaryDirectory(prefix="omarchy-setup-install-") as directory:
            launcher = Path(directory) / "uwsm-app"
            launcher.write_text("#!/bin/sh\nexit 0\n")
            launcher.chmod(0o700)
            environment = os.environ.copy()
            environment["PATH"] = f"{directory}:{environment.get('PATH', os.defpath)}"
            self._run(program.install_command, environment=environment, capture=quiet)

    def _install_mamba(self, paths: ProgramPaths, *, quiet: bool) -> None:
        if (paths.mamba_root / "bin" / "mamba").is_file():
            return
        if paths.mamba_root.exists():
            raise ProgramError(
                f"refusing to overwrite incomplete Miniforge installation: {paths.mamba_root}"
            )
        artifact = MINIFORGE_ARTIFACTS.get(platform.machine().lower())
        if artifact is None:
            raise ProgramError(
                f"unsupported CPU architecture for Miniforge: {platform.machine()}"
            )
        archive_name, expected_digest = artifact
        paths.mamba_root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=paths.mamba_root.parent) as directory:
            installer = Path(directory) / archive_name
            try:
                with urllib.request.urlopen(
                    f"{MINIFORGE_RELEASE}/{archive_name}", timeout=180
                ) as response, installer.open("wb") as output:
                    shutil.copyfileobj(response, output)
            except OSError as error:
                raise ProgramError(f"failed to download Miniforge: {error}") from error
            digest = hashlib.sha256(installer.read_bytes()).hexdigest()
            if digest != expected_digest:
                raise ProgramError(
                    f"Miniforge checksum mismatch: expected {expected_digest}, received {digest}"
                )
            self._run(
                ("bash", str(installer), "-b", "-p", str(paths.mamba_root)),
                capture=quiet,
            )

        mamba = paths.mamba_root / "bin" / "mamba"
        if not mamba.is_file():
            raise ProgramError("Miniforge installed without a mamba executable")
        _install_mamba_shell_block(paths)

    def set_default(self, program: Program) -> None:
        if program.default_command is not None:
            self._run(program.default_command)
            selected = self._run(("omarchy", "default", "browser")).stdout.strip()
            if selected != program.name:
                raise ProgramError(
                    f"{program.label} default could not be verified; Omarchy reports '{selected}'"
                )

    def launch_login(self, program: Program) -> None:
        if program.login_command is None:
            return
        try:
            subprocess.Popen(
                program.login_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            raise ProgramError(f"could not open {program.label} login: {error}") from error


def resolve_programs(selection: str) -> tuple[Program, ...]:
    if selection == "all":
        return PROGRAMS
    for program in PROGRAMS:
        if selection == program.name or selection in program.aliases:
            return (program,)
    names = ", ".join(program.name for program in PROGRAMS)
    raise ProgramError(f"unknown program '{selection}'; choose one of: all, {names}")


def format_program_list() -> str:
    """Return the user-facing catalog for ``install ls``."""
    lines = ["Available installation protocols:"]
    for program in PROGRAMS:
        lines.append(f"  {program.name:<12} {program.description}")
    lines.append("  all          Install every missing protocol above.")
    return "\n".join(lines)


MAMBA_BLOCK_START = "# >>> omarchy-setup mamba >>>"
MAMBA_BLOCK_END = "# <<< omarchy-setup mamba <<<"


def _shell_quote(value: Path) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def _install_mamba_shell_block(paths: ProgramPaths) -> None:
    try:
        current = paths.shell_rc.read_text()
    except FileNotFoundError:
        current = ""
    except OSError as error:
        raise ProgramError(
            f"could not read shell startup file {paths.shell_rc}: {error}"
        ) from error

    if MAMBA_BLOCK_START in current:
        if MAMBA_BLOCK_END not in current:
            raise ProgramError(f"incomplete managed mamba block in {paths.shell_rc}")
        return

    root = _shell_quote(paths.mamba_root)
    block = (
        f"\n{MAMBA_BLOCK_START}\n"
        f"export OMARCHY_SETUP_MAMBA_ROOT={root}\n"
        'if [[ -r "$OMARCHY_SETUP_MAMBA_ROOT/etc/profile.d/conda.sh" ]]; then\n'
        "  export CONDA_CHANGEPS1=false\n"
        "  case \":$PATH:\" in\n"
        '    *":$OMARCHY_SETUP_MAMBA_ROOT/condabin:"*) ;;\n'
        '    *) PATH="$PATH:$OMARCHY_SETUP_MAMBA_ROOT/condabin" ; export PATH ;;\n'
        "  esac\n"
        '  source "$OMARCHY_SETUP_MAMBA_ROOT/etc/profile.d/conda.sh"\n'
        '  [[ -r "$OMARCHY_SETUP_MAMBA_ROOT/etc/profile.d/mamba.sh" ]] && source "$OMARCHY_SETUP_MAMBA_ROOT/etc/profile.d/mamba.sh"\n'
        "fi\n"
        f"{MAMBA_BLOCK_END}\n"
    )
    try:
        paths.shell_rc.parent.mkdir(parents=True, exist_ok=True)
        with paths.shell_rc.open("a") as shell_rc:
            shell_rc.write(block)
    except OSError as error:
        raise ProgramError(
            f"could not update shell startup file {paths.shell_rc}: {error}"
        ) from error


def _confirm(stdin: TextIO, stdout: TextIO) -> bool:
    print("Continue with this installation plan? [y/N] ", end="", flush=True, file=stdout)
    return stdin.readline().strip().lower() in {"y", "yes"}


def run_install(
    selection: str,
    *,
    paths: ProgramPaths,
    backend: Backend,
    assume_yes: bool,
    login: bool,
    set_defaults: bool,
    dry_run: bool,
    quiet: bool,
    stdin: TextIO,
    stdout: TextIO,
    progress: bool = True,
) -> int:
    programs = resolve_programs(selection)
    display = ProgressDisplay(
        stdout, enabled=progress, quiet=quiet, total=len(programs) + 3
    )
    display.stage(1, "Checking Omarchy compatibility")
    version = backend.check_environment()
    display.stage(2, "Inspecting installed programs")
    installed = {program.name: backend.is_installed(program, paths) for program in programs}
    missing = [program for program in programs if not installed[program.name]]

    if not quiet:
        display.message(f"Omarchy {version}")
        for program in programs:
            state = "already installed" if installed[program.name] else "install"
            actions = [state]
            if set_defaults and program.default_command is not None:
                actions.append("set default")
            if login and program.login_command is not None:
                actions.append("open login")
            display.message(f"  {program.label}: {', '.join(actions)}")

    if dry_run:
        display.stage(len(programs) + 3, "Dry run complete; no programs changed")
        if not quiet:
            print("Dry run complete; no programs changed or opened.", file=stdout)
        return 0

    has_actions = bool(missing) or login or set_defaults
    if has_actions and not assume_yes and not _confirm(stdin, stdout):
        if not quiet:
            print("Cancelled. No programs changed or opened.", file=stdout)
        return 0

    total = len(programs)
    for index, program in enumerate(programs, start=1):
        if not installed[program.name]:
            display.stage(index + 2, f"Installing {program.label}")
            backend.install(program, paths, quiet=quiet)
            if not backend.is_installed(program, paths):
                raise ProgramError(f"{program.label} installation could not be verified")
        else:
            display.stage(index + 2, f"{program.label} already installed; skipping")

        if set_defaults and program.default_command is not None:
            backend.set_default(program)
            if not quiet:
                display.message(f"      Set {program.label} as an Omarchy default.")
        if login and program.login_command is not None:
            backend.launch_login(program)
            if not quiet:
                display.message(f"      Opened {program.label} login/onboarding.")

    display.stage(total + 3, "Program setup verified")
    if not quiet:
        print("Program setup complete.", file=stdout)
    return 0
