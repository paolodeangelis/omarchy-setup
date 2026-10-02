from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omarchy_setup.modules.programs.core import ProgramPaths


WINAPPS_REVISION = "42c7e8318280c6fc3426c7afebfc7f43b895f4c8"
WINAPPS_REPOSITORY = "https://github.com/winapps-org/winapps.git"
WINDOWS_IMAGE = (
    "ghcr.io/dockur/windows@"
    "sha256:32cc92715a6c5dc1f63142d3be11059279d64d0faa7519618a07290b3076f9f2"
)


class WinAppsError(RuntimeError):
    """A safe, user-facing WinApps preparation failure."""


@dataclass(frozen=True)
class WinAppsPaths:
    config_root: Path
    state_root: Path
    bin_root: Path
    data_root: Path
    templates: Path

    @classmethod
    def from_program_paths(cls, paths: ProgramPaths) -> "WinAppsPaths":
        home = paths.shell_rc.parent
        repo_root = Path(__file__).resolve().parents[4]
        return cls(
            config_root=(paths.config_home or home / ".config") / "winapps",
            state_root=(paths.state_home or home / ".local" / "state")
            / "omarchy-setup"
            / "winapps",
            bin_root=paths.bin_home or home / ".local" / "bin",
            data_root=paths.data_home / "winapps",
            templates=repo_root / "programs" / "winapps" / "templates",
        )

    @property
    def source(self) -> Path:
        return self.state_root / "upstream"

    @property
    def active_source(self) -> Path:
        return self.bin_root / "winapps-src"


class WinAppsInstaller:
    def __init__(self, paths: WinAppsPaths):
        self.paths = paths

    def is_prepared(self) -> bool:
        source = self._usable_source()
        if source is None:
            return False
        return all(
            path.exists()
            for path in (
                self.paths.config_root / "compose.yaml",
                self.paths.config_root / "winapps.conf",
                self.paths.config_root / "oem",
                self.paths.bin_root / "winapps",
            )
        )

    def prepare(self) -> None:
        self._check_host()
        self._prepare_source()
        self._prepare_active_source()
        self._install_launcher()
        self._install_templates()
        self._install_oem()
        self._write_metadata()
        if not self.is_prepared():
            raise WinAppsError("WinApps preparation could not be verified")

    def _check_host(self) -> None:
        if os.geteuid() == 0:
            raise WinAppsError("do not prepare WinApps as root")
        if not os.access("/dev/kvm", os.R_OK | os.W_OK):
            raise WinAppsError("/dev/kvm is not accessible to the current user")
        if not Path("/dev/net/tun").exists():
            raise WinAppsError("/dev/net/tun is unavailable")

    def _git_head(self, path: Path) -> str | None:
        if not (path / ".git").exists():
            return None
        result = subprocess.run(
            ("git", "-C", str(path), "rev-parse", "HEAD"),
            text=True,
            capture_output=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def _usable_source(self) -> Path | None:
        for path in (self.paths.source, self.paths.active_source):
            if self._git_head(path) == WINAPPS_REVISION:
                return path
        return None

    def _prepare_source(self) -> None:
        if self.paths.source.exists():
            head = self._git_head(self.paths.source)
            if head != WINAPPS_REVISION:
                raise WinAppsError(
                    f"refusing to replace unreviewed WinApps source at {self.paths.source}"
                )
            return
        self.paths.source.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(
                prefix="winapps-source-", dir=self.paths.source.parent
            ) as directory:
                candidate = Path(directory) / "upstream"
                subprocess.run(
                    (
                        "git",
                        "clone",
                        "--filter=blob:none",
                        "--no-checkout",
                        WINAPPS_REPOSITORY,
                        str(candidate),
                    ),
                    check=True,
                )
                subprocess.run(
                    (
                        "git",
                        "-C",
                        str(candidate),
                        "fetch",
                        "--depth=1",
                        "origin",
                        WINAPPS_REVISION,
                    ),
                    check=True,
                )
                subprocess.run(
                    (
                        "git",
                        "-C",
                        str(candidate),
                        "checkout",
                        "--detach",
                        WINAPPS_REVISION,
                    ),
                    check=True,
                )
                if self._git_head(candidate) != WINAPPS_REVISION:
                    raise WinAppsError("downloaded WinApps revision did not verify")
                candidate.rename(self.paths.source)
        except (OSError, subprocess.CalledProcessError) as error:
            raise WinAppsError(f"failed to prepare pinned WinApps source: {error}") from error

    def _prepare_active_source(self) -> None:
        active = self.paths.active_source
        if active.exists() or active.is_symlink():
            if self._git_head(active) != WINAPPS_REVISION:
                raise WinAppsError(
                    f"refusing to replace existing WinApps source at {active}"
                )
            return
        active.parent.mkdir(parents=True, exist_ok=True)
        active.symlink_to(self.paths.source)

    def _install_launcher(self) -> None:
        launcher = self.paths.bin_root / "winapps"
        target = self.paths.active_source / "bin" / "winapps"
        if launcher.exists() or launcher.is_symlink():
            if launcher.resolve() != target.resolve():
                raise WinAppsError(f"refusing to replace existing launcher {launcher}")
            return
        launcher.symlink_to(target)

    def _copy_template(self, name: str, destination: str | None = None) -> None:
        source = self.paths.templates / name
        target = self.paths.config_root / (destination or name)
        if target.exists():
            return
        if not source.is_file():
            raise WinAppsError(f"WinApps template missing: {source}")
        shutil.copy2(source, target)

    def _install_templates(self) -> None:
        self.paths.config_root.mkdir(parents=True, exist_ok=True)
        self._copy_template("compose.yaml")
        self._copy_template("winapps.conf")
        self._copy_template("credentials.env.example")
        (self.paths.config_root / "compose.yaml").chmod(0o600)
        (self.paths.config_root / "winapps.conf").chmod(0o600)

    def _install_oem(self) -> None:
        target = self.paths.config_root / "oem"
        if target.exists():
            return
        shutil.copytree(self.paths.active_source / "oem", target)

    def _write_metadata(self) -> None:
        self.paths.state_root.mkdir(parents=True, exist_ok=True)
        metadata = {
            "winapps_revision": WINAPPS_REVISION,
            "windows_image": WINDOWS_IMAGE,
            "onboarding": "required",
        }
        target = self.paths.state_root / "managed.json"
        rendered = json.dumps(metadata, indent=2, sort_keys=True) + "\n"
        if not target.exists() or target.read_text() != rendered:
            target.write_text(rendered)
