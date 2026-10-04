"""Adapt only terminal lifecycle for the disposable guest's official updater."""
import os
from pathlib import Path
import subprocess
import tempfile


def adapt_update(source):
    replacements = {
        "  omarchy-update-status\n": "  timeout --kill-after=5s 60s omarchy-update-status\n",
        "  omarchy-update-restart\n": (
            "  echo 'CI: reboot deferred to the VM harness; post-reboot checks are required'\n"
        ),
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise RuntimeError("updater lifecycle changed; review CI adapter")
        source = source.replace(old, new, 1)
    return source


def main():
    if subprocess.check_output(["hostname"], text=True).strip() != "omarchy-test":
        raise RuntimeError("requires disposable acceptance guest")
    subprocess.run(["systemd-detect-virt", "--vm"], check=True)
    root = Path("/usr/share/omarchy")
    source = adapt_update((root / "bin/omarchy-update").read_text())
    # guest.sh tees output into /tmp/omarchy-update.log before this starts.
    # Keep the existing authorized TTY instead of creating another with script.
    environment = dict(os.environ, OMARCHY_UPDATE_LOGGED="1", OMARCHY_PATH=str(root))
    environment["PATH"] = str(root / "bin") + ":" + os.environ["PATH"]
    with tempfile.TemporaryDirectory(prefix="omarchy-ci-update-") as directory:
        updater = Path(directory) / "update"
        updater.write_text(source)
        updater.chmod(0o700)
        result = subprocess.run([str(updater), "-y"], env=environment)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
