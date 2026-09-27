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
from omarchy_setup.modules.init import (
    InitError,
    InitPaths,
    UvBootstrapBackend,
    run_init,
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

    deblob = commands.add_parser("deblob", help="remove explicitly configured packages")
    deblob.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="accept ordinary confirmation prompts; safety checks still apply",
    )
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
    except (DeblobError, InitError) as error:
        print(f"Error: {error}", file=stderr)
        return 2

    return 2


def entrypoint() -> None:
    raise SystemExit(main())
