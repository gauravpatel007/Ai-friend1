# Phase 2 Completion Report: Rebuild AI Intent Understanding Using Structured Outputs

**Project:** Bond's Movie Hub Recommendation Engine Upgrade  
**Phase:** 2 of 10  
**Status:** Completed & Verified  
**Date:** 2026-11-02  

---

## 1. Executive Summary

Phase 2 replaces ad-hoc regex heuristics and unstructured string predictions with a **validated, structured intent understanding system** powered by native JSON schema enforcement, Pydantic validation, and a canonical movie taxonomy.

```
+---------------------------------------------------------------------------------------------------+
|                                   USER QUERY: "Recommend a mind-bending sci-fi with plot twists"  |
+---------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+---------------------------------------------------------------------------------------------------+
| STAGE A1: Few-Shot In-Context Prompt + Pydantic JSON Schema (format=StructuredOllamaIntent)       |
+---------------------------------------------------------------------------------------------------+
                                                  │
                         ┌────────────────────────┴────────────────────────┐
                         ▼                                                 ▼
             [Ollama Server Online]                             [Ollama Offline/Timeout]
                         │                                                 │
                         ▼                                                 ▼
+-------------------------------------------------+     +-----------------------------------------+
| Native JSON Extraction & 1-Time Error Repair    |     | Deterministic Rule-Based Fallback       |
+-------------------------------------------------+     +-----------------------------------------+
                         │                                                 │
                         └────────────────────────┬────────────────────────┘
                                                  │
                                                  ▼
+---------------------------------------------------------------------------------------------------+
| STAGE A2: Canonical Taxonomy Normalization (_normalize_and_merge_intent)                          |
| - TMDB ID mapping (Science Fiction -> 878, Mystery -> 9648)                                       |
| - OR vs. AND Genre separation (genres_any vs. genres_all)                                         |
| - Plot devices (plot twist, unreliable narrator, time loop) mapped to TMDB keywords                |
| - Regional languages (ml, te, ta, hi, gu) mapped to geographic industry rules                      |
+---------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+---------------------------------------------------------------------------------------------------+
| OUTPUT: ParsedRecommendationIntent                                                                |
| query_type: PLOT_BASED_DISCOVERY | genres_any: ['Science Fiction', 'Mystery'] | confidence: 0.96   |
+---------------------------------------------------------------------------------------------------+
```

### Key Milestones Achieved:
1. **Pydantic Structured Output Schema (`StructuredOllamaIntent`):** Implemented in [`movie_models.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/movie_models.py).
2. **Native Ollama JSON Schema Generation:** Updated [`ollama_client.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ollama_client.py) to pass `format=StructuredOllamaIntent.model_json_schema()`, completely eliminating thought tokens and markdown backtick artifacts.
3. **Canonical Genre & Keyword Taxonomy:** Built [`movie_taxonomy.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/movie_taxonomy.py) defining canonical TMDB IDs, mood expansions, slang decomposition, plot devices, regional boundaries, and era bounds.
4. **Disambiguation of OR vs. AND Conditions:** Structured extraction properly segregates `genres_any` (alternatives/OR logic) and `genres_all` (mandatory combo/AND logic).
5. **Plot-Based Concept Recognition:** Added extraction for high-concept plot devices (e.g., unexpected endings, unreliable narrators, time loops, parallel universes) without hallucinating fake titles.
6. **Controlled 1-Time Self-Repair & Offline Fallback:** If schema validation fails, a single targeted repair turn is executed; if the server remains unreachable, execution falls back cleanly to [`parse_intent_deterministic()`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/movie_recommendation_engine.py#L234).
7. **Notification Toast Clarification & Bug Fix:** Fixed alert bubbling in [`controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L600) so that `"No Speech Heard"` Windows notifications are suppressed when `voice.notify_on_empty_speech = false` or `general.show_tray_notifications = false`.

---

## 2. Benchmark Metrics: Before vs. After Phase 2

Evaluated against the 45-query ground truth benchmark suite created in Phase 1:

| Metric | Phase 1 Baseline | Phase 2 Upgrade | Delta | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Intent Extraction Accuracy** | **64.44%** | **88.89%** | **+24.45%** | **Significantly Improved** |
| Category E: Plot Discovery Accuracy | **0.0%** | **100.0%** | **+100.0%** | **Fixed** |
| Category A: Similar Movies Accuracy | 100.0% | 100.0% | 0.0% | Preserved |
| Category B: Genre Discovery Accuracy | 100.0% | 100.0% | 0.0% | Preserved |
| **Reference Movie Resolution** | 100.0% | 100.0% | 0.0% | Preserved |
| **Zero-Result Rate** | 0.0% | 0.0% | 0.0% | Preserved |
| **Avg Relevant Titles in Top 5** | 4.36 / 5.0 | 4.47 / 5.0 | +0.11 | Improved |
| **Duplicate Candidate Rate** | 0.0% | 0.0% | 0.0% | Clean |
| **Avg Retrieval Time** | 370.5 ms | 309.2 ms | -61.3 ms | Optimized |

---

## 3. Schema & Implementation Details

### 3.1 Pydantic Intent Schema (`StructuredOllamaIntent`)
Defined in [`app/api/movie_models.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/movie_models.py):

```python
class RecommendationQueryType(str, Enum):
    SIMILAR_TO = "similar_to"
    GENRE_DISCOVERY = "genre_discovery"
    MOOD_DISCOVERY = "mood_discovery"
    PLOT_BASED_DISCOVERY = "plot_based_discovery"
    REGIONAL_DISCOVERY = "regional_discovery"
    TIME_BASED_DISCOVERY = "time_based_discovery"
    PERSON_BASED_DISCOVERY = "person_based_discovery"
    HYBRID_DISCOVERY = "hybrid_discovery"
    GENERAL_DISCOVERY = "general_discovery"

class StructuredOllamaIntent(BaseModel):
    query_type: RecommendationQueryType
    content_type: str = "movie"
    genres_any: List[str] = []
    genres_all: List[str] = []
    moods: List[str] = []
    themes: List[str] = []
    plot_elements: List[str] = []
    keywords_any: List[str] = []
    reference_titles: List[str] = []
    reference_persons: List[str] = []
    original_languages: List[str] = []
    regions: List[str] = []
    countries: List[str] = []
    release_year_from: Optional[int] = None
    release_year_to: Optional[int] = None
    must_include: List[str] = []
    must_exclude: List[str] = []
    soft_preferences: List[str] = []
    confidence: float = 1.0
```

### 3.2 Canonical Taxonomy & Dictionary
Maintained in [`app/ai/movie_taxonomy.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/movie_taxonomy.py):
- **Genres & Slang:** Mappings for 19 TMDB Movie genres and 16 TV genres, with colloquial slang decomposition (e.g. `sci-fi`, `rom-com`, `whodunit`, `neo-noir`, `cyberpunk`, `slasher`).
- **Plot Elements:** Dedicated mappings for high-concept plot devices (`unexpected ending`, `unreliable narrator`, `time loop`, `parallel universes`, `reality distortion`, `detective protagonist`, `revenge`) mapped directly to verified TMDB search keywords.
- **Regional Languages:** Mappings for Indian cinema (`ml`, `te`, `ta`, `kn`, `hi`, `gu`, `mr`, `bn`) and international cinema (`ko`, `ja`, `es`, `fr`, `de`, `it`, `en`).
- **Temporal Bounds:** Mappings for decades (`90s`, `80s`, `70s`, `2000s`, `2010s`), eras (`recent`, `classic`), and explicit numerical ranges.

---

## 4. Test Verification Summary

All 45 automated verification tests across the recommendation engine and lifecycle subsystems passed successfully:

1. **Phase 2 Dedicated Tests:** [`tests/test_movie_recommendation_phase2.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_movie_recommendation_phase2.py) — **10 Passed**
   - Schema validation, serialization, and JSON schema export.
   - Canonical genre normalization (including plural and slang variants).
   - OR vs. AND logic detection.
   - Category E Plot discovery classification.
   - Category D Regional discovery classification.
   - 1-time controlled repair execution.
   - Offline fallback handling.
2. **Upgrade Regression Tests:** [`tests/test_movie_recommendation_upgrade.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_movie_recommendation_upgrade.py) — **16 Passed**
3. **Phase 1 Evaluation Benchmark Suite:** [`tests/test_movie_recommendation_evaluation.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_movie_recommendation_evaluation.py) — **16 Passed**
4. **Notification Suppression Tests:** [`tests/test_notification_suppression.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_notification_suppression.py) — **3 Passed**

---

## 5. User Feedback & Notification Troubleshooting

### "No Speech Heard" Toast Notification Setting
The Windows toast notification shown in your screenshot occurs when the local Whisper engine detects ambient silence after voice activity detection triggers.

**How it is controlled:**
1. **Config flag:** In `config/default_config.json` and user `settings.json`:
   ```json
   "voice": {
       "notify_on_empty_speech": false
   }
   ```
2. **Global notification toggle:**
   ```json
   "general": {
       "show_tray_notifications": true
   }
   ```
3. **Bug fix implemented in Phase 2:**
   In [`controller.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/controller.py#L602-L606), the notification suppression check was hoisted before `show_buddy_toast` so that empty speech warnings never pop up intrusive desktop banners when `notify_on_empty_speech` is `false`.

---

## 6. Phase 2 Completion Checklist & Next Steps

- [x] Separate intent understanding from movie catalog recommendation.
- [x] Pydantic structured output schema validated with native Ollama JSON format mode.
- [x] Few-shot system prompt verified against local `llama3.2:3b`.
- [x] Canonical taxonomy and dictionary for genres, moods, plot devices, and regional languages.
- [x] Category E Plot Discovery accuracy improved from 0.0% to 100.0%.
- [x] Overall intent extraction accuracy increased from 64.44% to 88.89%.
- [x] All 45 unit and regression tests passing.

> [!IMPORTANT]
> **STOPPING CONDITION:** As instructed, Phase 2 is complete and all deliverables have been verified. I will pause here and await your approval before proceeding to **PHASE 3 – REBUILD THE MULTI-STAGE CANDIDATE RETRIEVAL PIPELINE**.
