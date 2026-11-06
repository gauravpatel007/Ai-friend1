"""Centralized Date and Time Utility for AI Friend (Buddy).

Provides robust, timezone-aware datetime resolution, formatters, and helpers.
Guarantees verified real-time temporal data without relying on model training data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
import re
from typing import Any, Dict, Optional, Union

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore
except ImportError:
    ZoneInfo = None  # type: ignore
    ZoneInfoNotFoundError = Exception  # type: ignore

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Fallback known static timezone offsets when ZoneInfo (or Windows tzdata) is unavailable
KNOWN_TIMEZONE_OFFSETS: Dict[str, timedelta] = {
    "asia/kolkata": timedelta(hours=5, minutes=30),
    "asia/calcutta": timedelta(hours=5, minutes=30),
    "ist": timedelta(hours=5, minutes=30),
    "india": timedelta(hours=5, minutes=30),
    "utc": timedelta(0),
    "gmt": timedelta(0),
    "z": timedelta(0),
    "america/new_york": timedelta(hours=-5),
    "est": timedelta(hours=-5),
    "america/los_angeles": timedelta(hours=-8),
    "pst": timedelta(hours=-8),
    "europe/london": timedelta(0),
    "asia/tokyo": timedelta(hours=9),
    "jst": timedelta(hours=9),
}


def get_local_timezone() -> tzinfo:
    """Detect and return local system timezone."""
    local_tz = datetime.now().astimezone().tzinfo
    return local_tz if local_tz is not None else timezone.utc


def get_timezone(timezone_name: Optional[str] = None) -> tzinfo:
    """Resolve a timezone name into a valid timezone object.

    Handles ZoneInfo if available, known fixed-offset fallbacks on Windows,
    and defaults safely to local system timezone upon unexpected input.

    Args:
        timezone_name: IANA timezone name (e.g. 'Asia/Kolkata', 'UTC') or alias.

    Returns:
        A valid tzinfo object.
    """
    if not timezone_name or not timezone_name.strip():
        return get_local_timezone()

    tz_clean = timezone_name.strip()
    tz_lower = tz_clean.lower()

    # Try standard library ZoneInfo first
    if ZoneInfo is not None:
        try:
            return ZoneInfo(tz_clean)
        except (ZoneInfoNotFoundError, Exception):
            pass

    # Check known fixed-offset mappings
    if tz_lower in KNOWN_TIMEZONE_OFFSETS:
        offset = KNOWN_TIMEZONE_OFFSETS[tz_lower]
        display_name = tz_clean if tz_lower not in ("india", "ist") else "Asia/Kolkata"
        return timezone(offset, name=display_name)

    logger.warning("Unrecognized or unsupported timezone '%s'. Falling back to local timezone.", timezone_name)
    return get_local_timezone()


def get_current_datetime(
    timezone_name: Optional[str] = None,
    reference_time: Optional[Union[datetime, str]] = None,
) -> Dict[str, Any]:
    """Retrieve verified temporal information for a specified timezone.

    Args:
        timezone_name: Timezone identifier (default: local detected timezone).
        reference_time: Optional fixed datetime for testing / mocked clocks.

    Returns:
        Dict containing date, time, weekday, timezone, and ISO representations.
    """
    tz = get_timezone(timezone_name)

    if reference_time is not None:
        if isinstance(reference_time, str):
            try:
                base_dt = datetime.fromisoformat(reference_time)
            except Exception:
                base_dt = datetime.now(timezone.utc)
        else:
            base_dt = reference_time

        # Ensure reference datetime is timezone-aware
        if base_dt.tzinfo is None:
            # Assume local system time if naive
            base_dt = base_dt.replace(tzinfo=get_local_timezone())
        now = base_dt.astimezone(tz)
    else:
        now = datetime.now(tz)

    tz_str = timezone_name if timezone_name else (now.tzname() or "Local")

    return {
        "date": now.strftime("%B %d, %Y"),
        "time": now.strftime("%I:%M %p"),
        "weekday": now.strftime("%A"),
        "timezone": tz_str,
        "iso_datetime": now.isoformat(),
        "day": now.day,
        "month": now.strftime("%B"),
        "year": now.year,
        "full_date": now.strftime("%A, %B %d, %Y"),
        "raw_datetime": now,
    }


def format_date_in_format(dt: datetime, format_code: Optional[str] = None) -> str:
    """Format a datetime instance according to standard or custom representations."""
    if not format_code:
        return dt.strftime("%A, %B %d, %Y")

    fmt_upper = format_code.strip().upper()
    if fmt_upper in ("DD/MM/YYYY", "DD-MM-YYYY"):
        sep = "/" if "/" in fmt_upper else "-"
        return f"{dt.day:02d}{sep}{dt.month:02d}{sep}{dt.year}"
    elif fmt_upper in ("MM/DD/YYYY", "MM-DD-YYYY"):
        sep = "/" if "/" in fmt_upper else "-"
        return f"{dt.month:02d}{sep}{dt.day:02d}{sep}{dt.year}"
    elif fmt_upper == "YYYY-MM-DD":
        return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
    elif fmt_upper == "WEEKDAY":
        return dt.strftime("%A")

    try:
        return dt.strftime(format_code)
    except Exception:
        return dt.strftime("%A, %B %d, %Y")
