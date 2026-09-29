from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence, TextIO

from omarchy_setup import __version__
from omarchy_setup.modules.deblob import (
    DeblobError,
    OmarchyBackend,
    default_config_path,
    load_config,
    run_deblob,
)
from omarchy_setup.modules.doctor import run_doctor
from omarchy_setup.modules.init import (
    InitError,
    InitPaths,
    UvBootstrapBackend,
    run_init,
)
from omarchy_setup.modules.programs import (
    OmarchyProgramBackend,
    ProgramError,
    ProgramPaths,
    format_program_list,
    run_install,
)
from omarchy_setup.modules.theme import (
    OmarchyThemeBackend,
    ThemeError,
    ThemePaths,
    run_theme,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omarchy-setup")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="accept ordinary confirmation prompts; safety checks still apply",
    )

    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create the dedicated Python environment and launcher")
    init.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="accept ordinary confirmation prompts; safety checks still apply",
    )
    init.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect and plan without downloading or writing files",
    )
    init.add_argument("--quiet", action="store_true", help="suppress normal output")
    init.add_argument(
        "--no-progress",
        action="store_true",
        help="show plain stage messages instead of the terminal progress bar",
    )

    deblob = commands.add_parser("deblob", help="remove explicitly configured packages")
    deblob.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="accept ordinary confirmation prompts; safety checks still apply",
    )

    doctor = commands.add_parser("doctor", help="check Omarchy shell, IPC, bindings, and recent errors")
    doctor.add_argument("--quiet", action="store_true", help="suppress individual checks")
    doctor.add_argument("--ui", action="store_true", help="exercise all top-level menus and a real OSD call")
    deblob.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="package policy file",
    )
    deblob.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect and plan without requesting sudo or removing packages",
    )
    deblob.add_argument(
        "--quiet",
        action="store_true",
        help="suppress normal output; errors still print",
    )
    deblob.add_argument(
        "--no-progress",
        action="store_true",
        help="show plain stage messages instead of the terminal progress bar",
    )

    install = commands.add_parser("install", help="install optional programs and services")
    install.add_argument(
        "target",
        metavar="{ls,list,all,program}",
        help="program name, 'all', or 'ls' to list available installation protocols",
    )
    install.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="accept the installation plan; safety checks still apply",
    )
    install.add_argument(
        "-l",
        "--login",
        "--loggin",
        action="store_true",
        help="open account login/onboarding after installation",
    )
    install.add_argument(
        "-d",
        "--default",
        "--defoult",
        dest="set_defaults",
        action="store_true",
        help="apply available Omarchy defaults after installation",
    )
    install.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect and plan without installing or opening programs",
    )
    install.add_argument("--quiet", action="store_true", help="suppress normal output")
    install.add_argument(
        "--no-progress",
        action="store_true",
        help="show plain stage messages instead of the terminal progress bar",
    )

    theme = commands.add_parser("theme", help="install olio-su-silicio and select its bar style")
    theme.add_argument(
        "action",
        nargs="?",
        default="bar-fixed",
        choices=("bar-fixed", "bar-floating", "apply", "status", "restore"),
        help="bar-fixed (default), bar-floating, status, or restore",
    )
    theme.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="accept the reversible shell switch",
    )
    theme.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect and plan without building or switching the shell",
    )
    theme.add_argument(
        "--no-progress",
        action="store_true",
        help="show plain stage messages instead of the terminal progress bar",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    backend: OmarchyBackend | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr

    try:
        if args.command == "doctor":
            return run_doctor(quiet=args.quiet, ui=args.ui, stdout=stdout)
        if args.command == "init":
            paths = InitPaths.for_user()
            return run_init(
                paths,
                backend=backend or UvBootstrapBackend(),
                assume_yes=args.yes,
                dry_run=args.dry_run,
                quiet=args.quiet,
                stdin=stdin,
                stdout=stdout,
                progress=not args.no_progress,
            )
        if args.command == "deblob":
            config = load_config(args.config)
            return run_deblob(
                config,
                backend=backend or OmarchyBackend(),
                assume_yes=args.yes,
                dry_run=args.dry_run,
                quiet=args.quiet,
                progress=not args.no_progress,
                stdin=stdin,
                stdout=stdout,
            )
        if args.command == "install":
            if args.target in {"ls", "list"}:
                print(format_program_list(), file=stdout)
                return 0
            return run_install(
                args.target,
                paths=ProgramPaths.for_user(),
                backend=backend or OmarchyProgramBackend(),
                assume_yes=args.yes,
                login=args.login,
                set_defaults=args.set_defaults,
                dry_run=args.dry_run,
                quiet=args.quiet,
                stdin=stdin,
                stdout=stdout,
                progress=not args.no_progress,
            )
        if args.command == "theme":
            return run_theme(
                args.action,
                paths=ThemePaths.for_user(),
                backend=OmarchyThemeBackend(),
                assume_yes=args.yes,
                dry_run=args.dry_run,
                stdin=stdin,
                stdout=stdout,
                progress=not args.no_progress,
            )
    except (DeblobError, InitError, ProgramError, ThemeError) as error:
        print(f"Error: {error}", file=stderr)
        return 2

    return 2


def entrypoint() -> None:
    raise SystemExit(main())
