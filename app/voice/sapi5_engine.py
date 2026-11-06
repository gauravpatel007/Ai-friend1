"""Windows SAPI5 Text-to-Speech (TTS) Engine.

Native Windows speech synthesis engine using Microsoft SAPI5 COM automation
for zero-download, ultra-fast, offline desktop speech.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import QObject

from app.utils.logger import get_logger
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio, clean_text_for_speech

logger = get_logger(__name__)

DEFAULT_SAPI5_VOICE = "Microsoft David Desktop"
SAPI_SAMPLE_RATE = 22050
# SpeechAudioFormatType: SAFT22kHz16BitMono = 22
SAPI_FORMAT_22KHZ_16BIT_MONO = 22
# SpeechVoiceSpeakFlags: SVSFDefault = 0, SVSFPurgeBeforeSpeak = 2
SVSF_DEFAULT = 0
SVSF_PURGE_BEFORE_SPEAK = 2


class Sapi5TTSEngine(BaseTTSEngine):
    """Windows SAPI5 native speech synthesizer."""

    def __init__(
        self,
        default_voice: Optional[str] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.active_voice_name = default_voice or DEFAULT_SAPI5_VOICE
        self.sample_rate = SAPI_SAMPLE_RATE
        self._lock = threading.RLock()
        self._voice_token_map: Dict[str, str] = {}
        self._available_voices: List[str] = []

        self._active_voice: Any = None
        self._is_shutdown: bool = False

        # Probe and cache available voices on creation
        self._refresh_available_voices()
        if not default_voice and self._available_voices:
            self.active_voice_name = self._available_voices[0]

        # Automatically mark as loaded if SAPI is operational
        if self.is_available():
            self._is_loaded = True

    def _refresh_available_voices(self) -> None:
        """Scan the Windows registry and SAPI tokens to discover installed voices."""
        voices: List[str] = []
        token_map: Dict[str, str] = {}

        if sys.platform == "win32":
            import winreg

            # 1. Desktop voices in standard 64-bit and WOW64 registry paths
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Speech\Voices\Tokens"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"),
            ]

            for root_key, subpath in reg_paths:
                try:
                    with winreg.OpenKey(root_key, subpath) as key:
                        idx = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(key, idx)
                                idx += 1
                                full_token_id = f"HKEY_LOCAL_MACHINE\\{subpath}\\{subkey_name}"
                                voice_desc = ""
                                try:
                                    with winreg.OpenKey(key, subkey_name) as voice_key:
                                        voice_desc, _ = winreg.QueryValueEx(voice_key, "")
                                except OSError:
                                    voice_desc = subkey_name

                                if not voice_desc:
                                    voice_desc = subkey_name

                                if voice_desc not in voices:
                                    voices.append(voice_desc)
                                    token_map[voice_desc] = full_token_id
                                    # Also map short subkey name for convenience
                                    token_map[subkey_name] = full_token_id
                            except OSError:
                                break
                except OSError:
                    pass

        # If no registry voices discovered, provide sensible defaults
        if not voices:
            voices = ["Microsoft David Desktop", "Microsoft Zira Desktop"]

        self._available_voices = voices
        self._voice_token_map = token_map

    def is_available(self) -> bool:
        """Check whether Windows SAPI5 is operational on this host."""
        if sys.platform != "win32":
            return False

        # 1. Primary: Native win32com COM automation (pywin32)
        try:
            import pythoncom
            import win32com.client
            try:
                pythoncom.CoInitialize()
            except Exception:
                pass
            v_obj = win32com.client.Dispatch("SAPI.SpVoice")
            s_obj = win32com.client.Dispatch("SAPI.SpMemoryStream")
            return v_obj is not None and s_obj is not None
        except Exception:
            pass

        # 2. Fallback: PythonNet CLR bridge if installed
        try:
            import clr  # noqa: F401
            import importlib
            system_mod = importlib.import_module("System")
            type_cls = getattr(system_mod, "Type", None)
            if type_cls is None:
                return False

            v_type = type_cls.GetTypeFromProgID("SAPI.SpVoice")
            s_type = type_cls.GetTypeFromProgID("SAPI.SpMemoryStream")
            return v_type is not None and s_type is not None
        except Exception:
            return False

    def get_available_voices(self) -> List[str]:
        """Return list of human-readable voice identifiers available in SAPI5."""
        if not self._available_voices:
            self._refresh_available_voices()
        return list(self._available_voices)

    def load_model(self, voice_name: Optional[str] = None) -> bool:
        """Set active voice model by name or fuzzy identifier."""
        if voice_name:
            # Look for exact or case-insensitive partial match
            target = voice_name.strip().lower()
            matched = None
            for v in self.get_available_voices():
                if target in v.lower() or v.lower() in target:
                    matched = v
                    break
            self.active_voice_name = matched or voice_name
        elif self.get_available_voices():
            self.active_voice_name = self.get_available_voices()[0]

        self._is_loaded = True
        try:
            self.model_loaded.emit(self.active_voice_name)
        except RuntimeError:
            pass
        return True

    def synthesize(self, text: str, **kwargs) -> SynthesizedAudio:
        """Synthesize plain text into a float32 audio waveform synchronously."""
        cleaned_text = clean_text_for_speech(text)
        if not cleaned_text:
            return SynthesizedAudio(
                samples=np.zeros(0, dtype=np.float32),
                sample_rate=self.sample_rate,
                duration_seconds=0.0,
                text=text,
                voice_name=self.active_voice_name,
            )

        try:
            self.synthesis_started.emit(cleaned_text)
        except RuntimeError:
            pass

        if self._is_shutdown:
            logger.debug("SAPI5 synthesis rejected: engine is shut down.")
            return SynthesizedAudio(
                samples=np.zeros(0, dtype=np.float32),
                sample_rate=self.sample_rate,
                duration_seconds=0.0,
                text=cleaned_text,
                voice_name=self.active_voice_name,
            )

        if not self.is_available():
            logger.warning("Windows SAPI5 unavailable; using fallback synthesized audio.")
            return self._generate_fallback_audio(cleaned_text)

        with self._lock:
            if self._is_shutdown:
                return self._generate_fallback_audio(cleaned_text)

            # -----------------------------------------------------------------
            # 1. Primary: Native win32com COM automation (pywin32)
            # -----------------------------------------------------------------
            try:
                import pythoncom
                import win32com.client

                try:
                    pythoncom.CoInitialize()
                except Exception:
                    pass

                voice = win32com.client.Dispatch("SAPI.SpVoice")
                stream = win32com.client.Dispatch("SAPI.SpMemoryStream")
                fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")

                self._active_voice = voice

                # Configure format to 22050 Hz 16-bit Mono (SAFT22kHz16BitMono = 22)
                fmt.Type = SAPI_FORMAT_22KHZ_16BIT_MONO
                stream.Format = fmt

                # Map playback speed (0.5x to 2.0x) to SAPI Rate (-10 to +10)
                raw_rate = round((self._speed - 1.0) * 10.0)
                rate = max(-10, min(10, raw_rate))
                voice.Rate = rate

                # Select active voice token if requested and configured
                requested_voice = kwargs.get("voice_name") or self.active_voice_name
                target_name = (requested_voice or "").lower()
                token_id = self._voice_token_map.get(requested_voice, self._voice_token_map.get(self.active_voice_name))
                selected = False

                # First match via installed voice tokens collection
                try:
                    for token in voice.GetVoices():
                        desc = token.GetDescription().lower()
                        t_id = getattr(token, "Id", "").lower()
                        if target_name and (target_name in desc or desc in target_name):
                            voice.Voice = token
                            selected = True
                            break
                        if token_id and t_id.endswith(token_id.lower()):
                            voice.Voice = token
                            selected = True
                            break
                except Exception as ve:
                    logger.debug("Voice token iteration note: %s", ve)

                # Fallback to direct SpObjectToken SetId if not found in collection
                if not selected and token_id:
                    try:
                        token_obj = win32com.client.Dispatch("SAPI.SpObjectToken")
                        token_obj.SetId(token_id)
                        voice.Voice = token_obj
                        selected = True
                    except Exception as ve:
                        logger.debug("Direct SpObjectToken SetId note for '%s': %s", token_id, ve)

                # Direct output to memory stream
                voice.AudioOutputStream = stream

                # Synthesize text synchronously (SVSF_DEFAULT = 0)
                voice.Speak(cleaned_text, SVSF_DEFAULT)

                # Retrieve raw byte buffer from memory stream
                raw_data = stream.GetData()
                if raw_data is None:
                    raise RuntimeError("SAPI SpMemoryStream.GetData() returned None.")

                raw_bytes = bytes(raw_data)
                pcm16 = np.frombuffer(raw_bytes, dtype=np.int16)
                audio_samples = pcm16.astype(np.float32) / 32768.0

                duration_sec = len(audio_samples) / float(self.sample_rate) if self.sample_rate > 0 else 0.0

                result = SynthesizedAudio(
                    samples=audio_samples,
                    sample_rate=self.sample_rate,
                    duration_seconds=duration_sec,
                    text=cleaned_text,
                    voice_name=self.active_voice_name,
                )

                logger.info(
                    "SAPI5 (win32com) Synthesized %d characters in %.2fs (rate=%dHz)",
                    len(cleaned_text),
                    duration_sec,
                    self.sample_rate,
                )

                try:
                    self.synthesis_completed.emit(result)
                except RuntimeError:
                    pass

                return result

            except Exception as win32_err:
                logger.debug("win32com SAPI5 synthesis note (%s); attempting CLR fallback...", win32_err)

            # -----------------------------------------------------------------
            # 2. Fallback: PythonNet CLR bridge if installed
            # -----------------------------------------------------------------
            try:
                # Initialize COM for the current thread
                if sys.platform == "win32":
                    try:
                        ctypes.windll.ole32.CoInitialize(None)
                    except Exception:
                        pass

                import clr  # noqa: F401
                import importlib
                system_mod = importlib.import_module("System")
                type_cls = getattr(system_mod, "Type")
                activator_cls = getattr(system_mod, "Activator")
                reflection_mod = importlib.import_module("System.Reflection")
                binding_flags = getattr(reflection_mod, "BindingFlags")

                voice_type = type_cls.GetTypeFromProgID("SAPI.SpVoice")
                stream_type = type_cls.GetTypeFromProgID("SAPI.SpMemoryStream")
                fmt_type = type_cls.GetTypeFromProgID("SAPI.SpAudioFormat")

                if voice_type is None or stream_type is None or fmt_type is None:
                    raise RuntimeError("Failed to resolve SAPI COM types.")

                voice = activator_cls.CreateInstance(voice_type)
                stream = activator_cls.CreateInstance(stream_type)
                fmt = activator_cls.CreateInstance(fmt_type)

                self._active_voice = voice
                self._active_voice_type = voice_type
                self._binding_flags = binding_flags

                # Configure format to 22050 Hz 16-bit Mono
                fmt_type.InvokeMember("Type", binding_flags.SetProperty, None, fmt, [SAPI_FORMAT_22KHZ_16BIT_MONO])
                stream_type.InvokeMember("Format", binding_flags.SetProperty, None, stream, [fmt])

                # Map playback speed (0.5x to 2.0x) to SAPI Rate (-10 to +10)
                req_speed = kwargs.get("speed")
                if req_speed is not None:
                    raw_rate = round((float(req_speed) - 1.0) * 10.0)
                else:
                    raw_rate = round((self._speed - 1.0) * 10.0)
                rate = max(-10, min(10, raw_rate))
                voice_type.InvokeMember("Rate", binding_flags.SetProperty, None, voice, [rate])

                # Select active voice token if requested and configured
                requested_voice = kwargs.get("voice_name") or kwargs.get("voice") or self.active_voice_name
                target_name = (requested_voice or "").lower().strip()
                token_id = self._voice_token_map.get(requested_voice)
                if not token_id and target_name:
                    for v_name, v_tok in self._voice_token_map.items():
                        v_low = v_name.lower()
                        if target_name in v_low or v_low in target_name:
                            token_id = v_tok
                            break

                if token_id:
                    try:
                        token_type = type_cls.GetTypeFromProgID("SAPI.SpObjectToken")
                        if token_type is not None:
                            token = activator_cls.CreateInstance(token_type)
                            token_type.InvokeMember("SetId", binding_flags.InvokeMethod, None, token, [token_id, "", False])
                            voice_type.InvokeMember("Voice", binding_flags.SetProperty, None, voice, [token])
                    except Exception as ve:
                        logger.debug("Could not switch to voice token '%s' (fallback to default): %s", token_id, ve)

                # Direct output to memory stream
                voice_type.InvokeMember("AudioOutputStream", binding_flags.SetProperty, None, voice, [stream])

                # Synthesize text synchronously (SVSF_DEFAULT = 0)
                voice_type.InvokeMember("Speak", binding_flags.InvokeMethod, None, voice, [cleaned_text, SVSF_DEFAULT])

                # Retrieve raw byte buffer from memory stream
                raw_data = stream_type.InvokeMember("GetData", binding_flags.InvokeMethod, None, stream, None)
                if raw_data is None:
                    raise RuntimeError("SAPI SpMemoryStream.GetData() returned None.")

                raw_bytes = bytes(raw_data)
                pcm16 = np.frombuffer(raw_bytes, dtype=np.int16)
                audio_samples = pcm16.astype(np.float32) / 32768.0

                duration_sec = len(audio_samples) / float(self.sample_rate) if self.sample_rate > 0 else 0.0

                result = SynthesizedAudio(
                    samples=audio_samples,
                    sample_rate=self.sample_rate,
                    duration_seconds=duration_sec,
                    text=cleaned_text,
                    voice_name=requested_voice or self.active_voice_name,
                )

                logger.info(
                    "SAPI5 (CLR) Synthesized %d characters in %.2fs (rate=%dHz)",
                    len(cleaned_text),
                    duration_sec,
                    self.sample_rate,
                )

                try:
                    self.synthesis_completed.emit(result)
                except RuntimeError:
                    pass

                return result

            except Exception as e:
                err = f"SAPI5 synthesis error: {e}"
                logger.error(err)
                try:
                    self.error_occurred.emit(err)
                except RuntimeError:
                    pass
                return self._generate_fallback_audio(cleaned_text)
            finally:
                self._active_voice = None

    def _generate_fallback_audio(self, text: str) -> SynthesizedAudio:
        """Generate a synthetic tone when SAPI synthesis fails or runs off-platform."""
        duration_sec = max(0.2, len(text) * 0.04)
        total_samples = int(self.sample_rate * duration_sec)
        t = np.linspace(0, duration_sec, total_samples, endpoint=False, dtype=np.float32)
        freq = 440.0
        waveform = 0.1 * np.sin(2.0 * np.pi * freq * t)

        return SynthesizedAudio(
            samples=waveform,
            sample_rate=self.sample_rate,
            duration_seconds=duration_sec,
            text=text,
            voice_name=self.active_voice_name,
        )

    def stop(self) -> None:
        """Cancel current synthesis immediately."""
        active_voice = self._active_voice
        if active_voice is not None:
            # 1. win32com SpVoice
            if hasattr(active_voice, "Speak"):
                try:
                    active_voice.Speak("", SVSF_PURGE_BEFORE_SPEAK)
                    logger.info("Successfully purged active SAPI5 speech stream via win32com.")
                except Exception as e:
                    logger.debug("Failed to purge active SAPI voice instance via win32com: %s", e)
            else:
                # 2. CLR SpVoice
                active_type = getattr(self, "_active_voice_type", None)
                flags = getattr(self, "_binding_flags", None)
                if active_type is not None and flags is not None:
                    try:
                        active_type.InvokeMember(
                            "Speak", flags.InvokeMethod, None, active_voice, ["", SVSF_PURGE_BEFORE_SPEAK]
                        )
                        logger.info("Successfully purged active SAPI5 speech stream via CLR.")
                    except Exception as e:
                        logger.debug("Failed to purge active SAPI voice instance via CLR: %s", e)

        if not self.is_available():
            return

        # Purge global SAPI queue via win32com
        try:
            import pythoncom
            import win32com.client
            try:
                pythoncom.CoInitialize()
            except Exception:
                pass
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Speak("", SVSF_PURGE_BEFORE_SPEAK)
            return
        except Exception:
            pass

        # Fallback purge via CLR
        try:
            import clr  # noqa: F401
            import importlib
            system_mod = importlib.import_module("System")
            type_cls = getattr(system_mod, "Type")
            activator_cls = getattr(system_mod, "Activator")
            reflection_mod = importlib.import_module("System.Reflection")
            binding_flags = getattr(reflection_mod, "BindingFlags")

            voice_type = type_cls.GetTypeFromProgID("SAPI.SpVoice")
            if voice_type is not None:
                voice = activator_cls.CreateInstance(voice_type)
                voice_type.InvokeMember(
                    "Speak", binding_flags.InvokeMethod, None, voice, ["", SVSF_PURGE_BEFORE_SPEAK]
                )
        except Exception as e:
            logger.debug("Failed to purge SAPI speech stream: %s", e)

    def emergency_stop(self) -> None:
        """Immediately abort active SAPI synthesis."""
        self.stop()

    def shutdown(self) -> None:
        """Permanently shut down SAPI5 engine and free COM resources."""
        self._is_shutdown = True
        self.emergency_stop()
        self.unload_model()

    def unload_model(self) -> None:
        """Free cached SAPI COM resources."""
        self._is_loaded = False


# Convenient alias for system TTS engine
SystemTTSEngine = Sapi5TTSEngine
