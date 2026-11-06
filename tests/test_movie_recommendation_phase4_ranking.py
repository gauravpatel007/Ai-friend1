"""Phase 4 Verification Tests: Real Movie Relevance & Multi-Signal Ranking Engine.

Covers exact Phase 4 requirements:
4.1 Hard vs Soft Filter separation (language/era/exclusions hard-enforced; atmosphere/underrated soft-scored).
4.2 Normalized feature representation (CandidateFeatures extraction, overview tokens, franchise keys).
4.3 Configurable relevance scoring (weights customization, linear combination, breakdown reporting).
4.4 Quality & credibility scoring (Bayesian vote smoothing, avoiding popularity dominance and vote cutoffs).
4.5 Specific query handling:
    - "Underrated Malayalam psychological thriller" ranks acclaimed hidden gems highest.
    - "Mind-bending sci-fi or psychological mystery with plot twists" rewards disjunctive elements.
4.6 Diversity controls & franchise repetition damping (preventing 5 identical sequels from clogging results).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.api.movie_models import (
    GenreModel,
    MediaDetailsModel,
    MediaItemSummary,
    PagedResultModel,
    ParsedRecommendationIntent,
    RecommendationQueryType,
    RelevanceWeightsModel,
)
from app.ai.movie_ranking_engine import (
    CandidateFeatures,
    MovieRankingEngine,
    extract_candidate_features,
    extract_franchise_key,
)
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository


@pytest.fixture
def ranking_engine() -> MovieRankingEngine:
    """Provide a default MovieRankingEngine instance."""
    return MovieRankingEngine()


@pytest.fixture
def mock_storage_repo() -> MovieStorageRepository:
    """Provide a mocked MovieStorageRepository."""
    repo = MagicMock(spec=MovieStorageRepository)
    repo.get_preferences.return_value = None
    repo.get_watched.return_value = []
    return repo


@pytest.fixture
def sample_candidates() -> list[MediaItemSummary]:
    """Sample diverse candidates for ranking tests."""
    return [
        MediaItemSummary(
            id=1,
            title="Inception",
            original_title="Inception",
            media_type="movie",
            genre_ids=[878, 9648, 28],
            original_language="en",
            origin_country=["US"],
            release_year=2010,
            vote_average=8.4,
            vote_count=35000,
            popularity=110.0,
            overview="Cobb steals corporate secrets through dream-sharing technology and is tasked with planting an idea into a CEO's mind.",
            retrieval_source="recommendation",
        ),
        MediaItemSummary(
            id=2,
            title="Shutter Island",
            original_title="Shutter Island",
            media_type="movie",
            genre_ids=[9648, 53, 18],
            original_language="en",
            origin_country=["US"],
            release_year=2010,
            vote_average=8.2,
            vote_count=24000,
            popularity=95.0,
            overview="A U.S. Marshal investigates the disappearance of a murderer from a hospital for the criminally insane, uncovering shocking plot twists and questioning his own sanity.",
            retrieval_source="similar",
        ),
        MediaItemSummary(
            id=3,
            title="Iratta",
            original_title="Iratta",
            media_type="movie",
            genre_ids=[80, 53, 9648],
            original_language="ml",
            origin_country=["IN"],
            release_year=2023,
            vote_average=7.9,
            vote_count=650,
            popularity=15.0,
            overview="A tense investigation into a police officer's sudden death unveils dark family secrets, moral decay, and an unexpected ending.",
            retrieval_source="keyword_discover",
        ),
        MediaItemSummary(
            id=4,
            title="Drishyam",
            original_title="Drishyam",
            media_type="movie",
            genre_ids=[80, 53, 18],
            original_language="ml",
            origin_country=["IN"],
            release_year=2013,
            vote_average=8.5,
            vote_count=2200,
            popularity=22.0,
            overview="A cable operator goes to extreme lengths to protect his family after an uninvited crisis, creating a brilliant alibi and puzzle investigation.",
            retrieval_source="genre_discover",
        ),
        MediaItemSummary(
            id=5,
            title="Generic Blockbuster 4",
            original_title="Generic Blockbuster 4",
            media_type="movie",
            genre_ids=[28, 12],
            original_language="en",
            origin_country=["US"],
            release_year=2021,
            vote_average=5.9,
            vote_count=50000,
            popularity=300.0,
            overview="High speed explosions, car chases, and explosions around the globe.",
            retrieval_source="broad_popularity_fallback",
        ),
    ]


# =============================================================================
# 4.1 Hard Filters vs Soft Preferences
# =============================================================================


def test_hard_filters_drop_violating_candidates(ranking_engine: MovieRankingEngine, sample_candidates: list[MediaItemSummary]):
    """Verify explicit language and release bounds strictly eliminate ineligible candidates."""
    # Intent requires Malayalam language
    intent_ml = ParsedRecommendationIntent(
        language="ml",
        original_languages=["ml"],
        genres=["Thriller"],
        genre_ids=[53],
    )

    ranked = ranking_engine.rank_candidates(sample_candidates, intent_ml, limit=10)
    ranked_ids = [c[0].id for c in ranked]

    # Only Malayalam titles (3: Iratta, 4: Drishyam) should remain; English blockbusters dropped
    assert 3 in ranked_ids
    assert 4 in ranked_ids
    assert 1 not in ranked_ids  # Inception (en) dropped by hard filter
    assert 5 not in ranked_ids  # Generic Blockbuster (en) dropped by hard filter


def test_soft_preferences_do_not_drop_candidates(ranking_engine: MovieRankingEngine, sample_candidates: list[MediaItemSummary]):
    """Verify soft preferences (e.g. mood, themes) adjust score without dropping candidates."""
    intent_soft = ParsedRecommendationIntent(
        mood="mind-bending",
        keywords_any=["plot twist"],
    )

    ranked = ranking_engine.rank_candidates(sample_candidates, intent_soft, limit=10)
    # All candidates without hard violations remain eligible and are ranked by relevance
    assert len(ranked) == len(sample_candidates)

    # Shutter Island and Inception should rank top due to mind-bending/twist themes
    top_id = ranked[0][0].id
    assert top_id in (1, 2)


# =============================================================================
# 4.2 Normalized Feature Representation
# =============================================================================


def test_extract_candidate_features(sample_candidates: list[MediaItemSummary]):
    """Verify CandidateFeatures extraction correctly populates tokens, genres, and metadata."""
    cand = sample_candidates[1]  # Shutter Island
    feats = extract_candidate_features(cand)

    assert feats.movie_id == 2
    assert feats.title == "Shutter Island"
    assert "Mystery" in feats.genre_names
    assert "Thriller" in feats.genre_names
    assert "insane" in feats.overview_tokens
    assert "plot" in feats.overview_tokens
    assert feats.franchise_key == "shutter island"
    assert feats.vote_average == 8.2
    assert feats.vote_count == 24000


def test_extract_franchise_key():
    """Verify franchise cluster key extraction strips numbers, roman numerals, and subtitles."""
    assert extract_franchise_key("John Wick") == "john wick"
    assert extract_franchise_key("John Wick: Chapter 2") == "john wick"
    assert extract_franchise_key("John Wick: Chapter 3 - Parabellum") == "john wick"
    assert extract_franchise_key("Glass Onion: A Knives Out Mystery") == "knives out"
    assert extract_franchise_key("Spider-Man: Homecoming") == "spider-man"
    assert extract_franchise_key("The Dark Knight Rises") == "the dark knight"


# =============================================================================
# 4.3 Configurable Relevance Weights & Scoring
# =============================================================================


def test_configurable_relevance_weights():
    """Verify custom weights change normalized distribution and influence ranking."""
    default_engine = MovieRankingEngine()
    w_default = default_engine.get_normalized_weights()
    assert round(w_default["semantic_plot"], 2) == 0.30
    assert round(w_default["genre_relevance"], 2) == 0.20
    assert round(w_default["quality_credibility"], 2) == 0.05

    # Heavy genre emphasis
    custom_weights = RelevanceWeightsModel(
        semantic_plot=0.10,
        genre_relevance=0.60,
        theme_keywords=0.10,
        mood_atmosphere=0.05,
        source_signal=0.05,
        quality_credibility=0.05,
        contextual_preferences=0.05,
    )
    custom_engine = MovieRankingEngine(weights=custom_weights)
    w_custom = custom_engine.get_normalized_weights()
    assert round(w_custom["genre_relevance"], 2) == 0.60


def test_score_breakdown_transparency(ranking_engine: MovieRankingEngine, sample_candidates: list[MediaItemSummary]):
    """Verify candidate scoring outputs transparent breakdown for all 7 signals."""
    intent = ParsedRecommendationIntent(
        genres_any=["Science Fiction", "Mystery"],
        mood="mind-bending",
        plot_elements=["plot twist"],
    )

    score, reasons, features, breakdown = ranking_engine.score_candidate(sample_candidates[0], intent)

    assert 0.0 <= score <= 100.0
    assert "semantic_plot" in breakdown
    assert "genre_relevance" in breakdown
    assert "theme_keywords" in breakdown
    assert "mood_atmosphere" in breakdown
    assert "source_signal" in breakdown
    assert "quality_credibility" in breakdown
    assert "contextual_preferences" in breakdown
    assert len(reasons) >= 1


# =============================================================================
# 4.4 Quality & Credibility Scoring (Popularity vs Acclaim)
# =============================================================================


def test_quality_scoring_prevents_raw_popularity_dominance(ranking_engine: MovieRankingEngine):
    """Verify a high-quality movie with moderate votes outranks a low-rated blockbuster with huge votes."""
    acclaimed_gem = MediaItemSummary(
        id=10,
        title="Acclaimed Indie Gem",
        vote_average=8.4,
        vote_count=350,
        popularity=12.0,
    )
    mediocre_blockbuster = MediaItemSummary(
        id=20,
        title="Mediocre Blockbuster",
        vote_average=5.4,
        vote_count=80000,
        popularity=450.0,
    )

    q_gem, _ = ranking_engine.score_quality_credibility(extract_candidate_features(acclaimed_gem))
    q_blockbuster, _ = ranking_engine.score_quality_credibility(extract_candidate_features(mediocre_blockbuster))

    # Acclaimed gem with 8.4 rating must beat 5.4 blockbuster despite having far fewer votes
    assert q_gem > q_blockbuster


# =============================================================================
# 4.5 Specific Query Ranking Behavior
# =============================================================================


def test_underrated_malayalam_psychological_thriller(ranking_engine: MovieRankingEngine, sample_candidates: list[MediaItemSummary]):
    """Requirement 4.5: 'Underrated Malayalam psychological thriller' ranks Iratta & Drishyam above mainstream blockbusters."""
    intent = ParsedRecommendationIntent(
        language="ml",
        original_languages=["ml"],
        region="malayalam",
        genres=["Thriller", "Mystery"],
        genre_ids=[53, 9648],
        keywords=["underrated"],
        plot_elements=["psychological"],
    )

    ranked = ranking_engine.rank_candidates(sample_candidates, intent, limit=5)
    assert len(ranked) >= 2

    # Malayalam hidden gem thriller (Iratta / Drishyam) must be #1
    top_item = ranked[0][0]
    assert top_item.original_language == "ml"
    assert top_item.id in (3, 4)

    # English titles must not appear
    for item, _, _, _ in ranked:
        assert item.original_language == "ml"


def test_disjunctive_mind_bending_query(ranking_engine: MovieRankingEngine, sample_candidates: list[MediaItemSummary]):
    """Requirement 4.5: 'Mind-bending sci-fi or psychological mystery with plot twists' rewards either branch."""
    intent = ParsedRecommendationIntent(
        genres_any=["Science Fiction", "Mystery"],
        mood="mind-bending",
        plot_elements=["plot twist"],
    )

    ranked = ranking_engine.rank_candidates(sample_candidates, intent, limit=5)
    top_titles = [c[0].title for c in ranked[:2]]

    # Both Inception (Sci-Fi) and Shutter Island (Mystery with twists) must be the top 2
    assert "Inception" in top_titles
    assert "Shutter Island" in top_titles


# =============================================================================
# 4.6 Diversity Controls & Franchise Damping
# =============================================================================


def test_controlled_diversity_franchise_damping(ranking_engine: MovieRankingEngine):
    """Requirement 4.6: Excessive sequels from the same franchise are damped to present diverse alternatives."""
    franchise_candidates = [
        MediaItemSummary(
            id=101,
            title="John Wick",
            genre_ids=[28, 53],
            vote_average=7.4,
            popularity=80.0,
            overview="An ex-hitman comes out of retirement to track down the gangsters that took everything from him.",
        ),
        MediaItemSummary(
            id=102,
            title="John Wick: Chapter 2",
            genre_ids=[28, 53],
            vote_average=7.3,
            popularity=75.0,
            overview="Legendary hitman John Wick is forced out of retirement by a former associate bound by a blood oath.",
        ),
        MediaItemSummary(
            id=103,
            title="John Wick: Chapter 3 - Parabellum",
            genre_ids=[28, 53],
            vote_average=7.4,
            popularity=76.0,
            overview="John Wick is on the run after killing a member of the international assassin's guild.",
        ),
        MediaItemSummary(
            id=104,
            title="John Wick: Chapter 4",
            genre_ids=[28, 53],
            vote_average=7.7,
            popularity=85.0,
            overview="John Wick uncovers a path to defeating the High Table with martial arts and gun violence.",
        ),
        MediaItemSummary(
            id=201,
            title="Nobody",
            genre_ids=[28, 53],
            vote_average=7.3,
            popularity=65.0,
            overview="A bystander who intervenes to help a woman becomes the target of a vengeful drug lord.",
        ),
        MediaItemSummary(
            id=202,
            title="Atomic Blonde",
            genre_ids=[28, 53, 9648],
            vote_average=6.5,
            popularity=45.0,
            overview="An undercover MI6 agent is sent to Berlin during the Cold War to investigate murder of a fellow agent.",
        ),
        MediaItemSummary(
            id=203,
            title="The Raid: Redemption",
            genre_ids=[28, 53],
            vote_average=7.6,
            popularity=50.0,
            overview="An elite squad is tasked with infiltrating a high-rise building run by a ruthless drug lord.",
        ),
    ]

    intent = ParsedRecommendationIntent(
        reference_title="John Wick",
        genres_any=["Action", "Thriller"],
        genre_ids=[28, 53],
    )

    # Rank with diversity enabled
    ranked_diverse = ranking_engine.rank_candidates(
        franchise_candidates,
        intent,
        limit=5,
        apply_diversity=True,
        franchise_discount=0.60,
    )
    selected_titles = [item[0].title for item in ranked_diverse]

    # Verify that the top 5 is NOT 4 John Wick movies in a row!
    jw_count = sum(1 for t in selected_titles if "John Wick" in t)
    assert jw_count <= 2, f"Expected at most 2 John Wick titles in top 5, but got {jw_count}: {selected_titles}"

    # Diverse high-relevance alternatives like 'Nobody' or 'The Raid' must be included
    diverse_alternatives = [t for t in selected_titles if t in ("Nobody", "The Raid: Redemption", "Atomic Blonde")]
    assert len(diverse_alternatives) >= 2, f"Expected diverse alternatives in top 5, got {selected_titles}"
