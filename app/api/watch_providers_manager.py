"""Where to Watch - Streaming Provider Search URL Manager.

Manages customizable search URL templates for streaming and VOD platforms
(JioHotstar, Netflix, Amazon Prime Video, Apple TV, YouTube, Zee5, SonyLIV, etc.),
performs dynamic title substitution for movies and TV series, and provides persistence.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, quote_plus
from platformdirs import user_data_dir

from app.utils.logger import get_logger

logger = get_logger(__name__)

APP_NAME = "AIDesktopFriend"
CONFIG_FILENAME = "watch_providers_config.json"


def clean_title_for_search(title: Optional[str]) -> str:
    """Clean title for streaming service search queries.
    
    Removes colons, plus signs, pre-encodings, and search-cluttering punctuation,
    while preserving apostrophes, hyphens, ampersands, acronyms, and Indian-language Unicode:
    - 'Dhurandhar: The Revenge' -> 'Dhurandhar The Revenge'
    - 'Dhurandhar+The+Revenge' -> 'Dhurandhar The Revenge'
    - 'Pirates of the Caribbean: The Curse of the Black Pearl' -> 'Pirates of the Caribbean The Curse of the Black Pearl'
    - 'Grey\'s Anatomy' -> 'Grey\'s Anatomy'
    - 'Spider-Man: No Way Home' -> 'Spider-Man No Way Home'
    - 'Law & Order: Special Victims Unit' -> 'Law & Order Special Victims Unit'
    - 'धुरंधर: द रिवेंज' -> 'धुरंधर द रिवेंज'
    """
    raw = (title or "").strip()
    if not raw:
        return ""
    # 1. If string is already URL-encoded, safely decode first to prevent double-encoding
    try:
        if "%" in raw:
            from urllib.parse import unquote
            raw = unquote(raw)
    except Exception:
        pass

    # 2. Replace pluses and colons with clean spaces
    t = re.sub(r"[:+]", " ", raw)

    # 3. Remove quotation marks, exclamation, semicolons, question marks,
    # while preserving apostrophes (e.g. Grey's Anatomy), hyphens (e.g. Spider-Man),
    # ampersands (e.g. Law & Order), dots (e.g. K.G.F.), and all Unicode letters
    t = re.sub(r'["“”?!;]', "", t)

    # 4. Collapse multiple whitespace into a single clean space
    t = re.sub(r"\s+", " ", t).strip()
    return t or raw


# Default search URL templates for all major streaming & digital rental platforms
DEFAULT_PROVIDER_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "key": "hotstar",
        "label": "JioHotstar / Hotstar",
        "aliases": ["hotstar", "disney+ hotstar", "disney plus hotstar", "jiohotstar", "jio hotstar"],
        "template": "https://www.hotstar.com/in/explore?search_query={title}",
        "url_encoding": "standard",  # Standard %20 encoding ensures no '+' leak into Hotstar search input
        "description": "Primary streaming provider for Disney+, HBO, and Star network content in India.",
    },
    {
        "key": "netflix",
        "label": "Netflix",
        "aliases": ["netflix", "netflix basic with ads"],
        "template": "https://www.netflix.com/search?q={title}",
        "url_encoding": "standard",
        "description": "Global streaming platform for films, series, and original productions.",
    },
    {
        "key": "primevideo",
        "label": "Amazon Prime Video",
        "aliases": ["prime video", "amazon prime video", "amazon video"],
        "template": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={title}",
        "url_encoding": "standard",
        "description": "Amazon Prime Video movies, series, and video rentals/purchases.",
    },
    {
        "key": "jiocinema",
        "label": "JioCinema",
        "aliases": ["jiocinema", "jio cinema"],
        "template": "https://www.jiocinema.com/search/{title}",
        "url_encoding": "standard",
        "description": "JioCinema entertainment, HBO, Warner Bros, and Indian regional cinema.",
    },
    {
        "key": "appletv",
        "label": "Apple TV / iTunes",
        "aliases": ["apple tv", "apple tv plus", "apple tv+", "itunes"],
        "template": "https://tv.apple.com/search?term={title}",
        "url_encoding": "standard",
        "description": "Apple TV+ originals and 4K HDR digital movie rentals and purchases.",
    },
    {
        "key": "googleplay",
        "label": "Google Play Movies / TV",
        "aliases": ["google play movies", "google play", "google tv"],
        "template": "https://play.google.com/store/search?q={title}&c=movies",
        "url_encoding": "standard",
        "description": "Google Play and Google TV digital film store.",
    },
    {
        "key": "youtube",
        "label": "YouTube Movies & Rentals",
        "aliases": ["youtube", "youtube premium"],
        "template": "https://www.youtube.com/results?search_query={title}",
        "url_encoding": "standard",
        "description": "YouTube Movies rental, purchase, and ad-supported library.",
    },
    {
        "key": "zee5",
        "label": "ZEE5",
        "aliases": ["zee5", "zee"],
        "template": "https://www.zee5.com/search?q={title}",
        "url_encoding": "standard",
        "description": "ZEE5 Indian movies, web series, and regional entertainment.",
    },
    {
        "key": "sonyliv",
        "label": "SonyLIV",
        "aliases": ["sonyliv", "sony liv"],
        "template": "https://www.sonyliv.com/search/{title}",
        "url_encoding": "standard",
        "description": "SonyLIV premium streaming, originals, and Sony Pictures catalog.",
    },
    {
        "key": "aha",
        "label": "Aha Video",
        "aliases": ["aha", "aha video"],
        "template": "https://www.aha.video/search?q={title}",
        "url_encoding": "standard",
        "description": "100% Telugu and Tamil cinema and original entertainment.",
    },
    {
        "key": "lionsgateplay",
        "label": "Lionsgate Play",
        "aliases": ["lionsgate play", "lionsgate plus", "lionsgate"],
        "template": "https://www.lionsgateplay.com/search?q={title}",
        "url_encoding": "standard",
        "description": "Hollywood blockbusters and Starz/Lionsgate original series.",
    },
    {
        "key": "sunnxt",
        "label": "Sun NXT",
        "aliases": ["sun nxt", "sunnxt"],
        "template": "https://www.sunnxt.com/search?q={title}",
        "url_encoding": "standard",
        "description": "South Indian regional movies and TV entertainment across 6 languages.",
    },
    {
        "key": "discoveryplus",
        "label": "Discovery+",
        "aliases": ["discovery+", "discovery plus", "discovery"],
        "template": "https://www.discoveryplus.in/search?q={title}",
        "url_encoding": "standard",
        "description": "Discovery, Animal Planet, TLC, and factual documentary streaming.",
    },
    {
        "key": "crunchyroll",
        "label": "Crunchyroll",
        "aliases": ["crunchyroll"],
        "template": "https://www.crunchyroll.com/search?q={title}",
        "url_encoding": "standard",
        "description": "Global anime streaming and Asian cinema catalog.",
    },
    {
        "key": "hulu",
        "label": "Hulu",
        "aliases": ["hulu"],
        "template": "https://www.hulu.com/search?q={title}",
        "url_encoding": "standard",
        "description": "Hulu originals, FX on Hulu, and network television.",
    },
    {
        "key": "max",
        "label": "Max (HBO)",
        "aliases": ["max", "hbo max", "hbo"],
        "template": "https://www.max.com/search?q={title}",
        "url_encoding": "standard",
        "description": "Warner Bros, HBO, DC Universe, and Max original content.",
    },
    {
        "key": "paramountplus",
        "label": "Paramount+",
        "aliases": ["paramount+", "paramount plus", "paramount"],
        "template": "https://www.paramountplus.com/search/?q={title}",
        "url_encoding": "standard",
        "description": "Paramount Pictures, CBS, Showtime, and Star Trek universe.",
    },
    {
        "key": "peacock",
        "label": "Peacock",
        "aliases": ["peacock", "peacock premium"],
        "template": "https://www.peacocktv.com/search?q={title}",
        "url_encoding": "standard",
        "description": "NBCUniversal, Peacock Originals, and Universal Pictures streaming.",
    },
    {
        "key": "bookmyshow",
        "label": "BookMyShow Stream",
        "aliases": ["bookmyshow", "bookmyshow stream"],
        "template": "https://in.bookmyshow.com/explore/movies?q={title}",
        "url_encoding": "standard",
        "description": "BookMyShow transaction VOD rental and buy platform in India.",
    },
    {
        "key": "mxplayer",
        "label": "MX Player",
        "aliases": ["mx player", "mxplayer"],
        "template": "https://www.mxplayer.in/search?q={title}",
        "url_encoding": "standard",
        "description": "Ad-supported movies, web shows, and regional content.",
    },
    {
        "key": "hoichoi",
        "label": "Hoichoi",
        "aliases": ["hoichoi"],
        "template": "https://www.hoichoi.tv/search?q={title}",
        "url_encoding": "standard",
        "description": "Bengali cinema, series, and entertainment platform.",
    },
    {
        "key": "mubi",
        "label": "MUBI",
        "aliases": ["mubi"],
        "template": "https://mubi.com/search?query={title}",
        "url_encoding": "standard",
        "description": "Curated cinema, festival favorites, and auteur film streaming.",
    },
    {
        "key": "erosnow",
        "label": "Eros Now",
        "aliases": ["eros now", "eros"],
        "template": "https://erosnow.com/search?q={title}",
        "url_encoding": "standard",
        "description": "Bollywood blockbuster films and Hindi music catalog.",
    },
]


def _normalize_name(name: str) -> str:
    """Normalize provider name for robust alias matching."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


class WatchProvidersManager:
    """Thread-safe manager for streaming search URLs and user customizations."""

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        self._lock = threading.RLock()
        if config_path:
            self.config_path = Path(config_path)
        else:
            app_data = Path(user_data_dir(appname=APP_NAME, appauthor=APP_NAME))
            app_data.mkdir(parents=True, exist_ok=True)
            self.config_path = app_data / CONFIG_FILENAME

        # User custom overrides: key -> custom_url_template
        self._custom_templates: Dict[str, str] = {}
        self._load_config()

    def _load_config(self) -> None:
        with self._lock:
            if self.config_path.exists():
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._custom_templates = data.get("custom_templates", {})
                    logger.info("Loaded %d custom watch provider templates", len(self._custom_templates))
                except Exception as e:
                    logger.warning("Failed to parse %s: %s", self.config_path, e)
                    self._custom_templates = {}

    def _save_config(self) -> None:
        with self._lock:
            try:
                payload = {
                    "custom_templates": self._custom_templates,
                }
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
            except Exception as e:
                logger.error("Failed to write watch provider templates: %s", e)

    def find_definition(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """Find matching definition by alias or fuzzy normalized name."""
        norm = _normalize_name(provider_name)
        if not norm:
            return None

        # 1. Exact match on key or aliases
        for defn in DEFAULT_PROVIDER_DEFINITIONS:
            if norm == _normalize_name(defn["key"]):
                return defn
            for alias in defn["aliases"]:
                if norm == _normalize_name(alias):
                    return defn

        # 2. Substring matching (e.g. 'hotstar' in 'disneyplusplushotstar' or 'prime' in 'amazonprime')
        for defn in DEFAULT_PROVIDER_DEFINITIONS:
            key_norm = _normalize_name(defn["key"])
            if key_norm in norm or norm in key_norm:
                return defn

        return None

    def get_template_for_provider(self, provider_name: str) -> Tuple[str, str]:
        """Return (active_template, encoding_type) for a provider."""
        with self._lock:
            defn = self.find_definition(provider_name)
            if defn:
                key = defn["key"]
                encoding = defn.get("url_encoding", "standard")
                if key in self._custom_templates and self._custom_templates[key].strip():
                    return self._custom_templates[key].strip(), encoding
                return defn["template"], encoding

            # Universal Fallback for unlisted/indie providers
            fallback_template = "https://www.google.com/search?q=watch%20{title}%20on%20{provider}"
            return fallback_template, "standard"

    def format_title_for_url(self, title: str, encoding: str = "standard") -> str:
        """Format movie title for URL placement using clean standard %20 encoding.
        
        Cleans colons, plus signs, and breaking punctuation while preserving apostrophes,
        hyphens, and Indian-language titles. Ensures spaces are encoded as %20 so literal
        '+' characters never appear in OTT platform search fields.
        """
        cleaned = clean_title_for_search(title)
        if not cleaned:
            return ""

        # Safe set ensures spaces become %20, '&' becomes '%26', apostrophes and hyphens remain clean
        return quote(cleaned, safe="-._~'()")

    def resolve_url(self, provider_name: str, media_title: str) -> str:
        """Resolve a full search/watch URL for a given provider and movie title."""
        title = (media_title or "").strip()
        if not title:
            title = "Movie"

        template, encoding = self.get_template_for_provider(provider_name)
        formatted_title = self.format_title_for_url(title, encoding)

        resolved = template

        # Replace '{title}' placeholder
        if "{title}" in resolved:
            resolved = resolved.replace("{title}", formatted_title)
        # Also support 'pixels' placeholder for consistency with HDHub4u
        elif "pixels" in resolved:
            resolved = resolved.replace("pixels", formatted_title)
        # Replace '{provider}' placeholder for universal fallback
        if "{provider}" in resolved:
            prov_encoded = quote(provider_name.strip())
            resolved = resolved.replace("{provider}", prov_encoded)

        # If template had no placeholder, append appropriately
        if "{title}" not in template and "pixels" not in template:
            separator = "&" if "?" in resolved else "?"
            resolved = f"{resolved}{separator}q={formatted_title}"

        return resolved

    def get_all_templates(self, sample_title: str = "Law & Order: Special Victims Unit") -> List[Dict[str, Any]]:
        """Return all supported providers with active templates and sample previews."""
        with self._lock:
            result: List[Dict[str, Any]] = []
            for defn in DEFAULT_PROVIDER_DEFINITIONS:
                key = defn["key"]
                is_custom = key in self._custom_templates and bool(self._custom_templates[key].strip())
                active = self._custom_templates.get(key, "").strip() if is_custom else defn["template"]
                
                # Generate live sample preview
                preview = self.resolve_url(defn["label"], sample_title)

                result.append({
                    "key": key,
                    "label": defn["label"],
                    "template": active,
                    "default_template": defn["template"],
                    "is_custom": is_custom,
                    "description": defn["description"],
                    "sample_preview": preview,
                })
            return result

    def update_template(self, key: str, template: Optional[str]) -> bool:
        """Update or clear a custom template for a provider key."""
        with self._lock:
            if not template or template.strip() == "":
                self._custom_templates.pop(key, None)
            else:
                self._custom_templates[key] = template.strip()
            self._save_config()
            return True

    def update_multiple_templates(self, templates_dict: Dict[str, str]) -> Dict[str, Any]:
        """Bulk update custom templates."""
        with self._lock:
            for k, val in templates_dict.items():
                if not val or not val.strip():
                    self._custom_templates.pop(k, None)
                else:
                    self._custom_templates[k] = val.strip()
            self._save_config()
            return {"status": "success", "count": len(self._custom_templates)}

    def reset_to_defaults(self) -> Dict[str, Any]:
        """Reset all templates to initial built-in defaults."""
        with self._lock:
            self._custom_templates.clear()
            self._save_config()
            return {"status": "success", "message": "All provider templates reset to default."}


# Global singleton instance
_watch_providers_manager: Optional[WatchProvidersManager] = None
_manager_lock = threading.Lock()


def get_watch_providers_manager() -> WatchProvidersManager:
    global _watch_providers_manager
    if _watch_providers_manager is None:
        with _manager_lock:
            if _watch_providers_manager is None:
                _watch_providers_manager = WatchProvidersManager()
    return _watch_providers_manager
