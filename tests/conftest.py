"""Pytest fixtures and configuration."""

from pathlib import Path
import shutil
import uuid

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp_instance():
    """Ensure a QApplication instance exists throughout the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def tmp_path():
    """Custom tmp_path fixture that avoids Windows symlink permission errors in sandbox."""
    scratch = Path("tests/_test_scratch")
    scratch.mkdir(exist_ok=True)
    d = scratch / f"test_run_{uuid.uuid4().hex[:12]}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        yield d
    finally:
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass
