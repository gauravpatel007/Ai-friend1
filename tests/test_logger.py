"""Tests for Logger and Privacy Filter."""

import logging
from pathlib import Path

from app.utils.logger import get_logger, setup_logging


def test_logger_setup_and_file_creation(tmp_path: Path):
    """Test setting up logger creates app.log in the specified directory."""
    log_file = setup_logging(log_dir=tmp_path, log_level=logging.DEBUG, console_output=False)
    assert log_file.exists()

    logger = get_logger("test_module")
    test_msg = "Diagnostic test message 12345"
    logger.info(test_msg)

    # Force flush handlers
    for handler in logging.getLogger().handlers:
        handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert test_msg in content


def test_privacy_filter_redacts_sensitive_fields(tmp_path: Path):
    """Test that privacy filter redacts user speech or sensitive tokens."""
    log_file = setup_logging(log_dir=tmp_path, log_level=logging.INFO, console_output=False)
    logger = get_logger("privacy_test")

    sensitive_msg = '{"user_speech": "Secret private conversation contents"}'
    logger.info(sensitive_msg)

    for handler in logging.getLogger().handlers:
        handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "Secret private conversation contents" not in content
    assert "[REDACTED CONTENT" in content
