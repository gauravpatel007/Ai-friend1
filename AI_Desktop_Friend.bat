@echo off
title AI Desktop Friend
cd /d "%~dp0"
if "%~1"=="" (
    ".\.venv\Scripts\python.exe" "run_desktop.py" --keep-terminal
) else (
    ".\.venv\Scripts\python.exe" "run_desktop.py" %*
)
