"""Ollama-Powered AI Recommendation Engine for Movie Hub.

Provides natural-language intent parsing, reference movie resolution, multi-stage
catalog retrieval from real TMDB metadata (recommendations, similar, keywords, discovery),
transparent multi-signal ranking, and grounded explanations strictly anchored in verified title metadata.
"""

from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from app.api.movie_models import (
    EditedPreferenceModel,
    MediaDetailsModel,
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
    RecommendationQueryType,
    RecommendationResponse,
    RecommendedTitleModel,
    StructuredOllamaIntent,
)
from app.ai.movie_taxonomy import (
    LANGUAGE_AND_REGION_MAP,
    MOOD_DICTIONARY,
    PLOT_ELEMENT_DICTIONARY,
    TEMPORAL_EXPRESSIONS,
    TMDB_ID_TO_GENRE,
    TMDB_KEYWORD_IDS,
    TMDB_MOVIE_GENRES,
    TMDB_TV_GENRES,
    USER_EXPRESSION_DECOMPOSITION,
    normalize_genre_name,
    resolve_keyword_ids,
    resolve_mood_semantics,
    resolve_plot_elements,
)
from app.api.tmdb_client import (
    TMDBClient,
    TMDBAuthError,
    TMDBNetworkError,
    TMDBRateLimitError,
    TMDBTimeoutError,
)
from app.ai.ollama_client import OllamaClient, OllamaClientError
from app.ai.movie_ranking_engine import MovieRankingEngine
from app.ai.movie_semantic_service import MovieSemanticService
from app.ai.movie_explanation_engine import MovieExplanationEngine
from app.memory.movie_storage_repository import MovieStorageRepository
from app.ai.regional_classifier import (
    INDIAN_LANGUAGES,
    REGION_BOLLYWOOD,
    REGION_HOLLYWOOD,
    REGION_INDIAN,
    REGION_INTERNATIONAL,
    REGION_KANNADA,
    REGION_MALAYALAM,
    REGION_SOUTH_INDIAN,
    REGION_TAMIL,
    REGION_TELUGU,
    SOUTH_INDIAN_LANGUAGES,
    classify_regional_industries,
    filter_eligible_candidates,
    validate_candidate_eligibility,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Genre Name to TMDB Genre ID mapping
GENRE_TAXONOMY: Dict[str, int] = {
    "action": 28,
    "adventure": 12,
    "animation": 16,
    "comedy": 35,
    "crime": 80,
    "documentary": 99,
    "drama": 18,
    "family": 10751,
    "fantasy": 14,
    "history": 36,
    "horror": 27,
    "music": 10402,
    "mystery": 9648,
    "romance": 10749,
    "science fiction": 878,
    "sci-fi": 878,
    "thriller": 53,
    "war": 10752,
    "western": 37,
}

GENRE_NAME_BY_ID: Dict[int, str] = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    53: "Thriller",
    10752: "War",
    37: "Western",
    10759: "Action & Adventure",
    10765: "Sci-Fi & Fantasy",
}

# Language Keyword to ISO 639-1 code
LANGUAGE_MAP: Dict[str, str] = {
    "hindi": "hi",
    "bollywood": "hi",
    "telugu": "te",
    "tollywood": "te",
    "tamil": "ta",
    "kollywood": "ta",
    "malayalam": "ml",
    "mollywood": "ml",
    "kannada": "kn",
    "sandalwood": "kn",
    "bengali": "bn",
    "marathi": "mr",
    "punjabi": "pa",
    "gujarati": "gu",
    "english": "en",
    "hollywood": "en",
    "korean": "ko",
    "japanese": "ja",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
}

# Regional mapping
REGION_KEYWORDS: Dict[str, str] = {
    "south indian": "south_indian",
    "south india": "south_indian",
    "malayalam": "malayalam",
    "mollywood": "malayalam",
    "tamil": "tamil",
    "kollywood": "tamil",
    "telugu": "telugu",
    "tollywood": "telugu",
    "kannada": "kannada",
    "sandalwood": "kannada",
    "gujarati": "gujarati",
    "bollywood": "bollywood",
    "hindi cinema": "bollywood",
    "indian": "indian",
    "india": "indian",
    "hollywood": "hollywood",
    "american": "hollywood",
    "international": "international",
    "world cinema": "international",
    "foreign": "international",
    "anime": "anime",
    "korean": "korean",
    "japanese": "japanese",
}

# Mood and Theme taxonomy
MOOD_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "mind_bending": {
        "keywords": ["mind bending", "mind-bending", "surreal", "psychological", "plot twist", "unexpected twist", "twist ending"],
        "genre_ids": [878, 9648, 53],
        "tmdb_keywords": ["plot twist", "psychological", "surreal", "mind bending", "puzzle", "alternate reality"],
    },
    "feel_good": {
        "keywords": ["feel good", "feel-good", "uplifting", "heartwarming", "wholesome", "cozy evening", "comforting"],
        "genre_ids": [35, 18, 10749, 10751],
        "tmdb_keywords": ["uplifting", "wholesome", "friendship", "optimistic", "heartwarming"],
    },
    "dark_gritty": {
        "keywords": ["dark and gritty", "dark & gritty", "gritty", "dark", "noir", "neo-noir", "grimy", "underworld"],
        "genre_ids": [80, 53, 9648],
        "tmdb_keywords": ["neo-noir", "dark", "gritty", "corruption", "underworld"],
    },
    "adrenaline": {
        "keywords": ["adrenaline", "fast-paced", "high-stakes", "explosive", "action packed", "adrenaline rush", "thrill ride"],
        "genre_ids": [28, 53, 12],
        "tmdb_keywords": ["martial arts", "chase", "combat", "revenge", "explosive"],
    },
    "spine_chilling": {
        "keywords": ["spine chilling", "spine-chilling", "scary", "terrifying", "spooky", "creepy", "haunting"],
        "genre_ids": [27, 9648, 53],
        "tmdb_keywords": ["haunting", "supernatural", "ghost", "psychological horror", "slasher"],
    },
    "cozy": {
        "keywords": ["cozy", "relaxing", "comforting", "slice of life", "peaceful", "gentle"],
        "genre_ids": [10751, 16, 35, 10749],
        "tmdb_keywords": ["family", "comforting", "friendship", "gentle"],
    },
    "survival": {
        "keywords": ["survival", "stranded", "castaway", "isolated", "wilderness survival", "disaster survival"],
        "genre_ids": [12, 18, 53],
        "tmdb_keywords": ["survival", "stranded", "wilderness", "island", "extreme conditions"],
    },
    "whodunit": {
        "keywords": ["whodunit", "who done it", "murder mystery", "detective", "sleuth", "clue", "alibi", "investigation"],
        "genre_ids": [9648, 80, 35],
        "tmdb_keywords": ["detective", "murder mystery", "whodunit", "investigation", "suspect"],
    },
    "period_drama": {
        "keywords": ["period", "period drama", "historical", "costume drama", "epic", "ancient", "dynasty"],
        "genre_ids": [36, 18, 28, 10752],
        "tmdb_keywords": ["historical", "period piece", "epic", "costume drama"],
    },
    "emotional": {
        "keywords": ["emotional", "tearjerker", "tearjerkers", "poignant", "heartbreaking", "touching", "sad"],
        "genre_ids": [18, 10749],
        "tmdb_keywords": ["tragedy", "loss of loved one", "sacrifice", "redemption"],
    },
}


def clean_reference_title_string(raw_title: str) -> Tuple[str, Optional[int]]:
    """Clean reference title string by stripping sentence noise, prefixes, and year brackets.
    
    Examples:
    - "Mystery Movies similar to Glass Onion" -> ("Glass Onion", None)
    - "Movies like Interstellar (2014)" -> ("Interstellar", 2014)
    - "Suggest films like The Prestige" -> ("The Prestige", None)
    - "Glass Onion: A Knives Out Mystery" -> ("Glass Onion: A Knives Out Mystery", None)
    """
    if not raw_title:
        return "", None

    text = raw_title.strip()

    # Extract year if present, e.g. "(2014)" or "2014"
    year_hint: Optional[int] = None
    year_match = re.search(r"\((\d{4})\)", text)
    if year_match:
        year_hint = int(year_match.group(1))
        text = text[:year_match.start()] + text[year_match.end():]
    else:
        trail_year = re.search(r"\b(19\d{2}|20\d{2})\b$", text)
        if trail_year:
            year_hint = int(trail_year.group(1))
            text = text[:trail_year.start()].strip()

    # Strip conversational and category prefixes
    noise_patterns = [
        r"^(?:suggest|recommend|find|show me|give me|what are|tell me)\s+(?:some\s+)?",
        r"^(?:south indian|indian|hollywood|bollywood|malayalam|hindi|telugu|tamil|korean|japanese|sci-fi|mystery|action|thriller|horror|comedy|drama|crime|romance)\s*(?:movies|films|series|shows|tv shows|cinema)?\s+(?:like|similar to|resembling)\s+",
        r"^(?:movies|films|series|shows|cinema)\s+(?:like|similar to|resembling)\s+",
        r"^(?:similar to|like)\s+",
    ]
    for pat in noise_patterns:
        text = re.sub(pat, "", text, flags=re.IGNORECASE).strip()

    # Strip surrounding quotes
    text = text.strip("'\"""''«»")
    return text.strip(), year_hint


class MovieRecommendationEngine:
    """Orchestrates natural language intent parsing, reference title resolution,
    multi-stage TMDB catalog candidate retrieval, transparent multi-signal ranking,
    and grounded Ollama explanations.
    """

    def __init__(
        self,
        tmdb_client: TMDBClient,
        storage_repo: MovieStorageRepository,
        ollama_client: Optional[OllamaClient] = None,
        default_model: str = "llama3.2:3b",
        ranking_engine: Optional[MovieRankingEngine] = None,
        semantic_service: Optional[MovieSemanticService] = None,
        explanation_engine: Optional[MovieExplanationEngine] = None,
    ) -> None:
        self.tmdb_client = tmdb_client
        self.storage_repo = storage_repo
        self.ollama_client = ollama_client or OllamaClient()
        self.default_model = default_model
        self.ranking_engine = ranking_engine or MovieRankingEngine()
        self.semantic_service = semantic_service or MovieSemanticService(
            ollama_client=self.ollama_client,
            storage_repo=self.storage_repo,
        )
        self.explanation_engine = explanation_engine or MovieExplanationEngine(
            ollama_client=self.ollama_client,
            default_model=self.default_model,
        )
        self._is_cancelled = False
        # In-memory cache for resolved reference titles to accelerate repeated queries
        self._reference_cache: Dict[str, MediaDetailsModel] = {}
        # In-memory cache for query recommendation responses
        self._response_cache: Dict[str, Tuple[float, RecommendationResponse]] = {}

    def cancel(self) -> None:
        """Signal ongoing recommendation generation to cancel immediately."""
        self._is_cancelled = True
        logger.info("[MovieRecommendation] Cancellation signaled.")

    # =========================================================================
    # Stage A: Natural Language Intent Parsing
    # =========================================================================

    def parse_intent_deterministic(self, query: str) -> ParsedRecommendationIntent:
        """Deterministic rule-based intent parser for movie recommendation queries."""
        q_lower = query.lower().strip()
        intent = ParsedRecommendationIntent()
        mand_map: Dict[str, Any] = {}
        opt_map: Dict[str, Any] = {}

        # 1. Content Type detection (movies vs series vs all)
        has_tv = any(w in q_lower for w in ["series", "tv show", "television", "tv series", "season", "shows", "show", "miniseries"])
        has_movie = any(w in q_lower for w in ["movie", "film", "cinema", "feature", "movies", "films", "motion picture"])

        if has_tv and has_movie:
            if any(w in q_lower for w in ["series only", "tv only", "shows only"]):
                intent.content_type = "tv"
                mand_map["content_type"] = "tv"
            elif any(w in q_lower for w in ["movies only", "movie only", "films only", "film only"]):
                intent.content_type = "movie"
                mand_map["content_type"] = "movie"
            else:
                intent.content_type = "all"
        elif has_tv:
            intent.content_type = "tv"
            mand_map["content_type"] = "tv"
        elif has_movie:
            intent.content_type = "movie"
            mand_map["content_type"] = "movie"
        else:
            intent.content_type = "all"

        # 2. Reference Movie Extraction ("similar_to" intent)
        # Patterns like: "Movies like Glass Onion", "Films similar to Interstellar", "Something like Inception"
        q_clean_for_sim = re.sub(
            r"(?i)\b(?:i\s+would\s+like|would\s+like|i'd\s+like|we\s+would\s+like|we'd\s+like|i\s+like|we\s+like|feel\s+like)\b",
            " ",
            query,
        )

        sim_pattern = (
            r"(?:movies?\s+like|films?\s+like|series\s+like|shows?\s+like|similar\s+to|"
            r"something\s+like|along\s+the\s+lines\s+of|recommend\s+.*?\blike|"
            r"in\s+the\s+vein\s+of|^like|"
            r"(?:thrillers?|comedies|comedy|dramas?|action|horrors?|mysteries|mystery|sci-fi|romance|romcoms?|adventures?|classics?)\s+like)\s+[\"']?([^\"'\n]+)[\"']?"
        )
        sim_match = re.search(sim_pattern, q_clean_for_sim, re.IGNORECASE)

        if sim_match:
            raw_cand = sim_match.group(1).strip()
            # Clean trailing modifiers from reference title
            cleaned_ref = raw_cand
            cleaned_ref = re.sub(r"(?i)\s+(?:released\s+)?(?:after|since|before|prior\s+to|between|from|in)\s+\d{4}.*$", "", cleaned_ref)
            cleaned_ref = re.sub(r"(?i)\s+\b(?:only|movies only|series only|films only)\b.*$", "", cleaned_ref)
            cleaned_ref = re.sub(r"(?i)\s+with\s+(?:plot twists|unexpected endings|good music|high ratings).*$", "", cleaned_ref)
            cleaned_ref = re.sub(r"(?i)\s+but\s+.*$", "", cleaned_ref)
            cleaned_ref = re.sub(r"(?i)\b(movies|movie|film|films|series|shows|show|tv show)\b$", "", cleaned_ref).strip(" \"',.?!")

            # Extract explicit year from title e.g. "Dune (2021)" or "Dune 2021"
            year_in_title = re.search(r"\(?(\b19\d{2}|\b20\d{2})\)?$", cleaned_ref)
            if year_in_title:
                intent.reference_year = int(year_in_title.group(1))
                cleaned_ref = re.sub(r"\(?(\b19\d{2}|\b20\d{2})\)?$", "", cleaned_ref).strip()

            genre_and_generic_words = set(GENRE_TAXONOMY.keys()) | {
                "movie", "movies", "film", "films", "series", "show", "shows", "cinema",
                "good", "great", "fun", "scary", "exciting", "entertaining", "new", "recent",
                "popular", "underrated", "best", "top", "a", "an", "the", "something", "anything"
            }
            cand_words = set(re.findall(r"\b[A-Za-z0-9]+\b", cleaned_ref.lower()))
            is_generic = bool(cand_words and cand_words.issubset(genre_and_generic_words))

            if len(cleaned_ref) >= 2 and not is_generic:
                intent.reference_title = cleaned_ref
                intent.similar_to_title = cleaned_ref
                intent.reference_titles = [cleaned_ref]
                intent.similarity_mode = "reference_title"
                intent.intent_type = "similar_to"
                intent.query_type = RecommendationQueryType.SIMILAR_TO
                intent.request_type = "similar_to"

        # 3. Regional Industry and Language detection
        detected_regions: List[str] = []
        for reg_kw, reg_id in REGION_KEYWORDS.items():
            if re.search(rf"\b{re.escape(reg_kw)}\b", q_lower):
                if reg_id not in detected_regions:
                    detected_regions.append(reg_id)

        detected_lang = None
        for lang_name, lang_code in LANGUAGE_MAP.items():
            if re.search(rf"\b{re.escape(lang_name)}\b", q_lower):
                detected_lang = lang_code
                break

        primary_region = detected_regions[0] if detected_regions else None

        if primary_region == REGION_SOUTH_INDIAN:
            intent.region = REGION_SOUTH_INDIAN
            intent.origin_country = "IN"
            intent.countries = ["IN"]
            intent.is_explicit_country = True
            mand_map["region"] = REGION_SOUTH_INDIAN
            mand_map["origin_country"] = "IN"
            if detected_lang in SOUTH_INDIAN_LANGUAGES:
                intent.language = detected_lang
                intent.languages = [detected_lang]
                intent.original_languages = [detected_lang]
                intent.required_languages = [detected_lang]
                intent.is_explicit_language = True
                mand_map["language"] = detected_lang
            else:
                intent.languages = sorted(list(SOUTH_INDIAN_LANGUAGES))
                intent.original_languages = list(intent.languages)
                intent.required_languages = []
                intent.is_explicit_language = False
            intent.intent_type = "similar_to" if intent.reference_title else "complex"
            intent.request_type = "regional_similarity" if intent.reference_title else "regional_discovery"
            intent.query_type = RecommendationQueryType.SIMILAR_TO if intent.reference_title else RecommendationQueryType.REGIONAL_DISCOVERY

        elif primary_region in (REGION_MALAYALAM, REGION_TAMIL, REGION_TELUGU, REGION_KANNADA):
            intent.region = primary_region
            intent.origin_country = "IN"
            intent.countries = ["IN"]
            intent.is_explicit_country = True
            intent.is_explicit_language = True
            mand_map["region"] = primary_region
            mand_map["origin_country"] = "IN"
            reg_lang = {
                REGION_MALAYALAM: "ml",
                REGION_TAMIL: "ta",
                REGION_TELUGU: "te",
                REGION_KANNADA: "kn",
            }[primary_region]
            intent.language = reg_lang
            intent.languages = [reg_lang]
            intent.original_languages = [reg_lang]
            intent.required_languages = [reg_lang]
            mand_map["language"] = reg_lang
            intent.intent_type = "similar_to" if intent.reference_title else "complex"
            intent.request_type = "regional_similarity" if intent.reference_title else "regional_discovery"
            intent.query_type = RecommendationQueryType.SIMILAR_TO if intent.reference_title else RecommendationQueryType.REGIONAL_DISCOVERY

        elif primary_region == "gujarati" or detected_lang == "gu":
            intent.region = "gujarati"
            intent.origin_country = "IN"
            intent.countries = ["IN"]
            intent.is_explicit_country = True
            intent.is_explicit_language = True
            mand_map["region"] = "gujarati"
            mand_map["origin_country"] = "IN"
            intent.language = "gu"
            intent.languages = ["gu"]
            intent.original_languages = ["gu"]
            intent.required_languages = ["gu"]
            mand_map["language"] = "gu"
            intent.intent_type = "similar_to" if intent.reference_title else "complex"
            intent.request_type = "regional_similarity" if intent.reference_title else "regional_discovery"
            intent.query_type = RecommendationQueryType.SIMILAR_TO if intent.reference_title else RecommendationQueryType.REGIONAL_DISCOVERY

        elif primary_region == REGION_BOLLYWOOD:
            intent.region = REGION_BOLLYWOOD
            intent.origin_country = "IN"
            intent.countries = ["IN"]
            intent.is_explicit_country = True
            intent.is_explicit_language = True
            mand_map["region"] = REGION_BOLLYWOOD
            mand_map["origin_country"] = "IN"
            intent.language = "hi"
            intent.languages = ["hi"]
            intent.original_languages = ["hi"]
            intent.required_languages = ["hi"]
            mand_map["language"] = "hi"
            intent.intent_type = "similar_to" if intent.reference_title else "complex"
            intent.request_type = "regional_similarity" if intent.reference_title else "regional_discovery"
            intent.query_type = RecommendationQueryType.SIMILAR_TO if intent.reference_title else RecommendationQueryType.REGIONAL_DISCOVERY

        elif primary_region == REGION_HOLLYWOOD:
            intent.region = REGION_HOLLYWOOD
            intent.origin_country = "US"
            intent.countries = ["US"]
            intent.is_explicit_country = True
            intent.is_explicit_language = True
            mand_map["region"] = REGION_HOLLYWOOD
            mand_map["origin_country"] = "US"
            intent.language = "en"
            intent.languages = ["en"]
            intent.original_languages = ["en"]
            intent.required_languages = ["en"]
            mand_map["language"] = "en"
            intent.intent_type = "similar_to" if intent.reference_title else "complex"
            intent.request_type = "regional_similarity" if intent.reference_title else "regional_discovery"
            intent.query_type = RecommendationQueryType.SIMILAR_TO if intent.reference_title else RecommendationQueryType.REGIONAL_DISCOVERY

        elif primary_region == REGION_INDIAN:
            intent.region = REGION_INDIAN
            intent.origin_country = "IN"
            intent.countries = ["IN"]
            intent.is_explicit_country = True
            mand_map["region"] = REGION_INDIAN
            mand_map["origin_country"] = "IN"
            if detected_lang in INDIAN_LANGUAGES:
                intent.language = detected_lang
                intent.languages = [detected_lang]
                intent.original_languages = [detected_lang]
                intent.required_languages = [detected_lang]
                intent.is_explicit_language = True
                mand_map["language"] = detected_lang
            else:
                intent.language = None
                intent.languages = sorted(list(INDIAN_LANGUAGES))
                intent.original_languages = list(intent.languages)
                intent.required_languages = []
                intent.is_explicit_language = False
            intent.intent_type = "similar_to" if intent.reference_title else "regional"
            intent.request_type = "regional_similarity" if intent.reference_title else "regional_discovery"
            intent.query_type = RecommendationQueryType.SIMILAR_TO if intent.reference_title else RecommendationQueryType.REGIONAL_DISCOVERY

        elif detected_lang:
            intent.language = detected_lang
            intent.languages = [detected_lang]
            intent.original_languages = [detected_lang]
            intent.required_languages = [detected_lang]
            intent.is_explicit_language = True
            mand_map["language"] = detected_lang
            if detected_lang in SOUTH_INDIAN_LANGUAGES:
                intent.region = REGION_SOUTH_INDIAN
                intent.origin_country = "IN"
                intent.countries = ["IN"]
                intent.is_explicit_country = True
            elif detected_lang == "hi":
                intent.region = REGION_BOLLYWOOD
                intent.origin_country = "IN"
                intent.countries = ["IN"]
                intent.is_explicit_country = True
            elif detected_lang == "en":
                intent.region = REGION_HOLLYWOOD
                intent.origin_country = "US"
                intent.countries = ["US"]
                intent.is_explicit_country = True
            elif detected_lang == "ko":
                intent.region = "korean"
                intent.origin_country = "KR"
                intent.countries = ["KR"]
                intent.is_explicit_country = True
            elif detected_lang == "ja":
                intent.region = "japanese"
                intent.origin_country = "JP"
                intent.countries = ["JP"]
                intent.is_explicit_country = True
            intent.intent_type = "similar_to" if intent.reference_title else "regional"
            intent.request_type = "regional_similarity" if intent.reference_title else "regional_discovery"
            intent.query_type = RecommendationQueryType.SIMILAR_TO if intent.reference_title else RecommendationQueryType.REGIONAL_DISCOVERY

        elif primary_region:
            intent.region = primary_region
            mand_map["region"] = primary_region
            intent.intent_type = "similar_to" if intent.reference_title else "regional"
            intent.request_type = "regional_similarity" if intent.reference_title else "regional_discovery"
            intent.query_type = RecommendationQueryType.SIMILAR_TO if intent.reference_title else RecommendationQueryType.REGIONAL_DISCOVERY

        elif intent.reference_title:
            intent.request_type = "similar_to"
            intent.intent_type = "similar_to"
            intent.query_type = RecommendationQueryType.SIMILAR_TO
            intent.origin_country = None
            intent.countries = []
            intent.language = None
            intent.languages = []
            intent.is_explicit_country = False
            intent.is_explicit_language = False

        # Check for conflicting constraints (e.g. Hollywood + Malayalam, or Hollywood + Bollywood)
        has_hollywood = "hollywood" in q_lower or intent.region == REGION_HOLLYWOOD
        has_indian = (
            intent.region in (REGION_INDIAN, REGION_BOLLYWOOD, REGION_SOUTH_INDIAN, REGION_MALAYALAM, REGION_TAMIL, REGION_TELUGU, REGION_KANNADA)
            or (intent.language in INDIAN_LANGUAGES)
            or any(w in q_lower for w in ["malayalam", "hindi", "tamil", "telugu", "kannada", "bollywood"])
        )
        if has_hollywood and has_indian:
            intent.has_conflict = True
            intent.conflict_message = "Conflicting industry constraints: 'Hollywood' and Indian/regional cinema cannot be combined."

        # 4. Release Period / Decade Detection ("time_period" intent)
        range_match = re.search(r"(?:between|from)\s+(\d{4})\s+(?:and|to)\s+(\d{4})", q_lower)
        if not range_match:
            range_match = re.search(r"\b(\d{4})\s*[-–]\s*(\d{4})\b", q_lower)
        if range_match:
            y1 = int(range_match.group(1))
            y2 = int(range_match.group(2))
            intent.release_year_gte = min(y1, y2)
            intent.release_year_lte = max(y1, y2)
            intent.release_year_min = intent.release_year_gte
            intent.release_year_max = intent.release_year_lte
            intent.release_year_from = intent.release_year_gte
            intent.release_year_to = intent.release_year_lte
            mand_map["release_year_min"] = intent.release_year_gte
            mand_map["release_year_max"] = intent.release_year_lte
            intent.intent_type = "time_period" if intent.intent_type == "general" else "complex"
            intent.query_type = RecommendationQueryType.TIME_BASED_DISCOVERY
        else:
            after_match = re.search(r"(?:released\s+)?(?:after|since|later\s+than)\s+(\d{4})", q_lower)
            if after_match:
                yr = int(after_match.group(1))
                intent.release_year_gte = yr + 1 if ("after" in after_match.group(0) or "later" in after_match.group(0)) else yr
                intent.release_year_min = intent.release_year_gte
                intent.release_year_from = intent.release_year_gte
                mand_map["release_year_min"] = intent.release_year_gte
                intent.intent_type = "time_period" if intent.intent_type == "general" else "complex"
                intent.query_type = RecommendationQueryType.TIME_BASED_DISCOVERY

            before_match = re.search(r"(?:released\s+)?(?:before|prior\s+to|earlier\s+than)\s+(\d{4})", q_lower)
            if before_match:
                yr = int(before_match.group(1))
                intent.release_year_lte = yr - 1
                intent.release_year_max = intent.release_year_lte
                intent.release_year_to = intent.release_year_lte
                mand_map["release_year_max"] = intent.release_year_lte
                intent.intent_type = "time_period" if intent.intent_type == "general" else "complex"
                intent.query_type = RecommendationQueryType.TIME_BASED_DISCOVERY

            if not intent.release_year_gte and not intent.release_year_lte:
                decade_match = re.search(r"\b(19\d0s|20\d0s|90s|80s|70s|2000s|2010s|2020s)\b", q_lower)
                if decade_match:
                    dec = decade_match.group(1).rstrip("s")
                    if dec == "90":
                        intent.release_year_gte = 1990
                        intent.release_year_lte = 1999
                    elif dec == "80":
                        intent.release_year_gte = 1980
                        intent.release_year_lte = 1989
                    elif dec == "70":
                        intent.release_year_gte = 1970
                        intent.release_year_lte = 1979
                    elif len(dec) == 4 and dec.isdigit():
                        start_year = int(dec)
                        intent.release_year_gte = start_year
                        intent.release_year_lte = start_year + 9
                    intent.release_year_min = intent.release_year_gte
                    intent.release_year_max = intent.release_year_lte
                    intent.release_year_from = intent.release_year_gte
                    intent.release_year_to = intent.release_year_lte
                    mand_map["release_year_min"] = intent.release_year_gte
                    mand_map["release_year_max"] = intent.release_year_lte
                    intent.intent_type = "time_period" if intent.intent_type == "general" else "complex"
                    intent.query_type = RecommendationQueryType.TIME_BASED_DISCOVERY

            if not intent.release_year_gte and not intent.release_year_lte:
                year_match = re.search(r"\b(19\d{2}|20\d{2})\b", q_lower)
                if year_match and not (intent.reference_title and str(year_match.group(1)) in intent.reference_title):
                    intent.release_year = int(year_match.group(1))
                    intent.release_year_min = intent.release_year
                    intent.release_year_max = intent.release_year
                    intent.release_year_from = intent.release_year
                    intent.release_year_to = intent.release_year
                    mand_map["release_year"] = intent.release_year
                    intent.intent_type = "time_period" if intent.intent_type == "general" else "complex"
                    intent.query_type = RecommendationQueryType.TIME_BASED_DISCOVERY

        # 5. Genre Extraction
        matched_genres: List[str] = []
        matched_ids: List[int] = []
        q_norm = q_lower.replace("-", " ")

        if any(k in q_norm for k in ["romantic comedy", "romantic comedies", "rom com", "romcom"]):
            if "Romance" not in matched_genres:
                matched_genres.append("Romance")
                matched_ids.append(10749)
            if "Comedy" not in matched_genres:
                matched_genres.append("Comedy")
                matched_ids.append(35)

        for g_name, g_id in GENRE_TAXONOMY.items():
            # Support plural forms: thriller/thrillers, mystery/mysteries, comedy/comedies, etc.
            if g_name.endswith("y"):
                base_stem = g_name[:-1]
                pattern = rf"\b({re.escape(g_name)}|{re.escape(base_stem)}ies)\b"
            else:
                pattern = rf"\b{re.escape(g_name)}(?:s|es)?\b"
            if re.search(pattern, q_lower) or re.search(pattern, q_norm):
                proper_name = "Science Fiction" if g_name in ("sci-fi", "sci fi", "science fiction") else g_name.title()
                if proper_name not in matched_genres:
                    matched_genres.append(proper_name)
                    matched_ids.append(g_id)

        intent.genres = list(matched_genres)
        intent.genre_ids = list(matched_ids)
        intent.is_explicit_genre = bool(matched_genres)
        intent.required_genres = list(matched_genres)
        if " or " in q_lower:
            intent.genres_any = list(matched_genres)
            intent.genres_all = []
        else:
            intent.genres_all = list(matched_genres)
            intent.genres_any = list(matched_genres)

        if matched_genres and intent.intent_type == "general":
            intent.intent_type = "genre"
            intent.query_type = RecommendationQueryType.GENRE_DISCOVERY

        # 5b. Plot Element Extraction
        detected_pe = resolve_plot_elements(query)
        if detected_pe:
            for item in detected_pe:
                for alias in item["aliases"]:
                    if alias in q_lower and alias not in intent.plot_elements:
                        intent.plot_elements.append(alias)
                for kw in item.get("tmdb_keywords", []):
                    if kw not in intent.keywords:
                        intent.keywords.append(kw)
                    if kw not in intent.keywords_any:
                        intent.keywords_any.append(kw)
                for pg in item.get("primary_genres", []):
                    if pg not in intent.genres:
                        intent.genres.append(pg)
                        gid = GENRE_TAXONOMY.get(pg.lower())
                        if gid and gid not in intent.genre_ids:
                            intent.genre_ids.append(gid)
            if not intent.reference_title and intent.query_type == RecommendationQueryType.GENERAL_DISCOVERY:
                intent.query_type = RecommendationQueryType.PLOT_BASED_DISCOVERY
                intent.intent_type = "plot_based"

        # 6. Mood and Thematic Keywords
        detected_keywords: List[str] = []
        for mood_key, mood_info in MOOD_TAXONOMY.items():
            for kw in mood_info["keywords"]:
                if re.search(rf"\b{re.escape(kw)}\b", q_lower):
                    if mood_key not in detected_keywords:
                        detected_keywords.append(mood_key)
                    intent.mood = mood_key
                    if mood_key not in intent.moods:
                        intent.moods.append(mood_key)
                    # Add associated genres if not already present
                    for gid in mood_info["genre_ids"]:
                        if gid not in intent.genre_ids:
                            intent.genre_ids.append(gid)
                            g_name = GENRE_NAME_BY_ID.get(gid)
                            if g_name and g_name not in intent.genres:
                                intent.genres.append(g_name)
                    if intent.intent_type == "general":
                        intent.intent_type = "mood"
                        intent.query_type = RecommendationQueryType.MOOD_DISCOVERY
                    break

        if "underrated" in q_lower or "hidden gem" in q_lower:
            detected_keywords.append("underrated")
            intent.sort_by = "vote_average.desc"
        elif "popular" in q_lower or "trending" in q_lower:
            detected_keywords.append("popular")
            intent.sort_by = "popularity.desc"
        elif "top rated" in q_lower or "critically acclaimed" in q_lower:
            detected_keywords.append("top_rated")
            intent.sort_by = "vote_average.desc"

        intent.keywords = detected_keywords

        # 7. Final Classification Validation
        has_explicit_genres = len(matched_genres) >= 2
        has_temporal = bool(intent.release_year or intent.release_year_min)
        has_regional = bool(intent.region or intent.language)
        has_ref = bool(intent.reference_title)
        has_mood = bool(intent.mood)
        has_plot = bool(intent.plot_elements)

        condition_count = (
            (1 if has_ref else 0)
            + (1 if has_regional else 0)
            + (1 if has_temporal else 0)
            + (1 if has_mood else 0)
            + (1 if has_explicit_genres else 0)
            + (1 if has_plot else 0)
        )
        if condition_count >= 2:
            intent.intent_type = "complex"
            if not intent.reference_title:
                intent.query_type = RecommendationQueryType.HYBRID_DISCOVERY
        elif intent.reference_title:
            intent.intent_type = "similar_to"
            intent.query_type = RecommendationQueryType.SIMILAR_TO
        elif intent.plot_elements:
            intent.intent_type = "plot_based"
            intent.query_type = RecommendationQueryType.PLOT_BASED_DISCOVERY
        elif intent.region or intent.language:
            intent.intent_type = "regional"
            intent.query_type = RecommendationQueryType.REGIONAL_DISCOVERY
        elif intent.release_year_min or intent.release_year:
            intent.intent_type = "time_period"
            intent.query_type = RecommendationQueryType.TIME_BASED_DISCOVERY
        elif intent.mood:
            intent.intent_type = "mood"
            intent.query_type = RecommendationQueryType.MOOD_DISCOVERY
        elif intent.genres:
            intent.intent_type = "genre"
            intent.query_type = RecommendationQueryType.GENRE_DISCOVERY

        intent.mandatory_constraints = mand_map
        opt_map["genres"] = intent.genres
        opt_map["genre_ids"] = intent.genre_ids
        opt_map["keywords"] = intent.keywords
        if intent.reference_title:
            opt_map["reference_title"] = intent.reference_title
        opt_map["sort_by"] = intent.sort_by
        intent.optional_preferences = opt_map

        # Build readable interpreted summary
        parts: List[str] = []
        if intent.language:
            inv_lang = {v: k.title() for k, v in LANGUAGE_MAP.items() if not k.endswith("wood")}
            parts.append(inv_lang.get(intent.language, intent.language.upper()))
        if intent.region and not intent.language:
            parts.append(intent.region.replace("_", " ").title())
        if intent.mood:
            parts.append(intent.mood.replace("_", " ").title())
        if intent.genres:
            parts.append("/".join(intent.genres))
        parts.append("Series" if intent.content_type == "tv" else ("Movies" if intent.content_type == "movie" else "Titles"))
        if intent.release_year:
            parts.append(f"({intent.release_year})")
        elif intent.release_year_min and intent.release_year_max:
            parts.append(f"({intent.release_year_min}–{intent.release_year_max})")
        elif intent.release_year_min:
            parts.append(f"(>{intent.release_year_min})")
        elif intent.release_year_max:
            parts.append(f"(<{intent.release_year_max})")
        if intent.reference_title:
            parts.append(f"similar to '{intent.reference_title}'")
        if intent.keywords:
            clean_kws = [k.replace('_', ' ') for k in intent.keywords if k != intent.mood]
            if clean_kws:
                parts.append(f"[{', '.join(clean_kws)}]")

        intent.interpreted_summary = " ".join(parts).strip()
        return intent

    def parse_intent_with_llm(self, query: str) -> ParsedRecommendationIntent:
        """Enrich intent using local Ollama model with structured JSON schema outputs, safely falling back to deterministic parser."""
        deterministic = self.parse_intent_deterministic(query)

        if not self.ollama_client.is_server_reachable():
            return deterministic

        system_prompt = (
            "You are an expert entertainment intent parser. Your task is to analyze user movie/TV requests and extract structured intent JSON.\n"
            "Do NOT invent movie titles or fake recommendations. Only extract what the user is asking for.\n"
            "Do NOT add reference_titles unless the user explicitly refers to a movie as a reference (e.g. 'Movies like Glass Onion', 'Indian movies like Premalu').\n"
            "CRITICAL LANGUAGE RULE: For similarity queries ('Movies like X', 'Indian movies like X'), do NOT guess or invent the language of the reference movie. "
            "Leave original_languages empty ([]) unless the user explicitly requested a specific language in their query (e.g. 'Malayalam movies like Premalu'). "
            "Always use standard two-letter ISO 639-1 language codes (e.g. 'ml', 'hi', 'en', 'ko'), NEVER language names like 'Telugu' or 'Hindi'.\n\n"
            "Query Types:\n"
            "- 'similar_to': User wants titles similar to a specific named film/series.\n"
            "- 'genre_discovery': User wants titles in specific genres.\n"
            "- 'mood_discovery': User wants titles matching a mood/feeling (feel-good, cozy, dark, etc.).\n"
            "- 'plot_based_discovery': User asks for specific plot concepts (time loops, plot twists, unreliable narrator, etc.).\n"
            "- 'regional_discovery': User asks for movies from a specific region/language (Malayalam, Hindi, Telugu, Korean, etc.).\n"
            "- 'time_based_discovery': User asks for titles from a specific decade or year (90s, 80s, recent, etc.).\n"
            "- 'person_based_discovery': User asks for films by an actor or director.\n"
            "- 'hybrid_discovery': Multi-constraint query combining multiple criteria.\n"
            "- 'general_discovery': Broad or unconstrained request.\n\n"
            "Examples:\n"
            "User: \"Indian movies like Premalu\"\n"
            "Output: {\"query_type\": \"similar_to\", \"genres_any\": [\"Romance\", \"Comedy\"], \"genres_all\": [], \"moods\": [\"feel-good\"], \"themes\": [\"youth\", \"relationships\"], \"plot_elements\": [], \"keywords_any\": [\"Indian cinema\", \"romantic comedy\"], \"reference_titles\": [\"Premalu\"], \"original_languages\": [], \"countries\": [\"IN\"], \"release_year_from\": null, \"release_year_to\": null, \"must_include\": [], \"must_exclude\": [], \"soft_preferences\": [\"humor\", \"charm\"], \"confidence\": 0.98}\n\n"
            "User: \"Malayalam movies like Premalu\"\n"
            "Output: {\"query_type\": \"similar_to\", \"genres_any\": [\"Romance\", \"Comedy\"], \"genres_all\": [], \"moods\": [], \"themes\": [\"youth\"], \"plot_elements\": [], \"keywords_any\": [], \"reference_titles\": [\"Premalu\"], \"original_languages\": [\"ml\"], \"countries\": [\"IN\"], \"release_year_from\": null, \"release_year_to\": null, \"must_include\": [\"Malayalam\"], \"must_exclude\": [], \"soft_preferences\": [], \"confidence\": 0.98}\n\n"
            "User: \"Korean thrillers like Forgotten\"\n"
            "Output: {\"query_type\": \"similar_to\", \"genres_any\": [\"Thriller\"], \"genres_all\": [\"Thriller\"], \"moods\": [\"tense\", \"mind-bending\"], \"themes\": [\"psychological\"], \"plot_elements\": [\"plot twists\"], \"keywords_any\": [\"mystery\"], \"reference_titles\": [\"Forgotten\"], \"original_languages\": [\"ko\"], \"countries\": [\"KR\"], \"release_year_from\": null, \"release_year_to\": null, \"must_include\": [], \"must_exclude\": [], \"soft_preferences\": [], \"confidence\": 0.98}\n\n"
            "User: \"Movies like Glass Onion\"\n"
            "Output: {\"query_type\": \"similar_to\", \"genres_any\": [\"Mystery\", \"Comedy\"], \"genres_all\": [], \"moods\": [\"witty\"], \"themes\": [\"whodunit\", \"eccentric detective\"], \"plot_elements\": [\"puzzle murder mystery\"], \"keywords_any\": [\"whodunit\", \"detective\", \"murder mystery\"], \"reference_titles\": [\"Glass Onion\"], \"original_languages\": [], \"countries\": [], \"release_year_from\": null, \"release_year_to\": null, \"must_include\": [], \"must_exclude\": [], \"soft_preferences\": [\"witty dialogue\", \"clever plot\"], \"confidence\": 0.98}\n\n"
            "User: \"Recommend a mind-bending sci-fi or psychological mystery with plot twists.\"\n"
            "Output: {\"query_type\": \"plot_based_discovery\", \"genres_any\": [\"Science Fiction\", \"Mystery\", \"Thriller\"], \"genres_all\": [], \"moods\": [\"mind-bending\"], \"themes\": [\"psychological\", \"reality distortion\"], \"plot_elements\": [\"unexpected plot twists\", \"unpredictable revelations\"], \"keywords_any\": [\"non-linear narrative\", \"unreliable narrator\", \"reality bending\"], \"reference_titles\": [], \"original_languages\": [], \"countries\": [], \"release_year_from\": null, \"release_year_to\": null, \"must_include\": [\"plot twists\"], \"must_exclude\": [], \"soft_preferences\": [\"strong storytelling\"], \"confidence\": 0.96}\n\n"
            "User: \"Underrated Malayalam thrillers\"\n"
            "Output: {\"query_type\": \"regional_discovery\", \"genres_any\": [\"Thriller\"], \"genres_all\": [\"Thriller\"], \"moods\": [\"tense\", \"suspenseful\"], \"themes\": [\"crime investigation\", \"dark mystery\"], \"plot_elements\": [], \"keywords_any\": [\"underrated\", \"hidden gems\"], \"reference_titles\": [], \"original_languages\": [\"ml\"], \"countries\": [\"IN\"], \"release_year_from\": null, \"release_year_to\": null, \"must_include\": [\"Malayalam\"], \"must_exclude\": [], \"soft_preferences\": [\"underrated\", \"critically acclaimed\"], \"confidence\": 0.95}\n\n"
            "User: \"90s Hollywood action classics\"\n"
            "Output: {\"query_type\": \"hybrid_discovery\", \"genres_any\": [\"Action\"], \"genres_all\": [\"Action\"], \"moods\": [\"adrenaline\"], \"themes\": [\"high-octane\", \"heroic stunts\"], \"plot_elements\": [], \"keywords_any\": [\"classic\", \"blockbuster\"], \"reference_titles\": [], \"original_languages\": [\"en\"], \"countries\": [\"US\"], \"release_year_from\": 1990, \"release_year_to\": 1999, \"must_include\": [], \"must_exclude\": [], \"soft_preferences\": [\"acclaimed classics\"], \"confidence\": 0.97}\n\n"
            "User: \"Movies involving time loops\"\n"
            "Output: {\"query_type\": \"plot_based_discovery\", \"genres_any\": [\"Science Fiction\", \"Mystery\"], \"genres_all\": [], \"moods\": [\"mind-bending\"], \"themes\": [\"temporal paradox\"], \"plot_elements\": [\"time loop\", \"repeating day\"], \"keywords_any\": [\"time loop\", \"repeating day\", \"temporal paradox\"], \"reference_titles\": [], \"original_languages\": [], \"countries\": [], \"release_year_from\": null, \"release_year_to\": null, \"must_include\": [\"time loop\"], \"must_exclude\": [], \"soft_preferences\": [], \"confidence\": 0.98}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        schema = StructuredOllamaIntent.model_json_schema()

        try:
            raw_response = self.ollama_client.chat(
                messages=messages,
                model=self.default_model,
                format=schema,
                options={"temperature": 0.0, "num_predict": 300},
                keep_alive="5m",
            )
            clean_str = raw_response.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_str)
            structured = StructuredOllamaIntent.model_validate(data)
            return self._normalize_and_merge_intent(deterministic, structured)
        except Exception as first_err:
            logger.warning("Structured intent validation error: %s. Attempting 1 controlled repair...", first_err)
            repair_prompt = f"The previous output failed schema validation: {first_err}. Please output valid JSON matching the requested schema."
            messages.append({"role": "user", "content": repair_prompt})
            try:
                repair_response = self.ollama_client.chat(
                    messages=messages,
                    model=self.default_model,
                    format=schema,
                    options={"temperature": 0.0, "num_predict": 300},
                    keep_alive="5m",
                )
                clean_repair = repair_response.strip().replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_repair)
                structured = StructuredOllamaIntent.model_validate(data)
                return self._normalize_and_merge_intent(deterministic, structured)
            except Exception as repair_err:
                logger.warning("Controlled repair attempt failed: %s. Falling back to deterministic parser.", repair_err)
                return deterministic

    def _normalize_and_merge_intent(
        self,
        deterministic: ParsedRecommendationIntent,
        structured: StructuredOllamaIntent,
    ) -> ParsedRecommendationIntent:
        """Merge validated structured LLM intent into deterministic intent."""
        # 1. Query type
        if structured.query_type:
            deterministic.query_type = structured.query_type
            type_map = {
                RecommendationQueryType.SIMILAR_TO: "similar_to",
                RecommendationQueryType.GENRE_DISCOVERY: "genre",
                RecommendationQueryType.MOOD_DISCOVERY: "mood",
                RecommendationQueryType.PLOT_BASED_DISCOVERY: "plot_based",
                RecommendationQueryType.REGIONAL_DISCOVERY: "regional",
                RecommendationQueryType.TIME_BASED_DISCOVERY: "time_period",
                RecommendationQueryType.PERSON_BASED_DISCOVERY: "complex",
                RecommendationQueryType.HYBRID_DISCOVERY: "complex",
                RecommendationQueryType.GENERAL_DISCOVERY: "general",
            }
            deterministic.intent_type = type_map.get(structured.query_type, "complex")

        # 2. Reference titles (only if query contains similarity trigger or deterministic reference title found)
        has_sim_word = any(
            w in (deterministic.raw_query or "").lower()
            for w in ["like", "similar to", "same as", "in the vein of", "along the lines of", "inspired by"]
        )
        if (deterministic.reference_title or (has_sim_word and structured.query_type == RecommendationQueryType.SIMILAR_TO)) and structured.reference_titles:
            ref = str(structured.reference_titles[0]).strip()
            if ref and ref.lower() not in ("null", "none", "", "undefined"):
                # If deterministic parser extracted a more complete title (e.g. "Premalu" vs "Prem"), keep deterministic
                if deterministic.reference_title and ref.lower() in deterministic.reference_title.lower() and len(ref) < len(deterministic.reference_title):
                    pass
                else:
                    deterministic.reference_title = ref
                    deterministic.similar_to_title = ref
                    deterministic.similarity_mode = "reference_title"
                    deterministic.reference_titles = list(structured.reference_titles)
        elif not deterministic.reference_title:
            deterministic.reference_title = None
            deterministic.similar_to_title = None
            deterministic.reference_titles = []

        # 3. Canonicalize Genres
        norm_genres: List[str] = []
        norm_ids: List[int] = []

        if structured.genres_any:
            deterministic.genres_any = []
            for g in structured.genres_any:
                canonical = normalize_genre_name(g) or g.title()
                if canonical not in deterministic.genres_any:
                    deterministic.genres_any.append(canonical)
                if canonical not in norm_genres:
                    norm_genres.append(canonical)
                gid = TMDB_MOVIE_GENRES.get(canonical) or GENRE_TAXONOMY.get(canonical.lower())
                if gid and gid not in norm_ids:
                    norm_ids.append(gid)

        if structured.genres_all:
            deterministic.genres_all = []
            for g in structured.genres_all:
                canonical = normalize_genre_name(g) or g.title()
                if canonical not in deterministic.genres_all:
                    deterministic.genres_all.append(canonical)
                if canonical not in norm_genres:
                    norm_genres.append(canonical)
                gid = TMDB_MOVIE_GENRES.get(canonical) or GENRE_TAXONOMY.get(canonical.lower())
                if gid and gid not in norm_ids:
                    norm_ids.append(gid)

        if norm_genres:
            for g in norm_genres:
                if g not in deterministic.genres:
                    deterministic.genres.append(g)
            for gid in norm_ids:
                if gid not in deterministic.genre_ids:
                    deterministic.genre_ids.append(gid)

        # 4. Moods & Themes
        if structured.moods:
            deterministic.moods = list(structured.moods)
            if not deterministic.mood:
                deterministic.mood = structured.moods[0].replace("-", "_")

        if structured.themes:
            deterministic.themes = list(structured.themes)

        # 5. Plot Elements
        if structured.plot_elements:
            for pe in structured.plot_elements:
                if pe not in deterministic.plot_elements:
                    deterministic.plot_elements.append(pe)
                if pe not in deterministic.keywords:
                    deterministic.keywords.append(pe)

        # 6. Keywords
        if structured.keywords_any:
            deterministic.keywords_any = list(structured.keywords_any)
            for k in structured.keywords_any:
                if k not in deterministic.keywords:
                    deterministic.keywords.append(k)

        # 7. Languages and Countries
        norm_llm_langs: List[str] = []
        if structured.original_languages:
            for l in structured.original_languages:
                l_str = str(l).lower().strip()
                iso = LANGUAGE_MAP.get(l_str) or (l_str if len(l_str) == 2 else None)
                if iso and iso not in norm_llm_langs:
                    norm_llm_langs.append(iso)

        if deterministic.is_explicit_language:
            # User explicitly requested a language (e.g. "Malayalam movies like Premalu")
            # Preserve deterministic language
            pass
        elif deterministic.region == "indian":
            # Multi-lingual Indian query e.g. "Indian movies like Premalu"
            # Rule C: Language has NO restriction unless explicitly requested!
            deterministic.language = None
            deterministic.required_languages = []
            deterministic.is_explicit_language = False
            if "language" in deterministic.mandatory_constraints:
                del deterministic.mandatory_constraints["language"]
        elif deterministic.reference_title and not deterministic.is_explicit_language:
            # Similarity query without explicit language e.g. "Movies like Premalu"
            deterministic.language = None
            deterministic.required_languages = []
            deterministic.is_explicit_language = False
            if "language" in deterministic.mandatory_constraints:
                del deterministic.mandatory_constraints["language"]
        else:
            if norm_llm_langs:
                deterministic.original_languages = list(norm_llm_langs)
                deterministic.languages = list(norm_llm_langs)
                deterministic.language = norm_llm_langs[0]
                deterministic.required_languages = list(norm_llm_langs)
                deterministic.is_explicit_language = True

        if deterministic.origin_country:
            deterministic.countries = [deterministic.origin_country]
            deterministic.mandatory_constraints["origin_country"] = deterministic.origin_country
        elif not deterministic.is_explicit_country:
            deterministic.origin_country = None
            deterministic.countries = []
            if "origin_country" in deterministic.mandatory_constraints:
                del deterministic.mandatory_constraints["origin_country"]
            if "region" in deterministic.mandatory_constraints:
                del deterministic.mandatory_constraints["region"]

        # 8. Release Year Bounds
        if structured.release_year_from is not None:
            deterministic.release_year_from = structured.release_year_from
            deterministic.release_year_gte = structured.release_year_from
            deterministic.release_year_min = structured.release_year_from
        if structured.release_year_to is not None:
            deterministic.release_year_to = structured.release_year_to
            deterministic.release_year_lte = structured.release_year_to
            deterministic.release_year_max = structured.release_year_to

        # 9. Inclusions, Exclusions, and Preferences
        if structured.must_include:
            deterministic.must_include = list(structured.must_include)
        if structured.must_exclude:
            deterministic.must_exclude = list(structured.must_exclude)
        if structured.soft_preferences:
            deterministic.soft_preferences = list(structured.soft_preferences)

        if structured.confidence is not None:
            deterministic.confidence = structured.confidence

        # Re-sync mandatory and optional constraints
        if deterministic.language and deterministic.is_explicit_language:
            deterministic.mandatory_constraints["language"] = deterministic.language
        elif "language" in deterministic.mandatory_constraints and not deterministic.is_explicit_language:
            del deterministic.mandatory_constraints["language"]

        if deterministic.origin_country and deterministic.is_explicit_country:
            deterministic.mandatory_constraints["origin_country"] = deterministic.origin_country
        elif "origin_country" in deterministic.mandatory_constraints and not deterministic.is_explicit_country:
            del deterministic.mandatory_constraints["origin_country"]

        if deterministic.region and deterministic.is_explicit_country:
            deterministic.mandatory_constraints["region"] = deterministic.region
        elif "region" in deterministic.mandatory_constraints and not deterministic.is_explicit_country:
            del deterministic.mandatory_constraints["region"]
        if deterministic.region:
            deterministic.mandatory_constraints["region"] = deterministic.region
        if deterministic.release_year_min:
            deterministic.mandatory_constraints["release_year_min"] = deterministic.release_year_min
        if deterministic.release_year_max:
            deterministic.mandatory_constraints["release_year_max"] = deterministic.release_year_max
        if deterministic.content_type != "all":
            deterministic.mandatory_constraints["content_type"] = deterministic.content_type

        deterministic.optional_preferences["genres"] = deterministic.genres
        deterministic.optional_preferences["genre_ids"] = deterministic.genre_ids
        deterministic.optional_preferences["keywords"] = deterministic.keywords
        if deterministic.plot_elements:
            deterministic.optional_preferences["plot_elements"] = deterministic.plot_elements

        return deterministic

    # =========================================================================
    # Stage B: Resolve Reference Movies
    # =========================================================================

    def resolve_reference_title(self, intent: ParsedRecommendationIntent) -> Optional[MediaDetailsModel]:
        """Resolve reference movie or TV series against TMDB verified catalog with multi-tier matching."""
        ref_raw = intent.reference_title or intent.similar_to_title
        if not ref_raw:
            return None

        # Clean noise words ("Movies like Glass Onion" -> "Glass Onion")
        ref_name, extracted_year = clean_reference_title_string(ref_raw)
        if not ref_name:
            ref_name = ref_raw.strip()

        if extracted_year and not intent.reference_year:
            intent.reference_year = extracted_year

        # Check in-memory cache first
        cache_key = f"{ref_name.lower().strip()}_{intent.reference_year or ''}"
        if cache_key in self._reference_cache:
            details = self._reference_cache[cache_key]
            self._apply_resolved_reference_metadata(intent, details)
            return details

        logger.info("[MovieRecommendation] Resolving reference title in TMDB: '%s' (cleaned: '%s', year hint: %s)", ref_raw, ref_name, intent.reference_year)

        candidates: List[MediaItemSummary] = []
        try:
            # 1. Universal search across movies and TV series first
            try:
                multi_search = self.tmdb_client.search_multi(query=ref_name, year=intent.reference_year)
                candidates.extend(multi_search.results)
            except Exception:
                pass

            # 2. Search movies directly
            if not candidates:
                try:
                    movie_search = self.tmdb_client.search_movies(query=ref_name, primary_release_year=intent.reference_year)
                    candidates.extend(movie_search.results)
                except Exception:
                    pass

            # 3. Subtitle / prefix fallback: If title contains colon or hyphen e.g. "Glass Onion: A Knives Out Mystery"
            if not candidates and (":" in ref_name or " - " in ref_name):
                simplified_name = re.split(r"[:\-]", ref_name)[0].strip()
                if len(simplified_name) >= 3:
                    logger.info("[MovieRecommendation] Trying simplified reference search: '%s'", simplified_name)
                    try:
                        sub_search = self.tmdb_client.search_movies(query=simplified_name)
                        candidates.extend(sub_search.results)
                    except Exception:
                        pass

            # 4. If still not found and ref_raw was different from ref_name, try raw string as fallback
            if not candidates and ref_raw != ref_name:
                try:
                    raw_search = self.tmdb_client.search_movies(query=ref_raw)
                    candidates.extend(raw_search.results)
                except Exception:
                    pass

            if not candidates:
                logger.warning("[MovieRecommendation] No TMDB record found for reference title: '%s'", ref_name)
                return None

            # Prioritize matching content type if explicitly requested
            target_type = intent.content_type if intent.content_type in ("movie", "tv") else None
            filtered_candidates = [r for r in candidates if not target_type or r.media_type == target_type] or candidates

            # Candidate scoring to pick the best match
            ref_clean = re.sub(r"[^\w\s]", "", ref_name.lower()).strip()
            best_match: Optional[MediaItemSummary] = None
            best_score = -1.0

            for cand in filtered_candidates:
                score = 0.0
                cand_title_clean = re.sub(r"[^\w\s]", "", (cand.title or "").lower()).strip()
                cand_orig_clean = re.sub(r"[^\w\s]", "", (cand.original_title or "").lower()).strip()

                if cand_title_clean == ref_clean or cand_orig_clean == ref_clean:
                    score += 100.0
                elif cand_title_clean.startswith(ref_clean) or ref_clean.startswith(cand_title_clean):
                    score += 70.0
                elif any(word in cand_title_clean for word in ref_clean.split()):
                    score += 40.0

                if intent.reference_year and cand.release_year == intent.reference_year:
                    score += 30.0

                # Popularity signal as tie-breaker
                score += math.log1p(cand.popularity or 0.0) * 2.0

                if score > best_score:
                    best_score = score
                    best_match = cand

            if not best_match or best_score < 35.0:
                logger.warning("[MovieRecommendation] No good title match found for reference '%s'", ref_name)
                return None

            # Fetch rich details including cast, directors, and genres
            if best_match.media_type == "tv":
                details = self.tmdb_client.get_series_details(best_match.id)
            else:
                details = self.tmdb_client.get_movie_details(best_match.id)

            self._apply_resolved_reference_metadata(intent, details)

            # Cache the resolved reference
            self._reference_cache[cache_key] = details
            self._reference_cache[details.title.lower().strip()] = details

            logger.info(
                "[MovieRecommendation] Resolved reference '%s' -> '%s' (ID: %d, Type: %s, Year: %s, Genres: %s, Lang: %s, Countries: %s)",
                ref_name,
                details.title,
                details.id,
                details.media_type,
                details.release_year,
                [g.name for g in getattr(details, "genres", [])],
                details.original_language,
                details.origin_country,
            )
            return details
        except Exception as e:
            logger.error("[MovieRecommendation] Error resolving reference title '%s': %s", ref_name, e)
            return None

    def _apply_resolved_reference_metadata(self, intent: ParsedRecommendationIntent, details: MediaDetailsModel) -> None:
        """Ground intent with verified TMDB metadata for reference title (Phase 1 Rules C & D)."""
        ref_genres = [g.name for g in (details.genres or [])]
        ref_lang = details.original_language or "en"
        ref_countries = details.origin_country or []

        lang_names = {
            "ml": "Malayalam", "hi": "Hindi", "te": "Telugu", "ta": "Tamil",
            "kn": "Kannada", "bn": "Bengali", "en": "English", "ko": "Korean",
            "ja": "Japanese", "es": "Spanish", "fr": "French", "de": "German",
        }
        ref_lang_name = lang_names.get(ref_lang, ref_lang.upper())

        intent.reference_media = details
        intent.reference_title = details.title
        intent.similar_to_title = details.title
        intent.reference_year = details.release_year
        if details.genres:
            intent.reference_genres = [g.id for g in details.genres]

        intent.reference_characteristics = {
            "tmdb_id": details.id,
            "title": details.title,
            "original_title": details.original_title or details.title,
            "original_language": ref_lang,
            "language_name": ref_lang_name,
            "origin_country": ref_countries,
            "release_year": details.release_year,
            "genres": ref_genres,
            "verified": True,
        }

        # Rule C: Inherit genres from verified reference metadata as preferred_genres (if not explicitly requested by user)
        if details.genres:
            if not intent.is_explicit_genre or not intent.required_genres:
                intent.preferred_genres = list(ref_genres)
                if not intent.genres:
                    intent.genres = list(ref_genres)
                if not intent.genre_ids:
                    intent.genre_ids = list(intent.reference_genres)

        # Rule C & D: Enforce verified language behavior
        if not intent.is_explicit_language:
            # User did NOT explicitly ask for a specific language -> NO hard language restriction
            intent.language = None
            intent.required_languages = []
            if "language" in intent.mandatory_constraints:
                del intent.mandatory_constraints["language"]
            # Store verified language as soft preference for ranking
            if ref_lang and ref_lang not in intent.preferred_languages:
                intent.preferred_languages = [ref_lang]
        else:
            # User explicitly requested a language (e.g. "Malayalam movies like Premalu")
            if intent.language:
                intent.mandatory_constraints["language"] = intent.language
                intent.required_languages = [intent.language]

        # Rule C: Enforce verified country behavior
        if not intent.is_explicit_country:
            # Pure similarity -> No mandatory country restriction
            intent.origin_country = None
            intent.countries = []
            if "region" in intent.mandatory_constraints:
                del intent.mandatory_constraints["region"]
            if "origin_country" in intent.mandatory_constraints:
                del intent.mandatory_constraints["origin_country"]
        else:
            if intent.origin_country:
                intent.mandatory_constraints["origin_country"] = intent.origin_country

    # =========================================================================
    # Stage C & D: Multi-Stage Candidate Retrieval & Fallback Pipeline
    # =========================================================================

    def _record_tmdb_error(self, e: Exception, diagnostic_info: Dict[str, Any]) -> None:
        """Capture specific TMDB failure modes into diagnostic payload."""
        if isinstance(e, TMDBRateLimitError):
            diagnostic_info["error_type"] = "rate_limit_exceeded"
            diagnostic_info["error_message"] = "TMDB rate limit reached. Please wait a moment before trying again."
        elif isinstance(e, TMDBTimeoutError):
            diagnostic_info["error_type"] = "network_timeout"
            diagnostic_info["error_message"] = f"TMDB request timed out: {e}"
        elif isinstance(e, TMDBNetworkError):
            diagnostic_info["error_type"] = "network_error"
            diagnostic_info["error_message"] = f"Network error communicating with TMDB: {e}"
        elif isinstance(e, TMDBAuthError):
            diagnostic_info["error_type"] = "tmdb_auth_error"
            diagnostic_info["error_message"] = "TMDB authentication failed. Please verify your TMDB API key in Settings."
        else:
            diagnostic_info["error_type"] = "tmdb_error"
            diagnostic_info["error_message"] = str(e)

    def retrieve_candidates(
        self,
        intent: ParsedRecommendationIntent,
        limit: int = 36,
        return_diagnostics: bool = False,
    ) -> List[MediaItemSummary] | Tuple[List[MediaItemSummary], Dict[str, Any]]:
        """Multi-source candidate retrieval pipeline combining recommendations, similar titles,
        keyword discovery, and parameterized discovery with progressive fallbacks.
        """
        if self._is_cancelled:
            raise RuntimeError("Recommendation cancelled by user")

        candidates: List[MediaItemSummary] = []
        seen_ids: Set[int] = set()
        diagnostic_info: Dict[str, Any] = {
            "retrieval_tiers_used": [],
            "counts_per_tier": {},
        }

        # Phase 2 Rules A, B, C, D: Multi-source, country-aware, paginated retrieval
        if intent.reference_title or intent.query_type == RecommendationQueryType.SIMILAR_TO:
            target_candidates = max(limit * 5, 40)  # Aim for 40-60 candidates for similarity
        elif (
            intent.query_type in (RecommendationQueryType.HYBRID_DISCOVERY, RecommendationQueryType.PLOT_BASED_DISCOVERY)
            or intent.intent_type == "complex"
        ):
            target_candidates = max(limit * 6, 45)
        else:
            target_candidates = max(limit * 4, 30)

        # Exclude reference movie itself from recommendations
        ref_id: Optional[int] = None
        if intent.reference_media:
            ref_id = intent.reference_media.id
            seen_ids.add(ref_id)

        eligible_count = 0

        def add_candidate(cand: MediaItemSummary, source: str, ref_movie_id: Optional[int] = None) -> bool:
            """Helper to tag provenance metadata, deduplicate strictly by TMDB ID, and track eligibility."""
            nonlocal eligible_count
            if not cand or cand.id in seen_ids:
                return False
            if ref_id and cand.id == ref_id:
                return False

            # Tag provenance metadata (Requirement 3.6)
            cand.retrieval_source = source
            if ref_movie_id:
                cand.reference_movie_id = ref_movie_id

            seen_ids.add(cand.id)
            candidates.append(cand)

            is_ok, _ = validate_candidate_eligibility(cand, intent)
            if is_ok:
                eligible_count += 1
                return True
            return False

        # Phase 2 Rule B: Country-Aware Discovery
        # Establish origin_country and target_lang early
        origin_country: Optional[str] = intent.origin_country or None
        if not origin_country:
            if intent.region in ("indian", "bollywood", "south_indian", "malayalam", "tamil", "telugu"):
                origin_country = "IN"
            elif intent.region == "hollywood":
                origin_country = "US"
            elif intent.region == "korean":
                origin_country = "KR"

        # Do NOT confuse language with production country!
        # Indian cinema includes ml, hi, ta, te, kn, bn etc.
        # target_lang is ONLY set if user explicitly requested that language.
        target_lang: Optional[str] = None
        if intent.language and intent.is_explicit_language:
            target_lang = intent.language
        elif intent.region == "south_indian" and not intent.is_explicit_language:
            target_lang = "ml|te|ta|kn"
        elif not origin_country and intent.language and intent.is_explicit_language:
            target_lang = intent.language

        date_gte = f"{intent.release_year_min or intent.release_year_gte}-01-01" if (intent.release_year_min or intent.release_year_gte) else None
        date_lte = f"{intent.release_year_max or intent.release_year_lte}-12-31" if (intent.release_year_max or intent.release_year_lte) else None
        vote_count_gte = 30 if "underrated" in intent.keywords else (10 if intent.region else 20)

        # =====================================================================
        # REFERENCE MOVIE PIPELINE (Phase 2 Rule A & C)
        # =====================================================================
        if self._is_cancelled:
            raise RuntimeError("Recommendation cancelled by user")
        if intent.reference_title or intent.similar_to_title:
            if not intent.reference_media:
                self.resolve_reference_title(intent)
                if intent.reference_media:
                    ref_id = intent.reference_media.id
                    seen_ids.add(ref_id)

            if intent.reference_media:
                media_id = intent.reference_media.id
                is_tv = intent.reference_media.media_type == "tv"

                # If reference_media already contains similar titles from details, include them
                if getattr(intent.reference_media, "similar", None):
                    for sim_item in intent.reference_media.similar:
                        add_candidate(sim_item, source="details_similar", ref_movie_id=media_id)

                # 1. Movie Search: /search/movie for reference directors or related works (Req A.1)
                try:
                    directors = getattr(intent.reference_media, "directors", []) or []
                    for director in directors[:2]:
                        dir_paged = self.tmdb_client.search_movies(query=director, page=1)
                        count_dir = 0
                        for item in (dir_paged.results if dir_paged else []):
                            if add_candidate(item, source="movie_search_director", ref_movie_id=media_id):
                                count_dir += 1
                        if count_dir > 0:
                            diagnostic_info["retrieval_tiers_used"].append("movie_search_director")
                            diagnostic_info["counts_per_tier"]["movie_search_director"] = count_dir
                            logger.info("[MovieRecommendation] Source 1 (/search/movie for '%s'): found %d eligible titles", director, count_dir)
                except Exception as e:
                    self._record_tmdb_error(e, diagnostic_info)
                    logger.debug("[MovieRecommendation] Source 1 (/search/movie) error: %s", e)

                # 2. Recommended Movies: /movie/{id}/recommendations (Req A.3)
                try:
                    recs_paged = (
                        self.tmdb_client.get_series_recommendations(media_id, page=1)
                        if is_tv
                        else self.tmdb_client.get_movie_recommendations(media_id, page=1)
                    )
                    count_rec = 0
                    for item in recs_paged.results:
                        if add_candidate(item, source="tmdb_recommendations", ref_movie_id=media_id):
                            count_rec += 1
                    diagnostic_info["retrieval_tiers_used"].append("tmdb_curated_recommendations")
                    diagnostic_info["counts_per_tier"]["tmdb_curated_recommendations"] = count_rec
                    logger.info("[MovieRecommendation] Source 2 (TMDB recommendations): found %d eligible titles", count_rec)

                    # Pagination: Page 2 if needed (Req D)
                    if eligible_count < target_candidates and recs_paged.total_pages > 1:
                        recs_paged_2 = (
                            self.tmdb_client.get_series_recommendations(media_id, page=2)
                            if is_tv
                            else self.tmdb_client.get_movie_recommendations(media_id, page=2)
                        )
                        count_rec_2 = 0
                        for item in recs_paged_2.results:
                            if add_candidate(item, source="tmdb_recommendations_p2", ref_movie_id=media_id):
                                count_rec_2 += 1
                        if count_rec_2 > 0:
                            logger.info("[MovieRecommendation] TMDB recommendations (page 2): found %d eligible titles", count_rec_2)
                except Exception as e:
                    self._record_tmdb_error(e, diagnostic_info)
                    logger.warning("[MovieRecommendation] Source 2 error: %s", e)

                # 3. Similar Movies: /movie/{id}/similar (Req A.2)
                try:
                    sim_paged = (
                        self.tmdb_client.get_series_similar(media_id, page=1)
                        if is_tv
                        else self.tmdb_client.get_movie_similar(media_id, page=1)
                    )
                    count_sim = 0
                    for item in sim_paged.results:
                        if add_candidate(item, source="tmdb_similar", ref_movie_id=media_id):
                            count_sim += 1
                    diagnostic_info["retrieval_tiers_used"].append("tmdb_similar")
                    diagnostic_info["counts_per_tier"]["tmdb_similar"] = count_sim
                    logger.info("[MovieRecommendation] Source 3 (Similar titles): found %d eligible titles", count_sim)

                    # Pagination: Page 2 if needed (Req D)
                    if eligible_count < target_candidates and sim_paged.total_pages > 1:
                        sim_paged_2 = (
                            self.tmdb_client.get_series_similar(media_id, page=2)
                            if is_tv
                            else self.tmdb_client.get_movie_similar(media_id, page=2)
                        )
                        count_sim_2 = 0
                        for item in sim_paged_2.results:
                            if add_candidate(item, source="tmdb_similar_p2", ref_movie_id=media_id):
                                count_sim_2 += 1
                        if count_sim_2 > 0:
                            logger.info("[MovieRecommendation] TMDB similar (page 2): found %d eligible titles", count_sim_2)
                except Exception as e:
                    self._record_tmdb_error(e, diagnostic_info)
                    logger.warning("[MovieRecommendation] Source 3 error: %s", e)

                # 4. Discover Movies: Reference Thematic Keywords with Country Filtering (Req A.4, B & C)
                try:
                    raw_keywords = (
                        self.tmdb_client.get_series_keywords(media_id)
                        if is_tv
                        else self.tmdb_client.get_movie_keywords(media_id)
                    )
                    ref_kw_ids = [str(k["id"]) for k in raw_keywords if "id" in k][:5]
                    if ref_kw_ids:
                        kw_pipe_str = "|".join(ref_kw_ids)
                        kw_paged = (
                            self.tmdb_client.discover_series(
                                with_keywords=kw_pipe_str,
                                with_origin_country=origin_country,
                                with_original_language=target_lang,
                                sort_by="popularity.desc",
                                page=1,
                            )
                            if is_tv
                            else self.tmdb_client.discover_movies(
                                with_keywords=kw_pipe_str,
                                with_origin_country=origin_country,
                                with_original_language=target_lang,
                                sort_by="popularity.desc",
                                page=1,
                            )
                        )
                        count_ref_kw = 0
                        for item in kw_paged.results:
                            if add_candidate(item, source="keyword_discover", ref_movie_id=media_id):
                                count_ref_kw += 1
                        diagnostic_info["retrieval_tiers_used"].append("reference_keyword_discovery")
                        diagnostic_info["counts_per_tier"]["reference_keyword_discovery"] = count_ref_kw
                        logger.info("[MovieRecommendation] Reference keywords (country-aware): found %d eligible titles", count_ref_kw)

                        # Pagination: Page 2 if needed (Req D)
                        if eligible_count < target_candidates and kw_paged.total_pages > 1:
                            kw_paged_2 = (
                                self.tmdb_client.discover_series(
                                    with_keywords=kw_pipe_str,
                                    with_origin_country=origin_country,
                                    with_original_language=target_lang,
                                    sort_by="popularity.desc",
                                    page=2,
                                )
                                if is_tv
                                else self.tmdb_client.discover_movies(
                                    with_keywords=kw_pipe_str,
                                    with_origin_country=origin_country,
                                    with_original_language=target_lang,
                                    sort_by="popularity.desc",
                                    page=2,
                                )
                            )
                            for item in kw_paged_2.results:
                                add_candidate(item, source="keyword_discover_p2", ref_movie_id=media_id)
                except Exception as e:
                    self._record_tmdb_error(e, diagnostic_info)
                    logger.warning("[MovieRecommendation] Reference keywords error: %s", e)

                # 5. Discover Movies: Reference Genres Combination with Country Filtering (Req A.4, B & C)
                # For Premalu: Romance [10749] and Comedy [35]
                ref_genres = getattr(intent.reference_media, "genre_ids", []) or getattr(intent, "reference_genres", []) or []
                if not ref_genres and intent.preferred_genres:
                    ref_genres = [TMDB_MOVIE_GENRES[g] for g in intent.preferred_genres if g in TMDB_MOVIE_GENRES]

                if ref_genres and eligible_count < target_candidates:
                    try:
                        # First: Conjunction (AND) for reference genres (e.g. Romance AND Comedy)
                        if len(ref_genres) >= 2:
                            genre_and_str = ",".join(str(gid) for gid in ref_genres[:3])
                            and_paged = (
                                self.tmdb_client.discover_series(
                                    with_genres=genre_and_str,
                                    with_origin_country=origin_country,
                                    with_original_language=target_lang,
                                    sort_by="popularity.desc",
                                    page=1,
                                )
                                if is_tv
                                else self.tmdb_client.discover_movies(
                                    with_genres=genre_and_str,
                                    with_origin_country=origin_country,
                                    with_original_language=target_lang,
                                    sort_by="popularity.desc",
                                    page=1,
                                )
                            )
                            count_and = 0
                            for item in (and_paged.results if and_paged else []):
                                if add_candidate(item, source="reference_genre_combo", ref_movie_id=media_id):
                                    count_and += 1
                            if count_and > 0:
                                diagnostic_info["retrieval_tiers_used"].append("reference_genre_combo")
                                diagnostic_info["counts_per_tier"]["reference_genre_combo"] = count_and
                                logger.info("[MovieRecommendation] Reference genre combo (AND): found %d eligible titles", count_and)

                            # Pagination: Page 2 of AND combo if needed
                            if eligible_count < target_candidates and and_paged.total_pages > 1:
                                and_paged_2 = (
                                    self.tmdb_client.discover_series(
                                        with_genres=genre_and_str,
                                        with_origin_country=origin_country,
                                        with_original_language=target_lang,
                                        sort_by="popularity.desc",
                                        page=2,
                                    )
                                    if is_tv
                                    else self.tmdb_client.discover_movies(
                                        with_genres=genre_and_str,
                                        with_origin_country=origin_country,
                                        with_original_language=target_lang,
                                        sort_by="popularity.desc",
                                        page=2,
                                    )
                                )
                                for item in (and_paged_2.results if and_paged_2 else []):
                                    add_candidate(item, source="reference_genre_combo_p2", ref_movie_id=media_id)

                        # Second: Disjunction (OR) for reference genres (e.g. Romance OR Comedy)
                        if eligible_count < target_candidates:
                            genre_or_str = "|".join(str(gid) for gid in ref_genres)
                            or_paged = (
                                self.tmdb_client.discover_series(
                                    with_genres=genre_or_str,
                                    with_origin_country=origin_country,
                                    with_original_language=target_lang,
                                    sort_by="popularity.desc",
                                    page=1,
                                )
                                if is_tv
                                else self.tmdb_client.discover_movies(
                                    with_genres=genre_or_str,
                                    with_origin_country=origin_country,
                                    with_original_language=target_lang,
                                    sort_by="popularity.desc",
                                    page=1,
                                )
                            )
                            count_or = 0
                            for item in (or_paged.results if or_paged else []):
                                if add_candidate(item, source="reference_genre_or", ref_movie_id=media_id):
                                    count_or += 1
                            if count_or > 0:
                                diagnostic_info["retrieval_tiers_used"].append("reference_genre_or")
                                diagnostic_info["counts_per_tier"]["reference_genre_or"] = count_or
                                logger.info("[MovieRecommendation] Reference genre (OR): found %d eligible titles", count_or)
                    except Exception as e:
                        self._record_tmdb_error(e, diagnostic_info)
                        logger.warning("[MovieRecommendation] Reference genre discover error: %s", e)

        # =====================================================================
        # DEDICATED REGIONAL COUNTRY DISCOVERY (Phase 2 Rule B & C)
        # =====================================================================
        if origin_country == "IN" and eligible_count < target_candidates:
            try:
                ref_genres_for_in = intent.genre_ids or (
                    [TMDB_MOVIE_GENRES[g] for g in intent.preferred_genres if g in TMDB_MOVIE_GENRES]
                    if intent.preferred_genres else None
                )
                in_genre_str = "|".join(str(gid) for gid in ref_genres_for_in) if ref_genres_for_in else None
                indian_paged = (
                    self.tmdb_client.discover_movies(
                        with_origin_country="IN",
                        with_original_language=target_lang,
                        with_genres=in_genre_str,
                        sort_by="popularity.desc",
                        page=1,
                    )
                    if intent.content_type == "movie"
                    else self.tmdb_client.discover_all(
                        with_origin_country="IN",
                        with_original_language=target_lang,
                        with_genres=in_genre_str,
                        sort_by="popularity.desc",
                        page=1,
                    )
                )
                count_in = 0
                for item in (indian_paged.results if indian_paged else []):
                    if add_candidate(item, source="indian_movie_discover"):
                        count_in += 1
                if count_in > 0:
                    diagnostic_info["retrieval_tiers_used"].append("indian_movie_discovery")
                    diagnostic_info["counts_per_tier"]["indian_movie_discovery"] = count_in
                    logger.info("[MovieRecommendation] Dedicated Indian discovery: found %d eligible titles", count_in)

                # Pagination: Page 2 if needed
                if eligible_count < target_candidates and indian_paged.total_pages > 1:
                    indian_paged_2 = (
                        self.tmdb_client.discover_movies(
                            with_origin_country="IN",
                            with_original_language=target_lang,
                            with_genres=in_genre_str,
                            sort_by="popularity.desc",
                            page=2,
                        )
                        if intent.content_type == "movie"
                        else self.tmdb_client.discover_all(
                            with_origin_country="IN",
                            with_original_language=target_lang,
                            with_genres=in_genre_str,
                            sort_by="popularity.desc",
                            page=2,
                        )
                    )
                    for item in (indian_paged_2.results if indian_paged_2 else []):
                        add_candidate(item, source="indian_movie_discover_p2")
            except Exception as e:
                self._record_tmdb_error(e, diagnostic_info)
                logger.debug("[MovieRecommendation] Dedicated Indian discovery error: %s", e)

        # =====================================================================
        # SOURCE 3: Keyword-Based Discovery (Plot Elements & Tropes)
        # =====================================================================
        if self._is_cancelled:
            raise RuntimeError("Recommendation cancelled by user")
        kw_sources = list(intent.keywords_any)
        for pe in intent.plot_elements:
            if pe not in kw_sources:
                kw_sources.append(pe)
        for kw in intent.keywords:
            if kw not in kw_sources:
                kw_sources.append(kw)

        resolved_kw_ids = resolve_keyword_ids(kw_sources, tmdb_client=self.tmdb_client)

        if resolved_kw_ids and eligible_count < target_candidates:
            # 3.5 Use OR matching for keywords: '|' pipe
            kw_pipe_str = "|".join(str(kid) for kid in resolved_kw_ids)
            try:
                if intent.content_type == "movie":
                    kw_paged = self.tmdb_client.discover_movies(
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_keywords=kw_pipe_str,
                        sort_by=intent.sort_by,
                        primary_release_year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=vote_count_gte,
                        page=1,
                    )
                elif intent.content_type == "tv":
                    kw_paged = self.tmdb_client.discover_series(
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_keywords=kw_pipe_str,
                        sort_by=intent.sort_by,
                        first_air_date_year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=vote_count_gte,
                        page=1,
                    )
                else:
                    kw_paged = self.tmdb_client.discover_all(
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_keywords=kw_pipe_str,
                        sort_by=intent.sort_by,
                        year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=vote_count_gte,
                        page=1,
                    )
                count_kw = 0
                for item in (kw_paged.results if kw_paged else []):
                    if add_candidate(item, source="keyword_discover"):
                        count_kw += 1
                diagnostic_info["retrieval_tiers_used"].append("keyword_discovery")
                diagnostic_info["counts_per_tier"]["keyword_discovery"] = count_kw
                logger.info("[MovieRecommendation] Source 3 (Keyword discovery): found %d eligible titles", count_kw)
            except Exception as e:
                self._record_tmdb_error(e, diagnostic_info)
                logger.warning("[MovieRecommendation] Source 3 error: %s", e)

        # =====================================================================
        # SOURCE 4: Parameterized Genre Discovery (/discover/movie & /discover/tv)
        # =====================================================================
        if self._is_cancelled:
            raise RuntimeError("Recommendation cancelled by user")
        if eligible_count < target_candidates:
            # 3.4 Resolve genre IDs: use OR '|' if genres_any, use AND ',' if genres_all
            genre_filter_str: Optional[str] = None
            if intent.genres_any:
                any_ids = [
                    TMDB_MOVIE_GENRES.get(g) or GENRE_TAXONOMY.get(g.lower())
                    for g in intent.genres_any
                    if TMDB_MOVIE_GENRES.get(g) or GENRE_TAXONOMY.get(g.lower())
                ]
                if any_ids:
                    genre_filter_str = "|".join(str(gid) for gid in any_ids)
            elif intent.genres_all and len(intent.genres_all) > 1:
                all_ids = [
                    TMDB_MOVIE_GENRES.get(g) or GENRE_TAXONOMY.get(g.lower())
                    for g in intent.genres_all
                    if TMDB_MOVIE_GENRES.get(g) or GENRE_TAXONOMY.get(g.lower())
                ]
                if all_ids:
                    genre_filter_str = ",".join(str(gid) for gid in all_ids)
            elif intent.genre_ids:
                genre_filter_str = "|".join(str(gid) for gid in intent.genre_ids)
            elif intent.preferred_genres:
                pref_ids = [
                    TMDB_MOVIE_GENRES.get(g) or GENRE_TAXONOMY.get(g.lower())
                    for g in intent.preferred_genres
                    if TMDB_MOVIE_GENRES.get(g) or GENRE_TAXONOMY.get(g.lower())
                ]
                if pref_ids:
                    genre_filter_str = "|".join(str(gid) for gid in pref_ids)

            try:
                paged: Optional[PagedResultModel] = None
                if intent.content_type == "movie":
                    paged = self.tmdb_client.discover_movies(
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_genres=genre_filter_str,
                        sort_by=intent.sort_by,
                        primary_release_year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=vote_count_gte,
                        page=1,
                    )
                elif intent.content_type == "tv":
                    paged = self.tmdb_client.discover_series(
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_genres=genre_filter_str,
                        sort_by=intent.sort_by,
                        first_air_date_year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=vote_count_gte,
                        page=1,
                    )
                else:
                    paged = self.tmdb_client.discover_all(
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_genres=genre_filter_str,
                        sort_by=intent.sort_by,
                        year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=vote_count_gte,
                        page=1,
                    )

                count_b = 0
                for item in (paged.results if paged else []):
                    if add_candidate(item, source="genre_discover"):
                        count_b += 1
                diagnostic_info["retrieval_tiers_used"].append("parameterized_discovery")
                diagnostic_info["counts_per_tier"]["parameterized_discovery"] = count_b
                logger.info("[MovieRecommendation] Source 4 (Genre discovery): found %d eligible titles", count_b)
            except Exception as e:
                self._record_tmdb_error(e, diagnostic_info)
                logger.error("[MovieRecommendation] Source 4 error: %s", e)

        # =====================================================================
        # 3.7 Progressive Fallback Retrieval
        # =====================================================================
        # If candidate count is below target, progress through fallback tiers:
        # 1. Page 2 of primary strategy
        # 2. Relax optional filters (vote_count_gte = 0)
        # 3. Broad genre / popularity while keeping hard language/region constraints locked!

        # Fallback Tier 1: Page 2 of Discovery
        if eligible_count < target_candidates:
            try:
                paged2: Optional[PagedResultModel] = None
                genre_filter_str = "|".join(str(gid) for gid in intent.genre_ids) if intent.genre_ids else None
                if intent.content_type == "movie":
                    paged2 = self.tmdb_client.discover_movies(
                        page=2,
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_genres=genre_filter_str,
                        sort_by=intent.sort_by,
                        primary_release_year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=vote_count_gte,
                    )
                elif intent.content_type == "tv":
                    paged2 = self.tmdb_client.discover_series(
                        page=2,
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_genres=genre_filter_str,
                        sort_by=intent.sort_by,
                        first_air_date_year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=vote_count_gte,
                    )
                else:
                    paged2 = self.tmdb_client.discover_all(
                        page=2,
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_genres=genre_filter_str,
                        sort_by=intent.sort_by,
                        year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=vote_count_gte,
                    )
                count_p2 = 0
                for item in (paged2.results if paged2 else []):
                    if add_candidate(item, source="page_2_fallback"):
                        count_p2 += 1
                if count_p2 > 0:
                    diagnostic_info["retrieval_tiers_used"].append("page_2_discovery")
                    diagnostic_info["counts_per_tier"]["page_2_discovery"] = count_p2
                    logger.info("[MovieRecommendation] Fallback Page 2: found %d eligible titles", count_p2)
            except Exception as e:
                self._record_tmdb_error(e, diagnostic_info)
                logger.debug("[MovieRecommendation] Fallback Page 2 error: %s", e)

        # Fallback Tier 2: Lower vote count threshold (vote_count_gte = 0)
        # NEVER relax mandatory constraints (language, region, date range)!
        if eligible_count < target_candidates:
            try:
                target_genre_ids = intent.genre_ids or intent.reference_genres
                genre_str = "|".join(str(gid) for gid in target_genre_ids) if target_genre_ids else None
                fallback_paged = (
                    self.tmdb_client.discover_movies(
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_genres=genre_str,
                        sort_by="vote_average.desc" if "underrated" in intent.keywords else "popularity.desc",
                        primary_release_year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=0,
                    )
                    if intent.content_type == "movie"
                    else self.tmdb_client.discover_all(
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        with_genres=genre_str,
                        sort_by="popularity.desc",
                        year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=0,
                    )
                )
                count_c1 = 0
                for item in fallback_paged.results:
                    if add_candidate(item, source="relaxed_vote_fallback"):
                        count_c1 += 1
                if count_c1 > 0:
                    diagnostic_info["retrieval_tiers_used"].append("fallback_relaxed_vote_count")
                    diagnostic_info["counts_per_tier"]["fallback_relaxed_vote_count"] = count_c1
                    logger.info("[MovieRecommendation] Fallback Tier 2 (vote_count_gte=0): found %d eligible titles", count_c1)
            except Exception as e:
                self._record_tmdb_error(e, diagnostic_info)
                logger.debug("[MovieRecommendation] Fallback Tier 2 error: %s", e)

        # Fallback Tier 3: Broad Regional / Popular Discovery if still low candidates
        if eligible_count < target_candidates:
            try:
                fallback_broad = (
                    self.tmdb_client.discover_movies(
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        sort_by="popularity.desc",
                        primary_release_year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=0,
                    )
                    if intent.content_type == "movie"
                    else self.tmdb_client.discover_all(
                        with_original_language=target_lang,
                        with_origin_country=origin_country,
                        sort_by="popularity.desc",
                        year=intent.release_year,
                        release_date_gte=date_gte,
                        release_date_lte=date_lte,
                        vote_count_gte=0,
                    )
                )
                count_c2 = 0
                for item in fallback_broad.results:
                    if add_candidate(item, source="broad_popularity_fallback"):
                        count_c2 += 1
                if count_c2 > 0:
                    diagnostic_info["retrieval_tiers_used"].append("fallback_broad_popularity")
                    diagnostic_info["counts_per_tier"]["fallback_broad_popularity"] = count_c2
                    logger.info("[MovieRecommendation] Fallback Tier 3 (Broad popularity): found %d eligible titles", count_c2)
            except Exception as e:
                self._record_tmdb_error(e, diagnostic_info)
                logger.debug("[MovieRecommendation] Fallback Tier 3 error: %s", e)

        diagnostic_info["total_retrieved"] = len(candidates)
        # Prioritize eligible candidates so fallback discoveries are not sliced away
        eligible_cands = []
        ineligible_cands = []
        for c in candidates:
            is_ok, _ = validate_candidate_eligibility(c, intent)
            if is_ok:
                eligible_cands.append(c)
            else:
                ineligible_cands.append(c)

        sorted_candidates = eligible_cands + ineligible_cands
        diagnostic_info["eligible_retrieved"] = len(eligible_cands)
        result_cands = sorted_candidates[:max(target_candidates, len(eligible_cands))]

        if return_diagnostics:
            return result_cands, diagnostic_info
        return result_cands

    def _adaptive_expand_retrieval(
        self,
        intent: ParsedRecommendationIntent,
        current_candidates: List[MediaItemSummary],
        target_min: int = 10,
    ) -> List[MediaItemSummary]:
        """Adaptively expand candidate pool if too few survive initial retrieval (Requirement D).

        Strictly preserves mandatory hard constraints (e.g. origin_country == 'IN' when Indian cinema is requested).
        Relaxes soft preference thresholds and queries additional discovery pages.
        """
        seen_ids = {c.id for c in current_candidates if c.id}
        expanded = list(current_candidates)

        is_indian = (
            intent.origin_country == "IN"
            or intent.region in (
                REGION_INDIAN,
                REGION_SOUTH_INDIAN,
                REGION_BOLLYWOOD,
                REGION_MALAYALAM,
                REGION_TAMIL,
                REGION_TELUGU,
                REGION_KANNADA,
            )
            or getattr(intent, "is_explicit_country", False)
        )
        origin_country = "IN" if is_indian else intent.origin_country
        target_lang = intent.language if getattr(intent, "is_explicit_language", False) else None

        try:
            # Query additional pages (2 and 3) of popular titles matching mandatory country/language constraints
            for page in (2, 3):
                paged = self.tmdb_client.discover_movies(
                    page=page,
                    sort_by="popularity.desc",
                    with_origin_country=origin_country,
                    with_original_language=target_lang,
                    vote_count_gte=15,
                )
                for item in (paged.results if paged else []):
                    if item.id and item.id not in seen_ids:
                        seen_ids.add(item.id)
                        item.retrieval_source = "adaptive_expansion"
                        expanded.append(item)
                if len(expanded) >= 40:
                    break
        except Exception as e:
            logger.warning("[MovieRecommendation] Adaptive retrieval expansion error: %s", e)

        return expanded

    # =========================================================================
    # Stage E: Multi-Signal Relevance Scoring & Ranking
    # =========================================================================

    def rank_candidates(
        self,
        candidates: List[MediaItemSummary],
        intent: ParsedRecommendationIntent,
        include_saved_preferences: bool = True,
        user_profile: Optional[Any] = None,
        limit: int = 6,
        apply_diversity: bool = True,
    ) -> List[Tuple[MediaItemSummary, float, List[str], Dict[str, float]]]:
        """Rank retrieved candidates using the multi-signal MovieRankingEngine with diversity controls."""
        if self._is_cancelled:
            raise RuntimeError("Recommendation cancelled by user")
        if not candidates:
            return []

        user_prefs = self.storage_repo.get_preferences() if include_saved_preferences else None
        if user_profile is None and include_saved_preferences:
            try:
                user_profile = self.storage_repo.build_user_profile()
            except Exception as e:
                logger.debug("[MovieRecommendation] Could not build user profile: %s", e)
                user_profile = None

        watched_titles = self.storage_repo.get_watched()
        watched_ids = {w.tmdb_id for w in watched_titles}

        # Phase 5: Generate query and candidate embeddings if semantic service is available
        semantic_scores: Optional[Dict[int, float]] = None
        sem_diag: Dict[str, Any] = {"active": False}

        if self.semantic_service and self.semantic_service.is_available():
            try:
                t_sem_start = time.perf_counter()
                semantic_query = self.semantic_service.build_semantic_query(intent)
                query_embedding = self.semantic_service.get_query_embedding(semantic_query)

                if query_embedding:
                    cand_embeddings, cand_emb_diag = self.semantic_service.get_candidate_embeddings(candidates)
                    if cand_embeddings:
                        semantic_scores = self.semantic_service.score_candidates_semantically(
                            candidates, query_embedding, cand_embeddings
                        )
                        sem_time_ms = round((time.perf_counter() - t_sem_start) * 1000.0, 1)
                        sem_diag = {
                            "active": True,
                            "model": self.semantic_service.model_name,
                            "query_embedded": True,
                            "candidates_embedded": len(cand_embeddings),
                            "cached_hits": cand_emb_diag.get("cached_hits", 0),
                            "time_ms": sem_time_ms,
                        }
            except Exception as e:
                logger.warning("Semantic embedding scoring encountered error, falling back to deterministic: %s", e)
                sem_diag = {"active": False, "error": str(e)}

        intent.diagnostics = intent.diagnostics or {}
        intent.diagnostics["semantic_ranking"] = sem_diag

        return self.ranking_engine.rank_candidates(
            candidates=candidates,
            intent=intent,
            user_prefs=user_prefs,
            user_profile=user_profile,
            watched_ids=watched_ids,
            limit=limit,
            apply_diversity=apply_diversity,
            semantic_scores=semantic_scores,
        )

    # =========================================================================
    # Stage F: Grounded Explanations via Ollama
    # =========================================================================

    def generate_grounded_explanations(
        self,
        ranked: List[Any],
        intent: ParsedRecommendationIntent,
        user_query: str,
    ) -> List[RecommendedTitleModel]:
        """Generate concise grounded explanations strictly anchored in real title synopsis."""
        if self._is_cancelled:
            raise RuntimeError("Recommendation cancelled by user")

        return self.explanation_engine.generate_explanations(
            ranked_candidates=ranked,
            intent=intent,
            user_query=user_query,
            is_cancelled=lambda: self._is_cancelled,
        )

    # =========================================================================
    # =========================================================================
    # Complete End-to-End Recommendation Workflow & Interactive Preference Editing
    # =========================================================================

    def apply_edited_preferences_to_intent(
        self,
        intent: ParsedRecommendationIntent,
        edited_preferences: List[Any],
        removed_preferences: Optional[List[Any]] = None,
    ) -> ParsedRecommendationIntent:
        """Apply authoritative user-edited preference chips to parsed intent."""
        intent_dict = intent.model_dump()
        new_intent = ParsedRecommendationIntent(**intent_dict)

        if edited_preferences is None:
            return new_intent

        prefs: List[EditedPreferenceModel] = []
        for p in edited_preferences:
            if isinstance(p, dict):
                prefs.append(EditedPreferenceModel(**p))
            elif isinstance(p, EditedPreferenceModel):
                prefs.append(p)
            elif hasattr(p, "category") and hasattr(p, "value"):
                prefs.append(EditedPreferenceModel(id=getattr(p, "id", None), category=p.category, label=getattr(p, "label", p.value), value=p.value))

        rems: List[EditedPreferenceModel] = []
        for p in (removed_preferences or []):
            if isinstance(p, dict):
                rems.append(EditedPreferenceModel(**p))
            elif isinstance(p, EditedPreferenceModel):
                rems.append(p)
            elif hasattr(p, "category") and hasattr(p, "value"):
                rems.append(EditedPreferenceModel(id=getattr(p, "id", None), category=p.category, label=getattr(p, "label", p.value), value=p.value))

        # 1. Reference Title ('ref')
        ref_chips = [p for p in prefs if p.category == "ref"]
        if ref_chips:
            ref_val = ref_chips[0].value.strip()
            new_intent.reference_title = ref_val
            new_intent.similar_to_title = ref_val
            new_intent.reference_titles = [ref_val]
        else:
            # Explicitly cleared reference title
            new_intent.reference_title = None
            new_intent.similar_to_title = None
            new_intent.reference_titles = []
            new_intent.reference_media = None
            new_intent.reference_genres = []
            if new_intent.intent_type == "similar_to":
                new_intent.intent_type = "general"

        # 2. Genres ('genre')
        genre_names: List[str] = []
        req_genres: List[str] = []
        pref_genres: List[str] = []
        for p in prefs:
            if p.category == "genre":
                norm = normalize_genre_name(p.value) or p.value
                genre_names.append(norm)
                if getattr(p, "nature", "preferred") == "required":
                    req_genres.append(norm)
                else:
                    pref_genres.append(norm)

        new_intent.genres = list(dict.fromkeys(genre_names))
        new_intent.genres_any = new_intent.genres
        new_intent.required_genres = list(dict.fromkeys(req_genres))
        new_intent.preferred_genres = list(dict.fromkeys(pref_genres))
        new_intent.genre_ids = [TMDB_MOVIE_GENRES[g] for g in new_intent.genres if g in TMDB_MOVIE_GENRES]

        # Enforce genre exclusions
        must_exclude = list(new_intent.must_exclude or [])
        for p in rems:
            if p.category == "genre":
                norm = normalize_genre_name(p.value) or p.value
                if norm not in must_exclude:
                    must_exclude.append(norm)
        new_intent.must_exclude = must_exclude

        # 3. Languages ('lang') - Support soft preferred vs hard required languages
        lang_codes: List[str] = []
        req_lang_codes: List[str] = []
        pref_lang_codes: List[str] = []
        for p in prefs:
            if p.category == "lang":
                val_clean = p.value.strip().lower()
                code = None
                if val_clean in LANGUAGE_AND_REGION_MAP:
                    code = LANGUAGE_AND_REGION_MAP[val_clean].get("language")
                elif len(val_clean) == 2:
                    code = val_clean
                else:
                    for lang_key, info in LANGUAGE_AND_REGION_MAP.items():
                        if val_clean in lang_key or lang_key in val_clean:
                            if info.get("language"):
                                code = info["language"]
                                break
                if code:
                    lang_codes.append(code)
                    if getattr(p, "nature", "preferred") == "required":
                        req_lang_codes.append(code)
                    else:
                        pref_lang_codes.append(code)

        lang_codes = list(dict.fromkeys(lang_codes))
        req_lang_codes = list(dict.fromkeys(req_lang_codes))
        pref_lang_codes = list(dict.fromkeys(pref_lang_codes))

        new_intent.original_languages = lang_codes
        new_intent.languages = lang_codes
        new_intent.language = lang_codes[0] if len(lang_codes) == 1 else (lang_codes[0] if lang_codes else None)
        new_intent.required_languages = req_lang_codes
        new_intent.preferred_languages = pref_lang_codes

        # Do not treat every language refinement as a mandatory filter!
        # Only enforce language as a hard gate if explicitly required by user.
        if req_lang_codes:
            new_intent.is_explicit_language = True
        else:
            new_intent.is_explicit_language = False

        # 4. Themes ('theme')
        new_intent.themes = [p.value for p in prefs if p.category == "theme"]
        new_intent.preferred_themes = [p.value for p in prefs if p.category == "theme"]

        # 5. Moods ('mood')
        new_intent.moods = [p.value for p in prefs if p.category == "mood"]
        new_intent.preferred_moods = [p.value for p in prefs if p.category == "mood"]
        if new_intent.moods:
            new_intent.mood = new_intent.moods[0]

        # 6. Plot elements ('plot')
        new_intent.plot_elements = [p.value for p in prefs if p.category == "plot"]

        # 7. Other preferences ('other' / temporal / vibes)
        keywords = list(new_intent.keywords or [])
        plot_elements = list(new_intent.plot_elements or [])
        for p in prefs:
            if p.category == "other":
                val_low = p.value.lower()
                if "underrated" in val_low and "underrated" not in keywords:
                    keywords.append("underrated")
                if ("plot twist" in val_low or "twists" in val_low) and "plot twist" not in plot_elements:
                    plot_elements.append("plot twist")
                if "fast paced" in val_low or "faster paced" in val_low or "fast-paced" in val_low:
                    if "fast-paced" not in keywords:
                        keywords.append("fast-paced")
                if "international" in val_low:
                    if "international" not in keywords:
                        keywords.append("international")
                if "recent" in val_low or "2020" in val_low:
                    new_intent.release_year_from = 2021
                    new_intent.release_year_gte = 2020
                if "classic" in val_low:
                    new_intent.release_year_to = 1990
            elif p.category == "theme":
                val_low = p.value.lower()
                if "psychological" in val_low and "psychological" not in plot_elements:
                    plot_elements.append("psychological")
        new_intent.keywords = keywords
        new_intent.plot_elements = plot_elements

        # Build clean summary
        summary_parts = []
        if new_intent.reference_title:
            summary_parts.append(f"Like '{new_intent.reference_title}'")
        if new_intent.genres:
            summary_parts.append(f"Genres: {', '.join(new_intent.genres)}")
        if new_intent.original_languages:
            summary_parts.append(f"Languages: {', '.join(new_intent.original_languages)}")
        if new_intent.themes:
            summary_parts.append(f"Themes: {', '.join(new_intent.themes)}")
        if new_intent.must_exclude:
            summary_parts.append(f"Excluding: {', '.join(new_intent.must_exclude)}")
        new_intent.interpreted_summary = " | ".join(summary_parts) or "Interactive preference discovery"

        return new_intent

    def recommend(
        self,
        query: str,
        include_saved_preferences: bool = True,
        limit: int = 6,
        edited_preferences: Optional[List[Any]] = None,
        removed_preferences: Optional[List[Any]] = None,
        request_id: Optional[str] = None,
    ) -> RecommendationResponse:
        """Execute full end-to-end multi-stage recommendation workflow with developer diagnostics."""
        t_start = time.perf_counter()
        self._is_cancelled = False
        is_ai_available = self.ollama_client.is_server_reachable()

        clean_q = query.strip()
        if not clean_q:
            return RecommendationResponse(
                query=query,
                interpreted_intent=ParsedRecommendationIntent(),
                recommendations=[],
                error_type="empty_query",
                error_message="Recommendation query cannot be empty.",
            )

        # Check in-memory response cache for identical repeat queries (Requirement 9.5)
        # Include authoritative edited and removed preferences in cache key to prevent stale cache collisions
        if edited_preferences is not None:
            def _chip_sig(c: Any) -> str:
                if isinstance(c, dict):
                    return f"{c.get('category')}:{c.get('value', '').lower()}"
                return f"{getattr(c, 'category', '')}:{getattr(c, 'value', '').lower()}"
            prefs_sig = "_".join(sorted(_chip_sig(p) for p in edited_preferences))
            rem_sig = "_".join(sorted(_chip_sig(p) for p in (removed_preferences or [])))
            cache_key = f"{clean_q.lower()}_edited_{prefs_sig}_rem_{rem_sig}_{include_saved_preferences}_{limit}"
        else:
            cache_key = f"{clean_q.lower()}_{include_saved_preferences}_{limit}"

        now = time.time()
        if cache_key in self._response_cache:
            cached_time, cached_resp = self._response_cache[cache_key]
            if now - cached_time < 300:  # 5-minute cache TTL
                logger.info("[MovieRecommendation] In-memory response cache hit for query: '%s'", clean_q)
                return cached_resp

        if not self.tmdb_client.is_configured():
            t_total = time.perf_counter() - t_start
            return RecommendationResponse(
                query=clean_q,
                interpreted_intent=ParsedRecommendationIntent(
                    interpreted_summary=clean_q,
                    content_type="all",
                ),
                recommendations=[],
                error_type="tmdb_unconfigured",
                error_message="TMDB API is not configured. Please add your TMDB API key in Settings.",
                diagnostics={
                    "original_query": clean_q,
                    "error": "TMDB API key not configured",
                    "timings_ms": {"total_pipeline": round(t_total * 1000.0, 1)},
                },
            )

        # Step 1: Parse natural-language intent (Stage A)
        t_parse_start = time.perf_counter()
        intent = self.parse_intent_with_llm(clean_q) if is_ai_available else self.parse_intent_deterministic(clean_q)
        t_parse_end = time.perf_counter()

        # Step 1.5: If user supplied authoritative edited preferences, override the intent
        if edited_preferences is not None:
            intent = self.apply_edited_preferences_to_intent(
                intent,
                edited_preferences=edited_preferences,
                removed_preferences=removed_preferences,
            )
            logger.info(
                "[MovieRecommendation] Applied user-edited preferences: %d active chips, %d removed",
                len(edited_preferences),
                len(removed_preferences or []),
            )

        if self._is_cancelled:
            raise RuntimeError("Recommendation cancelled by user")

        logger.info(
            "[MovieRecommendation] Parsed intent for '%s': type=%s, ref=%s, content=%s, region=%s, lang=%s, genres=%s",
            clean_q,
            intent.intent_type,
            intent.reference_title,
            intent.content_type,
            intent.region,
            intent.language,
            intent.genres,
        )

        # Step 2: Resolve reference title verified metadata (Stage B)
        t_res_start = time.perf_counter()
        ref_resolved = False
        if intent.reference_title or intent.similar_to_title:
            ref_media = self.resolve_reference_title(intent)
            ref_resolved = bool(ref_media)
        t_res_end = time.perf_counter()

        if self._is_cancelled:
            raise RuntimeError("Recommendation cancelled by user")

        # Step 3: Multi-stage candidate retrieval & fallback (Stage C & D)
        t_ret_start = time.perf_counter()
        ret_result = self.retrieve_candidates(intent, limit=36, return_diagnostics=True)
        if isinstance(ret_result, tuple) and len(ret_result) == 2 and isinstance(ret_result[1], dict):
            raw_candidates, ret_diag = ret_result
        else:
            raw_candidates = ret_result if isinstance(ret_result, list) else []
            ret_diag = {"retrieval_tiers_used": ["direct_retrieval"], "counts_per_tier": {}}
        t_ret_end = time.perf_counter()

        logger.info(
            "[MovieRecommendation] Retrieved %d raw candidates across tiers: %s",
            len(raw_candidates),
            ret_diag.get("retrieval_tiers_used", []),
        )

        # Step 4: Strict eligibility filtering
        t_filt_start = time.perf_counter()
        eligible_candidates, rejected_candidates = filter_eligible_candidates(raw_candidates, intent)
        t_filt_end = time.perf_counter()

        logger.info(
            "[MovieRecommendation] Eligibility filtering: %d passed, %d rejected",
            len(eligible_candidates),
            len(rejected_candidates),
        )

        # Step 4.5: Automatic Intelligent Recovery & Adaptive Expansion (Phase 5 Requirement B)
        # When possible:
        # 1. Retry retrieval
        # 2. Expand candidate discovery
        # 3. Relax soft preferences
        # 4. Preserve hard constraints
        # 5. Re-rank candidates
        # Do not automatically remove mandatory user requirements.
        recovery_attempted = False
        recovery_successful = False
        recovery_actions: List[str] = []

        if len(eligible_candidates) < 10 and not (ret_diag.get("error_type") in ("api_failure", "tmdb_unconfigured", "network_error")):
            recovery_attempted = True
            logger.info(
                "[MovieRecommendation] Few eligible candidates (%d); initiating automatic recovery pipeline",
                len(eligible_candidates),
            )
            # Action 1: Preserve hard constraints and expand candidate discovery (pages 2 and 3)
            recovery_actions.append("expanded_discovery")
            raw_candidates = self._adaptive_expand_retrieval(intent, raw_candidates, target_min=24)
            eligible_candidates, rejected_candidates = filter_eligible_candidates(raw_candidates, intent)

            # Action 2: If still fewer than 6, query popular titles in verified target country/industry
            if len(eligible_candidates) < 6:
                recovery_actions.append("country_aware_top_discovery")
                is_indian = (
                    intent.origin_country == "IN"
                    or intent.region in (
                        REGION_INDIAN,
                        REGION_SOUTH_INDIAN,
                        REGION_BOLLYWOOD,
                        REGION_MALAYALAM,
                        REGION_TAMIL,
                        REGION_TELUGU,
                        REGION_KANNADA,
                    )
                    or getattr(intent, "is_explicit_country", False)
                )
                origin_c = "IN" if is_indian else intent.origin_country
                target_lang = intent.language if getattr(intent, "is_explicit_language", False) else None
                genre_ids_str = ",".join(str(gid) for gid in intent.genre_ids[:2]) if intent.genre_ids else None

                try:
                    paged = self.tmdb_client.discover_movies(
                        page=1,
                        sort_by="popularity.desc",
                        with_origin_country=origin_c,
                        with_original_language=target_lang,
                        with_genres=genre_ids_str,
                        vote_count_gte=20,
                    )
                    existing_ids = {c.id for c in raw_candidates if c.id}
                    for item in (paged.results if paged else []):
                        if item.id and item.id not in existing_ids:
                            existing_ids.add(item.id)
                            item.retrieval_source = "recovery_top_discovery"
                            raw_candidates.append(item)
                    eligible_candidates, rejected_candidates = filter_eligible_candidates(raw_candidates, intent)
                except Exception as ex:
                    logger.warning("[MovieRecommendation] Recovery discovery query warning: %s", ex)

        # Step 5: Multi-signal ranking (Stage E)
        # Return preferably 10 to 20 recommendations when sufficient candidates exist
        target_limit = min(20, max(limit, 12)) if len(eligible_candidates) >= 12 else min(len(eligible_candidates), max(limit, 10))
        t_rank_start = time.perf_counter()
        ranked = self.rank_candidates(
            candidates=eligible_candidates,
            intent=intent,
            include_saved_preferences=include_saved_preferences,
            limit=target_limit,
        )
        t_rank_end = time.perf_counter()

        # Step 6: Grounded explanations (Stage F)
        if self._is_cancelled:
            raise RuntimeError("Recommendation cancelled by user")
        t_exp_start = time.perf_counter()
        recommended_models = self.generate_grounded_explanations(
            ranked=ranked,
            intent=intent,
            user_query=clean_q,
        )
        t_exp_end = time.perf_counter()

        # Step 7: Final candidate validation & deduplication
        final_recommendations: List[RecommendedTitleModel] = []
        final_seen_ids: Set[int] = set()
        ref_id = intent.reference_media.id if intent.reference_media else None

        for rec in recommended_models:
            item = rec.media
            if not item or item.id in final_seen_ids:
                continue
            if ref_id and item.id == ref_id:
                continue

            is_valid, _ = validate_candidate_eligibility(item, intent)
            if is_valid:
                final_recommendations.append(rec)
                final_seen_ids.add(item.id)

        # Action 3: Post-ranking recovery - If 0 recommendations survived ranking but eligible candidates exist
        if not final_recommendations and eligible_candidates:
            recovery_actions.append("relaxed_soft_ranking")
            target_limit = min(20, max(limit, 8))
            ranked = self.rank_candidates(
                candidates=eligible_candidates,
                intent=intent,
                include_saved_preferences=include_saved_preferences,
                limit=target_limit,
            )
            if ranked:
                recommended_models = self.generate_grounded_explanations(
                    ranked=ranked,
                    intent=intent,
                    user_query=clean_q,
                )
                for rec in recommended_models:
                    item = rec.media
                    if not item or item.id in final_seen_ids:
                        continue
                    if ref_id and item.id == ref_id:
                        continue
                    is_valid, _ = validate_candidate_eligibility(item, intent)
                    if is_valid:
                        final_recommendations.append(rec)
                        final_seen_ids.add(item.id)

        if final_recommendations:
            if recovery_attempted:
                recovery_successful = True

        t_total = time.perf_counter() - t_start

        # Phase 5 Requirement A: Determine exact empty-result root cause
        error_type: Optional[str] = None
        error_message: Optional[str] = None

        rejection_breakdown: Dict[str, int] = {}
        for _, reason in rejected_candidates:
            r_low = reason.lower()
            if "regional" in r_low or "country" in r_low or "origin" in r_low:
                rejection_breakdown["country_mismatch"] = rejection_breakdown.get("country_mismatch", 0) + 1
            elif "language" in r_low:
                rejection_breakdown["language_mismatch"] = rejection_breakdown.get("language_mismatch", 0) + 1
            elif "missing" in r_low or "incomplete" in r_low:
                rejection_breakdown["incomplete_metadata"] = rejection_breakdown.get("incomplete_metadata", 0) + 1
            elif "era" in r_low or "year" in r_low:
                rejection_breakdown["era_mismatch"] = rejection_breakdown.get("era_mismatch", 0) + 1
            elif "content type" in r_low:
                rejection_breakdown["content_type_mismatch"] = rejection_breakdown.get("content_type_mismatch", 0) + 1
            elif "excluded" in r_low:
                rejection_breakdown["excluded_genre"] = rejection_breakdown.get("excluded_genre", 0) + 1
            else:
                rejection_breakdown["other_criteria"] = rejection_breakdown.get("other_criteria", 0) + 1

        if not final_recommendations:
            # 1. API failure occurred
            if ret_diag.get("error_type") in ("api_failure", "tmdb_unconfigured", "network_error", "tmdb_auth_error"):
                error_type = "api_failure"
                error_message = ret_diag.get("error_message") or "TMDB search service connection or API key error."
            # 2. Reference movie was not resolved
            elif (intent.reference_title or intent.similar_to_title) and not ref_resolved:
                error_type = "reference_not_resolved"
                ref_name = intent.reference_title or intent.similar_to_title
                error_message = f"Reference movie '{ref_name}' could not be resolved in the TMDB filmography catalog."
            # 3. TMDB returned no candidates at all
            elif not raw_candidates:
                error_type = "tmdb_no_candidates"
                error_message = f"TMDB returned zero candidates for '{clean_q}'. Try broadening query keywords or exploring by mood."
            # 4. Candidates were returned, but 0 passed hard filters
            elif raw_candidates and not eligible_candidates:
                c_rej = rejection_breakdown.get("country_mismatch", 0)
                l_rej = rejection_breakdown.get("language_mismatch", 0)
                m_rej = rejection_breakdown.get("incomplete_metadata", 0)

                if c_rej > 0 and c_rej >= l_rej and c_rej >= m_rej:
                    error_type = "country_too_restrictive"
                    c_name = intent.origin_country or intent.region or "the required country"
                    error_message = f"Country filtering was too restrictive: all {len(raw_candidates)} retrieved titles were rejected because they did not match the required region/country ({c_name})."
                elif l_rej > 0 and l_rej >= m_rej:
                    error_type = "language_too_restrictive"
                    l_name = intent.language or ", ".join(intent.original_languages) or "the required language"
                    error_message = f"Language filtering was too restrictive: all {len(raw_candidates)} retrieved titles were rejected because they did not match the required language ({l_name})."
                elif m_rej > 0:
                    error_type = "metadata_incomplete"
                    error_message = f"Metadata was incomplete: {m_rej} retrieved titles lacked critical metadata (e.g. original language or origin country) necessary to verify eligibility."
                else:
                    error_type = "candidates_filtered"
                    error_message = f"Discovered {len(raw_candidates)} titles in TMDB, but none satisfied all mandatory criteria ({intent.interpreted_summary})."
            # 5. Candidates passed hard filters, but ranking score was too low
            elif eligible_candidates and not final_recommendations:
                error_type = "ranking_threshold_too_high"
                error_message = f"{len(eligible_candidates)} candidates passed hard filters, but none met the minimum relevance ranking threshold."
            else:
                error_type = "zero_results"
                error_message = "No matching recommendations selected after filtering and ranking."

        # Build Developer Diagnostics & Transparency Payload (Phase 5 Requirement C)
        diagnostics: Dict[str, Any] = {
            "original_query": clean_q,
            "request_id": request_id,
            "edited_preferences_applied": bool(edited_preferences is not None),
            "intent_type": intent.intent_type,
            "reference_movie": intent.reference_media.title if intent.reference_media else (intent.reference_title or None),
            "reference_title_requested": intent.reference_title,
            "reference_resolved": ref_resolved,
            "reference_tmdb_id": intent.reference_media.id if intent.reference_media else None,
            "reference_media_title": intent.reference_media.title if intent.reference_media else None,
            "required_country": intent.origin_country or (intent.region if intent.is_explicit_country else None),
            "required_language": intent.language if intent.is_explicit_language else (intent.original_languages[0] if getattr(intent, 'is_explicit_language', False) and intent.original_languages else None),
            "preferred_genres": intent.preferred_genres or intent.genres or [],
            "preferred_themes": intent.preferred_themes or intent.themes or [],
            "preferred_languages": intent.preferred_languages or [],
            "candidates_retrieved": len(raw_candidates),
            "candidates_passing_hard_filters": len(eligible_candidates),
            "candidates_ranked": len(ranked),
            "final_recommendations_count": len(final_recommendations),
            "funnel_breakdown": {
                "retrieved": len(raw_candidates),
                "passed_hard_filters": len(eligible_candidates),
                "ranked": len(ranked),
                "final": len(final_recommendations),
            },
            "rejection_breakdown": rejection_breakdown,
            "recovery_attempted": recovery_attempted,
            "recovery_successful": recovery_successful,
            "recovery_actions": recovery_actions,
            "retrieval_tiers_used": ret_diag.get("retrieval_tiers_used", []),
            "candidates_per_tier": ret_diag.get("counts_per_tier", {}),
            "raw_candidates_count": len(raw_candidates),
            "eligible_candidates_count": len(eligible_candidates),
            "rejected_candidates_count": len(rejected_candidates),
            "ranking_weights": self.ranking_engine.get_normalized_weights(),
            "semantic_ranking": intent.diagnostics.get("semantic_ranking", {"active": False}) if intent.diagnostics else {"active": False},
            "timings_ms": {
                "intent_parsing": round((t_parse_end - t_parse_start) * 1000.0, 1),
                "reference_resolution": round((t_res_end - t_res_start) * 1000.0, 1),
                "candidate_retrieval": round((t_ret_end - t_ret_start) * 1000.0, 1),
                "filtering": round((t_filt_end - t_filt_start) * 1000.0, 1),
                "ranking": round((t_rank_end - t_rank_start) * 1000.0, 1),
                "explanation_generation": round((t_exp_end - t_exp_start) * 1000.0, 1),
                "total_pipeline": round(t_total * 1000.0, 1),
            },
        }

        intent.diagnostics = diagnostics

        # Organize presentation sections when useful (Requirement 6.4)
        presentation_sections = self.explanation_engine.organize_presentation_sections(
            final_recommendations,
            min_candidates=3,
        )

        resp = RecommendationResponse(
            query=clean_q,
            interpreted_intent=intent,
            recommendations=final_recommendations,
            presentation_sections=presentation_sections,
            total_candidates_analyzed=len(raw_candidates),
            ai_available=is_ai_available,
            model_used=self.default_model if is_ai_available else None,
            diagnostics=diagnostics,
            error_type=error_type,
            error_message=error_message,
        )
            presentation_sections=presentation_sections,
            total_candidates_analyzed=len(raw_candidates),
            ai_available=is_ai_available,
            model_used=self.default_model if is_ai_available else None,
            diagnostics=diagnostics,
            error_type=error_type,
            error_message=error_message,
        )
        if self._is_cancelled:
            raise RuntimeError("Recommendation cancelled by user")

        if not error_type and final_recommendations:
            self._response_cache[cache_key] = (time.time(), resp)

        return resp
