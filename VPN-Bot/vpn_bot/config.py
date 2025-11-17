"""Configuration loader for the VPN bot.

The project avoids optional dependencies and reads all configuration
from environment variables so it can run in simple environments.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional


@dataclass
class Settings:
    """Configuration values required by the application."""

    bot_token: str
    database_path: str = "vpn_bot.sqlite3"
    poll_interval: float = 1.0
    xui_verify_ssl: bool = False


def load_settings() -> Settings:
    """Load settings from environment variables.

    Returns
    -------
    Settings
        The populated configuration dataclass. Raises ``RuntimeError`` if the
        bot token is missing because nothing can work without it.
    """

    token = os.environ.get("BOT_TOKEN", "8259324966:AAH5VHzrtO5bwUjcX6LRv4BJwczZdCcgefg")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    db_path = os.environ.get("DB_PATH", "vpn_bot.sqlite3")
    poll_interval_raw = os.environ.get("POLL_INTERVAL", "1.0")
    try:
        poll_interval = float(poll_interval_raw)
    except ValueError as exc:  # pragma: no cover - defensive branch
        raise RuntimeError("POLL_INTERVAL must be a number") from exc

    verify_ssl = os.environ.get("XUI_VERIFY_SSL", "0") not in {"0", "false", "False"}

    return Settings(
        bot_token=token,
        database_path=db_path,
        poll_interval=poll_interval,
        xui_verify_ssl=verify_ssl,
    )
