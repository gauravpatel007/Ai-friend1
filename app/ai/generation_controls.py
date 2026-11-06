"""Generation controls and configuration for local LLM inference.

Provides configurable parameters for sampling temperature, token limits,
context windows, and conversational response styles.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Dict, Optional


@dataclass
class GenerationConfig:
    """Configurable generation parameters passed to the local LLM inference engine."""

    model: str = "llama3.2:latest"
    temperature: float = 0.7
    max_tokens: int = 250          # maps to Ollama 'num_predict'
    context_size: int = 2048       # maps to Ollama 'num_ctx'
    top_p: float = 0.9
    top_k: int = 40
    response_style: str = "concise" # "concise", "casual", "detailed"
    keep_alive: str = "5m"         # Ollama model retention window
    adaptive_tokens: bool = True   # dynamically scale num_predict to task complexity
    max_continuations: int = 2     # automatic continuations when hit by 'length' limit

    def to_ollama_options(self) -> Dict[str, Any]:
        """Convert settings to the Ollama options dictionary format."""
        return {
            "temperature": float(self.temperature),
            "num_predict": int(self.max_tokens),
            "num_ctx": int(self.context_size),
            "top_p": float(self.top_p),
            "top_k": int(self.top_k),
        }

    @classmethod
    def for_voice(cls, model: str = "llama3.2:latest") -> GenerationConfig:
        """Optimized preset for voice mode: concise, fast, and conversational."""
        return cls(
            model=model,
            temperature=0.6,
            max_tokens=90,
            context_size=2048,
            top_p=0.9,
            response_style="concise",
            keep_alive="15m",
            adaptive_tokens=True,
            max_continuations=1,
        )

    @classmethod
    def for_chat(cls, model: str = "llama3.2:latest") -> GenerationConfig:
        """Balanced preset for desktop text chat with room for complete answers."""
        return cls(
            model=model,
            temperature=0.7,
            max_tokens=1200,
            context_size=8192,
            top_p=0.9,
            response_style="casual",
            adaptive_tokens=True,
            max_continuations=2,
        )

    @staticmethod
    def estimate_task_token_budget(
        user_prompt: str,
        is_voice: bool = False,
        configured_limit: Optional[int] = None,
        style: Optional[Any] = None,
    ) -> int:
        """Dynamically estimate the required output token budget based on task complexity.
        
        Tasks require distinct token allocations:
        - Quick Answer: Very small (~70 - 120 voice, ~180 text)
        - Normal Conversation: Balanced (~180 - 280 voice, ~1000 text)
        - Detailed Explanation: Large (~450 - 750 voice, ~2800 text)
        - Step-by-Step: Medium-Large (~350 - 600 voice, ~2200 text)
        - Hands-Free Summary: Concise (~120 - 180 voice, ~450 text)
        """
        # If explicit adaptive response style is provided, consult guidelines
        if style is not None:
            from app.ai.adaptive_response_style import AdaptiveStyleGuidelines, ResponseStyle
            resolved_style = ResponseStyle.from_string(str(style))
            budget = AdaptiveStyleGuidelines.get_token_budget(resolved_style, is_voice)
            if configured_limit and configured_limit > budget:
                return configured_limit
            return budget

        cleaned = (user_prompt or "").strip()
        lower = cleaned.lower()

        # Check for adaptive response style cues directly from prompt
        from app.ai.adaptive_response_style import AdaptiveStyleDetector, AdaptiveStyleGuidelines
        detected_style, _, _ = AdaptiveStyleDetector.detect_style(cleaned, is_voice=is_voice)
        base_budget = AdaptiveStyleGuidelines.get_token_budget(detected_style, is_voice)

        # Voice mode prioritized for low latency conversational dialogue matching adaptive style
        if is_voice:
            # If user asks voice companion to write code or extensive list, allow slight expansion
            if any(k in lower for k in ["write code", "program", "tell me all", "complete list"]):
                return max(base_budget, 500)
            return base_budget

        # 1. Greetings & Pleasantries (Very Small)
        if re.match(r"^(hi|hello|hey|howdy|sup|greetings)(\s+(there|friend|bond|buddy|everyone|folks|you))?[\s!.,?]*$", lower):
            return 120
        if re.match(r"^good\s+(morning|afternoon|evening|day)(\s+(there|bond|buddy))?[\s!.,?]*$", lower):
            return 120
        if len(cleaned) < 15 and lower in ("thanks", "thank you", "ok", "okay", "bye", "goodbye"):
            return 80

        # 2. Number Sequences / Counting / Repetitive Listing (e.g. "write 1 to 100", "1 to 500")
        seq_match = re.search(r"(?:numbers?\s+)?(?:from\s+)?(\d+)\s*(?:to|through|-)\s*(\d+)", lower)
        if seq_match:
            try:
                start_n = int(seq_match.group(1))
                end_n = int(seq_match.group(2))
                count = abs(end_n - start_n) + 1
                # Each number + punctuation + whitespace consumes ~3-5 tokens
                needed = count * 6 + 100
                return min(max(needed, 500), 4096)
            except Exception:
                pass

        if "1 to 100" in lower or "1-100" in lower:
            return 750
        if "1 to 500" in lower or "1-500" in lower:
            return 3600

        # 3. Coding Tasks & Complete Programs (Large)
        code_patterns = [
            "python", "javascript", "typescript", "c++", "java", "html", "css", "sql",
            "write a program", "write code", "complete code", "function", "script",
            "implement", "algorithm", "class", "refactor", "bug fix", "regex",
        ]
        if any(p in lower for p in code_patterns):
            return 3072

        # 4. JSON / Structured Data Generation (Large)
        structured_patterns = [
            "json", "yaml", "xml", "csv", "table", "schema", "multiple objects",
            "array of", "list of objects", "structured format",
        ]
        if any(p in lower for p in structured_patterns):
            return max(base_budget, 2500)

        # 5. Detailed Explanations & Comprehensive Analysis (Large)
        detailed_patterns = [
            "in detail", "detailed explanation", "explain in detail", "in depth",
            "in-depth", "comprehensive", "elaborate on", "deep dive", "thoroughly explain",
            "detailed overview", "step by step explanation",
        ]
        if any(p in lower for p in detailed_patterns):
            return max(base_budget, 2800)

        # 6. Document Summarization & Detailed Takeaways (Medium-Large)
        summary_patterns = [
            "summarize this document", "summarize this long", "document summary",
            "summarize the document", "summarize the following", "key takeaways",
            "long document", "executive summary", "comprehensive summary",
        ]
        if any(p in lower for p in summary_patterns):
            return max(base_budget, 2048)

        # If user explicitly configured custom max_tokens (and not the old static 250 default), respect it
        if configured_limit and configured_limit > 250:
            return max(configured_limit, base_budget)

        # Standard Default: Use adaptive style token budget
        return base_budget

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GenerationConfig:
        """Instantiate config from dictionary with safe fallbacks."""
        return cls(
            model=str(data.get("model", "llama3.2:latest")),
            temperature=float(data.get("temperature", 0.7)),
            max_tokens=int(data.get("max_tokens", 250)),
            context_size=int(data.get("context_size", 2048)),
            top_p=float(data.get("top_p", 0.9)),
            top_k=int(data.get("top_k", 40)),
            response_style=str(data.get("response_style", "concise")),
            keep_alive=str(data.get("keep_alive", "5m")),
            adaptive_tokens=bool(data.get("adaptive_tokens", True)),
            max_continuations=int(data.get("max_continuations", 2)),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain dictionary."""
        return asdict(self)


def calculate_context_window(
    prompt_or_doc: str,
    model_context_limit: int = 32768,
    default_ctx: int = 2048,
) -> int:
    """Calculate appropriate num_ctx context capacity dynamically based on input length."""
    char_len = len(prompt_or_doc or "")
    estimated_tokens = char_len // 4
    needed = max(default_ctx, (estimated_tokens + 1500))
    if needed <= 2048:
        target = 2048
    elif needed <= 4096:
        target = 4096
    elif needed <= 8192:
        target = 8192
    elif needed <= 16384:
        target = 16384
    else:
        target = 32768
    return min(target, model_context_limit)
