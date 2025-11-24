"""Pricing calculation engine for VPN subscriptions.

This module handles both prebuilt package pricing and dynamic per-GB pricing.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)

# Pricing constraints
MAX_VOLUME_GB = 1000


def calculate_prebuilt_price(plan: Dict) -> float:
    """Calculate price for a prebuilt package.
    
    Parameters
    ----------
    plan : dict
        Plan record from database
        
    Returns
    -------
    float
        Total price
    """
    return float(plan.get("price", 0))


def calculate_pergb_price(
    volume_gb: int,
    duration_months: int,
    num_users: int,
    pricing: Dict
) -> Tuple[float, Dict[str, float]]:
    """Calculate price using per-GB pricing model.
    
    Parameters
    ----------
    volume_gb : int
        Volume in gigabytes
    duration_months : int
        Duration in months
    num_users : int
        Number of concurrent users
    pricing : dict
        Server pricing record from database
        
    Returns
    -------
    tuple
        (total_price, breakdown_dict)
    """
    breakdown = {}
    
    # Base price for first month
    price_per_gb = float(pricing.get("price_per_gb", 0))
    base_price = volume_gb * price_per_gb
    breakdown["base_volume"] = base_price
    
    # Additional months pricing
    extra_months = max(0, duration_months - 1)
    extra_month_price = 0
    
    if extra_months > 0:
        # Check if percentage or absolute pricing is configured
        extra_percent = pricing.get("extra_month_price_percent")
        extra_absolute = pricing.get("extra_month_price_absolute")
        
        if extra_percent is not None:
            # Percentage-based pricing
            extra_month_price = base_price * (float(extra_percent) / 100) * extra_months
        elif extra_absolute is not None:
            # Absolute pricing per extra month
            extra_month_price = float(extra_absolute) * extra_months
        else:
            # Default: proportional pricing (same as first month)
            extra_month_price = base_price * extra_months
        
        breakdown["extra_months"] = extra_month_price
    
    # Additional users pricing
    extra_users = max(0, num_users - 1)
    extra_users_price = 0
    
    if extra_users > 0:
        additional_user_price = float(pricing.get("additional_user_price", 0))
        extra_users_price = additional_user_price * extra_users
        breakdown["extra_users"] = extra_users_price
    
    # Total
    total = base_price + extra_month_price + extra_users_price
    breakdown["total"] = total
    
    return total, breakdown


def format_price_breakdown(breakdown: Dict[str, float], lang: str = "en") -> str:
    """Format price breakdown for display.
    
    Parameters
    ----------
    breakdown : dict
        Price breakdown dictionary
    lang : str
        Language code
        
    Returns
    -------
    str
        Formatted breakdown text
    """
    lines = []
    
    if lang == "fa":
        if "base_volume" in breakdown:
            lines.append(f"قیمت پایه: {breakdown['base_volume']:.2f}")
        if "extra_months" in breakdown:
            lines.append(f"ماه‌های اضافی: {breakdown['extra_months']:.2f}")
        if "extra_users" in breakdown:
            lines.append(f"کاربران اضافی: {breakdown['extra_users']:.2f}")
        if "total" in breakdown:
            lines.append(f"━━━━━━━━━━━━")
            lines.append(f"جمع کل: {breakdown['total']:.2f}")
    else:
        if "base_volume" in breakdown:
            lines.append(f"Base volume: ${breakdown['base_volume']:.2f}")
        if "extra_months" in breakdown:
            lines.append(f"Extra months: ${breakdown['extra_months']:.2f}")
        if "extra_users" in breakdown:
            lines.append(f"Extra users: ${breakdown['extra_users']:.2f}")
        if "total" in breakdown:
            lines.append(f"━━━━━━━━━━━━")
            lines.append(f"Total: ${breakdown['total']:.2f}")
    
    return "\n".join(lines)


def validate_pricing_constraints(
    volume_gb: int,
    duration_months: int,
    pricing: Optional[Dict]
) -> Tuple[bool, Optional[str]]:
    """Validate that user's selections meet pricing constraints.
    
    Parameters
    ----------
    volume_gb : int
        Selected volume
    duration_months : int
        Selected duration
    pricing : dict or None
        Server pricing record
        
    Returns
    -------
    tuple
        (is_valid, error_message)
    """
    if not pricing:
        return False, "No pricing configured for this server"
    
    min_months = int(pricing.get("min_months", 1))
    max_months = int(pricing.get("max_months", 6))
    
    if duration_months < min_months:
        return False, f"Minimum duration is {min_months} months"
    
    if duration_months > max_months:
        return False, f"Maximum duration is {max_months} months"
    
    if volume_gb <= 0:
        return False, "Volume must be greater than 0"
    
    if volume_gb > MAX_VOLUME_GB:
        return False, f"Volume too large (max {MAX_VOLUME_GB} GB)"
    
    return True, None


def get_pricing_for_server(conn, server_id: Optional[int]) -> Optional[Dict]:
    """Get pricing configuration for a server.
    
    Parameters
    ----------
    conn : sqlite3.Connection
        Database connection
    server_id : int or None
        Server ID, or None to get global pricing
        
    Returns
    -------
    dict or None
        Pricing record if found
    """
    try:
        cursor = conn.cursor()
        
        if server_id:
            # Try to get server-specific pricing first
            cursor.execute(
                "SELECT * FROM server_pricing WHERE server_id = ? ORDER BY updated_at DESC LIMIT 1",
                (server_id,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
        
        # Fall back to global pricing (apply_to_all = 1)
        cursor.execute(
            "SELECT * FROM server_pricing WHERE apply_to_all = 1 ORDER BY updated_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        
        return None
        
    except Exception as exc:
        LOGGER.error("failed to get pricing for server %s: %s", server_id, exc)
        return None
