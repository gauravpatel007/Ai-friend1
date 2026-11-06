"""Text-Based Emotion Classification and Tone Analysis (Phase 10.8 & 10.9).

Analyzes user utterances for emotional cues (Happy, Excited, Sad, Frustrated, Neutral)
and coordinates dynamic AI tone adaptation and character animation triggers.
"""

from __future__ import annotations

from enum import Enum
import re
from typing import Dict, List, Optional, Tuple


class EmotionType(Enum):
    HAPPY = "happy"
    EXCITED = "excited"
    SAD = "sad"
    FRUSTRATED = "frustrated"
    NEUTRAL = "neutral"


class EmotionClassifier:
    """Classifies user emotional indicators and provides tone adaptation prompts."""

    _LEXICON: Dict[EmotionType, List[str]] = {
        EmotionType.EXCITED: [
            r"\byay\b",
            r"\bawesome\b",
            r"\bcan\'?t wait\b",
            r"\blet\'?s go\b",
            r"\bincredible\b",
            r"\bamazing\b",
            r"\bthrilled\b",
            r"\bwhoo+hoo+\b",
            r"\bomg\b",
            r"\bso cool\b",
            r"!{2,}",  # Multiple exclamation marks
        ],
        EmotionType.HAPPY: [
            r"\bhappy\b",
            r"\bgreat\b",
            r"\bnice\b",
            r"\bglad\b",
            r"\bwonderful\b",
            r"\bthank you so much\b",
            r"\blove this\b",
            r"\bgood day\b",
            r"\bpleased\b",
            r":\)|:D|😊|🎉",
        ],
        EmotionType.SAD: [
            r"\bsad\b",
            r"\bunhappy\b",
            r"\bdepressed\b",
            r"\bheartbroken\b",
            r"\bdown in the dumps\b",
            r"\bfeeling down\b",
            r"\bcrying\b",
            r"\blonely\b",
            r"\bbummed\b",
            r":\(|😢|😞",
        ],
        EmotionType.FRUSTRATED: [
            r"\bfrustrated\b",
            r"\bannoyed\b",
            r"\bangry\b",
            r"\bstuck\b",
            r"\bdoesn\'?t work\b",
            r"\bbroken\b",
            r"\bhate this\b",
            r"\bargh+\b",
            r"\bwhy is this failing\b",
            r"\bso annoying\b",
            r"\bugh\b",
            r"😠|😡",
        ],
    }

    @classmethod
    def classify(cls, text: str) -> Tuple[EmotionType, float]:
        """Classify emotional state of text utterance.
        
        Returns:
            Tuple of (EmotionType, confidence_score: float)
        """
        cleaned = text.strip().lower()
        if not cleaned:
            return EmotionType.NEUTRAL, 0.0

        scores: Dict[EmotionType, int] = {
            EmotionType.EXCITED: 0,
            EmotionType.HAPPY: 0,
            EmotionType.SAD: 0,
            EmotionType.FRUSTRATED: 0,
        }

        for emotion, patterns in cls._LEXICON.items():
            for pat in patterns:
                matches = len(re.findall(pat, cleaned, re.IGNORECASE))
                if matches > 0:
                    scores[emotion] += matches

        # Exclamation density boost for excitement
        if "!" in text and scores[EmotionType.EXCITED] > 0:
            scores[EmotionType.EXCITED] += 1

        best_emotion = max(scores, key=lambda k: scores[k])
        max_score = scores[best_emotion]

        if max_score == 0:
            return EmotionType.NEUTRAL, 0.50

        # Calculate normalized confidence
        confidence = min(0.98, 0.60 + (max_score * 0.15))
        return best_emotion, float(confidence)

    @classmethod
    def get_tone_instruction(cls, emotion: EmotionType | str) -> str:
        """Return system prompt tone guidance corresponding to detected emotion."""
        if isinstance(emotion, str):
            try:
                emotion = EmotionType(emotion.lower().strip())
            except ValueError:
                emotion = EmotionType.NEUTRAL

        if emotion == EmotionType.EXCITED:
            return "Emotional context: The user is excited! Match their positive enthusiasm with celebratory, energetic replies."
        elif emotion == EmotionType.HAPPY:
            return "Emotional context: The user is in a happy mood. Respond with cheerful warmth and positivity."
        elif emotion == EmotionType.SAD:
            return "Emotional context: The user seems sad or down. Be gentle, comforting, patient, and empathetic."
        elif emotion == EmotionType.FRUSTRATED:
            return "Emotional context: The user is experiencing frustration. Be patient, reassuring, calm, and directly helpful."

        return ""
