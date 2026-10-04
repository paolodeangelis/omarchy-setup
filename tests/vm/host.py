"""Run a reviewed official ISO harness on an ephemeral GitHub KVM runner."""
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


def run_streamed(args, log):
    """Mirror a long-running command to Actions output and its artifact log."""
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    try:
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
    finally:
        process.stdout.close()
    returncode = process.wait()
    if returncode:
        raise subprocess.CalledProcessError(returncode, args)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("official harness contract changed; review adapter before running")
    return text.replace(old, new, 1)


def adapt_harness(text, upgrade, ovmf_code=None, ovmf_vars=None, image_command="magick"):
    # The workflow provisions its ephemeral host. Guest package operations
    # remain inside the VM.
    text = replace_once(text,
        "omarchy-pkg-add qemu-full edk2-ovmf socat imagemagick tesseract tesseract-data-eng",
        "# Runner prerequisites checked by omarchy-setup tests/vm/host.py")
    if ovmf_code and ovmf_vars:
        text = replace_once(text,
            'OVMF_CODE="/usr/share/edk2/x64/OVMF_CODE.4m.fd"',
            f'OVMF_CODE="{ovmf_code}"')
        text = replace_once(text,
            'OVMF_VARS_TEMPLATE="/usr/share/edk2/x64/OVMF_VARS.4m.fd"',
            f'OVMF_VARS_TEMPLATE="{ovmf_vars}"')
    if image_command != "magick":
        if text.count("  magick ") != 2:
            raise RuntimeError("official image conversion contract changed; review adapter")
        text = text.replace("  magick ", f"  {image_command} ")
    # App installation can exceed upstream's 420-second per-test limit.
    text = replace_once(text,
        "OMARCHY_PATH=/usr/share/omarchy OMARCHY_ACCEPTANCE_DIR=/tmp/omarchy-acceptance",
        "OMARCHY_ACCEPTANCE_TEST_TIMEOUT=10800 OMARCHY_PATH=/usr/share/omarchy OMARCHY_ACCEPTANCE_DIR=/tmp/omarchy-acceptance")
    # Share a guest TTY for sudo's normal timestamp cache across setup children.
    # Do not add a TTY to artifact tar transport.
    text = replace_once(text, 'ssh_guest "OMARCHY_ACCEPTANCE_TEST_TIMEOUT=',
                        'ssh_guest -tt "OMARCHY_ACCEPTANCE_TEST_TIMEOUT=')
    # The graphical greeter can reclaim the active VT during first boot. The
    # upstream harness types the console login blind, then waits two minutes
    # before retrying. Wait for the real getty prompts and use short early SSH
    # probes while retaining a longer final allowance for a genuinely slow VM.
    text = replace_once(text, '''  local attempt
  for attempt in 1 2 3; do
    press ctrl-alt-f3
    sleep 8
    press ret # settle a half-typed prompt from a previous attempt
    sleep 2
    type_text "$GUEST_USER"
    capture_console "success-first-boot-03-console-username"
    press ret
    sleep 3
    type_text "$GUEST_PASSWORD"
    press ret
    sleep 4
    type_text "curl -fsS http://10.0.2.2:$HTTP_PORT/bootstrap -o /tmp/bs && bash /tmp/bs"
    capture_console "success-first-boot-05-bootstrap-command"
    press ret

    if wait_for_ssh 120 "failure-first-boot-ssh-timeout-$attempt"; then''', '''  local attempt ssh_timeout
  for attempt in 1 2 3; do
    log "SSH bootstrap attempt $attempt/3"
    press ctrl-alt-f3
    sleep 3
    press ctrl-d # leave a prior shell/password prompt in a known getty state
    if ! wait_for_screen "login:" 30; then
      continue
    fi
    type_text "$GUEST_USER"
    capture_console "success-first-boot-03-console-username"
    press ret
    if ! wait_for_screen "Password:" 20; then
      continue
    fi
    type_text "$GUEST_PASSWORD"
    press ret
    sleep 3
    type_text "curl -fsS http://10.0.2.2:$HTTP_PORT/bootstrap -o /tmp/bs && bash /tmp/bs"
    capture_console "success-first-boot-05-bootstrap-command"
    press ret

    ssh_timeout=30
    ((attempt == 3)) && ssh_timeout=120
    if wait_for_ssh "$ssh_timeout" "failure-first-boot-ssh-timeout-$attempt"; then''')
    text = replace_once(text, '''    sleep 5
    ((waited += 5))
  done
}''', '''    if ((waited % 15 == 0)); then
      echo "    ... waiting for SSH (${waited}/${timeout}s)"
    fi
    sleep 5
    ((waited += 5))
  done
}''')
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


def first_file(candidates):
    return next((path for path in map(Path, candidates) if path.is_file()), None)


def main():
    repo = Path(__file__).resolve().parents[2]
    plan = json.loads(Path(sys.argv[1]).read_text())
    artifacts = repo / "vm-artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "release.json").write_text(json.dumps(plan, indent=2))
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") not in {"github-hosted", "self-hosted"}:
        raise RuntimeError("requires an ephemeral GitHub Actions VM runner; never run on the workstation")
    image_command = "magick" if shutil.which("magick") else "convert"
    for command in ("qemu-system-x86_64", "qemu-img", "socat", image_command, "tesseract", "ssh", "curl", "git"):
        if not shutil.which(command):
            raise RuntimeError(f"runner prerequisite missing: {command}")
    ovmf_code = first_file((
        "/usr/share/edk2/x64/OVMF_CODE.4m.fd",
        "/usr/share/OVMF/OVMF_CODE_4M.fd",
    ))
    ovmf_vars = first_file((
        "/usr/share/edk2/x64/OVMF_VARS.4m.fd",
        "/usr/share/OVMF/OVMF_VARS_4M.fd",
    ))
    if not ovmf_code or not ovmf_vars:
        raise RuntimeError("runner OVMF 4M firmware missing")
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
        program.write_text(adapt_harness(
            program.read_text(), plan["mode"] == "upgrade",
            str(ovmf_code), str(ovmf_vars), image_command,
        ))
        shutil.copy2(program, artifacts / "adapted-harness.sh")
        iso = work / plan["iso_name"]
        run("curl", "--fail", "--location", "--retry", "3", plan["iso_url"], "--output", str(iso))
        with iso.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != plan["iso_sha256"]:
            raise RuntimeError("downloaded ISO checksum mismatch")
        try:
            with (artifacts / "harness.log").open("w") as log:
                run_streamed(("bash", str(program), str(iso), "--sync-omarchy", str(source),
                    "--memory", "5120", "--no-preview"), log)
        finally:
            # Do not upload test-runs wholesale: it contains private SSH keys,
            # guest disks, firmware state, and potentially credentials.
            for item in (harness / "test-runs").rglob("*"):
                if item.is_file() and item.suffix in {".png", ".mp4", ".json", ".jsonl", ".log", ".txt"}:
                    dest = artifacts / "guest" / item.relative_to(harness / "test-runs")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)


if __name__ == "__main__":
    main()
