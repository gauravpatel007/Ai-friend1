"""Phase 4: Real Movie Relevance and Multi-Signal Ranking Engine.

Evaluates candidate relevance against natural language intent using:
- Normalized feature representations (genres, synopsis, keywords, ratings, source).
- Configurable multi-signal weighting:
  - Semantic plot similarity: 30%
  - Genre relevance: 20%
  - Themes & keywords: 20%
  - Mood & atmosphere: 10%
  - Source signal: 10%
  - Quality & credibility: 5%
  - Contextual preferences: 5%
- Hard filter enforcement (language, region, release era, exclusions) vs soft preference boosting.
- Bayesian credibility smoothing (avoiding raw popularity dominance and vote cutoff traps).
- Diversity controls with franchise repetition damping (preventing 5 identical sequels from clogging results).
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from app.api.movie_models import (
    MediaItemSummary,
    MovieUserPreferences,
    ParsedRecommendationIntent,
    RelevanceWeightsModel,
    UserMovieProfile,
)
from app.ai.movie_taxonomy import (
    MOOD_DICTIONARY,
    PLOT_ELEMENT_DICTIONARY,
    TMDB_ID_TO_GENRE,
    TMDB_KEYWORD_IDS,
    TMDB_MOVIE_GENRES,
    resolve_mood_semantics,
)
from app.ai.regional_classifier import (
    INDIAN_LANGUAGES,
    REGION_INDIAN,
    SOUTH_INDIAN_LANGUAGES,
)

logger = logging.getLogger(__name__)

STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have",
    "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers",
    "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've",
    "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more",
    "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only",
    "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such", "than",
    "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there", "there's",
    "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to",
    "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
    "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you",
    "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves",
}

THEMATIC_SYNONYM_MAP: Dict[str, List[str]] = {
    "unrequited love": [
        "unrequited", "one-sided", "crush", "friendzone", "heartbreak",
        "love triangle", "secret love", "rejection", "falls for", "friend",
        "romance", "romantic", "yearning", "infatuation", "feelings",
    ],
    "family drama": [
        "family", "father", "mother", "brother", "sister", "parents",
        "household", "generation", "relative", "relatives", "marriage",
        "wedding", "patriarch", "matriarch", "domestic", "clan",
    ],
    "social issues": [
        "society", "social", "caste", "class", "poverty", "struggle",
        "system", "tradition", "pressure", "cultural", "inequality", "activism",
    ],
    "emotional": [
        "emotional", "feelings", "heartfelt", "touching", "tears", "moving",
        "warmth", "sentimental", "poignant", "drama", "bonding", "sensitive",
    ],
    "romantic comedy": [
        "romantic comedy", "rom-com", "romance", "comedy", "humor", "fun",
        "dating", "relationships", "witty", "lighthearted", "quirky",
    ],
    "friendship": [
        "friendship", "friends", "friend", "roommate", "gang", "buddies",
        "companionship", "bromance", "loyalty", "mates",
    ],
    "coming-of-age": [
        "coming of age", "youth", "college", "campus", "young", "growing up",
        "ambition", "dreams", "career", "student", "adolescent",
    ],
    "feel-good": [
        "feel-good", "wholesome", "heartwarming", "uplifting", "charming",
        "delightful", "sweet", "fun", "positive",
    ],
    "dark & gritty": [
        "dark", "gritty", "intense", "raw", "crime", "violence",
        "underworld", "noir", "gloomy", "ruthless",
    ],
    "plot twists": [
        "twist", "unexpected", "secret", "reveal", "revelation",
        "shocking", "conspiracy", "truth", "deception", "surprise",
    ],
    "plot similarity": [
        "similar", "parallel", "trope", "storyline", "narrative", "premise",
        "journey", "scenario", "situation", "relationship", "dynamic", "plot",
    ],
}


@dataclass
class CandidateFeatures:
    """Normalized feature representation of a retrieved candidate title."""
    movie_id: int
    title: str
    original_title: str
    media_type: str
    genre_ids: List[int]
    genre_names: List[str]
    overview: str
    overview_tokens: Set[str]
    keywords: List[str]
    keyword_ids: Set[int]
    language: Optional[str]
    origin_country: List[str]
    release_year: Optional[int]
    vote_average: float
    vote_count: int
    popularity: float
    retrieval_source: Optional[str]
    reference_movie_id: Optional[int]
    franchise_key: str

    # Sub-scores (0.0 to 1.0 scale)
    semantic_plot_score: float = 0.0
    genre_relevance_score: float = 0.0
    theme_keywords_score: float = 0.0
    mood_atmosphere_score: float = 0.0
    source_signal_score: float = 0.0
    quality_credibility_score: float = 0.0
    contextual_preferences_score: float = 0.0
    total_relevance_score: float = 0.0


def extract_franchise_key(title: str) -> str:
    """Extract canonical franchise or title cluster key for diversity grouping.
    
    Examples:
    - 'John Wick: Chapter 2' -> 'john wick'
    - 'John Wick: Chapter 3 - Parabellum' -> 'john wick'
    - 'Knives Out' -> 'knives out'
    - 'Glass Onion: A Knives Out Mystery' -> 'knives out'
    - 'Spider-Man: Homecoming' -> 'spider-man'
    - 'The Dark Knight Rises' -> 'the dark knight'
    """
    if not title:
        return ""
    t_clean = title.strip().lower()

    # Known franchise prefixes
    for f_stem in [
        "the dark knight",
        "spider-man",
        "knives out",
        "john wick",
        "star wars",
        "harry potter",
        "lord of the rings",
        "mission: impossible",
        "mission impossible",
        "planet of the apes",
        "fast & furious",
        "fast and furious",
        "jurassic park",
        "jurassic world",
        "avengers",
        "batman",
    ]:
        if t_clean.startswith(f_stem):
            return f_stem

    # Split subtitle separators (: or spaced dash or em-dash/en-dash)
    parts = re.split(r":|\s+[-–—]\s+|[–—]", t_clean)
    stem = parts[0].strip()

    # Strip trailing numerals or chapter mentions: 'John Wick 2' -> 'john wick', 'Rocky IV' -> 'rocky'
    stem_no_num = re.sub(
        r"\b(?:part|chapter|vol|volume|season)?\s*(?:[0-9]+|[ivxlcdm]+)\b$",
        "",
        stem,
        flags=re.IGNORECASE,
    ).strip()
    if len(stem_no_num) >= 3:
        stem = stem_no_num

    # Subtitle reference check: e.g. 'A Knives Out Mystery' -> 'knives out'
    if len(parts) > 1:
        sub = parts[1].strip()
        for f_cand in ["knives out", "spider-man", "star wars", "batman", "avengers", "mission impossible"]:
            if f_cand in sub:
                return f_cand

    return stem


def tokenize_text(text: str) -> Set[str]:
    """Tokenize and filter text into informative lowercase alphanumeric tokens."""
    if not text:
        return set()
    words = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", text.lower())
    return {w for w in words if w not in STOPWORDS}


def extract_candidate_features(cand: MediaItemSummary) -> CandidateFeatures:
    """Extract normalized feature vector from a MediaItemSummary."""
    genre_names = [TMDB_ID_TO_GENRE[gid] for gid in cand.genre_ids if gid in TMDB_ID_TO_GENRE]
    overview_tokens = tokenize_text(cand.overview)
    franchise_key = extract_franchise_key(cand.title)

    # Keywords extraction from candidate overview / title
    kw_detected: List[str] = []
    kw_ids_detected: Set[int] = set()
    cand_text = f"{(cand.title or '').lower()} {(cand.overview or '').lower()}"

    for kw_str, kid in TMDB_KEYWORD_IDS.items():
        if kw_str in cand_text:
            kw_detected.append(kw_str)
            kw_ids_detected.add(kid)

    return CandidateFeatures(
        movie_id=cand.id,
        title=cand.title or "Untitled",
        original_title=cand.original_title or cand.title or "Untitled",
        media_type=cand.media_type or "movie",
        genre_ids=list(cand.genre_ids),
        genre_names=genre_names,
        overview=cand.overview or "",
        overview_tokens=overview_tokens,
        keywords=kw_detected,
        keyword_ids=kw_ids_detected,
        language=cand.original_language,
        origin_country=list(cand.origin_country or []),
        release_year=cand.release_year,
        vote_average=float(cand.vote_average or 0.0),
        vote_count=int(cand.vote_count or 0),
        popularity=float(cand.popularity or 0.0),
        retrieval_source=cand.retrieval_source,
        reference_movie_id=cand.reference_movie_id,
        franchise_key=franchise_key,
    )


class MovieRankingEngine:
    """Evaluates candidate relevance across 7 weighted signals, enforces hard filters,
    and applies controlled diversity reranking.
    """

    def __init__(self, weights: Optional[RelevanceWeightsModel] = None):
        self.weights = weights or RelevanceWeightsModel()

    def get_normalized_weights(self) -> Dict[str, float]:
        """Ensure sum of weights equals 1.0."""
        total = (
            self.weights.semantic_plot
            + self.weights.genre_relevance
            + self.weights.theme_keywords
            + self.weights.mood_atmosphere
            + self.weights.source_signal
            + self.weights.quality_credibility
            + self.weights.contextual_preferences
        )
        if total <= 0.0:
            return {
                "semantic_plot": 0.30,
                "genre_relevance": 0.20,
                "theme_keywords": 0.20,
                "mood_atmosphere": 0.10,
                "source_signal": 0.10,
                "quality_credibility": 0.05,
                "contextual_preferences": 0.05,
            }
        return {
            "semantic_plot": self.weights.semantic_plot / total,
            "genre_relevance": self.weights.genre_relevance / total,
            "theme_keywords": self.weights.theme_keywords / total,
            "mood_atmosphere": self.weights.mood_atmosphere / total,
            "source_signal": self.weights.source_signal / total,
            "quality_credibility": self.weights.quality_credibility / total,
            "contextual_preferences": self.weights.contextual_preferences / total,
        }

    # =========================================================================
    # Signal Scorers (Each outputs 0.0 to 1.0 scale + match reason)
    # =========================================================================

    def score_semantic_plot(
        self,
        features: CandidateFeatures,
        intent: ParsedRecommendationIntent,
        semantic_sim: Optional[float] = None,
    ) -> Tuple[float, Optional[str]]:
        """Score 1: Semantic plot mechanics, tropes, and neural embedding alignment (30%)."""
        plot_terms: Set[str] = set()
        for pe in intent.plot_elements:
            plot_terms.update(tokenize_text(pe))
        for kw in intent.keywords_any:
            plot_terms.update(tokenize_text(kw))
        for th in intent.themes:
            plot_terms.update(tokenize_text(th))

        overview_tokens = features.overview_tokens
        cand_overview_lower = features.overview.lower()

        # Disjunctive trope check: specific plot mechanics
        trope_matches = 0
        matched_tropes: List[str] = []

        # 1. Plot Twists / Unexpected Endings
        if any(t in intent.plot_elements or t in intent.keywords for t in ["plot twist", "plot twists", "unexpected ending", "twist ending", "shocking twist"]):
            twist_indicators = ["twist", "unexpected", "secret", "reveal", "revelation", "shocking", "conspiracy", "truth", "deception"]
            if any(tok.startswith(ind) or ind in tok for tok in overview_tokens for ind in twist_indicators if len(ind) >= 4):
                trope_matches += 1
                matched_tropes.append("unpredictable plot twists")

        # 2. Time Loops / Temporal Paradoxes
        if any("time loop" in pe or "looping" in pe or "repeating" in pe for pe in intent.plot_elements):
            loop_indicators = ["loop", "repeat", "temporal", "again", "stuck", "cycle"]
            if any(tok.startswith(w) or w in tok for tok in overview_tokens for w in loop_indicators):
                trope_matches += 1
                matched_tropes.append("time loop mechanic")

        # 3. Unreliable Narrator / Distorted Reality
        if any("unreliable" in pe or "hallucination" in pe or "memory" in pe for pe in intent.plot_elements):
            unreliable_indicators = ["memory", "hallucination", "sanity", "insane", "reality", "doubt", "paranoia", "delusion"]
            if any(tok.startswith(w) or w in tok for tok in overview_tokens for w in unreliable_indicators):
                trope_matches += 1
                matched_tropes.append("unreliable perspective")

        # 4. Parallel Universes / Multiverse
        if any("parallel" in pe or "universe" in pe or "multiverse" in pe or "dimension" in pe for pe in intent.plot_elements):
            multi_indicators = ["universe", "multiverse", "dimension", "alternate", "parallel", "quantum"]
            if any(tok.startswith(w) or w in tok for tok in overview_tokens for w in multi_indicators):
                trope_matches += 1
                matched_tropes.append("alternate reality concept")

        # 5. Detective Mystery / Investigation
        if any("detective" in pe or "whodunit" in pe or "investigation" in pe for pe in (intent.plot_elements + intent.keywords)):
            det_indicators = ["detective", "murder", "investigation", "clue", "suspect", "killer", "investigate"]
            if any(tok.startswith(w) or w in tok for tok in overview_tokens for w in det_indicators):
                trope_matches += 1
                matched_tropes.append("investigative mystery")

        # Overlap with reference title synopsis if present
        ref_overlap_score = 0.0
        if intent.reference_media and intent.reference_media.overview:
            ref_tokens = tokenize_text(intent.reference_media.overview)
            if ref_tokens and overview_tokens:
                overlap = len(ref_tokens & overview_tokens)
                ref_overlap_score = min(1.0, overlap / max(3, len(ref_tokens) * 0.25))

        # Direct token overlap with user requested plot terms
        user_term_overlap = 0.0
        if plot_terms and overview_tokens:
            matched_user_terms = len(plot_terms & overview_tokens)
            user_term_overlap = min(1.0, matched_user_terms / max(1, len(plot_terms)))

        # Baseline fallback for requests without explicit trope match or general discovery
        base_score = 0.60 if (intent.genres_any or intent.mood or intent.moods) else 0.40
        if not plot_terms and not intent.reference_media:
            rule_score = 0.70
        else:
            rule_score = max(
                min(1.0, 0.40 * trope_matches + 0.35 * user_term_overlap + 0.35 * ref_overlap_score + (0.50 if trope_matches == 0 else 0.0)),
                0.85 if trope_matches >= 1 else base_score,
            )

        # Phase 5: Integrate local neural embedding similarity when available
        if semantic_sim is not None:
            norm_sim = min(1.0, max(0.0, float(semantic_sim)))
            score = min(1.0, max(0.0, 0.65 * norm_sim + 0.35 * rule_score))
        else:
            norm_sim = None
            score = rule_score

        reason: Optional[str] = None
        if norm_sim is not None and norm_sim >= 0.40:
            if matched_tropes:
                reason = f"Features {matched_tropes[0]} ({round(norm_sim * 100)}% semantic match)"
            else:
                reason = f"Semantic narrative alignment ({round(norm_sim * 100)}% match)"
        elif matched_tropes:
            reason = f"Features {', '.join(matched_tropes)}"
        elif ref_overlap_score >= 0.5:
            reason = f"Narrative and thematic synergy with '{intent.reference_title}'"
        elif user_term_overlap >= 0.3:
            reason = "Synopsis aligns with requested plot elements"

        return min(1.0, max(0.0, score)), reason

    def score_genre_relevance(
        self,
        features: CandidateFeatures,
        intent: ParsedRecommendationIntent,
    ) -> Tuple[float, Optional[str]]:
        """Score 2: Genre alignment and DNA overlap (20%)."""
        cand_gids = set(features.genre_ids)
        score = 0.0
        reason: Optional[str] = None

        # Disjunctive (OR) Genres: intent.genres_any
        if intent.genres_any:
            target_ids = {
                TMDB_MOVIE_GENRES[g]
                for g in intent.genres_any
                if g in TMDB_MOVIE_GENRES
            }
            if target_ids:
                overlap = cand_gids & target_ids
                if overlap:
                    # Satisfying any requested genre gets strong score; additional matches reward full marks
                    score = min(1.0, 0.85 + 0.15 * (len(overlap) - 1))
                    matched_names = [TMDB_ID_TO_GENRE[gid] for gid in overlap if gid in TMDB_ID_TO_GENRE]
                    reason = f"Matches requested genre ({', '.join(matched_names)})"

        # Conjunctive (AND) Genres: intent.genres_all
        elif intent.genres_all:
            target_ids = {
                TMDB_MOVIE_GENRES[g]
                for g in intent.genres_all
                if g in TMDB_MOVIE_GENRES
            }
            if target_ids:
                overlap = cand_gids & target_ids
                score = len(overlap) / max(1, len(target_ids))
                if score >= 1.0:
                    matched_names = [TMDB_ID_TO_GENRE[gid] for gid in overlap if gid in TMDB_ID_TO_GENRE]
                    reason = f"Exact genre blend ({', '.join(matched_names)})"
                elif score >= 0.5:
                    reason = "Partial genre match"

        # Preferred Genres (from Phase 1 intent extraction / reference metadata)
        pref_genres = getattr(intent, "preferred_genres", []) or []
        if pref_genres and not score:
            target_ids = {
                TMDB_MOVIE_GENRES[g.lower()]
                for g in pref_genres
                if g.lower() in TMDB_MOVIE_GENRES
            }
            if target_ids and cand_gids:
                overlap = cand_gids & target_ids
                if overlap:
                    score = min(1.0, 0.60 + 0.20 * (len(overlap) / len(target_ids)))
                    matched_names = [TMDB_ID_TO_GENRE[gid] for gid in overlap if gid in TMDB_ID_TO_GENRE]
                    reason = f"Matches preferred genres ({', '.join(matched_names)})"

        # Reference Title Genre DNA Overlap
        if intent.reference_genres:
            ref_gids = set(intent.reference_genres)
            if ref_gids and cand_gids:
                overlap = ref_gids & cand_gids
                jaccard = len(overlap) / max(1, len(ref_gids | cand_gids))
                if overlap:
                    ref_score = min(1.0, 0.55 + 0.30 * (len(overlap) / len(ref_gids)) + 0.15 * jaccard)
                    if ref_score > score:
                        score = ref_score
                        reason = f"Shares genre DNA with '{intent.reference_title}'"

        # Complementary soft baseline: movies sharing general narrative genres (Drama, Comedy, Romance)
        if not score:
            if cand_gids & {18, 35, 10749}:  # Drama, Comedy, Romance
                score = 0.50
            else:
                score = 0.40

        # Default fallback for unconstrained genre queries
        if not intent.genres and not intent.genres_any and not intent.genres_all and not intent.reference_genres and not pref_genres:
            score = 0.75

        return min(1.0, max(0.0, score)), reason

    def score_theme_keywords(
        self,
        features: CandidateFeatures,
        intent: ParsedRecommendationIntent,
    ) -> Tuple[float, Optional[str]]:
        """Score 3: Themes and keyword descriptors with semantic cluster matching (20%)."""
        cand_text = f"{features.title.lower()} {features.overview.lower()}"
        cand_kws_lower = [k.lower() for k in features.keywords]
        cand_genres_lower = [g.lower() for g in features.genre_names]

        # Gather target keywords, themes, and preferred themes
        target_kws: List[str] = list(intent.keywords_any)
        for k in intent.keywords:
            if k not in target_kws:
                target_kws.append(k)
        for th in (getattr(intent, "themes", []) or []):
            if th not in target_kws:
                target_kws.append(th)
        for pth in (getattr(intent, "preferred_themes", []) or []):
            if pth not in target_kws:
                target_kws.append(pth)

        matches = 0
        matched_kws: List[str] = []

        for kw in target_kws:
            clean_kw = kw.strip().lower()
            if not clean_kw:
                continue

            # 1. Exact or substring match in synopsis or candidate keywords
            if clean_kw in cand_text or any(clean_kw in ck for ck in cand_kws_lower):
                matches += 1
                matched_kws.append(clean_kw)
                continue

            # 2. Semantic thematic cluster matching via synonym map
            synonyms = THEMATIC_SYNONYM_MAP.get(clean_kw, [])
            synonym_matched = False
            for syn in synonyms:
                if syn in cand_text or any(syn in ck for ck in cand_kws_lower):
                    matches += 1
                    matched_kws.append(clean_kw)
                    synonym_matched = True
                    break
            if synonym_matched:
                continue

            # 3. Soft Genre-Thematic Synergy (e.g. romance theme supported by Romance genre)
            if clean_kw in ("unrequited love", "romance", "romantic", "love", "dating") and "romance" in cand_genres_lower:
                matches += 1
                matched_kws.append(clean_kw)
            elif clean_kw in ("family drama", "family", "social issues") and "drama" in cand_genres_lower:
                matches += 1
                matched_kws.append(clean_kw)
            elif clean_kw in ("comedy", "humor", "witty", "feel-good") and "comedy" in cand_genres_lower:
                matches += 1
                matched_kws.append(clean_kw)

        # Keyword IDs overlap check
        if intent.keywords_any:
            req_ids = {TMDB_KEYWORD_IDS[k] for k in intent.keywords_any if k in TMDB_KEYWORD_IDS}
            if req_ids and features.keyword_ids:
                id_overlap = req_ids & features.keyword_ids
                if id_overlap:
                    matches += len(id_overlap)

        if target_kws:
            score = min(1.0, 0.40 + 0.60 * (matches / max(1, len(target_kws))))
            if matches == 0:
                # Soft baseline: never eliminate or zero-out candidates for missing obscure keywords
                score = 0.45 if ("romance" in cand_genres_lower or "comedy" in cand_genres_lower) else 0.35
        else:
            score = 0.70  # Neutral baseline if no keywords specified

        reason: Optional[str] = None
        if matched_kws:
            reason = f"Thematic alignment on [{', '.join(matched_kws[:2])}]"

        return min(1.0, max(0.0, score)), reason

    def score_mood_atmosphere(
        self,
        features: CandidateFeatures,
        intent: ParsedRecommendationIntent,
    ) -> Tuple[float, Optional[str]]:
        """Score 4: Mood, emotional resonance, and atmosphere (10%)."""
        if not intent.mood and not intent.moods:
            return 0.75, None  # Neutral baseline

        mood_term = intent.mood or (intent.moods[0] if intent.moods else "")
        mood_data = resolve_mood_semantics(mood_term)
        if not mood_data:
            return 0.70, None

        score = 0.50
        reason: Optional[str] = None

        # Check related genres
        related_genres = mood_data.get("related_genres", [])
        related_gids = {TMDB_MOVIE_GENRES[g] for g in related_genres if g in TMDB_MOVIE_GENRES}
        if related_gids and set(features.genre_ids) & related_gids:
            score += 0.30

        # Check thematic terms in overview
        cand_overview_lower = features.overview.lower()
        related_themes = mood_data.get("related_themes", []) + mood_data.get("aliases", [])
        if any(th in cand_overview_lower for th in related_themes):
            score += 0.20
            reason = f"Captures '{mood_term.replace('_', '-')}' atmosphere"

        if score >= 0.80 and not reason:
            reason = f"Matches {mood_term.replace('_', '-')} mood"

        return min(1.0, max(0.0, score)), reason

    def score_source_signal(self, features: CandidateFeatures) -> Tuple[float, Optional[str]]:
        """Score 5: Similar/recommended discovery source strength (10%)."""
        source = features.retrieval_source or ""
        reason: Optional[str] = None

        if source == "recommendation":
            score = 1.0
            reason = "Collaborative filtering recommendation"
        elif source == "details_similar":
            score = 0.95
            reason = "Direct reference similarity"
        elif source == "similar":
            score = 0.85
            reason = "Metadata similarity match"
        elif source == "keyword_discover":
            score = 0.80
            reason = "Verified keyword match"
        elif source == "genre_discover":
            score = 0.70
        elif source == "page_2_fallback":
            score = 0.60
        elif source == "relaxed_vote_fallback":
            score = 0.50
        else:
            score = 0.70

        return score, reason

    def score_quality_credibility(self, features: CandidateFeatures) -> Tuple[float, Optional[str]]:
        """Score 6: Quality and credibility with Bayesian vote smoothing (5%).
        
        Requirement 4.4:
        - TMDB vote average, vote count, popularity.
        - Popularity is NOT the main ranking factor.
        - Lesser-known but highly relevant titles can outrank mainstream titles.
        - Vote count acts as confidence signal rather than an absolute cutoff.
        """
        # Bayesian rating smoothing: prior mean m=6.0 with prior weight C=30 votes
        # smoothed = (vote_count * vote_average + 30 * 6.0) / (vote_count + 30)
        v_count = max(0, features.vote_count)
        v_avg = max(0.0, min(10.0, features.vote_average))

        smoothed_rating = (v_count * v_avg + 30.0 * 6.0) / (v_count + 30.0)
        norm_quality = smoothed_rating / 10.0

        # Gentle popularity tie-breaker (max +0.05 bonus)
        pop_bonus = min(0.05, math.log1p(features.popularity) * 0.01)
        final_quality = min(1.0, norm_quality + pop_bonus)

        reason: Optional[str] = None
        if features.vote_average >= 7.8 and features.vote_count >= 100:
            reason = f"Critically acclaimed ({features.vote_average:.1f}/10)"

        return round(final_quality, 3), reason

    def score_contextual_preferences(
        self,
        features: CandidateFeatures,
        intent: ParsedRecommendationIntent,
        user_prefs: Optional[MovieUserPreferences] = None,
        user_profile: Optional[UserMovieProfile] = None,
    ) -> Tuple[float, Optional[str]]:
        """Score 7: Underrated status, release era, and personalized taste (5%).
        
        Requirement 8.5:
        - Explicit query instructions take strict priority over learned background preferences.
        - Personalized profile acts as a supportive re-ranking signal.
        - Negative feedback (disliked titles/genres) penalizes candidates.
        - Liked titles and positive genre affinities boost candidates.
        """
        score = 0.50  # Neutral baseline
        reason: Optional[str] = None

        # Determine explicit genres requested in the prompt
        explicit_genres = {
            g.lower() for g in (
                list(intent.genres) + list(intent.genres_any) + list(intent.genres_all)
            ) if g
        }

        # Underrated / Hidden Gem Request (Query level)
        if "underrated" in intent.keywords or "hidden gem" in intent.keywords:
            if features.vote_average >= 7.0 and features.vote_count < 3000:
                score += 0.40
                reason = "Acclaimed hidden gem with high audience reception"
            elif features.vote_count > 15000:
                # Moderate dampener for mainstream mega-blockbusters when underrated was asked
                score -= 0.20

        # User Saved Preferences & Settings Match
        pref_underrated = False
        pref_highly_rated = False
        pref_newer = False
        pref_classic = False

        if user_prefs:
            pref_underrated = getattr(user_prefs, "prefer_underrated", False)
            pref_highly_rated = getattr(user_prefs, "prefer_highly_rated", False)
            pref_newer = getattr(user_prefs, "prefer_newer", False)
            pref_classic = getattr(user_prefs, "prefer_classic", False)

            if user_prefs.preferred_genres and features.genre_names:
                pref_set = {g.lower() for g in user_prefs.preferred_genres}
                if any(gn.lower() in pref_set for gn in features.genre_names):
                    score += 0.15
                    if not reason:
                        reason = "Matches your favorite genres"

            if user_prefs.preferred_languages and features.language in user_prefs.preferred_languages:
                score += 0.15

        if user_profile:
            pref_underrated = pref_underrated or getattr(user_profile, "prefer_underrated", False)
            pref_highly_rated = pref_highly_rated or getattr(user_profile, "prefer_highly_rated", False)
            pref_newer = pref_newer or getattr(user_profile, "prefer_newer", False)
            pref_classic = pref_classic or getattr(user_profile, "prefer_classic", False)

            # Check individual title feedback: Disliked vs Liked
            if features.movie_id in user_profile.disliked_ids:
                score -= 0.45
                reason = "Previously marked as not interested"
            elif features.movie_id in user_profile.liked_ids:
                score += 0.35
                if not reason:
                    reason = "Aligned with titles you liked"

            # Genre affinity & disliked genres (Prompt Intent strictly overrides background taste)
            cand_genres_lower = [gn.lower() for gn in features.genre_names]
            for g_name in cand_genres_lower:
                # If genre is disliked by user BUT explicitly asked for in query, DO NOT PENALIZE!
                if g_name in user_profile.disliked_genres:
                    if g_name not in explicit_genres:
                        score -= 0.30
                        reason = f"Suppressed (in your disliked genres: {g_name})"

                # Learned genre affinity boost
                affinity = user_profile.genre_affinities.get(g_name, 0.0)
                if affinity > 0:
                    boost = min(0.20, affinity * 0.04)
                    score += boost
                    if not reason and boost >= 0.10:
                        reason = f"Matches your taste profile ({g_name.title()})"

        # Optional preference flags (Req 8.2)
        if pref_underrated:
            if features.vote_average >= 7.0 and features.vote_count < 4000:
                score += 0.25
                if not reason:
                    reason = "Curated hidden gem (underrated preference)"
            elif features.vote_count > 15000:
                score -= 0.15

        if pref_highly_rated:
            if features.vote_average >= 7.8 and features.vote_count >= 200:
                score += 0.25
                if not reason:
                    reason = f"Critically acclaimed ({features.vote_average:.1f}/10)"

        if pref_newer:
            if features.release_year and features.release_year >= 2020:
                score += 0.20
                if not reason:
                    reason = f"Recent release ({features.release_year})"

        if pref_classic:
            if features.release_year and features.release_year <= 1990:
                score += 0.25
                if not reason:
                    reason = f"Classic film era ({features.release_year})"

        # Release Era Match from Query
        if intent.release_year and features.release_year == intent.release_year:
            score += 0.30
            if not reason:
                reason = f"Released in {features.release_year}"
        elif intent.release_year_min and features.release_year:
            if intent.release_year_min <= features.release_year <= (intent.release_year_max or 9999):
                score += 0.20

        return min(1.0, max(0.0, score)), reason

    # =========================================================================
    # Candidate Scoring & Hard Filter Evaluation
    # =========================================================================

    def passes_hard_filters(
        self,
        features: CandidateFeatures,
        intent: ParsedRecommendationIntent,
        user_prefs: Optional[MovieUserPreferences] = None,
        user_profile: Optional[UserMovieProfile] = None,
        watched_ids: Optional[Set[int]] = None,
        filter_watched: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Check strict hard filters. Returns (is_valid, rejection_reason)."""
        # 1. Reference movie itself must be excluded
        if intent.reference_media and features.movie_id == intent.reference_media.id:
            return False, "Self-match: reference movie itself"
        if intent.reference_title:
            if features.title.strip().lower() == intent.reference_title.strip().lower():
                return False, f"Self-match: '{features.title}' is the reference movie"

        # 2. Watched filter (explicit setting or preference flag)
        should_exclude_watched = (
            filter_watched
            or (user_prefs and getattr(user_prefs, "exclude_watched", False))
            or (user_profile and getattr(user_profile, "exclude_watched", False))
        )
        if should_exclude_watched and watched_ids and features.movie_id in watched_ids:
            return False, "Already watched by user"

        # 3. Explicit Language Hard Filter (Only enforce when user explicitly requested a specific language)
        is_explicit_lang = (
            getattr(intent, "is_explicit_language", False)
            or bool(getattr(intent, "original_languages", []))
            or (not intent.reference_title and not intent.similar_to_title and bool(intent.language or intent.languages))
        )
        if is_explicit_lang:
            if intent.language and features.language:
                if features.language.lower() != intent.language.lower():
                    return False, f"Language mismatch: expected {intent.language}, got {features.language}"

            if intent.languages and features.language:
                allowed_langs = {l.lower() for l in intent.languages}
                if features.language.lower() not in allowed_langs:
                    return False, f"Language mismatch: expected one of {intent.languages}, got {features.language}"

        # 4. Explicit Country Hard Filter (Enforced when user explicitly requested origin country, e.g. 'Indian movies')
        if getattr(intent, "is_explicit_country", False):
            target_country = (intent.origin_country or "").upper()
            if target_country == "IN" or (intent.countries and "IN" in [c.upper() for c in intent.countries]):
                cand_countries = [c.upper() for c in (features.origin_country or [])]
                cand_lang = (features.language or "").lower()
                is_indian = ("IN" in cand_countries) or (cand_lang in INDIAN_LANGUAGES)
                if not is_indian:
                    return False, f"Country mismatch: expected Indian cinema (IN), got country={cand_countries}, lang={cand_lang}"
            elif target_country in ("US", "GB") or (intent.countries and any(c.upper() in ("US", "GB") for c in intent.countries)):
                cand_countries = [c.upper() for c in (features.origin_country or [])]
                cand_lang = (features.language or "").lower()
                is_western = any(c in {"US", "GB", "CA", "AU"} for c in cand_countries) or (cand_lang == "en")
                if not is_western:
                    return False, f"Country mismatch: expected Western/Hollywood cinema, got country={cand_countries}, lang={cand_lang}"

        # 5. Explicit Excluded Genres Hard Filter (User removed or explicitly excluded genres)
        excluded_genres = list(getattr(intent, "excluded_genres", None) or []) + list(getattr(intent, "excluded_preferences", None) or [])
        if excluded_genres:
            excl_set = {g.strip().lower() for g in excluded_genres if g.strip()}
            cand_genres_lower = {gn.lower() for gn in features.genre_names}
            overlap = excl_set & cand_genres_lower
            if overlap:
                return False, f"Contains user-excluded genre: '{next(iter(overlap))}'"

        # 6. Explicit Release Year Bounds Hard Filter
        if intent.release_year and features.release_year:
            if features.release_year != intent.release_year:
                return False, f"Release year mismatch: expected {intent.release_year}, got {features.release_year}"

        if intent.release_year_min and features.release_year:
            if features.release_year < intent.release_year_min:
                return False, f"Released before minimum year {intent.release_year_min}"

        if intent.release_year_max and features.release_year:
            if features.release_year > intent.release_year_max:
                return False, f"Released after maximum year {intent.release_year_max}"

        # 7. Explicit Exclusions Hard Filter
        if intent.must_exclude:
            title_lower = features.title.lower()
            overview_lower = features.overview.lower()
            for excl in intent.must_exclude:
                excl_clean = excl.strip().lower()
                if excl_clean in title_lower or excl_clean in overview_lower:
                    return False, f"Contains excluded term: '{excl}'"

        return True, None

    def score_candidate(
        self,
        cand: MediaItemSummary,
        intent: ParsedRecommendationIntent,
        user_prefs: Optional[MovieUserPreferences] = None,
        user_profile: Optional[UserMovieProfile] = None,
        semantic_sim: Optional[float] = None,
    ) -> Tuple[float, List[str], CandidateFeatures, Dict[str, float]]:
        """Extract features, evaluate all 7 relevance signals, and compute final score (0.0 to 100.0)."""
        features = extract_candidate_features(cand)
        weights = self.get_normalized_weights()

        reasons: List[str] = []

        # 1. Semantic Plot (Phase 5: includes neural vector similarity when available)
        plot_score, r_plot = self.score_semantic_plot(features, intent, semantic_sim=semantic_sim)
        features.semantic_plot_score = plot_score
        if r_plot:
            reasons.append(r_plot)

        # 2. Genre Relevance
        genre_score, r_genre = self.score_genre_relevance(features, intent)
        features.genre_relevance_score = genre_score
        if r_genre and r_genre not in reasons:
            reasons.append(r_genre)

        # 3. Themes & Keywords
        theme_score, r_theme = self.score_theme_keywords(features, intent)
        features.theme_keywords_score = theme_score
        if r_theme and r_theme not in reasons:
            reasons.append(r_theme)

        # 4. Mood & Atmosphere
        mood_score, r_mood = self.score_mood_atmosphere(features, intent)
        features.mood_atmosphere_score = mood_score
        if r_mood and r_mood not in reasons:
            reasons.append(r_mood)

        # 5. Source Signal
        src_score, r_src = self.score_source_signal(features)
        features.source_signal_score = src_score
        if r_src and r_src not in reasons:
            reasons.append(r_src)

        # 6. Quality & Credibility
        quality_score, r_qual = self.score_quality_credibility(features)
        features.quality_credibility_score = quality_score
        if r_qual and r_qual not in reasons:
            reasons.append(r_qual)

        # 7. Contextual Preferences & Personalized Taste (Phase 8)
        ctx_score, r_ctx = self.score_contextual_preferences(
            features, intent, user_prefs=user_prefs, user_profile=user_profile
        )
        features.contextual_preferences_score = ctx_score
        if r_ctx and r_ctx not in reasons:
            reasons.append(r_ctx)

        # Multi-signal weighted sum
        total = (
            weights["semantic_plot"] * plot_score
            + weights["genre_relevance"] * genre_score
            + weights["theme_keywords"] * theme_score
            + weights["mood_atmosphere"] * mood_score
            + weights["source_signal"] * src_score
            + weights["quality_credibility"] * quality_score
            + weights["contextual_preferences"] * ctx_score
        )

        # Country Compatibility Soft Bonus (Requirement B)
        country_compat_score = 0.0
        if intent.origin_country == "IN" or intent.region == REGION_INDIAN:
            cand_countries = [c.upper() for c in (features.origin_country or [])]
            cand_lang = (features.language or "").lower()
            if "IN" in cand_countries or cand_lang in INDIAN_LANGUAGES:
                country_compat_score = 1.0
                total = min(1.0, total + 0.03)

        # Language Compatibility Soft Bonus (Requirement B)
        lang_compat_score = 0.0
        if getattr(intent, "preferred_languages", None):
            if features.language and features.language.lower() in [pl.lower() for pl in intent.preferred_languages]:
                lang_compat_score = 1.0
                total = min(1.0, total + 0.04)

        final_scaled_score = round(total * 100.0, 1)
        features.total_relevance_score = final_scaled_score

        breakdown = {
            "semantic_plot": round(plot_score * 100.0, 1),
            "genre_relevance": round(genre_score * 100.0, 1),
            "theme_keywords": round(theme_score * 100.0, 1),
            "mood_atmosphere": round(mood_score * 100.0, 1),
            "source_signal": round(src_score * 100.0, 1),
            "quality_credibility": round(quality_score * 100.0, 1),
            "contextual_preferences": round(ctx_score * 100.0, 1),
            "country_compatibility": round(country_compat_score * 100.0, 1),
            "language_compatibility": round(lang_compat_score * 100.0, 1),
        }
        if semantic_sim is not None:
            breakdown["neural_semantic_similarity"] = round(semantic_sim * 100.0, 1)

        return final_scaled_score, reasons[:3], features, breakdown

    # =========================================================================
    # Candidate Reranking with Diversity Controls (Requirement 4.6)
    # =========================================================================

    def rank_candidates(
        self,
        candidates: List[MediaItemSummary],
        intent: ParsedRecommendationIntent,
        user_prefs: Optional[MovieUserPreferences] = None,
        user_profile: Optional[UserMovieProfile] = None,
        watched_ids: Optional[Set[int]] = None,
        limit: int = 6,
        apply_diversity: bool = True,
        franchise_discount: float = 0.65,
        semantic_scores: Optional[Dict[int, float]] = None,
    ) -> List[Tuple[MediaItemSummary, float, List[str], Dict[str, float]]]:
        """Rank candidates using multi-signal relevance scoring and controlled diversity reranking."""
        if not candidates:
            return []

        filter_watched = False
        if user_prefs and user_prefs.recommendation_settings.get("include_watched") is False:
            filter_watched = True

        scored_candidates: List[Tuple[MediaItemSummary, float, List[str], CandidateFeatures, Dict[str, float]]] = []

        for cand in candidates:
            # 4.1 Separate Hard Filters from Soft Preferences (including exclude_watched from profile/prefs)
            passes, _ = self.passes_hard_filters(
                features=extract_candidate_features(cand),
                intent=intent,
                user_prefs=user_prefs,
                user_profile=user_profile,
                watched_ids=watched_ids,
                filter_watched=filter_watched,
            )
            if not passes:
                continue

            cand_sim = semantic_scores.get(cand.id) if (semantic_scores and cand.id) else None
            score, reasons, features, breakdown = self.score_candidate(
                cand, intent, user_prefs=user_prefs, user_profile=user_profile, semantic_sim=cand_sim
            )
            scored_candidates.append((cand, score, reasons, features, breakdown))

        if not scored_candidates:
            return []

        # Initial sort descending by score
        scored_candidates.sort(key=lambda x: (x[1], x[0].vote_average, x[0].popularity), reverse=True)

        # 4.6 Controlled Diversity Reranking
        if not apply_diversity or len(scored_candidates) <= 2:
            return [(cand, score, reasons, breakdown) for cand, score, reasons, _, breakdown in scored_candidates[:limit]]

        selected: List[Tuple[MediaItemSummary, float, List[str], Dict[str, float]]] = []
        pool = list(scored_candidates)
        franchise_counts: Counter = Counter()

        while pool and len(selected) < limit:
            best_idx = 0
            best_eff_score = -1.0

            for idx, (cand, base_score, _, feats, _) in enumerate(pool):
                f_key = feats.franchise_key
                f_count = franchise_counts.get(f_key, 0) if f_key else 0

                # Exponential franchise decay penalty (e.g. 1st sequel gets 0.65, 2nd sequel gets 0.42)
                effective_score = base_score * (franchise_discount ** f_count)

                if effective_score > best_eff_score:
                    best_eff_score = effective_score
                    best_idx = idx

            chosen_cand, chosen_score, chosen_reasons, chosen_feats, chosen_breakdown = pool.pop(best_idx)
            selected.append((chosen_cand, chosen_score, chosen_reasons, chosen_breakdown))

            if chosen_feats.franchise_key:
                franchise_counts[chosen_feats.franchise_key] += 1

        return selected
