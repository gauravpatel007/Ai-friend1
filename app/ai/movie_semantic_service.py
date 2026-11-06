"""Movie Semantic Understanding & Local Vector Embedding Service.

Phase 5 implementation of local semantic understanding using lightweight local
embeddings (all-minilm, nomic-embed-text).

Provides:
- Semantic document synthesis from movie metadata (title, overview, genres, keywords).
- SHA-256 document hashing for invalidation and caching.
- 2-tier caching: in-memory LRU cache + persistent SQLite cache.
- High-throughput batch embedding generation via Ollama /api/embed.
- Cosine similarity calculation and normalized semantic score distribution.
- Zero-downtime, transparent fallback when Ollama or embedding model is offline.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from app.ai.ollama_client import OllamaClient, OllamaClientError, OllamaConnectionError
from app.api.movie_models import MediaItemSummary, ParsedRecommendationIntent
from app.memory.movie_storage_repository import MovieStorageRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Default recommended local model (45 MB, 384 dims, 69ms latency on CPU)
DEFAULT_EMBED_MODEL = "all-minilm"
FALLBACK_EMBED_MODEL = "nomic-embed-text"


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculate the cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 <= 0.0 or norm2 <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm1) * math.sqrt(norm2))


def normalize_cosine_score(raw_sim: float, model_name: str = DEFAULT_EMBED_MODEL) -> float:
    """Normalize raw cosine similarity into a well-calibrated 0.0 to 1.0 relevance signal.
    
    For all-minilm:
    Typical baseline / random movie similarity is ~0.15 - 0.25.
    Moderate thematic match is ~0.30 - 0.40.
    High semantic match is ~0.45 - 0.75+.
    
    We linearly rescale [0.15, 0.70] into [0.0, 1.0] with soft clipping.
    """
    if "nomic" in model_name:
        # nomic-embed-text baseline is higher (~0.45 - 0.55), high matches are ~0.65 - 0.85
        min_bound = 0.40
        max_bound = 0.85
    else:
        # all-minilm baseline
        min_bound = 0.15
        max_bound = 0.70

    if raw_sim <= min_bound:
        return 0.0
    if raw_sim >= max_bound:
        return 1.0
    return (raw_sim - min_bound) / (max_bound - min_bound)


class MovieSemanticService:
    """Encapsulates semantic query formulation, embedding generation, caching,
    and cosine similarity scoring against candidate movies.
    """

    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        storage_repo: Optional[MovieStorageRepository] = None,
        model_name: str = DEFAULT_EMBED_MODEL,
        enabled: bool = True,
    ) -> None:
        self.ollama_client = ollama_client or OllamaClient()
        self.storage_repo = storage_repo
        self.model_name = model_name
        self.enabled = enabled

        # In-memory fast cache: (tmdb_id, media_type, model_name) -> (doc_hash, embedding)
        self._mem_cache: Dict[Tuple[int, str, str], Tuple[str, List[float]]] = {}
        self._availability_checked: bool = False
        self._is_available: bool = False

    # =========================================================================
    # 1. Connectivity & Model Availability Check
    # =========================================================================

    def is_available(self, force_refresh: bool = False) -> bool:
        """Check if local Ollama daemon is running and the embedding model is installed."""
        if not self.enabled:
            return False

        if self._availability_checked and not force_refresh:
            return self._is_available

        try:
            if not self.ollama_client.is_server_reachable(timeout=1.5):
                logger.debug("Ollama server unreachable for semantic embeddings.")
                self._is_available = False
                self._availability_checked = True
                return False

            # Check if model is listed or test probe
            models = self.ollama_client.get_model_names()
            clean_names = [m.split(":")[0] for m in models]
            target_base = self.model_name.split(":")[0]

            if target_base in clean_names:
                self._is_available = True
            elif FALLBACK_EMBED_MODEL.split(":")[0] in clean_names:
                logger.info("Switching semantic model from '%s' to available '%s'", self.model_name, FALLBACK_EMBED_MODEL)
                self.model_name = FALLBACK_EMBED_MODEL
                self._is_available = True
            else:
                # If tags endpoint didn't list it or mock client, try small probe
                try:
                    probe = self.ollama_client.embed("test probe", model=self.model_name, timeout=3.0)
                    self._is_available = bool(probe and probe[0])
                except Exception:
                    self._is_available = False

        except Exception as e:
            logger.debug("Semantic embedding availability check error: %s", e)
            self._is_available = False

        self._availability_checked = True
        return self._is_available

    # =========================================================================
    # 2. Text Representation & Hashing
    # =========================================================================

    def build_movie_document(self, cand: MediaItemSummary) -> str:
        """Construct rich semantic text representation of a movie for embedding.
        
        Requirement 5.3: Uses Title, Overview, Genres, Keywords, and Theme information.
        """
        parts: List[str] = []
        parts.append(f"Title: {cand.title or 'Unknown'}.")

        if cand.genre_names:
            parts.append(f"Genres: {', '.join(cand.genre_names)}.")

        if cand.overview:
            parts.append(f"Overview: {cand.overview.strip()}")

        # Keywords if available
        if hasattr(cand, "keywords") and cand.keywords:
            parts.append(f"Themes and Keywords: {', '.join(cand.keywords[:8])}.")

        doc_text = " ".join(parts)

        # Prefix for models requiring task instruction (e.g. nomic-embed-text)
        if "nomic" in self.model_name:
            return f"search_document: {doc_text}"
        return doc_text

    def build_semantic_query(self, intent: ParsedRecommendationIntent) -> str:
        """Formulate a comprehensive semantic search query from parsed intent.
        
        Requirement 5.4: Converts user's normalized search intent into a semantic query.
        """
        parts: List[str] = []

        # If user entered an explicit raw query, lead with that
        if intent.raw_query:
            clean_q = intent.raw_query.strip().rstrip(".?!")
            parts.append(clean_q)

        intent_details: List[str] = []
        if intent.genres_any:
            intent_details.append(f"genres: {', '.join(intent.genres_any)}")
        elif intent.genres:
            intent_details.append(f"genres: {', '.join(intent.genres)}")

        if intent.mood:
            intent_details.append(f"mood: {intent.mood.replace('_', ' ')}")

        if intent.themes:
            intent_details.append(f"themes: {', '.join(intent.themes)}")

        if intent.plot_elements:
            intent_details.append(f"plot: {', '.join(intent.plot_elements)}")

        if intent.keywords_any:
            intent_details.append(f"key elements: {', '.join(intent.keywords_any[:5])}")

        if intent_details:
            parts.append(f"({'; '.join(intent_details)})")

        query_text = " ".join(parts) if parts else (intent.interpreted_summary or "Recommended movies")

        # Prefix for models requiring query instruction (e.g. nomic-embed-text)
        if "nomic" in self.model_name:
            return f"search_query: {query_text}"
        return query_text

    @staticmethod
    def compute_doc_hash(text: str) -> str:
        """Return 16-character SHA-256 hex digest for document versioning/cache key."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    # =========================================================================
    # 3. Query & Movie Embedding Retrieval with 2-Tier Caching
    # =========================================================================

    def get_query_embedding(self, query_text: str) -> Optional[List[float]]:
        """Generate high-dimensional vector embedding for the semantic search query."""
        if not query_text or not self.is_available():
            return None

        try:
            t0 = time.perf_counter()
            vectors = self.ollama_client.embed(query_text, model=self.model_name, timeout=10.0)
            if vectors and len(vectors) > 0 and len(vectors[0]) > 0:
                logger.debug(
                    "Generated query embedding in %.1fms (dim: %d)",
                    (time.perf_counter() - t0) * 1000.0,
                    len(vectors[0]),
                )
                return vectors[0]
        except Exception as e:
            logger.warning("Failed to generate query embedding: %s", e)
        return None

    def get_candidate_embeddings(
        self,
        candidates: List[MediaItemSummary],
    ) -> Tuple[Dict[int, List[float]], Dict[str, Any]]:
        """Retrieve embeddings for all candidate movies using 2-tier caching.
        
        Returns:
            Tuple of:
            - Dict mapping tmdb_id -> embedding vector
            - Diagnostics dict (cache_hits, misses, generation_time_ms)
        """
        if not candidates or not self.is_available():
            return {}, {"cached_hits": 0, "generated": 0, "status": "unavailable"}

        embeddings: Dict[int, List[float]] = {}
        missing_candidates: List[MediaItemSummary] = []
        missing_docs: List[str] = []
        missing_hashes: List[str] = []

        cache_hits = 0
        t0 = time.perf_counter()

        # Step 1: Check In-Memory Cache
        remaining_candidates: List[MediaItemSummary] = []
        for cand in candidates:
            if not cand.id:
                continue
            m_type = cand.media_type or "movie"
            cache_key = (cand.id, m_type, self.model_name)
            doc_text = self.build_movie_document(cand)
            doc_hash = self.compute_doc_hash(doc_text)

            if cache_key in self._mem_cache:
                c_hash, c_emb = self._mem_cache[cache_key]
                if c_hash == doc_hash:
                    embeddings[cand.id] = c_emb
                    cache_hits += 1
                    continue

            remaining_candidates.append(cand)

        # Step 2: Check Persistent SQLite Cache
        if remaining_candidates and self.storage_repo:
            tmdb_ids = [c.id for c in remaining_candidates if c.id]
            db_cached = self.storage_repo.get_movie_embeddings_batch(
                tmdb_ids,
                media_type="movie",
                model_name=self.model_name,
            )
            for cand in remaining_candidates:
                if not cand.id:
                    continue
                doc_text = self.build_movie_document(cand)
                doc_hash = self.compute_doc_hash(doc_text)

                if cand.id in db_cached:
                    c_hash, c_emb = db_cached[cand.id]
                    if c_hash == doc_hash:
                        embeddings[cand.id] = c_emb
                        # Populate in-memory cache
                        self._mem_cache[(cand.id, cand.media_type or "movie", self.model_name)] = (c_hash, c_emb)
                        cache_hits += 1
                        continue

                missing_candidates.append(cand)
                missing_docs.append(doc_text)
                missing_hashes.append(doc_hash)
        else:
            for cand in remaining_candidates:
                if cand.id:
                    doc_text = self.build_movie_document(cand)
                    missing_candidates.append(cand)
                    missing_docs.append(doc_text)
                    missing_hashes.append(self.compute_doc_hash(doc_text))

        # Step 3: Batch Generate Embeddings for Cache Misses
        generated_count = 0
        if missing_candidates and missing_docs:
            try:
                t_gen_start = time.perf_counter()
                batch_vectors = self.ollama_client.embed(
                    missing_docs,
                    model=self.model_name,
                    timeout=30.0,
                )
                t_gen_ms = (time.perf_counter() - t_gen_start) * 1000.0
                logger.info(
                    "Generated %d movie embeddings via %s in %.1fms (%.1fms/doc)",
                    len(batch_vectors),
                    self.model_name,
                    t_gen_ms,
                    t_gen_ms / max(1, len(batch_vectors)),
                )

                db_save_entries: List[Dict[str, Any]] = []
                for cand, d_hash, emb_vec in zip(missing_candidates, missing_hashes, batch_vectors):
                    if cand.id and emb_vec:
                        embeddings[cand.id] = emb_vec
                        m_type = cand.media_type or "movie"
                        self._mem_cache[(cand.id, m_type, self.model_name)] = (d_hash, emb_vec)
                        generated_count += 1
                        db_save_entries.append({
                            "tmdb_id": cand.id,
                            "media_type": m_type,
                            "model_name": self.model_name,
                            "version": 1,
                            "doc_hash": d_hash,
                            "embedding": emb_vec,
                        })

                # Persist to SQLite in a single transaction
                if self.storage_repo and db_save_entries:
                    self.storage_repo.save_movie_embeddings_batch(db_save_entries)

            except Exception as e:
                logger.warning("Batch embedding generation failed: %s", e)

        total_time_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        diagnostics = {
            "cached_hits": cache_hits,
            "generated": generated_count,
            "total_candidates": len(candidates),
            "model_name": self.model_name,
            "time_ms": total_time_ms,
            "status": "success" if embeddings else "empty",
        }
        return embeddings, diagnostics

    # =========================================================================
    # 4. Semantic Similarity Scoring Pipeline
    # =========================================================================

    def score_candidates_semantically(
        self,
        candidates: List[MediaItemSummary],
        query_embedding: List[float],
        candidate_embeddings: Dict[int, List[float]],
    ) -> Dict[int, float]:
        """Compute normalized cosine similarity score [0.0 to 1.0] for each candidate.
        
        Requirement 5.5: Compares query embedding with candidate movie embeddings.
        """
        if not query_embedding or not candidate_embeddings:
            return {}

        scores: Dict[int, float] = {}
        for cand in candidates:
            if not cand.id or cand.id not in candidate_embeddings:
                continue
            cand_emb = candidate_embeddings[cand.id]
            raw_sim = cosine_similarity(query_embedding, cand_emb)
            norm_sim = normalize_cosine_score(raw_sim, model_name=self.model_name)
            scores[cand.id] = round(norm_sim, 4)

        return scores
