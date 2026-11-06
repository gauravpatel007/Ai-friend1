"""FastAPI REST Router for Movie Hub endpoints (/api/movies/*)."""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from app.api.movie_cache_manager import MovieCacheManager

from app.api.movie_models import (
    AddAISearchHistoryRequest,
    AISearchHistoryItemModel,
    AddToWatchlistRequest,
    MarkWatchedRequest,
    MediaDetailsModel,
    MovieFeedbackModel,
    MovieFeedbackRequest,
    MovieUserPreferences,
    PagedResultModel,
    ParsedRecommendationIntent,
    PreferencesUpdateRequest,
    RecommendationRequest,
    RecommendationResponse,
    RecommendedTitleModel,
    UserMovieProfile,
    SetFavoriteRequest,
    SetRatingRequest,
    TMDBActivateKeyRequest,
    TMDBConfigStatus,
    TMDBKeyStatusResponse,
    TMDBSaveKeyRequest,
    TMDBTestKeyRequest,
    TMDBTestKeyResponse,
    HDHub4uActivateUrlRequest,
    HDHub4uHistoryItem,
    HDHub4uSaveUrlRequest,
    HDHub4uStatusResponse,
    HDHub4uTestUrlRequest,
    HDHub4uTestUrlResponse,
    UpdateEntryStatusRequest,
    UserMediaEntry,
    WatchProvidersModel,
    WatchProviderConfigItem,
    WatchProviderTemplatesResponse,
    UpdateWatchProviderTemplatesRequest,
    ResolveWatchProviderUrlResponse,
)
from app.api.tmdb_client import (
    TMDBAuthError,
    TMDBClient,
    TMDBError,
    TMDBNetworkError,
    TMDBNotFoundError,
    TMDBRateLimitError,
    TMDBTimeoutError,
    TMDB_IMAGE_BASE_URL,
)
from app.api.tmdb_credential_manager import TMDBCredentialManager
from app.api.hdhub4u_manager import HDHub4uManager
from app.api.watch_providers_manager import WatchProvidersManager, get_watch_providers_manager
from app.api.websocket import ws_manager
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.memory.movie_storage_repository import MovieStorageRepository
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/movies", tags=["movies"])


def get_movie_cache(request: Request) -> MovieCacheManager:
    """Dependency provider for MovieCacheManager instance attached to app state."""
    cache: Optional[MovieCacheManager] = getattr(request.app.state, "movie_cache", None)
    if cache is None:
        db_mgr = getattr(request.app.state, "db_manager", None)
        if db_mgr is None:
            from app.memory.database import DatabaseManager
            db_mgr = DatabaseManager()
            request.app.state.db_manager = db_mgr
        cache = MovieCacheManager(db_manager=db_mgr)
        request.app.state.movie_cache = cache
    return cache


def get_tmdb_key_manager(request: Request) -> TMDBCredentialManager:
    """Dependency provider for TMDBCredentialManager attached to app state."""
    mgr: Optional[TMDBCredentialManager] = getattr(request.app.state, "tmdb_key_manager", None)
    if mgr is None:
        cfg: Optional[ConfigManager] = getattr(request.app.state, "config_manager", None)
        mgr = TMDBCredentialManager(config_manager=cfg)
        request.app.state.tmdb_key_manager = mgr
    return mgr


def get_hdhub4u_manager(request: Request) -> HDHub4uManager:
    """Dependency provider for HDHub4uManager attached to app state."""
    mgr: Optional[HDHub4uManager] = getattr(request.app.state, "hdhub4u_manager", None)
    if mgr is None:
        cfg: Optional[ConfigManager] = getattr(request.app.state, "config_manager", None)
        mgr = HDHub4uManager(config_manager=cfg)
        request.app.state.hdhub4u_manager = mgr
    return mgr


def get_watch_manager(request: Request) -> WatchProvidersManager:
    """Dependency provider for WatchProvidersManager attached to app state."""
    mgr: Optional[WatchProvidersManager] = getattr(request.app.state, "watch_providers_manager", None)
    if mgr is None:
        mgr = get_watch_providers_manager()
        request.app.state.watch_providers_manager = mgr
    return mgr


def get_tmdb_client(request: Request) -> TMDBClient:
    """Dependency provider for TMDBClient instance attached to app state."""
    client: Optional[TMDBClient] = getattr(request.app.state, "tmdb_client", None)
    cache = get_movie_cache(request)
    key_mgr = get_tmdb_key_manager(request)
    active_key, source, _ = key_mgr.get_active_api_key()

    if client is None:
        client = TMDBClient(api_key=active_key or None, cache_manager=cache)
        request.app.state.tmdb_client = client
    else:
        # Keep client's API key synchronized with active credential manager state
        if active_key and client.api_key != active_key:
            client.set_api_key(active_key)
        elif not active_key and not client.is_configured():
            pass
        if client.cache_manager is None:
            client.cache_manager = cache
    return client


def get_movie_storage(request: Request) -> MovieStorageRepository:
    """Dependency provider for MovieStorageRepository attached to app state."""
    repo: Optional[MovieStorageRepository] = getattr(request.app.state, "movie_repo", None)
    if repo is None:
        db_mgr = getattr(request.app.state, "db_manager", None)
        repo = MovieStorageRepository(db_manager=db_mgr)
        request.app.state.movie_repo = repo
    return repo


def get_recommendation_engine(request: Request) -> MovieRecommendationEngine:
    """Dependency provider for MovieRecommendationEngine reusing existing AI and TMDB services."""
    engine: Optional[MovieRecommendationEngine] = getattr(request.app.state, "movie_rec_engine", None)
    if engine is None:
        tmdb = get_tmdb_client(request)
        storage = get_movie_storage(request)
        ai_service = getattr(request.app.state, "ai_service", None)
        ollama_client = getattr(ai_service, "client", None) if ai_service else None
        cfg: Optional[ConfigManager] = getattr(request.app.state, "config_manager", None)
        active_model = "llama3.2:3b"
        if cfg:
            active_model = cfg.get("movies.recommendation_model", cfg.get("ai.model", "llama3.2:3b"))
        elif ai_service and hasattr(ai_service, "model_manager") and ai_service.model_manager:
            active_model = ai_service.model_manager.active_model

        engine = MovieRecommendationEngine(
            tmdb_client=tmdb,
            storage_repo=storage,
            ollama_client=ollama_client,
            default_model=active_model,
        )
        request.app.state.movie_rec_engine = engine
    return engine


def _translate_error(e: Exception) -> HTTPException:
    """Normalize internal TMDB exceptions to standard HTTP error codes."""
    if isinstance(e, TMDBAuthError):
        return HTTPException(status_code=401, detail=str(e))
    if isinstance(e, TMDBNotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, TMDBRateLimitError):
        return HTTPException(status_code=429, detail=str(e))
    if isinstance(e, TMDBTimeoutError):
        return HTTPException(status_code=504, detail=str(e))
    if isinstance(e, TMDBNetworkError):
        return HTTPException(status_code=503, detail=str(e))
    if isinstance(e, TMDBError):
        return HTTPException(status_code=502, detail=str(e))
    return HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.get("/config", response_model=TMDBConfigStatus)
async def get_movie_config(client: TMDBClient = Depends(get_tmdb_client)) -> TMDBConfigStatus:
    """Check whether TMDB integration is configured with an active API key."""
    return TMDBConfigStatus(
        configured=client.is_configured(),
        image_base_url=f"{TMDB_IMAGE_BASE_URL}/w500",
    )


# =============================================================================
# User-Managed TMDB API Key Endpoints
# =============================================================================


@router.get("/tmdb/key-status", response_model=TMDBKeyStatusResponse)
async def get_tmdb_key_status(
    key_mgr: TMDBCredentialManager = Depends(get_tmdb_key_manager),
) -> TMDBKeyStatusResponse:
    """Get non-sensitive status and history of configured TMDB API keys."""
    return TMDBKeyStatusResponse(**key_mgr.get_key_status())


@router.post("/tmdb/test-key", response_model=TMDBTestKeyResponse)
async def test_tmdb_key(
    req: TMDBTestKeyRequest = Body(...),
    key_mgr: TMDBCredentialManager = Depends(get_tmdb_key_manager),
) -> TMDBTestKeyResponse:
    """Test candidate or currently active TMDB API key against TMDB API."""
    key_to_test = (req.api_key or "").strip()
    if not key_to_test:
        if req.key_id:
            if req.key_id == "env":
                key_to_test = key_mgr.get_env_fallback_key()
            else:
                with key_mgr._lock:
                    cipher = key_mgr._cached_secrets.get(req.key_id)
                if cipher:
                    try:
                        key_to_test = key_mgr._decrypt(cipher)
                    except Exception:
                        pass
        else:
            active_key, _, _ = key_mgr.get_active_api_key()
            key_to_test = active_key

    if not key_to_test:
        return TMDBTestKeyResponse(
            valid=False,
            status_code=400,
            message="No API key provided or found to test.",
        )

    valid, msg, status_code = key_mgr.validate_key_against_tmdb(key_to_test)
    return TMDBTestKeyResponse(
        valid=valid,
        status_code=status_code,
        message=msg,
    )


@router.post("/tmdb/save-key", response_model=TMDBKeyStatusResponse)
async def save_tmdb_key(
    req: TMDBSaveKeyRequest = Body(...),
    key_mgr: TMDBCredentialManager = Depends(get_tmdb_key_manager),
    client: TMDBClient = Depends(get_tmdb_client),
) -> TMDBKeyStatusResponse:
    """Validate, encrypt, save to history, and activate a new TMDB API key."""
    success, msg, status_data = key_mgr.save_and_activate_key(req.api_key, label=req.label)
    if not success:
        # If the new key is invalid, show error and retain previously active key
        raise HTTPException(status_code=400, detail=msg)

    # Immediately activate on client
    active_key, _, _ = key_mgr.get_active_api_key()
    if active_key:
        client.set_api_key(active_key)

    # Broadcast real-time websocket event
    ws_manager.broadcast_sync("tmdb_key_updated", status_data)
    return TMDBKeyStatusResponse(**status_data)


@router.post("/tmdb/activate-key", response_model=TMDBKeyStatusResponse)
async def activate_tmdb_key(
    req: TMDBActivateKeyRequest = Body(...),
    key_mgr: TMDBCredentialManager = Depends(get_tmdb_key_manager),
    client: TMDBClient = Depends(get_tmdb_client),
) -> TMDBKeyStatusResponse:
    """Switch active key to a saved key or .env fallback."""
    success, msg, status_data = key_mgr.activate_key_by_id(req.key_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    active_key, _, _ = key_mgr.get_active_api_key()
    if active_key:
        client.set_api_key(active_key)

    ws_manager.broadcast_sync("tmdb_key_updated", status_data)
    return TMDBKeyStatusResponse(**status_data)


@router.delete("/tmdb/history/{key_id}", response_model=TMDBKeyStatusResponse)
async def delete_tmdb_key_history(
    key_id: str,
    key_mgr: TMDBCredentialManager = Depends(get_tmdb_key_manager),
    client: TMDBClient = Depends(get_tmdb_client),
) -> TMDBKeyStatusResponse:
    """Remove a previously saved key from secure storage and history."""
    success, msg, status_data = key_mgr.delete_key_by_id(key_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    active_key, _, _ = key_mgr.get_active_api_key()
    client.set_api_key(active_key or "")

    ws_manager.broadcast_sync("tmdb_key_updated", status_data)
    return TMDBKeyStatusResponse(**status_data)


# =============================================================================
# HDHub4u Dynamic Search URL & Mirror Configuration Endpoints
# =============================================================================


@router.get("/hdhub4u/status", response_model=HDHub4uStatusResponse)
async def get_hdhub4u_status(
    mgr: HDHub4uManager = Depends(get_hdhub4u_manager),
) -> HDHub4uStatusResponse:
    """Retrieve active HDHub4u search URL template and mirror history."""
    return HDHub4uStatusResponse(**mgr.get_status())


@router.post("/hdhub4u/test-url", response_model=HDHub4uTestUrlResponse)
async def test_hdhub4u_url(
    req: HDHub4uTestUrlRequest = Body(...),
    mgr: HDHub4uManager = Depends(get_hdhub4u_manager),
) -> HDHub4uTestUrlResponse:
    """Validate candidate URL format, perform reachability probe, and preview substitution."""
    url_to_test = (req.url or "").strip()
    if not url_to_test:
        if req.item_id:
            status = mgr.get_status()
            target = next((item for item in status["history"] if item["id"] == req.item_id), None)
            if target:
                url_to_test = target["url_template"]
        if not url_to_test:
            url_to_test = mgr.get_status()["active_url"]

    valid, msg, code, preview = mgr.validate_and_test_url(
        url_to_test, sample_title=req.sample_title or "Pixels"
    )
    return HDHub4uTestUrlResponse(
        valid=valid,
        status_code=code,
        message=msg,
        preview_url=preview,
    )


@router.post("/hdhub4u/save-url", response_model=HDHub4uStatusResponse)
async def save_hdhub4u_url(
    req: HDHub4uSaveUrlRequest = Body(...),
    mgr: HDHub4uManager = Depends(get_hdhub4u_manager),
) -> HDHub4uStatusResponse:
    """Validate, save into mirror history, and activate a new HDHub4u template."""
    success, msg, status_data = mgr.save_and_activate_url(req.url, label=req.label)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    ws_manager.broadcast_sync("hdhub4u_url_updated", status_data)
    return HDHub4uStatusResponse(**status_data)


@router.post("/hdhub4u/activate-url", response_model=HDHub4uStatusResponse)
async def activate_hdhub4u_url(
    req: HDHub4uActivateUrlRequest = Body(...),
    mgr: HDHub4uManager = Depends(get_hdhub4u_manager),
) -> HDHub4uStatusResponse:
    """Switch active HDHub4u template to a saved mirror or 'default'."""
    success, msg, status_data = mgr.activate_url_by_id(req.id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    ws_manager.broadcast_sync("hdhub4u_url_updated", status_data)
    return HDHub4uStatusResponse(**status_data)


@router.delete("/hdhub4u/history/{item_id}", response_model=HDHub4uStatusResponse)
async def delete_hdhub4u_history(
    item_id: str,
    mgr: HDHub4uManager = Depends(get_hdhub4u_manager),
) -> HDHub4uStatusResponse:
    """Remove a previously saved mirror from HDHub4u history."""
    success, msg, status_data = mgr.delete_history_item(item_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    ws_manager.broadcast_sync("hdhub4u_url_updated", status_data)
    return HDHub4uStatusResponse(**status_data)


@router.post("/hdhub4u/reset", response_model=HDHub4uStatusResponse)
async def reset_hdhub4u_url(
    mgr: HDHub4uManager = Depends(get_hdhub4u_manager),
) -> HDHub4uStatusResponse:
    """Reset HDHub4u URL to default template."""
    success, msg, status_data = mgr.reset_to_default()
    ws_manager.broadcast_sync("hdhub4u_url_updated", status_data)
    return HDHub4uStatusResponse(**status_data)


@router.get("/hdhub4u/search-url")
async def resolve_hdhub4u_search_url(
    title: str = Query(..., description="Movie or series title to format"),
    mgr: HDHub4uManager = Depends(get_hdhub4u_manager),
) -> Dict[str, str]:
    """Dynamically resolve any movie or series title to the final search URL."""
    resolved = mgr.build_search_url(title)
    return {"title": title, "url": resolved}


# =============================================================================
# Where to Watch - Streaming Provider Search URL Endpoints
# =============================================================================


@router.get("/watch-providers/templates", response_model=WatchProviderTemplatesResponse)
async def get_watch_provider_templates(
    sample_title: str = Query("Law & Order: Special Victims Unit", description="Sample movie/show title for preview generation"),
    mgr: WatchProvidersManager = Depends(get_watch_manager),
) -> WatchProviderTemplatesResponse:
    """Retrieve all streaming provider search URL templates with live previews."""
    templates = mgr.get_all_templates(sample_title=sample_title)
    custom_count = sum(1 for t in templates if t["is_custom"])
    return WatchProviderTemplatesResponse(
        providers=[WatchProviderConfigItem(**t) for t in templates],
        sample_title=sample_title,
        custom_count=custom_count,
    )


@router.post("/watch-providers/templates", response_model=WatchProviderTemplatesResponse)
async def update_watch_provider_templates(
    req: UpdateWatchProviderTemplatesRequest = Body(...),
    mgr: WatchProvidersManager = Depends(get_watch_manager),
) -> WatchProviderTemplatesResponse:
    """Save or update custom search templates for streaming platforms."""
    mgr.update_multiple_templates(req.templates)
    templates = mgr.get_all_templates()
    custom_count = sum(1 for t in templates if t["is_custom"])
    ws_manager.broadcast_sync("watch_providers_updated", {"custom_count": custom_count})
    return WatchProviderTemplatesResponse(
        providers=[WatchProviderConfigItem(**t) for t in templates],
        custom_count=custom_count,
    )


@router.post("/watch-providers/templates/reset", response_model=WatchProviderTemplatesResponse)
async def reset_watch_provider_templates(
    mgr: WatchProvidersManager = Depends(get_watch_manager),
) -> WatchProviderTemplatesResponse:
    """Reset all streaming search templates to system defaults."""
    mgr.reset_to_defaults()
    templates = mgr.get_all_templates()
    ws_manager.broadcast_sync("watch_providers_updated", {"custom_count": 0})
    return WatchProviderTemplatesResponse(
        providers=[WatchProviderConfigItem(**t) for t in templates],
        custom_count=0,
    )


@router.get("/watch-providers/resolve", response_model=ResolveWatchProviderUrlResponse)
async def resolve_watch_provider_url(
    provider: str = Query(..., description="Provider name e.g. 'Hotstar', 'Netflix', 'Prime Video'"),
    title: str = Query(..., description="Movie or series title e.g. 'Law & Order: Special Victims Unit'"),
    mgr: WatchProvidersManager = Depends(get_watch_manager),
) -> ResolveWatchProviderUrlResponse:
    """Resolve a streaming provider URL with dynamic movie title substitution."""
    resolved = mgr.resolve_url(provider_name=provider, media_title=title)
    return ResolveWatchProviderUrlResponse(
        provider=provider,
        title=title,
        url=resolved,
    )


@router.get("/discover", response_model=PagedResultModel)
async def discover_media(
    content_type: str = Query("all", description="'all', 'movies', or 'series'"),
    region: str = Query("all", description="Regional classification ('all', 'indian', 'bollywood', 'south_indian', 'hollywood', 'international')"),
    language: str = Query("all", description="Language code (e.g. 'hi', 'te', 'ta', 'ml', 'kn', 'bn', 'mr', 'pa', 'en')"),
    genre: str = Query("all", description="TMDB genre id string or comma/pipe separated ids"),
    year: str = Query("all", description="Release year or decade ('2024', '2020s', '2010s', '2000s', 'classic')"),
    sort_by: str = Query("popularity.desc", description="Sorting option"),
    page: int = Query(1, ge=1, le=500),
    page_size: int = Query(49, ge=1, le=100, description="Number of results per page (default: 49)"),
    client: TMDBClient = Depends(get_tmdb_client),
) -> PagedResultModel:
    """Discover movies or television series matching selected content and regional criteria.
    
    Applies multi-signal classification combining origin country and ISO 639-1 language
    families to reliably differentiate Indian regional cinema (Bollywood, Tollywood,
    Kollywood, Mollywood, Sandalwood), Hollywood, and International cinema.
    """
    try:
        # 1. Multi-signal Regional & Language Resolution
        resolved_country: Optional[str] = None
        resolved_lang: Optional[str] = None
        without_lang: Optional[str] = None

        if region == "indian":
            resolved_country = "IN"
            resolved_lang = "hi|te|ta|ml|kn|bn|mr|pa|gu|or|as"
        elif region == "bollywood":
            resolved_country = "IN"
            resolved_lang = "hi"
        elif region == "south_indian":
            resolved_country = "IN"
            resolved_lang = "te|ta|ml|kn"
        elif region == "hollywood":
            resolved_country = "US"
            resolved_lang = "en"
        elif region == "international":
            without_lang = "en"

        # Explicit user language filter takes precedence over regional default languages
        if language != "all":
            resolved_lang = language
            without_lang = None

        # 2. Resolve genre signal (supports single or multi-genre string)
        resolved_genre = genre if genre != "all" else None

        # 3. Resolve year and decade ranges
        resolved_year: Optional[int] = None
        date_gte: Optional[str] = None
        date_lte: Optional[str] = None

        if year != "all":
            if re.match(r"^\d{4}$", year):
                resolved_year = int(year)
            elif year == "2020s":
                date_gte = "2020-01-01"
                date_lte = "2029-12-31"
            elif year == "2010s":
                date_gte = "2010-01-01"
                date_lte = "2019-12-31"
            elif year == "2000s":
                date_gte = "2000-01-01"
                date_lte = "2009-12-31"
            elif year == "classic":
                date_lte = "1999-12-31"

        # 4. Dispatch based on content_type
        if content_type == "series":
            return client.discover_series(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                with_original_language=resolved_lang,
                without_original_language=without_lang,
                with_origin_country=resolved_country,
                with_genres=resolved_genre,
                first_air_date_year=resolved_year,
                release_date_gte=date_gte,
                release_date_lte=date_lte,
            )
        elif content_type == "movies":
            return client.discover_movies(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                with_original_language=resolved_lang,
                without_original_language=without_lang,
                with_origin_country=resolved_country,
                with_genres=resolved_genre,
                primary_release_year=resolved_year,
                release_date_gte=date_gte,
                release_date_lte=date_lte,
            )
        else:
            # Combined 'all': Retrieve both movies and series interleaved/sorted
            return client.discover_all(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                with_original_language=resolved_lang,
                without_original_language=without_lang,
                with_origin_country=resolved_country,
                with_genres=resolved_genre,
                year=resolved_year,
                release_date_gte=date_gte,
                release_date_lte=date_lte,
            )

    except Exception as e:
        raise _translate_error(e)


@router.get("/search", response_model=PagedResultModel)
async def search_media(
    query: str = Query(..., min_length=1, description="Search term for title or person"),
    content_type: str = Query("all", description="'all', 'movies', or 'series'"),
    language: str = Query("all", description="Optional language filter"),
    year: str = Query("all", description="Optional release year filter"),
    page: int = Query(1, ge=1, le=500),
    page_size: int = Query(49, ge=1, le=100, description="Number of results per page (default: 49)"),
    client: TMDBClient = Depends(get_tmdb_client),
) -> PagedResultModel:
    """Search titles or people matching query across movies, TV series, or combined catalog.
    
    Supports Person Search (extracting known_for filmography) and combining search with
    compatible language and year filters.
    """
    try:
        resolved_year: Optional[int] = int(year) if (year != "all" and re.match(r"^\d{4}$", year)) else None
        resolved_lang: Optional[str] = language if language != "all" else None

        if content_type == "movies":
            return client.search_movies(
                query=query,
                page=page,
                page_size=page_size,
                language=resolved_lang,
                primary_release_year=resolved_year,
            )
        elif content_type == "series":
            return client.search_series(
                query=query,
                page=page,
                page_size=page_size,
                language=resolved_lang,
                first_air_date_year=resolved_year,
            )
        else:
            return client.search_multi(
                query=query,
                page=page,
                page_size=page_size,
                language=resolved_lang,
                year=resolved_year,
            )
    except Exception as e:
        raise _translate_error(e)


@router.get("/genres")
async def get_genres(
    content_type: str = Query("movie", description="'movie' or 'tv'"),
    client: TMDBClient = Depends(get_tmdb_client),
) -> Dict[str, Any]:
    """Retrieve official genre taxonomy for movies or television series."""
    try:
        genres = client.get_genres(content_type=content_type)
        return {"content_type": content_type, "genres": [g.model_dump() for g in genres]}
    except Exception as e:
        raise _translate_error(e)


# =============================================================================
# Phase 8: Persistent Local Storage Endpoints (/api/movies/storage/*)
# =============================================================================


@router.get("/storage/summary")
async def get_tracking_summary(
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> Dict[str, Any]:
    """Retrieve quick lookup summary of tracked IDs (watchlist, favorites, watched, ratings)."""
    return storage.get_tracking_summary()


@router.get("/storage/entries", response_model=List[UserMediaEntry])
async def list_stored_entries(
    status: Optional[str] = Query("all", description="'all', 'watchlist', 'watching', 'watched', 'dropped', 'none'"),
    media_type: Optional[str] = Query("all", description="'all', 'movie', 'tv'"),
    is_favorite: Optional[bool] = Query(None, description="Filter for favorites"),
    min_rating: Optional[int] = Query(None, ge=1, le=10, description="Minimum local rating"),
    sort_by: str = Query("updated_at", description="'updated_at', 'created_at', 'title', 'user_rating'"),
    desc: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> List[UserMediaEntry]:
    """List all stored user media entries with flexible filtering and sorting."""
    return storage.list_entries(
        status=status if status != "all" else None,
        is_favorite=is_favorite,
        min_rating=min_rating,
        media_type=media_type if media_type != "all" else None,
        sort_by=sort_by,
        desc=desc,
        limit=limit,
        offset=offset,
    )


@router.get("/storage/watchlist", response_model=List[UserMediaEntry])
async def get_watchlist(
    media_type: Optional[str] = Query("all"),
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> List[UserMediaEntry]:
    """Retrieve all titles currently on user's watchlist."""
    return storage.get_watchlist(media_type=media_type if media_type != "all" else None)


@router.post("/storage/watchlist", response_model=UserMediaEntry)
async def add_to_watchlist(
    req: AddToWatchlistRequest,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> UserMediaEntry:
    """Add a movie or series to persistent watchlist with duplicate prevention."""
    try:
        return storage.add_or_update_entry(
            tmdb_id=req.tmdb_id,
            title=req.title,
            media_type=req.media_type,
            poster_path=req.poster_path,
            release_year=req.release_year,
            original_language=req.original_language,
            vote_average=req.vote_average or 0.0,
            overview=req.overview or "",
            status=req.status or "watchlist",
            is_favorite=req.is_favorite,
            user_rating=req.user_rating,
            genres=req.genres,
        )
    except Exception as e:
        logger.error("Failed to add to watchlist: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/storage/watchlist/{media_type}/{item_id}")
async def remove_from_watchlist(
    media_type: str,
    item_id: int,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> Dict[str, Any]:
    """Remove title from watchlist (preserves entry if marked favorite or locally rated)."""
    success = storage.remove_from_watchlist(tmdb_id=item_id, media_type=media_type)
    return {"status": "ok", "removed": success, "tmdb_id": item_id, "media_type": media_type}


@router.post("/storage/watched/{media_type}/{item_id}", response_model=UserMediaEntry)
async def mark_as_watched(
    media_type: str,
    item_id: int,
    req: Optional[MarkWatchedRequest] = Body(default=None),
    storage: MovieStorageRepository = Depends(get_movie_storage),
    request: Request = None,  # type: ignore
) -> UserMediaEntry:
    """Mark a title as watched with timestamp recording, creating entry if not present."""
    meta: Dict[str, Any] = req.model_dump(exclude_unset=True) if req else {}
    entry = storage.get_entry(tmdb_id=item_id, media_type=media_type)
    if not entry and not meta.get("title") and request is not None:
        try:
            client = get_tmdb_client(request)
            if client and client.is_configured():
                details = await client.get_details(media_type, item_id)
                if details:
                    meta["title"] = details.title
                    meta["poster_path"] = details.poster_path
                    meta["poster_url"] = details.poster_url
                    meta["backdrop_path"] = details.backdrop_path
                    meta["backdrop_url"] = details.backdrop_url
                    meta["release_year"] = details.release_year
                    meta["release_date"] = details.release_date
                    meta["vote_average"] = details.vote_average
                    meta["overview"] = details.overview
        except Exception as ex:
            logger.debug("Failed to auto-fetch TMDB details for watched title %s/%s: %s", media_type, item_id, ex)

    return storage.mark_as_watched(tmdb_id=item_id, media_type=media_type, item_metadata=meta)


@router.patch("/storage/status/{media_type}/{item_id}", response_model=UserMediaEntry)
async def update_status(
    media_type: str,
    item_id: int,
    req: UpdateEntryStatusRequest,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> UserMediaEntry:
    """Update title tracking status (watchlist, watching, watched, dropped, none)."""
    entry = storage.update_status(tmdb_id=item_id, media_type=media_type, status=req.status)
    if not entry:
        raise HTTPException(status_code=404, detail="Title not found in tracked storage")
    return entry


@router.get("/storage/favorites", response_model=List[UserMediaEntry])
async def get_favorites(
    media_type: Optional[str] = Query("all"),
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> List[UserMediaEntry]:
    """Retrieve all user favorite titles."""
    return storage.get_favorites(media_type=media_type if media_type != "all" else None)


@router.post("/storage/favorite/{media_type}/{item_id}", response_model=UserMediaEntry)
async def set_favorite(
    media_type: str,
    item_id: int,
    req: SetFavoriteRequest,
    storage: MovieStorageRepository = Depends(get_movie_storage),
    request: Request = None,  # type: ignore
) -> UserMediaEntry:
    """Mark or unmark a title as favorite, creating an entry if not present."""
    meta: Dict[str, Any] = req.model_dump(exclude_unset=True)
    if not meta.get("title") and req.is_favorite and request is not None:
        entry = storage.get_entry(tmdb_id=item_id, media_type=media_type)
        if not entry:
            try:
                client = get_tmdb_client(request)
                if client and client.is_configured():
                    details = await client.get_details(media_type, item_id)
                    if details:
                        meta["title"] = details.title
                        meta["poster_path"] = details.poster_path
                        meta["poster_url"] = details.poster_url
                        meta["backdrop_path"] = details.backdrop_path
                        meta["backdrop_url"] = details.backdrop_url
                        meta["release_year"] = details.release_year
                        meta["release_date"] = details.release_date
                        meta["vote_average"] = details.vote_average
                        meta["overview"] = details.overview
            except Exception as ex:
                logger.debug("Failed to auto-fetch TMDB details for favorite %s/%s: %s", media_type, item_id, ex)

    return storage.set_favorite(
        tmdb_id=item_id,
        media_type=media_type,
        is_favorite=req.is_favorite,
        item_metadata=meta,
    )


@router.post("/storage/rating/{media_type}/{item_id}", response_model=UserMediaEntry)
async def set_rating(
    media_type: str,
    item_id: int,
    req: SetRatingRequest,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> UserMediaEntry:
    """Assign or clear personal local user rating (1-10 integer)."""
    try:
        return storage.set_rating(
            tmdb_id=item_id,
            media_type=media_type,
            rating=req.rating,
            item_metadata=req.model_dump(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/storage/ratings", response_model=List[UserMediaEntry])
async def get_ratings(
    media_type: Optional[str] = Query("all"),
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> List[UserMediaEntry]:
    """Retrieve all titles locally rated by the user."""
    return storage.get_ratings(media_type=media_type if media_type != "all" else None)


@router.get("/storage/entry/{media_type}/{item_id}", response_model=Optional[UserMediaEntry])
async def get_entry_status(
    media_type: str,
    item_id: int,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> Optional[UserMediaEntry]:
    """Get tracked status, favorite flag, and user rating for a specific title."""
    return storage.get_entry(tmdb_id=item_id, media_type=media_type)


@router.delete("/storage/entry/{media_type}/{item_id}")
async def delete_entry(
    media_type: str,
    item_id: int,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> Dict[str, Any]:
    """Completely delete title from tracked storage."""
    deleted = storage.delete_entry(tmdb_id=item_id, media_type=media_type)
    return {"status": "ok", "deleted": deleted}


@router.get("/storage/preferences", response_model=MovieUserPreferences)
async def get_preferences(
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> MovieUserPreferences:
    """Retrieve user entertainment preferences."""
    return storage.get_preferences()


@router.put("/storage/preferences", response_model=MovieUserPreferences)
async def update_preferences(
    req: PreferencesUpdateRequest,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> MovieUserPreferences:
    """Update user entertainment preferences (genres, languages, regions, taste settings)."""
    return storage.update_preferences(
        preferred_genres=req.preferred_genres,
        preferred_languages=req.preferred_languages,
        preferred_regions=req.preferred_regions,
        disliked_genres=req.disliked_genres,
        exclude_watched=req.exclude_watched,
        prefer_underrated=req.prefer_underrated,
        prefer_highly_rated=req.prefer_highly_rated,
        prefer_newer=req.prefer_newer,
        prefer_classic=req.prefer_classic,
        recommendation_settings=req.recommendation_settings,
    )


@router.post("/storage/preferences/reset", response_model=MovieUserPreferences)
async def reset_preferences(
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> MovieUserPreferences:
    """Reset entertainment preferences to clean sensible defaults."""
    return storage.reset_preferences()


@router.get("/storage/profile", response_model=UserMovieProfile)
async def get_user_movie_profile(
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> UserMovieProfile:
    """Retrieve synthesized user taste profile and genre affinities."""
    return storage.build_user_profile()


# =============================================================================
# Movie Hub: Recommendation Feedback Endpoints (/api/movies/feedback/*)
# =============================================================================


@router.get("/feedback", response_model=List[MovieFeedbackModel])
async def get_all_feedback(
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> List[MovieFeedbackModel]:
    """Retrieve all recommendation feedback."""
    rows = storage.get_all_feedback()
    return [MovieFeedbackModel(**r) for r in rows]


@router.post("/feedback", response_model=Dict[str, Any])
async def record_movie_feedback(
    req: MovieFeedbackRequest,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> Dict[str, Any]:
    """Record recommendation feedback ('more_like_this', 'not_interested', 'already_watched', 'not_my_taste')."""
    return storage.record_feedback(
        tmdb_id=req.tmdb_id,
        media_type=req.media_type,
        feedback_type=req.feedback_type,
        title=req.title,
        genres=req.genres,
    )


@router.delete("/feedback/{media_type}/{item_id}")
async def delete_movie_feedback(
    media_type: str,
    item_id: int,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> Dict[str, Any]:
    """Delete feedback for a title."""
    deleted = storage.delete_feedback(tmdb_id=item_id, media_type=media_type)
    return {"status": "ok", "deleted": deleted}


# =============================================================================
# Movie Hub: AI Search History Endpoints (/api/movies/storage/history/*)
# =============================================================================


@router.get("/storage/history", response_model=List[AISearchHistoryItemModel])
async def get_ai_search_history(
    limit: int = Query(50, ge=1, le=100),
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> List[AISearchHistoryItemModel]:
    """Retrieve persistent AI recommendation search history from database."""
    items = storage.get_ai_search_history(limit=limit)
    return [AISearchHistoryItemModel(**item) for item in items]


@router.post("/storage/history", response_model=AISearchHistoryItemModel)
async def add_ai_search_history(
    req: AddAISearchHistoryRequest,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> AISearchHistoryItemModel:
    """Record an AI recommendation search query to database with deduplication."""
    clean_q = (req.query or "").strip()
    if not clean_q:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    item = storage.add_ai_search_history(clean_q)
    return AISearchHistoryItemModel(**item)


@router.delete("/storage/history/{item_id}")
async def delete_ai_search_history_item(
    item_id: str,
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> Dict[str, Any]:
    """Delete an individual search history record from database."""
    deleted = storage.delete_ai_search_history_item(item_id)
    return {"status": "ok", "deleted": deleted, "item_id": item_id}


@router.delete("/storage/history")
async def clear_ai_search_history(
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> Dict[str, Any]:
    """Clear all AI search history records from database."""
    cleared = storage.clear_ai_search_history()
    return {"status": "ok", "cleared": cleared}


# =============================================================================
# Phase 9: AI-Assisted Recommendation Endpoints (/api/movies/recommendations/*)
# =============================================================================


@router.post("/recommendations", response_model=RecommendationResponse)
async def generate_recommendations(
    req: RecommendationRequest,
    engine: MovieRecommendationEngine = Depends(get_recommendation_engine),
    storage: MovieStorageRepository = Depends(get_movie_storage),
) -> RecommendationResponse:
    """Analyze natural-language request, retrieve real TMDB titles, rank, and explain with Ollama."""
    raw_query = req.query or ""
    if not raw_query.strip():
        raise HTTPException(status_code=400, detail="Recommendation query cannot be empty.")

    clean_query = raw_query.strip()

    # Automatically record query to persistent database
    history_record = None
    try:
        history_record = storage.add_ai_search_history(clean_query)
    except Exception as ex:
        logger.debug("Automatic AI search history recording notice: %s", ex)

    try:
        import asyncio
        response = await asyncio.to_thread(
            engine.recommend,
            clean_query,
            req.include_saved_preferences,
            req.limit,
            req.edited_preferences,
            req.removed_preferences,
            req.request_id,
        )
        if history_record and isinstance(history_record, dict) and "id" in history_record:
            response.history_id = history_record["id"]
        return response
    except RuntimeError as re_err:
        if "cancelled" in str(re_err).lower():
            logger.info("[MovieRecommendation] Request was cancelled by user.")
            raise HTTPException(status_code=499, detail="Recommendation generation cancelled.")
        raise HTTPException(status_code=500, detail=str(re_err))
    except Exception as e:
        logger.error("Recommendation generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {e}")


@router.post("/recommendations/cancel")
async def cancel_recommendations(
    engine: MovieRecommendationEngine = Depends(get_recommendation_engine),
) -> Dict[str, Any]:
    """Halt any ongoing AI movie recommendation generation immediately."""
    engine.cancel()
    return {"status": "ok", "cancelled": True}


@router.post("/recommendations/parse", response_model=ParsedRecommendationIntent)
@router.get("/recommendations/parse", response_model=ParsedRecommendationIntent)
async def parse_recommendation_intent(
    query: Optional[str] = Query(None),
    payload: Optional[Dict[str, Any]] = Body(None),
    engine: MovieRecommendationEngine = Depends(get_recommendation_engine),
) -> ParsedRecommendationIntent:
    """Preview structured interpretation of natural-language recommendation prompt."""
    q = query
    if not q and payload:
        q = payload.get("query") or payload.get("prompt")
    if not q or not str(q).strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    return engine.parse_intent_deterministic(str(q).strip())


# =============================================================================
# Phase 10: Caching, Offline Behavior & Image Proxy Endpoints
# =============================================================================


@router.get("/cache/status")
async def get_cache_status(
    cache: MovieCacheManager = Depends(get_movie_cache),
) -> Dict[str, Any]:
    """Retrieve metadata and image cache capacity, occupancy, and metrics."""
    return cache.get_stats()


@router.post("/cache/clear")
async def clear_cache(
    category: Optional[str] = Query(None, description="'search', 'discover', 'movie_details', 'tv_details', 'images', or None for all"),
    cache: MovieCacheManager = Depends(get_movie_cache),
) -> Dict[str, Any]:
    """Invalidate cached metadata or prune image cache on demand."""
    if category == "images":
        pruned = cache.prune_image_cache_if_needed()
        return {"cleared": "images", "pruned_files": pruned}
    else:
        deleted = cache.invalidate_metadata(category=category)
        return {"cleared": category or "all", "deleted_metadata_records": deleted}


@router.get("/network-status")
async def check_network_status(
    client: TMDBClient = Depends(get_tmdb_client),
    cache: MovieCacheManager = Depends(get_movie_cache),
) -> Dict[str, Any]:
    """Probe network connectivity to TMDB and return reachability metrics."""
    start_time = time.time()
    online = False
    error_msg = None

    if client.is_configured():
        try:
            # Low-overhead ping to configuration endpoint with credentials
            resp = client._request("GET", "/configuration")
            online = bool(resp and isinstance(resp, dict))
        except Exception as e:
            online = False
            error_msg = str(e)
    else:
        # Check basic internet reachability to TMDB domain even if key is pending
        try:
            resp = client.session.head("https://api.themoviedb.org", timeout=3.0)
            online = resp.status_code < 500
        except Exception:
            online = False
            error_msg = "No internet connection"

    latency_ms = round((time.time() - start_time) * 1000, 1) if online else None
    cache_stats = cache.get_stats()

    return {
        "online": online,
        "configured": client.is_configured(),
        "latency_ms": latency_ms,
        "error": error_msg,
        "cached_metadata_count": cache_stats["metadata_entries"],
        "cached_images_count": cache_stats["image_files"],
    }


@router.get("/images/{size}/{image_path:path}")
async def get_cached_image(
    size: str,
    image_path: str,
    client: TMDBClient = Depends(get_tmdb_client),
) -> Response:
    """Stream locally cached image or download with bounded LRU eviction and offline fallback."""
    img_bytes, mime_type, is_cached = client.get_or_download_image(image_path, size=size)
    cache_header = "HIT" if is_cached else "MISS"

    return Response(
        content=img_bytes,
        media_type=mime_type,
        headers={
            "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
            "X-Cache": cache_header,
        },
    )


@router.get("/{media_type}/{item_id}/watch-providers", response_model=WatchProvidersModel)
async def get_watch_providers(
    media_type: str,
    item_id: int,
    region: str = Query("IN", description="ISO 3166-1 two-letter country code, default IN"),
    client: TMDBClient = Depends(get_tmdb_client),
) -> WatchProvidersModel:
    """Retrieve legitimate streaming, rental, and buy options powered by JustWatch via TMDB."""
    try:
        norm_type = "tv" if media_type.lower() in ("tv", "series") else "movie"
        return client.get_watch_providers(media_type=norm_type, item_id=item_id, region=region)
    except Exception as e:
        raise _translate_error(e)


@router.get("/{media_type}/{item_id}", response_model=MediaDetailsModel)
async def get_media_details(
    media_type: str,
    item_id: int,
    client: TMDBClient = Depends(get_tmdb_client),
) -> MediaDetailsModel:
    """Retrieve detailed metadata, credits, trailers, and similar recommendations."""
    try:
        norm_type = "tv" if media_type.lower() in ("tv", "series") else "movie"
        if norm_type == "tv":
            return client.get_series_details(series_id=item_id)
        else:
            return client.get_movie_details(movie_id=item_id)
    except Exception as e:
        raise _translate_error(e)
