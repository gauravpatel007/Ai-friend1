"""Phase 0 Audit Investigation Script.
Traces: 'Recommend a mind-bending sci-fi or psychological mystery with plot twists'
through the entire pipeline:
1. Ollama intent parsing
2. TMDB search / discover parameters
3. TMDB response
4. Filtering & candidate evaluation
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath("."))

from app.ai.ollama_client import OllamaClient
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.api.tmdb_client import TMDBClient
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository

query = "Recommend a mind-bending sci-fi or psychological mystery with plot twists"

print(f"=== 1. Original User Input: ===\n{query}\n")

# Check Ollama
oc = OllamaClient()
reachable = oc.is_server_reachable()
print(f"Ollama server reachable: {reachable}")

tmdb = TMDBClient()
print(f"TMDB client configured: {tmdb.is_configured()}")

db = DatabaseManager()
repo = MovieStorageRepository(db)
engine = MovieRecommendationEngine(tmdb, repo, oc)

# 2. Deterministic Parse
det_intent = engine.parse_intent_deterministic(query)
print(f"\n=== 2. Deterministic Parsed Intent ===")
print(f"intent_type: {det_intent.intent_type}")
print(f"content_type: {det_intent.content_type}")
print(f"genres: {det_intent.genres}")
print(f"genre_ids: {det_intent.genre_ids}")
print(f"mood: {det_intent.mood}")
print(f"keywords: {det_intent.keywords}")
print(f"language: {det_intent.language}")
print(f"region: {det_intent.region}")
print(f"interpreted_summary: {det_intent.interpreted_summary}")

# 3. LLM Parse
if reachable:
    print(f"\n=== 3. Testing LLM Intent Parsing with Ollama ===")
    system_prompt = (
        "You are a precise entertainment intent parser. Convert user recommendation requests into JSON matching this schema:\n"
        "{\n"
        '  "intent_type": "similar_to" | "genre" | "regional" | "time_period" | "mood" | "complex" | "general",\n'
        '  "reference_title": string or null,\n'
        '  "reference_year": integer or null,\n'
        '  "content_type": "all" | "movie" | "tv",\n'
        '  "language": "hi"|"te"|"ta"|"ml"|"kn"|"gu"|"en"|"ko"|"ja"|"es"|"fr"|null,\n'
        '  "region": "south_indian"|"bollywood"|"hollywood"|"indian"|null,\n'
        '  "genres": ["Action", "Thriller", "Comedy", etc.],\n'
        '  "release_year_min": integer or null,\n'
        '  "release_year_max": integer or null,\n'
        '  "mood": string or null,\n'
        '  "keywords": ["underrated", "whodunit", "plot twist", "survival", etc.]\n'
        "}\n"
        "IMPORTANT RULES:\n"
        "1. If user asks for 'Movies like [Title]', set reference_title to the exact title name, and intent_type to 'similar_to'.\n"
        "2. DO NOT set language or region unless explicitly requested by the user in words.\n"
        "3. Return ONLY a valid JSON object. No thoughts, no preamble, no markdown backticks."
    )
    raw_llm = oc.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        model=engine.default_model,
        options={"temperature": 0.0, "num_predict": 180},
    )
    print(f"Raw Ollama Response:\n{raw_llm}\n")
    llm_intent = engine.parse_intent_with_llm(query)
    print(f"LLM Merged Intent Summary: {llm_intent.interpreted_summary}")
    print(f"LLM Merged Genres: {llm_intent.genres} (IDs: {llm_intent.genre_ids})")
    print(f"LLM Merged Keywords: {llm_intent.keywords}")
    print(f"LLM Content Type: {llm_intent.content_type}")
    print(f"LLM Region: {llm_intent.region}, Language: {llm_intent.language}")
else:
    llm_intent = det_intent

# 4. Tracing Candidate Retrieval
print(f"\n=== 4. Tracing Candidate Retrieval ===")
raw_candidates, ret_diag = engine.retrieve_candidates(llm_intent, limit=36, return_diagnostics=True)
print(f"Raw Candidates Count: {len(raw_candidates)}")
print(f"Retrieval Tiers Used: {ret_diag.get('retrieval_tiers_used')}")
print(f"Counts per Tier: {ret_diag.get('counts_per_tier')}")

# 5. Filtering
from app.ai.regional_classifier import filter_eligible_candidates
eligible, rejected = filter_eligible_candidates(raw_candidates, llm_intent)
print(f"\n=== 5. Filtering Results ===")
print(f"Eligible Count: {len(eligible)}")
print(f"Rejected Count: {len(rejected)}")
if rejected:
    print(f"First 5 rejection reasons:")
    for item, reason in rejected[:5]:
        print(f"  - {item.title}: {reason}")

# 6. Ranking
ranked = engine.rank_candidates(eligible, llm_intent, limit=6)
print(f"\n=== 6. Ranking Results ===")
print(f"Ranked Count: {len(ranked)}")
for item, score, factors in ranked:
    print(f"  - {item.title} (score={score:.2f}, factors={factors})")

print("\n=== Audit Script Complete ===")
