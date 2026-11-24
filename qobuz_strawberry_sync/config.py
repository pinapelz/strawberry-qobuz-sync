"""Discovery of Strawberry paths and reading Qobuz credentials from strawberry.conf."""

from __future__ import annotations

import configparser
import os
from pathlib import Path

from .models import ConfigError, Credentials


def _clean_qsettings_value(raw: str) -> str:
    val = raw.strip()
    if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
        val = val[1:-1]
    if val.startswith("@Invalid("):
        return ""
    return val


def candidate_config_paths() -> list[Path]:
    home = Path.home()
    xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return [
        xdg_config / "strawberry" / "strawberry.conf",
        home
        / ".var"
        / "app"
        / "org.strawberrymusicplayer.strawberry"
        / "config"
        / "strawberry"
        / "strawberry.conf",
    ]


def candidate_db_paths() -> list[Path]:
    home = Path.home()
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return [
        xdg_data / "strawberry" / "strawberry" / "strawberry.db",
        home
        / ".var"
        / "app"
        / "org.strawberrymusicplayer.strawberry"
        / "data"
        / "strawberry"
        / "strawberry"
        / "strawberry.db",
    ]


def resolve_config_path(explicit_path: str | Path | None = None) -> Path:
    if explicit_path:
        p = Path(explicit_path).expanduser()
        if not p.is_file():
            raise ConfigError(f"Config file not found: {p}")
        return p
    for candidate in candidate_config_paths():
        if candidate.is_file():
            return candidate
    searched = "\n  - ".join(str(p) for p in candidate_config_paths())
    raise ConfigError(
        f"Could not locate strawberry.conf automatically. Checked:\n  - {searched}\n"
        "Pass --config-path to specify its location."
    )


def resolve_db_path(explicit_path: str | Path | None = None) -> Path:
    if explicit_path:
        p = Path(explicit_path).expanduser()
        if not p.is_file():
            raise ConfigError(f"Database file not found: {p}")
        return p
    for candidate in candidate_db_paths():
        if candidate.is_file():
            return candidate
    searched = "\n  - ".join(str(p) for p in candidate_db_paths())
    raise ConfigError(
        f"Could not locate strawberry.db automatically. Checked:\n  - {searched}\n"
        "Pass --db-path to specify its location."
    )


def load_strawberry_credentials(config_path: Path) -> Credentials:
    parser = configparser.RawConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read(config_path, encoding="utf-8")

    conf_values: dict[str, str] = {}
    for section in parser.sections():
        if section.lower() == "qobuz":
            conf_values = {k: _clean_qsettings_value(v) for k, v in parser.items(section)}
            break

    app_id = conf_values.get("app_id", "")
    user_auth_token = conf_values.get("user_auth_token", "")
    if not app_id or not user_auth_token:
        raise ConfigError(
            f"Missing Qobuz credentials in {config_path}. "
            "Log in to Qobuz inside Strawberry (Settings -> Qobuz) first."
        )

    return Credentials(app_id=app_id, user_auth_token=user_auth_token)
