"""Intelligent Automatic Model Router (Phase 4).

Deterministically analyzes user prompts, conversation context, attachments, and hardware constraints
to select the optimal local AI model for each request.

Features:
- 12 distinct task classification categories considering multi-turn context and file attachments
- Safe resource-aware selection respecting available RAM/VRAM budgets with automatic fallback
- Anti-thrashing affinity mechanism preventing unnecessary model switching on follow-up messages
- Objective benchmark-driven candidate scoring
- Clean UI badge formatting ('Fast Model — Simple Conversation', 'Coding Model — Programming Task')
- Transparent routing explanations and research limitation notices
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple

import psutil

from app.ai.model_capability_registry import (
    ModelCapability,
    ModelCapabilityRegistry,
    ModelProfile,
    get_model_capability_registry,
)
from app.ai.model_benchmark_service import (
    BenchmarkRepository,
    get_current_gpu_vram_mb,
    get_current_system_ram_mb,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TaskCategory(str, Enum):
    """Supported task detection categories."""

    GREETING = "greeting"
    SIMPLE_VOICE_COMMAND = "simple_voice_command"
    QUICK_FACTUAL_QUESTION = "quick_factual_question"
    GENERAL_CONVERSATION = "general_conversation"
    COMPLEX_REASONING = "complex_reasoning"
    CODING = "coding"
    DEBUGGING = "debugging"
    DOCUMENT_SUMMARIZATION = "document_summarization"
    LONG_FORM_GENERATION = "long_form_generation"
    IMAGE_UNDERSTANDING = "image_understanding"
    STRUCTURED_DATA_EXTRACTION = "structured_data_extraction"
    RESEARCH_ORIENTED_ANALYSIS = "research_oriented_analysis"


# Human-friendly UI badge mappings
TASK_UI_BADGES: Dict[TaskCategory, str] = {
    TaskCategory.GREETING: "Fast Model — Simple Greeting",
    TaskCategory.SIMPLE_VOICE_COMMAND: "Fast Model — Voice Command",
    TaskCategory.QUICK_FACTUAL_QUESTION: "Fast Model — Quick Fact",
    TaskCategory.GENERAL_CONVERSATION: "Balanced Model — Conversation",
    TaskCategory.COMPLEX_REASONING: "Reasoning Model — Complex Analysis",
    TaskCategory.CODING: "Coding Model — Programming Task",
    TaskCategory.DEBUGGING: "Coding Model — Bug Diagnosis",
    TaskCategory.DOCUMENT_SUMMARIZATION: "Long-Context Model — Document Summary",
    TaskCategory.LONG_FORM_GENERATION: "Balanced Model — Long-Form Content",
    TaskCategory.IMAGE_UNDERSTANDING: "Vision Model — Image Analysis",
    TaskCategory.STRUCTURED_DATA_EXTRACTION: "Structured Model — JSON Extraction",
    TaskCategory.RESEARCH_ORIENTED_ANALYSIS: "Reasoning Model — In-Depth Research",
}

# Task to required and preferred capabilities mapping
TASK_CAPABILITY_REQUIREMENTS: Dict[TaskCategory, Tuple[List[ModelCapability], List[ModelCapability]]] = {
    # (Mandatory capabilities, Preferred capabilities)
    TaskCategory.GREETING: (
        [],
        [ModelCapability.FAST_RESPONSE, ModelCapability.GENERAL_CONVERSATION],
    ),
    TaskCategory.SIMPLE_VOICE_COMMAND: (
        [],
        [ModelCapability.FAST_RESPONSE, ModelCapability.GENERAL_CONVERSATION],
    ),
    TaskCategory.QUICK_FACTUAL_QUESTION: (
        [],
        [ModelCapability.FAST_RESPONSE, ModelCapability.GENERAL_CONVERSATION],
    ),
    TaskCategory.GENERAL_CONVERSATION: (
        [ModelCapability.GENERAL_CONVERSATION],
        [ModelCapability.FAST_RESPONSE],
    ),
    TaskCategory.COMPLEX_REASONING: (
        [ModelCapability.REASONING],
        [ModelCapability.LONG_CONTEXT],
    ),
    TaskCategory.CODING: (
        [ModelCapability.CODING],
        [ModelCapability.REASONING, ModelCapability.STRUCTURED_OUTPUT],
    ),
    TaskCategory.DEBUGGING: (
        [ModelCapability.CODING],
        [ModelCapability.REASONING],
    ),
    TaskCategory.DOCUMENT_SUMMARIZATION: (
        [ModelCapability.SUMMARIZATION],
        [ModelCapability.LONG_CONTEXT],
    ),
    TaskCategory.LONG_FORM_GENERATION: (
        [ModelCapability.LONG_CONTEXT],
        [ModelCapability.GENERAL_CONVERSATION],
    ),
    TaskCategory.IMAGE_UNDERSTANDING: (
        [ModelCapability.VISION],
        [ModelCapability.GENERAL_CONVERSATION],
    ),
    TaskCategory.STRUCTURED_DATA_EXTRACTION: (
        [ModelCapability.STRUCTURED_OUTPUT],
        [ModelCapability.LONG_CONTEXT],
    ),
    TaskCategory.RESEARCH_ORIENTED_ANALYSIS: (
        [ModelCapability.REASONING],
        [ModelCapability.LONG_CONTEXT, ModelCapability.SUMMARIZATION],
    ),
}


@dataclass
class RoutingDecision:
    """Detailed record of a model routing evaluation."""

    detected_task: TaskCategory
    selected_model: str
    previous_model: str
    switched: bool
    reason: str
    fallback_used: bool
    ui_badge: str
    required_capabilities: List[ModelCapability]
    resource_metrics: Dict[str, Any]
    research_limitation_noted: bool = False
    material_change_note: Optional[str] = None
    model_unavailable: bool = False
    fallback_notification: Optional[str] = None

    def __getitem__(self, item: str) -> Any:
        """Allow dict-style indexing for backwards compatibility."""
        return getattr(self, item)

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary."""
        return {
            "detected_task": self.detected_task.value,
            "selected_model": self.selected_model,
            "previous_model": self.previous_model,
            "switched": self.switched,
            "reason": self.reason,
            "fallback_used": self.fallback_used,
            "ui_badge": self.ui_badge,
            "required_capabilities": [c.value for c in self.required_capabilities],
            "resource_metrics": self.resource_metrics,
            "research_limitation_noted": self.research_limitation_noted,
            "material_change_note": self.material_change_note,
            "model_unavailable": self.model_unavailable,
            "fallback_notification": self.fallback_notification,
        }


# ─── Task Classification Engine ────────────────────────────────────────────────


class TaskDetector:
    """Classifies user requests using message structure, multi-turn context, and attachments."""

    @staticmethod
    def detect_task(
        prompt: str,
        context_history: Optional[List[Dict[str, str]]] = None,
        images: Optional[List[Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        is_voice: bool = False,
        format_json: bool = False,
    ) -> Tuple[TaskCategory, Dict[str, Any]]:
        """Classify request into one of the 12 task categories.

        Evaluates syntax patterns, context continuity, file types, and multi-word semantic cues
        rather than isolated single keywords.
        """
        raw_text = (prompt or "").strip()
        lower = raw_text.lower()
        metadata: Dict[str, Any] = {"input_length": len(raw_text)}

        # 1. Image & Video Visual Understanding (Phase 7)
        has_images = bool(images and len(images) > 0)
        has_visual_attachments = False
        has_spreadsheet = False
        has_document = False
        if attachments:
            for att in attachments:
                name = str(att.get("name") or att.get("file_name") or "").lower()
                mtype = str(att.get("type") or att.get("mime_type") or "").lower()
                cat = str(att.get("category", "")).lower()
                if (
                    any(name.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".mp4", ".mov"])
                    or "image/" in mtype
                    or "video/" in mtype
                    or cat in ("image", "video")
                ):
                    has_visual_attachments = True
                if any(name.endswith(ext) for ext in [".csv", ".xlsx"]) or cat == "spreadsheet":
                    has_spreadsheet = True
                if any(name.endswith(ext) for ext in [".pdf", ".docx", ".txt", ".md"]) or cat == "document":
                    has_document = True

        if has_images or has_visual_attachments:
            metadata["evidence"] = "Attached image or visual video media present."
            return TaskCategory.IMAGE_UNDERSTANDING, metadata

        # 2. Structured Data Extraction
        is_structured_request = format_json or bool(re.search(
            r"\b(?:return|output|generate|extract|format|respond)\s+(?:the\s+output\s+)?(?:strictly\s+)?(?:only\s+)?(?:in\s+)?(?:as\s+)?(?:valid\s+)?json\b|\bjson\s+(?:format|object|array|schema)\b",
            lower,
        ))
        if is_structured_request:
            metadata["evidence"] = "Explicit JSON structured output request."
            return TaskCategory.STRUCTURED_DATA_EXTRACTION, metadata

        # 3. Debugging (Tracebacks, Stack Traces, Error Messages)
        error_indicators = [
            "traceback (most recent call last)",
            "syntaxerror:",
            "typeerror:",
            "valueerror:",
            "indexerror:",
            "keyerror:",
            "attributeerror:",
            "nullpointerexception",
            "runtimeerror:",
            "fix this bug",
            "why is my code giving",
            "debug this error",
            "why am i getting this error",
            "fix the error in this",
        ]
        if any(err in lower for err in error_indicators) or ("error:" in lower and ("line " in lower or "file " in lower)):
            metadata["evidence"] = "Traceback error log or bug diagnostic request."
            return TaskCategory.DEBUGGING, metadata

        # 4. Coding & Programming Tasks
        # Multi-word regex and syntax blocks (e.g. ```, def, function, class)
        has_code_block = bool(re.search(r"```(?:python|javascript|ts|js|cpp|java|csharp|go|rust|html|css|sql)?\s*[\s\S]+?```", raw_text))
        has_syntax_defs = bool(re.search(r"\b(def\s+[a-zA-Z_]\w*|function\s+[a-zA-Z_]\w*|class\s+[a-zA-Z_]\w*|import\s+[a-zA-Z_]|from\s+[a-zA-Z_]\w*\s+import)\b", raw_text))
        has_coding_intent = bool(re.search(
            r"\b(write\s+(?:a\s+)?(?:python|javascript|typescript|c\+\+|java|rust|go|sql|bash|html)?\s*(?:script|code|function|program|algorithm|api|endpoint|regex))\b|"
            r"\b(can\s+you\s+(?:explain|refactor|optimize)\s+this\s+(?:python|javascript|typescript|c\+\+|java)?\s*code)\b|"
            r"\b(implement\s+(?:an?\s+)?(?:[a-zA-Z0-9_-]+\s+)*(?:binary|linked|sorting|stack|queue|rest|crud|jwt|auth|lru|cache|tree|graph|algorithm|class|function|method))\b|"
            r"\b(how\s+to\s+(?:code|program|implement)\s+[a-zA-Z0-9_\s]+in\s+(?:python|javascript|typescript|c\+\+|java|rust|go))\b",
            lower,
        ))

        # Check multi-turn conversation context for coding follow-up
        is_coding_followup = False
        if context_history and len(context_history) >= 2:
            last_assistant_msg = context_history[-1].get("content", "").lower()
            last_user_msg = context_history[-2].get("content", "").lower()
            was_prior_turn_code = "```" in last_assistant_msg or "def " in last_assistant_msg or "function" in last_assistant_msg
            if was_prior_turn_code and re.search(r"\b(now\s+add|make\s+it|write\s+tests|convert\s+to|what\s+about|add\s+error|refactor\s+that)\b", lower):
                is_coding_followup = True

        if has_code_block or has_syntax_defs or has_coding_intent or is_coding_followup:
            metadata["evidence"] = "Programming code constructs, explicit coding intent, or coding follow-up."
            return TaskCategory.CODING, metadata

        # 5a. Tabular Spreadsheet & Multi-Attachment Comparative Analysis (Phase 7)
        is_multi_file_comp = bool(attachments and len(attachments) > 1 and any(w in lower for w in ("compare", "findings", "analyze", "trend", "calculate", "highest", "revenue", "sales", "difference", "cross-reference", "correlation")))
        if has_spreadsheet or is_multi_file_comp:
            metadata["evidence"] = "Tabular dataset analysis or multi-file comparative reasoning."
            return TaskCategory.COMPLEX_REASONING, metadata

        # 5b. Document Summarization
        # Long text (> 350 words) accompanied by summary requests or attached document
        word_count = len(raw_text.split())
        summary_request = bool(re.search(
            r"\b(summarize\b|summary\b|key\s+takeaways|key\s+points|bullet\s+points|tldr)\b",
            lower,
        ))
        if (summary_request or has_document) and (word_count > 120 or (attachments and len(attachments) > 0)):
            metadata["evidence"] = "Document summarization query with substantial content or attached document."
            return TaskCategory.DOCUMENT_SUMMARIZATION, metadata

        # 6. Complex Analytical & Step-by-Step Reasoning
        reasoning_patterns = [
            r"\b(which\s+is\s+(?:larger|bigger|smaller|greater)\b.*\b(?:9\.11|9\.9|decimal))\b",
            r"\b(think\s+step\s+by\s+step|step-by-step\s+reasoning|logical\s+deduction)\b",
            r"\b(solve\s+this\s+(?:riddle|logic\s+puzzle|math\s+problem))\b",
            r"\b(if\s+all\s+[a-zA-Z]+\s+are\s+[a-zA-Z]+\s+and\s+all\s+[a-zA-Z]+)\b",
            r"\b(prove\s+that|proof\s+by\s+induction|mathematical\s+proof)\b",
            r"\b(calculate\s+the\s+probability\s+of|expected\s+value)\b",
        ]
        if any(re.search(p, lower) for p in reasoning_patterns):
            metadata["evidence"] = "Analytical, logical puzzle, or step-by-step mathematical reasoning."
            return TaskCategory.COMPLEX_REASONING, metadata

        # 7. Research-Oriented Analysis
        research_patterns = [
            r"\b(?:provide\s+(?:an?\s+)?)?(?:in-depth|comparative|thorough|detailed|systematic)\s+(?:analysis|comparison|study|investigation|evaluation|literature\s+review)\b",
            r"\b(research\s+(?:the\s+)?(?:advancements|history|implications|architecture))\b",
            r"\b(literature\s+review|state-of-the-art\s+developments)\b",
            r"\b(comprehensive\s+(?:analysis|comparison)\s+(?:between|of))\b",
        ]
        if any(re.search(p, lower) for p in research_patterns):
            metadata["evidence"] = "In-depth academic or comparative research query."
            return TaskCategory.RESEARCH_ORIENTED_ANALYSIS, metadata

        # 8. Long-Form Generation
        longform_patterns = [
            r"\b(write|generate|compose|draft)\s+(?:a|an)\s+(?:detailed|long|comprehensive|full|in-depth)?\s*(?:essay|guide|article|novel|story|report|paper|documentation)\b",
            r"\b(create|develop)\s+a\s+complete\s+(?:business\s+plan|curriculum|syllabus|strategy)\b",
            r"\b(write|generate)\s+(?:at\s+least\s+)?\d+\s+words?\s+on\b",
        ]
        if any(re.search(p, lower) for p in longform_patterns):
            metadata["evidence"] = "Long-form essay, comprehensive guide, or extensive generative content."
            return TaskCategory.LONG_FORM_GENERATION, metadata

        # 9. Simple Voice Command
        voice_commands = [
            "mute", "unmute", "stop speaking", "shut up", "be quiet", "stop talking",
            "what time is it", "what's the time", "what date is today", "what is today's date",
            "go to sleep", "sleep mode", "wake up", "open settings", "system status",
        ]
        is_voice_cmd = is_voice and (
            lower in voice_commands
            or any(lower == cmd for cmd in voice_commands)
            or bool(re.search(r"\b(pause|resume|turn\s+(?:up|down)|set\s+volume|volume\s+(?:up|down)|mute|unmute|stop\s+(?:speaking|talking))\b", lower))
        )
        if is_voice_cmd:
            metadata["evidence"] = "Direct voice control or immediate system command."
            return TaskCategory.SIMPLE_VOICE_COMMAND, metadata

        # 10. Greeting & Pleasantry
        # Handle "Hello Bond!", "Good morning, how are you?", "Hi there!", "Hey Bond Good morning"
        greeting_starters = r"^(hi|hello|hey|howdy|sup|greetings|good\s+(?:morning|afternoon|evening|day|night))\b"
        is_greeting_start = bool(re.match(greeting_starters, lower))
        if is_greeting_start:
            rest = re.sub(greeting_starters, "", lower).strip(" ,!.-?")
            pleasantry_phrases = [
                "", "there", "friend", "bond", "buddy", "everyone", "you", "assistant",
                "good morning", "good afternoon", "good evening",
                "how are you", "how are you doing", "how's it going", "how are things",
                "how do you do", "what's up", "whats up", "nice to meet you",
            ]
            if not rest or any(rest.startswith(p) for p in pleasantry_phrases) or word_count <= 6:
                if not any(k in lower for k in ["code", "write", "debug", "error", "traceback", "summarize", "why", "what is", "how to"]):
                    metadata["evidence"] = "Brief greeting, acknowledgement, or polite conversational opening."
                    return TaskCategory.GREETING, metadata
                elif any(p in rest for p in ["how are you", "how's it going", "how are you doing"]):
                    metadata["evidence"] = "Brief greeting with polite check-in."
                    return TaskCategory.GREETING, metadata

        is_politeness = bool(re.match(r"^(thanks|thank\s+you|bye|goodbye|see\s+ya|catch\s+you\s+later)[\s!.,?]*$", lower))
        if is_politeness:
            metadata["evidence"] = "Brief acknowledgement or polite conversational closing."
            return TaskCategory.GREETING, metadata

        # 11. Quick Factual Question & System Factual Inquiries
        factual_starters = [
            "what is the capital of",
            "who was the first",
            "how tall is",
            "how far is",
            "what year did",
            "who wrote",
            "who directed",
            "what is the speed of",
            "what is the atomic number of",
            "what time is it",
            "what is the time",
            "what date is it",
            "what day is it",
            "what is today's date",
            "what's the time",
        ]
        if word_count <= 14 and any(fs in lower for fs in factual_starters):
            metadata["evidence"] = "Concise single-turn factual question or time inquiry."
            return TaskCategory.QUICK_FACTUAL_QUESTION, metadata

        # 12. General Conversation (Default Companion Chit-Chat)
        metadata["evidence"] = "General everyday conversational turn."
        return TaskCategory.GENERAL_CONVERSATION, metadata


# ─── Model Routing & Selection Engine ──────────────────────────────────────────


class ModelRouter:
    """Intelligent, resource-aware automatic model selector."""

    def __init__(
        self,
        registry: Optional[ModelCapabilityRegistry] = None,
        repository: Optional[BenchmarkRepository] = None,
    ) -> None:
        self.registry = registry or get_model_capability_registry()
        self.repository = repository or BenchmarkRepository()
        self._last_decision: Optional[RoutingDecision] = None

    def route_request(
        self,
        prompt: str,
        current_active_model: str,
        context_history: Optional[List[Dict[str, str]]] = None,
        images: Optional[List[Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        is_voice: bool = False,
        format_json: bool = False,
        auto_routing_enabled: bool = True,
        max_allowed_ram_mb: Optional[int] = None,
        model_selection_mode: str = "auto",
        response_priority: str = "balanced",
        task_preferences: Optional[Dict[str, str]] = None,
        failed_models: Optional[List[str]] = None,
    ) -> RoutingDecision:
        """Evaluate incoming user request and select the optimal installed model.

        Selection Priority:
        1. User selection mode (Manual vs Automatic).
        2. Task-specific user preferences and response priority.
        3. Required capability compatibility (e.g. Vision for images, Reasoning for logic).
        4. Failure tracking (excluding failed models during automatic fallback).
        5. Context capacity compatibility.
        6. Available system resources (VRAM and RAM headroom).
        7. Task-specific benchmark performance.
        8. Anti-thrashing active model affinity.
        """
        # Step 1: Detect Task Category
        task_category, meta = TaskDetector.detect_task(
            prompt=prompt,
            context_history=context_history,
            images=images,
            attachments=attachments,
            is_voice=is_voice,
            format_json=format_json,
        )

        ui_badge = TASK_UI_BADGES.get(task_category, "Balanced Model — Conversation")
        mandatory_caps, preferred_caps = TASK_CAPABILITY_REQUIREMENTS.get(task_category, ([], []))

        # Check for real-time web research limitation
        research_limited = False
        lower_prompt = prompt.lower()
        if any(k in lower_prompt for k in [
            "today", "right now", "latest news", "stock price", "current weather", "real-time", "live score", "breaking news"
        ]):
            research_limited = True

        # Fetch system resource headroom
        free_ram_mb = get_current_system_ram_mb()
        avail_ram_mb = psutil.virtual_memory().available / (1024 * 1024)
        gpu_vram_mb = get_current_gpu_vram_mb()
        resource_metrics = {
            "available_system_ram_mb": round(avail_ram_mb, 1),
            "free_system_ram_mb": round(avail_ram_mb, 1),
            "used_gpu_vram_mb": round(gpu_vram_mb, 1),
        }

        # Step 2: Query candidate installed models from Registry
        installed_profiles = self.registry.get_installed_models(local_only=True)
        if not installed_profiles:
            installed_profiles = self.registry.get_installed_models(local_only=False)

        # Check Manual Model Selection Mode
        is_manual = (model_selection_mode.lower() == "manual") or (not auto_routing_enabled)
        if is_manual:
            is_available = any(p.model_id == current_active_model for p in installed_profiles)
            if not auto_routing_enabled:
                reason = (
                    f"Auto-routing disabled: pinned model '{current_active_model}' retained."
                    if is_available
                    else f"Pinned model '{current_active_model}' is currently unavailable in Ollama."
                )
            else:
                reason = (
                    f"Manual mode: user selected model '{current_active_model}' respected."
                    if is_available
                    else f"Manual model '{current_active_model}' is currently unavailable in Ollama."
                )
            decision = RoutingDecision(
                detected_task=task_category,
                selected_model=current_active_model,
                previous_model=current_active_model,
                switched=False,
                reason=reason,
                fallback_used=not is_available,
                ui_badge=f"Manual Model — {current_active_model}" if is_available else f"Model Unavailable — {current_active_model}",
                required_capabilities=mandatory_caps,
                resource_metrics=resource_metrics,
                research_limitation_noted=research_limited,
                model_unavailable=not is_available,
                fallback_notification=(
                    f"⚠️ Selected model '{current_active_model}' is unavailable in Ollama. Please select an installed model in Settings."
                    if not is_available
                    else None
                ),
            )
            self._last_decision = decision
            return decision

        if not installed_profiles:
            decision = RoutingDecision(
                detected_task=task_category,
                selected_model=current_active_model,
                previous_model=current_active_model,
                switched=False,
                reason="No models registered in capability registry. Retained active model.",
                fallback_used=True,
                ui_badge=ui_badge,
                required_capabilities=mandatory_caps,
                resource_metrics=resource_metrics,
                research_limitation_noted=research_limited,
            )
            self._last_decision = decision
            return decision

        failed_set = set(failed_models or [])

        # Check if safe resource fallback is needed
        needs_resource_fallback = False
        if max_allowed_ram_mb and mandatory_caps:
            has_fitting_capable = any(
                all(prof.has_capability(c) for c in mandatory_caps)
                and prof.estimated_vram_mb <= max_allowed_ram_mb
                and prof.model_id not in failed_set
                for prof in installed_profiles
            )
            if not has_fitting_capable:
                needs_resource_fallback = True

        # Resolve user task preference key
        TASK_PREF_MAP = {
            TaskCategory.GREETING: "general_conversation",
            TaskCategory.SIMPLE_VOICE_COMMAND: "general_conversation",
            TaskCategory.QUICK_FACTUAL_QUESTION: "general_conversation",
            TaskCategory.GENERAL_CONVERSATION: "general_conversation",
            TaskCategory.COMPLEX_REASONING: "complex_reasoning",
            TaskCategory.RESEARCH_ORIENTED_ANALYSIS: "complex_reasoning",
            TaskCategory.CODING: "coding",
            TaskCategory.DEBUGGING: "coding",
            TaskCategory.DOCUMENT_SUMMARIZATION: "document_summarization",
            TaskCategory.LONG_FORM_GENERATION: "document_summarization",
            TaskCategory.IMAGE_UNDERSTANDING: "vision",
            TaskCategory.STRUCTURED_DATA_EXTRACTION: "coding",
        }
        pref_key = TASK_PREF_MAP.get(task_category, "general_conversation")
        user_pref_model = (task_preferences or {}).get(pref_key)
        has_user_pref = bool(user_pref_model and user_pref_model != "auto")

        priority_norm = (response_priority or "balanced").lower().strip()

        # Step 3: Score candidates deterministically
        candidate_scores: List[Tuple[float, ModelProfile, str, bool]] = []
        prompt_tokens_est = len(prompt) // 4
        if context_history:
            prompt_tokens_est += sum(len(m.get("content", "")) // 4 for m in context_history)

        for prof in installed_profiles:
            score = 0.0
            reasons = []
            is_fallback = False

            # Exclude failed models if other viable candidates exist
            if prof.model_id in failed_set:
                if len(installed_profiles) > len(failed_set):
                    continue
                else:
                    score -= 500.0
                    reasons.append(f"Previously failed model ({prof.model_id})")
                    is_fallback = True

            # 1. Mandatory capability check
            missing_mandatory = [c for c in mandatory_caps if not prof.has_capability(c)]
            if missing_mandatory:
                if needs_resource_fallback or bool(failed_set):
                    score -= 40.0
                    reasons.append(f"Missing mandatory capabilities ({[c.value for c in missing_mandatory]})")
                    is_fallback = True
                else:
                    continue

            # 2. Context capacity check
            if prompt_tokens_est > prof.context_capacity:
                continue

            # 3. Memory budget check
            mem_needed = prof.estimated_vram_mb
            if max_allowed_ram_mb and mem_needed > max_allowed_ram_mb:
                score -= 150.0
                reasons.append(f"Exceeds memory ceiling ({mem_needed}MB > {max_allowed_ram_mb}MB)")
                is_fallback = True
            elif avail_ram_mb < 2048 and mem_needed > 5000:
                score -= 30.0
                reasons.append("Under severe system memory pressure")
                is_fallback = True

            # 4. User task-specific model preference boost
            if has_user_pref and prof.model_id == user_pref_model:
                score += 85.0
                reasons.append(f"+85 user preferred model for {pref_key}")

            # 5. Preferred Capability matches
            for p_cap in preferred_caps:
                if prof.has_capability(p_cap):
                    score += 20.0
                    reasons.append(f"+20 {p_cap.value}")

            # 6. Response Priority Modifiers (Phase 5)
            if priority_norm == "fastest":
                if prof.has_capability(ModelCapability.FAST_RESPONSE):
                    score += 45.0
                    reasons.append("+45 fastest priority response")
                if prof.size_bytes < 3.5 * (1024 ** 3):
                    score += 30.0
                    reasons.append("+30 compact footprint for fastest priority")
                elif prof.size_bytes > 5.0 * (1024 ** 3):
                    score -= 30.0
                    reasons.append("-30 heavy model penalty for fastest priority")

            elif priority_norm == "quality":
                if prof.benchmark_scores and "warm_performance" in prof.benchmark_scores:
                    wp = prof.benchmark_scores["warm_performance"]
                    q_score = wp.get("avg_quality_score", 0.0)
                    score += q_score * 35.0
                    reasons.append(f"+{q_score * 35.0:.1f} benchmark quality priority")
                if prof.size_bytes >= 4.0 * (1024 ** 3):
                    score += 30.0
                    reasons.append("+30 parameter capacity for quality priority")
                if prof.has_capability(ModelCapability.REASONING):
                    score += 25.0
                    reasons.append("+25 reasoning depth for quality priority")

            # 7. Task-specific specialization boosts
            if task_category in [TaskCategory.GREETING, TaskCategory.SIMPLE_VOICE_COMMAND, TaskCategory.QUICK_FACTUAL_QUESTION]:
                if prof.has_capability(ModelCapability.FAST_RESPONSE):
                    score += 35.0
                    reasons.append("+35 fast response")
                if prof.size_bytes > 3.8 * (1024 ** 3) and priority_norm != "quality":
                    score -= 15.0

            elif task_category in [TaskCategory.CODING, TaskCategory.DEBUGGING]:
                if prof.has_capability(ModelCapability.CODING):
                    score += 40.0
                    reasons.append("+40 coding specialization")
                if prof.has_capability(ModelCapability.REASONING):
                    score += 20.0
                    reasons.append("+20 reasoning support")

            elif task_category == TaskCategory.COMPLEX_REASONING:
                if prof.has_capability(ModelCapability.REASONING):
                    score += 50.0
                    reasons.append("+50 chain-of-thought reasoning")

            elif task_category == TaskCategory.IMAGE_UNDERSTANDING:
                if prof.has_capability(ModelCapability.VISION):
                    score += 60.0
                    reasons.append("+60 multimodal visual encoder")

            elif task_category == TaskCategory.DOCUMENT_SUMMARIZATION:
                if prof.has_capability(ModelCapability.SUMMARIZATION):
                    score += 30.0
                if prof.context_capacity >= 32768:
                    score += 25.0
                    reasons.append("+25 large context window")

            # 8. Benchmark performance bonus (standard warm performance)
            if priority_norm != "quality" and prof.benchmark_scores and "warm_performance" in prof.benchmark_scores:
                wp = prof.benchmark_scores["warm_performance"]
                q_score = wp.get("avg_quality_score", 0.0)
                score += q_score * 15.0

            # 9. Anti-Thrashing Active Model Affinity
            if prof.model_id == current_active_model and not is_fallback and prof.model_id not in failed_set:
                score += 15.0
                reasons.append("+15 active model affinity")

            candidate_scores.append((score, prof, ", ".join(reasons), is_fallback))

        # If no candidates met requirements
        if not candidate_scores:
            fallback_model = current_active_model
            if installed_profiles:
                fallback_model = installed_profiles[0].model_id
            decision = RoutingDecision(
                detected_task=task_category,
                selected_model=fallback_model,
                previous_model=current_active_model,
                switched=(fallback_model != current_active_model),
                reason=f"No installed model met mandatory capabilities ({[c.value for c in mandatory_caps]}). Fallback to '{fallback_model}'.",
                fallback_used=True,
                ui_badge=ui_badge,
                required_capabilities=mandatory_caps,
                resource_metrics=resource_metrics,
                research_limitation_noted=research_limited,
            )
            self._last_decision = decision
            return decision

        candidate_scores.sort(key=lambda item: item[0], reverse=True)
        best_score, best_prof, best_reasons, best_is_fallback = candidate_scores[0]
        selected_model_id = best_prof.model_id
        switched = (selected_model_id != current_active_model)

        # Detect Material Capability Changes on Fallback
        material_change_note = None
        fallback_notification = None
        if best_is_fallback or bool(failed_set):
            if task_category == TaskCategory.IMAGE_UNDERSTANDING and not best_prof.has_capability(ModelCapability.VISION):
                material_change_note = "Selected fallback model lacks native vision capabilities. Image inputs cannot be directly analyzed."
                fallback_notification = "⚠️ Vision model unavailable. Using conversational fallback model without direct image understanding."
            elif task_category in (TaskCategory.COMPLEX_REASONING, TaskCategory.RESEARCH_ORIENTED_ANALYSIS) and not best_prof.has_capability(ModelCapability.REASONING):
                material_change_note = "Selected fallback model lacks deep chain-of-thought reasoning capabilities."
                fallback_notification = "⚠️ Reasoning model unavailable. Using conversational fallback model."
            elif task_category in (TaskCategory.CODING, TaskCategory.DEBUGGING) and not best_prof.has_capability(ModelCapability.CODING):
                material_change_note = "Selected fallback model lacks specialized programming synthesis."
                fallback_notification = "⚠️ Coding model unavailable. Using conversational fallback model."
            elif failed_set:
                fallback_notification = f"⚠️ Switched to alternative model '{selected_model_id}' after primary model failed."

        if fallback_notification:
            ui_badge = f"Fallback Model — {selected_model_id}"

        explanation = (
            f"Detected task '{task_category.value}'. Selected '{selected_model_id}' "
            f"(Score: {best_score:.1f}; {best_reasons}). "
            f"{'Model switched from ' + current_active_model + '.' if switched else 'Active model retained.'}"
        )
        if material_change_note:
            explanation += f" Note: {material_change_note}"

        decision = RoutingDecision(
            detected_task=task_category,
            selected_model=selected_model_id,
            previous_model=current_active_model,
            switched=switched,
            reason=explanation,
            fallback_used=best_is_fallback or bool(failed_set),
            ui_badge=ui_badge,
            required_capabilities=mandatory_caps,
            resource_metrics=resource_metrics,
            research_limitation_noted=research_limited,
            material_change_note=material_change_note,
            model_unavailable=False,
            fallback_notification=fallback_notification,
        )

        self._last_decision = decision
        logger.info("[MODEL ROUTER] %s", explanation)
        return decision

    def get_compatible_models_by_task(self) -> Dict[str, List[str]]:
        """Return compatible installed models for each user-configurable task."""
        installed = self.registry.get_installed_models()
        res: Dict[str, List[str]] = {
            "general_conversation": [],
            "complex_reasoning": [],
            "coding": [],
            "document_summarization": [],
            "vision": [],
        }
        for prof in installed:
            m_id = prof.model_id
            if prof.has_capability(ModelCapability.GENERAL_CONVERSATION) or prof.has_capability(ModelCapability.FAST_RESPONSE):
                res["general_conversation"].append(m_id)
            if prof.has_capability(ModelCapability.REASONING):
                res["complex_reasoning"].append(m_id)
            if prof.has_capability(ModelCapability.CODING):
                res["coding"].append(m_id)
            if prof.has_capability(ModelCapability.SUMMARIZATION) or prof.context_capacity >= 16384:
                res["document_summarization"].append(m_id)
            if prof.has_capability(ModelCapability.VISION):
                res["vision"].append(m_id)
        return res

    def get_last_decision(self) -> Optional[RoutingDecision]:
        """Fetch the most recent routing decision."""
        return self._last_decision

    def get_router_status(self) -> Dict[str, Any]:
        """Return operational summary of the router and installed candidate pool."""
        installed = self.registry.get_installed_models()
        return {
            "registered_models_count": len(installed),
            "installed_models": [p.model_id for p in installed],
            "supported_categories": [c.value for c in TaskCategory],
            "has_vision_model": any(p.has_capability(ModelCapability.VISION) for p in installed),
            "has_reasoning_model": any(p.has_capability(ModelCapability.REASONING) for p in installed),
            "has_coding_model": any(p.has_capability(ModelCapability.CODING) for p in installed),
            "last_decision": self._last_decision.to_dict() if self._last_decision else None,
        }


# Global ModelRouter singleton
_GLOBAL_ROUTER: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Return the global ModelRouter singleton."""
    global _GLOBAL_ROUTER
    if _GLOBAL_ROUTER is None:
        _GLOBAL_ROUTER = ModelRouter()
    return _GLOBAL_ROUTER
