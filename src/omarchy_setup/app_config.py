from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


class AppConfigError(RuntimeError):
    """Invalid editable application defaults."""


@dataclass(frozen=True)
class AppConfig:
    browser: str
    mail: str
    browser_new_window: str
    mail_open: str
    mail_compose: str


def default_app_config_path() -> Path:
    root = os.environ.get("OMARCHY_SETUP_ROOT")
    return (Path(root) if root else Path(__file__).resolve().parents[2]) / "config" / "apps.toml"


def load_app_config(path: Path | None = None) -> AppConfig:
    source = path or default_app_config_path()
    try:
        document = tomllib.loads(source.read_text())
        defaults = document["defaults"]
        keybindings = document["keybindings"]
        values = AppConfig(
            browser=defaults["browser"],
            mail=defaults["mail"],
            browser_new_window=keybindings["browser"]["new_window"],
            mail_open=keybindings["mail"]["open"],
            mail_compose=keybindings["mail"]["compose"],
        )
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise AppConfigError(f"cannot read application configuration {source}: {error}") from error
    for label, value in vars(values).items():
        if not isinstance(value, str) or not value.strip():
            raise AppConfigError(f"{label} must be a non-empty string")
    for binding in (values.browser_new_window, values.mail_open, values.mail_compose):
        if not re.fullmatch(r"[A-Z0-9 +_-]+", binding):
            raise AppConfigError(f"invalid keybinding: {binding!r}")
    return values
