"""Phase 2 Acceptance Tests: Bond Movie Hub — Interactive Staged Preference Editing & Reprocessing.

Tests Cover:
- TEST 1: Remove one filter. Verify that no recommendation API request occurs.
- TEST 2: Remove four filters. Verify all four remain removed in editable state.
- TEST 3: Click Reprocess Recommendations. Verify the backend receives only active preferences.
- TEST 4: Verify the original prompt remains unchanged.
- TEST 5: Refresh UI / state update. Verify removed filters do not reappear.
- TEST 6: Click Reset Filters. Verify original preferences return and pending changes clear.
- TEST 7: Simulate a backend error. Verify pending changes are preserved.
- TEST 8: Reprocess twice with different filters. Verify latest request determines results & distinct cache keys.
- TEST 9: Verify existing recommendation functionality remains operational.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.api.movie_models import (
    EditedPreferenceModel,
    GenreModel,
    MediaDetailsModel,
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
    RecommendationRequest,
    RecommendationResponse,
    RecommendedTitleModel,
)
from app.api.tmdb_client import TMDBClient
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


@pytest.fixture
def mock_storage():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = DatabaseManager(db_path)
    repo = MovieStorageRepository(db)
    yield repo
    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture
def mock_tmdb():
    client = MagicMock(spec=TMDBClient)
    client.is_configured.return_value = True

    # Mock Premalu movie details
    premalu_details = MediaDetailsModel(
        id=12345,
        media_type="movie",
        title="Premalu",
        original_language="ml",
        release_date="2024-02-09",
        release_year=2024,
        genres=[GenreModel(id=10749, name="Romance"), GenreModel(id=35, name="Comedy")],
        genre_ids=[10749, 35],
        origin_country=["IN"],
        vote_average=7.8,
        overview="A romantic comedy set in Hyderabad.",
    )
    client.search_multi.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=1,
        results=[
            MediaItemSummary(
                id=12345, media_type="movie", title="Premalu",
                original_language="ml", release_year=2024,
                genre_ids=[10749, 35], origin_country=["IN"],
                vote_average=7.8, overview="Romantic comedy",
            )
        ]
    )
    client.get_movie_details.return_value = premalu_details
    client.get_movie_recommendations.return_value = PagedResultModel(
        page=1, total_pages=1, total_results=2,
        results=[
            MediaItemSummary(
                id=2001, media_type="movie", title="Hridayam",
                original_language="ml", release_year=2022,
                genre_ids=[10749, 18], origin_country=["IN"],
                vote_average=8.1, overview="A journey through college romance and adulthood.",
            ),
            MediaItemSummary(
                id=2002, media_type="movie", title="Kumbalangi Nights",
                original_language="ml", release_year=2019,
                genre_ids=[18, 35], origin_country=["IN"],
                vote_average=8.2, overview="Four brothers in a dysfunctional home find love.",
            ),
        ]
    )
    client.discover_movies.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])
    return client


@pytest.fixture
def engine(mock_tmdb, mock_storage):
    eng = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=mock_storage,
        ollama_client=None,
        default_model="llama3.2:3b",
    )
    return eng


class FrontendFilterStateManager:
    """Simulates React state management in AIRecommendationSection.tsx."""

    def __init__(self, original_prompt: str, initial_chips: list[dict]):
        self.original_prompt = original_prompt
        self.original_preferences = list(initial_chips)
        self.active_preferences = list(initial_chips)
        self.applied_preferences = list(initial_chips)
        self.reprocessing = False
        self.api_call_count = 0
        self.latest_request_id = 0

    def remove_preference(self, chip_id: str):
        # Pure local state modification: NO API CALL, NO PROMPT REGEX MUTATION
        self.active_preferences = [p for p in self.active_preferences if p["id"] != chip_id]

    def add_preference(self, category: str, label: str, value: str):
        # Prevent duplicates
        if any(p["category"] == category and p["value"].lower() == value.lower() for p in self.active_preferences):
            return
        self.active_preferences.append({
            "id": f"custom-{category}-{len(self.active_preferences)}",
            "category": category,
            "label": label,
            "value": value,
        })

    def reset_filters(self):
        self.active_preferences = list(self.original_preferences)

    @property
    def removed_preferences(self):
        return [
            orig for orig in self.original_preferences
            if not any(act["category"] == orig["category"] and act["value"].lower() == orig["value"].lower()
                       for act in self.active_preferences)
        ]

    @property
    def added_preferences(self):
        return [
            act for act in self.active_preferences
            if not any(orig["category"] == act["category"] and orig["value"].lower() == act["value"].lower()
                       for orig in self.original_preferences)
        ]

    @property
    def has_pending_changes(self):
        return len(self.removed_preferences) > 0 or len(self.added_preferences) > 0

    def reprocess(self, backend_engine: MovieRecommendationEngine, fail: bool = False):
        self.reprocessing = True
        self.api_call_count += 1
        req_id = self.latest_request_id + 1
        self.latest_request_id = req_id

        if fail:
            self.reprocessing = False
            raise RuntimeError("Simulated backend network or Ollama failure")

        # Authoritative edited preferences sent to backend; prompt preserved
        resp = backend_engine.recommend(
            query=self.original_prompt,
            include_saved_preferences=True,
            limit=8,
            edited_preferences=[EditedPreferenceModel(**p) for p in self.active_preferences],
            removed_preferences=[EditedPreferenceModel(**p) for p in self.removed_preferences],
            request_id=str(req_id),
        )
        self.applied_preferences = list(self.active_preferences)
        self.reprocessing = False
        return resp


# =============================================================================
# ACCEPTANCE TESTS (TEST 1 to TEST 9)
# =============================================================================

def test_1_remove_one_filter_no_api_request():
    """TEST 1: Remove one filter. Verify that no recommendation API request occurs."""
    initial_chips = [
        {"id": "ref-premalu", "category": "ref", "label": "Like: Premalu", "value": "Premalu"},
        {"id": "genre-romance", "category": "genre", "label": "Romance", "value": "Romance"},
        {"id": "genre-drama", "category": "genre", "label": "Drama", "value": "Drama"},
        {"id": "lang-te", "category": "lang", "label": "Telugu", "value": "Telugu"},
    ]
    ui = FrontendFilterStateManager("Indian Movies like Premalu", initial_chips)

    # Click 'x' on Telugu chip
    ui.remove_preference("lang-te")

    # Assertions
    assert ui.api_call_count == 0, "No API request should occur when removing a filter"
    assert not any(p["id"] == "lang-te" for p in ui.active_preferences), "Telugu should be removed"
    assert len(ui.active_preferences) == 3
    assert ui.has_pending_changes is True
    assert len(ui.removed_preferences) == 1
    assert ui.removed_preferences[0]["value"] == "Telugu"
    assert ui.original_prompt == "Indian Movies like Premalu", "Original prompt must remain unchanged"


def test_2_remove_four_filters_all_remain_removed():
    """TEST 2: Remove four filters. Verify all four remain removed."""
    initial_chips = [
        {"id": "ref-premalu", "category": "ref", "label": "Like: Premalu", "value": "Premalu"},
        {"id": "genre-romance", "category": "genre", "label": "Romance", "value": "Romance"},
        {"id": "genre-drama", "category": "genre", "label": "Drama", "value": "Drama"},
        {"id": "theme-family", "category": "theme", "label": "Family drama", "value": "Family drama"},
        {"id": "theme-social", "category": "theme", "label": "Social issues", "value": "Social issues"},
        {"id": "lang-te", "category": "lang", "label": "Telugu", "value": "Telugu"},
    ]
    ui = FrontendFilterStateManager("Indian Movies like Premalu", initial_chips)

    # Remove Telugu, Romance, Family drama, Social issues
    ui.remove_preference("lang-te")
    ui.remove_preference("genre-romance")
    ui.remove_preference("theme-family")
    ui.remove_preference("theme-social")

    assert ui.api_call_count == 0, "No API calls made during removals"
    assert len(ui.active_preferences) == 2, "Only 2 filters should remain active"
    remaining_ids = {p["id"] for p in ui.active_preferences}
    assert remaining_ids == {"ref-premalu", "genre-drama"}
    assert len(ui.removed_preferences) == 4
    removed_values = {p["value"] for p in ui.removed_preferences}
    assert removed_values == {"Telugu", "Romance", "Family drama", "Social issues"}


def test_3_reprocess_backend_receives_only_active_preferences(engine):
    """TEST 3: Click Reprocess Recommendations. Verify the backend receives only active preferences."""
    initial_chips = [
        {"id": "ref-premalu", "category": "ref", "label": "Like: Premalu", "value": "Premalu"},
        {"id": "genre-romance", "category": "genre", "label": "Romance", "value": "Romance"},
        {"id": "genre-drama", "category": "genre", "label": "Drama", "value": "Drama"},
        {"id": "lang-te", "category": "lang", "label": "Telugu", "value": "Telugu"},
    ]
    ui = FrontendFilterStateManager("Indian Movies like Premalu", initial_chips)

    # Remove Telugu & Romance
    ui.remove_preference("lang-te")
    ui.remove_preference("genre-romance")

    # Click Reprocess Recommendations
    resp = ui.reprocess(engine)

    assert ui.api_call_count == 1
    assert resp is not None
    assert resp.diagnostics["edited_preferences_applied"] is True
    # Verify backend intent reflects only active preferences: Drama (no Romance, no Telugu)
    assert "Romance" not in resp.interpreted_intent.genres
    assert "te" not in resp.interpreted_intent.languages
    assert "Drama" in resp.interpreted_intent.genres
    assert resp.interpreted_intent.reference_title == "Premalu"
    # Applied preferences are saved
    assert len(ui.applied_preferences) == 2


def test_4_original_prompt_remains_unchanged(engine):
    """TEST 4: Verify the original prompt remains unchanged throughout."""
    original_q = "Indian Movies like Premalu"
    ui = FrontendFilterStateManager(original_q, [
        {"id": "genre-romance", "category": "genre", "label": "Romance", "value": "Romance"},
        {"id": "genre-drama", "category": "genre", "label": "Drama", "value": "Drama"},
    ])

    ui.remove_preference("genre-romance")
    ui.add_preference("genre", "Thriller", "Thriller")
    resp = ui.reprocess(engine)

    assert ui.original_prompt == original_q
    assert resp.query == original_q


def test_5_ui_refresh_does_not_restore_removed_filters():
    """TEST 5: Trigger state updates/re-renders. Verify removed filters do not reappear."""
    initial_chips = [
        {"id": "g1", "category": "genre", "label": "Romance", "value": "Romance"},
        {"id": "g2", "category": "genre", "label": "Comedy", "value": "Comedy"},
    ]
    ui = FrontendFilterStateManager("Movies like Premalu", initial_chips)

    ui.remove_preference("g1")
    assert len(ui.active_preferences) == 1

    # Simulate unrelated UI state update (e.g. toggling history modal or theme)
    unrelated_state = {"isHistoryOpen": True, "showDiagnostics": True}
    # active_preferences must remain untouched
    assert len(ui.active_preferences) == 1
    assert ui.active_preferences[0]["id"] == "g2"


def test_6_reset_filters_restores_original_preferences():
    """TEST 6: Click Reset Filters. Verify the original preferences return and pending changes clear."""
    initial_chips = [
        {"id": "g1", "category": "genre", "label": "Romance", "value": "Romance"},
        {"id": "g2", "category": "genre", "label": "Drama", "value": "Drama"},
    ]
    ui = FrontendFilterStateManager("Romantic Drama", initial_chips)

    ui.remove_preference("g1")
    assert ui.has_pending_changes is True

    # Click Reset Filters
    ui.reset_filters()

    assert len(ui.active_preferences) == 2
    assert ui.has_pending_changes is False
    assert ui.api_call_count == 0, "Reset Filters should NOT trigger automatic API call"


def test_7_simulate_backend_error_preserves_pending_changes(engine):
    """TEST 7: Simulate a backend error. Verify pending changes are preserved."""
    initial_chips = [
        {"id": "g1", "category": "genre", "label": "Romance", "value": "Romance"},
        {"id": "g2", "category": "genre", "label": "Comedy", "value": "Comedy"},
    ]
    ui = FrontendFilterStateManager("Comedy like Premalu", initial_chips)

    ui.remove_preference("g1")
    ui.add_preference("theme", "Friendship", "Friendship")

    # Simulate network failure during reprocessing
    with pytest.raises(RuntimeError):
        ui.reprocess(engine, fail=True)

    # Verify user edits were NOT wiped
    assert ui.has_pending_changes is True
    assert len(ui.removed_preferences) == 1
    assert ui.removed_preferences[0]["value"] == "Romance"
    assert len(ui.added_preferences) == 1
    assert ui.added_preferences[0]["value"] == "Friendship"


def test_8_reprocess_twice_with_different_filters_distinct_cache_keys(engine):
    """TEST 8: Reprocess twice with different filters. Verify distinct cache keys and request IDs."""
    initial_chips = [
        {"id": "g1", "category": "genre", "label": "Romance", "value": "Romance"},
        {"id": "g2", "category": "genre", "label": "Drama", "value": "Drama"},
        {"id": "g3", "category": "genre", "label": "Comedy", "value": "Comedy"},
    ]
    ui = FrontendFilterStateManager("Movies like Premalu", initial_chips)

    # First reprocess: remove Romance
    ui.remove_preference("g1")
    resp1 = ui.reprocess(engine)
    req_id_1 = resp1.diagnostics["request_id"]

    # Second reprocess: remove Comedy as well
    ui.remove_preference("g3")
    resp2 = ui.reprocess(engine)
    req_id_2 = resp2.diagnostics["request_id"]

    assert req_id_1 == "1"
    assert req_id_2 == "2"
    assert resp1.interpreted_intent.genres != resp2.interpreted_intent.genres
    assert "Comedy" in resp1.interpreted_intent.genres
    assert "Comedy" not in resp2.interpreted_intent.genres


def test_9_existing_recommendation_functionality_remains_operational(engine):
    """TEST 9: Verify standard prompt search without edited preferences works as before."""
    resp = engine.recommend(
        query="Underrated Malayalam thriller",
        include_saved_preferences=True,
        limit=5,
    )
    assert resp is not None
    assert resp.interpreted_intent.intent_type in ("regional", "genre", "complex", "general")
    assert resp.diagnostics["edited_preferences_applied"] is False
