"""Dataset Loader and Model Definitions for Movie Recommendation Evaluation.

Provides typed models, loading functions, and validation checks for the 45-query
evaluation benchmark dataset.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DATASET_FILE = Path(__file__).resolve().parent / "recommendation_test_dataset.json"


@dataclass
class HardConstraints:
    content_type: str = "movie"
    language: Optional[str] = None
    region: Optional[str] = None
    release_year_min: Optional[int] = None
    release_year_max: Optional[int] = None


@dataclass
class EvaluationRules:
    min_genre_match: int = 1
    require_reference_title: bool = False
    require_language: bool = False
    require_region: bool = False
    require_year_bounds: bool = False


@dataclass
class ExpectedIntent:
    intent_types: List[str]
    reference_title: Optional[str]
    expected_genres: List[str]
    expected_themes: List[str]
    expected_plot_elements: List[str]
    expected_moods: List[str]
    hard_constraints: HardConstraints
    soft_preferences: List[str]
    evaluation_rules: EvaluationRules


@dataclass
class TestCase:
    __test__ = False  # Prevents pytest from collecting this data model as a test class
    id: str
    query: str
    category: str
    category_key: str
    expected_intent: ExpectedIntent

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        exp = data["expected_intent"]
        hc = exp["hard_constraints"]
        er = exp["evaluation_rules"]
        return cls(
            id=data["id"],
            query=data["query"],
            category=data["category"],
            category_key=data["category_key"],
            expected_intent=ExpectedIntent(
                intent_types=exp["intent_types"],
                reference_title=exp["reference_title"],
                expected_genres=exp["expected_genres"],
                expected_themes=exp["expected_themes"],
                expected_plot_elements=exp["expected_plot_elements"],
                expected_moods=exp["expected_moods"],
                hard_constraints=HardConstraints(
                    content_type=hc.get("content_type", "movie"),
                    language=hc.get("language"),
                    region=hc.get("region"),
                    release_year_min=hc.get("release_year_min"),
                    release_year_max=hc.get("release_year_max"),
                ),
                soft_preferences=exp.get("soft_preferences", []),
                evaluation_rules=EvaluationRules(
                    min_genre_match=er.get("min_genre_match", 1),
                    require_reference_title=er.get("require_reference_title", False),
                    require_language=er.get("require_language", False),
                    require_region=er.get("require_region", False),
                    require_year_bounds=er.get("require_year_bounds", False),
                ),
            ),
        )


def load_evaluation_dataset(dataset_path: Optional[Path] = None) -> List[TestCase]:
    """Load and parse all test cases from the JSON dataset file."""
    p = dataset_path or DATASET_FILE
    if not p.exists():
        raise FileNotFoundError(f"Evaluation dataset not found at: {p}")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    queries = data.get("queries", [])
    return [TestCase.from_dict(q) for q in queries]


def get_queries_by_category(category_key: str, dataset_path: Optional[Path] = None) -> List[TestCase]:
    """Filter test cases by category key."""
    all_cases = load_evaluation_dataset(dataset_path)
    return [c for c in all_cases if c.category_key == category_key]
