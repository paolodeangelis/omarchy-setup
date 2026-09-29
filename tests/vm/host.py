"""Run a reviewed official ISO harness on a dedicated, disposable KVM runner."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("official harness contract changed; review adapter before running")
    return text.replace(old, new, 1)


def adapt_harness(text, upgrade):
    # The dedicated runner is pre-provisioned. The harness must not install
    # packages on it. Guest package operations remain inside the VM.
    text = replace_once(text,
        "omarchy-pkg-add qemu-full edk2-ovmf socat imagemagick tesseract tesseract-data-eng",
        "# Runner prerequisites checked by omarchy-setup tests/vm/host.py")
    # App installation can exceed upstream's 420-second per-test limit.
    text = replace_once(text,
        "OMARCHY_PATH=/usr/share/omarchy OMARCHY_ACCEPTANCE_DIR=/tmp/omarchy-acceptance",
        "OMARCHY_ACCEPTANCE_TEST_TIMEOUT=10800 OMARCHY_PATH=/usr/share/omarchy OMARCHY_ACCEPTANCE_DIR=/tmp/omarchy-acceptance")
    # Share a guest TTY for sudo's normal timestamp cache across setup children.
    # Do not add a TTY to artifact tar transport.
    text = replace_once(text, 'ssh_guest "OMARCHY_ACCEPTANCE_TEST_TIMEOUT=',
                        'ssh_guest -tt "OMARCHY_ACCEPTANCE_TEST_TIMEOUT=')
    if upgrade:
        anchor = '  log "Collecting artifacts into $RUN_DIR"'
        reboot = '''  if ((status == 0)); then
    log "Rebooting the configured upgraded guest without replacing its disk"
    stop_vm
    start_vm "$RUN_DIR/run.qcow2" "$RUN_DIR/serial-post-upgrade.log"
    establish_session
    ssh_guest -tt "OMARCHY_ACCEPTANCE_SUDO_PASSWORD=$GUEST_PASSWORD bash .local/share/omarchy/test/omarchy-setup/tests/vm/guest.sh post-upgrade" || status=$?
  fi
'''
        text = replace_once(text, anchor, reboot + anchor)
    return text


def main():
    repo = Path(__file__).resolve().parents[2]
    plan = json.loads(Path(sys.argv[1]).read_text())
    artifacts = repo / "vm-artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "release.json").write_text(json.dumps(plan, indent=2))
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "self-hosted":
        raise RuntimeError("requires a dedicated self-hosted Actions VM runner; never run on the workstation")
    for command in ("qemu-system-x86_64", "qemu-img", "socat", "magick", "tesseract", "ssh", "curl", "git"):
        if not shutil.which(command):
            raise RuntimeError(f"runner prerequisite missing: {command}")
    for firmware in ("OVMF_CODE.4m.fd", "OVMF_VARS.4m.fd"):
        if not Path("/usr/share/edk2/x64", firmware).is_file():
            raise RuntimeError(f"runner firmware missing: {firmware}")
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        raise RuntimeError("runner has no usable KVM device")
    run("git", "rev-parse", "HEAD", stdout=(artifacts / "utility-commit.txt").open("w"))
    with tempfile.TemporaryDirectory(prefix="omarchy-ci-", dir=os.environ.get("RUNNER_TEMP")) as directory:
        work = Path(directory)
        harness = work / "iso"
        source = work / "upstream"
        run("git", "clone", "https://github.com/omacom/omarchy-iso.git", str(harness))
        run("git", "-C", str(harness), "checkout", "--detach", plan["harness_commit"])
        run("git", "clone", "https://github.com/omacom/omarchy.git", str(source))
        run("git", "-C", str(source), "checkout", "--detach", plan["upstream_commit"])
        if plan["mode"] == "upgrade":
            # Store the candidate acceptance suite separately; never sync
            # candidate product source over the installed baseline.
            run("git", "-C", str(source), "archive", "--format=tar", "--output=" + str(work / "candidate.tar"), plan["candidate_commit"], "test")
            (source / "test/candidate").mkdir()
            run("tar", "-xf", str(work / "candidate.tar"), "-C", str(source / "test/candidate"))
        setup = source / "test/omarchy-setup"
        run("git", "-C", str(repo), "archive", "--format=tar", "--output=" + str(work / "setup.tar"), "HEAD")
        setup.mkdir()
        run("tar", "-xf", str(work / "setup.tar"), "-C", str(setup))
        (setup / "tests/vm/run.json").write_text(json.dumps(plan))
        original = source / "test/acceptance"
        original.rename(source / "test/acceptance-upstream")
        original.write_text('#!/bin/bash\nexec bash "$(dirname "$0")/omarchy-setup/tests/vm/guest.sh" initial\n')
        program = harness / "bin/omarchy-iso-test"
        program.write_text(adapt_harness(program.read_text(), plan["mode"] == "upgrade"))
        shutil.copy2(program, artifacts / "adapted-harness.sh")
        iso = work / plan["iso_name"]
        run("curl", "--fail", "--location", "--retry", "3", plan["iso_url"], "--output", str(iso))
        with iso.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != plan["iso_sha256"]:
            raise RuntimeError("downloaded ISO checksum mismatch")
        try:
            with (artifacts / "harness.log").open("w") as log:
                run("bash", str(program), str(iso), "--sync-omarchy", str(source), "--no-preview", stdout=log, stderr=subprocess.STDOUT)
        finally:
            # Do not upload test-runs wholesale: it contains private SSH keys,
            # guest disks, firmware state, and potentially credentials.
            for item in (harness / "test-runs").rglob("*"):
                if item.is_file() and item.suffix in {".png", ".mp4", ".json", ".log", ".txt"}:
                    dest = artifacts / "guest" / item.relative_to(harness / "test-runs")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)


if __name__ == "__main__":
    main()
