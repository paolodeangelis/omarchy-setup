"""Disposable-guest companion panel evidence; not an animation quality oracle."""
import json
from pathlib import Path
import subprocess
import sys
import time


def run(*args):
    return subprocess.check_output(args, text=True)


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
    # Shell summon opens the plugin panel, not the radar's standalone window.
    for plugin in ("com.omastorm.radar", "jankeesvw.notification-center"):
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


if __name__ == "__main__":
    main()
