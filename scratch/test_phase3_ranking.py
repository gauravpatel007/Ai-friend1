import os
import sys
import time
import json

sys.path.insert(0, os.path.abspath("."))

from app.ai.ollama_client import OllamaClient
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.ai.movie_ranking_engine import MovieRankingEngine, THEMATIC_SYNONYM_MAP, extract_candidate_features
from app.api.tmdb_client import TMDBClient
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository
from app.ai.regional_classifier import INDIAN_LANGUAGES
from app.api.movie_models import MediaItemSummary, ParsedRecommendationIntent

def run_tests():
    print("=" * 60)
    print("PHASE 3 VERIFICATION SUITE: RANKING AND FILTERING")
    print("=" * 60)

    tmdb = TMDBClient()
    oc = OllamaClient()
    db = DatabaseManager()
    repo = MovieStorageRepository(db)
    engine = MovieRecommendationEngine(tmdb, repo, oc)
    ranking_engine = engine.ranking_engine

    # -------------------------------------------------------------
    # Test 1: Semantic Cluster & Synonym Scoring
    # -------------------------------------------------------------
    print("\n--- TEST 1: Thematic Synonym & Cluster Matching ---")
    mock_cand_1 = MediaItemSummary(
        id=9901,
        title="College Crush",
        overview="A young student experiences one-sided heartbreak when he falls for his friend in college.",
        genre_ids=[10749, 35],
        genre_names=["Romance", "Comedy"],
        original_language="ml",
        origin_country=["IN"],
        release_year=2023,
        vote_average=7.6,
        vote_count=120,
        popularity=25.0,
    )
    features_1 = extract_candidate_features(mock_cand_1)
    
    intent_unrequited = ParsedRecommendationIntent(
        keywords=["unrequited love"],
        themes=["unrequited love"],
    )
    
    theme_score, reason = ranking_engine.score_theme_keywords(features_1, intent_unrequited)
    print(f"Cand with 'one-sided heartbreak' for 'unrequited love' keyword: score={theme_score:.2f}, reason={reason}")
    assert theme_score >= 0.70, f"Expected thematic synonym match score >= 0.70, got {theme_score}"
    print("  -> Passed synonym cluster matching!")

    # Test candidate with Romance genre but completely generic synopsis
    mock_cand_2 = MediaItemSummary(
        id=9902,
        title="Simple Romance",
        overview="Two people meet in the city and navigate life.",
        genre_ids=[10749],
        genre_names=["Romance"],
        original_language="ta",
        origin_country=["IN"],
        release_year=2022,
        vote_average=7.0,
        vote_count=80,
        popularity=15.0,
    )
    features_2 = extract_candidate_features(mock_cand_2)
    theme_score_2, reason_2 = ranking_engine.score_theme_keywords(features_2, intent_unrequited)
    print(f"Cand with Romance genre (no exact syn): score={theme_score_2:.2f}, reason={reason_2}")
    assert theme_score_2 >= 0.40, f"Expected soft baseline >= 0.40, got {theme_score_2}"
    print("  -> Passed soft baseline synergy!")

    # -------------------------------------------------------------
    # Test 2: Hard Filter Separation
    # -------------------------------------------------------------
    print("\n--- TEST 2: Hard Filter Separation ---")
    # A. Hollywood movie should fail country filter when Indian requested
    hollywood_cand = MediaItemSummary(
        id=101,
        title="La La Land",
        overview="An aspiring actress and a dedicated jazz musician struggle to make ends meet in Los Angeles.",
        genre_ids=[10749, 35, 18],
        genre_names=["Romance", "Comedy", "Drama"],
        original_language="en",
        origin_country=["US"],
        release_year=2016,
    )
    indian_intent = engine.parse_intent_deterministic("Indian movies like Premalu")
    passes, rej_reason = ranking_engine.passes_hard_filters(
        extract_candidate_features(hollywood_cand),
        indian_intent,
    )
    print(f"Hollywood movie ('La La Land') passes Indian hard filter? {passes} (Reason: {rej_reason})")
    assert not passes, "Hollywood movie should have failed Indian hard country filter!"
    print("  -> Passed: Explicit Indian country constraint strictly enforced on non-Indian movie!")

    # B. Indian movie in Hindi should PASS "Indian movies like Premalu" (since language is NOT explicit)
    hindi_cand = MediaItemSummary(
        id=102,
        title="Yeh Jawaani Hai Deewani",
        overview="Kabir and Naina bond during a trekking trip, but their contrasting ambitions pull them apart until they reunite years later at a friend's wedding.",
        genre_ids=[10749, 35, 18],
        genre_names=["Romance", "Comedy", "Drama"],
        original_language="hi",
        origin_country=["IN"],
        release_year=2013,
    )
    passes_hi, rej_hi = ranking_engine.passes_hard_filters(
        extract_candidate_features(hindi_cand),
        indian_intent,
    )
    print(f"Hindi movie passes 'Indian movies like Premalu'? {passes_hi} (Reason: {rej_hi})")
    assert passes_hi, f"Hindi Indian movie should have passed: {rej_hi}"
    print("  -> Passed: Hindi Indian movie passed because language is soft!")

    # C. "Malayalam movies like Premalu" should REJECT Hindi movie (explicit language)
    malayalam_intent = engine.parse_intent_deterministic("Malayalam movies like Premalu")
    passes_mal_hi, rej_mal_hi = ranking_engine.passes_hard_filters(
        extract_candidate_features(hindi_cand),
        malayalam_intent,
    )
    print(f"Hindi movie passes 'Malayalam movies like Premalu'? {passes_mal_hi} (Reason: {rej_mal_hi})")
    assert not passes_mal_hi, "Hindi movie should be rejected when Malayalam was explicitly requested!"
    print("  -> Passed: Explicit language filter strictly enforced when requested!")

    # D. Excluded genre test
    excluded_intent = ParsedRecommendationIntent(
        origin_country="IN",
        is_explicit_country=True,
        excluded_genres=["Romance"],
    )
    passes_excl, rej_excl = ranking_engine.passes_hard_filters(
        extract_candidate_features(hindi_cand),
        excluded_intent,
    )
    print(f"Romance movie passes when 'Romance' is excluded? {passes_excl} (Reason: {rej_excl})")
    assert not passes_excl, "Romance movie should be rejected when Romance is in excluded_genres!"
    print("  -> Passed: Excluded genre hard filter verified!")

    # -------------------------------------------------------------
    # Test 3: Full End-to-End Recommendation with Real TMDB
    # -------------------------------------------------------------
    print("\n--- TEST 3: End-to-End Recommendation for 'Indian movies like Premalu' ---")
    resp = engine.recommend("Indian movies like Premalu")
    
    print(f"Query: {resp.query}")
    print(f"Total candidates analyzed: {resp.total_candidates_analyzed}")
    print(f"Final recommendations count: {len(resp.recommendations)}")
    print(f"Error type: {resp.error_type}")
    print(f"Error message: {resp.error_message}")

    assert len(resp.recommendations) >= 10, f"Expected 10-20 recommendations, got {len(resp.recommendations)}"
    assert resp.error_type is None, f"Expected no error, got {resp.error_type}: {resp.error_message}"

    print(f"\nTop Recommendations (Total: {len(resp.recommendations)}):")
    languages_seen = set()
    for idx, rec in enumerate(resp.recommendations, 1):
        m = rec.media
        lang = m.original_language
        languages_seen.add(lang)
        countries = m.origin_country or []
        is_indian = ("IN" in countries) or (lang in INDIAN_LANGUAGES)
        assert is_indian, f"Recommendation {m.title} ({lang}, {countries}) is NOT Indian cinema!"
        
        print(f"  {idx}. {m.title} ({m.release_year}) [{lang.upper()}] - Score: {rec.score}/100")
        print(f"     Reasons: {rec.match_reasons}")
        if rec.relevance_breakdown:
            print(f"     Breakdown: {rec.relevance_breakdown}")
        print(f"     Explanation: {rec.ai_explanation[:100]}...")

    print(f"\nLanguages represented across recommendations: {languages_seen}")
    assert len(languages_seen) > 1, f"Expected multiple Indian languages represented, got {languages_seen}"
    print("  -> Passed: Broad representation of Indian cinema across languages!")
    print("\nALL PHASE 3 RANKING & FILTERING TESTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
