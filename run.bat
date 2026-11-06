@echo off
title AI Desktop Friend
cd /d "%~dp0"
if not exist ".\.venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment python not found at .\.venv\Scripts\python.exe
    pause
    exit /b 1
)
".\.venv\Scripts\python.exe" "run_desktop.py" %*
