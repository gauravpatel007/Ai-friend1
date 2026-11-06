"""Deterministic Safe Date and Time Intent Evaluator.

Analyzes natural language queries across English, Hindi, and Gujarati for real-time
date, time, day-of-week, and timezone inquiries. Provides deterministic, verified
responses to avoid small LLM hallucinations, outdated cutoff dates, and template placeholders.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import re
from typing import Any, Dict, Optional, Tuple, Union

from app.utils.datetime_utils import format_date_in_format, get_current_datetime
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DateTimeIntent(str, Enum):
    """Categorized date/time inquiry intents."""

    DATE = "date"
    DAY = "day"
    TIME = "time"
    DATETIME = "datetime"


# Location and Timezone detection patterns
LOCATION_TIMEZONE_PATTERNS = [
    (
        re.compile(
            r"\b(?:in\s+india|india(?:'s)?|indian|i\s+am\s+in\s+india|i['’]m\s+in\s+india|in\s+delhi|in\s+mumbai|bharat|ist)\b",
            re.IGNORECASE,
        ),
        "Asia/Kolkata",
        "India",
    ),
    (
        re.compile(r"\b(?:in\s+utc|utc|gmt|zulu)\b", re.IGNORECASE),
        "UTC",
        "UTC",
    ),
    (
        re.compile(r"\b(?:in\s+new\s+york|in\s+ny|est|eastern\s+time)\b", re.IGNORECASE),
        "America/New_York",
        "New York",
    ),
    (
        re.compile(r"\b(?:in\s+london|in\s+the\s+uk|bst)\b", re.IGNORECASE),
        "Europe/London",
        "London",
    ),
    (
        re.compile(r"\b(?:in\s+california|in\s+la|pst|pacific\s+time)\b", re.IGNORECASE),
        "America/Los_Angeles",
        "California",
    ),
    (
        re.compile(r"\b(?:in\s+tokyo|in\s+japan|jst)\b", re.IGNORECASE),
        "Asia/Tokyo",
        "Tokyo",
    ),
]

# Requested format extraction (e.g. DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD)
FORMAT_PATTERN = re.compile(
    r"\b(dd[/ -]mm[/ -]yyyy|mm[/ -]dd[/ -]yyyy|yyyy[/ -]mm[/ -]dd)\b",
    re.IGNORECASE,
)

# Prefix stripping patterns (iteratively stripped from beginning of utterance)
PREFIX_PATTERNS = [
    re.compile(r"^(?:hey\s+|ok\s+|okay\s+)?(?:buddy|friend|assistant|computer)\b\s*", re.IGNORECASE),
    re.compile(r"^(?:please|kindly)\b\s*", re.IGNORECASE),
    re.compile(r"^(?:shut\s+up(?:\s+and)?)\b\s*", re.IGNORECASE),
    re.compile(r"^(?:can\s+you|could\s+you|would\s+you|will\s+you)(?:\s+please)?\b\s*", re.IGNORECASE),
    re.compile(r"^(?:tell\s+me|give\s+me|give|show\s+me|say|share|provide|drop)\b\s*", re.IGNORECASE),
    re.compile(r"^(?:what\s+is|what['’]s|whats|which\s+is)\b\s*", re.IGNORECASE),
    re.compile(r"^(?:do\s+you\s+know|do\s+you\s+have)\b\s*", re.IGNORECASE),
    re.compile(r"^(?:the|a|an)\b\s*", re.IGNORECASE),
    re.compile(r"^(?:just)\b\s*", re.IGNORECASE),
    re.compile(r"^(?:aaj\s+ki|aaj\s+ka|aaj|આજની|આજે)\b\s*", re.IGNORECASE),
    re.compile(r"^(?:bolo|batao|kaho|કહો|બતાવો)\b\s*", re.IGNORECASE),
]

# Suffix stripping patterns (iteratively stripped from end of utterance)
SUFFIX_PATTERNS = [
    re.compile(r"\s*\b(?:please|now|right\s+now|today|buddy|batao|bolo|kaho|kya\s+hai|hai|che|છે|કહો)\b\s*$", re.IGNORECASE),
    re.compile(r"\s*[.?!,;:\'\"।]+\s*$", re.IGNORECASE),
]

# Specific Intent Matching Patterns after normalization
DATE_AND_TIME_PATTERNS = [
    re.compile(r"^(?:current\s+)?(?:date\s+and\s+time|time\s+and\s+date)$", re.IGNORECASE),
    re.compile(r"^date\s+and\s+time$", re.IGNORECASE),
    re.compile(r"^(?:તારીખ\s+અને\s+સમય|तारीख\s+और\s+समय)$", re.IGNORECASE),
]

DATE_PATTERNS = [
    re.compile(r"^(?:todays?\s+)?date(?:\s+today)?$", re.IGNORECASE),
    re.compile(r"^date$", re.IGNORECASE),
    re.compile(r"^the\s+date$", re.IGNORECASE),
    re.compile(r"^todays?\s+date$", re.IGNORECASE),
    re.compile(r"^current\s+date$", re.IGNORECASE),
    re.compile(r"^what\s+date(?:\s+is\s+it)?$", re.IGNORECASE),
    re.compile(r"^which\s+date(?:\s+is\s+it)?$", re.IGNORECASE),
    re.compile(r"^date\s+(?:is\s+it|is\s+today)$", re.IGNORECASE),
    # Hindi / Hinglish
    re.compile(r"^(?:ki\s+)?(?:date|tarikh|tareekh)(?:\s+kya\s+hai)?$", re.IGNORECASE),
    re.compile(r"^konsi\s+date(?:\s+hai)?$", re.IGNORECASE),
    re.compile(r"^kya\s+date(?:\s+hai)?$", re.IGNORECASE),
    # Gujarati
    re.compile(r"^(?:આજની\s+)?તારીખ(?:\s+શું\s+છે)?$", re.IGNORECASE),
    re.compile(r"^કઈ\s+તારીખ(?:\s+છે)?$", re.IGNORECASE),
]

DAY_PATTERNS = [
    re.compile(r"^(?:what\s+)?day(?:\s+is)?(?:\s+it)?(?:\s+today)?$", re.IGNORECASE),
    re.compile(r"^(?:what\s+)?day\s+is\s+today$", re.IGNORECASE),
    re.compile(r"^what\s+day\s+are\s+we(?:\s+today)?$", re.IGNORECASE),
    re.compile(r"^what\s+day$", re.IGNORECASE),
    re.compile(r"^which\s+day(?:\s+is\s+it)?(?:\s+today)?$", re.IGNORECASE),
    # Hindi
    re.compile(r"^(?:kaun\s+sa|kya)\s+din(?:\s+hai)?$", re.IGNORECASE),
    re.compile(r"^(?:kaun\s+sa)\s+vaar(?:\s+hai)?$", re.IGNORECASE),
    # Gujarati
    re.compile(r"^કયો\s+વાર(?:\s+છે)?$", re.IGNORECASE),
]

TIME_PATTERNS = [
    re.compile(r"^(?:what\s+)?time(?:\s+is\s+it)?(?:\s+now)?$", re.IGNORECASE),
    re.compile(r"^(?:the\s+)?current\s+time$", re.IGNORECASE),
    re.compile(r"^time$", re.IGNORECASE),
    re.compile(r"^clock$", re.IGNORECASE),
    # Hindi
    re.compile(r"^(?:kitne|kya)\s+baje(?:\s+hain?)?$", re.IGNORECASE),
    re.compile(r"^samay(?:\s+kya\s+hai)?$", re.IGNORECASE),
    # Gujarati
    re.compile(r"^કેટલા\s+વાગ્યા(?:\s+છે)?$", re.IGNORECASE),
    re.compile(r"^સમય(?:\s+શું\s+છે)?$", re.IGNORECASE),
]

# Explicit negative patterns that must NEVER be classified as current date/time queries
NEGATIVE_CONTEXT_PATTERNS = [
    re.compile(r"\b(?:went\s+on\s+a\s+date|blind\s+date|play\s+date|double\s+date|set\s+a\s+date|save\s+the\s+date)\b", re.IGNORECASE),
    re.compile(r"\b(?:how['’]?s\s+your\s+day|how\s+is\s+your\s+day|have\s+a\s+(?:nice|good|great)\s+day)\b", re.IGNORECASE),
    re.compile(r"\b(?:date\s+of\s+birth|expiration\s+date|expiry\s+date|release\s+date|due\s+date)\b", re.IGNORECASE),
    re.compile(r"\b(?:up\s+to\s+date|out\s+of\s+date|date\s+range|start\s+date|end\s+date)\b", re.IGNORECASE),
    re.compile(r"\b(?:yesterday|tomorrow|next\s+week|last\s+year|last\s+month)\b", re.IGNORECASE),
    re.compile(r"\b(?:schedule|meeting|appointment|calendar|remind\s+me)\b", re.IGNORECASE),
]


class DateTimeEvaluator:
    """Safely extracts date/time intents and formats deterministic ground-truth responses."""

    @classmethod
    def _normalize_query(cls, text: str) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
        """Normalize query by extracting timezone, location, and requested format, then stripping fillers."""
        working = text.strip()

        # 1. Extract requested date format (e.g. DD/MM/YYYY)
        fmt_match = FORMAT_PATTERN.search(working)
        format_code = fmt_match.group(1).upper() if fmt_match else None
        if fmt_match:
            working = FORMAT_PATTERN.sub(" ", working)
            working = re.sub(r"\b(?:in\s+)?format\b", " ", working, flags=re.IGNORECASE)

        # 2. Extract location / timezone
        target_tz: Optional[str] = None
        location_name: Optional[str] = None
        for loc_pat, tz_identifier, loc_label in LOCATION_TIMEZONE_PATTERNS:
            if loc_pat.search(working):
                target_tz = tz_identifier
                location_name = loc_label
                working = loc_pat.sub(" ", working)
                break

        # 3. Clean contractions and punctuation
        cleaned = re.sub(r"['’]s\b", "s", working)
        cleaned = re.sub(r"[,;:\'\"\-_/]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # 4. Iteratively strip prefixes
        changed = True
        while changed:
            changed = False
            for pat in PREFIX_PATTERNS:
                new_text = pat.sub("", cleaned).strip()
                if new_text != cleaned and new_text:
                    cleaned = new_text
                    changed = True

        # 5. Iteratively strip suffixes
        changed = True
        while changed:
            changed = False
            for pat in SUFFIX_PATTERNS:
                new_text = pat.sub("", cleaned).strip()
                if new_text != cleaned and new_text:
                    cleaned = new_text
                    changed = True

        return cleaned.lower(), target_tz, location_name, format_code

    @classmethod
    def detect_intent(
        cls,
        text: str,
    ) -> Optional[Tuple[DateTimeIntent, Optional[str], Optional[str], Optional[str]]]:
        """Detect date/time intent, target timezone, location name, and requested format.

        Returns:
            Tuple of (DateTimeIntent, timezone_name, location_name, format_code) or None.
        """
        if not text or not text.strip():
            return None

        raw = text.strip()

        # Reject negative conversational patterns
        for neg_pat in NEGATIVE_CONTEXT_PATTERNS:
            if neg_pat.search(raw):
                return None

        candidate, target_tz, location_name, format_code = cls._normalize_query(raw)

        # Reject long queries (conversational questions meant for LLM chat)
        words = candidate.split()
        if len(words) > 7:
            return None

        # Check intent pattern matches
        for pat in DATE_AND_TIME_PATTERNS:
            if pat.search(candidate):
                return DateTimeIntent.DATETIME, target_tz, location_name, format_code

        for pat in DATE_PATTERNS:
            if pat.search(candidate):
                return DateTimeIntent.DATE, target_tz, location_name, format_code

        for pat in DAY_PATTERNS:
            if pat.search(candidate):
                return DateTimeIntent.DAY, target_tz, location_name, format_code

        for pat in TIME_PATTERNS:
            if pat.search(candidate):
                return DateTimeIntent.TIME, target_tz, location_name, format_code

        return None

    @classmethod
    def extract_and_answer(
        cls,
        text: str,
        personality: str = "friendly",
        is_voice: bool = False,
        reference_time: Optional[Union[datetime, str]] = None,
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Inspect user query and return deterministic ground truth answer if date/time query.

        Args:
            text: Raw user utterance.
            personality: Companion persona key.
            is_voice: Whether interaction is in voice mode.
            reference_time: Optional fixed datetime for testing.

        Returns:
            Tuple of (formatted_answer_string, diagnostic_details_dict) or None.
        """
        match = cls.detect_intent(text)
        if match is None:
            return None

        intent, tz_name, location_name, format_code = match

        # Obtain verified real-time datetime info
        dt_info = get_current_datetime(timezone_name=tz_name, reference_time=reference_time)
        raw_dt = dt_info["raw_datetime"]
        full_date = dt_info["full_date"]  # e.g., "Wednesday, October 28, 2026"
        time_str = dt_info["time"]        # e.g., "02:45 PM"
        weekday = dt_info["weekday"]      # e.g., "Wednesday"

        if format_code:
            formatted_date = format_date_in_format(raw_dt, format_code)
        else:
            formatted_date = full_date

        # Construct clear, direct, and unambiguous factual answer
        if intent == DateTimeIntent.DATE:
            if format_code:
                if location_name:
                    answer = f"In {location_name}, today's date is {formatted_date}."
                else:
                    answer = f"Today's date is {formatted_date}."
            else:
                if location_name:
                    answer = f"Today is {full_date}, in {location_name}."
                else:
                    answer = f"Today is {full_date}."

        elif intent == DateTimeIntent.DAY:
            if location_name:
                answer = f"In {location_name}, today is {weekday}."
            else:
                answer = f"Today is {weekday}."

        elif intent == DateTimeIntent.TIME:
            if location_name:
                answer = f"In {location_name}, the current time is {time_str}."
            else:
                answer = f"The current time is {time_str}."

        elif intent == DateTimeIntent.DATETIME:
            if location_name:
                answer = f"In {location_name}, it is currently {full_date}, {time_str}."
            else:
                answer = f"It is currently {full_date}, {time_str}."
        else:
            answer = f"Today is {full_date}."

        details: Dict[str, Any] = {
            "intent": intent.value,
            "timezone": dt_info["timezone"],
            "location": location_name,
            "format": format_code,
            "datetime_info": dt_info,
            "deterministic": True,
        }

        return answer, details
