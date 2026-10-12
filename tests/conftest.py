"""Pytest fixtures and configuration."""

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp_instance():
    """Ensure a QApplication instance exists throughout the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
