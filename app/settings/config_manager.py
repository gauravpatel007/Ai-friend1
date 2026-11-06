"""Configuration Manager.

Manages persistent application settings in the Windows application data directory.
Provides deep-merged default fallbacks, thread safety, and change notification signals.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Tuple

from platformdirs import user_data_dir
from PySide6.QtCore import QObject, Signal

from app.utils.logger import get_logger

logger = get_logger(__name__)

APP_NAME = "AIDesktopFriend"
CONFIG_FILENAME = "settings.json"


def _deep_merge(source: Dict[str, Any], destination: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge source dictionary into destination dictionary."""
    for key, value in source.items():
        if isinstance(value, dict) and key in destination and isinstance(destination[key], dict):
            _deep_merge(value, destination[key])
        else:
            destination[key] = copy.deepcopy(value)
    return destination


class ConfigManager(QObject):
    """Central configuration manager for application settings."""

    # Signal emitted when a setting changes: key_path, new_value
    setting_changed = Signal(str, object)
    config_reloaded = Signal()

    def __init__(
        self,
        config_path: Optional[Path | str] = None,
        default_config_path: Optional[Path | str] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()

        # Locate default config file
        if default_config_path:
            self.default_config_path = Path(default_config_path)
        else:
            # Fallback relative to project root
            self.default_config_path = (
                Path(__file__).resolve().parent.parent.parent / "config" / "default_config.json"
            )

        # Locate persistent config file in AppData
        if config_path:
            self.config_path = Path(config_path)
        else:
            app_data = Path(user_data_dir(appname=APP_NAME, appauthor=APP_NAME))
            app_data.mkdir(parents=True, exist_ok=True)
            self.config_path = app_data / CONFIG_FILENAME

        self._defaults: Dict[str, Any] = self._load_defaults()
        self._config_data: Dict[str, Any] = {}
        self.load()

    def _load_defaults(self) -> Dict[str, Any]:
        """Load default configuration from template file."""
        if self.default_config_path.exists():
            try:
                with open(self.default_config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to parse default config at %s: %s", self.default_config_path, e)

        # Fallback minimal defaults if file cannot be read
        return {
            "general": {"app_name": "AI Desktop Friend", "start_at_login": False, "debug": False},
            "pet": {"size": 120, "always_on_top": True},
            "ai": {"model": "llama3.2:3b", "personality": "friendly"},
            "voice": {"enabled": False, "mode": "push_to_talk"},
            "language": {
                "response_language": "auto",
                "response_format": "native",
                "voice_output_language": "follow_response",
                "specific_voice_language": "en",
                "stt_language": "auto",
            },
        }

    def load(self) -> None:
        """Load user settings from persistent file and merge with defaults."""
        with self._lock:
            # Start with deep copy of defaults
            merged_data = copy.deepcopy(self._defaults)

            if self.config_path.exists():
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        user_data = json.load(f)
                        if isinstance(user_data, dict):
                            _deep_merge(user_data, merged_data)
                            logger.info("Loaded settings from %s", self.config_path)
                        else:
                            logger.warning("Config file at %s was not a JSON object. Using defaults.", self.config_path)
                except Exception as e:
                    logger.error("Error reading settings file %s: %s. Using defaults.", self.config_path, e)
            else:
                logger.info("No existing settings file found at %s. Initializing from defaults.", self.config_path)
                self._config_data = merged_data
                self._save_internal(merged_data)
                return

            self._config_data = merged_data

    def save(self) -> bool:
        """Save current configuration to disk."""
        with self._lock:
            return self._save_internal(self._config_data)

    def _save_internal(self, data: Dict[str, Any]) -> bool:
        """Atomic write to configuration file with retry on transient Windows file lock."""
        import time
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.config_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Atomic replace (retry on Windows if transient file lock occurs)
            for attempt in range(3):
                try:
                    temp_path.replace(self.config_path)
                    break
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(0.05)
            logger.debug("Successfully saved settings to %s", self.config_path)
            return True
        except Exception as e:
            logger.error("Failed to write settings to %s: %s", self.config_path, e)
            return False

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get setting using dot notation (e.g. 'pet.size' or 'ai.model')."""
        with self._lock:
            keys = key_path.split(".")
            current: Any = self._config_data
            for k in keys:
                if isinstance(current, dict) and k in current:
                    current = current[k]
                else:
                    return default
            return copy.deepcopy(current)

    def get_category(self, category: str) -> Dict[str, Any]:
        """Return all configuration key-values for a given category (e.g. 'voice', 'pet')."""
        val = self.get(category, {})
        return val if isinstance(val, dict) else {}

    def set(self, key_path: str, value: Any, auto_save: bool = True) -> bool:
        """Set setting using dot notation and optionally save immediately."""
        changed = False
        with self._lock:
            keys = key_path.split(".")
            current = self._config_data
            for k in keys[:-1]:
                if k not in current or not isinstance(current[k], dict):
                    current[k] = {}
                current = current[k]
            
            # Guard against redundant setting updates
            if keys[-1] in current and current[keys[-1]] == value:
                return True

            current[keys[-1]] = copy.deepcopy(value)
            changed = True

        if changed:
            # Notify outside lock to avoid potential deadlocks in signal handlers
            self.setting_changed.emit(key_path, value)

            if auto_save:
                return self.save()
        return True

    def set_many(self, settings_dict: Dict[str, Any], auto_save: bool = True) -> bool:
        """Set multiple configuration keys atomically with a single disk save and individual change signals."""
        changed_keys: List[tuple[str, Any]] = []
        with self._lock:
            for key_path, value in settings_dict.items():
                keys = key_path.split(".")
                current = self._config_data
                for k in keys[:-1]:
                    if k not in current or not isinstance(current[k], dict):
                        current[k] = {}
                    current = current[k]

                if keys[-1] in current and current[keys[-1]] == value:
                    continue

                current[keys[-1]] = copy.deepcopy(value)
                changed_keys.append((key_path, value))

            if auto_save and changed_keys:
                self._save_internal(self._config_data)

        # Notify outside lock to avoid deadlocks or re-entrant recursion
        for key_path, value in changed_keys:
            self.setting_changed.emit(key_path, value)

        return True

    def reset_to_defaults(self) -> bool:
        """Reset all configuration values to defaults and save."""
        with self._lock:
            self._config_data = copy.deepcopy(self._defaults)
        success = self.save()
        self.config_reloaded.emit()
        return success

    @property
    def all_settings(self) -> Dict[str, Any]:
        """Return a copy of the entire configuration dictionary."""
        with self._lock:
            return copy.deepcopy(self._config_data)


_instance: Optional[ConfigManager] = None
_instance_lock = threading.Lock()


def get_config_manager(config_path: Optional[Path | str] = None) -> ConfigManager:
    """Return the global singleton ConfigManager instance."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ConfigManager(config_path=config_path)
        return _instance

