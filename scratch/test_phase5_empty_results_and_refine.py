import sys
import os

# Insert workspace root to path
sys.path.insert(0, os.path.abspath("."))

from app.api.movie_models import (
    ParsedRecommendationIntent,
    EditedPreferenceModel,
    MediaItemSummary,
)
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.api.tmdb_client import TMDBClient
from app.memory.movie_storage_repository import MovieStorageRepository

def test_phase5_refinements():
    print("\n--- TEST 1: Refinement Controls Soft Preference vs Mandatory Gate ---")
    engine = MovieRecommendationEngine(
        tmdb_client=TMDBClient(api_key=None),
        storage_repo=MovieStorageRepository(db_manager=None),
    )

    base_intent = ParsedRecommendationIntent(
        intent_type="similar_to",
        reference_title="Premalu",
        origin_country="IN",
        is_explicit_country=True,
        is_explicit_language=False,
    )

    # User clicks "More Malayalam" as a soft refinement from Refine Discovery
    malayalam_pref = EditedPreferenceModel(
        category="lang",
        label="Malayalam",
        value="Malayalam",
        nature="preferred"
    )

    updated_intent = engine.apply_edited_preferences_to_intent(
        base_intent,
        edited_preferences=[malayalam_pref],
    )

    assert "ml" in updated_intent.preferred_languages, "ml should be in preferred_languages"
    assert not updated_intent.is_explicit_language, "Soft refinement must NOT set is_explicit_language to True"
    assert updated_intent.origin_country == "IN", "Mandatory country constraint must be preserved"
    print("PASS: Soft refinement correctly registered in preferred_languages without turning into mandatory gate")

    # User clicks "More romantic" as a soft refinement
    romance_pref = EditedPreferenceModel(
        category="genre",
        label="Romance",
        value="Romance",
        nature="preferred"
    )
    updated_intent_2 = engine.apply_edited_preferences_to_intent(
        updated_intent,
        edited_preferences=[malayalam_pref, romance_pref],
    )
    assert "Romance" in updated_intent_2.preferred_genres or "Romance" in updated_intent_2.genres
    print("PASS: Genre refinement correctly registered as preferred genre")

    # User clicks "More plot similarity"
    plot_pref = EditedPreferenceModel(
        category="theme",
        label="Plot Similarity",
        value="Plot Similarity",
        nature="preferred"
    )
    updated_intent_3 = engine.apply_edited_preferences_to_intent(
        updated_intent_2,
        edited_preferences=[malayalam_pref, romance_pref, plot_pref],
    )
    assert "Plot Similarity" in updated_intent_3.preferred_themes
    print("PASS: Plot similarity refinement correctly registered in preferred_themes")


def test_phase5_diagnostics_and_empty_causes():
    print("\n--- TEST 2: Empty Result Handling & Root Cause Classification ---")
    engine = MovieRecommendationEngine(
        tmdb_client=TMDBClient(api_key=None),
        storage_repo=MovieStorageRepository(db_manager=None),
    )

    # Case A: Reference not resolved
    resp_ref_missing = engine.recommend("Movies like CompletelyFakeMovieTitle9999XYZ")
    assert resp_ref_missing.error_type == "reference_not_resolved", f"Expected reference_not_resolved, got {resp_ref_missing.error_type}"
    print(f"PASS: reference_not_resolved handled correctly -> {resp_ref_missing.error_message}")

    # Check UI transparency fields in diagnostics
    diag = resp_ref_missing.diagnostics
    assert diag is not None, "Diagnostics payload must be present"
    assert "reference_movie" in diag
    assert "required_country" in diag
    assert "required_language" in diag
    assert "preferred_genres" in diag
    assert "funnel_breakdown" in diag
    assert "candidates_retrieved" in diag
    assert "candidates_passing_hard_filters" in diag
    assert "candidates_ranked" in diag
    print(f"PASS: UI transparency diagnostics present: Funnel = {diag['funnel_breakdown']}")


if __name__ == "__main__":
    test_phase5_refinements()
    test_phase5_diagnostics_and_empty_causes()
    print("\nALL PHASE 5 TESTS COMPLETED SUCCESSFULLY!")
