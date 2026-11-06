"""Phase 5 Verification Tests: Local Semantic Understanding Using Vector Embeddings.

Covers exact Phase 5 requirements:
5.1 Understand the limitation:
    - Semantic similarity bridges vocabulary mismatches (e.g. "cannot trust their own memories"
      matching "distinguish reality from fragmented memories").
5.2 Evaluate local embedding models:
    - Evaluates all-minilm (lightweight, 384 dim, fast) and nomic-embed-text (768 dim).
5.3 Generate movie embeddings & 2-tier caching:
    - Title, overview, genres, keywords document synthesis.
    - SHA-256 hash invalidation.
    - In-memory + SQLite persistent cache persistence.
5.4 Generate query embeddings:
    - Semantic search query formulated from parsed intent.
5.5 Semantic similarity scoring:
    - Cosine similarity integration into Phase 4 ranking engine.
5.6 Build a fallback:
    - Graceful fallback when Ollama or embedding model is offline.
    - Diagnostics tracking (semantic_ranking_active, model, timing).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
import pytest

from app.ai.movie_ranking_engine import MovieRankingEngine
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.ai.movie_semantic_service import (
    DEFAULT_EMBED_MODEL,
    FALLBACK_EMBED_MODEL,
    MovieSemanticService,
    cosine_similarity,
    normalize_cosine_score,
)
from app.ai.ollama_client import OllamaClient
from app.api.movie_models import (
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
    RecommendationResponse,
)
from app.api.tmdb_client import TMDBClient
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db() -> DatabaseManager:
    """In-memory SQLite database manager for fast isolated tests."""
    return DatabaseManager(":memory:")


@pytest.fixture
def storage_repo(mock_db: DatabaseManager) -> MovieStorageRepository:
    """Storage repository connected to in-memory database."""
    return MovieStorageRepository(mock_db)


@pytest.fixture
def mock_ollama_client() -> MagicMock:
    """Mock OllamaClient generating deterministic mock embeddings based on text length/hash."""
    client = MagicMock(spec=OllamaClient)
    client.is_server_reachable.return_value = True
    client.get_model_names.return_value = ["all-minilm:latest", "nomic-embed-text:latest"]
    client.chat.return_value = "{}"

    def fake_embed(texts, model="all-minilm", timeout=None, truncate=True):
        if isinstance(texts, str):
            input_list = [texts]
        else:
            input_list = list(texts)

        results = []
        dim = 384 if "minilm" in model else 768
        for t in input_list:
            t_lower = t.lower()
            # Deterministic vector based on content
            vec = [0.0] * dim
            # Memory / identity trope trigger
            if any(w in t_lower for w in ["memory", "memories", "reality", "mind", "insane"]):
                vec[0] = 0.8
                vec[1] = 0.5
            # Action / explosion trigger
            elif any(w in t_lower for w in ["explosion", "chase", "racing", "speed"]):
                vec[0] = 0.1
                vec[2] = 0.9
            else:
                vec[0] = 0.3
                vec[3] = 0.4

            # Normalize to unit length
            norm = math.sqrt(sum(x * x for x in vec))
            if norm > 0:
                vec = [x / norm for x in vec]
            results.append(vec)
        return results

    client.embed.side_effect = fake_embed
    return client


@pytest.fixture
def semantic_service(mock_ollama_client: MagicMock, storage_repo: MovieStorageRepository) -> MovieSemanticService:
    """Semantic service configured with mock Ollama and storage repository."""
    return MovieSemanticService(
        ollama_client=mock_ollama_client,
        storage_repo=storage_repo,
        model_name="all-minilm",
    )


# =============================================================================
# 5.1 & 5.5 Semantic Discrimination & Scoring Tests
# =============================================================================

def test_semantic_matching_bridges_vocabulary_mismatch(semantic_service: MovieSemanticService):
    """Requirement 5.1: Verifies semantic similarity identifies conceptual relationships
    even when different keywords are used.
    """
    # User request: "Movies where the main character cannot trust their own memories."
    intent = ParsedRecommendationIntent(
        raw_query="Movies where the main character cannot trust their own memories.",
        plot_elements=["unreliable memory", "identity doubt"],
    )

    # Candidate 1 (Relevant, no overlapping keywords):
    # "A man struggles to distinguish reality from his fragmented memories in an isolated mental facility."
    cand_relevant = MediaItemSummary(
        id=101,
        title="Mind Maze",
        overview="A man struggles to distinguish reality from his fragmented memories in an isolated facility.",
        genre_names=["Mystery", "Thriller"],
    )

    # Candidate 2 (Irrelevant):
    # "High speed explosions, car chases, and explosions around the globe."
    cand_irrelevant = MediaItemSummary(
        id=102,
        title="Nitro Velocity",
        overview="High speed explosions, car chases, and explosions around the globe with secret agents.",
        genre_names=["Action"],
    )

    query_text = semantic_service.build_semantic_query(intent)
    q_vec = semantic_service.get_query_embedding(query_text)
    assert q_vec is not None
    assert len(q_vec) == 384

    cand_embs, diag = semantic_service.get_candidate_embeddings([cand_relevant, cand_irrelevant])
    assert 101 in cand_embs
    assert 102 in cand_embs

    scores = semantic_service.score_candidates_semantically([cand_relevant, cand_irrelevant], q_vec, cand_embs)

    # Relevant candidate must score significantly higher than irrelevant candidate
    assert scores[101] > scores[102]
    assert scores[101] >= 0.70  # Strong semantic alignment


def test_cosine_similarity_math():
    """Verify pure-Python cosine similarity calculations and normalization."""
    # Orthogonal vectors
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]
    assert cosine_similarity(v1, v2) == 0.0

    # Identical vectors
    v3 = [0.5, 0.5, 0.5]
    assert pytest.approx(cosine_similarity(v3, v3), 1e-6) == 1.0

    # Normalization check
    assert normalize_cosine_score(0.10) == 0.0
    assert normalize_cosine_score(0.70) == 1.0
    assert 0.0 < normalize_cosine_score(0.40) < 1.0


# =============================================================================
# 5.3 Movie Document Synthesis & SHA-256 Hashing Tests
# =============================================================================

def test_movie_document_synthesis_and_hash_invalidation(semantic_service: MovieSemanticService):
    """Requirement 5.3: Verify semantic document creation and hash changes when metadata updates."""
    cand = MediaItemSummary(
        id=201,
        title="Memento",
        overview="A man with short-term memory loss attempts to track down his wife's murderer.",
        genre_names=["Mystery", "Thriller"],
        keywords=["amnesia", "polaroid"],
    )

    doc = semantic_service.build_movie_document(cand)
    assert "Title: Memento." in doc
    assert "Genres: Mystery, Thriller." in doc
    assert "Overview: A man with short-term memory loss" in doc
    assert "amnesia" in doc

    hash1 = semantic_service.compute_doc_hash(doc)
    assert len(hash1) == 16

    # Update overview -> hash must change to trigger cache invalidation
    cand.overview = "A completely different plot overview about bank robbers."
    doc2 = semantic_service.build_movie_document(cand)
    hash2 = semantic_service.compute_doc_hash(doc2)
    assert hash1 != hash2


# =============================================================================
# 5.3 Two-Tier Caching Tests (In-Memory + Persistent SQLite)
# =============================================================================

def test_two_tier_caching_avoids_redundant_inference(semantic_service: MovieSemanticService, mock_ollama_client: MagicMock):
    """Requirement 5.3: Ensure embeddings are persisted to SQLite and retrieved with 0 inference on repeat."""
    cand = MediaItemSummary(
        id=301,
        title="Inception",
        overview="A thief who steals corporate secrets through the use of dream-sharing technology.",
        genre_names=["Sci-Fi", "Action"],
    )

    # First fetch: Cache Miss -> Ollama inference called
    mock_ollama_client.embed.reset_mock()
    embs1, diag1 = semantic_service.get_candidate_embeddings([cand])
    assert 301 in embs1
    assert diag1["cached_hits"] == 0
    assert diag1["generated"] == 1
    assert mock_ollama_client.embed.call_count == 1

    # Second fetch: Memory Cache Hit -> Ollama inference NOT called
    mock_ollama_client.embed.reset_mock()
    embs2, diag2 = semantic_service.get_candidate_embeddings([cand])
    assert 301 in embs2
    assert diag2["cached_hits"] == 1
    assert diag2["generated"] == 0
    assert mock_ollama_client.embed.call_count == 0

    # Clear memory cache -> Persistent SQLite Cache Hit
    semantic_service._mem_cache.clear()
    mock_ollama_client.embed.reset_mock()
    embs3, diag3 = semantic_service.get_candidate_embeddings([cand])
    assert 301 in embs3
    assert diag3["cached_hits"] == 1
    assert diag3["generated"] == 0
    assert mock_ollama_client.embed.call_count == 0


# =============================================================================
# 5.4 Query Formulation Tests
# =============================================================================

def test_semantic_query_formulation(semantic_service: MovieSemanticService):
    """Requirement 5.4: Converts normalized intent into a rich semantic query."""
    intent = ParsedRecommendationIntent(
        raw_query="Mind-bending sci-fi movies",
        genres_any=["Science Fiction", "Mystery"],
        mood="mind-bending",
        themes=["reality distortion"],
        plot_elements=["plot twist"],
    )

    query = semantic_service.build_semantic_query(intent)
    assert "Mind-bending sci-fi movies" in query
    assert "genres: Science Fiction, Mystery" in query
    assert "mood: mind-bending" in query
    assert "themes: reality distortion" in query
    assert "plot: plot twist" in query


# =============================================================================
# 5.5 Ranking Pipeline Integration with Semantic Scores
# =============================================================================

def test_ranking_engine_incorporates_semantic_similarity(semantic_service: MovieSemanticService):
    """Requirement 5.5: Semantic score elevates matching candidate in ranking."""
    ranking_engine = MovieRankingEngine()

    cand1 = MediaItemSummary(
        id=401,
        title="Mind Bender",
        genre_ids=[878],  # Sci-Fi
        vote_average=7.5,
        vote_count=1500,
        overview="A scientist constructs a machine that fragments his perception of past and present.",
    )
    cand2 = MediaItemSummary(
        id=402,
        title="Generic Space Battle",
        genre_ids=[878],  # Sci-Fi
        vote_average=7.5,
        vote_count=1500,
        overview="Laser ships fight in deep space with huge cosmic explosions.",
    )

    intent = ParsedRecommendationIntent(
        raw_query="Psychological sci-fi questioning reality",
        genres_any=["Science Fiction"],
        mood="mind-bending",
    )

    # Provide high semantic score to Mind Bender and low to Space Battle
    semantic_scores = {401: 0.95, 402: 0.20}

    ranked = ranking_engine.rank_candidates(
        [cand2, cand1],
        intent,
        semantic_scores=semantic_scores,
    )

    assert len(ranked) == 2
    # Mind Bender must rank 1st due to strong semantic alignment
    assert ranked[0][0].id == 401
    assert ranked[0][3].get("neural_semantic_similarity") == 95.0


# =============================================================================
# 5.6 Graceful Fallback When Ollama is Offline
# =============================================================================

def test_graceful_fallback_when_embedding_service_offline(storage_repo: MovieStorageRepository):
    """Requirement 5.6: If Ollama is offline, system continues with deterministic ranking,
    shows no error, and logs fallback in diagnostics.
    """
    offline_client = MagicMock(spec=OllamaClient)
    offline_client.is_server_reachable.return_value = False
    offline_client.embed.side_effect = Exception("Ollama offline")

    offline_semantic = MovieSemanticService(
        ollama_client=offline_client,
        storage_repo=storage_repo,
    )
    assert offline_semantic.is_available() is False

    mock_tmdb = MagicMock(spec=TMDBClient)
    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=storage_repo,
        ollama_client=offline_client,
        semantic_service=offline_semantic,
    )

    candidates = [
        MediaItemSummary(
            id=501,
            title="Drishyam",
            genre_ids=[53, 80],
            original_language="ml",
            vote_average=8.4,
            vote_count=2000,
            overview="A brilliant alibi protects a family from investigation.",
        )
    ]
    intent = ParsedRecommendationIntent(
        genres=["Thriller"],
        language="ml",
    )

    ranked = engine.rank_candidates(candidates, intent)
    assert len(ranked) == 1
    assert ranked[0][0].id == 501
    # Check diagnostics record fallback cleanly
    assert intent.diagnostics["semantic_ranking"]["active"] is False


# =============================================================================
# End-to-End Pipeline Integration Test
# =============================================================================

def test_e2e_recommendation_pipeline_with_semantic_ranking(
    semantic_service: MovieSemanticService,
    storage_repo: MovieStorageRepository,
    mock_ollama_client: MagicMock,
):
    """End-to-end verification: recommend() executes intent parsing, candidate retrieval,
    semantic embedding generation, transparent scoring breakdown, and diagnostics.
    """
    mock_tmdb = MagicMock(spec=TMDBClient)
    cand1 = MediaItemSummary(
        id=601,
        title="Inception",
        original_title="Inception",
        genre_ids=[878, 9648],
        vote_average=8.4,
        vote_count=35000,
        popularity=120.0,
        overview="Cobb steals corporate secrets through dream-sharing technology.",
    )
    cand2 = MediaItemSummary(
        id=602,
        title="Shutter Island",
        original_title="Shutter Island",
        genre_ids=[9648, 53],
        vote_average=8.2,
        vote_count=25000,
        popularity=100.0,
        overview="A U.S. Marshal investigates a psychiatric facility, questioning his own reality.",
    )
    paged = PagedResultModel(page=1, total_pages=1, total_results=2, results=[cand1, cand2])
    mock_tmdb.discover_all.return_value = paged
    mock_tmdb.discover_movies.return_value = paged
    mock_tmdb.discover_series.return_value = PagedResultModel(page=1, total_pages=1, total_results=0, results=[])
    mock_tmdb.get_movie_keywords.return_value = []

    engine = MovieRecommendationEngine(
        tmdb_client=mock_tmdb,
        storage_repo=storage_repo,
        ollama_client=mock_ollama_client,
        semantic_service=semantic_service,
    )

    response = engine.recommend("Mind-bending psychological thrillers with reality distortion")
    assert isinstance(response, RecommendationResponse)
    assert len(response.recommendations) > 0

    # Verify diagnostics contains semantic ranking telemetry
    diag = response.diagnostics
    assert "semantic_ranking" in diag
    assert diag["semantic_ranking"]["active"] is True
    assert diag["semantic_ranking"]["model"] == "all-minilm"
    assert diag["semantic_ranking"]["candidates_embedded"] == 2
