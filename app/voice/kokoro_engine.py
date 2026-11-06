"""Kokoro Text-to-Speech (TTS) Engine.

High-fidelity neural speech synthesis using Kokoro-82M ONNX model
producing natural 24kHz studio-quality voice.
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

DEFAULT_KOKORO_VOICE = "af_bella"
KOKORO_REPO_ID = "hexgrad/Kokoro-82M"
KOKORO_SAMPLE_RATE = 24000


class KokoroTTSEngine(BaseTTSEngine):
    """High-quality Kokoro-82M ONNX speech synthesis engine."""

    def __init__(
        self,
        default_voice: str = DEFAULT_KOKORO_VOICE,
        models_dir: Optional[Path | str] = None,
        parent: Optional[QObject] = None,
        fallback_engine: Optional[BaseTTSEngine] = None,
    ) -> None:
        super().__init__(parent)
        self.active_voice_name = default_voice
        self.fallback_engine = fallback_engine

        if models_dir:
            self.models_dir = Path(models_dir)
        else:
            self.models_dir = Path(user_data_dir(appname="AIDesktopFriend")) / "models" / "kokoro"
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self._kokoro = None
        self._lock = threading.RLock()

    def is_available(self) -> bool:
        """Check whether Kokoro is operational (dependencies installed and model weights exist)."""
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return False

        if self._is_loaded and self._kokoro is not None:
            return True

        onnx_path, voices_path = self._get_model_paths()
        return onnx_path.exists() and voices_path.exists()

    def get_available_voices(self) -> List[str]:
        if self._kokoro is not None:
            try:
                return self._kokoro.get_voices()
            except Exception:
                pass
        return [
            "af_heart",
            "af_bella",
            "af_sarah",
            "am_adam",
            "am_michael",
            "bf_emma",
            "bm_george",
        ]

    def _get_model_paths(self) -> tuple[Path, Path]:
        onnx_file = self.models_dir / "kokoro-v0_19.onnx"
        voices_file = self.models_dir / "voices.bin"
        return onnx_file, voices_file

    def _download_file(self, url: str, dest_path: Path, timeout: float = 60.0) -> bool:
        """Download remote asset via HTTP/HTTPS with User-Agent and atomic file replacement."""
        import urllib.request
        temp_dest = dest_path.with_suffix(".tmp")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AIDesktopFriend/1.0",
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status not in (200, 302, 304):
                    logger.warning("Download failed with HTTP %d for %s", response.status, url)
                    return False
                with open(temp_dest, "wb") as out_file:
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        out_file.write(chunk)
            if dest_path.exists():
                dest_path.unlink()
            temp_dest.replace(dest_path)
            return True
        except Exception as e:
            logger.debug("Failed downloading %s: %s", url, e)
            if temp_dest.exists():
                try:
                    temp_dest.unlink()
                except Exception:
                    pass
            return False

    def download_model_if_needed(self) -> bool:
        """Download Kokoro ONNX model and voice bins if not present."""
        onnx_path, voices_path = self._get_model_paths()
        if onnx_path.exists() and voices_path.exists():
            return True

        self.models_dir.mkdir(parents=True, exist_ok=True)

        # 1. Download kokoro-v0_19.onnx
        if not onnx_path.exists():
            downloaded = False
            # Source 1: Hugging Face hexgrad/Kokoro-82M
            try:
                from huggingface_hub import hf_hub_download
                logger.info("Downloading kokoro-v0_19.onnx from Hugging Face hexgrad/Kokoro-82M...")
                dl_path = hf_hub_download(
                    repo_id=KOKORO_REPO_ID,
                    filename="kokoro-v0_19.onnx",
                    local_dir=str(self.models_dir),
                )
                if Path(dl_path).exists():
                    if Path(dl_path) != onnx_path:
                        Path(dl_path).replace(onnx_path)
                    downloaded = True
                    logger.info("kokoro-v0_19.onnx downloaded from Hugging Face.")
            except Exception as e:
                logger.warning("HF download of kokoro-v0_19.onnx failed: %s; trying GitHub fallback...", e)

            # Source 2: GitHub Releases
            if not downloaded:
                github_model_url = (
                    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx"
                )
                logger.info("Downloading kokoro-v0_19.onnx from GitHub releases...")
                if self._download_file(github_model_url, onnx_path):
                    downloaded = True
                    logger.info("kokoro-v0_19.onnx downloaded from GitHub releases.")

            if not downloaded:
                logger.error("Failed to download kokoro-v0_19.onnx.")
                return False

        # 2. Download voices.bin
        if not voices_path.exists():
            downloaded = False
            # Source 1: GitHub Releases (canonical voices.bin for kokoro-onnx runtime)
            github_voices_url = (
                "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin"
            )
            logger.info("Downloading voices.bin from GitHub releases...")
            if self._download_file(github_voices_url, voices_path):
                downloaded = True
                logger.info("voices.bin downloaded from GitHub releases.")

            # Source 2: Hugging Face mirror
            if not downloaded:
                try:
                    from huggingface_hub import hf_hub_download
                    dl_path = hf_hub_download(
                        repo_id=KOKORO_REPO_ID,
                        filename="voices.bin",
                        local_dir=str(self.models_dir),
                    )
                    if Path(dl_path).exists():
                        if Path(dl_path) != voices_path:
                            Path(dl_path).replace(voices_path)
                        downloaded = True
                        logger.info("voices.bin downloaded from Hugging Face.")
                except Exception as e:
                    logger.warning("HF download of voices.bin failed: %s", e)

            if not downloaded:
                logger.error("Failed to download voices.bin.")
                return False

        return onnx_path.exists() and voices_path.exists()

    def load_model(self, voice_name: Optional[str] = None) -> bool:
        """Initialize Kokoro ONNX inference session."""
        with self._lock:
            if voice_name:
                clean_name = voice_name.strip()
                try:
                    from app.voice.voice_registry import VOICE_REGISTRY
                    if clean_name.lower() in VOICE_REGISTRY:
                        clean_name = VOICE_REGISTRY[clean_name.lower()].primary_voice_id
                except Exception:
                    pass
                # Normalize cross-engine voice names from Piper or Windows SAPI5
                if clean_name.startswith("en_") or "lessac" in clean_name or "amy" in clean_name or "Desktop" in clean_name:
                    self.active_voice_name = DEFAULT_KOKORO_VOICE
                else:
                    self.active_voice_name = clean_name

            onnx_path, voices_path = self._get_model_paths()
            if not (onnx_path.exists() and voices_path.exists()):
                if not self.download_model_if_needed():
                    logger.warning("Kokoro model files not found.")
                    self._is_loaded = False
                    return False

            try:
                # Cap ONNX Runtime thread count to prevent 100% CPU starvation during speech generation
                os.environ.setdefault("OMP_NUM_THREADS", "2")
                os.environ.setdefault("ONNXRUNTIME_NUM_THREADS", "2")
                import kokoro_onnx
                logger.info("Initializing Kokoro ONNX session...")
                self._kokoro = kokoro_onnx.Kokoro(
                    model_path=str(onnx_path),
                    voices_path=str(voices_path),
                )
                self._is_loaded = True
                logger.info("Kokoro engine loaded successfully.")
                self.model_loaded.emit(self.active_voice_name)
                return True
            except Exception as e:
                err = f"Failed to load Kokoro ONNX engine: {e}"
                logger.error(err)
                self._kokoro = None
                self._is_loaded = False
                self.error_occurred.emit(err)
                return False

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        """Synthesize text into a 24kHz float32 audio waveform."""
        cleaned_text = clean_text_for_speech(text)
        if not cleaned_text:
            return SynthesizedAudio(
                samples=np.zeros(0, dtype=np.float32),
                sample_rate=KOKORO_SAMPLE_RATE,
                duration_seconds=0.0,
                text=text,
                voice_name=self.active_voice_name,
            )

        self.synthesis_started.emit(cleaned_text)

        with self._lock:
            if not self._is_loaded or self._kokoro is None:
                if not self.load_model():
                    logger.warning("Kokoro model not loaded; checking fallback TTS engine.")
                    if (
                        self.fallback_engine
                        and hasattr(self.fallback_engine, "is_available")
                        and self.fallback_engine.is_available()
                    ):
                        logger.info("Delegating synthesis to fallback TTS engine: %s", type(self.fallback_engine).__name__)
                        return self.fallback_engine.synthesize(cleaned_text, **kwargs)
                    return self._generate_fallback_audio(cleaned_text)

            if self._kokoro is None:
                if (
                    self.fallback_engine
                    and hasattr(self.fallback_engine, "is_available")
                    and self.fallback_engine.is_available()
                ):
                    return self.fallback_engine.synthesize(cleaned_text, **kwargs)
                return self._generate_fallback_audio(cleaned_text)

            try:
                raw_voice = kwargs.get("voice") or kwargs.get("voice_name") or self.active_voice_name
                try:
                    from app.voice.voice_registry import VOICE_REGISTRY
                    if isinstance(raw_voice, str) and raw_voice.lower() in VOICE_REGISTRY:
                        raw_voice = VOICE_REGISTRY[raw_voice.lower()].primary_voice_id
                except Exception:
                    pass
                available = self.get_available_voices()
                if raw_voice not in available:
                    if DEFAULT_KOKORO_VOICE in available:
                        voice = DEFAULT_KOKORO_VOICE
                    elif "af_bella" in available:
                        voice = "af_bella"
                    elif "af" in available:
                        voice = "af"
                    elif available:
                        voice = available[0]
                    else:
                        voice = DEFAULT_KOKORO_VOICE
                else:
                    voice = raw_voice

                # Dynamically resolve language tag based on voice prefix or explicit kwargs
                lang_code = kwargs.get("lang")
                if not lang_code:
                    if voice.startswith(("bf_", "bm_")):
                        lang_code = "en-gb"
                    elif voice.startswith(("jf_", "jm_")):
                        lang_code = "ja"
                    elif voice.startswith(("zf_", "zm_")):
                        lang_code = "zh"
                    elif voice.startswith(("ef_", "em_")):
                        lang_code = "es"
                    elif voice.startswith(("ff_", "fm_")):
                        lang_code = "fr"
                    elif voice.startswith(("hf_", "hm_")):
                        lang_code = "hi"
                    elif voice.startswith(("if_", "im_")):
                        lang_code = "it"
                    elif voice.startswith(("pf_", "pm_")):
                        lang_code = "pt-br"
                    else:
                        lang_code = "en-us"

                effective_speed = float(kwargs.get("speed", self._speed))
                samples, sample_rate = self._kokoro.create(
                    text=cleaned_text,
                    voice=voice,
                    speed=effective_speed,
                    lang=lang_code,
                )

                samples = np.asarray(samples, dtype=np.float32)
                duration_sec = len(samples) / float(sample_rate) if sample_rate > 0 else 0.0

                result = SynthesizedAudio(
                    samples=samples,
                    sample_rate=sample_rate,
                    duration_seconds=duration_sec,
                    text=cleaned_text,
                    voice_name=voice,
                )
                logger.info("Kokoro synthesized %d chars into %.2fs audio (24kHz)", len(cleaned_text), duration_sec)
                self.synthesis_completed.emit(result)
                return result

            except Exception as e:
                err = f"Kokoro synthesis failed: {e}"
                logger.error(err)
                self.error_occurred.emit(err)
                if (
                    self.fallback_engine
                    and hasattr(self.fallback_engine, "is_available")
                    and self.fallback_engine.is_available()
                ):
                    logger.info("Delegating to fallback TTS engine after Kokoro synthesis failure.")
                    return self.fallback_engine.synthesize(cleaned_text, **kwargs)
                return self._generate_fallback_audio(cleaned_text)

    def _generate_fallback_audio(self, text: str) -> SynthesizedAudio:
        """Acoustic tonal fallback if model weights are unavailable."""
        sample_rate = KOKORO_SAMPLE_RATE
        duration = max(0.4, len(text) * 0.06 / self._speed)
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False, dtype=np.float32)
        freq = 280.0
        tone = 0.18 * np.sin(2 * np.pi * freq * t) + 0.07 * np.sin(2 * np.pi * (freq * 1.5) * t)
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
        pass

    def unload_model(self) -> None:
        with self._lock:
            self._kokoro = None
            self._is_loaded = False
            logger.info("Kokoro model unloaded.")
