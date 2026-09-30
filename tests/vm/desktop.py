"""Disposable-guest companion panel evidence; not an animation quality oracle."""
import json
from pathlib import Path
import subprocess
import sys
import time

from omarchy_setup.modules.doctor.core import shell_log_findings


def run(*args):
    return subprocess.check_output(args, text=True)


def validate_log(log):
    lines = [line for line in log.splitlines() if line.strip() and not line.startswith("-- ")]
    if not lines:
        raise RuntimeError("shell log unavailable: cannot establish runtime health")
    suspicious, _known_stock = shell_log_findings(log)
    if suspicious:
        raise RuntimeError("shell runtime errors detected; inspect shell-runtime.log")


def main():
    if run("hostname").strip() != "omarchy-test":
        raise RuntimeError("only run in the disposable acceptance guest")
    run("systemd-detect-virt", "--vm")
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    revisions = {}
    for directory in (Path.home() / ".config/omarchy/plugins").iterdir():
        if (directory / ".git").exists():
            revisions[directory.name] = run("git", "-C", str(directory), "rev-parse", "HEAD").strip()
    (output / "plugin-revisions.json").write_text(json.dumps(revisions, indent=2))
    run("notify-send", "Olio acceptance", "Notification archive integration probe")
    time.sleep(3)
    (output / "coverage.json").write_text(json.dumps({
        "radar_preview": "unverified: requires clicking the bar widget; summon opens a different surface",
        "spaces_interactions": "unverified: hover, settings, persistence and multi-output need UI acceptance",
        "animation_smoothness": "unverified: requires recorded transitions and frame review",
    }, indent=2))
    for plugin in ("jankeesvw.notification-center",):
        try:
            run("omarchy-shell", "shell", "summon", plugin)
            time.sleep(3)
            layers = run("hyprctl", "layers", "-j")
            (output / f"{plugin}-layers.json").write_text(layers)
            if "omarchy-keyboard-panel" not in layers:
                raise RuntimeError(f"{plugin}: no mapped popup layer")
            screenshot = output / f"{plugin}.png"
            run("grim", str(screenshot))
            text = run("tesseract", str(screenshot), "stdout")
            (output / f"{plugin}-ocr.txt").write_text(text)
            if plugin == "jankeesvw.notification-center" and "Notification archive integration probe" not in text:
                raise RuntimeError("notification archive content not visible; inspect screenshot/OCR")
        finally:
            run("omarchy-shell", "shell", "hide", plugin)
            time.sleep(1)
    log = run("journalctl", "--user", "-t", "omarchy-shell", "--since", sys.argv[2], "--no-pager", "-o", "cat")
    (output / "shell-runtime.log").write_text(log)
    validate_log(log)


if __name__ == "__main__":
    main()
