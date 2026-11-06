"""Evaluation Runner and Baseline Metric Harvester for Movie Recommendation Engine.

Executes test queries against the recommendation engine, calculates the 9 baseline
metrics, and stores the results for cross-phase objective comparison.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

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
from app.api.tmdb_client import TMDBClient
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository
from tests.evaluation.dataset import (
    DATASET_FILE,
    TestCase,
    load_evaluation_dataset,
)
from tests.evaluation.mock_tmdb_data import MockTMDBClient

logger = logging.getLogger(__name__)

BASELINE_RESULTS_PATH = Path(__file__).resolve().parent / "baseline_results.json"


def create_default_recommendation_engine(
    tmdb_client: Optional[Any] = None,
    storage_repo: Optional[Any] = None,
    ollama_client: Optional[Any] = None,
    use_mock_tmdb: bool = False,
    enable_llm_explanations: bool = False,
) -> MovieRecommendationEngine:
    """Helper to create a functional MovieRecommendationEngine for evaluations."""
    if tmdb_client is None:
        if use_mock_tmdb:
            tmdb_client = MockTMDBClient(scenario="success")
        else:
            try:
                tmdb_client = TMDBClient()
            except Exception:
                tmdb_client = MockTMDBClient(scenario="success")

    if storage_repo is None:
        db = DatabaseManager(":memory:")
        storage_repo = MovieStorageRepository(db)

    if ollama_client is None:
        # Create a mock or proxy client so that retrieval/ranking evaluations
        # do not spend 50+ minutes generating 225 individual LLM explanation essays
        ollama_client = MagicMock()
        ollama_client.is_server_reachable.return_value = enable_llm_explanations
        ollama_client.chat.return_value = {"message": {"content": "{}"}}

    return MovieRecommendationEngine(
        tmdb_client=tmdb_client,
        storage_repo=storage_repo,
        ollama_client=ollama_client,
    )


@dataclass
class QueryMetricResult:
    id: str
    query: str
    category: str
    category_key: str
    intent_accurate: bool
    reference_resolved: Optional[bool]
    candidate_retrieval_count: int
    is_zero_result: bool
    top_5_relevant_count: int
    has_duplicates: bool
    duplicate_count: int
    api_error: bool
    error_type: Optional[str]
    retrieval_time_ms: float
    total_time_ms: float
    extracted_intent: Dict[str, Any]
    top_5_titles: List[str]


@dataclass
class EvaluationSummaryMetrics:
    total_queries: int
    intent_extraction_accuracy_pct: float
    reference_resolution_accuracy_pct: float
    avg_candidate_retrieval_count: float
    zero_result_rate_pct: float
    avg_relevant_results_in_top_5: float
    duplicate_rate_pct: float
    api_error_rate_pct: float
    avg_retrieval_time_ms: float
    avg_total_recommendation_time_ms: float
    category_breakdown: Dict[str, Dict[str, Any]]
    generated_at: str
    system_version: str = "baseline_v0"


class RecommendationEvaluator:
    """Automated evaluation framework for the Movie Recommendation Engine."""

    def __init__(
        self,
        engine: Optional[MovieRecommendationEngine] = None,
        tmdb_client: Optional[Any] = None,
        use_llm: bool = False,
        use_mock_tmdb: bool = False,
        enable_llm_explanations: bool = False,
    ) -> None:
        self.engine = engine or create_default_recommendation_engine(
            tmdb_client=tmdb_client,
            use_mock_tmdb=use_mock_tmdb,
            enable_llm_explanations=enable_llm_explanations,
        )
        self.use_llm = use_llm

    def check_intent_accuracy(self, test_case: TestCase, intent: ParsedRecommendationIntent) -> bool:
        """Evaluate whether extracted intent matches expected intent definition."""
        rules = test_case.expected_intent.evaluation_rules
        hc = test_case.expected_intent.hard_constraints
        exp = test_case.expected_intent

        # 1. Hard constraint: Reference title
        if rules.require_reference_title:
            ref = intent.reference_title or intent.similar_to_title or ""
            exp_ref = exp.reference_title or ""
            if not ref or exp_ref.lower() not in ref.lower():
                return False

        # 2. Hard constraint: Language
        if rules.require_language:
            if not intent.language or intent.language.lower() != hc.language.lower():
                return False

        # 3. Hard constraint: Region
        if rules.require_region:
            matched_reg = False
            if intent.region and intent.region.lower() == hc.region.lower():
                matched_reg = True
            elif hc.region == "south_indian" and intent.region in ("malayalam", "tamil", "telugu", "kannada", "south_indian"):
                matched_reg = True
            elif hasattr(intent, "regions") and hc.region.lower() in [r.lower() for r in (intent.regions or [])]:
                matched_reg = True
            if not matched_reg:
                return False

        # 4. Hard constraint: Year bounds
        if rules.require_year_bounds:
            if hc.release_year_min and (intent.release_year_min or 0) < hc.release_year_min:
                return False
            if hc.release_year_max and (intent.release_year_max or 9999) > hc.release_year_max:
                return False

        # 5. Flexible Genre / Theme / Keyword / Mood Match
        # Rule: At least 1 expected genre or matching mood or matching keyword
        genre_match = False
        if exp.expected_genres:
            extracted_genres = [g.lower() for g in (intent.genres or [])]
            for eg in exp.expected_genres:
                if eg.lower() in extracted_genres:
                    genre_match = True
                    break

        mood_match = False
        if exp.expected_moods and intent.mood:
            if any(em.lower() in intent.mood.lower() or intent.mood.lower() in em.lower() for em in exp.expected_moods):
                mood_match = True

        keyword_match = False
        if exp.expected_plot_elements and intent.keywords:
            extracted_kw = [k.lower() for k in intent.keywords]
            if any(ep.lower() in extracted_kw for ep in exp.expected_plot_elements):
                keyword_match = True

        # If reference title matched, or genre matched, or mood matched, or keyword matched
        if rules.require_reference_title:
            return True
        if not exp.expected_genres and (rules.require_language or rules.require_region or rules.require_year_bounds):
            return True
        return genre_match or mood_match or keyword_match

    def judge_relevance(self, item: MediaItemSummary, test_case: TestCase) -> bool:
        """Heuristic check of candidate item relevance to the test case."""
        exp = test_case.expected_intent
        title_lower = (item.title or "").lower()
        overview_lower = (item.overview or "").lower()

        # If it's a similar_to query and reference title is present, check similarity
        if exp.reference_title and exp.reference_title.lower() in title_lower:
            return False  # Self-match is not a novel recommendation

        # Check genre intersection (supporting both genre_ids and genre_names)
        inv_genre_map = {v: k.lower() for k, v in GENRE_TAXONOMY.items()}
        item_genres = set()
        if hasattr(item, "genre_names") and item.genre_names:
            item_genres.update(g.lower() for g in item.genre_names)
        if hasattr(item, "genre_ids") and item.genre_ids:
            item_genres.update(inv_genre_map[gid] for gid in item.genre_ids if gid in inv_genre_map)

        for eg in exp.expected_genres:
            if eg.lower() in item_genres:
                return True

        # Check themes & plot elements in overview
        for theme in exp.expected_themes + exp.expected_plot_elements:
            if theme.lower() in overview_lower:
                return True

        # Check language match for regional queries
        if exp.hard_constraints.language:
            if item.original_language and item.original_language.lower() == exp.hard_constraints.language.lower():
                return True

        return False

    def evaluate_query(self, test_case: TestCase) -> QueryMetricResult:
        """Run single query evaluation and collect metrics."""
        t_start = time.perf_counter()
        t_retrieval_ms = 0.0
        top_5_titles: List[str] = []
        is_zero = True
        has_dupes = False
        dupe_count = 0
        raw_candidates_count = 0
        api_error = False
        error_type: Optional[str] = None
        ref_resolved: Optional[bool] = None
        top_5_relevant = 0

        # Step 1: Intent Extraction
        try:
            if self.use_llm:
                intent = self.engine.parse_intent_with_llm(test_case.query)
            else:
                intent = self.engine.parse_intent_deterministic(test_case.query)
        except Exception as e:
            intent = ParsedRecommendationIntent(query=test_case.query, intent_type="complex")
            api_error = True
            error_type = f"intent_error: {type(e).__name__}"

        intent_acc = self.check_intent_accuracy(test_case, intent)

        # Step 2: Reference Resolution (if applicable)
        if test_case.expected_intent.reference_title or intent.reference_title:
            try:
                # resolve_reference_title takes ParsedRecommendationIntent and returns Optional[MediaDetailsModel]
                if not intent.reference_title and test_case.expected_intent.reference_title:
                    intent.reference_title = test_case.expected_intent.reference_title
                resolved_media = self.engine.resolve_reference_title(intent)
                ref_resolved = resolved_media is not None
            except Exception:
                ref_resolved = False

        # Step 3: Run Full Recommendation (or Retrieval)
        try:
            t_ret_start = time.perf_counter()
            resp = self.engine.recommend(test_case.query, include_saved_preferences=False, limit=5)
            t_retrieval_ms = (time.perf_counter() - t_ret_start) * 1000.0

            raw_candidates_count = resp.total_candidates_analyzed
            recs = resp.recommendations or []
            is_zero = len(recs) == 0
            if resp.error_type:
                api_error = resp.error_type in ["auth_error", "network_error", "rate_limit"]
                error_type = resp.error_type

            # Check duplicates in recommendations
            seen_ids = set()
            for r in recs:
                if not r.media:
                    continue
                mid = r.media.id
                top_5_titles.append(r.media.title or f"ID-{mid}")
                if mid in seen_ids:
                    has_dupes = True
                    dupe_count += 1
                seen_ids.add(mid)

                # Check relevance of top 5
                if self.judge_relevance(r.media, test_case):
                    top_5_relevant += 1

        except Exception as e:
            api_error = True
            error_type = f"pipeline_error: {type(e).__name__}"
            is_zero = True

        total_time_ms = (time.perf_counter() - t_start) * 1000.0

        return QueryMetricResult(
            id=test_case.id,
            query=test_case.query,
            category=test_case.category,
            category_key=test_case.category_key,
            intent_accurate=intent_acc,
            reference_resolved=ref_resolved,
            candidate_retrieval_count=raw_candidates_count,
            is_zero_result=is_zero,
            top_5_relevant_count=top_5_relevant,
            has_duplicates=has_dupes,
            duplicate_count=dupe_count,
            api_error=api_error,
            error_type=error_type,
            retrieval_time_ms=round(t_retrieval_ms, 2),
            total_time_ms=round(total_time_ms, 2),
            extracted_intent={
                "intent_type": intent.intent_type,
                "reference_title": intent.reference_title,
                "genres": intent.genres,
                "mood": intent.mood,
                "language": intent.language,
                "region": intent.region,
                "release_year_min": intent.release_year_min,
                "release_year_max": intent.release_year_max,
                "keywords": intent.keywords,
            },
            top_5_titles=top_5_titles,
        )

    def run_evaluation(
        self,
        dataset: Optional[List[TestCase]] = None,
        save_baseline: bool = True,
    ) -> Tuple[EvaluationSummaryMetrics, List[QueryMetricResult]]:
        """Run full evaluation suite over all queries and compute summary metrics."""
        cases = dataset or load_evaluation_dataset()
        results: List[QueryMetricResult] = []
        total = len(cases)

        for i, case in enumerate(cases):
            print(f"[{i+1}/{total}] Evaluating {case.id} ({case.category_key}): {case.query[:50]}")
            res = self.evaluate_query(case)
            results.append(res)

        total = len(results)
        if total == 0:
            raise ValueError("No test cases evaluated")

        # Metric 1: Intent extraction accuracy
        intent_acc_count = sum(1 for r in results if r.intent_accurate)
        intent_acc_pct = (intent_acc_count / total) * 100.0

        # Metric 2: Reference movie resolution accuracy
        ref_cases = [r for r in results if r.reference_resolved is not None]
        ref_resolved_count = sum(1 for r in ref_cases if r.reference_resolved)
        ref_res_pct = (ref_resolved_count / len(ref_cases) * 100.0) if ref_cases else 100.0

        # Metric 3: Average Candidate retrieval count
        avg_candidates = sum(r.candidate_retrieval_count for r in results) / total

        # Metric 4: Zero-result rate
        zero_count = sum(1 for r in results if r.is_zero_result)
        zero_pct = (zero_count / total) * 100.0

        # Metric 5: Number of relevant results in top 5
        avg_top_5_rel = sum(r.top_5_relevant_count for r in results) / total

        # Metric 6: Duplicate rate
        dupe_query_count = sum(1 for r in results if r.has_duplicates)
        dupe_pct = (dupe_query_count / total) * 100.0

        # Metric 7: API error rate
        api_err_count = sum(1 for r in results if r.api_error)
        api_err_pct = (api_err_count / total) * 100.0

        # Metric 8: Average retrieval time
        avg_retrieval_time = sum(r.retrieval_time_ms for r in results) / total

        # Metric 9: Average complete recommendation time
        avg_total_time = sum(r.total_time_ms for r in results) / total

        # Category Breakdown
        categories: Dict[str, Dict[str, Any]] = {}
        for r in results:
            cat = r.category
            if cat not in categories:
                categories[cat] = {
                    "count": 0,
                    "intent_accurate_count": 0,
                    "zero_result_count": 0,
                    "top_5_relevant_total": 0,
                    "avg_total_time_ms": 0.0,
                }
            categories[cat]["count"] += 1
            if r.intent_accurate:
                categories[cat]["intent_accurate_count"] += 1
            if r.is_zero_result:
                categories[cat]["zero_result_count"] += 1
            categories[cat]["top_5_relevant_total"] += r.top_5_relevant_count
            categories[cat]["avg_total_time_ms"] += r.total_time_ms

        for cat, stats in categories.items():
            cnt = stats["count"]
            stats["intent_accuracy_pct"] = round((stats["intent_accurate_count"] / cnt) * 100.0, 1)
            stats["zero_result_pct"] = round((stats["zero_result_count"] / cnt) * 100.0, 1)
            stats["avg_relevant_in_top_5"] = round(stats["top_5_relevant_total"] / cnt, 2)
            stats["avg_total_time_ms"] = round(stats["avg_total_time_ms"] / cnt, 1)

        summary = EvaluationSummaryMetrics(
            total_queries=total,
            intent_extraction_accuracy_pct=round(intent_acc_pct, 2),
            reference_resolution_accuracy_pct=round(ref_res_pct, 2),
            avg_candidate_retrieval_count=round(avg_candidates, 1),
            zero_result_rate_pct=round(zero_pct, 2),
            avg_relevant_results_in_top_5=round(avg_top_5_rel, 2),
            duplicate_rate_pct=round(dupe_pct, 2),
            api_error_rate_pct=round(api_err_pct, 2),
            avg_retrieval_time_ms=round(avg_retrieval_time, 1),
            avg_total_recommendation_time_ms=round(avg_total_time, 1),
            category_breakdown=categories,
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            system_version="baseline_v0",
        )

        if save_baseline:
            self.save_baseline_file(summary, results)

        return summary, results

    def save_baseline_file(
        self,
        summary: EvaluationSummaryMetrics,
        results: List[QueryMetricResult],
        filepath: Optional[Path] = None,
    ) -> Path:
        """Write summary metrics and granular query results to JSON baseline file."""
        target = filepath or BASELINE_RESULTS_PATH
        payload = {
            "summary": asdict(summary),
            "granular_results": [asdict(r) for r in results],
        }
        with open(target, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return target


if __name__ == "__main__":
    print("Running baseline recommendation evaluation...")
    evaluator = RecommendationEvaluator()
    summary, _ = evaluator.run_evaluation(save_baseline=True)
    print("\n--- BASELINE METRICS SUMMARY ---")
    print(f"Total Queries: {summary.total_queries}")
    print(f"Intent Extraction Accuracy: {summary.intent_extraction_accuracy_pct}%")
    print(f"Reference Movie Resolution Accuracy: {summary.reference_resolution_accuracy_pct}%")
    print(f"Avg Candidate Retrieval Count: {summary.avg_candidate_retrieval_count}")
    print(f"Zero-Result Rate: {summary.zero_result_rate_pct}%")
    print(f"Avg Relevant Results in Top 5: {summary.avg_relevant_results_in_top_5} / 5.0")
    print(f"Duplicate Rate: {summary.duplicate_rate_pct}%")
    print(f"API Error Rate: {summary.api_error_rate_pct}%")
    print(f"Avg Retrieval Time: {summary.avg_retrieval_time_ms} ms")
    print(f"Avg Complete Recommendation Time: {summary.avg_total_recommendation_time_ms} ms")
