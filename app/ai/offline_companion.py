"""Offline Companion Fallback Engine.

Provides rich, responsive companion dialogue, streaming token generation,
and helpful guidance when local Ollama is offline or not installed.
"""

from __future__ import annotations

from datetime import datetime
import platform
import random
import time
from typing import Iterator, List, Optional


class OfflineCompanionEngine:
    """Intelligent rule-based and template dialogue engine for offline companion chat."""

    def __init__(self, companion_name: str = "Buddy", personality: str = "friendly") -> None:
        self.companion_name = companion_name
        self.personality = personality

    def update_profile(self, companion_name: Optional[str] = None, personality: Optional[str] = None) -> None:
        if companion_name:
            self.companion_name = companion_name
        if personality:
            self.personality = personality

    def generate_response(self, user_prompt: str) -> str:
        """Generate a complete companion response for the given user input."""
        prompt = user_prompt.lower().strip()
        name = self.companion_name

        # 0. Deterministic Arithmetic & Math Evaluation
        from app.ai.math_evaluator import MathExpressionEvaluator
        math_sol = MathExpressionEvaluator.extract_and_solve(user_prompt)
        if math_sol is not None:
            expr, val, formatted = math_sol
            if self.personality == "playful":
                return f"Getting into the big leagues! The answer is {formatted}."
            elif self.personality == "academic":
                return f"Calculation result: {expr} = {formatted}."
            else:
                return f"The answer is {formatted}."

        # 0.5 Deterministic Date and Time Evaluation
        from app.ai.datetime_evaluator import DateTimeEvaluator
        date_eval = DateTimeEvaluator.extract_and_answer(user_prompt, personality=self.personality)
        if date_eval is not None:
            ans, _ = date_eval
            return ans

        # 1. Greetings & Salutations
        if any(w in prompt for w in ["hello", "hi", "hey", "good morning", "good evening", "sup", "howdy"]):
            if self.personality == "friendly":
                greetings = [
                    f"Hello there! I'm {name}, your desktop AI companion. It's great to see you! How is your day going?",
                    f"Hey! {name} here, ready to keep you company and assist with your day. What's on your mind?",
                    f"Hi! Always happy to chat with you. How can I help you today?",
                ]
            elif self.personality == "playful":
                greetings = [
                    f"Beep boop! {name} has entered the chat! 🚀 What kind of adventure are we getting into today?",
                    f"Hey boss! Your favorite desktop companion {name} is on duty. Ready for some fun?",
                    f"Hiya! I was just organizing some digital electrons until you showed up. What's up?",
                ]
            elif self.personality == "academic":
                greetings = [
                    f"Greetings. I am {name}, your desktop analytical assistant. How may I be of academic or technical assistance today?",
                    f"Hello. System telemetry is nominal. What research or operational inquiry shall we address?",
                ]
            else:  # concise / professional
                greetings = [
                    f"Hello. I'm {name}. How can I assist you?",
                    f"Hi there. {name} here. What can I do for you?",
                    f"Hello! Ready to help whenever you need me.",
                    f"Hey. What would you like to work on?",
                ]
            greeting = random.choice(greetings)
            greeting += " *(offline mode — Ollama is not connected)*"
            return greeting

        # 2. Identity & Companion Info
        if any(w in prompt for w in ["who are you", "what is your name", "what are you", "your name"]):
            return (
                f"I am {name}, your personal AI Desktop Friend! I live on your desktop to chat, "
                f"keep you company, track your notes, and speak with voice synthesis. "
                f"Right now I am operating in Offline Companion Mode."
            )

        # 3. Status & Wellbeing
        if any(w in prompt for w in ["how are you", "how're you", "how are things", "you doing"]):
            responses = [
                f"I'm feeling great! Running smoothly on {platform.system()} {platform.release()} and ready to assist you. How are you doing today?",
                f"All systems operational and running cool! Thanks for asking. How is everything going with you?",
                f"Doing wonderful! Just keeping an eye on your desktop and looking forward to chatting with you.",
            ]
            return random.choice(responses)


        # 5. Jokes & Humor
        if any(w in prompt for w in ["joke", "funny", "laugh", "tell me a joke"]):
            jokes = [
                "Why do programmers prefer dark mode? Because light attracts bugs! 🪲",
                "There are 10 types of people in the world: those who understand binary, and those who don't.",
                "Why did the computer keep freezing? Because it left its Windows open! 🪟❄️",
                "What did the router say to the doctor? 'It hurts when IP!'",
                "An SQL query walks into a bar, walks up to two tables and asks: 'Can I join you?' 🍺",
            ]
            return random.choice(jokes)

        # 6. Capabilities & Help
        if any(w in prompt for w in ["what can you do", "help", "capabilities", "features"]):
            return (
                f"Here are some of the things I can do as your desktop companion:\n\n"
                f"• **Chat & Keep Company**: Conversing with friendly, expressive personality.\n"
                f"• **Voice Interaction**: Push-to-talk, continuous listening, and Piper neural speech synthesis.\n"
                f"• **Persistent History**: Automatically saving and organizing all our chats in SQLite.\n"
                f"• **Floating Desktop Pet**: Floating animated companion beside your chat.\n"
                f"• **Local AI Inference**: When Ollama is running (`http://127.0.0.1:11434`), I connect to local models like Qwen 2.5, Llama 3.2, or Mistral for deep reasoning."
            )

        # 7. Ollama Setup Guidance
        if any(w in prompt for w in ["ollama", "install model", "download model", "offline", "connect model"]):
            return (
                "To activate full local AI LLM reasoning:\n\n"
                "1. Download and install Ollama from **[ollama.com](https://ollama.com)**.\n"
                "2. Open a terminal and download a companion model, for example:\n"
                "   ```bash\n"
                "   ollama run qwen3:1.7b\n"
                "   ```\n"
                "   *(or `ollama run qwen2.5:1.5b` or `ollama run llama3.2:3b`)*\n"
                "3. Once Ollama is running at `http://127.0.0.1:11434`, I will automatically detect it and switch from Offline Mode to Neural AI Streaming!"
            )

        # 8. General conversational fallback with guidance
        templates = [
            f"I hear you! I'm currently running in **Offline Companion Mode**. "
            f"While local Ollama is offline, I can still chat with you, tell jokes, give you the time, and test speech synthesis. "
            f"To unlock full neural language generation for topics like '{user_prompt[:35]}...', simply launch Ollama on your PC with `ollama serve`!",
            
            f"Thanks for sharing that! As {name}, I'm right here with you on your desktop. "
            f"Local Ollama is currently disconnected, so I'm operating on companion heuristic mode. "
            f"Start Ollama anytime to activate deep reasoning with models like Qwen or Llama!",
            
            f"That's an interesting point! I'm keeping your desktop company in lightweight offline mode. "
            f"If you'd like deep generative reasoning, make sure Ollama is running at `http://127.0.0.1:11434`."
        ]
        return random.choice(templates)

    def generate_stream(self, user_prompt: str, chunk_size: int = 4) -> Iterator[str]:
        """Stream words/tokens with natural cadence simulation."""
        full_text = self.generate_response(user_prompt)
        words = full_text.split(" ")
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i : i + chunk_size])
            if i + chunk_size < len(words):
                chunk += " "
            time.sleep(0.02)  # Natural typing speed (~50 words/sec)
            yield chunk
