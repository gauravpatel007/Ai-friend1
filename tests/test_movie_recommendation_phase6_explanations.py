"""Phase 6 Verification Tests: Grounded Explanations & Recommendation Presentation.

Covers exact Phase 6 requirements:
6.1 Specific LLM responsibilities (conversational explanation without fabricating film metadata).
6.2 Grounded movie explanations (specific narrative connections, no generic cliches).
6.3 Prevention of hallucinations (banned streaming claims, year tampering, unverified cast).
6.4 Recommendation presentation structure (Best Matches, Hidden Gems, More Like Your Request, Alternative Picks).
6.5 Avoid unnecessary LLM calls (single batched explanation call instead of N sequential calls).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from app.ai.movie_explanation_engine import MovieExplanationEngine
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.ai.movie_semantic_service import MovieSemanticService
from app.ai.ollama_client import OllamaClient
from app.api.movie_models import (
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
    RecommendationResponse,
    RecommendedTitleModel,
)
from app.api.tmdb_client import TMDBClient
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db() -> DatabaseManager:
    """In-memory SQLite database manager."""
    return DatabaseManager(":memory:")


@pytest.fixture
def storage_repo(mock_db: DatabaseManager) -> MovieStorageRepository:
    """Storage repository connected to in-memory database."""
    return MovieStorageRepository(mock_db)


@pytest.fixture
def sample_candidates() -> List[Tuple[MediaItemSummary, float, List[str], Dict[str, float]]]:
    """Sample ranked candidates for explanation testing."""
    c1 = MediaItemSummary(
        id=101,
        title="Inception",
        original_title="Inception",
        release_year=2010,
        original_language="en",
        media_type="movie",
        genre_ids=[878, 9648],
        genre_names=["Science Fiction", "Mystery"],
        vote_average=8.4,
        vote_count=35000,
        overview="Cobb steals corporate secrets through dream-sharing technology and is tasked with planting an idea into a CEO's mind.",
    )
    c2 = MediaItemSummary(
        id=102,
        title="Iratta",
        original_title="Iratta",
        release_year=2023,
        original_language="ml",
        media_type="movie",
        genre_ids=[80, 53, 9648],
        genre_names=["Crime", "Thriller", "Mystery"],
        vote_average=7.9,
        vote_count=650,
        overview="A tense investigation into a police officer's sudden death unveils dark family secrets, moral decay, and an unexpected ending.",
    )
    c3 = MediaItemSummary(
        id=103,
        title="Shutter Island",
        original_title="Shutter Island",
        release_year=2010,
        original_language="en",
        media_type="movie",
        genre_ids=[9648, 53],
        genre_names=["Mystery", "Thriller"],
        vote_average=8.2,
        vote_count=24000,
        overview="A U.S. Marshal investigates a psychiatric facility on an isolated island, uncovering shocking plot twists and questioning his own sanity.",
    )
    c4 = MediaItemSummary(
        id=104,
        title="Dark City",
        original_title="Dark City",
        release_year=1998,
        original_language="en",
        media_type="movie",
        genre_ids=[878, 9648],
        genre_names=["Science Fiction", "Mystery"],
        vote_average=7.6,
        vote_count=3200,
        overview="A man struggles with amnesia in a nocturnal metropolis ruled by mysterious beings who alter the city every midnight.",
    )

    return [
        (c1, 88.5, ["Matches requested genre (Science Fiction, Mystery)", "Critically acclaimed (8.4/10)"], {}),
        (c2, 82.0, ["Acclaimed hidden gem with high audience reception", "Features unpredictable plot twists"], {}),
        (c3, 79.0, ["Features unpredictable plot twists", "Critically acclaimed (8.2/10)"], {}),
        (c4, 68.0, ["Shares genre DNA", "Cult classic atmospheric mystery"], {}),
    ]


# =============================================================================
# 6.2 & 6.3 Grounded Explanations & Hallucination Safeguard Tests
# =============================================================================

def test_deterministic_grounded_fallback_accuracy():
    """Requirement 6.2 & 6.3: Grounded fallback strictly references verified metadata."""
    cand = MediaItemSummary(
        id=101,
        title="Inception",
        release_year=2010,
        original_language="en",
        media_type="movie",
        genre_names=["Science Fiction", "Mystery"],
        vote_average=8.4,
        overview="Cobb steals corporate secrets through dream-sharing technology.",
    )
    intent = ParsedRecommendationIntent(
        genres=["Science Fiction"],
        mood="mind-bending",
    )

    exp = MovieExplanationEngine.build_deterministic_grounded_explanation(
        cand,
        intent,
        match_reasons=["Features unpredictable plot twists."],
    )

    assert "Science Fiction" in exp
    assert "2010" in exp
    assert "8.4/10" in exp
    assert "Features unpredictable plot twists." in exp


def test_hallucination_safeguards_banned_streaming_claims():
    """Requirement 6.3: Explanations making unverified streaming claims are rejected."""
    cand = MediaItemSummary(
        id=101,
        title="Inception",
        release_year=2010,
        vote_average=8.4,
    )
    intent = ParsedRecommendationIntent()

    # Streaming claim -> Must be rejected
    bad_exp = "Inception is a mind-bending sci-fi thriller available on Netflix right now."
    is_valid, _ = MovieExplanationEngine.verify_and_filter_explanation(bad_exp, cand, intent)
    assert is_valid is False

    # Legitimate claim -> Must be accepted
    good_exp = "Inception connects directly to your mind-bending request with its multi-layered dream heist."
    is_valid, text = MovieExplanationEngine.verify_and_filter_explanation(good_exp, cand, intent)
    assert is_valid is True
    assert text == good_exp


def test_hallucination_safeguards_year_tampering():
    """Requirement 6.3: Reject explanations claiming incorrect release years."""
    cand = MediaItemSummary(
        id=101,
        title="Inception",
        release_year=2010,
        vote_average=8.4,
    )
    intent = ParsedRecommendationIntent()

    # Claiming 1999 when actual is 2010 -> Must be rejected
    tampered_exp = "Released in 1999, Inception redefined modern science fiction cinema."
    is_valid, _ = MovieExplanationEngine.verify_and_filter_explanation(tampered_exp, cand, intent)
    assert is_valid is False

    # Accurate year -> Must be accepted
    accurate_exp = "Released in 2010, Inception redefined modern science fiction cinema."
    is_valid, text = MovieExplanationEngine.verify_and_filter_explanation(accurate_exp, cand, intent)
    assert is_valid is True


def test_hallucination_safeguards_generic_platitudes():
    """Requirement 6.2: Reject generic platitudes ('This is an amazing movie you will love')."""
    cand = MediaItemSummary(id=101, title="Inception", release_year=2010)
    intent = ParsedRecommendationIntent()

    platitude = "This is an amazing movie you will love with great scenes."
    is_valid, _ = MovieExplanationEngine.verify_and_filter_explanation(platitude, cand, intent)
    assert is_valid is False


# =============================================================================
# 6.5 Batched Explanation Generation Tests
# =============================================================================

def test_batched_explanation_generation_single_llm_call(
    sample_candidates: List[Tuple[MediaItemSummary, float, List[str], Dict[str, float]]],
):
    """Requirement 6.5: Verify ALL candidates are explained in a SINGLE batched LLM call."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama.is_server_reachable.return_value = True

    # Return batched JSON response
    batched_json = json.dumps({
        "explanations": [
            {"id": 101, "explanation": "Inception aligns with your request through its intricate dream-within-a-dream puzzles."},
            {"id": 102, "explanation": "Iratta delivers an intense psychological investigation culminating in devastating revelations."},
            {"id": 103, "explanation": "Shutter Island explores psychological paranoia and deception in a remote island asylum."},
            {"id": 104, "explanation": "Dark City offers a surreal noir mystery where nocturnal architects manipulate human memory."},
        ]
    })
    mock_ollama.chat.return_value = batched_json

    engine = MovieExplanationEngine(ollama_client=mock_ollama)
    intent = ParsedRecommendationIntent(mood="mind-bending")

    results = engine.generate_explanations(
        sample_candidates,
        intent=intent,
        user_query="Mind-bending psychological mysteries",
    )

    # EXACTLY 1 model call must be made for all 4 candidates
    assert mock_ollama.chat.call_count == 1
    assert len(results) == 4

    assert results[0].is_ai_generated is True
    assert "dream-within-a-dream" in results[0].ai_explanation
    assert results[1].is_ai_generated is True
    assert "Iratta" in results[1].media.title
    assert "psychological investigation" in results[1].ai_explanation


def test_batched_explanation_fallback_when_ollama_offline(
    sample_candidates: List[Tuple[MediaItemSummary, float, List[str], Dict[str, float]]],
):
    """Requirement 6.5: Offline Ollama uses deterministic grounded fallback with zero user disruption."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama.is_server_reachable.return_value = False

    engine = MovieExplanationEngine(ollama_client=mock_ollama)
    intent = ParsedRecommendationIntent(mood="mind-bending")

    results = engine.generate_explanations(
        sample_candidates,
        intent=intent,
        user_query="Mind-bending psychological mysteries",
    )

    assert mock_ollama.chat.call_count == 0
    assert len(results) == 4
    for r in results:
        assert r.is_ai_generated is False
        assert len(r.ai_explanation) > 20
        assert r.media.title != ""


# =============================================================================
# 6.4 Recommendation Presentation Structure Tests
# =============================================================================

def test_presentation_section_organization_sufficient_candidates(
    sample_candidates: List[Tuple[MediaItemSummary, float, List[str], Dict[str, float]]],
):
    """Requirement 6.4: Group recommendations into Best Matches, Hidden Gems, Alternative Picks."""
    recs: List[RecommendedTitleModel] = []
    for cand, score, reasons, breakdown in sample_candidates:
        recs.append(
            RecommendedTitleModel(
                media=cand,
                score=score,
                match_reasons=reasons,
                relevance_breakdown=breakdown,
                ai_explanation="Grounded explanation",
                is_ai_generated=False,
            )
        )

    sections = MovieExplanationEngine.organize_presentation_sections(recs, min_candidates=3)
    assert sections is not None
    assert "Best Matches" in sections
    assert len(sections["Best Matches"]) >= 1

    # Candidate 102 (Iratta) has 650 votes and 7.9 rating -> Must be classified as Hidden Gems
    hidden_gem_titles = [m.media.title for m in sections.get("Hidden Gems", [])]
    assert "Iratta" in hidden_gem_titles

    # Each model in sections must have presentation_section field set
    for s_name, s_list in sections.items():
        for item in s_list:
            assert item.presentation_section == s_name


def test_presentation_sections_omitted_when_insufficient_candidates():
    """Requirement 6.4: Do not create sections if there are insufficient candidates (<3)."""
    cand = MediaItemSummary(id=1, title="Solo Candidate", vote_average=8.0)
    rec = RecommendedTitleModel(media=cand, score=85.0)

    # 1 candidate -> None
    sections_1 = MovieExplanationEngine.organize_presentation_sections([rec], min_candidates=3)
    assert sections_1 is None

    # 2 candidates -> None
    cand2 = MediaItemSummary(id=2, title="Second Candidate", vote_average=7.5)
    rec2 = RecommendedTitleModel(media=cand2, score=75.0)
    sections_2 = MovieExplanationEngine.organize_presentation_sections([rec, rec2], min_candidates=3)
    assert sections_2 is None


# =============================================================================
# End-to-End Recommendation with Grounded Sections
# =============================================================================

def test_end_to_end_recommendation_with_grounded_sections(storage_repo: MovieStorageRepository):
    """Verify recommend() produces structured presentation_sections and grounded explanations."""
    mock_tmdb = MagicMock(spec=TMDBClient)
    cand1 = MediaItemSummary(id=201, title="Inception", release_year=2010, vote_average=8.4, vote_count=35000, overview="Dream secrets.")
    cand2 = MediaItemSummary(id=202, title="Iratta", release_year=2023, vote_average=7.9, vote_count=650, overview="Police mystery.")
    cand3 = MediaItemSummary(id=203, title="Shutter Island", release_year=2010, vote_average=8.2, vote_count=24000, overview="Island asylum.")

    paged = PagedResultModel(page=1, total_pages=1, total_results=3, results=[cand1, cand2, cand3])
    mock_tmdb.discover_all.return_value = paged
    mock_tmdb.discover_movies.return_value = paged
    mock_tmdb.discover_series.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])
    mock_tmdb.get_movie_keywords.return_value = []

    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama.is_server_reachable.return_value = False

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=storage_repo,
        ollama_client=mock_ollama,
    )

    response = engine.recommend("Mind-bending mysteries with twists")
    assert isinstance(response, RecommendationResponse)
    assert len(response.recommendations) == 3
    assert response.presentation_sections is not None
    assert "Best Matches" in response.presentation_sections
    # Verify every recommendation has an explanation and match reasons
    for rec in response.recommendations:
        assert len(rec.ai_explanation) > 10
        assert rec.presentation_section is not None
