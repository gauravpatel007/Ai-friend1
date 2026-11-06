"""Tests for HDHub4uManager domain preservation and query integrity (Bug #22).

Verifies that build_search_url() never corrupts domains or hostnames containing
'pixels' and does not corrupt non-search query parameters containing 'pixels'.
"""

from pathlib import Path
import pytest

from app.api.hdhub4u_manager import HDHub4uManager


@pytest.fixture
def hdhub_mgr(tmp_path: Path) -> HDHub4uManager:
    cfg = tmp_path / "hdhub_test.json"
    return HDHub4uManager(config_path=cfg)


def test_domain_containing_pixels_preserved(hdhub_mgr: HDHub4uManager):
    """Bug #22: Domain with 'pixels' like https://pixels-movie.hdhub4u.com must remain intact."""
    tmpl = "https://pixels-movie.hdhub4u.com/search?q=pixels"
    url = hdhub_mgr.build_search_url("Avengers: Endgame", template=tmpl)
    assert url == "https://pixels-movie.hdhub4u.com/search?q=avengers+endgame"
    assert "pixels-movie.hdhub4u.com" in url


def test_domain_containing_pixels_with_existing_query_param(hdhub_mgr: HDHub4uManager):
    """Bug #22: Domain with 'pixels' and existing query value that is not 'pixels'."""
    tmpl = "https://pixels.hdhub4u.com/search.html?q=avatar"
    url = hdhub_mgr.build_search_url("Premalu", template=tmpl)
    assert url == "https://pixels.hdhub4u.com/search.html?q=premalu"
    assert "pixels.hdhub4u.com" in url


def test_non_search_param_containing_pixels_preserved(hdhub_mgr: HDHub4uManager):
    """Bug #22: Non-search query parameter like category=pixels must not be replaced."""
    tmpl = "https://new10.hdhub4u.cl/search.html?category=pixels&q=pixels"
    url = hdhub_mgr.build_search_url("Premalu", template=tmpl)
    assert url == "https://new10.hdhub4u.cl/search.html?category=pixels&q=premalu"


def test_wordpress_format_with_non_search_param(hdhub_mgr: HDHub4uManager):
    """Bug #22: WordPress ?s= format with non-search param containing pixels."""
    tmpl = "https://ghdhub.org/?ref=pixels_banner&s=pixels"
    url = hdhub_mgr.build_search_url("Dune", template=tmpl)
    assert url == "https://ghdhub.org/?ref=pixels_banner&s=dune"


def test_empty_title_on_pixels_domain(hdhub_mgr: HDHub4uManager):
    """Bug #22: Empty title should strip pixels from query without corrupting domain name."""
    tmpl = "https://pixels-movie.hdhub4u.com/search?q=pixels"
    url = hdhub_mgr.build_search_url("", template=tmpl)
    assert url == "https://pixels-movie.hdhub4u.com/search?q="
    assert "pixels-movie.hdhub4u.com" in url


def test_explicit_placeholder_on_pixels_domain(hdhub_mgr: HDHub4uManager):
    """Bug #22: Placeholder {title} in path/query with domain containing pixels."""
    tmpl = "https://pixels-stream.net/watch/{movie}"
    url = hdhub_mgr.build_search_url("Interstellar", template=tmpl)
    assert url == "https://pixels-stream.net/watch/interstellar"
    assert "pixels-stream.net" in url


def test_bare_domain_containing_pixels(hdhub_mgr: HDHub4uManager):
    """Bug #22: Bare domain containing pixels gets /search.html?q= appended without name alteration."""
    tmpl = "https://pixels-hub.com"
    url = hdhub_mgr.build_search_url("Premalu", template=tmpl)
    assert url == "https://pixels-hub.com/search.html?q=premalu"
    assert "pixels-hub.com" in url


def test_validate_and_test_url_preview_preserves_pixels_domain(hdhub_mgr: HDHub4uManager):
    """Bug #22: validate_and_test_url() generates preview URL without corrupting domain."""
    tmpl = "https://pixels-mirror.org/search.html?q=pixels"
    valid, msg, status_code, preview = hdhub_mgr.validate_and_test_url(tmpl, probe=False)
    assert valid is True
    assert preview == "https://pixels-mirror.org/search.html?q=pixels"
    assert "pixels-mirror.org" in preview
