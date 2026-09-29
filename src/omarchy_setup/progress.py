from __future__ import annotations

import os
from typing import TextIO


class ProgressDisplay:
    """Tqdm-backed progress with bootstrap and non-interactive fallbacks."""

    def __init__(self, stream: TextIO, *, enabled: bool, quiet: bool, total: int):
        self.stream = stream
        self.enabled = enabled and not quiet
        self.quiet = quiet
        self.total = total
        self.current = 0
        self._bar = None
        if self.enabled and getattr(self.stream, "isatty", lambda: False)():
            try:
                from tqdm import tqdm

                self._bar = tqdm(
                    total=total,
                    file=stream,
                    desc="Starting",
                    dynamic_ncols=True,
                    leave=True,
                    unit="step",
                    colour="cyan",
                    bar_format="{percentage:3.0f}% {bar}  {desc}",
                )
            except ImportError:
                # `init` starts under system Python before the managed
                # environment (and therefore tqdm) exists.
                self._bar = None

    def stage(self, step: int, text: str) -> None:
        if self.quiet:
            return
        if self._bar is not None:
            self._bar.set_description_str(text, refresh=False)
            self._bar.update(max(0, step - self.current))
            self.current = max(self.current, step)
            if step >= self.total:
                self._bar.close()
            else:
                self._bar.refresh()
            return
        if not self.enabled or not getattr(self.stream, "isatty", lambda: False)():
            print(f"[{step}/{self.total}] {text}", file=self.stream)
            return

        width = 28
        filled = round(width * step / self.total)
        bar = "█" * filled + "░" * (width - filled)
        percent = round(100 * step / self.total)
        color = "" if os.environ.get("NO_COLOR") else "\033[38;5;39m"
        reset = "" if not color else "\033[0m"
        print(f"{color}[{bar}] {percent:3d}%{reset}  {text}", file=self.stream)

    def message(self, text: str = "") -> None:
        if self.quiet:
            return
        if self._bar is not None:
            self._bar.write(text, file=self.stream)
        else:
            print(text, file=self.stream)
