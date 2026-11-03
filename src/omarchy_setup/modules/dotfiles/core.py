from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

from omarchy_setup.progress import ProgressDisplay


class DotfilesError(RuntimeError):
    """A user-facing dotfile deployment failure."""


TMUX_START = "# >>> omarchy-setup persistence >>>"
TMUX_END = "# <<< omarchy-setup persistence <<<"
HYPR_START = "-- >>> omarchy-setup window-close >>>"
HYPR_END = "-- <<< omarchy-setup window-close <<<"
BASH_START = "# >>> omarchy-setup aliases >>>"
BASH_END = "# <<< omarchy-setup aliases <<<"
ALIAS_START = "# >>> omarchy-setup shortcuts >>>"
ALIAS_END = "# <<< omarchy-setup shortcuts <<<"

PLUGINS = (
    (
        "tmux-resurrect",
        "https://github.com/tmux-plugins/tmux-resurrect.git",
        "cff343cf9e81983d3da0c8562b01616f12e8d548",
    ),
    (
        "tmux-continuum",
        "https://github.com/tmux-plugins/tmux-continuum.git",
        "0698e8f4b17d6454c71bf5212895ec055c578da0",
    ),
)


@dataclass(frozen=True)
class DotfilesPaths:
    repo_root: Path
    state_root: Path
    config_home: Path

    @classmethod
    def for_user(cls) -> "DotfilesPaths":
        root = Path(os.environ.get("OMARCHY_SETUP_ROOT", Path(__file__).resolve().parents[4]))
        state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return cls(root.resolve(), state / "omarchy-setup", config)

    @property
    def tmux_config(self) -> Path:
        return self.config_home / "tmux" / "tmux.conf"

    @property
    def hypr_bindings(self) -> Path:
        return self.config_home / "hypr" / "bindings.lua"

    @property
    def plugin_root(self) -> Path:
        return self.state_root / "tmux" / "plugins"

    @property
    def bashrc(self) -> Path:
        return self.config_home.parent / ".bashrc"

    @property
    def aliases(self) -> Path:
        return self.config_home.parent / ".alias"

    @property
    def aliases_source(self) -> Path:
        return self.repo_root / "dotfiles" / "bash" / "alias"


class Backend(Protocol):
    def check(self, paths: DotfilesPaths) -> None: ...
    def install_plugins(self, paths: DotfilesPaths) -> None: ...
    def apply(self, paths: DotfilesPaths) -> None: ...
    def verify(self, paths: DotfilesPaths) -> None: ...


def _replace_block(contents: str, start: str, end: str, block: str) -> str:
    begin = contents.find(start)
    if begin >= 0:
        finish = contents.find(end, begin)
        if finish < 0:
            raise DotfilesError(f"managed block {start!r} has no end marker")
        finish += len(end)
        contents = contents[:begin].rstrip() + "\n" + contents[finish:].lstrip("\n")
    return contents.rstrip() + "\n\n" + block.rstrip() + "\n"


class OmarchyDotfilesBackend:
    def check(self, paths: DotfilesPaths) -> None:
        for command in ("git", "tmux", "hyprctl"):
            if shutil.which(command) is None:
                raise DotfilesError(f"required command not found: {command}")
        for target in (paths.tmux_config, paths.hypr_bindings, paths.bashrc, paths.aliases_source):
            if not target.is_file():
                raise DotfilesError(f"expected Omarchy configuration is missing: {target}")

    def install_plugins(self, paths: DotfilesPaths) -> None:
        paths.plugin_root.mkdir(parents=True, exist_ok=True)
        for name, url, revision in PLUGINS:
            target = paths.plugin_root / name
            if target.exists():
                result = subprocess.run(
                    ("git", "-C", str(target), "rev-parse", "HEAD"),
                    text=True, capture_output=True,
                )
                if result.returncode or result.stdout.strip() != revision:
                    raise DotfilesError(
                        f"refusing to replace modified or unpinned plugin directory: {target}"
                    )
                continue
            with tempfile.TemporaryDirectory(dir=paths.plugin_root) as directory:
                checkout = Path(directory) / name
                try:
                    subprocess.run(
                        ("git", "clone", "--quiet", url, str(checkout)), check=True
                    )
                    subprocess.run(
                        ("git", "-C", str(checkout), "checkout", "--quiet", revision),
                        check=True,
                    )
                except subprocess.CalledProcessError as error:
                    raise DotfilesError(f"failed to install {name}") from error
                checkout.rename(target)

    def apply(self, paths: DotfilesPaths) -> None:
        tmux_block = f"""{TMUX_START}
set -g @resurrect-dir '~/.local/state/omarchy-setup/tmux/resurrect'
set -g @continuum-save-interval '1'
set -g @continuum-restore 'on'
run-shell '~/.local/state/omarchy-setup/tmux/plugins/tmux-resurrect/resurrect.tmux'
run-shell '~/.local/state/omarchy-setup/tmux/plugins/tmux-continuum/continuum.tmux'
{TMUX_END}"""
        hypr_block = f"""{HYPR_START}
-- SUPER+W was Omarchy's default close binding; use SUPER+Q instead.
hl.unbind("SUPER + W")
hl.unbind("SUPER + Q")
o.bind("SUPER + Q", "Close window", hl.dsp.window.close())
{HYPR_END}"""
        paths.tmux_config.write_text(
            _replace_block(paths.tmux_config.read_text(), TMUX_START, TMUX_END, tmux_block)
        )
        paths.hypr_bindings.write_text(
            _replace_block(paths.hypr_bindings.read_text(), HYPR_START, HYPR_END, hypr_block)
        )
        bash_block = f'''{BASH_START}
[[ -r "$HOME/.alias" ]] && source "$HOME/.alias"
{BASH_END}'''
        paths.bashrc.write_text(
            _replace_block(paths.bashrc.read_text(), BASH_START, BASH_END, bash_block)
        )
        alias_block = (
            f"{ALIAS_START}\n{paths.aliases_source.read_text().rstrip()}\n{ALIAS_END}"
        )
        existing_aliases = paths.aliases.read_text() if paths.aliases.exists() else ""
        paths.aliases.write_text(
            _replace_block(existing_aliases, ALIAS_START, ALIAS_END, alias_block)
        )

    def verify(self, paths: DotfilesPaths) -> None:
        tmux = paths.tmux_config.read_text()
        hypr = paths.hypr_bindings.read_text()
        bashrc = paths.bashrc.read_text()
        if tmux.count(TMUX_START) != 1 or tmux.count(TMUX_END) != 1:
            raise DotfilesError("tmux persistence block could not be verified")
        if hypr.count(HYPR_START) != 1 or hypr.count(HYPR_END) != 1:
            raise DotfilesError("Hyprland keybinding overrides could not be verified")
        if bashrc.count(BASH_START) != 1 or bashrc.count(BASH_END) != 1:
            raise DotfilesError("shell aliases block could not be verified")
        aliases = paths.aliases.read_text()
        if aliases.count(ALIAS_START) != 1 or aliases.count(ALIAS_END) != 1:
            raise DotfilesError("shell aliases file could not be verified")
        for line in paths.aliases_source.read_text().splitlines():
            if line and line not in aliases:
                raise DotfilesError("managed shell alias is missing")
        for name, _, revision in PLUGINS:
            result = subprocess.run(
                ("git", "-C", str(paths.plugin_root / name), "rev-parse", "HEAD"),
                text=True, capture_output=True,
            )
            if result.returncode or result.stdout.strip() != revision:
                raise DotfilesError(f"{name} revision could not be verified")


def run_dotfiles(
    *, paths: DotfilesPaths, backend: Backend, assume_yes: bool, dry_run: bool,
    stdin: TextIO, stdout: TextIO, progress: bool = True,
) -> int:
    display = ProgressDisplay(stdout, enabled=progress, quiet=False, total=4)
    display.stage(1, "Checking tmux and Hyprland configuration")
    backend.check(paths)
    if dry_run:
        display.stage(4, "Dry run complete; no dotfiles changed")
        return 0
    if not assume_yes:
        print("Install tmux persistence and change close-window to Super+Q? [y/N] ", end="", file=stdout, flush=True)
        if stdin.readline().strip().lower() not in {"y", "yes"}:
            print("Cancelled. No dotfiles changed.", file=stdout)
            return 0
    display.stage(2, "Installing pinned tmux persistence plugins")
    backend.install_plugins(paths)
    display.stage(3, "Applying managed tmux and Hyprland overrides")
    backend.apply(paths)
    display.stage(4, "Verifying managed dotfiles")
    backend.verify(paths)
    print("Dotfiles applied. New tmux servers restore the last saved layout.", file=stdout)
    return 0
