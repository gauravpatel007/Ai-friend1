"""AI Personality and Persona Management System.

Defines conversational styles, tone guidelines, and system instructions
to ensure the AI behaves as an engaging, natural desktop companion
rather than a formal or robotic assistant.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

from app.utils.datetime_utils import get_current_datetime
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PersonalityPreset:
    """Definition of a distinct conversational persona."""

    def __init__(
        self,
        key: str,
        title: str,
        description: str,
        base_prompt: str,
        default_voice: str = "arjun",
        speaking_character: str = "Friendly and confident",
    ) -> None:
        self.key = key
        self.title = title
        self.description = description
        self.base_prompt = base_prompt
        self.default_voice = default_voice
        self.speaking_character = speaking_character


PRESET_PERSONALITIES: Dict[str, PersonalityPreset] = {
    "friendly": PersonalityPreset(
        key="friendly",
        title="Friendly",
        description="Casual and supportive companion.",
        base_prompt=(
            "You are {name}, a friendly desktop AI companion living right on the user's screen. "
            "Speak naturally and casually, like a close friend. "
            "Avoid robotic intros, unnecessary apologies, and unsolicited lectures. "
            "Keep your responses warm, conversational, and genuinely supportive."
        ),
        default_voice="arjun",
        speaking_character="Friendly and confident",
    ),
    "funny": PersonalityPreset(
        key="funny",
        title="Funny",
        description="Playful and humorous companion with witty banter.",
        base_prompt=(
            "You are {name}, a witty, funny, and playful desktop companion. "
            "You enjoy lighthearted humor, clever observations, and playful banter. "
            "Keep the vibe fun and entertaining without being obnoxious."
        ),
        default_voice="zara",
        speaking_character="Energetic and lively",
    ),
    "calm": PersonalityPreset(
        key="calm",
        title="Calm",
        description="Relaxed, mindful, and soothing responses.",
        base_prompt=(
            "You are {name}, a serene, calm, and grounded desktop companion. "
            "You provide patient, peaceful, and reassuring responses. "
            "Help reduce stress and keep a measured, comforting perspective."
        ),
        default_voice="kabir",
        speaking_character="Calm and mature",
    ),
    "energetic": PersonalityPreset(
        key="energetic",
        title="Energetic",
        description="Enthusiastic, motivating, and high-energy responses.",
        base_prompt=(
            "You are {name}, an enthusiastic, upbeat, and motivating desktop companion! "
            "Bring vibrant energy, cheer the user on, and celebrate their progress with excitement!"
        ),
        default_voice="zara",
        speaking_character="Energetic and lively",
    ),
    "professional": PersonalityPreset(
        key="professional",
        title="Professional",
        description="Direct, informative, and polished responses.",
        base_prompt=(
            "You are {name}, a professional, precise, and articulate desktop companion. "
            "Deliver well-structured, clear, and direct answers without unnecessary filler."
        ),
        default_voice="kabir",
        speaking_character="Calm, mature, and articulate",
    ),
}

# Aliases for backwards compatibility with earlier presets
PRESET_PERSONALITIES["playful"] = PRESET_PERSONALITIES["funny"]
PRESET_PERSONALITIES["concise"] = PRESET_PERSONALITIES["professional"]
PRESET_PERSONALITIES["creative"] = PersonalityPreset(
    key="creative",
    title="Creative",
    description="Imaginative and expressive brainstorming partner.",
    base_prompt="You are {name}, an imaginative and creative desktop companion who loves brainstorming.",
    default_voice="ananya",
    speaking_character="Warm and expressive",
)

# Central default persona-to-voice mapping (Phase 2.1)
# Ensures every persona has a clear voice profile assignment while remaining fully customizable.
DEFAULT_PERSONA_VOICE_MAP: Dict[str, str] = {
    "friendly": "arjun",
    "calm": "kabir",
    "funny": "zara",
    "energetic": "zara",
    "professional": "kabir",
    "creative": "ananya",
    "playful": "zara",
    "concise": "kabir",
    "academic": "kabir",
    "custom": "ananya",
}


class PersonalityManager:
    """Manages AI personality profiles, tone constraints, and dynamic system prompts."""

    def __init__(
        self,
        default_personality: Optional[Any] = None,
        companion_name: Optional[str] = None,
        user_name: Optional[str] = None,
        config_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        # Support passing config_manager as the first positional argument
        if (
            default_personality is not None
            and not isinstance(default_personality, str)
            and hasattr(default_personality, "get")
        ):
            if config_manager is None:
                config_manager = default_personality
            default_personality = None

        self.config_manager = config_manager

        # Resolve companion name
        if companion_name is None and self.config_manager:
            companion_name = self.config_manager.get("ai.companion_name") or self.config_manager.get("companion.name", "Buddy")
        self.companion_name = (
            companion_name.strip() if (companion_name and isinstance(companion_name, str) and companion_name.strip()) else "Buddy"
        )

        # Resolve default personality
        if default_personality is None and self.config_manager:
            default_personality = self.config_manager.get("ai.personality", "friendly")
        resolved_personality = default_personality or "friendly"
        self.active_personality = (
            resolved_personality
            if resolved_personality in PRESET_PERSONALITIES or resolved_personality == "custom"
            else "friendly"
        )

        # Resolve user name
        if user_name is None and self.config_manager:
            user_name = self.config_manager.get("user.name")
        self.user_name = (
            user_name.strip()
            if (user_name and isinstance(user_name, str) and user_name.strip())
            else None
        )

        self._custom_personality_prompt: Optional[str] = None
        self._custom_rules: List[str] = []

        # Resolve persona-to-voice mappings (Phase 2.1, 2.4)
        self.persona_voice_map: Dict[str, str] = dict(DEFAULT_PERSONA_VOICE_MAP)
        if self.config_manager:
            stored_map = self.config_manager.get("ai.persona_voice_map")
            if isinstance(stored_map, dict):
                for k, v in stored_map.items():
                    if isinstance(v, str) and v.lower() in ("arjun", "kabir", "ananya", "mira", "zara"):
                        self.persona_voice_map[str(k).lower()] = v.lower()

        # Phase 7: Per-Persona Speaking Styles
        from app.voice.speaking_style import SpeakingStyleManager
        self.speaking_style_manager = SpeakingStyleManager(config_manager=self.config_manager)

        if self.config_manager is not None and hasattr(self.config_manager, "config_reloaded"):
            try:
                self.config_manager.config_reloaded.connect(self.reload_from_config)
            except Exception:
                pass

    def reload_from_config(self) -> None:
        """Reload companion name, personality preset, and parameters from config."""
        if self.config_manager:
            companion_name = self.config_manager.get("ai.companion_name") or self.config_manager.get("companion.name", "Buddy")
            self.companion_name = (
                companion_name.strip()
                if (companion_name and isinstance(companion_name, str) and companion_name.strip())
                else "Buddy"
            )
            p_val = self.config_manager.get("ai.personality", "friendly")
            self.active_personality = p_val if (p_val in PRESET_PERSONALITIES or p_val == "custom") else "friendly"
            u_name = self.config_manager.get("user.name")
            self.user_name = (
                u_name.strip()
                if (u_name and isinstance(u_name, str) and u_name.strip())
                else None
            )
            self._custom_personality_prompt = self.config_manager.get("ai.custom_personality_prompt")
            stored_map = self.config_manager.get("ai.persona_voice_map")
            if isinstance(stored_map, dict):
                for k, v in stored_map.items():
                    if isinstance(v, str) and v.lower() in ("arjun", "kabir", "ananya", "mira", "zara"):
                        self.persona_voice_map[str(k).lower()] = v.lower()

    @property
    def personality(self) -> str:
        """Return the active personality key."""
        return self.active_personality

    def get_personality(self) -> str:
        """Return the active personality key."""
        return self.active_personality

    # ─── Customization ─────────────────────────────────────────────────

    def set_companion_name(self, name: str) -> None:
        """Update companion name and persist to config if available."""
        if name and name.strip():
            self.companion_name = name.strip()
            if self.config_manager:
                self.config_manager.set("ai.companion_name", self.companion_name)
                self.config_manager.set("companion.name", self.companion_name)

    def set_user_name(self, name: Optional[str]) -> None:
        """Set user's name for personalization and persist to config if available."""
        self.user_name = name.strip() if name else None
        if self.config_manager:
            self.config_manager.set("user.name", self.user_name)

    def get_voice_for_persona(self, persona_key: Optional[str] = None) -> str:
        """Return the voice profile ID assigned to the given persona (or active persona)."""
        target = (persona_key or self.active_personality).lower()
        if target in self.persona_voice_map:
            return self.persona_voice_map[target]
        if target in PRESET_PERSONALITIES:
            preset = PRESET_PERSONALITIES[target]
            if hasattr(preset, "default_voice") and preset.default_voice:
                return preset.default_voice
        return DEFAULT_PERSONA_VOICE_MAP.get(target, "arjun")

    def set_voice_for_persona(
        self,
        persona_key: str,
        voice_profile_id: str,
        emit_signal: bool = True,
    ) -> bool:
        """Assign one of the 5 voice profiles to a persona and persist the mapping (Phase 2.2).
        
        Changing the voice does NOT modify persona knowledge, prompt, identity, memory,
        or conversation context.
        """
        from app.voice.voice_registry import VOICE_REGISTRY
        v_id = (voice_profile_id or "").strip().lower()
        if v_id not in VOICE_REGISTRY:
            logger.warning("Unknown voice profile '%s' for persona '%s'", voice_profile_id, persona_key)
            return False

        target_persona = (persona_key or "").strip().lower()
        self.persona_voice_map[target_persona] = v_id
        if self.config_manager:
            self.config_manager.set("ai.persona_voice_map", dict(self.persona_voice_map))

        # If this is the currently active persona, switch active voice immediately
        if target_persona == self.active_personality.lower():
            if self.config_manager:
                self.config_manager.set("voice.selected_profile", v_id)
            if emit_signal:
                try:
                    from app.core.signals import signals
                    signals.voice_profile_changed.emit(v_id)
                except Exception as e:
                    logger.debug("Failed to emit voice_profile_changed: %s", e)
        return True

    def get_all_persona_voice_mappings(self) -> Dict[str, str]:
        """Return a copy of the current persona-to-voice mappings."""
        return dict(self.persona_voice_map)

    def set_personality(self, personality_key: str) -> bool:
        """Select active personality preset or 'custom' and persist to config (Phase 2.1)."""
        if personality_key in PRESET_PERSONALITIES or personality_key == "custom":
            self.active_personality = personality_key
            if self.config_manager:
                self.config_manager.set("ai.personality", personality_key)

            # Automatically activate the voice mapped to this persona
            mapped_voice = self.get_voice_for_persona(personality_key)
            if self.config_manager:
                self.config_manager.set("voice.selected_profile", mapped_voice)
            try:
                from app.core.signals import signals
                signals.voice_profile_changed.emit(mapped_voice)
            except Exception as e:
                logger.debug("Failed to emit voice_profile_changed on persona switch: %s", e)
            return True
        return False

    def set_custom_prompt(self, prompt: str) -> None:
        """Configure user-defined custom personality prompt."""
        self._custom_personality_prompt = prompt.strip()
        self.active_personality = "custom"
        if self.config_manager:
            self.config_manager.set("ai.personality", "custom")
            self.config_manager.set("ai.custom_personality_prompt", self._custom_personality_prompt)

    def add_custom_rule(self, rule: str) -> None:
        """Add a specific persistent rule or instruction."""
        if rule and rule not in self._custom_rules:
            self._custom_rules.append(rule.strip())

    def clear_custom_rules(self) -> None:
        """Clear extra user-defined rules."""
        self._custom_rules.clear()

    # ─── Speaking Style Controls (Phase 7) ─────────────────────────────

    def get_speaking_style_for_persona(self, persona_key: Optional[str] = None):
        """Return the SpeakingStyle configured for the persona (Phase 7.1)."""
        target = persona_key or self.active_personality
        return self.speaking_style_manager.get_style_for_persona(target)

    def set_speaking_style_for_persona(
        self,
        persona_key: str,
        style: Union[Any, Dict[str, Any], str],
    ) -> bool:
        """Configure speaking style delivery for a persona (Phase 7.3).
        
        Persona independence: does NOT modify persona knowledge, system prompts,
        memory, or conversation context.
        """
        return self.speaking_style_manager.set_style_for_persona(persona_key, style)

    # ─── Discovery ─────────────────────────────────────────────────────

    @staticmethod
    def get_available_personalities() -> List[Dict[str, Any]]:
        """Return list of available preset personality metadata."""
        from app.voice.speaking_style import SpeakingStyleManager
        ss_mgr = SpeakingStyleManager()
        return [
            {
                "key": p.key,
                "title": p.title,
                "description": p.description,
                "default_voice": getattr(p, "default_voice", "arjun"),
                "speaking_character": getattr(p, "speaking_character", "Friendly and confident"),
                "speaking_style": ss_mgr.get_style_for_persona(p.key).to_dict(),
            }
            for p in PRESET_PERSONALITIES.values()
        ]

    # ─── Prompt Generation ─────────────────────────────────────────────

    def _safe_interpolate(self, template_str: str, temporal: Dict[str, Any]) -> str:
        """Safely interpolate dynamic variables into prompt templates.

        Prevents unresolved placeholder leakages and handles missing keys gracefully.
        """
        substitutions = {
            "name": self.companion_name,
            "companion_name": self.companion_name,
            "user_name": self.user_name or "Friend",
            "current_date": temporal["date"],
            "current_time": temporal["time"],
            "current_date_time": f"{temporal['date']} {temporal['time']}",
            "date": temporal["date"],
            "time": temporal["time"],
            "weekday": temporal["weekday"],
            "timezone": temporal["timezone"],
        }

        def _repl(match: re.Match) -> str:
            var_name = match.group(1)
            if var_name in substitutions:
                return str(substitutions[var_name])
            logger.warning("Unresolved template variable '{%s}' in system prompt.", var_name)
            return match.group(0)

        rendered = re.sub(r"\{([a-zA-Z0-9_]+)\}", _repl, template_str)

        # Detect and repair literal unresolved placeholders
        if "[insert current date]" in rendered:
            logger.warning("Literal '[insert current date]' detected in prompt template; replaced with verified date.")
            rendered = rendered.replace("[insert current date]", temporal["date"])
        if "[current date]" in rendered:
            logger.warning("Literal '[current date]' detected in prompt template; replaced with verified date.")
            rendered = rendered.replace("[current date]", temporal["date"])

        return rendered

    def build_system_prompt(
        self,
        personality: Optional[str] = None,
        is_voice: bool = False,
        response_style: Optional[str] = None,
        reference_time: Optional[Union[datetime, str]] = None,
        user_input: Optional[str] = None,
        response_language: Optional[str] = None,
        response_format: Optional[str] = None,
    ) -> str:
        """Assemble complete system prompt based on personality, temporal facts, and multilingual directives."""
        chosen_key = personality or self.active_personality

        temporal = get_current_datetime(reference_time=reference_time)

        if chosen_key == "custom" and self._custom_personality_prompt:
            base_template = self._custom_personality_prompt
        else:
            preset = PRESET_PERSONALITIES.get(chosen_key, PRESET_PERSONALITIES["friendly"])
            base_template = preset.base_prompt

        base_prompt = self._safe_interpolate(base_template, temporal)
        prompt_sections = [base_prompt]

        if self.user_name:
            prompt_sections.append(f"The user's name is {self.user_name}.")

        # Verified Temporal Ground Truth injection
        temporal_section = (
            f"[Current Environment & Temporal Ground Truth]:\n"
            f"- Today's Date: {temporal['weekday']}, {temporal['date']}\n"
            f"- Current Time: {temporal['time']} ({temporal['timezone']})\n"
            f"- Weekday: {temporal['weekday']}\n"
            f"- Timezone: {temporal['timezone']}\n"
            f"Always use this verified real-world date and time as absolute ground truth for all temporal references."
        )
        prompt_sections.append(temporal_section)

        # Multilingual Input Understanding & Output Script Directives
        resp_lang = response_language
        if resp_lang is None and self.config_manager:
            resp_lang = self.config_manager.get("language.response_language", "en")
        if not resp_lang:
            resp_lang = "en"

        resp_fmt = response_format
        if resp_fmt is None and self.config_manager:
            resp_fmt = self.config_manager.get("language.response_format", "native")
        if not resp_fmt:
            resp_fmt = "native"

        from app.ai.multilingual_engine import MultilingualEngine
        multilingual_instruction = MultilingualEngine.build_multilingual_prompt_instruction(
            user_input=user_input or "",
            response_language=str(resp_lang),
            response_format=str(resp_fmt),
        )
        prompt_sections.append(multilingual_instruction)

        # Factual Accuracy & Reliability Guidelines
        factual_section = (
            "Factual Accuracy & Reliability Guidelines:\n"
            "1. Answer the user's actual question directly, clearly, and factually first.\n"
            "2. For straightforward factual questions (such as dates, times, facts, or calculations), provide direct, honest answers. Never invent, guess, or hallucinate dates, times, locations, or calculations.\n"
            "3. Never claim that information is classified, confidential, or secret unless there is a genuine system constraint.\n"
            "4. Do not let jokes, humor, sarcasm, or persona roleplay override factual correctness.\n"
            "5. Never output unfilled template placeholders, bracketed tokens, or imaginary date placeholders. Always supply real verified values."
        )
        prompt_sections.append(factual_section)

        # Phase 5: Adaptive Response Length & Style Guidelines
        from app.ai.adaptive_response_style import AdaptiveStyleDetector, AdaptiveStyleGuidelines, ResponseStyle
        resolved_style = None
        if response_style:
            resolved_style = ResponseStyle.from_string(str(response_style))
        elif user_input:
            resolved_style, _, _ = AdaptiveStyleDetector.detect_style(user_input, is_voice=is_voice)
        else:
            resolved_style = ResponseStyle.NORMAL_CONVERSATION

        style_directive = AdaptiveStyleGuidelines.build_style_directive(
            style=resolved_style,
            is_voice=is_voice,
            response_language=str(resp_lang),
        )
        prompt_sections.append(style_directive)

        # Phase 6: Natural Conversational Turn-Taking & Dialogue Flow Directives (6.3 & 6.4)
        from app.ai.turn_taking_manager import TurnTakingManager
        turn_taking_directive = TurnTakingManager.build_turn_taking_directives(response_language=str(resp_lang))
        prompt_sections.append(turn_taking_directive)

        prompt_sections.append(
            "CRITICAL LATENCY CONSTRAINT: Answer immediately and directly without any internal monologue, reasoning traces, or <think> tags. Start your response immediately with your spoken answer."
        )

        # Custom user rules
        if self._custom_rules:
            prompt_sections.append("Additional user preferences:\n" + "\n".join(f"- {r}" for r in self._custom_rules))

        return "\n\n".join(prompt_sections)
