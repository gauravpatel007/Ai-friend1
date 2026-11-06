"""Centralized Voice Profile Registry for Bond AI Desktop Companion.

Provides a single source of truth for voice identities, TTS engine mappings,
gender metadata, conversational styles, speaking rates, and multilingual fallback rules.
(Phase 1 - 5 Genuinely Distinct Voices)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class VoiceProfile:
    """Immutable descriptor for a Bond voice persona."""

    profile_id: str                      # Unique identifier, e.g. "arjun", "mira"
    name: str                            # User-facing display name, e.g. "Arjun"
    gender: str                          # "male" | "female"
    description: str                     # Personality & tonal characteristics
    primary_engine: str                  # "kokoro", "sapi5", or "piper"
    primary_voice_id: str                # Engine-specific voice ID (e.g. "am_adam")
    supported_languages: List[str]       # ["en", "hi", "gu"]
    speaking_rate: float = 1.0           # Default speed multiplier (e.g. 0.95x, 1.05x)
    pitch: Optional[float] = None        # Semitone offset if supported
    style_parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Engine fallback when primary engine is unavailable or unsuited for a language
    fallback_engine: str = "sapi5"
    fallback_voice_id: str = "Microsoft David Desktop"
    indian_accent_voice_id: Optional[str] = None  # SAPI Indian English voice for Indic pronunciation

    def to_dict(self) -> Dict[str, Any]:
        """Serialize profile to dictionary for UI and API consumers."""
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "gender": self.gender,
            "description": self.description,
            "primary_engine": self.primary_engine,
            "primary_voice_id": self.primary_voice_id,
            "supported_languages": list(self.supported_languages),
            "speaking_rate": self.speaking_rate,
            "pitch": self.pitch,
            "fallback_engine": self.fallback_engine,
            "fallback_voice_id": self.fallback_voice_id,
            "indian_accent_voice_id": self.indian_accent_voice_id,
        }


# ─── Standardized Fair Comparison Sample Sentences ──────────────────────────────
# All 5 voices use the exact same sentence in each language for unbiased comparison.
VOICE_PREVIEW_SAMPLES: Dict[str, str] = {
    "en": "Hello! I am Bond, your personal AI desktop companion. How can I help you today?",
    "hi": "नमस्ते! मैं बॉन्ड हूँ, आपका निजी साथी। आज मैं आपकी कैसे मदद कर सकता हूँ?",
    "gu": "નમસ્તે! હું બોન્ડ છું, તમારો અંગત મિત્ર. આજે હું તમને કેવી રીતે મદદ કરી શકું?",
}


# ─── The 5 Distinct Voice Profiles ──────────────────────────────────────────────
# 2 Male Voices: Arjun, Kabir
# 3 Female Voices: Ananya, Mira, Zara
# Genuinely different acoustic models and speaker weights from Kokoro & Windows SAPI5.

VOICE_REGISTRY: Dict[str, VoiceProfile] = {
    "arjun": VoiceProfile(
        profile_id="arjun",
        name="Arjun",
        gender="male",
        description="Natural, friendly, and confident with a warm conversational tone.",
        primary_engine="kokoro",
        primary_voice_id="am_adam",
        supported_languages=["en", "hi", "gu"],
        speaking_rate=1.0,
        fallback_engine="sapi5",
        fallback_voice_id="Microsoft David Desktop",
        indian_accent_voice_id="Microsoft Ravi - English (India)",
    ),
    "kabir": VoiceProfile(
        profile_id="kabir",
        name="Kabir",
        gender="male",
        description="Calm, mature, and composed with a slightly deeper conversational tone.",
        primary_engine="kokoro",
        primary_voice_id="am_michael",
        supported_languages=["en", "hi", "gu"],
        speaking_rate=0.95,
        fallback_engine="sapi5",
        fallback_voice_id="Microsoft David Desktop",
        indian_accent_voice_id="Microsoft Ravi - English (India)",
    ),
    "ananya": VoiceProfile(
        profile_id="ananya",
        name="Ananya",
        gender="female",
        description="Warm, friendly, and expressive with an engaging companion presence.",
        primary_engine="kokoro",
        primary_voice_id="af_bella",
        supported_languages=["en", "hi", "gu"],
        speaking_rate=1.0,
        fallback_engine="sapi5",
        fallback_voice_id="Microsoft Zira Desktop",
        indian_accent_voice_id="Microsoft Heera - English (India)",
    ),
    "mira": VoiceProfile(
        profile_id="mira",
        name="Mira",
        gender="female",
        description="Calm, soft, and gentle with a soothing, reassuring cadence.",
        primary_engine="kokoro",
        primary_voice_id="af_heart",
        supported_languages=["en", "hi", "gu"],
        speaking_rate=0.95,
        fallback_engine="sapi5",
        fallback_voice_id="Microsoft Zira Desktop",
        indian_accent_voice_id="Microsoft Heera - English (India)",
    ),
    "zara": VoiceProfile(
        profile_id="zara",
        name="Zara",
        gender="female",
        description="Energetic, confident, and lively with a crisp, articulate British style.",
        primary_engine="kokoro",
        primary_voice_id="bf_emma",
        supported_languages=["en", "hi", "gu"],
        speaking_rate=1.05,
        fallback_engine="sapi5",
        fallback_voice_id="Microsoft Zira Desktop",
        indian_accent_voice_id="Microsoft Heera - English (India)",
    ),
}

DEFAULT_VOICE_PROFILE_ID = "arjun"


def get_voice_profile(profile_id: Optional[str]) -> VoiceProfile:
    """Retrieve voice profile by ID with graceful fallback to default (Arjun)."""
    if not profile_id:
        return VOICE_REGISTRY[DEFAULT_VOICE_PROFILE_ID]
    norm_id = profile_id.strip().lower()
    return VOICE_REGISTRY.get(norm_id, VOICE_REGISTRY[DEFAULT_VOICE_PROFILE_ID])


def list_voice_profiles() -> List[VoiceProfile]:
    """Return all 5 registered voice profiles in consistent display order."""
    return [
        VOICE_REGISTRY["arjun"],
        VOICE_REGISTRY["kabir"],
        VOICE_REGISTRY["ananya"],
        VOICE_REGISTRY["mira"],
        VOICE_REGISTRY["zara"],
    ]


def get_preview_sample_text(language: str = "en") -> str:
    """Return the standardized preview sentence for the given language."""
    return VOICE_PREVIEW_SAMPLES.get(language, VOICE_PREVIEW_SAMPLES["en"])
