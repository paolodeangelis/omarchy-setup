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


def text_visible(text, expected):
    """Match OCR text without treating capitalization noise as a UI failure."""
    return expected.casefold() in text.casefold()


def capture_panel(output, plugin, delay=2):
    try:
        run("omarchy-shell", "shell", "summon", plugin)
        time.sleep(delay)
        layers = run("hyprctl", "layers", "-j")
        (output / f"{plugin}-layers.json").write_text(layers)
        if "omarchy-keyboard-panel" not in layers:
            raise RuntimeError(f"{plugin}: no mapped popup layer")
        screenshot = output / f"{plugin}.png"
        run("grim", str(screenshot))
        return screenshot
    finally:
        run("omarchy-shell", "shell", "hide", plugin)
        time.sleep(1)


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
    # Exercise deterministic panel rendering without asserting remote weather,
    # network, Bluetooth, audio, or battery data that a CI guest may not have.
    for plugin in ("omarchy.weather", "omarchy.bluetooth", "omarchy.network", "omarchy.audio", "omarchy.monitor"):
        capture_panel(output, plugin)

    screenshot = capture_panel(output, "jankeesvw.notification-center", delay=3)
    text = run("tesseract", str(screenshot), "stdout")
    (output / "jankeesvw.notification-center-ocr.txt").write_text(text)
    if "Notification archive integration probe" not in text:
        raise RuntimeError("notification archive content not visible; inspect screenshot/OCR")

    try:
        run("omarchy-menu", "summon", "system")
        time.sleep(2)
        menu = output / "system-menu.png"
        run("grim", str(menu))
        menu_text = run("tesseract", str(menu), "stdout")
        (output / "system-menu-ocr.txt").write_text(menu_text)
        if not text_visible(menu_text, "Shutdown"):
            raise RuntimeError("system menu content not visible; inspect screenshot/OCR")
    finally:
        run("omarchy-menu", "close")

    osd = subprocess.Popen(("omarchy-osd", "-i", "volume-high", "-p", "50", "-d", "1200"))
    time.sleep(0.35)
    run("grim", str(output / "volume-osd.png"))
    if osd.wait() != 0:
        raise RuntimeError("OSD command failed")
    log = run("journalctl", "--user", "-t", "omarchy-shell", "--since", sys.argv[2], "--no-pager", "-o", "cat")
    (output / "shell-runtime.log").write_text(log)
    validate_log(log)


if __name__ == "__main__":
    main()
