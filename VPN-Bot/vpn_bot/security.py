"""Security utilities for the VPN bot.

This module provides input validation, sanitization, rate limiting,
and secure file handling.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

LOGGER = logging.getLogger(__name__)

# Security constants
MAX_STRING_LENGTH = 500
MAX_NUMERIC_VALUE = 1000000
MAX_FILENAME_LENGTH = 100
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB default


def sanitize_string(value: str, max_length: int = MAX_STRING_LENGTH) -> str:
    """Sanitize user input by removing potentially dangerous characters.
    
    Parameters
    ----------
    value : str
        Input string to sanitize
    max_length : int
        Maximum allowed length
        
    Returns
    -------
    str
        Sanitized string
    """
    if not isinstance(value, str):
        return ""
    
    # Trim to max length
    value = value[:max_length]
    
    # Remove any null bytes
    value = value.replace("\x00", "")
    
    # Strip leading/trailing whitespace
    value = value.strip()
    
    return value


def validate_numeric(value: str, min_value: int = 0, max_value: int = MAX_NUMERIC_VALUE) -> Tuple[bool, Optional[int]]:
    """Validate and parse numeric input.
    
    Parameters
    ----------
    value : str
        Input string to validate
    min_value : int
        Minimum allowed value
    max_value : int
        Maximum allowed value
        
    Returns
    -------
    tuple
        (is_valid, parsed_value)
    """
    try:
        num = int(value)
        if min_value <= num <= max_value:
            return True, num
        return False, None
    except (ValueError, TypeError):
        return False, None


def validate_float(value: str, min_value: float = 0.0, max_value: float = float(MAX_NUMERIC_VALUE)) -> Tuple[bool, Optional[float]]:
    """Validate and parse float input.
    
    Parameters
    ----------
    value : str
        Input string to validate
    min_value : float
        Minimum allowed value
    max_value : float
        Maximum allowed value
        
    Returns
    -------
    tuple
        (is_valid, parsed_value)
    """
    try:
        num = float(value)
        if min_value <= num <= max_value:
            return True, num
        return False, None
    except (ValueError, TypeError):
        return False, None


def validate_username(username: str) -> bool:
    """Validate Telegram username format.
    
    Parameters
    ----------
    username : str
        Username to validate
        
    Returns
    -------
    bool
        True if valid, False otherwise
    """
    if not username:
        return False
    
    # Remove @ if present
    username = username.lstrip("@")
    
    # Telegram usernames: 5-32 chars, alphanumeric + underscore
    pattern = r'^[a-zA-Z0-9_]{5,32}$'
    return bool(re.match(pattern, username))


def validate_url(url: str) -> bool:
    """Validate URL format.
    
    Parameters
    ----------
    url : str
        URL to validate
        
    Returns
    -------
    bool
        True if valid, False otherwise
    """
    if not url:
        return False
    
    # Basic URL validation
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    return bool(re.match(pattern, url, re.IGNORECASE))


def validate_file_extension(filename: str) -> bool:
    """Validate that file has an allowed image extension.
    
    Parameters
    ----------
    filename : str
        Filename to check
        
    Returns
    -------
    bool
        True if extension is allowed, False otherwise
    """
    if not filename:
        return False
    
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def check_rate_limit(conn, user_id: int, limit_per_minute: int = 20) -> bool:
    """Check if user has exceeded rate limit.
    
    Parameters
    ----------
    conn : sqlite3.Connection
        Database connection
    user_id : int
        User ID to check
    limit_per_minute : int
        Maximum requests per minute
        
    Returns
    -------
    bool
        True if within limit, False if exceeded
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rate_limit_count, rate_limit_reset FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return True
        
        count = row[0] or 0
        reset_time_str = row[1]
        
        now = datetime.utcnow()
        
        # Check if we need to reset the counter
        if reset_time_str:
            reset_time = datetime.fromisoformat(reset_time_str)
            if now >= reset_time:
                # Reset counter
                count = 0
                reset_time = now + timedelta(minutes=1)
        else:
            reset_time = now + timedelta(minutes=1)
        
        # Check limit
        if count >= limit_per_minute:
            LOGGER.warning("rate limit exceeded for user %s", user_id)
            log_security_event(conn, user_id, "rate_limit_exceeded", f"Exceeded {limit_per_minute} requests/min")
            return False
        
        # Increment counter
        cursor.execute(
            "UPDATE users SET rate_limit_count = ?, rate_limit_reset = ? WHERE id = ?",
            (count + 1, reset_time.isoformat(), user_id)
        )
        conn.commit()
        
        return True
        
    except Exception as exc:
        LOGGER.error("failed to check rate limit: %s", exc)
        # Fail open - allow request if we can't check
        return True


def log_security_event(conn, user_id: Optional[int], event_type: str, description: str, telegram_id: Optional[str] = None) -> None:
    """Log a security-related event.
    
    Parameters
    ----------
    conn : sqlite3.Connection
        Database connection
    user_id : int or None
        User ID if available
    event_type : str
        Type of security event
    description : str
        Event description
    telegram_id : str or None
        Telegram ID if user_id not available
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO security_events (user_id, telegram_id, event_type, description) VALUES (?, ?, ?, ?)",
            (user_id, telegram_id, event_type, description)
        )
        conn.commit()
        LOGGER.info("security event logged: %s - %s", event_type, description)
    except Exception as exc:
        LOGGER.error("failed to log security event: %s", exc)


def secure_filename(filename: str) -> str:
    """Generate a secure filename by removing dangerous characters.
    
    Parameters
    ----------
    filename : str
        Original filename
        
    Returns
    -------
    str
        Sanitized filename
    """
    # Remove path components
    filename = os.path.basename(filename)
    
    # Keep only alphanumeric, dots, dashes, and underscores
    filename = re.sub(r'[^a-zA-Z0-9._-]', '', filename)
    
    # Limit length
    if len(filename) > MAX_FILENAME_LENGTH:
        ext = Path(filename).suffix
        name = Path(filename).stem[:MAX_FILENAME_LENGTH-len(ext)]
        filename = name + ext
    
    return filename or "unknown"


def get_secure_upload_path(upload_dir: str, user_id: int, filename: str) -> Path:
    """Generate a secure path for uploaded files.
    
    Parameters
    ----------
    upload_dir : str
        Base upload directory
    user_id : int
        User ID
    filename : str
        Original filename
        
    Returns
    -------
    Path
        Secure file path
    """
    # Create user-specific subdirectory
    user_dir = Path(upload_dir) / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    ext = Path(filename).suffix
    secure_name = f"{timestamp}_{secure_filename(filename)}"
    
    return user_dir / secure_name


def validate_admin_pin(provided_pin: str, correct_pin: str) -> bool:
    """Validate admin PIN in constant time to prevent timing attacks.
    
    Parameters
    ----------
    provided_pin : str
        PIN provided by user
    correct_pin : str
        Correct PIN from configuration
        
    Returns
    -------
    bool
        True if PIN matches, False otherwise
    """
    if not provided_pin or not correct_pin:
        return False
    
    # Constant-time comparison
    if len(provided_pin) != len(correct_pin):
        return False
    
    result = 0
    for a, b in zip(provided_pin, correct_pin):
        result |= ord(a) ^ ord(b)
    
    return result == 0
