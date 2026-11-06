"""Piper Text-to-Speech (TTS) Engine.

Lightweight, local neural speech synthesis using Piper ONNX models with
automatic model downloading and caching in user application data.
"""

from __future__ import annotations

import os
from pathlib import Path
import threading
from typing import List, Optional

import numpy as np
from platformdirs import user_data_dir

from PySide6.QtCore import QObject

from app.utils.logger import get_logger
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio, clean_text_for_speech

logger = get_logger(__name__)

DEFAULT_PIPER_VOICE = "en_US-lessac-medium"
PIPER_REPO_ID = "rhasspy/piper-voices"

# Registry of supported Piper voices and their Hugging Face paths
PIPER_VOICE_REGISTRY = {
    "en_US-lessac-medium": {
        "onnx": "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "json": "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        "sample_rate": 22050,
        "language": "en",
    },
    "en_US-amy-low": {
        "onnx": "en/en_US/amy/low/en_US-amy-low.onnx",
        "json": "en/en_US/amy/low/en_US-amy-low.onnx.json",
        "sample_rate": 16000,
        "language": "en",
    },
}


class PiperTTSEngine(BaseTTSEngine):
    """Local Piper TTS synthesizer."""

    def __init__(
        self,
        default_voice: str = DEFAULT_PIPER_VOICE,
        models_dir: Optional[Path | str] = None,
        fallback_engine: Optional[BaseTTSEngine] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.active_voice_name = default_voice
        self.fallback_engine = fallback_engine

        if models_dir:
            self.models_dir = Path(models_dir)
        else:
            self.models_dir = Path(user_data_dir(appname="AIDesktopFriend")) / "models" / "piper"
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self._voice = None
        self._lock = threading.RLock()

    def is_available(self) -> bool:
        """Check whether Piper is installed and voice weights exist on disk or in memory."""
        try:
            import piper  # noqa: F401
        except ImportError:
            return False

        if self._is_loaded and self._voice is not None:
            return True

        onnx_path, json_path = self._get_voice_paths(self.active_voice_name)
        if onnx_path.exists() and json_path.exists():
            return True

        for v in PIPER_VOICE_REGISTRY:
            o, j = self._get_voice_paths(v)
            if o.exists() and j.exists():
                return True

        return False

    def get_available_voices(self) -> List[str]:
        return list(PIPER_VOICE_REGISTRY.keys())

    def _get_voice_paths(self, voice_name: str) -> tuple[Path, Path]:
        """Return local paths for the .onnx and .json files for the voice."""
        onnx_file = self.models_dir / f"{voice_name}.onnx"
        json_file = self.models_dir / f"{voice_name}.onnx.json"
        return onnx_file, json_file

    def download_voice_if_needed(self, voice_name: str) -> bool:
        """Download voice model assets from Hugging Face if not cached locally."""
        if voice_name not in PIPER_VOICE_REGISTRY:
            logger.warning("Voice '%s' not recognized in Piper registry.", voice_name)
            return False

        onnx_path, json_path = self._get_voice_paths(voice_name)
        if onnx_path.exists() and json_path.exists():
            return True

        info = PIPER_VOICE_REGISTRY[voice_name]
        try:
            from huggingface_hub import hf_hub_download
            logger.info("Downloading Piper voice '%s' from Hugging Face...", voice_name)

            downloaded_onnx = hf_hub_download(
                repo_id=PIPER_REPO_ID,
                filename=str(info["onnx"]),
                local_dir=str(self.models_dir),
            )
            downloaded_json = hf_hub_download(
                repo_id=PIPER_REPO_ID,
                filename=str(info["json"]),
                local_dir=str(self.models_dir),
            )

            # Move/rename to standard format if needed
            downloaded_onnx_path = Path(downloaded_onnx)
            downloaded_json_path = Path(downloaded_json)

            if downloaded_onnx_path != onnx_path:
                downloaded_onnx_path.replace(onnx_path)
            if downloaded_json_path != json_path:
                downloaded_json_path.replace(json_path)

            logger.info("Piper voice '%s' downloaded successfully.", voice_name)
            return True
        except Exception as e:
            logger.error("Failed to download Piper voice '%s': %s", voice_name, e)
            return False

    def load_model(self, voice_name: Optional[str] = None) -> bool:
        """Load Piper voice model into memory."""
        with self._lock:
            target_voice = voice_name or self.active_voice_name
            if target_voice not in PIPER_VOICE_REGISTRY:
                target_voice = DEFAULT_PIPER_VOICE
            self.active_voice_name = target_voice

            onnx_path, json_path = self._get_voice_paths(target_voice)
            if not (onnx_path.exists() and json_path.exists()):
                downloaded = self.download_voice_if_needed(target_voice)
                if not downloaded:
                    logger.warning("Could not find or download Piper voice '%s'.", target_voice)
                    self._is_loaded = False
                    return False

            try:
                import piper
                logger.info("Loading Piper voice '%s' from %s...", target_voice, onnx_path)
                self._voice = piper.PiperVoice.load(
                    model_path=str(onnx_path),
                    config_path=str(json_path),
                )
                self._is_loaded = True
                logger.info("Piper voice '%s' loaded successfully.", target_voice)
                try:
                    self.model_loaded.emit(target_voice)
                except RuntimeError:
                    pass
                return True
            except Exception as e:
                err = f"Failed to load Piper model '{target_voice}': {e}"
                logger.error(err)
                self._voice = None
                self._is_loaded = False
                try:
                    self.error_occurred.emit(err)
                except RuntimeError:
                    pass
                return False

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        """Synthesize text into a float32 audio waveform."""
        cleaned_text = clean_text_for_speech(text)
        if not cleaned_text:
            return SynthesizedAudio(
                samples=np.zeros(0, dtype=np.float32),
                sample_rate=22050,
                duration_seconds=0.0,
                text=text,
                voice_name=self.active_voice_name,
            )

        try:
            self.synthesis_started.emit(cleaned_text)
        except RuntimeError:
            pass

        with self._lock:
            # Check if dynamic voice switch requested
            requested_voice = kwargs.get("voice") or kwargs.get("voice_name")
            if requested_voice and requested_voice in PIPER_VOICE_REGISTRY and requested_voice != self.active_voice_name:
                self.load_model(requested_voice)

            # Fallback if model is not loaded
            if not self._is_loaded or self._voice is None:
                if not self.load_model():
                    if self.fallback_engine and hasattr(self.fallback_engine, "synthesize") and self.fallback_engine.is_available():
                        logger.info("Piper model not loaded; delegating synthesis to %s.", type(self.fallback_engine).__name__)
                        return self.fallback_engine.synthesize(cleaned_text, **kwargs)
                    logger.warning("Piper model not loaded; generating synthetic fallback audio.")
                    return self._generate_fallback_audio(cleaned_text)

            try:
                import piper
                voice = self._voice
                if voice is None:
                    if self.fallback_engine and hasattr(self.fallback_engine, "synthesize") and self.fallback_engine.is_available():
                        return self.fallback_engine.synthesize(cleaned_text, **kwargs)
                    return self._generate_fallback_audio(cleaned_text)

                # Speed control: Piper length_scale < 1.0 increases speed
                effective_speed = float(kwargs.get("speed", self._speed))
                length_scale = 1.0 / max(0.5, min(2.0, effective_speed))
                syn_config = piper.SynthesisConfig(length_scale=length_scale)

                chunks = list(voice.synthesize(cleaned_text, syn_config=syn_config))
                if not chunks:
                    if self.fallback_engine and hasattr(self.fallback_engine, "synthesize") and self.fallback_engine.is_available():
                        return self.fallback_engine.synthesize(cleaned_text, **kwargs)
                    return self._generate_fallback_audio(cleaned_text)

                sample_rate = chunks[0].sample_rate
                # Collect float32 arrays
                valid_arrays = [c.audio_float_array for c in chunks if c.audio_float_array is not None]
                if valid_arrays:
                    audio_samples = np.concatenate(valid_arrays).astype(np.float32)
                else:
                    audio_samples = np.zeros(0, dtype=np.float32)

                duration_sec = len(audio_samples) / float(sample_rate) if sample_rate > 0 else 0.0

                result = SynthesizedAudio(
                    samples=audio_samples,
                    sample_rate=sample_rate,
                    duration_seconds=duration_sec,
                    text=cleaned_text,
                    voice_name=self.active_voice_name,
                )
                logger.info("Synthesized %d characters in %.2fs (rate=%dHz)", len(cleaned_text), duration_sec, sample_rate)
                try:
                    self.synthesis_completed.emit(result)
                except RuntimeError:
                    pass
                return result

            except Exception as e:
                err = f"Piper synthesis error: {e}"
                logger.error(err)
                try:
                    self.error_occurred.emit(err)
                except RuntimeError:
                    pass
                if self.fallback_engine and hasattr(self.fallback_engine, "synthesize") and self.fallback_engine.is_available():
                    logger.info("Piper error occurred; delegating to %s.", type(self.fallback_engine).__name__)
                    return self.fallback_engine.synthesize(cleaned_text, **kwargs)
                return self._generate_fallback_audio(cleaned_text)

    def _generate_fallback_audio(self, text: str) -> SynthesizedAudio:
        """Generate gentle tonal acoustic fallback when neural weights are unavailable."""
        sample_rate = 22050
        # Estimate duration: ~70ms per character
        duration = max(0.4, len(text) * 0.06 / self._speed)
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False, dtype=np.float32)

        # Melodic warm tones that modulate with phoneme-like cadence
        freq = 240.0
        tone = 0.15 * np.sin(2 * np.pi * freq * t) + 0.08 * np.sin(2 * np.pi * (freq * 1.5) * t)
        # Apply smooth envelope
        envelope = np.maximum(0.0, np.sin(np.pi * np.linspace(0, 1, len(t), dtype=np.float32))) ** 0.5
        samples = (tone * envelope).astype(np.float32)

        result = SynthesizedAudio(
            samples=samples,
            sample_rate=sample_rate,
            duration_seconds=duration,
            text=text,
            voice_name="fallback",
        )
        self.synthesis_completed.emit(result)
        return result

    def stop(self) -> None:
        """Cancel ongoing synthesis."""
        pass

    def unload_model(self) -> None:
        """Free memory occupied by the active Piper voice."""
        with self._lock:
            self._voice = None
            self._is_loaded = False
            logger.info("Piper voice unloaded.")
