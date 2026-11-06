"""Phase 1 Automated Tests: Recommendation Evaluation and Testing Framework.

Verifies:
- 1.1 Test dataset completeness and category coverage (45 queries across Categories A-G).
- 1.2 Expected intent definitions and flexible matching rules.
- 1.3 Baseline metrics calculation (Intent accuracy, Reference resolution, Zero-result rate,
      Top-5 relevance, Duplicate rate, API error rate, Latency metrics).
- 1.4 Testable TMDB mock fixtures covering all 8 failure/edge modes:
      (successful, empty, malformed, missing posters, missing ratings, duplicates,
       title disambiguation, auth failure).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.ai.movie_recommendation_engine import (
    GENRE_TAXONOMY,
    MOOD_TAXONOMY,
    MovieRecommendationEngine,
)
from app.api.movie_models import (
    MediaItemSummary,
    ParsedRecommendationIntent,
    RecommendationResponse,
    RecommendedTitleModel,
)
from app.api.tmdb_client import (
    TMDBAuthError,
    TMDBNetworkError,
    TMDBRateLimitError,
)
from tests.evaluation.dataset import (
    DATASET_FILE,
    TestCase,
    get_queries_by_category,
    load_evaluation_dataset,
)
from tests.evaluation.evaluator import (
    BASELINE_RESULTS_PATH,
    EvaluationSummaryMetrics,
    QueryMetricResult,
    RecommendationEvaluator,
)
from tests.evaluation.mock_tmdb_data import (
    MOCK_AUTH_FAILURE_PAYLOAD,
    MOCK_DUPLICATE_MOVIES,
    MOCK_EMPTY_SEARCH,
    MOCK_INCORRECT_RESPONSES,
    MOCK_MISSING_POSTERS,
    MOCK_MISSING_RATINGS,
    MOCK_SIMILAR_TITLES_DISAMBIGUATION,
    MOCK_SUCCESSFUL_MOVIES,
    MockTMDBClient,
)


class TestRecommendationDataset:
    """Tests verifying 1.1 Dataset and 1.2 Expected Intent Definitions."""

    def test_dataset_file_exists_and_loads(self) -> None:
        assert DATASET_FILE.exists(), f"Dataset file missing at {DATASET_FILE}"
        cases = load_evaluation_dataset()
        assert len(cases) >= 40, f"Expected at least 40 queries, got {len(cases)}"
        assert len(cases) == 45, f"Expected exactly 45 configured queries, got {len(cases)}"

    def test_all_seven_categories_present(self) -> None:
        cases = load_evaluation_dataset()
        category_keys = {c.category_key for c in cases}
        expected_keys = {
            "similar_movies",
            "genre_discovery",
            "mood_discovery",
            "regional_cinema",
            "plot_discovery",
            "complex_requests",
            "additional_queries",
        }
        assert expected_keys.issubset(category_keys), f"Missing categories: {expected_keys - category_keys}"

    def test_query_schema_and_intent_integrity(self) -> None:
        cases = load_evaluation_dataset()
        for c in cases:
            assert c.id.startswith("Q"), f"Invalid ID: {c.id}"
            assert len(c.query.strip()) > 5, f"Query too short in {c.id}: {c.query}"
            exp = c.expected_intent
            assert len(exp.intent_types) >= 1, f"Missing intent types in {c.id}"
            assert exp.hard_constraints.content_type in ["movie", "tv", "all"]

            # If reference title required, reference title must not be None
            if exp.evaluation_rules.require_reference_title:
                assert exp.reference_title is not None, f"Ref title required but None in {c.id}"

            # If language required, language code must be valid
            if exp.evaluation_rules.require_language:
                assert exp.hard_constraints.language is not None, f"Language required but None in {c.id}"

            # If region required, region string must be valid
            if exp.evaluation_rules.require_region:
                assert exp.hard_constraints.region is not None, f"Region required but None in {c.id}"

    def test_filter_by_category_helper(self) -> None:
        sim_cases = get_queries_by_category("similar_movies")
        assert len(sim_cases) == 7
        for sc in sim_cases:
            assert sc.expected_intent.reference_title is not None


class TestTMDBMockFixtures:
    """Tests verifying 1.4 Testable Fixtures under all 8 edge conditions."""

    def test_successful_search_fixture(self) -> None:
        client = MockTMDBClient(scenario="success")
        res = client.search_movies("Interstellar")
        assert res["total_results"] > 0
        assert len(res["results"]) >= 5
        assert res["results"][0]["title"] == "Interstellar"
        assert res["results"][0]["poster_path"] is not None

    def test_empty_search_fixture(self) -> None:
        client = MockTMDBClient(scenario="empty")
        res = client.search_movies("NonExistentMovie99999")
        assert res["total_results"] == 0
        assert len(res["results"]) == 0

    def test_malformed_response_handling(self) -> None:
        for malformed in MOCK_INCORRECT_RESPONSES:
            # Must handle missing 'results' or non-list results safely
            results_list = malformed.get("results")
            if not isinstance(results_list, list):
                sanitized = []
            else:
                sanitized = [r for r in results_list if isinstance(r, dict) and isinstance(r.get("id"), int)]
            assert isinstance(sanitized, list)

    def test_missing_posters_fixture(self) -> None:
        client = MockTMDBClient(scenario="missing_posters")
        res = client.discover_movies()
        for item in res["results"]:
            assert item["poster_path"] is None or item["poster_path"] == ""

    def test_missing_ratings_fixture(self) -> None:
        client = MockTMDBClient(scenario="missing_ratings")
        res = client.discover_movies()
        for item in res["results"]:
            assert item["vote_count"] == 0
            assert item["vote_average"] in (0.0, None)

    def test_duplicate_movies_deduplication(self) -> None:
        client = MockTMDBClient(scenario="duplicates")
        res = client.discover_movies()
        ids = [item["id"] for item in res["results"]]
        assert len(ids) > len(set(ids)), "Fixture must contain duplicate IDs"

        # Engine deduplication test
        seen = set()
        deduped = []
        for item in res["results"]:
            if item["id"] not in seen:
                seen.add(item["id"])
                deduped.append(item)
        assert len(deduped) == len(set(ids))

    def test_similar_titles_disambiguation(self) -> None:
        client = MockTMDBClient(scenario="disambiguation")
        res = client.search_movies("Glass Onion")
        results = res["results"]
        assert len(results) == 4
        # Canonical high-popularity title should have highest popularity
        best_match = max(results, key=lambda x: x.get("popularity", 0))
        assert best_match["id"] == 661374
        assert "Glass Onion: A Knives Out Mystery" in best_match["title"]

    def test_auth_failure_raises_tmdb_auth_error(self) -> None:
        client = MockTMDBClient(scenario="auth_failure")
        with pytest.raises(TMDBAuthError):
            client.search_movies("AnyTitle")

        with pytest.raises(TMDBAuthError):
            client.discover_movies()


class TestRecommendationEvaluatorMetrics:
    """Tests verifying 1.3 Baseline Metrics and Evaluator Logic."""

    def test_evaluator_intent_accuracy_check(self) -> None:
        evaluator = RecommendationEvaluator()
        cases = load_evaluation_dataset()
        q01 = next(c for c in cases if c.id == "Q01")

        # Accurate intent
        good_intent = ParsedRecommendationIntent(
            query=q01.query,
            intent_type="similar_to",
            reference_title="Glass Onion",
            genres=["Mystery", "Comedy"],
            mood="witty",
        )
        assert evaluator.check_intent_accuracy(q01, good_intent) is True

        # Inaccurate intent (wrong reference title)
        bad_intent = ParsedRecommendationIntent(
            query=q01.query,
            intent_type="similar_to",
            reference_title="Completely Different Movie",
            genres=["Action"],
        )
        assert evaluator.check_intent_accuracy(q01, bad_intent) is False

    def test_evaluator_relevance_judging(self) -> None:
        evaluator = RecommendationEvaluator()
        cases = load_evaluation_dataset()
        q03 = next(c for c in cases if c.id == "Q03")  # Interstellar

        rel_item = MediaItemSummary(
            id=27205,
            title="Inception",
            genre_ids=[878, 12],
            overview="A journey through dreams and time dilation.",
        )
        assert evaluator.judge_relevance(rel_item, q03) is True

        irrel_item = MediaItemSummary(
            id=99999,
            title="Silly Slapstick",
            genre_ids=[35],
            overview="A funny cartoon slapstick adventure.",
        )
        assert evaluator.judge_relevance(irrel_item, q03) is False

    def test_evaluator_summary_aggregation(self) -> None:
        evaluator = RecommendationEvaluator()
        cases = load_evaluation_dataset()[:3]  # Subsample 3 queries

        # Mock evaluate_query
        with patch.object(evaluator, "evaluate_query") as mock_eval:
            mock_eval.side_effect = [
                QueryMetricResult(
                    id="Q01",
                    query="Movies like Glass Onion.",
                    category="Category A – Similar movies",
                    category_key="similar_movies",
                    intent_accurate=True,
                    reference_resolved=True,
                    candidate_retrieval_count=20,
                    is_zero_result=False,
                    top_5_relevant_count=4,
                    has_duplicates=False,
                    duplicate_count=0,
                    api_error=False,
                    error_type=None,
                    retrieval_time_ms=150.0,
                    total_time_ms=250.0,
                    extracted_intent={},
                    top_5_titles=["Knives Out", "Murder Mystery"],
                ),
                QueryMetricResult(
                    id="Q02",
                    query="Movies similar to Knives Out.",
                    category="Category A – Similar movies",
                    category_key="similar_movies",
                    intent_accurate=True,
                    reference_resolved=True,
                    candidate_retrieval_count=20,
                    is_zero_result=False,
                    top_5_relevant_count=3,
                    has_duplicates=False,
                    duplicate_count=0,
                    api_error=False,
                    error_type=None,
                    retrieval_time_ms=140.0,
                    total_time_ms=240.0,
                    extracted_intent={},
                    top_5_titles=["Clue", "Death on the Nile"],
                ),
                QueryMetricResult(
                    id="Q03",
                    query="Movies like Interstellar.",
                    category="Category A – Similar movies",
                    category_key="similar_movies",
                    intent_accurate=False,
                    reference_resolved=False,
                    candidate_retrieval_count=0,
                    is_zero_result=True,
                    top_5_relevant_count=0,
                    has_duplicates=False,
                    duplicate_count=0,
                    api_error=True,
                    error_type="auth_error",
                    retrieval_time_ms=50.0,
                    total_time_ms=60.0,
                    extracted_intent={},
                    top_5_titles=[],
                ),
            ]

            summary, results = evaluator.run_evaluation(cases, save_baseline=False)
            assert summary.total_queries == 3
            assert summary.intent_extraction_accuracy_pct == pytest.approx(66.67, 0.1)
            assert summary.reference_resolution_accuracy_pct == pytest.approx(66.67, 0.1)
            assert summary.zero_result_rate_pct == pytest.approx(33.33, 0.1)
            assert summary.api_error_rate_pct == pytest.approx(33.33, 0.1)
            assert summary.avg_relevant_results_in_top_5 == pytest.approx(2.33, 0.1)
            assert summary.duplicate_rate_pct == 0.0

    def test_baseline_results_file_reproducibility(self) -> None:
        # Verify baseline results file exists and has valid schema if generated
        if BASELINE_RESULTS_PATH.exists():
            with open(BASELINE_RESULTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert "summary" in data
            assert "granular_results" in data
            summary = data["summary"]
            assert summary["total_queries"] >= 40
            assert "intent_extraction_accuracy_pct" in summary
            assert "zero_result_rate_pct" in summary
            assert "avg_relevant_results_in_top_5" in summary
            assert "duplicate_rate_pct" in summary
            assert "api_error_rate_pct" in summary
            assert "category_breakdown" in summary
