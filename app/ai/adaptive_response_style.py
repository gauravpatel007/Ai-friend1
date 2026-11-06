"""Adaptive Response Length and Style Engine (Phase 5).

Provides dynamic detection of user intent for response length and structure,
supporting five distinct conversational modes across English, Gujarati, and Hindi:
1. QUICK_ANSWER: Direct, 1-2 sentences, zero filler.
2. NORMAL_CONVERSATION: Conversational, engaging, balanced depth.
3. DETAILED_EXPLANATION: Comprehensive deep-dive with examples and logical sections.
4. STEP_BY_STEP: Sequential, actionable, procedural walkthrough.
5. HANDS_FREE_SUMMARY: Executive bullet-point takeaway for on-the-go/driving.

Includes direct user overrides ("Keep it short", "Explain more", "Give me an example",
"Continue", "Summarize it") with multilingual comprehension and voice-specific formatting rules.
"""

from __future__ import annotations

from enum import Enum
import re
import unicodedata
from typing import Any, Optional, Tuple


class ResponseStyle(str, Enum):
    """The five adaptive response styles supported by Bond."""

    QUICK_ANSWER = "quick_answer"
    NORMAL_CONVERSATION = "normal_conversation"
    DETAILED_EXPLANATION = "detailed_explanation"
    STEP_BY_STEP = "step_by_step"
    HANDS_FREE_SUMMARY = "hands_free_summary"

    @classmethod
    def from_string(cls, val: Any) -> "ResponseStyle":
        """Convert string or enum to ResponseStyle with graceful fallback."""
        if isinstance(val, cls):
            return val
        if hasattr(val, "value"):
            val = val.value
        if not val:
            return cls.NORMAL_CONVERSATION
        cleaned = str(val).lower().strip().replace("-", "_").replace(" ", "_")
        if "quick" in cleaned or "concise" in cleaned or "brief" in cleaned or "short" in cleaned:
            return cls.QUICK_ANSWER
        if "detailed" in cleaned or "deep_dive" in cleaned or "comprehensive" in cleaned or "in_depth" in cleaned:
            return cls.DETAILED_EXPLANATION
        if "step" in cleaned or "instruction" in cleaned or "tutorial" in cleaned or "guide" in cleaned:
            return cls.STEP_BY_STEP
        if "summary" in cleaned or "hands_free" in cleaned or "tldr" in cleaned or "overview" in cleaned:
            return cls.HANDS_FREE_SUMMARY
        if "normal" in cleaned or "casual" in cleaned or "standard" in cleaned or "default" in cleaned:
            return cls.NORMAL_CONVERSATION
        return cls.NORMAL_CONVERSATION


def _normalize_text(text: str) -> str:
    """Normalize unicode punctuation, strip diacritics, and collapse whitespace."""
    if not text:
        return ""
    chars = []
    for ch in text.lower():
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            chars.append(" ")
        else:
            chars.append(ch)
    return " ".join("".join(chars).split())


class AdaptiveStyleDetector:
    """Detects user desired response style from prompts and direct overrides."""

    # ─────────────────────────────────────────────────────────────────────────
    # DIRECT USER OVERRIDES (Section 5.4)
    # Direct instructions that immediately switch the active response style
    # ─────────────────────────────────────────────────────────────────────────

    # Override -> QUICK_ANSWER
    _OVERRIDE_QUICK_PATTERNS = [
        # English
        re.compile(r"\b(keep it short|make it short|make it brief|be brief|in short|just the answer|short answer|briefly|one line answer|in one sentence|quick answer)\b"),
        # Hindi & Romanized
        re.compile(r"(छोटा बताओ|संक्षेप में बताओ|सीधा जवाब दो|कम शब्दों में बताओ|एक लाइन में|जल्दी बताओ|छोटा उत्तर|बस जवाब दो)"),
        re.compile(r"\b(chhota batao|chota batao|sankshep me|seedha jawab|kam shabdo me|ek line me|jaldi batao|bas jawab do)\b"),
        # Gujarati & Romanized
        re.compile(r"(ટૂંકમાં કહો|ટૂંકમાં જણાવો|ટૂંકો જવાબ|સીધો જવાબ|એક લીટીમાં કહો|સંક્ષિપ્તમાં જણાવો|માત્ર જવાબ આપો)"),
        re.compile(r"\b(tunkma kaho|tunkma janavo|tunko jawab|sidho jawab|ek litima|sankshiptma|matra jawab aapo)\b"),
    ]

    # Override -> DETAILED_EXPLANATION
    _OVERRIDE_DETAILED_PATTERNS = [
        # English
        re.compile(r"\b(explain more|tell me more|give me more details|elaborate|elaborate further|deep dive|explain further|give me an example|show an example|with examples?)\b"),
        # Hindi & Romanized
        re.compile(r"(विस्तार से समझाओ|और बताओ|पूरी जानकारी दो|विस्तार से बताओ|उदाहरण के साथ बताओ|उदाहरण दो|गहराई से समझाओ)"),
        re.compile(r"\b(vistar se samjhao|aur batao|puri jankari|vistar se batao|udaharan ke saath|udaharan do|gahrai se)\b"),
        # Gujarati & Romanized
        re.compile(r"(વધુ સમજાવો|વિસ્તારથી સમજાવો|વિગતવાર જણાવો|ઉદાહરણ સાથે સમજાવો|ઉદાહરણ આપો|દાખલો આપો|ઊંડાણપૂર્વક સમજાવો)"),
        re.compile(r"\b(vadhu samjavo|vistarthi samjavo|vigatvar janavo|udaharan sathe|udaharan aapo|dakhlo aapo|undanpurvak)\b"),
    ]

    # Override -> STEP_BY_STEP
    _OVERRIDE_STEP_BY_STEP_PATTERNS = [
        # English
        re.compile(r"\b(step by step|guide me step by step|walk me through|steps to|instructions? for|how do i do this step by step)\b"),
        # Hindi & Romanized
        re.compile(r"(कदम दर कदम|स्टेप बाय स्टेप|चरणबद्ध तरीके से|चरणबद्ध|एक एक करके बताओ|प्रक्रिया समझाओ)"),
        re.compile(r"\b(kadam dar kadam|step by step|charanbaddh|ek ek karke|prakriya samjhao)\b"),
        # Gujarati & Romanized
        re.compile(r"(પગલાંવાર|સ્ટેપ બાય સ્ટેપ|ક્રમશઃ|એક પછી એક પગલું|રીત સમજાવો|પદ્ધતિ બતાવો)"),
        re.compile(r"\b(paglavar|step by step|kramashah|ek pachi ek|rit samjavo)\b"),
    ]

    # Override -> HANDS_FREE_SUMMARY
    _OVERRIDE_SUMMARY_PATTERNS = [
        # English
        re.compile(r"\b(summarize it|summarize this|give me a summary|hands-?free summary|quick summary|tldr|key takeaways|recap it)\b"),
        # Hindi & Romanized
        re.compile(r"(सारांश दो|सारांश बताओ|मुख्य बातें बताओ|संक्षेप में सारांश|सार बताओ|निचोड़ बताओ)"),
        re.compile(r"\b(saransh do|saransh batao|mukhya baatein|sar batao|nichod batao)\b"),
        # Gujarati & Romanized
        re.compile(r"(સારાંશ આપો|ટૂંકસાર આપો|મુખ્ય મુદ્દાઓ કહો|સારાંશ જણાવો)"),
        re.compile(r"\b(saransh aapo|tunksar aapo|mukhya muddao|saransh janavo)\b"),
    ]

    # Override -> CONTINUATION
    _OVERRIDE_CONTINUE_PATTERNS = [
        # English
        re.compile(r"^(continue|go on|keep going|carry on|next part)\b"),
        # Hindi & Romanized
        re.compile(r"(आगे बताओ|आगे बोलो|जारी रखो|और बोलो)"),
        re.compile(r"\b(aage batao|aage bolo|jaari rakho|aur bolo)\b"),
        # Gujarati & Romanized
        re.compile(r"(આગળ બોલો|ચાલુ રાખો|આગળ કહો|આગળ જણાવો)"),
        re.compile(r"\b(aagad bolo|chalu rakho|aagad kaho|aagad janavo)\b"),
    ]

    # ─────────────────────────────────────────────────────────────────────────
    # GENERAL PROMPT INTENT CUES (Section 5.2)
    # Detects desired style embedded in broader user queries
    # ─────────────────────────────────────────────────────────────────────────

    _INTENT_QUICK_PATTERNS = [
        re.compile(r"^(just\s+tell\s+me\s+the\s+answer|tell\s+me\s+just\s+the\s+answer)\b"),
        re.compile(r"\b(yes\s+or\s+no|true\s+or\s+false|in\s+one\s+word|in\s+a\s+nutshell)\b"),
        re.compile(r"^(what\s+is\s+the\s+(capital|population|height|distance|time|date|currency|symbol))\b"),
        re.compile(r"(માત્ર જવાબ|ફક્ત જવાબ|બસ જવાબ|सिर्फ जवाब|केवल उत्तर)"),
        re.compile(r"\b(matra jawab|sirf jawab|bas jawab)\b"),
    ]

    _INTENT_DETAILED_PATTERNS = [
        re.compile(r"\b(explain\s+(this\s+)?in\s+complete\s+detail(\s+with\s+examples)?)\b"),
        re.compile(r"\b(explain\s+(this\s+)?in\s+detail|detailed\s+explanation|deep\s+dive|comprehensive\s+guide|thoroughly\s+explain)\b"),
        re.compile(r"\b(compare\s+and\s+contrast|in-?depth\s+analysis|with\s+practical\s+examples?)\b"),
        re.compile(r"(વિસ્તારથી સમજાવો|વિગતવાર સમજાવો|ઉદાહરણ સાથે સમજાવો|સંપૂર્ણ વિગતો સાથે)"),
        re.compile(r"(विस्तार से समझाइए|पूरी जानकारी के साथ|उदाहरण सहित|विस्तृत विश्लेषण)"),
        re.compile(r"\b(vistarthi samjavo|vigatvar samjavo|vistar se samjhaiye|puri jankari ke saath)\b"),
    ]

    _INTENT_STEP_BY_STEP_PATTERNS = [
        re.compile(r"\b(step\s+by\s+step|guide\s+me\s+step\s+by\s+step|step\s+by\s+step\s+guide|step\s+by\s+step\s+instructions?)\b"),
        re.compile(r"\b(how\s+do\s+i\s+(install|build|create|cook|setup|make|configure|fix|prepare)\b.*(step\s+by\s+step|steps))\b"),
        re.compile(r"^(how\s+to\s+(install|make|create|setup|cook|fix|prepare))\b"),
        re.compile(r"(પગલાંવાર|સ્ટેપ બાય સ્ટેપ|કેવી રીતે બનાવવું|કેવી રીતે કરવું)"),
        re.compile(r"(कदम दर कदम|स्टेप बाय स्टेप|कैसे बनाएं|कैसे करें)"),
        re.compile(r"\b(paglavar|step by step|kaise kare|kaise banaye)\b"),
    ]

    _INTENT_SUMMARY_PATTERNS = [
        re.compile(r"\b(summarize\s+(this\s+)?while\s+i'?m\s+driving|while\s+driving|hands-?free\s+summary)\b"),
        re.compile(r"\b(give\s+me\s+a\s+quick\s+summary|summarize\s+(this|the)\b|key\s+takeaways?|bullet\s+points?\s+summary)\b"),
        re.compile(r"(ડ્રાઇવિંગ કરતી વખતે સારાંશ|ચલાવતી વખતે સારાંશ|ઝડપી સારાંશ)"),
        re.compile(r"(ड्राइविंग करते हुए सारांश|गाड़ी चलाते समय सारांश|जल्दी में सारांश)"),
        re.compile(r"\b(driving karte hue saransh|driving karti vakhte saransh)\b"),
    ]

    @classmethod
    def check_override(cls, text: str) -> Tuple[bool, Optional[ResponseStyle], str]:
        """Check if user prompt is a direct style override instruction.

        Returns:
            Tuple of (is_override, style, reason).
        """
        norm = _normalize_text(text)
        if not norm:
            return False, None, "empty"

        # Check QUICK_ANSWER overrides
        for pat in cls._OVERRIDE_QUICK_PATTERNS:
            if pat.search(norm) or pat.search(text):
                return True, ResponseStyle.QUICK_ANSWER, "user_override_quick"

        # Check DETAILED_EXPLANATION overrides
        for pat in cls._OVERRIDE_DETAILED_PATTERNS:
            if pat.search(norm) or pat.search(text):
                return True, ResponseStyle.DETAILED_EXPLANATION, "user_override_detailed"

        # Check STEP_BY_STEP overrides
        for pat in cls._OVERRIDE_STEP_BY_STEP_PATTERNS:
            if pat.search(norm) or pat.search(text):
                return True, ResponseStyle.STEP_BY_STEP, "user_override_step_by_step"

        # Check HANDS_FREE_SUMMARY overrides
        for pat in cls._OVERRIDE_SUMMARY_PATTERNS:
            if pat.search(norm) or pat.search(text):
                return True, ResponseStyle.HANDS_FREE_SUMMARY, "user_override_summary"

        # Check CONTINUATION overrides
        for pat in cls._OVERRIDE_CONTINUE_PATTERNS:
            if pat.search(norm) or pat.search(text):
                return True, ResponseStyle.NORMAL_CONVERSATION, "user_override_continue"

        return False, None, "no_override"

    @classmethod
    def detect_style(
        cls,
        user_prompt: str,
        is_voice: bool = False,
        current_style: Optional[ResponseStyle] = None,
    ) -> Tuple[ResponseStyle, bool, str]:
        """Detect the appropriate response style for a user input.

        Args:
            user_prompt: Raw user input text.
            is_voice: Whether the interaction is occurring via hands-free voice.
            current_style: Previously active style if set.

        Returns:
            Tuple of (detected_style, is_override, reason).
        """
        cleaned = (user_prompt or "").strip()
        if not cleaned:
            default_style = ResponseStyle.NORMAL_CONVERSATION
            return default_style, False, "empty_input"

        # 1. Direct User Override check takes highest precedence (Section 5.4)
        is_override, override_style, reason = cls.check_override(cleaned)
        if is_override and override_style:
            return override_style, True, reason

        norm = _normalize_text(cleaned)

        # 2. Check Hands-Free Summary Intent (driving / on-the-go cues)
        for pat in cls._INTENT_SUMMARY_PATTERNS:
            if pat.search(norm) or pat.search(cleaned):
                return ResponseStyle.HANDS_FREE_SUMMARY, False, "intent_summary"

        # 3. Check Detailed Explanation Intent
        for pat in cls._INTENT_DETAILED_PATTERNS:
            if pat.search(norm) or pat.search(cleaned):
                return ResponseStyle.DETAILED_EXPLANATION, False, "intent_detailed"

        # 4. Check Step-by-Step Instructions Intent
        for pat in cls._INTENT_STEP_BY_STEP_PATTERNS:
            if pat.search(norm) or pat.search(cleaned):
                return ResponseStyle.STEP_BY_STEP, False, "intent_step_by_step"

        # 5. Check Quick Answer Intent
        for pat in cls._INTENT_QUICK_PATTERNS:
            if pat.search(norm) or pat.search(cleaned):
                return ResponseStyle.QUICK_ANSWER, False, "intent_quick"

        # 6. Default Fallback Behavior
        # If user is in ongoing session with active override style (e.g. detailed), preserve it
        if current_style and current_style != ResponseStyle.NORMAL_CONVERSATION:
            # But do not carry quick_answer into complex inquiries unless overridden
            if not (current_style == ResponseStyle.QUICK_ANSWER and len(cleaned.split()) > 10):
                return current_style, False, "session_preserved_style"

        # Standard default: Normal Conversation
        return ResponseStyle.NORMAL_CONVERSATION, False, "default_normal"


class AdaptiveStyleGuidelines:
    """Generates prompt directives and token allocations for the five response styles."""

    @staticmethod
    def get_token_budget(style: ResponseStyle, is_voice: bool) -> int:
        """Calculate the estimated output token budget based on style and modality."""
        if is_voice:
            if style == ResponseStyle.QUICK_ANSWER:
                return 110
            elif style == ResponseStyle.HANDS_FREE_SUMMARY:
                return 180
            elif style == ResponseStyle.NORMAL_CONVERSATION:
                return 260
            elif style == ResponseStyle.STEP_BY_STEP:
                return 450
            elif style == ResponseStyle.DETAILED_EXPLANATION:
                return 750
        else:
            if style == ResponseStyle.QUICK_ANSWER:
                return 180
            elif style == ResponseStyle.HANDS_FREE_SUMMARY:
                return 450
            elif style == ResponseStyle.NORMAL_CONVERSATION:
                return 1000
            elif style == ResponseStyle.STEP_BY_STEP:
                return 2200
            elif style == ResponseStyle.DETAILED_EXPLANATION:
                return 2800

        return 260 if is_voice else 1000

    @staticmethod
    def build_style_directive(
        style: ResponseStyle,
        is_voice: bool,
        response_language: str = "en",
    ) -> str:
        """Build precise model instructions for the adaptive response style."""
        directives = []

        # Header
        style_title = style.value.upper().replace("_", " ")
        directives.append(f"[ADAPTIVE RESPONSE STYLE: {style_title}]")

        # Core Style Guidelines
        if style == ResponseStyle.QUICK_ANSWER:
            directives.append(
                "• Mode: Quick Answer.\n"
                "• Output Length: 1 or 2 concise sentences directly answering the user's inquiry.\n"
                "• Omit all conversational preamble, pleasantries, background explanations, or follow-up questions.\n"
                "• Deliver immediately the exact factual answer."
            )
        elif style == ResponseStyle.NORMAL_CONVERSATION:
            if is_voice:
                directives.append(
                    "• Mode: Normal Conversation (Spoken).\n"
                    "• Output Length: 2 to 4 engaging, natural spoken sentences.\n"
                    "• Tone: Warm, friendly, and balanced. Easy to listen to without cognitive overload."
                )
            else:
                directives.append(
                    "• Mode: Normal Conversation (Chat).\n"
                    "• Output Length: 1 to 2 conversational paragraphs.\n"
                    "• Tone: Natural, friendly, helpful, and balanced."
                )
        elif style == ResponseStyle.DETAILED_EXPLANATION:
            if is_voice:
                directives.append(
                    "• Mode: Detailed Explanation (Spoken Hands-Free).\n"
                    "• Organization: Organize into logical conversational sections using clear spoken transitions.\n"
                    "• Spoken Chunking: Keep individual sentences crisp and clear so they synthesize smoothly. "
                    "Pause naturally between major concepts.\n"
                    "• Clarity: Explain underlying concepts thoroughly and include practical examples. "
                    "Keep in mind the user can interrupt at any point."
                )
            else:
                directives.append(
                    "• Mode: Detailed Explanation (Comprehensive).\n"
                    "• Organization: Provide an in-depth, thorough explanation with complete background, "
                    "conceptual breakdown, and real-world examples.\n"
                    "• Structure: Use clear section headers, logical progressions, and thorough analysis."
                )
        elif style == ResponseStyle.STEP_BY_STEP:
            if is_voice:
                directives.append(
                    "• Mode: Step-by-Step Instructions (Spoken Walkthrough).\n"
                    "• Sequencing: Present steps sequentially using spoken transitions: "
                    "'First...', 'Next...', 'Then...', 'Finally...'.\n"
                    "• Simplicity: Keep each step concise and actionable. Do not cram multiple complicated actions into a single step."
                )
            else:
                directives.append(
                    "• Mode: Step-by-Step Instructions (Procedural Guide).\n"
                    "• Sequencing: Provide a clearly numbered list of sequential steps (1, 2, 3...).\n"
                    "• Clarity: For each step, provide actionable instructions and necessary context."
                )
        elif style == ResponseStyle.HANDS_FREE_SUMMARY:
            if is_voice:
                directives.append(
                    "• Mode: Hands-Free Summary (Driving / On-the-Go).\n"
                    "• Brevity: Deliver only the high-level executive takeaway in 2 to 3 crisp, spoken sentences.\n"
                    "• Voice Polish: Use smooth spoken transitions. Do NOT read bullet symbols, numbers, or punctuation aloud.\n"
                    "• Focus: Deliver maximum insight with minimum cognitive distraction."
                )
            else:
                directives.append(
                    "• Mode: Hands-Free Summary (Executive Overview).\n"
                    "• Brevity: Provide a high-level summary highlighting the key core takeaways and essential conclusions."
                )

        # Voice-Specific Output Formatting Constraints (Section 5.3)
        if is_voice:
            directives.append(
                "[CRITICAL VOICE FORMATTING CONSTRAINTS]:\n"
                "1. You are speaking aloud through a text-to-speech synthesizer.\n"
                "2. NEVER use markdown tables (| Column |).\n"
                "3. NEVER use asterisks for bolding or italics (**word** or *word*).\n"
                "4. NEVER output raw web URLs (https://...).\n"
                "5. NEVER read raw code blocks verbatim; describe what the code does in plain words.\n"
                "6. Prefer natural spoken sentences that flow comfortably when read aloud."
            )

        # Language Integrity (Section 5.5)
        lang_name = "English"
        if response_language == "gu":
            lang_name = "Gujarati"
        elif response_language == "hi":
            lang_name = "Hindi"

        directives.append(
            f"[STRICT RESPONSE LANGUAGE RULE]:\n"
            f"Regardless of the selected response style or input language, formulate your entire response "
            f"100% in {lang_name}. Never change response language based on response style."
        )

        return "\n\n".join(directives)
