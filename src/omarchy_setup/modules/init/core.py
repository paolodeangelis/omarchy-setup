from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO


UV_VERSION = "0.12.19"
UV_RELEASE = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}"
UV_ARTIFACTS = {
    "x86_64": (
        "uv-x86_64-unknown-linux-gnu.tar.gz",
        "23bf5552d220e0842b65c862097b2ebaeba0064b74eda5e565e77fd25969d8c8",
    ),
    "aarch64": (
        "uv-aarch64-unknown-linux-gnu.tar.gz",
        "0804e9b164c64b6914182d5920c08551958a095986f10a3731056df701126436",
    ),
}


class InitError(RuntimeError):
    """A user-facing bootstrap safety or execution failure."""


@dataclass(frozen=True)
class InitPaths:
    repo_root: Path
    state_root: Path
    bin_dir: Path

    @classmethod
    def for_user(cls) -> "InitPaths":
        configured_root = os.environ.get("OMARCHY_SETUP_ROOT")
        repo_root = (
            Path(configured_root).resolve()
            if configured_root
            else Path(__file__).resolve().parents[4]
        )
        state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        bin_dir = Path(os.environ.get("OMARCHY_SETUP_BIN_DIR", Path.home() / ".local" / "bin"))
        return cls(
            repo_root=repo_root,
            state_root=state_home / "omarchy-setup",
            bin_dir=bin_dir,
        )

    @property
    def uv(self) -> Path:
        return self.state_root / "bin" / "uv"

    @property
    def environment(self) -> Path:
        return self.state_root / "environment"

    @property
    def previous_environment(self) -> Path:
        return self.state_root / "environment.previous"

    @property
    def environments(self) -> Path:
        return self.state_root / "environments"

    @property
    def metadata(self) -> Path:
        return self.state_root / "init.json"

    @property
    def launcher(self) -> Path:
        return self.bin_dir / "omarchy-setup"

    @property
    def source_launcher(self) -> Path:
        return self.repo_root / "omarchy-setup"


class BootstrapBackend(Protocol):
    def uv_is_current(self, uv_path: Path) -> bool: ...

    def install_uv(self, uv_path: Path) -> None: ...

    def build_environment(self, paths: InitPaths, destination: Path) -> None: ...

    def verify_environment(self, environment: Path) -> None: ...


def _run(command: tuple[str, ...], *, environment: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            env=environment,
        )
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "command failed").strip().splitlines()
        message = details[-1] if details else "command failed"
        raise InitError(f"{' '.join(command)}: {message}") from error
    return result.stdout.strip()


class UvBootstrapBackend:
    def uv_is_current(self, uv_path: Path) -> bool:
        if not uv_path.is_file() or not os.access(uv_path, os.X_OK):
            return False
        try:
            return _run((str(uv_path), "--version")).split()[1] == UV_VERSION
        except (InitError, IndexError):
            return False

    def install_uv(self, uv_path: Path) -> None:
        machine = platform.machine().lower()
        artifact = UV_ARTIFACTS.get(machine)
        if artifact is None:
            raise InitError(f"unsupported CPU architecture for uv bootstrap: {machine}")
        archive_name, expected_digest = artifact
        url = f"{UV_RELEASE}/{archive_name}"

        uv_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=uv_path.parent) as temporary_directory:
            archive = Path(temporary_directory) / archive_name
            try:
                with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as file:
                    shutil.copyfileobj(response, file)
            except OSError as error:
                raise InitError(f"failed to download uv {UV_VERSION}: {error}") from error

            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            if digest != expected_digest:
                raise InitError(
                    f"uv archive checksum mismatch: expected {expected_digest}, received {digest}"
                )

            with tarfile.open(archive, "r:gz") as tar:
                members = [member for member in tar.getmembers() if Path(member.name).name == "uv"]
                if len(members) != 1 or not members[0].isfile():
                    raise InitError("uv archive does not contain one regular uv binary")
                extracted = tar.extractfile(members[0])
                if extracted is None:
                    raise InitError("could not extract uv binary")
                candidate = Path(temporary_directory) / "uv"
                with candidate.open("wb") as file:
                    shutil.copyfileobj(extracted, file)
                candidate.chmod(candidate.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                os.replace(candidate, uv_path)

        if not self.uv_is_current(uv_path):
            raise InitError("installed uv binary failed version verification")

    def build_environment(self, paths: InitPaths, destination: Path) -> None:
        environment = os.environ.copy()
        environment.update(
            {
                "UV_CACHE_DIR": str(paths.state_root / "uv-cache"),
                "UV_PROJECT_ENVIRONMENT": str(destination),
                "UV_PYTHON_INSTALL_DIR": str(paths.state_root / "uv-python"),
                "UV_PYTHON_DOWNLOADS": "never",
            }
        )
        with tempfile.TemporaryDirectory(
            prefix="build-source-", dir=paths.state_root
        ) as temporary_directory:
            build_source = Path(temporary_directory)
            shutil.copy2(paths.repo_root / "pyproject.toml", build_source)
            shutil.copy2(paths.repo_root / "uv.lock", build_source)
            shutil.copytree(paths.repo_root / "src", build_source / "src")
            _run(
                (
                    str(paths.uv),
                    "sync",
                    "--project",
                    str(build_source),
                    "--locked",
                    "--no-dev",
                    "--no-editable",
                    "--python",
                    "/usr/bin/python3",
                ),
                environment=environment,
            )

    def verify_environment(self, environment: Path) -> None:
        command = environment / "bin" / "omarchy-setup"
        if not command.is_file():
            raise InitError("new environment does not contain omarchy-setup")
        output = _run((str(command), "--version"))
        if not output.startswith("omarchy-setup "):
            raise InitError("new environment failed CLI verification")


def project_fingerprint(repo_root: Path) -> str:
    files = [repo_root / "pyproject.toml", repo_root / "uv.lock"]
    files.extend(sorted((repo_root / "src").rglob("*.py")))
    digest = hashlib.sha256()
    for path in files:
        if not path.is_file():
            raise InitError(f"required project file missing: {path}")
        digest.update(path.relative_to(repo_root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _recorded_fingerprint(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    value = data.get("project_fingerprint")
    return value if isinstance(value, str) else None


def _launcher_is_current(paths: InitPaths) -> bool:
    return paths.launcher.is_symlink() and paths.launcher.resolve() == paths.source_launcher.resolve()


def _confirm(stdin: TextIO, stdout: TextIO) -> bool:
    print("Create or update the omarchy-setup environment? [y/N] ", end="", flush=True, file=stdout)
    return stdin.readline().strip().lower() in {"y", "yes"}


def _managed_environment_target(link: Path, environments: Path) -> Path | None:
    if not link.exists() and not link.is_symlink():
        return None
    if not link.is_symlink():
        raise InitError(f"refusing to replace non-symlink environment: {link}")
    try:
        target = link.resolve(strict=True)
    except OSError as error:
        raise InitError(f"environment link is broken: {link}") from error
    if target.parent != environments.resolve():
        raise InitError(f"environment link points outside managed state: {link}")
    return target


def _replace_symlink(link: Path, target: Path) -> None:
    temporary = link.with_name(f".{link.name}.next")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(target)
    os.replace(temporary, link)


def _activate_environment(paths: InitPaths, candidate: Path) -> None:
    old_active = _managed_environment_target(paths.environment, paths.environments)
    old_previous = _managed_environment_target(paths.previous_environment, paths.environments)

    try:
        _replace_symlink(paths.environment, candidate)
        if old_active is not None:
            _replace_symlink(paths.previous_environment, old_active)
    except OSError:
        if old_active is None:
            paths.environment.unlink(missing_ok=True)
        else:
            _replace_symlink(paths.environment, old_active)
        raise

    if old_previous is not None and old_previous not in {candidate, old_active}:
        shutil.rmtree(old_previous, ignore_errors=True)


def _install_launcher(paths: InitPaths) -> None:
    paths.bin_dir.mkdir(parents=True, exist_ok=True)
    if paths.launcher.exists() or paths.launcher.is_symlink():
        if _launcher_is_current(paths):
            return
        raise InitError(f"refusing to replace unrelated launcher: {paths.launcher}")
    temporary = paths.bin_dir / ".omarchy-setup.next"
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(paths.source_launcher)
    os.replace(temporary, paths.launcher)


def run_init(
    paths: InitPaths,
    *,
    backend: BootstrapBackend,
    assume_yes: bool,
    dry_run: bool,
    quiet: bool,
    stdin: TextIO,
    stdout: TextIO,
) -> int:
    if os.geteuid() == 0:
        raise InitError("do not run omarchy-setup init as root")
    if not paths.source_launcher.is_file():
        raise InitError(f"repository launcher missing: {paths.source_launcher}")
    if (paths.launcher.exists() or paths.launcher.is_symlink()) and not _launcher_is_current(paths):
        raise InitError(f"refusing to replace unrelated launcher: {paths.launcher}")
    _managed_environment_target(paths.environment, paths.environments)
    _managed_environment_target(paths.previous_environment, paths.environments)

    fingerprint = project_fingerprint(paths.repo_root)
    needs_uv = not backend.uv_is_current(paths.uv)
    environment_command = paths.environment / "bin" / "omarchy-setup"
    needs_environment = (
        not environment_command.is_file()
        or not os.access(environment_command, os.X_OK)
        or _recorded_fingerprint(paths.metadata) != fingerprint
    )
    if not needs_environment:
        try:
            backend.verify_environment(paths.environment)
        except InitError:
            needs_environment = True
    needs_launcher = not _launcher_is_current(paths)

    changes = []
    if needs_uv:
        changes.append(f"install uv {UV_VERSION} in {paths.uv}")
    if needs_environment:
        changes.append(f"create dedicated environment in {paths.environment}")
    if needs_launcher:
        changes.append(f"link {paths.launcher} to this repository")

    if not changes:
        backend.verify_environment(paths.environment)
        if not quiet:
            print("omarchy-setup is already initialized.", file=stdout)
        return 0

    if not quiet:
        print("Initialization plan:", file=stdout)
        for change in changes:
            print(f"  - {change}", file=stdout)

    if dry_run:
        if not quiet:
            print("Dry run complete; no files changed.", file=stdout)
        return 0
    if not assume_yes and not _confirm(stdin, stdout):
        if not quiet:
            print("Cancelled. No files changed.", file=stdout)
        return 0

    paths.state_root.mkdir(parents=True, exist_ok=True)
    if needs_uv:
        if not quiet:
            print(f"Installing verified uv {UV_VERSION}...", file=stdout)
        backend.install_uv(paths.uv)

    if needs_environment:
        if not quiet:
            print("Building and verifying dedicated Python environment...", file=stdout)
        paths.environments.mkdir(parents=True, exist_ok=True)
        candidate = Path(
            tempfile.mkdtemp(prefix=f"{fingerprint[:12]}-", dir=paths.environments)
        )
        try:
            backend.build_environment(paths, candidate)
            backend.verify_environment(candidate)
            _activate_environment(paths, candidate)
        except Exception:
            if candidate.exists():
                shutil.rmtree(candidate)
            raise
        metadata_next = paths.state_root / "init.json.next"
        metadata_next.write_text(
            json.dumps(
                {"project_fingerprint": fingerprint, "uv_version": UV_VERSION},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        os.replace(metadata_next, paths.metadata)

    if needs_launcher:
        _install_launcher(paths)

    backend.verify_environment(paths.environment)
    if not quiet:
        print(f"Ready. Run: {paths.launcher} deblob --dry-run", file=stdout)
    return 0
