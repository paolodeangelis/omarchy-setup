"""Disposable-guest companion panel evidence; not an animation quality oracle."""
import json
from pathlib import Path
import shutil
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


def current_boot_shell_log():
    return run("journalctl", "--user", "-b", "-t", "omarchy-shell", "--no-pager", "-o", "cat")


def text_visible(text, expected):
    """Match OCR text without treating capitalization noise as a UI failure."""
    return expected.casefold() in text.casefold()


def notification_crop_geometry(width, height):
    """Crop the right-side archive's first cards, scaled to the captured display."""
    crop_width = round(width * 0.328125)
    crop_height = round(height * 0.3125)
    left = width - crop_width
    top = round(height * 0.125)
    return f"{crop_width}x{crop_height}+{left}+{top}"


def notification_archive_ocr(screenshot, output):
    image_tool = shutil.which("magick") or shutil.which("convert")
    if not image_tool:
        raise RuntimeError("ImageMagick is required to inspect the notification panel crop")
    dimensions = run("identify", "-format", "%w %h", str(screenshot))
    width, height = map(int, dimensions.split())
    crop = output / "notification-center-ocr-crop.png"
    run(image_tool, str(screenshot), "-crop", notification_crop_geometry(width, height), "+repage", str(crop))
    return run("tesseract", str(crop), "stdout", "--psm", "6")


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
    text = notification_archive_ocr(screenshot, output)
    (output / "jankeesvw.notification-center-ocr.txt").write_text(text)
    # The archive retains one probe per tested theme mode. OCR may misread
    # the final word ("probe" -> "prove") when multiple cards are visible.
    if not text_visible(text, "Notification archive integration"):
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
    log = current_boot_shell_log()
    (output / "shell-runtime.log").write_text(log)
    validate_log(log)


if __name__ == "__main__":
    main()
