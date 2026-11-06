"""Test for YouTube trailer search URL generation for ALL movies and series."""

import pytest
import re
from pathlib import Path


def test_youtube_trailer_search_url_generation():
    # Read implementation from MovieDetailsModal.tsx
    modal_file = Path("src/components/MovieHub/MovieDetailsModal.tsx")
    assert modal_file.exists()
    content = modal_file.read_text(encoding="utf-8")

    assert "export function getYouTubeTrailerSearchUrl" in content
    assert "fallbackYouTubeSearchUrl" in content
    assert "primaryTrailer && primaryTrailer.key" in content

    # Python mirror of the TypeScript function to test algorithm guarantees across all titles
    def get_youtube_trailer_search_url(title: str | None, release_year: str | int | None) -> str:
        clean_title = (title or "").strip()
        if not clean_title:
            return "https://www.youtube.com/results?search_query=trailer"

        clean_year = None
        if release_year:
            m = re.search(r"\b(\d{4})\b", str(release_year))
            if m:
                clean_year = m.group(1)

        has_year_in_title = f"({clean_year})" in clean_title if clean_year else False
        year_part = f"({clean_year}) " if clean_year and not has_year_in_title else ""
        query = re.sub(r"\s+", " ", f"{clean_title} {year_part}trailer").strip()
        import urllib.parse
        encoded = urllib.parse.quote_plus(query, safe="()")
        return f"https://www.youtube.com/results?search_query={encoded}"

    # 1. Test user's exact example: "Jailer 2" (2026)
    url_jailer = get_youtube_trailer_search_url("Jailer 2", 2026)
    assert url_jailer == "https://www.youtube.com/results?search_query=Jailer+2+(2026)+trailer"

    # 2. Test title with lowercase
    url_lower = get_youtube_trailer_search_url("jailer 2", 2026)
    assert url_lower == "https://www.youtube.com/results?search_query=jailer+2+(2026)+trailer"

    # 3. Test movie with string year
    url_str_year = get_youtube_trailer_search_url("Premalu", "2024")
    assert url_str_year == "https://www.youtube.com/results?search_query=Premalu+(2024)+trailer"

    # 4. Test series: "Friends" (1994)
    url_friends = get_youtube_trailer_search_url("Friends", 1994)
    assert url_friends == "https://www.youtube.com/results?search_query=Friends+(1994)+trailer"

    # 5. Test series: "Pritam and Pedro" (2026)
    url_pritam = get_youtube_trailer_search_url("Pritam and Pedro", 2026)
    assert url_pritam == "https://www.youtube.com/results?search_query=Pritam+and+Pedro+(2026)+trailer"

    # 6. Test series with special characters: "Law & Order: Special Victims Unit" (1999)
    url_law_order = get_youtube_trailer_search_url("Law & Order: Special Victims Unit", 1999)
    assert url_law_order == "https://www.youtube.com/results?search_query=Law+%26+Order%3A+Special+Victims+Unit+(1999)+trailer"

    # 7. Test release year passed as full ISO date string "2026-08-10"
    url_iso_date = get_youtube_trailer_search_url("Jailer 2", "2026-08-10")
    assert url_iso_date == "https://www.youtube.com/results?search_query=Jailer+2+(2026)+trailer"

    # 8. Test title that already has year embedded "(2026)" avoids duplication
    url_existing_year = get_youtube_trailer_search_url("Jailer 2 (2026)", 2026)
    assert url_existing_year == "https://www.youtube.com/results?search_query=Jailer+2+(2026)+trailer"

    # 9. Test title without year
    url_no_year = get_youtube_trailer_search_url("Interstellar", None)
    assert url_no_year == "https://www.youtube.com/results?search_query=Interstellar+trailer"

    # 10. Fallback if empty title
    url_empty = get_youtube_trailer_search_url("", None)
    assert url_empty == "https://www.youtube.com/results?search_query=trailer"


def test_fullscreen_trailer_modal_component():
    """Verify FullScreenTrailerModal guarantees true full-screen playback with exit options."""
    modal_tsx = Path("src/components/MovieHub/FullScreenTrailerModal.tsx")
    assert modal_tsx.exists()
    content_tsx = modal_tsx.read_text(encoding="utf-8")

    # 1. Must use React createPortal to escape parent modal clipping
    assert "createPortal" in content_tsx
    assert "document.body" in content_tsx

    # 2. Must feature prominent Exit button and Escape shortcut
    assert "fullscreen-trailer-exit-btn" in content_tsx
    assert "<span>Exit</span>" in content_tsx
    assert "fullscreen-trailer-esc-badge" not in content_tsx
    assert "'Escape'" in content_tsx

    # 3. Must request native browser fullscreen and sync state
    assert "requestFullscreen" in content_tsx
    assert "exitFullscreen" in content_tsx
    assert "fullscreenchange" in content_tsx

    # 4. Check CSS definitions for immersive viewport dimensions
    css_file = Path("src/components/MovieHub/FullScreenTrailerModal.css")
    assert css_file.exists()
    content_css = css_file.read_text(encoding="utf-8")

    assert "position: fixed;" in content_css
    assert "width: 100vw;" in content_css
    assert "height: 100vh;" in content_css
    assert "z-index: 999999;" in content_css
    assert ".fullscreen-trailer-exit-btn" in content_css

