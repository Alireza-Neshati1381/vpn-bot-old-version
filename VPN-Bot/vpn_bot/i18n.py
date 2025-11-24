"""Internationalization (i18n) system for bilingual support (Persian & English).

This module provides simple translation functionality without external dependencies.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)

# Cache for loaded translations
_TRANSLATIONS: Dict[str, Dict[str, Any]] = {}

# Supported languages
SUPPORTED_LANGUAGES = ["en", "fa"]
DEFAULT_LANGUAGE = "fa"


def load_translations() -> None:
    """Load all translation files into memory."""
    translations_dir = Path(__file__).parent.parent / "translations"
    
    for lang in SUPPORTED_LANGUAGES:
        file_path = translations_dir / f"{lang}.json"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                _TRANSLATIONS[lang] = json.load(f)
            LOGGER.info("loaded translations for language: %s", lang)
        except FileNotFoundError:
            LOGGER.warning("translation file not found: %s", file_path)
            _TRANSLATIONS[lang] = {}
        except json.JSONDecodeError as exc:
            LOGGER.error("failed to parse translation file %s: %s", file_path, exc)
            _TRANSLATIONS[lang] = {}


def get_text(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """Get translated text for a given key.
    
    Parameters
    ----------
    key : str
        Translation key, can be nested using dots (e.g., 'admin.add_server')
    lang : str
        Language code ('en' or 'fa')
    **kwargs
        Format parameters for string interpolation
        
    Returns
    -------
    str
        Translated and formatted text, or the key itself if translation not found
    """
    if not _TRANSLATIONS:
        load_translations()
    
    # Fallback to default language if requested language not available
    if lang not in _TRANSLATIONS:
        lang = DEFAULT_LANGUAGE
    
    translations = _TRANSLATIONS.get(lang, {})
    
    # Navigate nested keys
    parts = key.split(".")
    value = translations
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
            break
    
    # If not found, try English as fallback
    if value is None and lang != "en":
        return get_text(key, "en", **kwargs)
    
    # If still not found, return the key itself
    if value is None:
        LOGGER.warning("translation not found: %s (lang: %s)", key, lang)
        return key
    
    # Format the string with provided kwargs
    if isinstance(value, str) and kwargs:
        try:
            return value.format(**kwargs)
        except KeyError as exc:
            LOGGER.warning("missing format parameter %s for key %s", exc, key)
            return value
    
    return str(value)


def get_user_language(user_data: Dict[str, Any]) -> str:
    """Get user's preferred language from user data.
    
    Parameters
    ----------
    user_data : dict
        User record from database
        
    Returns
    -------
    str
        Language code ('en' or 'fa')
    """
    lang = user_data.get("language", DEFAULT_LANGUAGE)
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def set_user_language(conn, user_id: int, lang: str) -> bool:
    """Set user's preferred language.
    
    Parameters
    ----------
    conn : sqlite3.Connection
        Database connection
    user_id : int
        User ID
    lang : str
        Language code ('en' or 'fa')
        
    Returns
    -------
    bool
        True if successful, False otherwise
    """
    if lang not in SUPPORTED_LANGUAGES:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET language = ? WHERE id = ?",
            (lang, user_id)
        )
        conn.commit()
        return True
    except Exception as exc:
        LOGGER.error("failed to set user language: %s", exc)
        return False


# Initialize translations on module import
load_translations()
