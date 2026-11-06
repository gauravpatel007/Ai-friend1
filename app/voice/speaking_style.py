"""Per-Persona Speaking Style Architecture (Phase 7).

Provides independent, configurable speaking style delivery profiles for Bond AI companions:
- 7.1 Speaking style configuration: speaking rate, pitch, expressiveness, energy,
  pause duration, sentence delivery, and conversational style.
- 7.2 Voice style presets:
    * Arjun: Friendly, confident, natural pace, warm delivery.
    * Kabir: Calm, mature, measured speaking pace, composed delivery.
    * Ananya: Warm, expressive, friendly, natural conversational pace.
    * Mira: Gentle, calm, softer delivery, relaxed pace.
    * Zara: Energetic, confident, expressive, lively delivery.
- 7.3 Persona independence: Decoupled from persona knowledge, system prompts,
  and base audio models; independently customizable and persistent.
- 7.4 Natural speech: Guardrails preventing robotic delivery, unnatural pitch shifts,
  excessive pauses, or volume inconsistencies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Dict, List, Optional, Union

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─── Natural Speech Guardrail Boundaries (Section 7.4) ───────────────────────
MIN_SPEAKING_RATE = 0.75
MAX_SPEAKING_RATE = 1.35

MIN_PITCH_SEMITONES = -2.0
MAX_PITCH_SEMITONES = 2.0

MIN_EXPRESSIVENESS = 0.0
MAX_EXPRESSIVENESS = 1.0

MIN_ENERGY = 0.1
MAX_ENERGY = 1.0

MIN_PAUSE_MS = 60
MAX_PAUSE_MS = 260


@dataclass
class SpeakingStyle:
    """Configurable voice delivery parameters reflecting persona character."""

    style_id: str                     # Unique style identifier (e.g. "arjun", "calm")
    name: str                         # User-facing style name
    speaking_rate: float = 1.00       # Delivery tempo multiplier (0.75 to 1.35)
    pitch: float = 0.0                # Semitone offset (-2.0 to +2.0 semitones)
    expressiveness: float = 0.65      # Expressive inflection (0.0 to 1.0)
    energy: float = 0.60              # Acoustic energy / delivery gain (0.1 to 1.0)
    pause_duration_ms: int = 120      # Inter-sentence pause duration (60ms to 260ms)
    sentence_delivery: str = "Warm delivery"
    conversational_style: str = "Friendly and confident"

    def __post_init__(self) -> None:
        """Clamp parameters within natural human speech guardrails (Section 7.4)."""
        self.speaking_rate = round(max(MIN_SPEAKING_RATE, min(MAX_SPEAKING_RATE, float(self.speaking_rate))), 3)
        self.pitch = round(max(MIN_PITCH_SEMITONES, min(MAX_PITCH_SEMITONES, float(self.pitch))), 2)
        self.expressiveness = round(max(MIN_EXPRESSIVENESS, min(MAX_EXPRESSIVENESS, float(self.expressiveness))), 2)
        self.energy = round(max(MIN_ENERGY, min(MAX_ENERGY, float(self.energy))), 2)
        self.pause_duration_ms = int(max(MIN_PAUSE_MS, min(MAX_PAUSE_MS, int(self.pause_duration_ms))))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize speaking style to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpeakingStyle":
        """Instantiate SpeakingStyle from dictionary with fallback defaults."""
        return cls(
            style_id=str(data.get("style_id", "arjun")),
            name=str(data.get("name", "Arjun")),
            speaking_rate=float(data.get("speaking_rate", 1.0)),
            pitch=float(data.get("pitch", 0.0)),
            expressiveness=float(data.get("expressiveness", 0.65)),
            energy=float(data.get("energy", 0.60)),
            pause_duration_ms=int(data.get("pause_duration_ms", 120)),
            sentence_delivery=str(data.get("sentence_delivery", "Warm delivery")),
            conversational_style=str(data.get("conversational_style", "Friendly and confident")),
        )


# ─── Initial Baseline Voice Styles (Section 7.2) ──────────────────────────────
# Configured defaults per voice profile matching the specification
DEFAULT_SPEAKING_STYLES: Dict[str, SpeakingStyle] = {
    "arjun": SpeakingStyle(
        style_id="arjun",
        name="Arjun (Friendly & Confident)",
        speaking_rate=1.00,
        pitch=0.0,
        expressiveness=0.65,
        energy=0.60,
        pause_duration_ms=120,
        sentence_delivery="Warm delivery",
        conversational_style="Friendly and confident",
    ),
    "kabir": SpeakingStyle(
        style_id="kabir",
        name="Kabir (Calm & Mature)",
        speaking_rate=0.92,
        pitch=-0.8,
        expressiveness=0.45,
        energy=0.45,
        pause_duration_ms=180,
        sentence_delivery="Composed delivery",
        conversational_style="Calm and mature",
    ),
    "ananya": SpeakingStyle(
        style_id="ananya",
        name="Ananya (Warm & Expressive)",
        speaking_rate=1.00,
        pitch=0.0,
        expressiveness=0.80,
        energy=0.65,
        pause_duration_ms=110,
        sentence_delivery="Warm and friendly",
        conversational_style="Warm and expressive",
    ),
    "mira": SpeakingStyle(
        style_id="mira",
        name="Mira (Gentle & Soft)",
        speaking_rate=0.93,
        pitch=0.4,
        expressiveness=0.50,
        energy=0.38,
        pause_duration_ms=160,
        sentence_delivery="Softer delivery",
        conversational_style="Gentle and calm",
    ),
    "zara": SpeakingStyle(
        style_id="zara",
        name="Zara (Energetic & Lively)",
        speaking_rate=1.08,
        pitch=0.8,
        expressiveness=0.85,
        energy=0.85,
        pause_duration_ms=85,
        sentence_delivery="Lively delivery",
        conversational_style="Energetic and lively",
    ),
}

# Persona to initial default speaking style mapping
DEFAULT_PERSONA_STYLE_MAP: Dict[str, str] = {
    "friendly": "arjun",
    "calm": "kabir",
    "creative": "ananya",
    "funny": "zara",
    "energetic": "zara",
    "playful": "zara",
    "professional": "kabir",
    "concise": "kabir",
    "academic": "kabir",
    "custom": "arjun",
}


class SpeakingStyleManager:
    """Manages speaking styles, persistence, and per-persona associations."""

    def __init__(self, config_manager: Optional[Any] = None) -> None:
        self.config_manager = config_manager
        self._persona_styles: Dict[str, SpeakingStyle] = {}
        self._load_from_config()

    def _load_from_config(self) -> None:
        """Load configured persona speaking styles or initialize defaults."""
        stored: Optional[Dict[str, Any]] = None
        if self.config_manager:
            stored = self.config_manager.get("voice.persona_speaking_styles")

        self._persona_styles.clear()
        if isinstance(stored, dict):
            for persona, style_data in stored.items():
                try:
                    if isinstance(style_data, dict):
                        self._persona_styles[str(persona).lower()] = SpeakingStyle.from_dict(style_data)
                    elif isinstance(style_data, str) and style_data.lower() in DEFAULT_SPEAKING_STYLES:
                        preset = DEFAULT_SPEAKING_STYLES[style_data.lower()]
                        self._persona_styles[str(persona).lower()] = SpeakingStyle.from_dict(preset.to_dict())
                except Exception as e:
                    logger.debug("Failed to deserialize speaking style for persona '%s': %s", persona, e)

    def get_style_for_persona(self, persona_key: Optional[str] = None) -> SpeakingStyle:
        """Retrieve active SpeakingStyle for the specified persona with graceful fallback."""
        key = (persona_key or "friendly").strip().lower()
        if key in self._persona_styles:
            return self._persona_styles[key]

        # Use default persona-to-style mapping
        style_id = DEFAULT_PERSONA_STYLE_MAP.get(key, "arjun")
        base_style = DEFAULT_SPEAKING_STYLES.get(style_id, DEFAULT_SPEAKING_STYLES["arjun"])
        # Return a copy
        return SpeakingStyle.from_dict(base_style.to_dict())

    def get_style_by_id(self, style_id: str) -> SpeakingStyle:
        """Retrieve one of the 5 baseline speaking styles."""
        sid = (style_id or "arjun").strip().lower()
        base = DEFAULT_SPEAKING_STYLES.get(sid, DEFAULT_SPEAKING_STYLES["arjun"])
        return SpeakingStyle.from_dict(base.to_dict())

    def set_style_for_persona(
        self,
        persona_key: str,
        style: Union[SpeakingStyle, Dict[str, Any], str],
    ) -> bool:
        """Configure and persist a custom speaking style for a persona (Section 7.3).
        
        Persona independence: does NOT modify persona knowledge, system prompts,
        memory, or conversation context.
        """
        pkey = (persona_key or "").strip().lower()
        if not pkey:
            return False

        if isinstance(style, str):
            sid = style.strip().lower()
            if sid not in DEFAULT_SPEAKING_STYLES:
                logger.warning("Unknown speaking style ID: %s", style)
                return False
            resolved = SpeakingStyle.from_dict(DEFAULT_SPEAKING_STYLES[sid].to_dict())
        elif isinstance(style, dict):
            resolved = SpeakingStyle.from_dict(style)
        elif isinstance(style, SpeakingStyle):
            resolved = style
        else:
            return False

        self._persona_styles[pkey] = resolved
        self._persist()
        logger.info("[SPEAKING_STYLE] Configured persona '%s' delivery: rate=%.2f, pitch=%.1f, pause=%dms",
                    pkey, resolved.speaking_rate, resolved.pitch, resolved.pause_duration_ms)
        return True

    def reset_persona_style(self, persona_key: str) -> None:
        """Reset a persona's speaking style to its specification default."""
        pkey = (persona_key or "").strip().lower()
        if pkey in self._persona_styles:
            del self._persona_styles[pkey]
            self._persist()

    def get_all_persona_styles(self) -> Dict[str, Dict[str, Any]]:
        """Return all active persona speaking style configurations."""
        res = {}
        for pkey in DEFAULT_PERSONA_STYLE_MAP:
            res[pkey] = self.get_style_for_persona(pkey).to_dict()
        return res

    def get_all_preset_styles(self) -> List[Dict[str, Any]]:
        """Return the 5 baseline specification presets."""
        return [s.to_dict() for s in DEFAULT_SPEAKING_STYLES.values()]

    def _persist(self) -> None:
        """Save persona styles to configuration if config_manager is available."""
        if self.config_manager:
            payload = {k: v.to_dict() for k, v in self._persona_styles.items()}
            self.config_manager.set("voice.persona_speaking_styles", payload)


# ─── Audio Signal Processing for Speaking Styles (Section 7.4) ────────────────

def apply_speaking_style_dsp(
    samples: np.ndarray,
    sample_rate: int,
    style: SpeakingStyle,
    is_inter_sentence: bool = False,
) -> np.ndarray:
    """Apply pitch coloring, acoustic energy scaling, and inter-sentence pauses.
    
    Ensures natural, artifact-free delivery without robotic modulation or clipping.
    """
    if samples.size == 0 or sample_rate <= 0:
        return samples

    processed = np.array(samples, dtype=np.float32, copy=True)

    # 1. Subtle Pitch Coloring (where pitch offset != 0.0, clamped in [-2.0, +2.0] semitones)
    if abs(style.pitch) >= 0.15:
        # Semitone ratio r = 2^(semitones / 12)
        ratio = 2.0 ** (style.pitch / 12.0)
        # Resample smoothly in time domain to apply pitch shift
        orig_indices = np.arange(len(processed))
        new_indices = np.linspace(0, len(processed) - 1, int(len(processed) / ratio))
        if len(new_indices) > 0:
            resampled = np.interp(new_indices, orig_indices, processed)
            processed = resampled.astype(np.float32)

    # 2. Acoustic Energy / Gain Scaling
    # Energy in [0.1, 1.0]. 0.6 is neutral (1.0x).
    # Higher energy (e.g. Zara 0.85) gives confident acoustic boost (+1.5 dB).
    # Lower energy (e.g. Mira 0.38) gives softer, gentler acoustic profile (-1.8 dB).
    energy_factor = 0.70 + (style.energy * 0.50)  # Maps [0.1, 1.0] to [0.75, 1.20]
    processed = processed * energy_factor

    # Soft tanh saturation to guarantee zero digital clipping (avoiding distortion)
    max_amp = float(np.max(np.abs(processed)))
    if max_amp > 0.95:
        processed = np.tanh(processed * 0.95)

    # 3. Inter-Sentence Pause Insertion
    if is_inter_sentence and style.pause_duration_ms > 0:
        pause_samples_count = int((style.pause_duration_ms / 1000.0) * sample_rate)
        if pause_samples_count > 0:
            pause_silence = np.zeros(pause_samples_count, dtype=np.float32)
            processed = np.concatenate([processed, pause_silence])

    return processed
