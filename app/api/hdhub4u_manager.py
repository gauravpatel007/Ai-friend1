"""HDHub4u URL Template and Mirror Manager.

Manages user-configurable search URL templates for HDHub4u, maintains mirror
history, validates URLs, and handles dynamic title substitution where 'pixels'
or query placeholders are replaced with the active movie or series title.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urlparse, urlunparse
import uuid

import requests
from platformdirs import user_data_dir

from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

APP_NAME = "AIDesktopFriend"
CONFIG_FILENAME = "hdhub4u_config.json"
DEFAULT_HDHUB4U_URL = "https://new10.hdhub4u.cl/search.html?q=pixels"
DEFAULT_HDHUB4U_LABEL = "HDHub4u Primary (.cl)"


class HDHub4uManager:
    """Thread-safe manager for HDHub4u search URL templates and history."""

    def __init__(
        self,
        config_path: Optional[Path | str] = None,
        config_manager: Optional[ConfigManager] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._config_manager = config_manager

        if config_path:
            self.config_path = Path(config_path)
        else:
            app_data = Path(user_data_dir(appname=APP_NAME, appauthor=APP_NAME))
            app_data.mkdir(parents=True, exist_ok=True)
            self.config_path = app_data / CONFIG_FILENAME

        self._active_url: str = DEFAULT_HDHUB4U_URL
        self._active_id: str = "default"
        self._history: List[Dict[str, Any]] = []

        self._load_config()

    @staticmethod
    def sanitize_url(url_str: Optional[str]) -> str:
        """Sanitize and normalize user URL input, eliminating duplicate schemes.
        
        Fixes concatenated duplicates like:
        'https://new10.hdhub4u.cl/search.html?q=pixelshttps://new10.hdhub4u.cl/search.html?q=pixels'
        and ensures valid https:// prefix.
        """
        raw = (url_str or "").strip()
        if not raw:
            return DEFAULT_HDHUB4U_URL

        # 1. Detect and heal multiple http:// or https:// prefixes
        matches = list(re.finditer(r"https?://", raw, re.IGNORECASE))
        if len(matches) > 1:
            # Extract the last complete URL occurrence
            raw = raw[matches[-1].start():].strip()

        # 2. Add https:// if scheme is completely missing
        if not re.match(r"^https?://", raw, re.IGNORECASE):
            raw = f"https://{raw.lstrip('/')}"

        # 3. Clean trailing whitespace and extra slashes after query
        raw = raw.strip()
        return raw

    def _load_config(self) -> None:
        """Load saved URL configuration and history from disk with auto-healing."""
        with self._lock:
            needs_heal_save = False
            if self.config_path.exists():
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    raw_active = data.get("active_url", DEFAULT_HDHUB4U_URL)
                    self._active_url = self.sanitize_url(raw_active)
                    if self._active_url != raw_active:
                        needs_heal_save = True

                    self._active_id = data.get("active_id", "default")
                    raw_history = data.get("history", [])
                    clean_history = []
                    for item in raw_history:
                        clean_item = dict(item)
                        orig_tmpl = clean_item.get("url_template", "")
                        clean_tmpl = self.sanitize_url(orig_tmpl)
                        if clean_tmpl != orig_tmpl:
                            clean_item["url_template"] = clean_tmpl
                            needs_heal_save = True
                        clean_history.append(clean_item)
                    self._history = clean_history
                except Exception as ex:
                    logger.error("Failed to read HDHub4u configuration from %s: %s", self.config_path, ex)
                    self._active_url = DEFAULT_HDHUB4U_URL
                    self._active_id = "default"
                    self._history = []
            else:
                self._active_url = DEFAULT_HDHUB4U_URL
                self._active_id = "default"
                self._history = []

            if needs_heal_save:
                self._save_config()

    def _save_config(self) -> None:
        """Persist current configuration and history to disk."""
        try:
            payload = {
                "active_url": self._active_url,
                "active_id": self._active_id,
                "history": self._history,
                "updated_at": time.time(),
            }
            tmp_path = self.config_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            tmp_path.replace(self.config_path)
        except Exception as ex:
            logger.error("Failed to save HDHub4u configuration to %s: %s", self.config_path, ex)

    def get_status(self) -> Dict[str, Any]:
        """Return non-sensitive status, active URL, and mirror history."""
        with self._lock:
            history_copy = copy.deepcopy(self._history)
            for item in history_copy:
                item["is_active"] = (item.get("id") == self._active_id)

            return {
                "active_url": self._active_url,
                "default_url": DEFAULT_HDHUB4U_URL,
                "is_custom": (self._active_url != DEFAULT_HDHUB4U_URL),
                "active_id": self._active_id,
                "history": history_copy,
            }

    @staticmethod
    def format_title_for_query(title: Optional[str]) -> str:
        """Format movie or series title for search queries.
        
        Removes noisy punctuation while preserving clean word boundaries
        e.g. 'Avengers: Endgame' -> 'avengers endgame', 'Premalu' -> 'premalu'.
        """
        if not title:
            return ""
        # Replace punctuation characters with space
        cleaned = re.sub(r"[:\-\–—\(\)\[\]\{\}\'\"!?,.]", " ", title.strip())
        # Collapse multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
        return cleaned or re.sub(r"[^\w\d]", "", title.strip().lower())

    def build_search_url(self, title: Optional[str], template: Optional[str] = None) -> str:
        """Generate final search URL by replacing 'pixels' or query placeholder with title.
        
        Guarantees single valid URL formation without duplicate parameters and preserves
        the scheme and netloc hostname intact even if they contain 'pixels'.
        
        Args:
            title: Movie or series title (e.g. 'Premalu', 'Interstellar').
            template: Optional specific template. If None, uses current active URL.
        """
        candidate_tmpl = template or self._active_url or DEFAULT_HDHUB4U_URL
        tmpl = self.sanitize_url(candidate_tmpl)
        formatted_title = self.format_title_for_query(title)
        encoded_title = quote_plus(formatted_title) if formatted_title else ""

        parsed = urlparse(tmpl)
        scheme = parsed.scheme
        netloc = parsed.netloc
        path = parsed.path
        params = parsed.params
        query = parsed.query
        fragment = parsed.fragment

        if not formatted_title:
            # Strip 'pixels' or placeholder markers only from query and path, preserving domain/netloc
            new_path = re.sub(r"\{query\}|\{title\}|\{movie\}", "", path, flags=re.IGNORECASE)
            new_path = re.sub(r"(?:/|^)pixels(?:\.[a-z]+|/|$)", "/", new_path, flags=re.IGNORECASE)

            new_query = query
            if new_query:
                # If search param (q, s, query, search) exists, strip pixels/placeholders from it
                search_param_match = re.search(r"(^|&)(q|s|query|search)=([^&]*)", new_query, re.IGNORECASE)
                if search_param_match:
                    prefix = search_param_match.group(1)
                    param_name = search_param_match.group(2)
                    param_val = search_param_match.group(3)
                    new_val = re.sub(r"pixels|\{query\}|\{title\}|\{movie\}", "", param_val, flags=re.IGNORECASE)
                    start, end = search_param_match.span()
                    new_query = new_query[:start] + f"{prefix}{param_name}={new_val}" + new_query[end:]
                else:
                    new_query = re.sub(r"pixels|\{query\}|\{title\}|\{movie\}", "", new_query, flags=re.IGNORECASE)

            result = urlunparse((scheme, netloc, new_path, params, new_query, fragment))
            if tmpl.endswith("?") and not result.endswith("?"):
                result = f"{result}?"
            return result

        # 1. Check for explicit template placeholders like {query}, {title}, or {movie} in query or path
        if re.search(r"\{query\}|\{title\}|\{movie\}", query + path, re.IGNORECASE):
            new_path = re.sub(r"\{query\}|\{title\}|\{movie\}", encoded_title, path, flags=re.IGNORECASE)
            new_query = re.sub(r"\{query\}|\{title\}|\{movie\}", encoded_title, query, flags=re.IGNORECASE)
            return urlunparse((scheme, netloc, new_path, params, new_query, fragment))

        # 2. Check query parameters
        if query:
            # Check for standard search param (q, s, query, search)
            search_param_match = re.search(r"(^|&)(q|s|query|search)=([^&]*)", query, re.IGNORECASE)
            if search_param_match:
                prefix = search_param_match.group(1)
                param_name = search_param_match.group(2)
                param_val = search_param_match.group(3)

                # If param value contains 'pixels' (e.g. q=pixels, q=hdhub4u+pixels, q=PIXELS)
                if re.search(r"pixels", param_val, re.IGNORECASE):
                    new_val = re.sub(r"pixels", encoded_title, param_val, flags=re.IGNORECASE)
                else:
                    # Replace the existing search query value (e.g. q=avatar -> q=premalu)
                    new_val = encoded_title

                start, end = search_param_match.span()
                new_query = query[:start] + f"{prefix}{param_name}={new_val}" + query[end:]
                return urlunparse((scheme, netloc, path, params, new_query, fragment))

            # Non-standard search param whose value contains 'pixels' (e.g. &keyword=pixels)
            other_pixel_match = re.search(r"(^|&)([^&=]+)=([^&]*pixels[^&]*)", query, re.IGNORECASE)
            if other_pixel_match:
                prefix = other_pixel_match.group(1)
                param_name = other_pixel_match.group(2)
                param_val = other_pixel_match.group(3)
                new_val = re.sub(r"pixels", encoded_title, param_val, flags=re.IGNORECASE)
                start, end = other_pixel_match.span()
                new_query = query[:start] + f"{prefix}{param_name}={new_val}" + query[end:]
                return urlunparse((scheme, netloc, path, params, new_query, fragment))

            # Query exists but has no search param or pixels value: append &q=...
            sep = "&" if not query.endswith(("&", "?")) else ""
            new_query = f"{query}{sep}q={encoded_title}"
            return urlunparse((scheme, netloc, path, params, new_query, fragment))

        # 3. Path contains 'pixels' keyword (e.g. /search/pixels or /find/pixels)
        if re.search(r"\bpixels\b", path, re.IGNORECASE):
            new_path = re.sub(r"\bpixels\b", encoded_title, path, flags=re.IGNORECASE)
            return urlunparse((scheme, netloc, new_path, params, query, fragment))

        # 4. URL ends with '?'
        if tmpl.endswith("?"):
            return f"{tmpl}q={encoded_title}"

        # 5. Bare domain or path without query parameter
        clean_base = tmpl.rstrip("/")
        if clean_base.endswith(".html") or clean_base.endswith(".php"):
            return f"{clean_base}?q={encoded_title}"
        return f"{clean_base}/search.html?q={encoded_title}"

    def validate_and_test_url(
        self, url_candidate: str, sample_title: str = "Pixels", probe: bool = True
    ) -> Tuple[bool, str, int, str]:
        """Validate URL candidate structure and perform lightweight connectivity probe.
        
        Returns:
            (valid, message, status_code, preview_url)
        """
        raw = (url_candidate or "").strip()
        if not raw:
            return False, "URL cannot be empty.", 400, ""

        # Detect and heal multiple schemes if user pasted doubled URL
        matches = list(re.finditer(r"https?://", raw, re.IGNORECASE))
        if len(matches) > 1:
            raw = raw[matches[-1].start():].strip()

        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https"):
            return False, "URL must start with http:// or https://", 400, ""

        if not parsed.netloc:
            return False, "URL must include a valid domain name (e.g., new10.hdhub4u.cl).", 400, ""

        preview_url = self.build_search_url(sample_title, template=raw)

        if not probe:
            return True, "URL format is valid.", 200, preview_url

        # Attempt low-latency reachability probe (HEAD/GET with 2.0s timeout)
        status_code = 200
        message = "URL format is valid and domain is reachable."
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            probe_url = f"{parsed.scheme}://{parsed.netloc}"
            resp = requests.head(probe_url, headers=headers, timeout=2.0, allow_redirects=True)
            status_code = resp.status_code
            if status_code >= 400:
                resp = requests.get(probe_url, headers=headers, timeout=2.0, stream=True)
                status_code = resp.status_code

            if status_code < 400 or status_code in (403, 401, 429):
                message = f"Connection verified. Host responded with HTTP {status_code}."
            else:
                message = f"Host returned HTTP {status_code}. Saved template will still function if accessible in browser."
        except requests.exceptions.Timeout:
            message = "Connection probe timed out (2s). URL format is valid and will open directly in browser."
            status_code = 200
        except requests.exceptions.RequestException as rex:
            message = f"Network probe notice: {rex}. URL syntax is valid and saved."
            status_code = 200

        return True, message, status_code, preview_url

    def save_and_activate_url(
        self, url_candidate: str, label: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Validate, store in history, and activate a new HDHub4u URL template."""
        clean_url = self.sanitize_url(url_candidate)
        valid, msg, code, preview = self.validate_and_test_url(clean_url, probe=False)
        if not valid:
            return False, msg, self.get_status()

        user_label = (label or "").strip()
        if not user_label:
            parsed = urlparse(clean_url)
            user_label = f"HDHub4u ({parsed.netloc or 'Custom'})"

        with self._lock:
            # Check for existing duplicate by normalized URL
            existing = next(
                (item for item in self._history if item.get("url_template", "").strip().lower() == clean_url.lower()),
                None,
            )

            if existing:
                item_id = existing["id"]
                existing["label"] = user_label or existing.get("label", user_label)
                existing["created_at"] = time.time()
                existing["last_status"] = "valid"
            else:
                item_id = str(uuid.uuid4())[:8]
                new_item = {
                    "id": item_id,
                    "url_template": clean_url,
                    "label": user_label,
                    "created_at": time.time(),
                    "last_status": "valid",
                }
                self._history.insert(0, new_item)

            self._active_url = clean_url
            self._active_id = item_id
            self._save_config()

        logger.info("Saved and activated HDHub4u search template: %s", clean_url)
        return True, "HDHub4u URL saved and activated successfully.", self.get_status()

    def activate_url_by_id(self, item_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Switch active URL to a saved history item or 'default'."""
        with self._lock:
            if item_id == "default":
                self._active_url = DEFAULT_HDHUB4U_URL
                self._active_id = "default"
                self._save_config()
                return True, "Reverted HDHub4u URL to default template.", self.get_status()

            target = next((item for item in self._history if item.get("id") == item_id), None)
            if not target:
                return False, f"History entry with ID '{item_id}' not found.", self.get_status()

            self._active_url = target["url_template"]
            self._active_id = target["id"]
            self._save_config()

        logger.info("Activated HDHub4u URL: %s", self._active_url)
        return True, f"Activated '{target['label']}'.", self.get_status()

    def delete_history_item(self, item_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Remove a saved URL entry from history."""
        with self._lock:
            initial_count = len(self._history)
            self._history = [item for item in self._history if item.get("id") != item_id]
            if len(self._history) == initial_count:
                return False, f"History entry '{item_id}' not found.", self.get_status()

            # If active item was deleted, fallback to default
            if self._active_id == item_id:
                self._active_url = DEFAULT_HDHUB4U_URL
                self._active_id = "default"

            self._save_config()

        return True, "Removed HDHub4u URL from history.", self.get_status()

    def reset_to_default(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Reset active URL to original default."""
        return self.activate_url_by_id("default")
