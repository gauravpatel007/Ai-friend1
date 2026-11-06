"""Application Logging and Error Handling.

Provides centralized, rotating log files with privacy-preserving filters.
Logs are stored in the Windows application data directory by default.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
from typing import Optional

from platformdirs import user_log_dir

APP_NAME = "AIDesktopFriend"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
DEFAULT_BACKUP_COUNT = 3


class PrivacyFilter(logging.Filter):
    """Filter that prevents accidental leaking of private conversation or raw audio.
    
    Ensures that conversation logs or sensitive tokens do not get persisted in clear text.
    """

    SENSITIVE_KEYS = ("user_speech", "transcript_raw", "prompt_text", "api_key", "password")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        # Basic check to avoid dumping raw user speech into disk logs
        for key in self.SENSITIVE_KEYS:
            if f'"{key}"' in message or f"'{key}'" in message:
                record.msg = f"[REDACTED CONTENT - Contains sensitive field '{key}']"
                record.args = ()
                break
        return True


def get_default_log_dir() -> Path:
    """Return the platform-specific log directory."""
    try:
        log_dir = Path(user_log_dir(appname=APP_NAME, appauthor=APP_NAME))
    except Exception:
        log_dir = Path.home() / ".ai_desktop_friend" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(
    log_dir: Optional[Path | str] = None,
    log_level: int = logging.INFO,
    console_output: bool = True,
) -> Path:
    """Configure root and application loggers with rotating file and console handlers.

    Args:
        log_dir: Optional custom log directory. Defaults to Windows user log dir.
        log_level: Minimum logging level.
        console_output: Whether to also stream logs to standard output.

    Returns:
        Path to the primary log file.
    """
    if log_dir is None:
        target_dir = get_default_log_dir()
    else:
        target_dir = Path(log_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

    log_file_path = target_dir / "app.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler
    file_handler = RotatingFileHandler(
        filename=str(log_file_path),
        maxBytes=DEFAULT_MAX_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(PrivacyFilter())
    root_logger.addHandler(file_handler)

    # Console handler
    if console_output:
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(PrivacyFilter())
        root_logger.addHandler(console_handler)

    # Hook unhandled exceptions to logger
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        root_logger.critical("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    root_logger.info("Application logging initialized. Log file: %s", log_file_path)
    return log_file_path


def get_logger(name: str) -> logging.Logger:
    """Retrieve a namespaced logger."""
    return logging.getLogger(name)
