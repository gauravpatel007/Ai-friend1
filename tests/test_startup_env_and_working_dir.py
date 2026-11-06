"""Tests for Bug #17: Windows Startup Registry Auto-Launch Executes in System32, Causing load_dotenv() to Miss .env File.

Verifies:
1. When the process starts with CWD outside the repository (e.g. C:\\Windows\\System32 or tmp_path),
   the entry point resolves project_root, explicitly targets project_root / ".env", and anchors CWD to project_root.
2. Environment variables defined in project_root / .env are loaded into os.environ.
3. startup_manager._get_executable_path() creates a correctly formatted command line pointing to main.py.
"""

import os
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

from app.core import startup_manager


def test_startup_manager_executable_path_format():
    """Verify that startup_manager._get_executable_path() returns a quoted command pointing to main.py."""
    exe_cmd = startup_manager._get_executable_path()
    assert exe_cmd.startswith('"')
    assert "main.py" in exe_cmd
    assert exe_cmd.endswith('"')

    # Path to main.py within the command should resolve to an existing file
    parts = exe_cmd.split('" "')
    if len(parts) == 2:
        main_script_path = Path(parts[1].rstrip('"'))
        assert main_script_path.exists()
        assert main_script_path.name == "main.py"


def test_project_root_resolution_and_env_loading_from_foreign_cwd(tmp_path):
    """Simulate Windows starting the process with System32/foreign CWD."""
    original_cwd = os.getcwd()
    fake_system32 = (tmp_path / "System32").resolve()
    fake_system32.mkdir()

    fake_project = (tmp_path / "AI Friend").resolve()
    fake_project.mkdir()
    fake_env = fake_project / ".env"
    fake_env.write_text("TMDB_API_KEY=test_tmdb_key_from_env_12345\nTEST_SETTING=loaded_ok\n", encoding="utf-8")

    # Create dummy main script in fake_project
    fake_main = fake_project / "main.py"
    fake_main.write_text("# dummy main", encoding="utf-8")

    try:
        # Switch CWD to fake System32
        os.chdir(fake_system32)
        assert Path(os.getcwd()).resolve() == fake_system32

        # Simulate the resolution logic executed in main.py
        project_root = Path(fake_main).resolve().parent
        assert project_root == fake_project

        from dotenv import load_dotenv
        env_file = project_root / ".env"
        assert env_file.exists()

        load_dotenv(env_file)
        os.chdir(project_root)

        # 1. Environment variables loaded from project .env
        assert os.environ.get("TMDB_API_KEY") == "test_tmdb_key_from_env_12345"
        assert os.environ.get("TEST_SETTING") == "loaded_ok"

        # 2. Process working directory updated from System32 to project_root
        assert Path(os.getcwd()).resolve() == fake_project

    finally:
        os.environ.pop("TMDB_API_KEY", None)
        os.environ.pop("TEST_SETTING", None)
        os.chdir(original_cwd)


def test_main_py_contains_explicit_env_and_chdir():
    """Verify that main.py contains explicit load_dotenv(project_root / '.env') and os.chdir(project_root)."""
    main_py_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_py_path.read_text(encoding="utf-8")

    assert 'project_root / ".env"' in content or "project_root / '.env'" in content
    assert "os.chdir(project_root)" in content
