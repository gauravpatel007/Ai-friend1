"""Phase 2 Verification Test Suite - AI Intent Understanding & Structured Outputs.

Verifies:
1. Pydantic validation of StructuredOllamaIntent schema.
2. Canonical genre and colloquial term resolution (movie_taxonomy).
3. OR vs AND genre conditions (genres_any vs genres_all).
4. Plot-based discovery extraction (unexpected endings, unreliable narrators, time loops).
5. Controlled 1-time repair handling and graceful deterministic fallback.
6. Evaluation accuracy on benchmark queries.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from app.ai.movie_recommendation_engine import (
    GENRE_TAXONOMY,
    MovieRecommendationEngine,
)
from app.ai.movie_taxonomy import (
    TMDB_MOVIE_GENRES,
    normalize_genre_name,
    resolve_plot_elements,
    resolve_mood_semantics,
)
from app.api.movie_models import (
    ParsedRecommendationIntent,
    RecommendationQueryType,
    StructuredOllamaIntent,
)


@pytest.fixture
def mock_engine() -> MovieRecommendationEngine:
    mock_tmdb = MagicMock()
    mock_tmdb.is_configured.return_value = True
    mock_repo = MagicMock()
    mock_ollama = MagicMock()
    mock_ollama.is_server_reachable.return_value = True

    return MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=mock_repo,
        ollama_client=mock_ollama,
        default_model="llama3.2:3b",
    )


# -----------------------------------------------------------------------------
# 1. StructuredOllamaIntent Schema & Validation Tests
# -----------------------------------------------------------------------------

def test_structured_ollama_intent_schema_valid() -> None:
    """Ensure StructuredOllamaIntent produces a valid JSON schema with all required Phase 2 fields."""
    schema = StructuredOllamaIntent.model_json_schema()
    assert "properties" in schema
    props = schema["properties"]
    assert "query_type" in props
    assert "genres_any" in props
    assert "genres_all" in props
    assert "moods" in props
    assert "themes" in props
    assert "plot_elements" in props
    assert "keywords_any" in props
    assert "reference_titles" in props
    assert "original_languages" in props
    assert "confidence" in props


def test_structured_ollama_intent_instantiation_and_validation() -> None:
    """Verify StructuredOllamaIntent parses realistic JSON without loss."""
    raw = {
        "query_type": "plot_based_discovery",
        "genres_any": ["Science Fiction", "Mystery", "Thriller"],
        "genres_all": [],
        "moods": ["mind-bending"],
        "themes": ["psychological", "reality distortion"],
        "plot_elements": ["unexpected plot twists", "unpredictable revelations"],
        "keywords_any": ["non-linear narrative", "unreliable narrator", "reality bending"],
        "reference_titles": [],
        "original_languages": [],
        "countries": [],
        "release_year_from": None,
        "release_year_to": None,
        "must_include": ["plot twists"],
        "must_exclude": [],
        "soft_preferences": ["strong storytelling"],
        "confidence": 0.94,
    }
    intent = StructuredOllamaIntent.model_validate(raw)
    assert intent.query_type == "plot_based_discovery"
    assert len(intent.genres_any) == 3
    assert "mind-bending" in intent.moods
    assert intent.confidence == 0.94


# -----------------------------------------------------------------------------
# 2. Canonical Taxonomy Resolution Tests
# -----------------------------------------------------------------------------

def test_normalize_genre_name_variants() -> None:
    """Verify colloquial genre terms map to canonical TMDB movie genres."""
    assert normalize_genre_name("sci-fi") == "Science Fiction"
    assert normalize_genre_name("scifi") == "Science Fiction"
    assert normalize_genre_name("science fiction") == "Science Fiction"
    assert normalize_genre_name("rom-com") == "Romance"
    assert normalize_genre_name("thrillers") == "Thriller"
    assert normalize_genre_name("comedies") == "Comedy"


def test_resolve_plot_elements_taxonomy() -> None:
    """Verify plot element dictionary matches high-concept devices."""
    res_twist = resolve_plot_elements("Movies with unexpected endings and shocking twists")
    assert any(x["aliases"][0] in ("unexpected ending", "plot twist") for x in res_twist)

    res_loops = resolve_plot_elements("Movies involving time loops or repeating day")
    assert any("time loop" in x["aliases"] for x in res_loops)

    res_multiverse = resolve_plot_elements("Films about parallel universes and alternate realities")
    assert any("parallel universe" in x["aliases"] for x in res_multiverse)


# -----------------------------------------------------------------------------
# 3. Deterministic Parsing: OR vs AND & Plot Elements
# -----------------------------------------------------------------------------

def test_deterministic_or_vs_and_logic(mock_engine: MovieRecommendationEngine) -> None:
    """Verify 'or' between genres places them in genres_any."""
    intent_or = mock_engine.parse_intent_deterministic("Recommend a sci-fi or psychological mystery")
    assert len(intent_or.genres_any) >= 2
    assert intent_or.genres_all == []
    assert "Science Fiction" in intent_or.genres
    assert "Mystery" in intent_or.genres

    intent_and = mock_engine.parse_intent_deterministic("Romantic comedy movies")
    assert "Romance" in intent_and.genres_all
    assert "Comedy" in intent_and.genres_all


def test_deterministic_plot_element_discovery(mock_engine: MovieRecommendationEngine) -> None:
    """Verify Category E queries classify as PLOT_BASED_DISCOVERY."""
    q1 = mock_engine.parse_intent_deterministic("Movies with unexpected endings")
    assert q1.query_type == RecommendationQueryType.PLOT_BASED_DISCOVERY
    assert "unexpected endings" in q1.plot_elements or any("unexpected" in pe for pe in q1.plot_elements)

    q2 = mock_engine.parse_intent_deterministic("Movies involving time loops")
    assert q2.query_type == RecommendationQueryType.PLOT_BASED_DISCOVERY
    assert any("time loop" in pe for pe in q2.plot_elements)


def test_deterministic_regional_discovery(mock_engine: MovieRecommendationEngine) -> None:
    """Verify Category D queries classify as REGIONAL_DISCOVERY."""
    q_mal = mock_engine.parse_intent_deterministic("Underrated Malayalam thrillers")
    assert q_mal.query_type == RecommendationQueryType.REGIONAL_DISCOVERY
    assert q_mal.language == "ml"
    assert "IN" in q_mal.countries

    q_guj = mock_engine.parse_intent_deterministic("Best Gujarati movies")
    assert q_guj.query_type == RecommendationQueryType.REGIONAL_DISCOVERY
    assert q_guj.language == "gu"
    assert q_guj.region == "gujarati"


# -----------------------------------------------------------------------------
# 4. LLM Intent Extraction with 1-Time Repair & Graceful Fallback
# -----------------------------------------------------------------------------

def test_llm_intent_extraction_successful(mock_engine: MovieRecommendationEngine) -> None:
    """Verify parse_intent_with_llm accurately merges structured JSON from Ollama."""
    mock_payload = {
        "query_type": "plot_based_discovery",
        "genres_any": ["Science Fiction", "Mystery"],
        "genres_all": [],
        "moods": ["mind-bending"],
        "themes": ["psychological"],
        "plot_elements": ["plot twists"],
        "keywords_any": ["unreliable narrator"],
        "reference_titles": [],
        "original_languages": [],
        "countries": [],
        "release_year_from": None,
        "release_year_to": None,
        "must_include": [],
        "must_exclude": [],
        "soft_preferences": [],
        "confidence": 0.95,
    }
    mock_engine.ollama_client.chat.return_value = json.dumps(mock_payload)

    intent = mock_engine.parse_intent_with_llm("Recommend a mind-bending sci-fi with plot twists")
    assert intent.query_type == RecommendationQueryType.PLOT_BASED_DISCOVERY
    assert "Science Fiction" in intent.genres_any
    assert "Mystery" in intent.genres_any
    assert "plot twists" in intent.plot_elements
    assert intent.confidence == 0.95


def test_llm_intent_extraction_one_time_repair(mock_engine: MovieRecommendationEngine) -> None:
    """Verify parse_intent_with_llm attempts 1 repair when first response is invalid JSON."""
    invalid_response = "Not valid JSON: { broken }"
    valid_repaired_payload = {
        "query_type": "regional_discovery",
        "genres_any": ["Thriller"],
        "genres_all": ["Thriller"],
        "moods": ["tense"],
        "themes": ["investigation"],
        "plot_elements": [],
        "keywords_any": ["underrated"],
        "reference_titles": [],
        "original_languages": ["ml"],
        "countries": ["IN"],
        "release_year_from": None,
        "release_year_to": None,
        "must_include": ["Malayalam"],
        "must_exclude": [],
        "soft_preferences": ["underrated"],
        "confidence": 0.93,
    }

    mock_engine.ollama_client.chat.side_effect = [
        invalid_response,
        json.dumps(valid_repaired_payload),
    ]

    intent = mock_engine.parse_intent_with_llm("Underrated Malayalam thrillers")
    assert mock_engine.ollama_client.chat.call_count == 2
    assert intent.query_type == RecommendationQueryType.REGIONAL_DISCOVERY
    assert intent.language == "ml"
    assert intent.confidence == 0.93


def test_llm_intent_extraction_fallback_to_deterministic_when_offline(mock_engine: MovieRecommendationEngine) -> None:
    """Verify fallback to deterministic parser when Ollama server is unreachable."""
    mock_engine.ollama_client.is_server_reachable.return_value = False

    intent = mock_engine.parse_intent_with_llm("Movies like Glass Onion")
    assert intent.intent_type == "similar_to"
    assert intent.reference_title == "Glass Onion"
