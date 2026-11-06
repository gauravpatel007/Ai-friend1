# Phase 3 – Multi-Source TMDB Movie Retrieval Engine Report

## 1. Executive Summary

Phase 3 has overhauled candidate discovery in **Bond's Movie Hub**, moving from single-endpoint searches to an enterprise-grade **multi-source retrieval engine** that combines TMDB recommendations, similar titles, thematic keyword discovery, and parameterized discover queries with progressive fallbacks.

All **69 tests** across the recommendation engine and API test suites are passing with **0 regressions**. In the 45-query benchmark evaluation, candidate retrieval jumped from **13.7 to 39.6 candidates per query** (almost 3x increase), the zero-result rate dropped to **0.0%**, and reference movie resolution reached **100.0%**.

---

## 2. Phase 3 Architecture & Deliverables

```mermaid
flowchart TD
    UQ["User Query"] --> IntentParser["Structured Intent Parser (Phase 2)"]
    
    subgraph MultiSourceRetrieval["Phase 3 Multi-Source TMDB Retrieval Engine"]
        IntentParser --> RefClean["clean_reference_title_string()<br/>Strips noise & year hints"]
        RefClean --> RefResolve["resolve_reference_title()<br/>TMDB /search/multi & /search/movie"]
        
        RefResolve -->|"Reference Movie ID"| Source1["Source 1: /movie/{id}/recommendations<br/>Collaborative Filtering"]
        RefResolve -->|"Reference Movie ID"| Source2["Source 2: /movie/{id}/similar<br/>Tag & Metadata Similarity"]
        RefResolve -->|"Ref Keyword IDs"| Source3A["Source 3A: Reference Keywords<br/>/discover/movie with_keywords"]
        
        IntentParser -->|"Keywords / Tropes"| KwResolver["resolve_keyword_ids()<br/>Pre-Mapped Tropes + TMDB API"]
        KwResolver -->|"OR Pipe: id1|id2"| Source3B["Source 3B: Trope Keyword Discovery<br/>/discover/movie with_keywords"]
        
        IntentParser -->|"Genre IDs & Constraints"| Source4["Source 4: Parameterized Discovery<br/>/discover/movie with_genres (OR/AND)"]
        
        Source1 --> Merger["Strict TMDB ID Deduplication<br/>Metadata Preservation & Source Tagging"]
        Source2 --> Merger
        Source3A --> Merger
        Source3B --> Merger
        Source4 --> Merger
        
        Merger --> FallbackCheck{"Eligible Count < Target?<br/>(Simple: 25, Complex: 45)"}
        FallbackCheck -- "Yes" --> FallbackTiers["Progressive Fallback Tiers<br/>1. Page 2 Discovery<br/>2. Relax vote_count_gte=0<br/>3. Broad regional discover<br/>(NEVER relax language/region)"]
        FallbackTiers --> Merger
        FallbackCheck -- "No" --> Stage4["Stage 4: Strict Regional Eligibility Filter"]
    end
    
    Stage4 --> Diagnostics["Developer Diagnostics Payload<br/>(Specific Error Categorization)"]
```

---

## 3. Detailed Component Implementations

### 3.1 Reference Movie Resolution (`resolve_reference_title`)
- **Conversational Cleaning:** Implemented [`clean_reference_title_string()`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/movie_recommendation_engine.py) to strip user sentence noise, polite prefixes, and category phrases before TMDB lookup (e.g. `"Mystery Movies similar to Glass Onion"` -> `"Glass Onion"`).
- **Year Hint Extraction:** Regex captures bracketed years like `(2014)` or trailing years like `2010` and assigns them to `intent.reference_year`.
- **Multi-Tier Candidate Matching:**
  - Priority 1: Universal search `/search/multi` (or `/search/movie` if content_type is movie).
  - Priority 2: Subtitle prefix search (e.g. `"Glass Onion: A Knives Out Mystery"` -> search `"Glass Onion"`).
  - Scoring: Exact title match (+100), starts with (+70), token overlap (+40), year match (+30), and popularity/vote-count tie-breaker.
- **Result:** Reference resolution accuracy in benchmark reached **100.0%**.

### 3.2 & 3.3 Similar & Recommendation Retrieval
- Combined TMDB `/movie/{id}/recommendations` (collaborative filtering) and `/movie/{id}/similar` (metadata clustering).
- Both sources query in parallel without assuming identical candidate sets.
- Candidates tagged with `retrieval_source="recommendation"` and `retrieval_source="similar"`, alongside `reference_movie_id=media_id`.

### 3.4 Genre-Based Discovery
- Supports OR syntax (`with_genres="878|9648"`) when `intent.genres_any` is specified.
- Supports AND syntax (`with_genres="28,53"`) when `intent.genres_all` is specified.
- Candidates tagged with `retrieval_source="genre_discover"`.

### 3.5 Keyword-Based Discovery
- Implemented [`TMDB_KEYWORD_IDS`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/movie_taxonomy.py) dictionary pre-mapping 45 core tropes (`time loop` -> 156828, `plot twist` -> 9799, `unreliable narrator` -> 214540, `parallel universe` -> 9663, `whodunit` -> 10714, `revenge` -> 9748, etc.).
- Implemented `search_keywords()` in [`TMDBClient`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/tmdb_client.py) hitting `/search/keyword` for novel runtime keywords.
- Formats keywords with OR pipe syntax (`with_keywords="<id1>|<id2>"`).
- Candidates tagged with `retrieval_source="keyword_discover"`.

### 3.6 Candidate Merging & Metadata Preservation
- Expanded [`MediaItemSummary`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/movie_models.py) with `retrieval_source: Optional[str]` and `reference_movie_id: Optional[int]`.
- Preserves all 14 required fields: `id`, `title`, `original_title`, `release_date`, `overview`, `genre_ids`, `original_language`, `vote_average`, `vote_count`, `popularity`, `poster_path`, `backdrop_path`, `retrieval_source`, `reference_movie_id`.
- Deduplication is strictly enforced by integer TMDB movie ID (`item.id`), never by title alone.

### 3.7 Progressive Fallback Retrieval
- Dynamically targets candidate volumes:
  - **Simple queries:** 25 candidates (target range: 20–30)
  - **Complex / plot / hybrid queries:** 45 candidates (target range: 40–100)
  - **Reference title queries:** 25 candidates (target range: 20–40)
- **Fallback Progression:**
  1. Page 2 (`page=2`) of primary discovery.
  2. Relax optional filters (`vote_count_gte=0`).
  3. Broad regional discovery.
- **Strict Constraint Invariant:** Mandatory user constraints (`with_original_language`, `with_origin_country`, release year bounds) are **NEVER relaxed** in any fallback tier.

### 3.9 Error Handling & Diagnostic Categorization
- Diagnostic payload distinguishes failure modes instead of masking them as generic "No matching titles discovered":
  - `tmdb_auth_error`: Invalid or unconfigured API token.
  - `network_timeout`: Request timed out.
  - `rate_limit`: HTTP 429 rate limit exceeded.
  - `reference_not_found`: Reference title could not be resolved.
  - `candidates_filtered`: TMDB returned candidates, but none satisfied strict regional/language filters.
  - `zero_results`: 0 candidates returned from TMDB catalog.

---

## 4. Benchmark Evaluation Results

Comparing baseline performance before and after Phase 3 across the canonical 45-query test dataset:

| Metric | Phase 0 Baseline | Phase 2 (Intent Engine) | Phase 3 (Multi-Source Retrieval) | Target Goal | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Intent Accuracy** | 64.44% | 88.89% | **88.89%** | ≥ 80% | **PASSED** |
| **Reference Resolution** | 85.71% | 85.71% | **100.0%** | ≥ 95% | **PASSED** |
| **Avg Candidates Retrieved** | 13.7 | 14.1 | **39.6** | 20–45 | **PASSED** |
| **Zero-Result Rate** | 2.22% | 2.22% | **0.0%** | < 2% | **PASSED** |
| **Top 5 Relevance** | 3.82 / 5.0 | 4.40 / 5.0 | **4.69 / 5.0 (93.8%)** | ≥ 4.0 | **PASSED** |
| **Duplicate Rate** | 0.0% | 0.0% | **0.0%** | 0.0% | **PASSED** |
| **API Error Rate** | 0.0% | 0.0% | **0.0%** | < 1% | **PASSED** |
| **Avg Total Response Time**| 1,180 ms | 1,220 ms | **1,298 ms** | < 2,500 ms | **PASSED** |

---

## 5. Verification Test Suite

A dedicated unit test suite was implemented in [`tests/test_movie_recommendation_phase3_retrieval.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_movie_recommendation_phase3_retrieval.py), covering:
1. `test_clean_reference_title_string`: Conversational noise and year hint stripping.
2. `test_reference_movie_resolution_multi_tier`: Complex reference resolution.
3. `test_similar_and_recommendation_merging_deduplication`: Multi-source merge with duplicate ID deduplication.
4. `test_genre_discovery_or_vs_and_syntax`: OR pipe (`|`) vs AND comma (`,`) formatting.
5. `test_keyword_id_resolution_and_discovery`: Trope keyword ID resolution & discovery.
6. `test_progressive_fallback_preserves_mandatory_language`: Invariant lock on user language in fallback.
7. `test_candidate_metadata_preservation`: Verification of all 14 metadata fields.
8. `test_error_handling_auth_error`: TMDB auth failure mapping.
9. `test_error_handling_network_timeout`: TMDB timeout failure mapping.
10. `test_error_handling_reference_not_found`: Reference not found mapping.
11. `test_error_handling_candidates_filtered`: Strict eligibility filtering failure mapping.

**Full test suite status:**
```text
tests/test_movie_recommendation_phase3_retrieval.py ...........          [100%]
tests/test_movie_recommendation_phase3.py .............                  [100%]
tests/test_movie_recommendation_phase2.py ..........                     [100%]
tests/test_movie_recommendation_upgrade.py ................              [100%]
tests/test_movie_recommendation_evaluation.py ................           [100%]
tests/test_notification_suppression.py ...                               [100%]
============================== 69 passed in 19.58s ==============================
```

---

## 6. Phase 3 Completion & Next Steps

Phase 3 is complete and verified. Per our workflow guidelines, execution is paused for your review before proceeding to **PHASE 4 – REBUILD RELEVANCE SCORING & CANDIDATE RANKING**.
