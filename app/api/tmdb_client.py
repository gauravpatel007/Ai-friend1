"""TMDB API Integration Client for Movie Hub.

Provides authenticated requests, parameter validation, rate limiting protection,
timeout handling, response normalization, and graceful error handling.
"""

from __future__ import annotations

import os
import re
import math
from typing import Any, Dict, List, Optional, Tuple
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.api.movie_models import (
    CastMemberModel,
    CrewMemberModel,
    GenreModel,
    MediaDetailsModel,
    MediaItemSummary,
    PagedResultModel,
    VideoModel,
    WatchProviderItem,
    WatchProvidersModel,
)
from app.api.movie_cache_manager import MovieCacheManager, FALLBACK_POSTER_SVG
from app.utils.logger import get_logger

logger = get_logger(__name__)

TMDB_API_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
DEFAULT_TIMEOUT_SEC = 10.0

TMDB_GENRE_MAP: Dict[int, str] = {
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
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
    10759: "Action & Adventure",
    10762: "Kids",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics",
}


# Custom TMDB Exceptions
class TMDBError(Exception):
    """Base exception for all TMDB API errors."""
    pass


class TMDBAuthError(TMDBError):
    """Raised when authentication credentials are missing or invalid."""
    pass


class TMDBNotFoundError(TMDBError):
    """Raised when a requested resource was not found."""
    pass


class TMDBRateLimitError(TMDBError):
    """Raised when TMDB rate limit (HTTP 429) is encountered."""
    pass


class TMDBTimeoutError(TMDBError):
    """Raised when an API request times out."""
    pass


class TMDBNetworkError(TMDBError):
    """Raised on connection drops, DNS failures, or socket errors."""
    pass


class TMDBClient:
    """Dedicated HTTP client for The Movie Database (TMDB) API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SEC,
        session: Optional[requests.Session] = None,
        cache_manager: Optional[MovieCacheManager] = None,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key.strip()
        else:
            self.api_key = os.environ.get("TMDB_API_KEY", "").strip()
        self.timeout = timeout
        self.session = session or requests.Session()
        self.cache_manager = cache_manager

    def set_api_key(self, key: str) -> None:
        """Update or configure the TMDB API key."""
        self.api_key = (key or "").strip()

    def is_configured(self) -> bool:
        """Return True if an API credential is configured."""
        return bool(self.api_key)

    def ping(self) -> bool:
        """Verify reachability and authentication to TMDB API."""
        if not self.is_configured():
            return False
        try:
            resp = self._request("GET", "/configuration")
            return bool(resp and isinstance(resp, dict))
        except Exception:
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Construct secure headers without exposing secrets in logs."""
        headers = {
            "Accept": "application/json",
            "User-Agent": "AIDesktopFriend-MovieHub/2.0",
        }
        if self.api_key:
            # If the token is a v4 Bearer token (JWT) or long key
            if self.api_key.startswith("ey") or len(self.api_key) > 40:
                headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _prepare_params(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Prepare request parameters with v3 API key fallback if needed."""
        clean_params = dict(params or {})
        # If API key is a standard 32-character v3 key, supply as query parameter
        if self.api_key and not self.api_key.startswith("ey") and len(self.api_key) <= 40:
            clean_params["api_key"] = self.api_key
        return clean_params

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an HTTP request with error normalization and timeouts."""
        if not self.is_configured():
            raise TMDBAuthError(
                "TMDB API key is not configured. Please configure your key in settings or TMDB_API_KEY env."
            )

        url = f"{TMDB_API_BASE_URL}{path}"
        headers = self._get_headers()
        clean_params = self._prepare_params(params)

        try:
            resp = self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=clean_params,
                timeout=self.timeout,
            )
        except requests.Timeout as e:
            logger.warning("TMDB request timed out for %s", path)
            raise TMDBTimeoutError(f"Request to TMDB timed out after {self.timeout}s.") from e
        except requests.RequestException as e:
            logger.warning("TMDB network connection error for %s: %s", path, e)
            raise TMDBNetworkError(f"Network error connecting to TMDB: {e}") from e

        # Normalize HTTP error codes
        if resp.status_code == 401:
            raise TMDBAuthError("Invalid or unauthorized TMDB API key.")
        if resp.status_code == 404:
            raise TMDBNotFoundError(f"Resource {path} not found on TMDB.")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "10")
            raise TMDBRateLimitError(f"TMDB rate limit exceeded. Retry after {retry_after}s.")
        if not resp.ok:
            raise TMDBError(f"TMDB API error ({resp.status_code}): {resp.text}")

        try:
            return resp.json()
        except ValueError as e:
            raise TMDBError(f"Malformed JSON response received from TMDB: {e}") from e

    def _build_cache_key(self, path: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Construct canonical deterministic cache key for a request."""
        clean = self._prepare_params(params)
        clean.pop("api_key", None)
        sorted_items = sorted((str(k), str(v)) for k, v in clean.items() if v is not None)
        query_str = "&".join(f"{k}={v}" for k, v in sorted_items)
        return f"{path}?{query_str}" if query_str else path

    def _request_cached(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        category: str = "default",
        bypass_cache: bool = False,
    ) -> Dict[str, Any]:
        """Execute request with two-tier caching and offline stale fallback."""
        cache_key = self._build_cache_key(path, params)

        if self.cache_manager and not bypass_cache and method.upper() == "GET":
            cached, is_stale = self.cache_manager.get_metadata(cache_key, allow_stale=False)
            if cached is not None:
                logger.debug("TMDB Cache HIT (%s): %s", category, cache_key)
                return cached

        try:
            data = self._request(method, path, params=params)
            if self.cache_manager and method.upper() == "GET":
                self.cache_manager.set_metadata(cache_key, category, data)
            return data
        except (TMDBNetworkError, TMDBTimeoutError) as err:
            if self.cache_manager and method.upper() == "GET":
                stale_data, is_stale = self.cache_manager.get_metadata(cache_key, allow_stale=True)
                if stale_data is not None:
                    logger.warning("Serving stale cached response for %s due to network error: %s", path, err)
                    if isinstance(stale_data, dict):
                        stale_data["_is_stale"] = True
                    return stale_data
            raise

    def get_or_download_image(
        self,
        image_path: str,
        size: str = "w500",
    ) -> Tuple[bytes, str, bool]:
        """Retrieve image from disk cache or fetch from TMDB with offline fallback.
        
        Returns:
            (image_bytes, mime_type, is_from_cache)
        """
        if self.cache_manager:
            cached = self.cache_manager.get_image(image_path, size)
            if cached is not None:
                return cached[0], cached[1], True

        # Fetch from TMDB
        clean_path = image_path.lstrip("/")
        url = f"{TMDB_IMAGE_BASE_URL}/{size}/{clean_path}"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.ok and len(resp.content) >= 100:
                mime_type = resp.headers.get("Content-Type", "image/jpeg")
                if self.cache_manager:
                    self.cache_manager.save_image(image_path, size, resp.content)
                return resp.content, mime_type, False
        except Exception as e:
            logger.warning("Failed to download image %s: %s", url, e)

        # Fallback to local offline SVG
        if self.cache_manager:
            return self.cache_manager.get_fallback_poster_svg(), "image/svg+xml", False
        return FALLBACK_POSTER_SVG, "image/svg+xml", False

    # =========================================================================
    # Helpers for Normalizing Media Records
    # =========================================================================

    @staticmethod
    def _construct_image_url(path: Optional[str], size: str = "w500") -> Optional[str]:
        if not path:
            return None
        return f"{TMDB_IMAGE_BASE_URL}/{size}{path}"

    @classmethod
    def _parse_media_summary(
        cls,
        data: Dict[str, Any],
        default_type: str = "movie",
        retrieval_source: Optional[str] = None,
        reference_movie_id: Optional[int] = None,
    ) -> MediaItemSummary:
        media_type = data.get("media_type") or default_type
        # Movie title vs TV name
        title = data.get("title") or data.get("name") or "Untitled"
        original_title = data.get("original_title") or data.get("original_name")
        
        # Movie release_date vs TV first_air_date
        release_date = data.get("release_date") or data.get("first_air_date") or None
        release_year = None
        if release_date and len(release_date) >= 4:
            match = re.match(r"^(\d{4})", release_date)
            if match:
                release_year = int(match.group(1))

        poster_path = data.get("poster_path")
        backdrop_path = data.get("backdrop_path")

        # Resolve genre_names from genre_ids or genres array (Requirement E)
        genre_ids = data.get("genre_ids") or []
        genre_names: List[str] = []
        if data.get("genres"):
            genre_names = [g.get("name") for g in data["genres"] if isinstance(g, dict) and g.get("name")]
        if not genre_names and genre_ids:
            genre_names = [TMDB_GENRE_MAP[gid] for gid in genre_ids if gid in TMDB_GENRE_MAP]

        # Resolve keywords list (Requirement E)
        raw_kws = data.get("keywords") or []
        keywords: List[str] = []
        if isinstance(raw_kws, list):
            for k in raw_kws:
                if isinstance(k, dict) and k.get("name"):
                    keywords.append(str(k["name"]))
                elif isinstance(k, str):
                    keywords.append(k)
        elif isinstance(raw_kws, dict) and "keywords" in raw_kws:
            for k in raw_kws["keywords"]:
                if isinstance(k, dict) and k.get("name"):
                    keywords.append(str(k["name"]))

        # Origin country extraction (supports TV origin_country and Movie production_countries)
        origin_country = None
        raw_countries = data.get("origin_country")
        if isinstance(raw_countries, list):
            origin_country = [str(c).upper() for c in raw_countries if c]
        elif isinstance(raw_countries, str) and raw_countries.strip():
            origin_country = [raw_countries.strip().upper()]

        if not origin_country and data.get("production_countries"):
            prod_c = data.get("production_countries") or []
            origin_country = [
                str(c.get("iso_3166_1")).upper()
                for c in prod_c
                if isinstance(c, dict) and c.get("iso_3166_1")
            ]

        # Known regional language inferral for origin country when TMDB list results omit it
        orig_lang = data.get("original_language")
        if not origin_country and orig_lang in (
            "ml", "hi", "ta", "te", "kn", "bn", "mr", "pa", "gu", "or", "as"
        ):
            origin_country = ["IN"]
        elif not origin_country and orig_lang == "ko":
            origin_country = ["KR"]
        elif not origin_country and orig_lang == "ja":
            origin_country = ["JP"]

        return MediaItemSummary(
            id=int(data.get("id", 0)),
            title=title,
            original_title=original_title,
            media_type=media_type,
            overview=data.get("overview") or "",
            poster_path=poster_path,
            backdrop_path=backdrop_path,
            poster_url=cls._construct_image_url(poster_path, "w500"),
            backdrop_url=cls._construct_image_url(backdrop_path, "w1280"),
            release_date=release_date,
            release_year=release_year,
            original_language=orig_lang,
            origin_country=origin_country or None,
            genre_ids=genre_ids,
            genre_names=genre_names,
            keywords=keywords,
            vote_average=float(data.get("vote_average") or 0.0),
            vote_count=int(data.get("vote_count") or 0),
            popularity=float(data.get("popularity") or 0.0),
            retrieval_source=retrieval_source or data.get("retrieval_source"),
            reference_movie_id=reference_movie_id or data.get("reference_movie_id"),
        )

    # =========================================================================
    # 4.4 Essential Retrieval Operations
    # =========================================================================

    @staticmethod
    def _map_genres_for_tv(genre_str: Optional[str]) -> Optional[str]:
        """Map movie genre IDs to TV genre IDs where TMDB defines separate IDs."""
        if not genre_str:
            return None
        # In TMDB:
        # 28 (Action) -> 10759 (Action & Adventure)
        # 12 (Adventure) -> 10759 (Action & Adventure)
        # 878 (Sci-Fi) -> 10765 (Sci-Fi & Fantasy)
        # 14 (Fantasy) -> 10765 (Sci-Fi & Fantasy)
        tokens = re.split(r"([,|])", genre_str)
        mapped = []
        for tok in tokens:
            if tok in ("28", "12"):
                mapped.append("10759")
            elif tok in ("878", "14"):
                mapped.append("10765")
            else:
                mapped.append(tok)
        return "".join(mapped)

    def _fetch_tmdb_pages(
        self,
        endpoint: str,
        base_params: Dict[str, Any],
        page: int,
        page_size: int = 20,
        category: str = "discover",
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """Fetch and assemble results across multiple TMDB pages to fulfill custom page_size.
        
        Returns (sliced_raw_results, client_total_pages, tmdb_total_results).
        """
        if page_size == 20:
            params = dict(base_params)
            params["page"] = max(1, min(500, page))
            data = self._request_cached("GET", endpoint, params=params, category=category)
            raw = data.get("results") or []
            tmdb_total_pages = int(data.get("total_pages", 1))
            tmdb_total_results = int(data.get("total_results", len(raw)))
            return raw, tmdb_total_pages, tmdb_total_results

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        first_tmdb_page = max(1, min(500, (start_idx // 20) + 1))
        last_tmdb_page = max(1, min(500, ((end_idx - 1) // 20) + 1))
        slice_start = start_idx - (first_tmdb_page - 1) * 20
        slice_end = slice_start + page_size

        all_raw_results: List[Dict[str, Any]] = []
        tmdb_total_results = 0
        tmdb_total_pages = 1

        for tmdb_page in range(first_tmdb_page, last_tmdb_page + 1):
            page_params = dict(base_params)
            page_params["page"] = tmdb_page
            data = self._request_cached("GET", endpoint, params=page_params, category=category)
            page_results = data.get("results") or []
            all_raw_results.extend(page_results)
            tmdb_total_results = max(tmdb_total_results, int(data.get("total_results", 0)))
            tmdb_total_pages = int(data.get("total_pages", 1))

            # Stop early if TMDB has no more items or reached end of catalog
            if len(page_results) < 20 or tmdb_page >= tmdb_total_pages:
                break

        target_raw = all_raw_results[slice_start:slice_end]
        client_total_pages = max(1, math.ceil(tmdb_total_results / page_size)) if tmdb_total_results > 0 else 1
        client_total_pages = min(client_total_pages, max(1, (500 * 20) // page_size))

        return target_raw, client_total_pages, tmdb_total_results

    def discover_movies(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "popularity.desc",
        with_original_language: Optional[str] = None,
        without_original_language: Optional[str] = None,
        with_origin_country: Optional[str] = None,
        with_genres: Optional[str] = None,
        with_keywords: Optional[str] = None,
        primary_release_year: Optional[int] = None,
        release_date_gte: Optional[str] = None,
        release_date_lte: Optional[str] = None,
        vote_count_gte: int = 10,
    ) -> PagedResultModel:
        """Retrieve paginated movies matching filters. Ensures only movies are returned."""
        # Normalize sort_by for movie endpoint (TMDB movie discover uses primary_release_date)
        norm_sort = sort_by
        if "first_air_date" in norm_sort:
            norm_sort = norm_sort.replace("first_air_date", "primary_release_date")
        elif norm_sort == "release_date.desc":
            norm_sort = "primary_release_date.desc"
        elif norm_sort == "release_date.asc":
            norm_sort = "primary_release_date.asc"
        elif norm_sort == "title.asc":
            norm_sort = "original_title.asc"

        params: Dict[str, Any] = {
            "sort_by": norm_sort,
            "vote_count.gte": vote_count_gte,
            "include_adult": False,
        }
        if with_original_language:
            params["with_original_language"] = with_original_language
        if without_original_language:
            params["without_original_language"] = without_original_language
        if with_origin_country:
            params["with_origin_country"] = with_origin_country
        if with_genres:
            params["with_genres"] = with_genres
        if with_keywords:
            params["with_keywords"] = with_keywords
        if primary_release_year:
            params["primary_release_year"] = primary_release_year
        if release_date_gte:
            params["primary_release_date.gte"] = release_date_gte
        if release_date_lte:
            params["primary_release_date.lte"] = release_date_lte

        raw_results, client_total_pages, tmdb_total_results = self._fetch_tmdb_pages(
            "/discover/movie",
            params,
            page=page,
            page_size=page_size,
            category="discover",
        )
        if with_origin_country:
            for item in raw_results:
                if not item.get("origin_country"):
                    item["origin_country"] = [with_origin_country.upper()]

        parsed = [
            self._parse_media_summary(item, default_type="movie")
            for item in raw_results
        ]
        movies_only = [item for item in parsed if item.media_type == "movie"]

        return PagedResultModel(
            page=page,
            total_pages=client_total_pages,
            total_results=tmdb_total_results if tmdb_total_results > 0 else len(movies_only),
            results=movies_only,
        )

    def discover_series(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "popularity.desc",
        with_original_language: Optional[str] = None,
        without_original_language: Optional[str] = None,
        with_origin_country: Optional[str] = None,
        with_genres: Optional[str] = None,
        with_keywords: Optional[str] = None,
        first_air_date_year: Optional[int] = None,
        release_date_gte: Optional[str] = None,
        release_date_lte: Optional[str] = None,
        vote_count_gte: int = 10,
    ) -> PagedResultModel:
        """Retrieve paginated television series matching filters. Ensures only TV series are returned."""
        # Normalize sort_by for TV endpoint (TMDB series discover uses first_air_date)
        norm_sort = sort_by
        if "primary_release_date" in norm_sort:
            norm_sort = norm_sort.replace("primary_release_date", "first_air_date")
        elif norm_sort == "release_date.desc":
            norm_sort = "first_air_date.desc"
        elif norm_sort == "release_date.asc":
            norm_sort = "first_air_date.asc"
        elif norm_sort == "title.asc":
            norm_sort = "popularity.desc"

        params: Dict[str, Any] = {
            "sort_by": norm_sort,
            "vote_count.gte": vote_count_gte,
            "include_adult": False,
        }
        if with_original_language:
            params["with_original_language"] = with_original_language
        if without_original_language:
            params["without_original_language"] = without_original_language
        if with_origin_country:
            params["with_origin_country"] = with_origin_country
        if with_genres:
            # Map movie genre IDs to TV genre taxonomy
            params["with_genres"] = self._map_genres_for_tv(with_genres)
        if with_keywords:
            params["with_keywords"] = with_keywords
        if first_air_date_year:
            params["first_air_date_year"] = first_air_date_year
        if release_date_gte:
            params["first_air_date.gte"] = release_date_gte
        if release_date_lte:
            params["first_air_date.lte"] = release_date_lte

        raw_results, client_total_pages, tmdb_total_results = self._fetch_tmdb_pages(
            "/discover/tv",
            params,
            page=page,
            page_size=page_size,
            category="discover",
        )
        if with_origin_country:
            for item in raw_results:
                if not item.get("origin_country"):
                    item["origin_country"] = [with_origin_country.upper()]

        parsed = [
            self._parse_media_summary(item, default_type="tv")
            for item in raw_results
        ]
        series_only = [item for item in parsed if item.media_type == "tv"]

        return PagedResultModel(
            page=page,
            total_pages=client_total_pages,
            total_results=tmdb_total_results if tmdb_total_results > 0 else len(series_only),
            results=series_only,
        )

    def discover_all(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "popularity.desc",
        with_original_language: Optional[str] = None,
        without_original_language: Optional[str] = None,
        with_origin_country: Optional[str] = None,
        with_genres: Optional[str] = None,
        with_keywords: Optional[str] = None,
        year: Optional[int] = None,
        release_date_gte: Optional[str] = None,
        release_date_lte: Optional[str] = None,
        vote_count_gte: int = 10,
    ) -> PagedResultModel:
        """Retrieve combined movie and television series content together.

        Fetches both movies and TV series using provider discovery endpoints,
        unifies them into a single coherent feed, orders the combined batch by the
        requested sort criteria, and preserves accurate content-type labels.
        """
        movies_res = self.discover_movies(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            with_original_language=with_original_language,
            without_original_language=without_original_language,
            with_origin_country=with_origin_country,
            with_genres=with_genres,
            with_keywords=with_keywords,
            primary_release_year=year,
            release_date_gte=release_date_gte,
            release_date_lte=release_date_lte,
            vote_count_gte=vote_count_gte,
        )
        series_res = self.discover_series(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            with_original_language=with_original_language,
            without_original_language=without_original_language,
            with_origin_country=with_origin_country,
            with_genres=with_genres,
            with_keywords=with_keywords,
            first_air_date_year=year,
            release_date_gte=release_date_gte,
            release_date_lte=release_date_lte,
            vote_count_gte=vote_count_gte,
        )

        combined: List[MediaItemSummary] = list(movies_res.results) + list(series_res.results)

        # Apply multi-content ordering strategy
        is_desc = "desc" in sort_by or "asc" not in sort_by
        if "vote_average" in sort_by:
            combined.sort(key=lambda x: (x.vote_average, x.vote_count), reverse=is_desc)
        elif "release_date" in sort_by or "primary_release_date" in sort_by or "first_air_date" in sort_by:
            combined.sort(key=lambda x: x.release_date or "", reverse=is_desc)
        elif "title" in sort_by:
            combined.sort(key=lambda x: (x.title or "").lower(), reverse=(not is_desc if "asc" in sort_by else is_desc))
        else:
            # Default: sort by popularity
            combined.sort(key=lambda x: x.popularity, reverse=is_desc)

        total_pages = max(movies_res.total_pages, series_res.total_pages)
        total_results = movies_res.total_results + series_res.total_results

        return PagedResultModel(
            page=page,
            total_pages=total_pages,
            total_results=total_results,
            results=combined[:page_size],
        )

    def search_movies(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
        language: Optional[str] = None,
        primary_release_year: Optional[int] = None,
    ) -> PagedResultModel:
        """Search movies by title query or person query."""
        if not query.strip():
            return PagedResultModel()
        params: Dict[str, Any] = {"query": query.strip(), "include_adult": False}
        if primary_release_year:
            params["primary_release_year"] = primary_release_year

        raw_results, client_total_pages, tmdb_total_results = self._fetch_tmdb_pages(
            "/search/movie",
            params,
            page=page,
            page_size=page_size,
            category="search",
        )

        # If movie search returns no direct titles on page 1, attempt person lookup
        if not raw_results and page == 1:
            multi_data = self._request_cached("GET", "/search/person", params={"query": query.strip(), "page": 1}, category="search")
            for person in (multi_data.get("results") or []):
                for k in person.get("known_for", []):
                    if k.get("media_type") == "movie" or "title" in k:
                        raw_results.append(k)

        parsed = [self._parse_media_summary(item, default_type="movie") for item in raw_results]
        movies_only = [item for item in parsed if item.media_type == "movie"]

        # Apply optional language filter if specified
        if language and language != "all":
            movies_only = [item for item in movies_only if item.original_language == language]

        return PagedResultModel(
            page=page,
            total_pages=client_total_pages,
            total_results=tmdb_total_results if tmdb_total_results > 0 else len(movies_only),
            results=movies_only,
        )

    def search_series(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
        language: Optional[str] = None,
        first_air_date_year: Optional[int] = None,
    ) -> PagedResultModel:
        """Search TV series by title query or person query."""
        if not query.strip():
            return PagedResultModel()
        params: Dict[str, Any] = {"query": query.strip(), "include_adult": False}
        if first_air_date_year:
            params["first_air_date_year"] = first_air_date_year

        raw_results, client_total_pages, tmdb_total_results = self._fetch_tmdb_pages(
            "/search/tv",
            params,
            page=page,
            page_size=page_size,
            category="search",
        )

        # If TV search returns no direct titles on page 1, attempt person lookup
        if not raw_results and page == 1:
            multi_data = self._request_cached("GET", "/search/person", params={"query": query.strip(), "page": 1}, category="search")
            for person in (multi_data.get("results") or []):
                for k in person.get("known_for", []):
                    if k.get("media_type") == "tv" or "name" in k:
                        raw_results.append(k)

        parsed = [self._parse_media_summary(item, default_type="tv") for item in raw_results]
        series_only = [item for item in parsed if item.media_type == "tv"]

        # Apply optional language filter if specified
        if language and language != "all":
            series_only = [item for item in series_only if item.original_language == language]

        return PagedResultModel(
            page=page,
            total_pages=client_total_pages,
            total_results=tmdb_total_results if tmdb_total_results > 0 else len(series_only),
            results=series_only,
        )

    def search_multi(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
        language: Optional[str] = None,
        year: Optional[int] = None,
    ) -> PagedResultModel:
        """Universal search across movies, TV series, and people (extracting known_for media)."""
        if not query.strip():
            return PagedResultModel()
        params = {"query": query.strip(), "include_adult": False}
        raw_results, client_total_pages, tmdb_total_results = self._fetch_tmdb_pages(
            "/search/multi",
            params,
            page=page,
            page_size=page_size,
            category="search",
        )

        seen_keys = set()
        parsed: List[MediaItemSummary] = []

        for item in raw_results:
            m_type = item.get("media_type")
            if m_type in ("movie", "tv"):
                key = (m_type, item.get("id"))
                if key not in seen_keys:
                    seen_keys.add(key)
                    parsed.append(self._parse_media_summary(item))
            elif m_type == "person":
                # Person Search Support: extract movies and TV series the person is famous for
                for k in item.get("known_for", []):
                    k_type = k.get("media_type", "movie" if "title" in k else "tv")
                    if k_type in ("movie", "tv"):
                        key = (k_type, k.get("id"))
                        if key not in seen_keys:
                            seen_keys.add(key)
                            parsed.append(self._parse_media_summary(k, default_type=k_type))

        # Apply optional compatible filters if specified
        if language and language != "all":
            parsed = [p for p in parsed if p.original_language == language]
        if year:
            parsed = [p for p in parsed if p.release_year == year]

        return PagedResultModel(
            page=page,
            total_pages=client_total_pages,
            total_results=tmdb_total_results if tmdb_total_results > 0 else len(parsed),
            results=parsed,
        )

    def get_genres(self, content_type: str = "movie") -> List[GenreModel]:
        """Fetch list of genres for movies or TV series."""
        endpoint = "/genre/movie/list" if content_type == "movie" else "/genre/tv/list"
        data = self._request_cached("GET", endpoint, category="genres")
        genres_raw = data.get("genres") or []
        return [GenreModel(id=int(g["id"]), name=str(g["name"])) for g in genres_raw]

    def get_movie_details(self, movie_id: int) -> MediaDetailsModel:
        """Fetch rich details for a movie including cast, crew, and trailers."""
        params = {"append_to_response": "credits,videos,similar"}
        data = self._request_cached("GET", f"/movie/{movie_id}", params=params, category="movie_details")
        summary = self._parse_media_summary(data, default_type="movie")

        # Genres
        genres = [
            GenreModel(id=int(g["id"]), name=str(g["name"]))
            for g in (data.get("genres") or [])
        ]

        # Credits
        credits_data = data.get("credits") or {}
        raw_cast = credits_data.get("cast") or []
        raw_crew = credits_data.get("crew") or []

        cast = [
            CastMemberModel(
                id=int(c.get("id", 0)),
                name=c.get("name") or "",
                character=c.get("character"),
                profile_path=c.get("profile_path"),
                profile_url=self._construct_image_url(c.get("profile_path"), "w185"),
                order=c.get("order", 0),
            )
            for c in raw_cast[:12]
        ]

        directors = [
            c.get("name")
            for c in raw_crew
            if c.get("job") == "Director" and c.get("name")
        ]

        # Videos / Trailers (prefer official YouTube trailers with valid keys)
        raw_videos = [
            v for v in ((data.get("videos") or {}).get("results") or [])
            if v.get("site") == "YouTube" and v.get("key")
        ]
        # Sort so official trailers appear first
        raw_videos.sort(key=lambda x: (not x.get("official", False), x.get("type") != "Trailer"))

        trailers = [
            VideoModel(
                id=v.get("id", ""),
                key=v.get("key", ""),
                name=v.get("name", "Trailer"),
                site="YouTube",
                type=v.get("type", "Trailer"),
                official=bool(v.get("official", False)),
                url=f"https://www.youtube.com/watch?v={v.get('key')}",
            )
            for v in raw_videos[:4]
        ]

        # Similar titles
        raw_similar = (data.get("similar") or {}).get("results") or []
        similar = [self._parse_media_summary(s, default_type="movie") for s in raw_similar[:8]]

        return MediaDetailsModel(
            **summary.model_dump(),
            tagline=data.get("tagline"),
            runtime_minutes=data.get("runtime"),
            status=data.get("status"),
            genres=genres,
            cast=cast,
            directors=directors,
            trailers=trailers,
            similar=similar,
        )

    def get_series_details(self, series_id: int) -> MediaDetailsModel:
        """Fetch rich details for a television series."""
        params = {"append_to_response": "credits,videos,similar"}
        data = self._request_cached("GET", f"/tv/{series_id}", params=params, category="tv_details")
        summary = self._parse_media_summary(data, default_type="tv")

        # Genres
        genres = [
            GenreModel(id=int(g["id"]), name=str(g["name"]))
            for g in (data.get("genres") or [])
        ]

        # Credits
        credits_data = data.get("credits") or {}
        raw_cast = credits_data.get("cast") or []
        cast = [
            CastMemberModel(
                id=int(c.get("id", 0)),
                name=c.get("name") or "",
                character=c.get("character"),
                profile_path=c.get("profile_path"),
                profile_url=self._construct_image_url(c.get("profile_path"), "w185"),
                order=c.get("order", 0),
            )
            for c in raw_cast[:12]
        ]

        # Creators
        created_by = [c.get("name") for c in (data.get("created_by") or []) if c.get("name")]

        # Videos / Trailers (prefer official YouTube trailers with valid keys)
        raw_videos = [
            v for v in ((data.get("videos") or {}).get("results") or [])
            if v.get("site") == "YouTube" and v.get("key")
        ]
        # Sort so official trailers appear first
        raw_videos.sort(key=lambda x: (not x.get("official", False), x.get("type") != "Trailer"))

        trailers = [
            VideoModel(
                id=v.get("id", ""),
                key=v.get("key", ""),
                name=v.get("name", "Trailer"),
                site="YouTube",
                type=v.get("type", "Trailer"),
                official=bool(v.get("official", False)),
                url=f"https://www.youtube.com/watch?v={v.get('key')}",
            )
            for v in raw_videos[:4]
        ]

        # Similar
        raw_similar = (data.get("similar") or {}).get("results") or []
        similar = [self._parse_media_summary(s, default_type="tv") for s in raw_similar[:8]]

        return MediaDetailsModel(
            **summary.model_dump(),
            tagline=data.get("tagline"),
            runtime_minutes=(data.get("episode_run_time") or [None])[0] if data.get("episode_run_time") else None,
            status=data.get("status"),
            genres=genres,
            cast=cast,
            directors=created_by,
            trailers=trailers,
            similar=similar,
            number_of_seasons=data.get("number_of_seasons"),
            number_of_episodes=data.get("number_of_episodes"),
        )

    def get_movie_recommendations(self, movie_id: int, page: int = 1) -> PagedResultModel:
        """Fetch curated TMDB user collaborative filtering recommendations for a movie."""
        try:
            params = {"page": max(1, min(500, page))}
            data = self._request_cached("GET", f"/movie/{movie_id}/recommendations", params=params, category="movie_recommendations")
            raw_results = data.get("results") or []
            parsed = [self._parse_media_summary(item, default_type="movie") for item in raw_results]
            return PagedResultModel(
                page=int(data.get("page", 1)),
                total_pages=int(data.get("total_pages", 1)),
                total_results=int(data.get("total_results", len(parsed))),
                results=parsed,
            )
        except Exception as e:
            logger.warning("Failed to fetch TMDB movie recommendations for ID %d: %s", movie_id, e)
            return PagedResultModel()

    def get_movie_similar(self, movie_id: int, page: int = 1) -> PagedResultModel:
        """Fetch similar movies based on metadata overlap and tags for a movie."""
        try:
            params = {"page": max(1, min(500, page))}
            data = self._request_cached("GET", f"/movie/{movie_id}/similar", params=params, category="movie_similar")
            raw_results = data.get("results") or []
            parsed = [self._parse_media_summary(item, default_type="movie") for item in raw_results]
            return PagedResultModel(
                page=int(data.get("page", 1)),
                total_pages=int(data.get("total_pages", 1)),
                total_results=int(data.get("total_results", len(parsed))),
                results=parsed,
            )
        except Exception as e:
            logger.warning("Failed to fetch TMDB similar movies for ID %d: %s", movie_id, e)
            return PagedResultModel()

    def get_movie_keywords(self, movie_id: int) -> List[Dict[str, Any]]:
        """Fetch associated thematic keywords for a movie."""
        try:
            data = self._request_cached("GET", f"/movie/{movie_id}/keywords", category="movie_keywords")
            return list(data.get("keywords") or [])
        except Exception as e:
            logger.warning("Failed to fetch TMDB keywords for movie ID %d: %s", movie_id, e)
            return []

    def get_series_recommendations(self, series_id: int, page: int = 1) -> PagedResultModel:
        """Fetch curated TMDB user recommendations for a television series."""
        try:
            params = {"page": max(1, min(500, page))}
            data = self._request_cached("GET", f"/tv/{series_id}/recommendations", params=params, category="tv_recommendations")
            raw_results = data.get("results") or []
            parsed = [self._parse_media_summary(item, default_type="tv") for item in raw_results]
            return PagedResultModel(
                page=int(data.get("page", 1)),
                total_pages=int(data.get("total_pages", 1)),
                total_results=int(data.get("total_results", len(parsed))),
                results=parsed,
            )
        except Exception as e:
            logger.warning("Failed to fetch TMDB series recommendations for ID %d: %s", series_id, e)
            return PagedResultModel()

    def get_series_similar(self, series_id: int, page: int = 1) -> PagedResultModel:
        """Fetch similar television series based on metadata tags for a series."""
        try:
            params = {"page": max(1, min(500, page))}
            data = self._request_cached("GET", f"/tv/{series_id}/similar", params=params, category="tv_similar")
            raw_results = data.get("results") or []
            parsed = [self._parse_media_summary(item, default_type="tv") for item in raw_results]
            return PagedResultModel(
                page=int(data.get("page", 1)),
                total_pages=int(data.get("total_pages", 1)),
                total_results=int(data.get("total_results", len(parsed))),
                results=parsed,
            )
        except Exception as e:
            logger.warning("Failed to fetch TMDB similar series for ID %d: %s", series_id, e)
            return PagedResultModel()

    def get_series_keywords(self, series_id: int) -> List[Dict[str, Any]]:
        """Fetch associated thematic keywords for a television series."""
        try:
            data = self._request_cached("GET", f"/tv/{series_id}/keywords", category="tv_keywords")
            return list(data.get("results") or [])
        except Exception as e:
            logger.warning("Failed to fetch TMDB keywords for series ID %d: %s", series_id, e)
            return []

    def search_keywords(self, query: str, page: int = 1) -> List[Dict[str, Any]]:
        """Search TMDB keyword taxonomy by text query."""
        if not query or not query.strip():
            return []
        try:
            params = {"query": query.strip(), "page": max(1, min(500, page))}
            data = self._request_cached("GET", "/search/keyword", params=params, category="search_keyword")
            return list(data.get("results") or [])
        except Exception as e:
            logger.warning("Failed to search TMDB keywords for query '%s': %s", query, e)
            return []

    def get_watch_providers(
        self,
        media_type: str,
        item_id: int,
        region: str = "IN",
    ) -> WatchProvidersModel:
        """Fetch streaming, rental, and buy availability powered by JustWatch via TMDB."""
        safe_type = "tv" if media_type == "tv" else "movie"
        endpoint = f"/{safe_type}/{item_id}/watch/providers"
        try:
            data = self._request_cached("GET", endpoint, category="watch_providers")
        except Exception as e:
            logger.warning("Failed to fetch watch providers for %s/%s: %s", safe_type, item_id, e)
            return WatchProvidersModel(id=item_id, region=region)

        results = data.get("results") or {}
        req_code = (region or "IN").upper()
        region_data = results.get(req_code) or {}

        # If requested region has no entries, check IN then US or first available
        active_code = req_code
        if not region_data:
            if "IN" in results:
                region_data = results["IN"]
                active_code = "IN"
            elif "US" in results:
                region_data = results["US"]
                active_code = "US"
            elif results:
                active_code = next(iter(results.keys()))
                region_data = results[active_code]

        def _parse_provider_list(items: Optional[List[Dict[str, Any]]]) -> List[WatchProviderItem]:
            parsed: List[WatchProviderItem] = []
            if not items:
                return parsed
            for p in items:
                logo_path = p.get("logo_path")
                parsed.append(
                    WatchProviderItem(
                        provider_id=int(p.get("provider_id", 0)),
                        provider_name=str(p.get("provider_name", "Provider")),
                        logo_path=logo_path,
                        logo_url=self._construct_image_url(logo_path, "w92") if logo_path else None,
                        display_priority=int(p.get("display_priority", 0)),
                    )
                )
            parsed.sort(key=lambda x: x.display_priority)
            return parsed

        return WatchProvidersModel(
            id=item_id,
            region=active_code,
            tmdb_link=region_data.get("link"),
            flatrate=_parse_provider_list(region_data.get("flatrate")),
            rent=_parse_provider_list(region_data.get("rent")),
            buy=_parse_provider_list(region_data.get("buy")),
            attribution="Streaming availability data provided by JustWatch via TMDB.",
        )
