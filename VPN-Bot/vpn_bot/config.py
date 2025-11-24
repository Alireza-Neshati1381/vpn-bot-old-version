"""Configuration loader for the VPN bot.

Configuration is loaded from environment variables or .env files.
The python-dotenv package is used for .env file support, but the code
remains compatible with environments where it's not available.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


@dataclass
class Settings:
    """Configuration values required by the application."""

    bot_token: str
    admin_pin: str
    database_path: str = "vpn_bot.sqlite3"
    poll_interval: float = 1.0
    xui_verify_ssl: bool = False
    rate_limit_per_min: int = 20
    max_receipt_size_mb: float = 5.0
    receipt_storage: str = "local"
    receipt_upload_dir: str = "uploads/receipts"
    default_language: str = "fa"
    log_level: str = "INFO"


def load_settings() -> Settings:
    """Load settings from environment variables.

    Automatically loads .env file from VPN-Bot directory if python-dotenv is available.
    Environment variables take precedence over .env file values.

    Returns
    -------
    Settings
        The populated configuration dataclass. Raises ``RuntimeError`` if the
        bot token or admin PIN is missing.
    """
    # Try to load .env file if python-dotenv is available
    # This is done inside the function to avoid issues during module import
    try:
        from dotenv import load_dotenv
        # Load .env file from the VPN-Bot directory (parent of vpn_bot package)
        # Allow override via DOTENV_PATH environment variable
        dotenv_path = os.environ.get("DOTENV_PATH")
        if dotenv_path:
            env_path = Path(dotenv_path)
        else:
            env_path = Path(__file__).parent.parent / '.env'
        
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
    except ImportError:
        # python-dotenv not available, rely on environment variables only
        pass

    # SECURITY: Bot token must be set (via environment variable or .env file)
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")

    # SECURITY: Admin PIN must be set (via environment variable or .env file)
    admin_pin = os.environ.get("BOT_ADMIN_PIN")
    if not admin_pin:
        raise RuntimeError("BOT_ADMIN_PIN environment variable is required")

    db_path = os.environ.get("DB_PATH", "vpn_bot.sqlite3")
    
    poll_interval_raw = os.environ.get("POLL_INTERVAL", "1.0")
    try:
        poll_interval = float(poll_interval_raw)
    except ValueError as exc:  # pragma: no cover - defensive branch
        raise RuntimeError("POLL_INTERVAL must be a number") from exc

    verify_ssl = os.environ.get("XUI_VERIFY_SSL", "0") not in {"0", "false", "False"}

    # Rate limiting
    rate_limit_raw = os.environ.get("RATE_LIMIT_PER_MIN", "20")
    try:
        rate_limit = int(rate_limit_raw)
    except ValueError:
        rate_limit = 20

    # Receipt handling
    max_receipt_size_raw = os.environ.get("MAX_RECEIPT_SIZE_MB", "5.0")
    try:
        max_receipt_size = float(max_receipt_size_raw)
    except ValueError:
        max_receipt_size = 5.0

    receipt_storage = os.environ.get("RECEIPT_STORAGE", "local")
    receipt_upload_dir = os.environ.get("RECEIPT_UPLOAD_DIR", "uploads/receipts")

    # Language settings
    default_language = os.environ.get("DEFAULT_LANGUAGE", "fa")
    if default_language not in ["en", "fa"]:
        default_language = "fa"

    # Logging
    log_level = os.environ.get("LOG_LEVEL", "INFO")

    return Settings(
        bot_token=token,
        admin_pin=admin_pin,
        database_path=db_path,
        poll_interval=poll_interval,
        xui_verify_ssl=verify_ssl,
        rate_limit_per_min=rate_limit,
        max_receipt_size_mb=max_receipt_size,
        receipt_storage=receipt_storage,
        receipt_upload_dir=receipt_upload_dir,
        default_language=default_language,
        log_level=log_level,
    )
