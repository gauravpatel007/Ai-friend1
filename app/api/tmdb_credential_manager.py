"""TMDB Credential Manager for User-Managed API Keys.

Provides secure storage using Windows DPAPI (Data Protection API) with safe
cross-platform fallback, local key history tracking, deduplication, live TMDB
validation, and persistent active key selection with .env fallback.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

import requests
from platformdirs import user_data_dir

from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

APP_NAME = "AIDesktopFriend"
CREDENTIALS_FILENAME = "tmdb_credentials.enc"
TMDB_AUTH_URL = "https://api.themoviedb.org/3/authentication"
TMDB_CONFIG_URL = "https://api.themoviedb.org/3/configuration"


def mask_api_key(key: str) -> str:
    """Safely mask an API key for display, exposing only the last 4 characters."""
    if not key:
        return ""
    clean = key.strip()
    if len(clean) <= 6:
        return "••••"
    return "•" * (len(clean) - 4) + clean[-4:]


def _hash_fingerprint(key: str) -> str:
    """Compute a salted hash fingerprint to detect duplicates without storing plaintext."""
    salt = "ai_friend_tmdb_salt_v1"
    return hashlib.sha256(f"{salt}:{key.strip()}".encode("utf-8")).hexdigest()


class WindowsDPAPI:
    """Windows Data Protection API wrapper via ctypes.windll.crypt32."""

    @staticmethod
    def is_available() -> bool:
        return sys.platform == "win32"

    @staticmethod
    def encrypt(text: str) -> str:
        """Encrypt string using logged-in Windows user credentials."""
        import ctypes
        import ctypes.wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        data = text.encode("utf-8")
        blob_in = DATA_BLOB(
            len(data),
            ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)),
        )
        blob_out = DATA_BLOB()

        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), "TMDB_VAULT", None, None, None, 0, ctypes.byref(blob_out)
        ):
            raise RuntimeError("CryptProtectData failed on current system.")

        encrypted_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return base64.b64encode(encrypted_bytes).decode("ascii")

    @staticmethod
    def decrypt(b64_cipher: str) -> str:
        """Decrypt string using logged-in Windows user credentials."""
        import ctypes
        import ctypes.wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        raw_bytes = base64.b64decode(b64_cipher.encode("ascii"))
        blob_in = DATA_BLOB(
            len(raw_bytes),
            ctypes.cast(ctypes.create_string_buffer(raw_bytes), ctypes.POINTER(ctypes.c_char)),
        )
        blob_out = DATA_BLOB()

        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            raise RuntimeError("CryptUnprotectData failed on current system.")

        decrypted_text = ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8")
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return decrypted_text


class FallbackVault:
    """Machine/User tied obfuscation fallback for non-Windows platforms or test runners."""

    @staticmethod
    def _get_machine_key() -> bytes:
        machine_seed = f"{os.environ.get('USERNAME', 'default')}:{sys.platform}:{os.environ.get('COMPUTERNAME', 'host')}"
        return hashlib.sha256(machine_seed.encode("utf-8")).digest()

    @classmethod
    def encrypt(cls, text: str) -> str:
        key = cls._get_machine_key()
        raw = text.encode("utf-8")
        xor_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(raw)])
        return base64.b64encode(xor_bytes).decode("ascii")

    @classmethod
    def decrypt(cls, b64_cipher: str) -> str:
        key = cls._get_machine_key()
        raw = base64.b64decode(b64_cipher.encode("ascii"))
        decrypted_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(raw)])
        return decrypted_bytes.decode("utf-8")


class TMDBCredentialManager:
    """Manages secure persistence and live switching of TMDB API keys."""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        vault_path: Optional[Path | str] = None,
    ) -> None:
        self._lock = threading.Lock()
        self.config_manager = config_manager

        if vault_path:
            self.vault_path = Path(vault_path)
        else:
            app_data = Path(user_data_dir(appname=APP_NAME, appauthor=APP_NAME))
            app_data.mkdir(parents=True, exist_ok=True)
            self.vault_path = app_data / CREDENTIALS_FILENAME

        self._cached_secrets: Dict[str, str] = {}
        self._load_vault()

        if self.config_manager is not None and hasattr(self.config_manager, "config_reloaded"):
            try:
                self.config_manager.config_reloaded.connect(self.refresh)
            except Exception:
                pass

    def refresh(self) -> Tuple[str, str, str]:
        """Reload credentials vault and determine active API key tuple (active_key, source, active_key_id)."""
        self._load_vault()
        active_key, source, active_id = self.get_active_api_key()
        logger.debug("TMDBCredentialManager refreshed (source=%s, id=%s)", source, active_id)
        return active_key, source, active_id

    def _encrypt(self, text: str) -> str:
        if WindowsDPAPI.is_available():
            try:
                return "dpapi:" + WindowsDPAPI.encrypt(text)
            except Exception as e:
                logger.warning("Windows DPAPI encryption fell back: %s", e)
        return "fallback:" + FallbackVault.encrypt(text)

    def _decrypt(self, cipher_str: str) -> str:
        if cipher_str.startswith("dpapi:") and WindowsDPAPI.is_available():
            try:
                return WindowsDPAPI.decrypt(cipher_str[len("dpapi:"):])
            except Exception as e:
                logger.warning("DPAPI decryption error: %s", e)
        elif cipher_str.startswith("fallback:"):
            return FallbackVault.decrypt(cipher_str[len("fallback:"):])
        # Direct attempt if legacy or un-prefixed
        try:
            return WindowsDPAPI.decrypt(cipher_str)
        except Exception:
            return FallbackVault.decrypt(cipher_str)

    def _load_vault(self) -> None:
        """Load encrypted secrets dictionary from vault file."""
        with self._lock:
            if not self.vault_path.exists():
                self._cached_secrets = {}
                return
            try:
                with open(self.vault_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._cached_secrets = data
                    else:
                        self._cached_secrets = {}
            except Exception as e:
                logger.error("Failed to read TMDB credential vault: %s", e)
                self._cached_secrets = {}

    def _save_vault(self) -> bool:
        """Persist encrypted secrets dictionary to vault file atomically."""
        try:
            self.vault_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.vault_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._cached_secrets, f, indent=2)

            for attempt in range(3):
                try:
                    temp_path.replace(self.vault_path)
                    break
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(0.05)
            return True
        except Exception as e:
            logger.error("Failed to write TMDB credential vault: %s", e)
            return False

    def validate_key_against_tmdb(self, api_key: str) -> Tuple[bool, str, int]:
        """Validate candidate key against TMDB API without logging the key."""
        clean = (api_key or "").strip()
        if not clean:
            return False, "API key cannot be empty.", 400

        headers = {
            "Accept": "application/json",
            "User-Agent": "AIDesktopFriend-MovieHub/2.0",
        }
        params: Dict[str, Any] = {}

        if clean.startswith("ey") or len(clean) > 40:
            headers["Authorization"] = f"Bearer {clean}"
        else:
            params["api_key"] = clean

        try:
            # Check authentication endpoint
            resp = requests.get(
                TMDB_AUTH_URL,
                headers=headers,
                params=params,
                timeout=8.0,
            )
            if resp.status_code == 200:
                return True, "Successfully connected and verified with TMDB API.", 200
            elif resp.status_code == 401:
                return False, "Authentication failed: Invalid TMDB API key (HTTP 401).", 401
            elif resp.status_code == 404:
                # Fallback to configuration endpoint
                cfg_resp = requests.get(
                    TMDB_CONFIG_URL,
                    headers=headers,
                    params=params,
                    timeout=8.0,
                )
                if cfg_resp.status_code == 200:
                    return True, "Successfully verified with TMDB configuration endpoint.", 200
                return False, f"TMDB returned error status {cfg_resp.status_code}.", cfg_resp.status_code
            else:
                return False, f"TMDB verification returned status {resp.status_code}.", resp.status_code
        except requests.Timeout:
            return False, "Connection to TMDB timed out. Please check your internet connection.", 504
        except requests.RequestException as e:
            return False, f"Network error connecting to TMDB: {e}", 503

    def get_env_fallback_key(self) -> str:
        """Get the initial fallback key from .env without mutating .env."""
        return os.environ.get("TMDB_API_KEY", "").strip()

    def get_active_api_key(self) -> Tuple[str, str, str]:
        """Return (active_key, source, active_key_id).

        Source is 'custom', 'env', or 'none'.
        """
        active_id = "env"
        if self.config_manager:
            active_id = self.config_manager.get("movies.tmdb_active_key_id", "env")

        # 1. Custom Key from vault
        if active_id and active_id != "env":
            with self._lock:
                cipher = self._cached_secrets.get(active_id)
            if cipher:
                try:
                    decrypted = self._decrypt(cipher)
                    if decrypted:
                        return decrypted, "custom", active_id
                except Exception as e:
                    logger.warning("Failed to decrypt active key %s, falling back to env: %s", active_id, e)

        # 2. Initial Fallback from environment
        env_key = self.get_env_fallback_key()
        if env_key:
            return env_key, "env", "env"

        return "", "none", ""

    def get_key_status(self) -> Dict[str, Any]:
        """Return full non-sensitive status and history for UI."""
        active_key, source, active_id = self.get_active_api_key()
        env_key = self.get_env_fallback_key()

        history_items: List[Dict[str, Any]] = []
        if self.config_manager:
            raw_history = self.config_manager.get("movies.tmdb_key_history", [])
            if isinstance(raw_history, list):
                for item in raw_history:
                    if isinstance(item, dict) and "id" in item:
                        item_id = item["id"]
                        is_active = (item_id == active_id)
                        history_items.append({
                            "id": item_id,
                            "masked_key": item.get("masked_key", "••••"),
                            "label": item.get("label", f"Key ending in {item.get('masked_key', '')[-4:]}"),
                            "source": "custom",
                            "created_at": item.get("created_at", ""),
                            "last_used_at": item.get("last_used_at", ""),
                            "is_active": is_active,
                        })

        return {
            "configured": bool(active_key),
            "source": source,
            "active_key_id": active_id,
            "masked_key": mask_api_key(active_key) if active_key else "",
            "has_env_fallback": bool(env_key),
            "env_masked_key": mask_api_key(env_key) if env_key else "",
            "history": history_items,
        }

    def save_and_activate_key(
        self,
        api_key: str,
        label: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Validate, encrypt, save to history, and activate candidate key."""
        clean = (api_key or "").strip()
        if not clean:
            return False, "API key cannot be empty.", self.get_key_status()

        # Step 1: Validate against TMDB
        valid, msg, code = self.validate_key_against_tmdb(clean)
        if not valid:
            logger.warning("Attempted to save invalid TMDB API key: %s (code %d)", msg, code)
            return False, msg, self.get_key_status()

        # Step 2: Avoid duplicates by checking fingerprint
        fingerprint = _hash_fingerprint(clean)
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        masked = mask_api_key(clean)
        key_label = label.strip() if (label and label.strip()) else f"Key (ends with {clean[-4:]})"

        with self._lock:
            existing_history: List[Dict[str, Any]] = []
            if self.config_manager:
                existing_history = list(self.config_manager.get("movies.tmdb_key_history", []))

            # Look for duplicate fingerprint
            matched_id: Optional[str] = None
            for item in existing_history:
                if item.get("fingerprint") == fingerprint:
                    matched_id = item["id"]
                    item["last_used_at"] = now_iso
                    if label and label.strip():
                        item["label"] = label.strip()
                    break

            if matched_id:
                target_id = matched_id
            else:
                target_id = f"tmdb_{uuid.uuid4().hex[:8]}"
                # Store encrypted in vault
                self._cached_secrets[target_id] = self._encrypt(clean)
                self._save_vault()

                existing_history.append({
                    "id": target_id,
                    "masked_key": masked,
                    "fingerprint": fingerprint,
                    "label": key_label,
                    "created_at": now_iso,
                    "last_used_at": now_iso,
                })

            if self.config_manager:
                self.config_manager.set("movies.tmdb_key_history", existing_history)
                self.config_manager.set("movies.tmdb_active_key_id", target_id)
                self.config_manager.save()

        logger.info("Activated new TMDB API key with ID: %s (masked: %s)", target_id, masked)
        return True, "TMDB API key successfully validated and activated.", self.get_key_status()

    def activate_key_by_id(self, key_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Switch active key to an existing history key or 'env' fallback."""
        if not key_id:
            return False, "Target key ID is required.", self.get_key_status()

        if key_id == "env":
            env_key = self.get_env_fallback_key()
            if not env_key:
                return False, "No fallback TMDB_API_KEY found in .env.", self.get_key_status()

            if self.config_manager:
                self.config_manager.set("movies.tmdb_active_key_id", "env")
                self.config_manager.save()
            return True, "Switched to .env fallback API key.", self.get_key_status()

        # Custom key lookup
        with self._lock:
            cipher = self._cached_secrets.get(key_id)
            if not cipher:
                return False, f"Key ID '{key_id}' not found in secure storage.", self.get_key_status()
            try:
                decrypted = self._decrypt(cipher)
            except Exception as e:
                return False, f"Failed to decrypt key: {e}", self.get_key_status()

        # Validate with TMDB before activating
        valid, msg, _ = self.validate_key_against_tmdb(decrypted)
        if not valid:
            return False, f"Stored key failed validation: {msg}", self.get_key_status()

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if self.config_manager:
            history = list(self.config_manager.get("movies.tmdb_key_history", []))
            for item in history:
                if item.get("id") == key_id:
                    item["last_used_at"] = now_iso
                    break
            self.config_manager.set("movies.tmdb_key_history", history)
            self.config_manager.set("movies.tmdb_active_key_id", key_id)
            self.config_manager.save()

        return True, "Key activated successfully.", self.get_key_status()

    def delete_key_by_id(self, key_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Remove a saved key from secure storage and history."""
        if key_id == "env":
            return False, "Cannot delete the system .env fallback key.", self.get_key_status()

        with self._lock:
            if key_id in self._cached_secrets:
                del self._cached_secrets[key_id]
                self._save_vault()

            if self.config_manager:
                history = list(self.config_manager.get("movies.tmdb_key_history", []))
                history = [item for item in history if item.get("id") != key_id]
                self.config_manager.set("movies.tmdb_key_history", history)

                current_active = self.config_manager.get("movies.tmdb_active_key_id")
                if current_active == key_id:
                    # Fall back to first available custom key or 'env'
                    if history:
                        self.config_manager.set("movies.tmdb_active_key_id", history[0]["id"])
                    else:
                        self.config_manager.set("movies.tmdb_active_key_id", "env")
                self.config_manager.save()

        return True, "Key removed from history.", self.get_key_status()

