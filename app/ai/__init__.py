"""Local Ollama LLM Runtime and AI Integration (Phase 4)."""

from app.ai.ai_service import AIService
from app.ai.cancellation import CancellationToken
from app.ai.conversation_context import ConversationContext
from app.ai.emotion_classifier import EmotionClassifier, EmotionType
from app.ai.generation_controls import GenerationConfig
from app.ai.model_manager import ModelManager
from app.ai.ollama_client import (
    OllamaCancelledError,
    OllamaClient,
    OllamaClientError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)
from app.ai.ollama_supervisor import OllamaSupervisor
from app.ai.personality_manager import PersonalityManager
from app.ai.thinking_filter import StreamingThinkingFilter, ThinkingFilter, strip_thinking_tags

__all__ = [
    "AIService",
    "CancellationToken",
    "ConversationContext",
    "EmotionClassifier",
    "EmotionType",
    "GenerationConfig",
    "ModelManager",
    "OllamaClient",
    "OllamaClientError",
    "OllamaConnectionError",
    "OllamaModelNotFoundError",
    "OllamaTimeoutError",
    "OllamaCancelledError",
    "OllamaSupervisor",
    "PersonalityManager",
    "StreamingThinkingFilter",
    "ThinkingFilter",
    "strip_thinking_tags",
]
