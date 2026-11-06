"""Centralized Regional and Industry Classification Service for Movie Hub.

Provides deterministic, verified classification of media items across film industries,
regional cinema boundaries, and strict eligibility enforcement for AI recommendations.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple

from app.api.movie_models import MediaItemSummary, ParsedRecommendationIntent

logger = logging.getLogger(__name__)

# =============================================================================
# Regional Industry Definitions & Taxonomy
# =============================================================================

# Distinct South Indian Cinema languages (Dravidian group)
SOUTH_INDIAN_LANGUAGES: Set[str] = {"ml", "te", "ta", "kn"}

# Comprehensive Indian Cinema languages
INDIAN_LANGUAGES: Set[str] = {
    "hi",  # Hindi / Bollywood
    "te",  # Telugu / Tollywood
    "ta",  # Tamil / Kollywood
    "ml",  # Malayalam / Mollywood
    "kn",  # Kannada / Sandalwood
    "bn",  # Bengali
    "mr",  # Marathi
    "pa",  # Punjabi
    "gu",  # Gujarati
    "or",  # Odia
    "as",  # Assamese
    "ur",  # Urdu (South Asian)
}

BOLLYWOOD_LANGUAGES: Set[str] = {"hi"}
HOLLYWOOD_LANGUAGES: Set[str] = {"en"}
HOLLYWOOD_COUNTRIES: Set[str] = {"US"}
INDIAN_COUNTRIES: Set[str] = {"IN"}

# Recognized regional industries
REGION_SOUTH_INDIAN = "south_indian"
REGION_MALAYALAM = "malayalam"
REGION_TAMIL = "tamil"
REGION_TELUGU = "telugu"
REGION_KANNADA = "kannada"
REGION_BOLLYWOOD = "bollywood"
REGION_INDIAN = "indian"
REGION_HOLLYWOOD = "hollywood"
REGION_INTERNATIONAL = "international"
REGION_ANIME = "anime"
REGION_KOREAN = "korean"

# Mapping from region code to permitted original languages
REGION_TO_PERMITTED_LANGUAGES: Dict[str, Set[str]] = {
    REGION_SOUTH_INDIAN: SOUTH_INDIAN_LANGUAGES,
    REGION_MALAYALAM: {"ml"},
    REGION_TAMIL: {"ta"},
    REGION_TELUGU: {"te"},
    REGION_KANNADA: {"kn"},
    REGION_BOLLYWOOD: BOLLYWOOD_LANGUAGES,
    REGION_INDIAN: INDIAN_LANGUAGES,
    REGION_HOLLYWOOD: HOLLYWOOD_LANGUAGES,
    REGION_ANIME: {"ja"},
    REGION_KOREAN: {"ko"},
}


# =============================================================================
# Classification Engine
# =============================================================================

def classify_regional_industries(item: MediaItemSummary) -> Set[str]:
    """Classify a media item into its applicable regional industries.

    Distinguishes strictly between original language, country of origin,
    and regional film industry.
    """
    classifications: Set[str] = set()
    lang = (item.original_language or "").lower().strip()
    countries = {c.upper().strip() for c in (item.origin_country or [])}

    # 1. South Indian Cinema Classification
    if lang in SOUTH_INDIAN_LANGUAGES:
        # Non-contradicting origin country: either unspecified or includes IN
        if not countries or "IN" in countries:
            classifications.add(REGION_SOUTH_INDIAN)
            classifications.add(REGION_INDIAN)
            if lang == "ml":
                classifications.add(REGION_MALAYALAM)
            elif lang == "ta":
                classifications.add(REGION_TAMIL)
            elif lang == "te":
                classifications.add(REGION_TELUGU)
            elif lang == "kn":
                classifications.add(REGION_KANNADA)

    # 2. Bollywood / Hindi Cinema
    elif lang == "hi":
        if not countries or "IN" in countries:
            classifications.add(REGION_BOLLYWOOD)
            classifications.add(REGION_INDIAN)

    # 3. Other Indian Cinema
    elif lang in INDIAN_LANGUAGES or ("IN" in countries and lang not in HOLLYWOOD_LANGUAGES):
        classifications.add(REGION_INDIAN)

    # 4. Hollywood / US Cinema
    if lang == "en":
        # Must originate from the US to be classified as Hollywood
        if "US" in countries:
            classifications.add(REGION_HOLLYWOOD)
        elif not countries:
            # Country unknown: unconfirmed Hollywood
            pass

    # 5. International Cinema (non-English world cinema)
    if lang and lang != "en":
        classifications.add(REGION_INTERNATIONAL)

    # 6. Anime / Japanese & Korean
    if lang == "ja":
        classifications.add(REGION_ANIME)
    elif lang == "ko":
        classifications.add(REGION_KOREAN)

    return classifications


# =============================================================================
# Strict Candidate Eligibility Verification
# =============================================================================

def validate_candidate_eligibility(
    item: MediaItemSummary,
    intent: ParsedRecommendationIntent,
) -> Tuple[bool, Optional[str]]:
    """Determine whether a candidate title satisfies all mandatory user constraints.

    Mandatory rules:
    - Content type (movie vs tv)
    - Specific language requirement
    - Regional cinema industry rules
    - Era / release year boundaries

    Returns:
        (True, None) if candidate is fully eligible.
        (False, reason_string) if candidate fails any mandatory gate.
    """
    # 1. Content Type Hard Gate
    if intent.content_type in ("movie", "tv"):
        if item.media_type != intent.content_type:
            return False, f"Content type mismatch: requested {intent.content_type}, but '{item.title}' is {item.media_type}"

    # Determine if this is a similarity-driven query where language/region are soft unless explicitly requested
    is_similarity_query = bool(
        intent.reference_title
        or intent.similar_to_title
        or getattr(intent, "intent_type", "") == "similar_to"
        or getattr(intent, "request_type", "") in ("similar_to", "regional_similarity")
    )
    mand_map = getattr(intent, "mandatory_constraints", {}) or {}
    is_explicit_lang = getattr(intent, "is_explicit_language", False) or bool("language" in mand_map and getattr(intent, "is_explicit_language", False))
    is_explicit_region = getattr(intent, "is_explicit_country", False) or bool(intent.region and intent.region != REGION_INTERNATIONAL)

    # 2. Strict Language Hard Gate (Single Language - only if explicitly requested by user)
    if intent.language and is_explicit_lang:
        if not item.original_language:
            return False, f"Missing original_language: cannot verify '{intent.language}' language eligibility for '{item.title}'"
        if item.original_language != intent.language:
            return False, f"Language mismatch: requested '{intent.language}', but '{item.title}' is '{item.original_language}'"

    # 3. Regional / Permitted Languages Hard Gate (only if explicitly requested or strictly bound)
    if intent.languages and is_explicit_lang:
        if not item.original_language:
            return False, f"Missing original_language: cannot verify permitted languages eligibility for '{item.title}'"
        if item.original_language not in intent.languages:
            return False, f"Language mismatch: '{item.title}' ({item.original_language}) is not in permitted languages: {intent.languages}"

    # 4. Regional Cinema Industry Hard Gate
    if intent.region and (not is_similarity_query or is_explicit_region):
        reg = intent.region.lower().strip()
        item_lang = (item.original_language or "").lower().strip()
        countries = {c.upper().strip() for c in (item.origin_country or [])}

        if reg == REGION_SOUTH_INDIAN:
            if not item_lang:
                return False, f"Missing original_language: cannot verify South Indian regional eligibility for '{item.title}'"
            if item_lang not in SOUTH_INDIAN_LANGUAGES:
                return False, f"Regional mismatch: '{item.title}' ({item_lang}) is not South Indian (requires ml, te, ta, kn)"
            if countries and "IN" not in countries:
                return False, f"Regional mismatch: '{item.title}' origin {countries} contradicts India"

        elif reg == REGION_MALAYALAM:
            if item_lang != "ml":
                return False, f"Regional mismatch: '{item.title}' ({item_lang}) is not Malayalam ('ml')"
            if countries and "IN" not in countries:
                return False, f"Regional mismatch: '{item.title}' origin {countries} contradicts India"

        elif reg == REGION_TAMIL:
            if item_lang != "ta":
                return False, f"Regional mismatch: '{item.title}' ({item_lang}) is not Tamil ('ta')"
            if countries and "IN" not in countries:
                return False, f"Regional mismatch: '{item.title}' origin {countries} contradicts India"

        elif reg == REGION_TELUGU:
            if item_lang != "te":
                return False, f"Regional mismatch: '{item.title}' ({item_lang}) is not Telugu ('te')"
            if countries and "IN" not in countries:
                return False, f"Regional mismatch: '{item.title}' origin {countries} contradicts India"

        elif reg == REGION_KANNADA:
            if item_lang != "kn":
                return False, f"Regional mismatch: '{item.title}' ({item_lang}) is not Kannada ('kn')"
            if countries and "IN" not in countries:
                return False, f"Regional mismatch: '{item.title}' origin {countries} contradicts India"

        elif reg == REGION_BOLLYWOOD:
            if item_lang != "hi":
                return False, f"Regional mismatch: '{item.title}' ({item_lang}) is not Hindi/Bollywood ('hi')"
            if countries and "IN" not in countries:
                return False, f"Regional mismatch: '{item.title}' origin {countries} contradicts India"

        elif reg == REGION_INDIAN:
            if item_lang not in INDIAN_LANGUAGES and ("IN" not in countries):
                return False, f"Regional mismatch: '{item.title}' ({item_lang}, origin: {countries}) is not Indian cinema"

        elif reg == REGION_HOLLYWOOD:
            if item_lang != "en":
                return False, f"Regional mismatch: '{item.title}' ({item_lang}) is not Hollywood/English"
            if countries and not countries.intersection({"US", "GB", "CA", "AU"}):
                return False, f"Regional mismatch: '{item.title}' is English but origin {countries} is not Hollywood/Western"

        elif reg == REGION_INTERNATIONAL:
            # Only gate on international if the user explicitly requested foreign / non-English cinema
            requires_non_english = any(kw in (intent.keywords or []) for kw in ["foreign", "non_english", "world_cinema"])
            if requires_non_english and item_lang == "en":
                return False, f"Regional mismatch: '{item.title}' is English, but foreign/international cinema requested"

    # 5. Release Year Exact Hard Gate
    if intent.release_year:
        if item.release_year and item.release_year != intent.release_year:
            return False, f"Release year mismatch: requested {intent.release_year}, got {item.release_year}"

    # 6. Release Year Range Hard Gates
    min_year = intent.release_year_min or intent.release_year_gte
    if min_year and item.release_year:
        if item.release_year < min_year:
            return False, f"Release era mismatch: '{item.title}' ({item.release_year}) released before minimum {min_year}"

    max_year = intent.release_year_max or intent.release_year_lte
    if max_year and item.release_year:
        if item.release_year > max_year:
            return False, f"Release era mismatch: '{item.title}' ({item.release_year}) released after maximum {max_year}"

    return True, None


def filter_eligible_candidates(
    candidates: List[MediaItemSummary],
    intent: ParsedRecommendationIntent,
) -> Tuple[List[MediaItemSummary], List[Tuple[MediaItemSummary, str]]]:
    """Filter candidates strictly against mandatory intent constraints.

    Returns:
        (eligible_candidates, rejected_candidates_with_reasons)
    """
    eligible: List[MediaItemSummary] = []
    rejected: List[Tuple[MediaItemSummary, str]] = []

    for item in candidates:
        is_ok, reason = validate_candidate_eligibility(item, intent)
        if is_ok:
            eligible.append(item)
        else:
            rejected.append((item, reason or "Failed eligibility criteria"))

    return eligible, rejected

