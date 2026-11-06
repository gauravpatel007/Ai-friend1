"""Mock TMDB Responses and Testable Fixtures for Evaluation.

Provides reproducible TMDB v3 API responses covering 8 specific fixture scenarios:
1. Successful search results
2. Empty search results
3. Incorrect / malformed responses
4. Missing posters
5. Missing ratings
6. Duplicate movies
7. Multiple movies with similar titles (disambiguation)
8. API authentication failures
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from app.api.movie_models import PagedResultModel
from app.api.tmdb_client import (
    TMDBAuthError,
    TMDBClient,
    TMDBNetworkError,
    TMDBRateLimitError,
)

# ---------------------------------------------------------------------------
# 1. Successful Search Results (Rich canonical data)
# ---------------------------------------------------------------------------
MOCK_SUCCESSFUL_MOVIES: Dict[str, Any] = {
    "page": 1,
    "total_pages": 5,
    "total_results": 95,
    "results": [
        {
            "id": 157336,
            "title": "Interstellar",
            "original_title": "Interstellar",
            "overview": "The adventures of a group of explorers who make use of a newly discovered wormhole to surpass the limitations on human space travel.",
            "release_date": "2014-11-05",
            "genre_ids": [12, 18, 878],
            "original_language": "en",
            "popularity": 145.2,
            "vote_average": 8.4,
            "vote_count": 34500,
            "poster_path": "/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",
            "backdrop_path": "/xJHokMbljvjADYdit5fK5VQsXEG.jpg",
            "media_type": "movie",
        },
        {
            "id": 27205,
            "title": "Inception",
            "original_title": "Inception",
            "overview": "Cobb, a skilled thief who commits corporate espionage by infiltrating the subconscious of his targets is offered a chance to regain his old life.",
            "release_date": "2010-07-15",
            "genre_ids": [28, 878, 12, 53],
            "original_language": "en",
            "popularity": 122.8,
            "vote_average": 8.4,
            "vote_count": 36100,
            "poster_path": "/edv5CZvWj09upOsy2Y6IwDhK8bt.jpg",
            "backdrop_path": "/s3TBrRGB1iav7gFOCNx3H31MoES.jpg",
            "media_type": "movie",
        },
        {
            "id": 11324,
            "title": "Shutter Island",
            "original_title": "Shutter Island",
            "overview": "World War II soldier-turned-U.S. Marshal Teddy Daniels investigates the disappearance of a patient from Boston's Shutter Island Ashecliffe Hospital.",
            "release_date": "2010-02-14",
            "genre_ids": [18, 53, 9648],
            "original_language": "en",
            "popularity": 98.4,
            "vote_average": 8.2,
            "vote_count": 23500,
            "poster_path": "/4GDy0PHYX3VRXUtwK5ysag3geEx.jpg",
            "backdrop_path": "/c7WknG8rJcR4gYc751Z62XhT62K.jpg",
            "media_type": "movie",
        },
        {
            "id": 661374,
            "title": "Glass Onion: A Knives Out Mystery",
            "original_title": "Glass Onion: A Knives Out Mystery",
            "overview": "World-famous detective Benoit Blanc heads to Greece to peel back the layers of a mystery involving a tech billionaire and his eclectic crew of friends.",
            "release_date": "2022-11-23",
            "genre_ids": [35, 9648, 53],
            "original_language": "en",
            "popularity": 87.5,
            "vote_average": 7.1,
            "vote_count": 5200,
            "poster_path": "/vDGr1YdrlfbU9wxTOdpf3zChmv9.jpg",
            "backdrop_path": "/dKqa850uvbNSCaQCV4Im1XlzEtQ.jpg",
            "media_type": "movie",
        },
        {
            "id": 546554,
            "title": "Knives Out",
            "original_title": "Knives Out",
            "overview": "When renowned crime novelist Harlan Thrombey is found dead at his estate, the inquisitive Detective Benoit Blanc is mysteriously enlisted to investigate.",
            "release_date": "2019-11-27",
            "genre_ids": [35, 9648, 18],
            "original_language": "en",
            "popularity": 79.1,
            "vote_average": 7.9,
            "vote_count": 12100,
            "poster_path": "/pThyQovXQrw2m0s9x82twj48Jq4.jpg",
            "backdrop_path": "/4HWAQu28e2yaWrtupFPGFkdNU7V.jpg",
            "media_type": "movie",
        },
    ],
}

# ---------------------------------------------------------------------------
# 2. Empty Search Results
# ---------------------------------------------------------------------------
MOCK_EMPTY_SEARCH: Dict[str, Any] = {
    "page": 1,
    "total_pages": 0,
    "total_results": 0,
    "results": [],
}

# ---------------------------------------------------------------------------
# 3. Incorrect / Malformed Responses
# ---------------------------------------------------------------------------
MOCK_INCORRECT_RESPONSES: List[Dict[str, Any]] = [
    # Missing 'results' key entirely
    {"page": 1, "total_pages": 1, "items": []},
    # Results is not a list
    {"page": 1, "results": "corrupted_payload_string"},
    # Malformed internal items (missing id or title)
    {
        "page": 1,
        "results": [
            {"name": "No ID Item", "vote_average": 8.0},
            {"id": "non_integer_id", "title": "Bad ID Title"},
        ],
    },
]

# ---------------------------------------------------------------------------
# 4. Missing Posters (poster_path is None or empty)
# ---------------------------------------------------------------------------
MOCK_MISSING_POSTERS: Dict[str, Any] = {
    "page": 1,
    "total_pages": 1,
    "total_results": 3,
    "results": [
        {
            "id": 90001,
            "title": "Ghost Movie No Poster",
            "overview": "A mysterious film with zero promotional art or poster images.",
            "release_date": "2023-01-01",
            "genre_ids": [9648, 53],
            "original_language": "en",
            "popularity": 12.0,
            "vote_average": 7.0,
            "vote_count": 50,
            "poster_path": None,
            "backdrop_path": None,
            "media_type": "movie",
        },
        {
            "id": 90002,
            "title": "Empty String Poster Film",
            "overview": "Another film where poster_path is an empty string instead of None.",
            "release_date": "2022-05-10",
            "genre_ids": [878],
            "original_language": "en",
            "popularity": 8.5,
            "vote_average": 6.8,
            "vote_count": 30,
            "poster_path": "",
            "backdrop_path": "",
            "media_type": "movie",
        },
    ],
}

# ---------------------------------------------------------------------------
# 5. Missing Ratings (vote_average 0 or None, vote_count 0)
# ---------------------------------------------------------------------------
MOCK_MISSING_RATINGS: Dict[str, Any] = {
    "page": 1,
    "total_pages": 1,
    "total_results": 2,
    "results": [
        {
            "id": 91001,
            "title": "Unreleased Indie Thriller",
            "overview": "A brand new festival thriller that has not yet received public ratings.",
            "release_date": "2026-10-01",
            "genre_ids": [53, 9648],
            "original_language": "en",
            "popularity": 5.0,
            "vote_average": 0.0,
            "vote_count": 0,
            "poster_path": "/sample_poster_1.jpg",
            "media_type": "movie",
        },
        {
            "id": 91002,
            "title": "Zero Votes Feature",
            "overview": "Obscure title with null rating attributes.",
            "release_date": "2025-02-14",
            "genre_ids": [18],
            "original_language": "en",
            "popularity": 2.1,
            "vote_average": None,
            "vote_count": 0,
            "poster_path": "/sample_poster_2.jpg",
            "media_type": "movie",
        },
    ],
}

# ---------------------------------------------------------------------------
# 6. Duplicate Movies Across Result Batches
# ---------------------------------------------------------------------------
MOCK_DUPLICATE_MOVIES: Dict[str, Any] = {
    "page": 1,
    "total_pages": 1,
    "total_results": 5,
    "results": [
        {
            "id": 157336,
            "title": "Interstellar",
            "overview": "First occurrence of Interstellar in candidate pool.",
            "release_date": "2014-11-05",
            "genre_ids": [878, 18],
            "original_language": "en",
            "popularity": 145.0,
            "vote_average": 8.4,
            "vote_count": 34000,
            "poster_path": "/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",
            "media_type": "movie",
        },
        {
            "id": 157336,  # DUPLICATE ID
            "title": "Interstellar",
            "overview": "Duplicate entry returned from another search tier.",
            "release_date": "2014-11-05",
            "genre_ids": [878, 18],
            "original_language": "en",
            "popularity": 145.0,
            "vote_average": 8.4,
            "vote_count": 34000,
            "poster_path": "/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",
            "media_type": "movie",
        },
        {
            "id": 27205,
            "title": "Inception",
            "overview": "Inception candidate entry.",
            "release_date": "2010-07-15",
            "genre_ids": [878, 28],
            "original_language": "en",
            "popularity": 120.0,
            "vote_average": 8.4,
            "vote_count": 36000,
            "poster_path": "/edv5CZvWj09upOsy2Y6IwDhK8bt.jpg",
            "media_type": "movie",
        },
        {
            "id": 157336,  # TRIPLICATE ID
            "title": "Interstellar (Special Edition)",
            "overview": "Third duplicate appearance.",
            "release_date": "2014-11-05",
            "genre_ids": [878],
            "original_language": "en",
            "popularity": 145.0,
            "vote_average": 8.4,
            "vote_count": 34000,
            "poster_path": "/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",
            "media_type": "movie",
        },
    ],
}

# ---------------------------------------------------------------------------
# 7. Multiple Movies with Similar Titles (Disambiguation challenge)
# ---------------------------------------------------------------------------
MOCK_SIMILAR_TITLES_DISAMBIGUATION: Dict[str, Any] = {
    "page": 1,
    "total_pages": 1,
    "total_results": 4,
    "results": [
        {
            "id": 661374,
            "title": "Glass Onion: A Knives Out Mystery",
            "overview": "Canonical blockbuster sequel directed by Rian Johnson.",
            "release_date": "2022-11-23",
            "genre_ids": [35, 9648, 53],
            "original_language": "en",
            "popularity": 180.5,
            "vote_average": 7.1,
            "vote_count": 5200,
            "poster_path": "/vDGr1YdrlfbU9wxTOdpf3zChmv9.jpg",
            "media_type": "movie",
        },
        {
            "id": 999901,
            "title": "Making of Glass Onion",
            "overview": "A 12-minute behind-the-scenes promotional featurette.",
            "release_date": "2022-12-01",
            "genre_ids": [99],
            "original_language": "en",
            "popularity": 1.2,
            "vote_average": 6.0,
            "vote_count": 12,
            "poster_path": None,
            "media_type": "movie",
        },
        {
            "id": 999902,
            "title": "Glass Onion: The Fan Parody",
            "overview": "Low budget YouTube parody.",
            "release_date": "2023-03-15",
            "genre_ids": [35],
            "original_language": "en",
            "popularity": 0.4,
            "vote_average": 4.5,
            "vote_count": 3,
            "poster_path": None,
            "media_type": "movie",
        },
        {
            "id": 999903,
            "title": "The Glass Onion: Beatles Song Story",
            "overview": "Documentary about the 1968 Beatles track.",
            "release_date": "2018-09-10",
            "genre_ids": [99, 10402],
            "original_language": "en",
            "popularity": 2.1,
            "vote_average": 6.5,
            "vote_count": 25,
            "poster_path": "/beatles_glass.jpg",
            "media_type": "movie",
        },
    ],
}

# ---------------------------------------------------------------------------
# 8. Authentication Failure Payload
# ---------------------------------------------------------------------------
MOCK_AUTH_FAILURE_PAYLOAD: Dict[str, Any] = {
    "status_code": 7,
    "status_message": "Invalid API key: You must be granted a valid key.",
    "success": False,
}


class MockTMDBClient:
    """Mock TMDB client configurable for testing different fixture scenarios."""

    def __init__(self, scenario: str = "success") -> None:
        self.scenario = scenario
        self.call_count = 0
        self.recorded_queries: List[str] = []

    def is_configured(self) -> bool:
        return self.scenario != "auth_failure"

    def search_movies(self, query: str, page: int = 1) -> Dict[str, Any]:
        self.call_count += 1
        self.recorded_queries.append(query)

        if self.scenario == "auth_failure":
            raise TMDBAuthError("TMDB authentication failed (401)")
        elif self.scenario == "rate_limit":
            raise TMDBRateLimitError("TMDB rate limit exceeded (429)")
        elif self.scenario == "network_error":
            raise TMDBNetworkError("Connection refused")
        elif self.scenario == "empty":
            return MOCK_EMPTY_SEARCH
        elif self.scenario == "disambiguation":
            return MOCK_SIMILAR_TITLES_DISAMBIGUATION
        elif self.scenario == "missing_posters":
            return MOCK_MISSING_POSTERS
        elif self.scenario == "missing_ratings":
            return MOCK_MISSING_RATINGS
        elif self.scenario == "duplicates":
            return MOCK_DUPLICATE_MOVIES
        elif self.scenario == "malformed":
            return MOCK_INCORRECT_RESPONSES[0]

        # Default success scenario
        return PagedResultModel(**MOCK_SUCCESSFUL_MOVIES)

    def search_multi(self, query: str, page: int = 1) -> Dict[str, Any]:
        return self.search_movies(query, page)

    def discover_movies(self, **kwargs) -> Any:
        self.call_count += 1
        if self.scenario == "auth_failure":
            raise TMDBAuthError("TMDB authentication failed (401)")
        elif self.scenario == "empty":
            return PagedResultModel(**MOCK_EMPTY_SEARCH)
        elif self.scenario == "duplicates":
            return PagedResultModel(**MOCK_DUPLICATE_MOVIES)
        elif self.scenario == "missing_posters":
            return PagedResultModel(**MOCK_MISSING_POSTERS)
        elif self.scenario == "missing_ratings":
            return PagedResultModel(**MOCK_MISSING_RATINGS)
        return PagedResultModel(**MOCK_SUCCESSFUL_MOVIES)

    def discover_tv(self, **kwargs) -> Any:
        return self.discover_movies(**kwargs)

    def discover_all(self, **kwargs) -> Any:
        return self.discover_movies(**kwargs)

    def get_similar_movies(self, movie_id: int, page: int = 1) -> Any:
        self.call_count += 1
        if self.scenario == "auth_failure":
            raise TMDBAuthError("TMDB authentication failed (401)")
        elif self.scenario == "empty":
            return PagedResultModel(**MOCK_EMPTY_SEARCH)
        return PagedResultModel(**MOCK_SUCCESSFUL_MOVIES)

    def get_movie_recommendations(self, movie_id: int, page: int = 1) -> Dict[str, Any]:
        return self.get_similar_movies(movie_id, page)
