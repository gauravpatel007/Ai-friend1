"""Pydantic data models for Movie Hub metadata, discovery, details, and errors."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class GenreModel(BaseModel):
    """Movie or television genre metadata."""
    id: int
    name: str


class CastMemberModel(BaseModel):
    """Acting cast credit."""
    id: int
    name: str
    character: Optional[str] = None
    profile_path: Optional[str] = None
    profile_url: Optional[str] = None
    order: Optional[int] = 0


class CrewMemberModel(BaseModel):
    """Production or directing crew credit."""
    id: int
    name: str
    job: Optional[str] = None
    department: Optional[str] = None
    profile_path: Optional[str] = None


class VideoModel(BaseModel):
    """Trailer, teaser, or clip metadata."""
    id: str
    key: str
    name: str
    site: str = "YouTube"
    type: str = "Trailer"
    official: bool = True
    url: Optional[str] = None


class MediaItemSummary(BaseModel):
    """Normalized media item summary for catalog cards and discovery grids."""
    id: int
    title: str
    original_title: Optional[str] = None
    media_type: str = Field(default="movie", description="'movie' or 'tv'")
    overview: str = ""
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    release_date: Optional[str] = None
    release_year: Optional[int] = None
    original_language: Optional[str] = None
    origin_country: Optional[List[str]] = None
    genre_ids: List[int] = Field(default_factory=list)
    genre_names: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    vote_average: float = 0.0
    vote_count: int = 0
    popularity: float = 0.0
    retrieval_source: Optional[str] = Field(default=None, description="Retrieval source: similar, recommendation, keyword_discover, genre_discover, fallback")
    reference_movie_id: Optional[int] = Field(default=None, description="TMDB ID of reference movie if retrieved via similarity")


class MediaDetailsModel(MediaItemSummary):
    """Comprehensive details for a movie or TV series."""
    tagline: Optional[str] = None
    runtime_minutes: Optional[int] = None
    status: Optional[str] = None
    genres: List[GenreModel] = Field(default_factory=list)
    cast: List[CastMemberModel] = Field(default_factory=list)
    directors: List[str] = Field(default_factory=list)
    trailers: List[VideoModel] = Field(default_factory=list)
    similar: List[MediaItemSummary] = Field(default_factory=list)
    number_of_seasons: Optional[int] = None
    number_of_episodes: Optional[int] = None


class PagedResultModel(BaseModel):
    """Paginated collection of media items."""
    page: int = 1
    total_pages: int = 1
    total_results: int = 0
    results: List[MediaItemSummary] = Field(default_factory=list)


class TMDBConfigStatus(BaseModel):
    """TMDB service operational configuration and status."""
    configured: bool
    image_base_url: str
    attribution: str = "This product uses the TMDB API but is not endorsed or certified by TMDB."
    supported_media_types: List[str] = Field(default_factory=lambda: ["all", "movies", "series"])


# =============================================================================
# Phase 8: Local Storage, Watchlist, Favorites & User Preferences Models
# =============================================================================


class UserMediaEntry(BaseModel):
    """User-saved media entry tracked in local SQLite database."""
    id: Optional[int] = None
    tmdb_id: int
    media_type: str = Field(default="movie", description="'movie' or 'tv'")
    title: str
    poster_path: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_path: Optional[str] = None
    backdrop_url: Optional[str] = None
    release_year: Optional[int] = None
    release_date: Optional[str] = None
    original_language: Optional[str] = None
    vote_average: float = 0.0
    overview: str = ""
    status: str = Field(default="watchlist", description="'watchlist', 'watching', 'watched', 'dropped', 'none'")
    is_favorite: bool = False
    user_rating: Optional[int] = Field(default=None, ge=1, le=10, description="Local personal rating (1-10)")
    user_notes: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    watched_at: Optional[str] = None
    genres: Optional[str] = Field(default="", description="Comma-separated or JSON list of genre names or IDs")


class AddToWatchlistRequest(BaseModel):
    """Request payload to save or update title in watchlist."""
    tmdb_id: int
    media_type: str = "movie"
    title: str
    poster_path: Optional[str] = None
    release_year: Optional[int] = None
    original_language: Optional[str] = None
    vote_average: Optional[float] = 0.0
    overview: Optional[str] = ""
    status: str = "watchlist"
    is_favorite: Optional[bool] = None
    user_rating: Optional[int] = Field(default=None, ge=1, le=10)
    genres: Optional[str] = ""


class UpdateEntryStatusRequest(BaseModel):
    """Request payload to alter tracking status."""
    status: str = Field(..., description="'watchlist', 'watching', 'watched', 'dropped', 'plan_to_watch', 'none'")


class MarkWatchedRequest(BaseModel):
    """Optional request payload when marking a title as watched."""
    title: Optional[str] = None
    poster_path: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_path: Optional[str] = None
    backdrop_url: Optional[str] = None
    release_year: Optional[int] = None
    release_date: Optional[str] = None
    original_language: Optional[str] = None
    vote_average: Optional[float] = 0.0
    overview: Optional[str] = ""
    genres: Optional[str] = ""


class SetFavoriteRequest(BaseModel):
    """Request payload to toggle favorite status."""
    is_favorite: bool
    title: Optional[str] = None
    poster_path: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_path: Optional[str] = None
    backdrop_url: Optional[str] = None
    release_year: Optional[int] = None
    release_date: Optional[str] = None
    original_language: Optional[str] = None
    vote_average: Optional[float] = 0.0
    overview: Optional[str] = ""
    genres: Optional[str] = ""


class SetRatingRequest(BaseModel):
    """Request payload to assign or clear local user rating."""
    rating: Optional[int] = Field(default=None, ge=1, le=10, description="1 to 10 integer rating, or None to clear")
    title: Optional[str] = None
    poster_path: Optional[str] = None
    release_year: Optional[int] = None


class MovieUserPreferences(BaseModel):
    """User preferences for preferred genres, languages, and regional cinema."""
    preferred_genres: List[str] = Field(default_factory=list)
    preferred_languages: List[str] = Field(default_factory=lambda: ["all"])
    preferred_regions: List[str] = Field(default_factory=lambda: ["all"])
    disliked_genres: List[str] = Field(default_factory=list)
    exclude_watched: bool = False
    prefer_underrated: bool = False
    prefer_highly_rated: bool = False
    prefer_newer: bool = False
    prefer_classic: bool = False
    recommendation_settings: Dict[str, Any] = Field(
        default_factory=lambda: {
            "min_rating": 6.0,
            "include_watched": False,
            "exclude_watched": True,
            "prefer_underrated": False,
            "prefer_highly_rated": False,
            "prefer_newer": False,
            "prefer_classic": False,
        }
    )
    updated_at: Optional[str] = None


class PreferencesUpdateRequest(BaseModel):
    """Request payload to update user entertainment preferences."""
    preferred_genres: Optional[List[str]] = None
    preferred_languages: Optional[List[str]] = None
    preferred_regions: Optional[List[str]] = None
    disliked_genres: Optional[List[str]] = None
    exclude_watched: Optional[bool] = None
    prefer_underrated: Optional[bool] = None
    prefer_highly_rated: Optional[bool] = None
    prefer_newer: Optional[bool] = None
    prefer_classic: Optional[bool] = None
    recommendation_settings: Optional[Dict[str, Any]] = None


class MovieFeedbackRequest(BaseModel):
    """Request payload to record user feedback on a movie recommendation."""
    tmdb_id: int
    media_type: str = "movie"
    feedback_type: str = Field(..., description="'more_like_this', 'not_interested', 'already_watched', 'not_my_taste'")
    title: Optional[str] = ""
    genres: Optional[str] = ""


class MovieFeedbackModel(BaseModel):
    """Stored user feedback item."""
    id: str
    tmdb_id: int
    media_type: str
    feedback_type: str
    title: str = ""
    genres: str = ""
    created_at: str
    updated_at: str


class UserMovieProfile(BaseModel):
    """Constructed user preference profile for personalized recommendation scoring."""
    preferred_genres: List[str] = Field(default_factory=list)
    disliked_genres: List[str] = Field(default_factory=list)
    preferred_languages: List[str] = Field(default_factory=list)
    exclude_watched: bool = False
    prefer_underrated: bool = False
    prefer_highly_rated: bool = False
    prefer_newer: bool = False
    prefer_classic: bool = False
    favorite_ids: Set[int] = Field(default_factory=set)
    watched_ids: Set[int] = Field(default_factory=set)
    watchlist_ids: Set[int] = Field(default_factory=set)
    liked_ids: Set[int] = Field(default_factory=set)
    disliked_ids: Set[int] = Field(default_factory=set)
    genre_affinities: Dict[str, float] = Field(default_factory=dict)


UserMovieProfile.model_rebuild()


# =============================================================================
# =============================================================================
# Phase 9 & Recommendation Upgrade: AI Intent & Evaluation Models
# =============================================================================


class RecommendationQueryType(str, Enum):
    """Fine-grained classification of movie recommendation queries."""
    SIMILAR_TO = "similar_to"
    GENRE_DISCOVERY = "genre_discovery"
    MOOD_DISCOVERY = "mood_discovery"
    PLOT_BASED_DISCOVERY = "plot_based_discovery"
    REGIONAL_DISCOVERY = "regional_discovery"
    TIME_BASED_DISCOVERY = "time_based_discovery"
    PERSON_BASED_DISCOVERY = "person_based_discovery"
    HYBRID_DISCOVERY = "hybrid_discovery"
    GENERAL_DISCOVERY = "general_discovery"


class StructuredOllamaIntent(BaseModel):
    """Raw structured intent output extracted by Ollama using native JSON schema."""
    query_type: str = Field(
        default="general_discovery",
        description="'similar_to', 'genre_discovery', 'mood_discovery', 'plot_based_discovery', 'regional_discovery', 'time_based_discovery', 'person_based_discovery', 'hybrid_discovery', or 'general_discovery'",
    )
    content_type: str = Field(default="movie", description="'movie', 'tv', or 'all'")
    genres_any: List[str] = Field(default_factory=list, description="Alternative acceptable genres (OR logic)")
    genres_all: List[str] = Field(default_factory=list, description="Mandatory required genres (AND logic)")
    moods: List[str] = Field(default_factory=list, description="Atmospheric or emotional moods e.g. ['mind-bending']")
    themes: List[str] = Field(default_factory=list, description="Thematic topics e.g. ['psychological', 'reality distortion']")
    plot_elements: List[str] = Field(default_factory=list, description="Specific plot mechanics e.g. ['plot twist', 'unreliable narrator', 'time loop']")
    keywords_any: List[str] = Field(default_factory=list, description="Descriptive search terms or keywords")
    reference_titles: List[str] = Field(default_factory=list, description="Titles of specific reference movies or shows")
    reference_persons: List[str] = Field(default_factory=list, description="Directors, actors, or creators mentioned")
    original_languages: List[str] = Field(default_factory=list, description="ISO language codes e.g. ['ml', 'hi', 'en']")
    regions: List[str] = Field(default_factory=list, description="Regional industries e.g. ['south_indian', 'bollywood', 'hollywood']")
    countries: List[str] = Field(default_factory=list, description="Origin countries e.g. ['IN', 'US', 'KR']")
    release_year_from: Optional[int] = Field(default=None, description="Earliest release year")
    release_year_to: Optional[int] = Field(default=None, description="Latest release year")
    must_include: List[str] = Field(default_factory=list, description="Strictly required terms")
    must_exclude: List[str] = Field(default_factory=list, description="Terms or elements that must be avoided")
    soft_preferences: List[str] = Field(default_factory=list, description="Desirable but non-mandatory preferences")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ParsedRecommendationIntent(BaseModel):
    """Structured extraction of natural-language recommendation preferences."""
    # Intent Classification
    intent_type: str = Field(default="general", description="'similar_to', 'genre', 'regional', 'time_period', 'mood', 'complex', or 'general'")
    query_type: str = Field(default="general_discovery", description="Fine-grained classification from StructuredOllamaIntent")
    request_type: str = Field(default="general_discovery", description="'similar_to', 'regional_similarity', 'genre_discovery', 'regional_discovery', 'hybrid_discovery'")
    raw_query: Optional[str] = Field(default=None, description="Original raw user search query string")

    # Mandatory Constraints & Explicit Flags
    content_type: str = Field(default="all", description="'all', 'movie', or 'tv'")
    origin_country: Optional[str] = Field(default=None, description="Target origin country code e.g. 'IN', 'US', 'KR'")
    is_explicit_language: bool = Field(default=False, description="True if language was explicitly mentioned by user")
    is_explicit_country: bool = Field(default=False, description="True if country or regional industry was explicitly mentioned by user")
    is_explicit_genre: bool = Field(default=False, description="True if genre was explicitly mentioned by user")
    language: Optional[str] = Field(default=None, description="ISO 639-1 code e.g. 'ml', 'hi', 'en'")
    languages: List[str] = Field(default_factory=list, description="Permitted language codes e.g. ['te', 'ta', 'ml', 'kn']")
    original_languages: List[str] = Field(default_factory=list, description="Explicit requested languages")
    preferred_languages: List[str] = Field(default_factory=list, description="Soft preferred language codes")
    required_languages: List[str] = Field(default_factory=list, description="Mandatory required language codes")
    region: Optional[str] = Field(default=None, description="'south_indian', 'bollywood', 'hollywood', etc.")
    regions: List[str] = Field(default_factory=list, description="Regional industries e.g. ['south_indian', 'bollywood']")
    countries: List[str] = Field(default_factory=list, description="Target origin countries e.g. ['IN', 'US']")
    release_year: Optional[int] = None
    release_year_gte: Optional[int] = None
    release_year_lte: Optional[int] = None
    release_year_min: Optional[int] = None
    release_year_max: Optional[int] = None
    release_year_from: Optional[int] = None
    release_year_to: Optional[int] = None
    release_period: Optional[str] = Field(default=None, description="Human readable period e.g. 'after 2020', '90s'")
    rating_preference: Optional[str] = Field(default=None, description="e.g. 'highly rated', 'underrated'")
    similarity_strength: str = Field(default="balanced", description="'strict', 'balanced', or 'loose'")
    excluded_preferences: List[str] = Field(default_factory=list, description="Preferences or tags to exclude")
    excluded_genres: List[str] = Field(default_factory=list, description="Explicitly excluded genre names")

    # Reference Title & Person Resolution
    similar_to_title: Optional[str] = None
    reference_title: Optional[str] = None
    reference_titles: List[str] = Field(default_factory=list)
    reference_persons: List[str] = Field(default_factory=list)
    reference_year: Optional[int] = None
    similarity_mode: str = Field(default="attributes", description="'reference_title', 'attributes', or 'mood'")
    reference_media: Optional[MediaItemSummary] = None
    reference_genres: List[int] = Field(default_factory=list, description="TMDB genre IDs inherited from reference title")
    reference_characteristics: Dict[str, Any] = Field(default_factory=dict, description="Verified TMDB metadata for reference title")

    # Thematic, Mood, & Logical Filter Conditions
    genres: List[str] = Field(default_factory=list, description="Genre names e.g. ['Thriller']")
    genres_any: List[str] = Field(default_factory=list, description="Alternative acceptable genres (OR logic)")
    genres_all: List[str] = Field(default_factory=list, description="Mandatory required genres (AND logic)")
    required_genres: List[str] = Field(default_factory=list, description="Mandatory required genres")
    preferred_genres: List[str] = Field(default_factory=list, description="Soft preferred genres")
    genre_ids: List[int] = Field(default_factory=list, description="TMDB genre IDs")
    keywords: List[str] = Field(default_factory=list, description="Descriptive terms e.g. ['underrated', 'whodunit']")
    keywords_any: List[str] = Field(default_factory=list, description="Alternative keywords (OR logic)")
    mood: Optional[str] = Field(default=None, description="Mood or thematic tone e.g. 'mind-bending', 'feel-good'")
    moods: List[str] = Field(default_factory=list, description="Multiple atmospheric moods")
    preferred_moods: List[str] = Field(default_factory=list, description="Preferred moods")
    themes: List[str] = Field(default_factory=list, description="Thematic topics e.g. ['psychological']")
    preferred_themes: List[str] = Field(default_factory=list, description="Preferred themes")
    plot_elements: List[str] = Field(default_factory=list, description="Plot mechanics e.g. ['plot twist', 'time loop']")
    must_include: List[str] = Field(default_factory=list, description="Mandatory elements")
    must_exclude: List[str] = Field(default_factory=list, description="Forbidden elements")
    soft_preferences: List[str] = Field(default_factory=list, description="Desirable preferences")
    confidence: float = Field(default=1.0)
    sort_by: str = "popularity.desc"

    # Validation & Conflicts
    has_conflict: bool = False
    conflict_message: Optional[str] = None
    mandatory_constraints: Dict[str, Any] = Field(default_factory=dict)
    optional_preferences: Dict[str, Any] = Field(default_factory=dict)
    interpreted_summary: str = ""
    diagnostics: Optional[Dict[str, Any]] = None


class RelevanceWeightsModel(BaseModel):
    """Configurable weights for multi-signal movie relevance scoring engine."""
    semantic_plot: float = Field(default=0.30, ge=0.0, le=1.0, description="Semantic plot & synopsis similarity (default 30%)")
    genre_relevance: float = Field(default=0.20, ge=0.0, le=1.0, description="Genre alignment and DNA overlap (default 20%)")
    theme_keywords: float = Field(default=0.20, ge=0.0, le=1.0, description="Thematic and trope keyword matches (default 20%)")
    mood_atmosphere: float = Field(default=0.10, ge=0.0, le=1.0, description="Atmospheric and emotional tone (default 10%)")
    source_signal: float = Field(default=0.10, ge=0.0, le=1.0, description="Similar/recommended collaborative filtering source (default 10%)")
    quality_credibility: float = Field(default=0.05, ge=0.0, le=1.0, description="Bayesian smoothed rating and vote confidence (default 5%)")
    contextual_preferences: float = Field(default=0.05, ge=0.0, le=1.0, description="Underrated gems, release era, and user taste (default 5%)")


class RecommendedTitleModel(BaseModel):
    """A verified title with recommendation score and grounded AI explanation."""
    media: MediaItemSummary
    score: float = Field(default=0.0, description="Normalized ranking score (0-100)")
    match_reasons: List[str] = Field(default_factory=list)
    relevance_breakdown: Optional[Dict[str, float]] = Field(default=None, description="Granular signal scores (plot, genre, themes, mood, source, quality, context)")
    ai_explanation: str = Field(default="", description="Grounded explanation strictly referencing metadata")
    is_ai_generated: bool = Field(default=True, description="True if generated by LLM, False if fallback")
    presentation_section: Optional[str] = Field(default=None, description="Presentation group e.g. 'Best Matches', 'Hidden Gems', 'More Like Your Request', 'Alternative Picks'")


class EditedPreferenceModel(BaseModel):
    """User-edited preference chip for interactive preference management."""
    id: Optional[str] = None
    category: str = Field(default="theme", description="'genre', 'mood', 'theme', 'plot', 'lang', 'year', 'ref', 'country', 'other'")
    label: str
    value: str
    nature: str = Field(default="preferred", description="'required', 'preferred', or 'reference'")


class RecommendationRequest(BaseModel):
    """Request payload asking for AI recommendations."""
    query: str = Field(default="", description="Natural-language recommendation request")
    include_saved_preferences: bool = True
    limit: int = Field(default=6, ge=1, le=20)
    edited_preferences: Optional[List[EditedPreferenceModel]] = Field(
        default=None,
        description="Authoritative active preference chips when user modifies preferences"
    )
    removed_preferences: Optional[List[EditedPreferenceModel]] = Field(
        default=None,
        description="Explicitly removed preference chips"
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Client session or request identifier to prevent stale overwrites"
    )


class RecommendationResponse(BaseModel):
    """Comprehensive response with interpreted intent, verified titles, and grounded explanations."""
    query: str
    interpreted_intent: ParsedRecommendationIntent
    recommendations: List[RecommendedTitleModel] = Field(default_factory=list)
    presentation_sections: Optional[Dict[str, List[RecommendedTitleModel]]] = Field(default=None, description="Organized presentation groupings e.g. Best Matches, Hidden Gems, etc.")
    total_candidates_analyzed: int = 0
    ai_available: bool = True
    model_used: Optional[str] = None
    history_id: Optional[str] = None
    diagnostics: Optional[Dict[str, Any]] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


# =============================================================================
# Phase 11: Streaming Availability Models (JustWatch via TMDB)
# =============================================================================


class WatchProviderItem(BaseModel):
    """Streaming, rental, or purchase provider metadata."""
    provider_id: int
    provider_name: str
    logo_path: Optional[str] = None
    logo_url: Optional[str] = None
    display_priority: int = 0


class WatchProvidersModel(BaseModel):
    """Regional streaming availability information."""
    id: int
    region: str = "IN"
    tmdb_link: Optional[str] = None
    flatrate: List[WatchProviderItem] = Field(default_factory=list, description="Subscription streaming (e.g. Netflix, Hotstar)")
    rent: List[WatchProviderItem] = Field(default_factory=list, description="Digital rental (e.g. Google TV, Apple TV)")
    buy: List[WatchProviderItem] = Field(default_factory=list, description="Digital purchase")
    attribution: str = "Streaming availability data provided by JustWatch via TMDB."


class WatchProviderConfigItem(BaseModel):
    """Configuration item for a streaming search URL template."""
    key: str
    label: str
    template: str
    default_template: str
    is_custom: bool = False
    description: str = ""
    sample_preview: Optional[str] = None


class WatchProviderTemplatesResponse(BaseModel):
    """Response containing all available watch provider templates."""
    providers: List[WatchProviderConfigItem]
    sample_title: str = "Law & Order: Special Victims Unit"
    custom_count: int = 0


class UpdateWatchProviderTemplatesRequest(BaseModel):
    """Request to update one or more streaming provider templates."""
    templates: Dict[str, str] = Field(..., description="Mapping of provider key -> custom URL template")


class ResolveWatchProviderUrlResponse(BaseModel):
    """Resolved URL for a specific provider and movie title."""
    provider: str
    title: str
    url: str


# =============================================================================
# Movie Hub: AI Search History Models
# =============================================================================


class AISearchHistoryItemModel(BaseModel):
    """A recorded AI recommendation search query."""
    id: str
    query: str
    timestamp: int
    created_at: str


class AddAISearchHistoryRequest(BaseModel):
    """Payload to record an AI search query."""
    query: str


# =============================================================================
# Movie Hub: User-Managed TMDB API Key Models
# =============================================================================


class TMDBKeyHistoryItem(BaseModel):
    id: str
    masked_key: str
    label: str
    source: str = "custom"
    created_at: str = ""
    last_used_at: str = ""
    is_active: bool = False


class TMDBKeyStatusResponse(BaseModel):
    configured: bool
    source: str = "none"  # "custom" | "env" | "none"
    active_key_id: str = ""
    masked_key: str = ""
    has_env_fallback: bool = False
    env_masked_key: str = ""
    history: List[TMDBKeyHistoryItem] = Field(default_factory=list)


class TMDBTestKeyRequest(BaseModel):
    api_key: Optional[str] = None
    key_id: Optional[str] = None


class TMDBTestKeyResponse(BaseModel):
    valid: bool
    status_code: int = 200
    message: str


class TMDBSaveKeyRequest(BaseModel):
    api_key: str
    label: Optional[str] = None


class TMDBActivateKeyRequest(BaseModel):
    key_id: str


# =============================================================================
# HDHub4u URL Template and Mirror Configuration Models
# =============================================================================


class HDHub4uHistoryItem(BaseModel):
    id: str
    url_template: str
    label: str
    is_active: bool
    created_at: float
    last_status: str = "valid"


class HDHub4uStatusResponse(BaseModel):
    active_url: str
    default_url: str
    is_custom: bool
    active_id: str
    history: List[HDHub4uHistoryItem] = Field(default_factory=list)


class HDHub4uTestUrlRequest(BaseModel):
    url: Optional[str] = None
    item_id: Optional[str] = None
    sample_title: Optional[str] = "Pixels"


class HDHub4uTestUrlResponse(BaseModel):
    valid: bool
    status_code: int = 200
    message: str
    preview_url: str = ""


class HDHub4uSaveUrlRequest(BaseModel):
    url: str
    label: Optional[str] = None


class HDHub4uActivateUrlRequest(BaseModel):
    id: str




