@echo off
title AI Desktop Friend - Backend Daemon
cd /d "%~dp0"
echo Starting AI Desktop Friend Backend Daemon on http://127.0.0.1:8765 ...
".\.venv\Scripts\python.exe" main_api.py

