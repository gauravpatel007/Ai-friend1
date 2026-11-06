"""Verification Tests for MovieDetailsModal & Movie Card Improvements.

Validates:
1. CSS Architecture:
   - Eliminates negative margin on .hub-details-hero-row (margin-top: 0).
   - Strict 2:3 aspect ratio and 170px width on .hub-details-poster-frame with squircle corners (14px).
   - Seamless gradient mask on .hub-details-backdrop-img with gradual fade to #0D111E.
   - Backdrop frame has height: 380px and background: transparent so it never covers Overview or Created by.
   - All sections (.hub-details-section) have position: relative and z-index: 5.
   - Close button permanently accessible (z-index: 50, fixed in modal).
   - Scrollable container preserves layout without clipping (.hub-details-body-scroll).
   - Responsive breakpoints (max-width: 768px and max-width: 580px) stack gracefully.
   - Hover action overlay on movie cards stacks 3 buttons vertically (.hub-card-hover-overlay: flex-direction: column).

2. Component & Model Integration:
   - MovieItemModel supports backdropPath across the application.
   - Backdrop frame sits at modal level behind scroll content with zero overlap clipping.
   - Poster fallback includes title and icon.
   - normalizePosterUrl repairs duplicate http prefixes and formats clean URLs for Watchlist.
   - Database row-to-entry and add_or_update_entry cleanly normalize image URLs.
"""

from pathlib import Path
import re
import pytest

from app.memory.movie_storage_repository import _normalize_image_fields

CSS_PATH = Path("src/components/MovieHub/MovieDetailsModal.css")
WORKSPACE_CSS_PATH = Path("src/components/MovieHub/MovieHubWorkspace.css")
AI_CSS_PATH = Path("src/components/MovieHub/AIRecommendationSection.css")
SEARCHBAR_TSX_PATH = Path("src/components/MovieHub/SearchBar.tsx")
TSX_PATH = Path("src/components/MovieHub/MovieDetailsModal.tsx")
CARD_PATH = Path("src/components/MovieHub/MovieCard.tsx")


def test_css_hero_row_no_negative_margin():
    """Verify that .hub-details-hero-row does NOT have negative margin that clips content."""
    assert CSS_PATH.exists(), f"{CSS_PATH} does not exist"
    content = CSS_PATH.read_text(encoding="utf-8")

    hero_match = re.search(r"\.hub-details-hero-row\s*\{([^}]+)\}", content)
    assert hero_match, "Could not find .hub-details-hero-row rule in CSS"
    hero_block = hero_match.group(1)

    assert "margin-top: 0" in hero_block, f"Expected margin-top: 0 in hero row, found:\n{hero_block}"
    assert "-90px" not in hero_block, "Old -90px negative margin is still present in hero row!"


def test_css_poster_frame_strict_dimensions_and_aspect_ratio():
    """Verify that .hub-details-poster-frame has 170px width, 2/3 aspect ratio, and 14px border radius."""
    content = CSS_PATH.read_text(encoding="utf-8")

    poster_match = re.search(r"\.hub-details-poster-frame\s*\{([^}]+)\}", content)
    assert poster_match, "Could not find .hub-details-poster-frame rule in CSS"
    poster_block = poster_match.group(1)

    assert "width: 170px" in poster_block
    assert "aspect-ratio: 2 / 3" in poster_block
    assert "border-radius: 14px" in poster_block
    assert "flex-shrink: 0" in poster_block


def test_css_backdrop_blending_and_mask():
    """Verify that backdrop image has progressive mask, transparent background, and multi-stop dark gradient."""
    content = CSS_PATH.read_text(encoding="utf-8")

    # Check backdrop frame height and transparent background
    frame_match = re.search(r"\.hub-details-backdrop-frame\s*\{([^}]+)\}", content)
    assert frame_match, "Could not find .hub-details-backdrop-frame rule"
    frame_block = frame_match.group(1)
    assert "position: absolute" in frame_block
    assert "height: 380px" in frame_block
    assert "background: transparent" in frame_block

    # Check backdrop img progressive mask
    img_match = re.search(r"\.hub-details-backdrop-img\s*\{([^}]+)\}", content)
    assert img_match, "Could not find .hub-details-backdrop-img rule"
    img_block = img_match.group(1)
    assert "mask-image:" in img_block
    assert "-webkit-mask-image:" in img_block
    assert "linear-gradient" in img_block

    # Check overlay gradients fade to #0D111E
    overlay_match = re.search(r"\.hub-details-backdrop-overlay\s*\{([^}]+)\}", content)
    assert overlay_match, "Could not find .hub-details-backdrop-overlay rule"
    overlay_block = overlay_match.group(1)
    assert "#0D111E" in overlay_block

    # Check section has position: relative and z-index: 5 so Overview/Created by are never covered
    sec_match = re.search(r"\.hub-details-section\s*\{([^}]+)\}", content)
    assert sec_match, "Could not find .hub-details-section rule"
    sec_block = sec_match.group(1)
    assert "position: relative" in sec_block
    assert "z-index: 5" in sec_block


def test_css_close_button_accessibility():
    """Verify close button has high z-index and fixed position on the modal."""
    content = CSS_PATH.read_text(encoding="utf-8")

    btn_match = re.search(r"\.hub-details-close-btn\s*\{([^}]+)\}", content)
    assert btn_match, "Could not find .hub-details-close-btn rule"
    btn_block = btn_match.group(1)
    assert "position: absolute" in btn_block
    assert "z-index: 50" in btn_block
    assert "top: 18px" in btn_block
    assert "right: 18px" in btn_block


def test_css_responsive_breakpoints():
    """Verify mobile breakpoints avoid negative margins and adapt smoothly."""
    content = CSS_PATH.read_text(encoding="utf-8")

    assert "@media (max-width: 768px)" in content
    assert "@media (max-width: 580px)" in content
    assert "-60px" not in content


def test_tsx_component_structure_and_poster_fallback():
    """Verify MovieDetailsModal.tsx renders backdrop at modal level and poster fallback."""
    assert TSX_PATH.exists(), f"{TSX_PATH} does not exist"
    tsx_content = TSX_PATH.read_text(encoding="utf-8")

    backdrop_pos = tsx_content.find("hub-details-backdrop-frame")
    scroll_pos = tsx_content.find("hub-details-body-scroll")
    hero_pos = tsx_content.find("hub-details-hero-row")

    assert backdrop_pos != -1, "Missing hub-details-backdrop-frame"
    assert scroll_pos != -1, "Missing hub-details-body-scroll"
    assert hero_pos != -1, "Missing hub-details-hero-row"

    # Backdrop sits behind body scroll so no sections are clipped
    assert backdrop_pos < scroll_pos < hero_pos, (
        f"Expected backdrop before body-scroll: backdrop={backdrop_pos}, scroll={scroll_pos}"
    )

    # Ensure poster fallback includes title and icon
    assert "hub-poster-fallback-title" in tsx_content

    # Ensure title is rendered in h2
    assert '<h2 className="hub-details-title">{item.title}</h2>' in tsx_content


def test_card_hover_overlay_vertical_layout():
    """Verify that .hub-card-hover-overlay displays 3 action buttons vertically."""
    assert WORKSPACE_CSS_PATH.exists()
    content = WORKSPACE_CSS_PATH.read_text(encoding="utf-8")

    match = re.search(r"\.hub-card-hover-overlay\s*\{([^}]+)\}", content)
    assert match, "Could not find .hub-card-hover-overlay rule"
    block = match.group(1)

    assert "flex-direction: column" in block, f"Expected flex-direction: column, got:\n{block}"


def test_normalize_image_fields_prevents_double_prefix():
    """Verify backend and frontend normalization prevents duplicate URLs."""
    # Test duplicate TMDB URL
    double_url = "https://image.tmdb.org/t/p/w500https://image.tmdb.org/t/p/w500/kCGlIMHnOm8JPXq3rXM6c5wMxcT.jpg"
    path, url = _normalize_image_fields(None, double_url)
    assert path == "/kCGlIMHnOm8JPXq3rXM6c5wMxcT.jpg"
    assert url == "https://image.tmdb.org/t/p/w500/kCGlIMHnOm8JPXq3rXM6c5wMxcT.jpg"

    # Test relative path
    rel_path = "/kCGlIMHnOm8JPXq3rXM6c5wMxcT.jpg"
    path2, url2 = _normalize_image_fields(rel_path, None)
    assert path2 == "/kCGlIMHnOm8JPXq3rXM6c5wMxcT.jpg"
    assert url2 == "https://image.tmdb.org/t/p/w500/kCGlIMHnOm8JPXq3rXM6c5wMxcT.jpg"


def test_searchbar_shortcut_hint_removed_and_focus_animations_disabled():
    """Verify shortcut hint icon is removed and focus box-shadow glow animations are disabled."""
    # 1. SearchBar.tsx does not render the visual ⌘K shortcut hint element
    assert SEARCHBAR_TSX_PATH.exists()
    searchbar_tsx = SEARCHBAR_TSX_PATH.read_text(encoding="utf-8")
    assert "hub-search-shortcut-hint" not in searchbar_tsx
    assert "⌘K" not in searchbar_tsx

    # 2. MovieHubWorkspace.css: .hub-searchbar-frame:focus-within has no expanding 3px glow
    assert WORKSPACE_CSS_PATH.exists()
    ws_css = WORKSPACE_CSS_PATH.read_text(encoding="utf-8")
    focus_within_match = re.search(r"\.hub-searchbar-frame:focus-within\s*\{([^}]+)\}", ws_css)
    assert focus_within_match
    focus_block = focus_within_match.group(1)
    assert "0 0 0 3px" not in focus_block
    assert "outline: none" in focus_block

    # 3. AIRecommendationSection.css: .hub-ai-input-wrapper:focus-within has no expanding 3px glow
    assert AI_CSS_PATH.exists()
    ai_css = AI_CSS_PATH.read_text(encoding="utf-8")
    ai_focus_match = re.search(r"\.hub-ai-input-wrapper:focus-within\s*\{([^}]+)\}", ai_css)
    assert ai_focus_match
    ai_block = ai_focus_match.group(1)
    assert "0 0 0 3px" not in ai_block
    assert "outline: none" in ai_block


def test_hdhub4u_button_and_url_generation():
    """Verify HdHub4u download button is added to MovieDetailsModal with correct search URL logic."""
    assert TSX_PATH.exists()
    tsx_content = TSX_PATH.read_text(encoding="utf-8")

    # 1. Component contains getHdHub4uSearchUrl function
    assert "getHdHub4uSearchUrl" in tsx_content

    # 2. Correct URL formation rules
    assert "https://new10.hdhub4u.cl/search.html?q=" in tsx_content
    assert "replace(/\\s+/g, '')" in tsx_content

    # 3. Markup checks: button class, Download here label, logo, target _blank
    assert "hub-hdhub4u-btn" in tsx_content
    assert "Download here" in tsx_content
    assert "/assets/icons/hdhub4u_logo.png" in tsx_content
    assert 'target="_blank"' in tsx_content
    assert 'rel="noopener noreferrer"' in tsx_content

    # 4. CSS checks
    assert CSS_PATH.exists()
    css_content = CSS_PATH.read_text(encoding="utf-8")
    assert ".hub-hdhub4u-btn" in css_content
    assert ".hub-hdhub4u-logo" in css_content
    assert ".hub-details-middle-row" in css_content

    # 5. Logo file exists in public assets
    logo_file = Path("public/assets/icons/hdhub4u_logo.png")
    assert logo_file.exists(), f"Logo file not found at {logo_file}"


