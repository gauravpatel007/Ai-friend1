# Bond Movie Hub — Phase 5: Local Semantic Embeddings Technical Report

**Document ID:** `BMH-P5-SEMANTIC-2026-11-02`  
**Phase:** 5 of 10 — Local Semantic Understanding, Vector Embeddings & 2-Tier Caching  
**Status:** COMPLETE & VERIFIED  
**Date:** 2026-11-02  

---

## 1. Executive Summary

In **Phase 5**, we developed and integrated a zero-cloud, privacy-preserving **Local Semantic Embedding System** ([`MovieSemanticService`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/movie_semantic_service.py)) for Bond's Movie Hub.

### The Problem Solved
Traditional keyword matching struggles with vocabulary mismatches. For example:
- **User query:** *"Movies where the main character cannot trust their own memories."*
- **Movie synopsis (*Memento*):** *"A man struggles to distinguish reality from his fragmented memories in an isolated facility."*

Keyword search misses this relationship because the words "cannot trust their own" and "distinguish reality from fragmented" do not overlap literally. A semantic vector embedding captures the underlying conceptual meaning and recognizes their high conceptual proximity.

### What Was Built
1. **Local Model Evaluation & Integration:** Evaluated local Ollama embedding models (`all-minilm:latest`, `nomic-embed-text:latest`, `mxbai-embed-large:latest`). Selected `all-minilm` (45 MB, 384 dimensions) as the primary engine for its **69 ms inference latency** and **185 ms batch-5 throughput** on CPU with zero GPU requirement, while maintaining compatibility with `nomic-embed-text` (768 dimensions).
2. **Movie Document Synthesis & SHA-256 Hashing:** Automatically synthesizes dense, contextual movie representations combining Title, Overview, Genres, and Thematic Keywords, versioned with 16-character SHA-256 digests for automatic cache invalidation upon synopsis edits.
3. **High-Performance 2-Tier Caching:**
   - **Tier 1 (In-Memory LRU Cache):** Delivers instant **0.0 ms** vector retrieval for repeated session queries.
   - **Tier 2 (ACID SQLite Cache):** Persists vectors in [`movie_embeddings_cache`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/memory/database.py#L288) via [`MovieStorageRepository`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/memory/movie_storage_repository.py#L804), eliminating redundant Ollama inferences across app restarts.
4. **Normalized Cosine Scoring Integration:** Integrated continuous cosine similarity vectors directly into Phase 4's multi-signal ranking formula (65% neural vector similarity + 35% trope/rule confirmation within the 30% semantic plot signal).
5. **Zero-Error Fallback Architecture:** If Ollama daemon is offline or embedding models are unavailable, discovery is never blocked; the system falls back cleanly to Phase 4's deterministic keyword/trope scoring and logs `semantic_ranking: {"active": False}` in telemetry.
6. **Regression Verification:** All **71 tests** across all 5 phases pass cleanly, and the 45-query evaluation benchmark achieved **4.44 / 5.0 (88.8%) top-5 relevance** with complete recommendation latency dropping to **1,037.0 ms**.

---

## 2. Local Embedding Model Evaluation

Per Requirement 5.2, we inspected the user's local Ollama environment and benchmarked candidate models directly on the host hardware (Windows 11, Intel Core CPU, loopback connection):

```mermaid
quadrantChart
    title Embedding Model Evaluation Matrix (Latency vs Quality vs Footprint)
    x-axis Low Memory Footprint --> High Memory Footprint
    y-axis High Latency (Slow) --> Low Latency (Fast)
    quadrant-1 High Resource / High Speed
    quadrant-2 Production Sweet Spot (Recommended)
    quadrant-3 Heavy / Cloud Alternative
    quadrant-4 Resource Intensive / Slow
    "all-minilm (45 MB)": [0.15, 0.92]
    "nomic-embed-text (274 MB)": [0.45, 0.25]
    "mxbai-embed-large (669 MB)": [0.75, 0.15]
    "embeddinggemma (Not Installed)": [0.60, 0.30]
```

### 2.1 Model Comparison & Benchmark Results

| Model | Size | Dimensions | Cold Start | Warm Single Latency | Batch-5 Latency | Discrimination Margin | Hardware Recommendation |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **`all-minilm:latest`** (Selected) | **45 MB** | **384** | **2.09 s** | **69.3 ms** | **185.1 ms** (~37ms/doc) | **+0.0778** | **Recommended Primary:** Zero GPU load, ultra-low memory, instant responses. |
| `nomic-embed-text:latest` | 274 MB | 768 | 58.75 s | 4,014.7 ms | ~18,000 ms | +0.0771 | Compatible secondary: High quality but 58x slower on CPU without dedicated GPU. |
| `mxbai-embed-large:latest` | 669 MB | 1024 | >90 s | ~7,500 ms | >35,000 ms | +0.0810 | Too heavy for interactive desktop responsiveness on CPU. |

**Decision:** `all-minilm` produces virtually identical semantic discrimination margins (+0.0778 vs +0.0771) to `nomic-embed-text` while executing **58 times faster** with **6 times less disk footprint**. We configured `all-minilm` as the default engine with seamless fallback to `nomic-embed-text` if selected.

---

## 3. Architecture & Data Flow

```mermaid
flowchart TD
    subgraph Query Processing
        UQ[User Query / Natural Language Intent] --> SQ[MovieSemanticService.build_semantic_query]
        SQ --> QE[OllamaClient.embed: all-minilm<br/>Dim: 384]
        QE --> QVec[Query Vector Q]
    end

    subgraph Candidate Pool
        Cands[TMDB Retrieved Candidates<br/>Tiers 1-5: Similar, Recommendations, Discover]
    end

    subgraph Two-Tier Caching Layer
        Cands --> MemCheck{Tier 1: In-Memory LRU?}
        MemCheck -- Hit --> CachedVec[Instant Vector (0ms)]
        MemCheck -- Miss --> DBCheck{Tier 2: SQLite Cache?}
        DBCheck -- Hit --> DBVec[SQLite Vector (1ms)]
        DBCheck -- Miss --> BatchEmbed[Batch /api/embed via Ollama<br/>185ms for 5 docs]
        BatchEmbed --> SaveDB[(movie_embeddings_cache)]
        BatchEmbed --> SaveMem[In-Memory Cache]
        BatchEmbed --> NewVec[New Vector]
    end

    subgraph Cosine Scoring & Ranking
        QVec & CachedVec & DBVec & NewVec --> Cosine[Cosine Similarity: cos(Q, D)]
        Cosine --> NormScore[Calibrated Range: 0.0 to 1.0]
        NormScore --> Phase4[Phase 4 Multi-Signal Ranking Engine]
        Phase4 --> Blend[30% Plot Signal = 0.65 * NeuralSim + 0.35 * TropeScore]
        Blend --> Output[Top-K Recommendations + Diagnostics + Grounded Explanations]
    end
```

### 3.1 Document Synthesis & Hashing
Each movie's semantic document is constructed via:
```python
doc = f"Title: {cand.title}. Genres: {', '.join(cand.genre_names)}. Overview: {cand.overview}. Themes and Keywords: {', '.join(cand.keywords)}."
```
A 16-character SHA-256 digest `doc_hash = hashlib.sha256(doc.encode()).hexdigest()[:16]` is stored alongside the vector. When TMDB metadata or overview updates, the hash mismatches and invalidates the stale vector automatically.

### 3.2 Vector Storage Schema
Added to SQLite database via [`DatabaseManager._init_schema()`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/memory/database.py#L288-L305):
```sql
CREATE TABLE IF NOT EXISTS movie_embeddings_cache (
    tmdb_id INTEGER NOT NULL,
    media_type TEXT NOT NULL DEFAULT 'movie',
    model_name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    doc_hash TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tmdb_id, media_type, model_name)
);
CREATE INDEX IF NOT EXISTS idx_movie_embeddings_tmdb ON movie_embeddings_cache(tmdb_id, media_type);
```

---

## 4. Mathematical Formulation

### 4.1 Cosine Similarity
For query embedding $\mathbf{q}$ and candidate document embedding $\mathbf{d}$:

$$\cos(\mathbf{q}, \mathbf{d}) = \frac{\mathbf{q} \cdot \mathbf{d}}{\|\mathbf{q}\|_2 \|\mathbf{d}\|_2} = \frac{\sum_{j=1}^{M} q_j d_j}{\sqrt{\sum_{j=1}^{M} q_j^2} \sqrt{\sum_{j=1}^{M} d_j^2}}$$

### 4.2 Score Normalization & Calibration
For `all-minilm`, raw cosine similarities for unrelated movies hover around $0.15 - 0.25$, whereas genuine conceptual matches reach $0.45 - 0.70+$. We map raw cosine similarity into a calibrated $[0.0, 1.0]$ signal:

$$S_{\text{semantic}} = \max\left(0.0, \min\left(1.0, \frac{\cos(\mathbf{q}, \mathbf{d}) - 0.15}{0.70 - 0.15}\right)\right)$$

### 4.3 Ranking Signal Blending
Within Phase 4's 30% Semantic Plot Weight:

$$s_1 = 0.65 \cdot S_{\text{semantic}} + 0.35 \cdot S_{\text{trope}}$$

When the embedding service is offline or unavailable, the engine falls back seamlessly to $s_1 = S_{\text{trope}}$ (pure deterministic Phase 4 scoring).

---

## 5. Implementation Files

| File | Changes & Purpose |
|---|---|
| [`app/ai/ollama_client.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ollama_client.py#L463-L574) | Added `embed()` method supporting batch `/api/embed` and legacy `/api/embeddings` fallback with unit-test support. |
| [`app/memory/database.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/memory/database.py#L288-L305) | Added `movie_embeddings_cache` table and indexes with WAL persistence. |
| [`app/memory/movie_storage_repository.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/memory/movie_storage_repository.py#L804-L905) | Added single & batch cache retrieval and atomic transaction batch upsert methods. |
| [`app/ai/movie_semantic_service.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/movie_semantic_service.py#L1-L300) | **New core Phase 5 service:** document synthesis, hashing, 2-tier caching, query embedding, and cosine similarity. |
| [`app/ai/movie_ranking_engine.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/movie_ranking_engine.py#L250-L770) | Integrated `semantic_sim` into `score_semantic_plot`, `score_candidate`, and `rank_candidates`. Added `neural_semantic_similarity` to breakdown. |
| [`app/ai/movie_recommendation_engine.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/movie_recommendation_engine.py#L1580-L1620) | Integrated `MovieSemanticService` into `rank_candidates` and recorded diagnostics telemetry. |
| [`app/api/movie_models.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/movie_models.py#L62) | Added `genre_names`, `keywords`, and `raw_query` fields. |
| [`tests/test_movie_recommendation_phase5_semantic.py`](file:///g:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_movie_recommendation_phase5_semantic.py#L1-L425) | Comprehensive 8-scenario unit test suite covering vocabulary bridging, caching, query formulation, and fallback. |

---

## 6. Verification & Test Results

### 6.1 Unit & Regression Suite (All 71 Tests Passing)
```
============================= 71 passed in 19.47s =============================
tests/test_movie_recommendation_phase5_semantic.py::test_semantic_matching_bridges_vocabulary_mismatch PASSED [  1%]
tests/test_movie_recommendation_phase5_semantic.py::test_cosine_similarity_math PASSED [  2%]
tests/test_movie_recommendation_phase5_semantic.py::test_movie_document_synthesis_and_hash_invalidation PASSED [  4%]
tests/test_movie_recommendation_phase5_semantic.py::test_two_tier_caching_avoids_redundant_inference PASSED [  5%]
tests/test_movie_recommendation_phase5_semantic.py::test_semantic_query_formulation PASSED [  7%]
tests/test_movie_recommendation_phase5_semantic.py::test_ranking_engine_incorporates_semantic_similarity PASSED [  8%]
tests/test_movie_recommendation_phase5_semantic.py::test_graceful_fallback_when_embedding_service_offline PASSED [  9%]
tests/test_movie_recommendation_phase5_semantic.py::test_e2e_recommendation_pipeline_with_semantic_ranking PASSED [ 11%]
tests/test_movie_recommendation_phase4_ranking.py (10 passed)
tests/test_movie_recommendation_phase3_retrieval.py (11 passed)
tests/test_movie_recommendation_phase3.py (13 passed)
tests/test_movie_recommendation_phase2.py (10 passed)
tests/test_movie_recommendation_upgrade.py (16 passed)
tests/test_notification_suppression.py (3 passed)
```

### 6.2 45-Query Benchmark Evaluation
- **Total Queries Evaluated:** 45 / 45
- **Avg Relevant Results in Top 5:** **4.44 / 5.0 (88.8%)**
- **Mood Discovery:** **5.00 / 5.0 (100.0%)**
- **Regional Cinema:** **5.00 / 5.0 (100.0%)**
- **Complex Requests:** **5.00 / 5.0 (100.0%)**
- **Zero-Result Rate:** **0.0%**
- **Duplicate Rate:** **0.0%**
- **Avg Complete Recommendation Latency:** **1,037.0 ms** (reduced from 1,264 ms in Phase 4 due to 2-tier vector caching)

---

## 7. Next Steps & Phase 6 Readiness

Phase 5 is complete and verified. Per our protocol, execution stops here to await user review and sign-off before proceeding to:

**PHASE 6 – GROUNDED RECOMMENDATION EXPLANATIONS & USER INTERACTION**
- Anchoring Ollama explanation essays strictly in retrieved TMDB facts and the transparent `relevance_breakdown`.
- Preventing hallucinated cast, plot details, or sequels.
- Interactive user feedback actions (thumbs up/down, "not interested", "seen it") to refine recommendation taste.
