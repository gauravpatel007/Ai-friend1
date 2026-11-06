"""Tests for Phase 11 — UI Polish, Accessibility, Voice Discovery, Mood Recommendations, Comparison, and Watch Providers."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.api.movie_models import (
    WatchProviderItem,
    WatchProvidersModel,
    MediaItemSummary,
)
from app.api.tmdb_client import TMDBClient
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.voice.command_dispatcher import VoiceCommandParser, VoiceCommandDispatcher


# =============================================================================
# 1. Watch Providers Unit Tests (11.6)
# =============================================================================

def test_watch_providers_model_structure():
    """Verify WatchProvidersModel and WatchProviderItem data structures."""
    provider = WatchProviderItem(
        provider_id=8,
        provider_name="Netflix",
        logo_path="/pbpMk2JmcoNnQwx5JGpXngfoWtp.jpg",
        logo_url="https://image.tmdb.org/t/p/w92/pbpMk2JmcoNnQwx5JGpXngfoWtp.jpg",
        display_priority=0,
    )
    model = WatchProvidersModel(
        id=550,
        region="IN",
        tmdb_link="https://www.themoviedb.org/movie/550/watch?locale=IN",
        flatrate=[provider],
        rent=[],
        buy=[],
    )
    assert model.id == 550
    assert model.region == "IN"
    assert len(model.flatrate) == 1
    assert model.flatrate[0].provider_name == "Netflix"
    assert "JustWatch" in model.attribution


def test_tmdb_client_get_watch_providers_parsing():
    """Verify TMDBClient parses regional watch provider responses accurately."""
    client = TMDBClient(api_key="test_key")
    mock_payload = {
        "id": 550,
        "results": {
            "IN": {
                "link": "https://themoviedb.org/movie/550/watch?locale=IN",
                "flatrate": [
                    {
                        "logo_path": "/net.jpg",
                        "provider_id": 8,
                        "provider_name": "Netflix",
                        "display_priority": 1,
                    }
                ],
                "rent": [
                    {
                        "logo_path": "/app.jpg",
                        "provider_id": 2,
                        "provider_name": "Apple TV",
                        "display_priority": 0,
                    }
                ],
                "buy": [],
            }
        },
    }

    with patch.object(client, "_request_cached", return_value=mock_payload):
        providers = client.get_watch_providers("movie", 550, region="IN")

    assert providers.id == 550
    assert providers.region == "IN"
    assert len(providers.flatrate) == 1
    assert providers.flatrate[0].provider_name == "Netflix"
    assert len(providers.rent) == 1
    assert providers.rent[0].provider_name == "Apple TV"
    assert len(providers.buy) == 0


def test_tmdb_client_get_watch_providers_empty_fallback():
    """Verify TMDBClient handles missing regions without raising exceptions."""
    client = TMDBClient(api_key="test_key")
    with patch.object(client, "_request_cached", return_value={"id": 999, "results": {}}):
        providers = client.get_watch_providers("movie", 999, region="IN")

    assert providers.id == 999
    assert len(providers.flatrate) == 0
    assert len(providers.rent) == 0
    assert len(providers.buy) == 0


# =============================================================================
# 2. Watch Providers REST Endpoint Test (11.6)
# =============================================================================

def test_api_watch_providers_endpoint():
    """Verify FastAPI GET /api/movies/{media_type}/{item_id}/watch-providers returns expected payload."""
    from app.api.server import create_app
    mock_client = MagicMock()
    mock_client.cache_manager = None
    mock_model = WatchProvidersModel(
        id=123,
        region="IN",
        flatrate=[
            WatchProviderItem(
                provider_id=8,
                provider_name="Disney+ Hotstar",
                display_priority=0,
            )
        ],
        rent=[],
        buy=[],
    )
    mock_client.get_watch_providers.return_value = mock_model
    app = create_app()
    app.state.tmdb_client = mock_client

    with TestClient(app) as test_client:
        res = test_client.get("/api/movies/movie/123/watch-providers?region=IN")

    assert res.status_code == 200
    data = res.json()
    assert data["id"] == 123
    assert data["region"] == "IN"
    assert len(data["flatrate"]) == 1
    assert data["flatrate"][0]["provider_name"] == "Disney+ Hotstar"


# =============================================================================
# 3. Voice-Powered Discovery Command Parsing (11.3)
# =============================================================================

def test_voice_command_parser_open_movies():
    """Verify voice parser matches explicit open movie hub commands."""
    res1 = VoiceCommandParser.parse("open movie hub")
    assert res1 is not None
    assert res1[0] == "open_movies"

    res2 = VoiceCommandParser.parse("show movies")
    assert res2 is not None
    assert res2[0] == "open_movies"

    res3 = VoiceCommandParser.parse("સિનેમા ખોલો")
    assert res3 is not None
    assert res3[0] == "open_movies"


def test_voice_command_parser_movie_discovery():
    """Verify voice parser captures movie discovery queries with search term."""
    res1 = VoiceCommandParser.parse("find me a telugu action movie")
    assert res1 is not None
    assert res1[0] == "movie_discovery"
    assert "telugu action movie" in res1[1]

    res2 = VoiceCommandParser.parse("recommend a hindi comedy movie")
    assert res2 is not None
    assert res2[0] == "movie_discovery"
    assert "hindi comedy movie" in res2[1]

    res3 = VoiceCommandParser.parse("search movie inception")
    assert res3 is not None
    assert res3[0] == "movie_discovery"
    assert "inception" in res3[1]


def test_voice_command_dispatcher_movie_handlers():
    """Verify VoiceCommandDispatcher dispatches open_movies and movie_discovery."""
    dispatcher = VoiceCommandDispatcher()
    with patch("app.api.websocket.ws_manager.broadcast_sync") as mock_broadcast:
        assert dispatcher.dispatch("open movie hub") is True
        mock_broadcast.assert_called_with("open_movie_hub", {})

    with patch("app.api.websocket.ws_manager.broadcast_sync") as mock_broadcast:
        assert dispatcher.dispatch("find me a telugu action movie") is True
        mock_broadcast.assert_called_with(
            "movie_voice_search",
            {"query": "telugu action movie", "auto_open": True},
        )


# =============================================================================
# 4. Mood-Based Recommendations Intent Mapping (11.4)
# =============================================================================

def test_mood_based_recommendation_intents():
    """Verify recommendation engine maps mood queries to grounded genres and keywords."""
    mock_tmdb = MagicMock(spec=TMDBClient)
    mock_storage = MagicMock()
    engine = MovieRecommendationEngine(tmdb_client=mock_tmdb, storage_repo=mock_storage)

    # 1. Feel-Good
    intent1 = engine.parse_intent_deterministic("Recommend a feel-good comedy movie")
    assert "feel_good" in intent1.keywords
    assert "Comedy" in intent1.genres

    # 2. Dark & Gritty
    intent2 = engine.parse_intent_deterministic("Recommend a dark and gritty crime thriller")
    assert "dark_gritty" in intent2.keywords
    assert "Crime" in intent2.genres

    # 3. Adrenaline Rush
    intent3 = engine.parse_intent_deterministic("Suggest an adrenaline rush high-stakes action film")
    assert "adrenaline" in intent3.keywords
    assert "Action" in intent3.genres

    # 4. Mind-Bending
    intent4 = engine.parse_intent_deterministic("Recommend a mind-bending sci-fi with plot twists")
    assert "mind_bending" in intent4.keywords
    assert "Science Fiction" in intent4.genres or "Mystery" in intent4.genres

    # 5. Tearjerker
    intent5 = engine.parse_intent_deterministic("Find an emotional tearjerker drama that will make me cry")
    assert "tearjerker" in intent5.keywords
    assert "Drama" in intent5.genres

    # 6. Spine-Chilling
    intent6 = engine.parse_intent_deterministic("Find a terrifying spine-chilling horror movie")
    assert "spine_chilling" in intent6.keywords
    assert "Horror" in intent6.genres

    # 7. Cozy
    intent7 = engine.parse_intent_deterministic("Suggest a cozy relaxing family movie")
    assert "cozy" in intent7.keywords
    assert "Family" in intent7.genres


# =============================================================================
# 5. Fullscreen Poster & Session Memory Contracts (Tab Switching & Lightbox)
# =============================================================================

def test_fullscreen_poster_modal_component_contract():
    """Verify FullScreenPosterModal component and styles implement fullscreen lightbox with ESC handler."""
    from pathlib import Path

    modal_tsx = Path("src/components/MovieHub/FullScreenPosterModal.tsx").read_text(encoding="utf-8")
    modal_css = Path("src/components/MovieHub/FullScreenPosterModal.css").read_text(encoding="utf-8")

    # Contract checks in TSX
    assert "FullScreenPosterModal" in modal_tsx
    assert "handleKeyDown" in modal_tsx
    assert "e.key === 'Escape'" in modal_tsx
    assert "/original/" in modal_tsx  # Upgrades TMDB resolution to original
    assert "onClose" in modal_tsx
    assert "aria-label=\"Close full-screen poster\"" in modal_tsx

    # Contract checks in CSS
    assert ".fullscreen-poster-overlay" in modal_css
    assert "backdrop-filter: blur" in modal_css
    assert "position: fixed" in modal_css
    assert "z-index: 99999" in modal_css
    assert "object-fit: contain" in modal_css


def test_session_memory_tab_switching_contract():
    """Verify sessionStorage persistence is implemented for AI draft prompt, recommendations, and active tab."""
    from pathlib import Path

    ai_section_tsx = Path("src/components/MovieHub/AIRecommendationSection.tsx").read_text(encoding="utf-8")
    workspace_tsx = Path("src/components/MovieHub/MovieHubWorkspace.tsx").read_text(encoding="utf-8")

    # AI Recommendation draft session memory
    assert "SESSION_KEY_AI_DRAFT" in ai_section_tsx
    assert "SESSION_KEY_AI_RESPONSE" in ai_section_tsx
    assert "sessionStorage.getItem(SESSION_KEY_AI_DRAFT)" in ai_section_tsx
    assert "sessionStorage.setItem(SESSION_KEY_AI_DRAFT" in ai_section_tsx
    assert "sessionStorage.setItem(SESSION_KEY_AI_RESPONSE" in ai_section_tsx

    # DOM preservation when switching tabs (CSS display toggle instead of unmounting)
    assert "display: hubTab === 'recommendations' ? 'block' : 'none'" in workspace_tsx
    assert "display: hubTab !== 'recommendations' ? 'contents' : 'none'" in workspace_tsx

    # Workspace session memory keys
    assert "SESSION_KEY_HUB_TAB" in workspace_tsx
    assert "SESSION_KEY_SEARCH" in workspace_tsx
    assert "SESSION_KEY_CONTENT_TYPE" in workspace_tsx
    assert "SESSION_KEY_REGION" in workspace_tsx


def test_poster_click_wiring_across_components():
    """Verify outer movie card clicks open details modal, while MovieDetailsModal poster opens full-screen."""
    from pathlib import Path

    card_tsx = Path("src/components/MovieHub/MovieCard.tsx").read_text(encoding="utf-8")
    details_tsx = Path("src/components/MovieHub/MovieDetailsModal.tsx").read_text(encoding="utf-8")
    workspace_tsx = Path("src/components/MovieHub/MovieHubWorkspace.tsx").read_text(encoding="utf-8")

    # Outer card click opens details modal
    assert 'onClick={() => onOpenDetails && onOpenDetails(item)}' in card_tsx
    # Poster frame inside card does NOT intercept with stopPropagation
    assert 'hub-card-poster-frame" onClick={(e) => { e.stopPropagation()' not in card_tsx

    # Inside MovieDetailsModal: clicking poster opens full screen lightbox
    assert "isPosterFullScreen" in details_tsx
    assert "FullScreenPosterModal" in details_tsx
    assert "setIsPosterFullScreen(true)" in details_tsx



