"""Movie Explanation Engine & Grounded Recommendation Presentation.

Phase 6 implementation:
- Batched LLM explanation generation via Ollama (single prompt for all candidates).
- Strict hallucination safeguards and fact verification filter.
- Deterministic grounded explanation fallback.
- Recommendation presentation grouping (Best Matches, Hidden Gems, More Like Your Request, Alternative Picks).
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.ai.ollama_client import OllamaClient, OllamaClientError
from app.api.movie_models import (
    MediaItemSummary,
    ParsedRecommendationIntent,
    RecommendedTitleModel,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Banned streaming availability phrases (preventing unverified claims)
BANNED_STREAMING_PATTERNS = [
    r"\bavailable\s+on\s+(?:netflix|prime|hulu|disney\+?|hbo|max|apple\s*tv|hotstar|paramount)\b",
    r"\bstreaming\s+now\s+on\b",
    r"\bwatch\s+(?:it\s+)?on\s+(?:netflix|prime|disney|hulu)\b",
]

# Generic boilerplate phrases to reject in favor of grounded facts
GENERIC_BOILERPLATE_PATTERNS = [
    r"this\s+is\s+an\s+amazing\s+movie\s+you\s+will\s+love",
    r"you\s+will\s+definitely\s+enjoy\s+this\s+masterpiece",
    r"an\s+incredible\s+must-watch\s+for\s+everyone",
    r"a\s+great\s+choice\s+for\s+any\s+movie\s+lover",
]


class MovieExplanationEngine:
    """Manages batched LLM explanation generation, strict hallucination filtering,
    and presentation sectioning for movie recommendations.
    """

    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        default_model: str = "llama3.2:3b",
    ) -> None:
        self.ollama_client = ollama_client or OllamaClient()
        self.default_model = default_model

    # =========================================================================
    # 1. Deterministic Grounded Explanation Fallback
    # =========================================================================

    @staticmethod
    def build_deterministic_grounded_explanation(
        cand: MediaItemSummary,
        intent: ParsedRecommendationIntent,
        match_reasons: Optional[List[str]] = None,
    ) -> str:
        """Construct a high-fidelity explanation strictly derived from verified TMDB facts.
        
        Guaranteed to contain zero hallucinations, exact release years, verified genres,
        and real synopsis elements.
        """
        reasons = match_reasons or []
        genre_label = ", ".join(cand.genre_names[:2]) if cand.genre_names else "cinema"
        type_label = "series" if cand.media_type == "tv" else "movie"
        year_str = f" ({cand.release_year})" if cand.release_year else ""
        lang_label = f"{cand.original_language.upper()} " if cand.original_language else ""
        reg_label = f"{intent.region.replace('_', ' ').title()} " if intent.region else ""

        # Rating description
        rating_str = f"rated {cand.vote_average:.1f}/10" if cand.vote_average > 0 else "recently released"

        # Reference movie synergy
        if intent.reference_title:
            base = (
                f"Recommended for fans of '{intent.reference_title}': a standout {reg_label}{lang_label}{genre_label} "
                f"{type_label}{year_str}, {rating_str}."
            )
        else:
            base = (
                f"A standout {reg_label}{lang_label}{genre_label} {type_label}{year_str}, "
                f"{rating_str} matching your request."
            )

        # Incorporate primary match reason if available
        if reasons:
            primary_reason = reasons[0]
            if not primary_reason.endswith("."):
                primary_reason += "."
            return f"{base} {primary_reason}"

        # Otherwise extract first sentence of synopsis
        if cand.overview:
            first_sentence = cand.overview.split(".")[0].strip()
            if len(first_sentence) > 15:
                return f"{base} Follows {first_sentence[0].lower() + first_sentence[1:]}."

        return base

    # =========================================================================
    # 2. Strict Hallucination Verification & Safeguards (Requirement 6.3)
    # =========================================================================

    @staticmethod
    def verify_and_filter_explanation(
        explanation: str,
        cand: MediaItemSummary,
        intent: ParsedRecommendationIntent,
    ) -> Tuple[bool, str]:
        """Verify generated explanation against verified TMDB metadata.
        
        Checks for:
        - Banned unverified streaming claims.
        - Invented release years.
        - Generic empty platitudes.
        
        Returns:
            Tuple of (is_valid: bool, cleaned_or_fallback_explanation: str).
        """
        if not explanation or len(explanation.strip()) < 15:
            return False, ""

        clean_text = explanation.strip().replace('"', '')

        # 1. Check for banned unverified streaming claims
        for pat in BANNED_STREAMING_PATTERNS:
            if re.search(pat, clean_text, flags=re.IGNORECASE):
                logger.warning("Rejected explanation for '%s' due to unverified streaming claim.", cand.title)
                return False, ""

        # 2. Check for generic boilerplate statements
        for pat in GENERIC_BOILERPLATE_PATTERNS:
            if re.search(pat, clean_text, flags=re.IGNORECASE):
                logger.warning("Rejected explanation for '%s' due to generic platitude.", cand.title)
                return False, ""

        # 3. Check for release year hallucination
        # If a 4-digit year is mentioned, it must match candidate's release year or reference title's year
        years_mentioned = re.findall(r"\b(19\d{2}|20\d{2})\b", clean_text)
        cand_year = str(cand.release_year) if cand.release_year else None
        ref_year = str(intent.reference_year) if intent.reference_year else None
        valid_years = {cand_year, ref_year} - {None}

        for ym in years_mentioned:
            if valid_years and ym not in valid_years:
                logger.warning(
                    "Rejected explanation for '%s' due to hallucinated year '%s' (actual: %s).",
                    cand.title,
                    ym,
                    cand_year,
                )
                return False, ""

        return True, clean_text

    # =========================================================================
    # 3. Batched LLM Explanation Generation (Requirement 6.2 & 6.5)
    # =========================================================================

    def generate_explanations(
        self,
        ranked_candidates: List[Tuple[MediaItemSummary, float, List[str], Dict[str, float]]],
        intent: ParsedRecommendationIntent,
        user_query: str,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> List[RecommendedTitleModel]:
        """Generate concise grounded explanations for all candidates in a SINGLE batched LLM call.
        
        Avoids making separate slow model calls for each movie card (Requirement 6.5).
        """
        if is_cancelled and is_cancelled():
            raise RuntimeError("Recommendation cancelled by user")

        if not ranked_candidates:
            return []

        # Prepare fallback results first
        models: List[RecommendedTitleModel] = []
        cand_map: Dict[int, MediaItemSummary] = {}
        reason_map: Dict[int, List[str]] = {}

        for entry in ranked_candidates:
            if len(entry) == 4:
                item, score, reasons, breakdown = entry
            else:
                item, score, reasons = entry[:3]
                breakdown = None
            cand_map[item.id] = item
            reason_map[item.id] = reasons
            fallback_exp = self.build_deterministic_grounded_explanation(item, intent, reasons)
            models.append(
                RecommendedTitleModel(
                    media=item,
                    score=score,
                    match_reasons=reasons,
                    relevance_breakdown=breakdown,
                    ai_explanation=fallback_exp,
                    is_ai_generated=False,
                )
            )

        # Check if Ollama is available for batched inference
        if not self.ollama_client.is_server_reachable():
            logger.debug("Ollama is offline; using deterministic grounded explanations.")
            return models

        # Build single batched prompt for all candidates
        cand_descriptions: List[str] = []
        for idx, entry in enumerate(ranked_candidates, 1):
            item = entry[0]
            reasons = entry[2]
            cand_descriptions.append(
                f"[{idx}] ID: {item.id} | Title: {item.title} ({item.release_year or 'N/A'}) | "
                f"Genres: {', '.join(item.genre_names[:3]) or 'N/A'} | Rating: {item.vote_average:.1f}/10 | "
                f"Key Match Signal: {', '.join(reasons[:2]) or 'High narrative relevance'} | "
                f"Synopsis: {item.overview[:250]}"
            )

        system_instruction = (
            "You are Bond's Movie Hub recommendation companion. Write a concise, grounded explanation "
            "for EACH recommended movie explaining specifically why it matches the user's request.\n"
            "STRICT GROUNDING & ANTI-HALLUCINATION RULES:\n"
            "1. ONLY reference the verified synopsis, genres, and signals provided for each movie.\n"
            "2. DO NOT invent actors, directors, awards, box office numbers, or streaming platforms (e.g. Netflix).\n"
            "3. DO NOT change release years or ratings.\n"
            "4. AVOID generic statements like 'This is an amazing movie you will love.' State the exact narrative connection.\n"
            "5. Return ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "explanations": [\n'
            '    {"id": <movie_id>, "explanation": "<1 or 2 concise sentences>"}\n'
            "  ]\n"
            "}"
        )

        user_prompt = (
            f"User Request: {user_query}\n"
            f"Reference Movie: {intent.reference_title or 'None'}\n"
            f"Interpreted Mood/Theme: {intent.mood or 'None'}, {', '.join(intent.themes) or 'None'}\n\n"
            f"Candidates to explain:\n" + "\n".join(cand_descriptions)
        )

        try:
            if is_cancelled and is_cancelled():
                raise RuntimeError("Recommendation cancelled by user")

            raw_response = self.ollama_client.chat(
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.default_model,
                options={"temperature": 0.3, "num_predict": 450},
                format="json",
                keep_alive="5m",
            )

            if is_cancelled and is_cancelled():
                raise RuntimeError("Recommendation cancelled by user")

            # Parse JSON explanations
            cleaned_json = raw_response.strip()
            # Extract json block if wrapped in markdown
            if "```" in cleaned_json:
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned_json)
                if match:
                    cleaned_json = match.group(1).strip()

            data = json.loads(cleaned_json)
            exp_list = data.get("explanations", [])
            exp_by_id: Dict[int, str] = {
                item.get("id"): item.get("explanation", "").strip()
                for item in exp_list
                if isinstance(item, dict) and "id" in item
            }

            # Verify each generated explanation against hallucination safeguards
            for rec_model in models:
                mid = rec_model.media.id
                if mid in exp_by_id:
                    candidate_exp = exp_by_id[mid]
                    is_valid, validated_text = self.verify_and_filter_explanation(
                        candidate_exp,
                        rec_model.media,
                        intent,
                    )
                    if is_valid and validated_text:
                        rec_model.ai_explanation = validated_text
                        rec_model.is_ai_generated = True

        except Exception as e:
            logger.warning("Batched explanation generation failed, retained grounded fallback: %s", e)

        return models

    # =========================================================================
    # 4. Recommendation Presentation Structuring (Requirement 6.4)
    # =========================================================================

    @staticmethod
    def organize_presentation_sections(
        recommendations: List[RecommendedTitleModel],
        min_candidates: int = 3,
    ) -> Optional[Dict[str, List[RecommendedTitleModel]]]:
        """Organize recommendations into intuitive sections when sufficient candidates exist.
        
        Sections:
        - 'Best Matches': Highest relevance candidates.
        - 'Hidden Gems': Highly rated titles with lower mainstream popularity/vote counts.
        - 'More Like Your Request': Direct thematic & genre continuations.
        - 'Alternative Picks': Stylistic or regional alternatives.
        
        Returns:
            Dict mapping section name -> list of RecommendedTitleModel, or None if < min_candidates.
        """
        if not recommendations or len(recommendations) < min_candidates:
            return None

        sections: Dict[str, List[RecommendedTitleModel]] = {
            "Best Matches": [],
            "Hidden Gems": [],
            "More Like Your Request": [],
            "Alternative Picks": [],
        }

        # Classify each candidate
        for idx, rec in enumerate(recommendations):
            item = rec.media
            score = rec.score
            vote_count = item.vote_count
            vote_avg = item.vote_average

            is_gem = (
                (vote_avg >= 7.2 and 0 < vote_count < 5000)
                or any("hidden gem" in r.lower() or "underrated" in r.lower() for r in (rec.match_reasons or []))
            )

            # 1. Best Matches: Always include #1 top recommendation
            if idx == 0:
                rec.presentation_section = "Best Matches"
                sections["Best Matches"].append(rec)
            # 2. Hidden Gems: Acclaimed title with low vote counts or explicit gem status
            elif is_gem:
                rec.presentation_section = "Hidden Gems"
                sections["Hidden Gems"].append(rec)
            # 3. Best Matches: Subsequent top-scoring matches
            elif score >= 78.0 and len(sections["Best Matches"]) < 3:
                rec.presentation_section = "Best Matches"
                sections["Best Matches"].append(rec)
            # 4. Alternative Picks: Distinct perspective or lower score
            elif score < 60.0 or idx >= len(recommendations) - 1:
                rec.presentation_section = "Alternative Picks"
                sections["Alternative Picks"].append(rec)
            # 5. More Like Your Request: Standard strong matches
            else:
                rec.presentation_section = "More Like Your Request"
                sections["More Like Your Request"].append(rec)

        # Remove empty sections
        clean_sections = {k: v for k, v in sections.items() if v}
        return clean_sections if len(clean_sections) >= 2 else None
