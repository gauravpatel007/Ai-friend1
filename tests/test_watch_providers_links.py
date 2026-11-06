"""Unit and integration tests for Where to Watch streaming search URLs.

Verifies:
1. Exact JioHotstar URL formatting for user-reported cases:
   - "Dhurandhar: The Revenge" -> "Dhurandhar The Revenge" (no colons, no pluses: %20)
   - "Pirates of the Caribbean: The Curse of the Black Pearl" -> (no colons, no pluses: %20)
   - "Law & Order: Special Victims Unit" -> (no colons, no pluses: %20)
2. Title replacement for Netflix, Amazon Prime Video, Apple TV, YouTube, Zee5, SonyLIV, JioCinema.
3. Fallback search resolution for unlisted or indie providers.
4. User custom template overrides and persistent saving.
5. Reverting custom templates back to system defaults.
6. FastAPI endpoints /api/movies/watch-providers/templates, /resolve, and /reset.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.watch_providers_manager import WatchProvidersManager, clean_title_for_search
from app.api.server import create_app


@pytest.fixture
def temp_manager(tmp_path: Path) -> WatchProvidersManager:
    config_file = tmp_path / "test_watch_providers.json"
    return WatchProvidersManager(config_path=config_file)


@pytest.fixture
def test_client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_clean_title_for_search_helper():
    """Verify that colons and search-breaking punctuation are cleanly stripped or converted to space."""
    assert clean_title_for_search("Dhurandhar: The Revenge") == "Dhurandhar The Revenge"
    assert clean_title_for_search("Pirates of the Caribbean: The Curse of the Black Pearl") == "Pirates of the Caribbean The Curse of the Black Pearl"
    assert clean_title_for_search("Law & Order: Special Victims Unit") == "Law & Order Special Victims Unit"
    assert clean_title_for_search('Mission: Impossible - Dead Reckoning "Part One"!') == "Mission Impossible - Dead Reckoning Part One"


def test_dhurandhar_the_revenge_hotstar_url(temp_manager: WatchProvidersManager):
    """Verify exact URL for 'Dhurandhar: The Revenge' matches user request with NO pluses and clean title."""
    title = "Dhurandhar: The Revenge"
    resolved = temp_manager.resolve_url("JioHotstar", title)
    expected = "https://www.hotstar.com/in/explore?search_query=Dhurandhar%20The%20Revenge"
    assert resolved == expected
    assert "+" not in resolved
    assert "%2B" not in resolved
    assert ":" not in resolved.split("?search_query=")[1]

    # Also verify if title was already plus-separated or pre-encoded, it still resolves cleanly to %20 without %2B
    resolved_plus = temp_manager.resolve_url("JioHotstar", "Dhurandhar+The+Revenge")
    assert resolved_plus == expected
    assert "+" not in resolved_plus
    assert "%2B" not in resolved_plus

    resolved_encoded = temp_manager.resolve_url("JioHotstar", "Dhurandhar%2BThe%2BRevenge")
    assert resolved_encoded == expected
    assert "+" not in resolved_encoded
    assert "%2B" not in resolved_encoded


def test_pirates_of_caribbean_hotstar_url(temp_manager: WatchProvidersManager):
    """Verify 'Pirates of the Caribbean: The Curse of the Black Pearl' has NO pluses in title."""
    title = "Pirates of the Caribbean: The Curse of the Black Pearl"
    resolved = temp_manager.resolve_url("Hotstar", title)
    expected = "https://www.hotstar.com/in/explore?search_query=Pirates%20of%20the%20Caribbean%20The%20Curse%20of%20the%20Black%20Pearl"
    assert resolved == expected
    assert "+" not in resolved


def test_law_and_order_hotstar_url(temp_manager: WatchProvidersManager):
    """Verify 'Law & Order: Special Victims Unit' produces %20 for spaces and preserves &."""
    title = "Law & Order: Special Victims Unit"
    resolved = temp_manager.resolve_url("JioHotstar", title)
    expected = "https://www.hotstar.com/in/explore?search_query=Law%20%26%20Order%20Special%20Victims%20Unit"
    assert resolved == expected
    assert "+" not in resolved


def test_netflix_url_generation(temp_manager: WatchProvidersManager):
    """Verify Netflix search URL format with proper title encoding."""
    movie_title = "Dhurandhar: The Revenge"
    resolved = temp_manager.resolve_url("Netflix", movie_title)
    assert resolved == "https://www.netflix.com/search?q=Dhurandhar%20The%20Revenge"
    assert "+" not in resolved


def test_amazon_prime_video_url_generation(temp_manager: WatchProvidersManager):
    """Verify Amazon Prime Video search URL format with clean standard encoding."""
    movie_title = "Pirates of the Caribbean: The Curse of the Black Pearl"
    resolved = temp_manager.resolve_url("Amazon Prime Video", movie_title)
    assert resolved == "https://www.primevideo.com/search/ref=atv_nb_sr?phrase=Pirates%20of%20the%20Caribbean%20The%20Curse%20of%20the%20Black%20Pearl"
    assert "+" not in resolved


def test_apple_tv_url_generation(temp_manager: WatchProvidersManager):
    """Verify Apple TV / iTunes search URL format."""
    movie_title = "Dhurandhar: The Revenge"
    for name in ["Apple TV", "Apple TV+", "Apple TV Plus"]:
        resolved = temp_manager.resolve_url(name, movie_title)
        assert resolved == "https://tv.apple.com/search?term=Dhurandhar%20The%20Revenge"


def test_youtube_url_generation(temp_manager: WatchProvidersManager):
    """Verify YouTube Movies search URL format."""
    movie_title = "Inception: The Beginning"
    resolved = temp_manager.resolve_url("YouTube", movie_title)
    assert resolved == "https://www.youtube.com/results?search_query=Inception%20The%20Beginning"


def test_jiocinema_url_generation(temp_manager: WatchProvidersManager):
    """Verify JioCinema search URL format."""
    movie_title = "Stree 2: Sarkate Ka Aatank"
    resolved = temp_manager.resolve_url("JioCinema", movie_title)
    assert resolved == "https://www.jiocinema.com/search/Stree%202%20Sarkate%20Ka%20Aatank"


def test_zee5_and_sonyliv_url_generation(temp_manager: WatchProvidersManager):
    """Verify Zee5 and SonyLIV search URLs."""
    title = "Gullak: Season 4"
    resolved_zee = temp_manager.resolve_url("ZEE5", title)
    assert resolved_zee == "https://www.zee5.com/search?q=Gullak%20Season%204"

    resolved_sony = temp_manager.resolve_url("SonyLIV", title)
    assert resolved_sony == "https://www.sonyliv.com/search/Gullak%20Season%204"


def test_universal_fallback_for_unknown_provider(temp_manager: WatchProvidersManager):
    """Verify unknown providers fall back cleanly to a Google search for that provider."""
    resolved = temp_manager.resolve_url("IndieFilmVault", "Premalu")
    assert "google.com/search?q=watch%20Premalu%20on%20IndieFilmVault" in resolved or "google.com/search?q=watch+Premalu+on+IndieFilmVault" in resolved


def test_custom_template_override_and_persistence(temp_manager: WatchProvidersManager, tmp_path: Path):
    """Verify updating a template overrides defaults and persists to disk."""
    custom_tmpl = "https://custom.hotstar.local/search?keyword={title}&src=test"
    temp_manager.update_template("hotstar", custom_tmpl)

    resolved = temp_manager.resolve_url("Hotstar", "Premalu: Love Story")
    assert resolved == "https://custom.hotstar.local/search?keyword=Premalu%20Love%20Story&src=test"

    # Reload in a new manager instance from the same file
    manager_reloaded = WatchProvidersManager(config_path=temp_manager.config_path)
    resolved_reloaded = manager_reloaded.resolve_url("JioHotstar", "Premalu: Love Story")
    assert resolved_reloaded == "https://custom.hotstar.local/search?keyword=Premalu%20Love%20Story&src=test"

    # Reset to defaults
    temp_manager.reset_to_defaults()
    resolved_after_reset = temp_manager.resolve_url("Hotstar", "Dhurandhar: The Revenge")
    assert resolved_after_reset == "https://www.hotstar.com/in/explore?search_query=Dhurandhar%20The%20Revenge"


def test_api_endpoints_templates_and_resolve(test_client: TestClient):
    """Verify /api/movies/watch-providers/templates and /resolve endpoints."""
    # 1. Fetch templates
    res = test_client.get("/api/movies/watch-providers/templates?sample_title=Inception")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    assert len(data["providers"]) >= 20

    hotstar_item = next(p for p in data["providers"] if p["key"] == "hotstar")
    assert hotstar_item["label"] == "JioHotstar / Hotstar"
    assert "search_query=" in hotstar_item["template"]
    assert "Inception" in hotstar_item["sample_preview"]

    # 2. Resolve endpoint for JioHotstar with colon title
    res_resolve = test_client.get(
        "/api/movies/watch-providers/resolve?provider=JioHotstar&title=Dhurandhar%3A+The+Revenge"
    )
    assert res_resolve.status_code == 200
    resolve_data = res_resolve.json()
    assert resolve_data["url"] == "https://www.hotstar.com/in/explore?search_query=Dhurandhar%20The%20Revenge"
    assert "+" not in resolve_data["url"]

    # 3. Resolve endpoint for Netflix
    res_netflix = test_client.get(
        "/api/movies/watch-providers/resolve?provider=Netflix&title=Stranger+Things%3A+Chapter+One"
    )
    assert res_netflix.status_code == 200
    assert "netflix.com/search?q=Stranger%20Things%20Chapter%20One" in res_netflix.json()["url"]


def test_apostrophe_and_indian_language_encoding(temp_manager: WatchProvidersManager):
    """Verify apostrophe preservation (Grey's Anatomy) and Indian language Unicode encoding."""
    # 1. Apostrophe preservation
    greys = temp_manager.resolve_url("Hotstar", "Grey's Anatomy")
    assert greys == "https://www.hotstar.com/in/explore?search_query=Grey's%20Anatomy" or greys == "https://www.hotstar.com/in/explore?search_query=Grey%27s%20Anatomy"
    assert "+" not in greys

    # 2. Hindi / Devanagari Unicode
    hindi = temp_manager.resolve_url("Hotstar", "धुरंधर: द रिवेंज")
    assert "%E0%A4%A7%E0%A5%81%E0%A4%B0%E0%A4%82%E0%A4%A7%E0%A4%B0" in hindi
    assert "%20" in hindi
    assert "+" not in hindi

    # 3. Telugu Unicode
    telugu = temp_manager.resolve_url("Netflix", "పుష్ప 2: ది రూల్")
    assert "%E0%B0%AA%E0%B1%81%E0%B0%B7%E0%B1%8D%E0%B0%AA" in telugu
    assert "%20" in telugu
    assert "+" not in telugu


def test_all_23_platforms_space_encoding(temp_manager: WatchProvidersManager):
    """Verify that every single supported platform encodes spaces as %20 with no '+' in the title param."""
    sample_movies = [
        "Dhurandhar: The Revenge",
        "Pirates of the Caribbean: The Curse of the Black Pearl",
        "Spider-Man: No Way Home",
        "Law & Order: Special Victims Unit",
    ]
    all_defs = temp_manager.get_all_templates()
    assert len(all_defs) >= 20

    for defn in all_defs:
        key = defn["key"]
        for movie in sample_movies:
            resolved = temp_manager.resolve_url(key, movie)
            assert "%2B" not in resolved
            # Verify the query string has %20 for spaces
            parsed_query = resolved.split("?", 1)[1] if "?" in resolved else resolved.split(".com/", 1)[1]
            assert "Dhurandhar+The" not in parsed_query
            assert "Pirates+of" not in parsed_query
            assert "Spider-Man+No" not in parsed_query
            assert "Law+&" not in parsed_query

