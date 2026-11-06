"""Ollama runtime dependency manager and installer utility for Windows."""

import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable, Dict, List, Optional
import urllib.error
import urllib.request
import webbrowser

logger = logging.getLogger(__name__)

OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_WEBSITE_URL = "https://ollama.com"

# Common Windows install locations for Ollama
KNOWN_WINDOWS_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
    Path(os.environ.get("PROGRAMFILES", "")) / "Ollama" / "ollama.exe",
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Ollama" / "ollama.exe",
]


class OllamaRuntimeManager:
    """Manages Ollama detection, daemon lifecycle, model verification and pulling."""

    def __init__(self, host: str = OLLAMA_DEFAULT_HOST):
        self.host = host.rstrip("/")

    def get_executable_path(self) -> Optional[Path]:
        """Locate the Ollama executable on the system."""
        # 1. Check system PATH
        which_path = shutil.which("ollama")
        if which_path:
            return Path(which_path)

        # 2. Check standard Windows installation directories
        if sys.platform == "win32":
            for path in KNOWN_WINDOWS_PATHS:
                try:
                    if path.exists() and path.is_file():
                        return path
                except Exception:
                    continue

        return None

    def is_installed(self) -> bool:
        """Check if Ollama executable is found on the local machine."""
        return self.get_executable_path() is not None

    def is_running(self, timeout: float = 2.0) -> bool:
        """Check if Ollama daemon is active and responding to HTTP requests."""
        endpoint = f"{self.host}/api/version"
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(endpoint, headers={"User-Agent": "AIDesktopFriend/0.1.0"})
            with opener.open(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            # Fallback check against /api/tags
            try:
                tags_endpoint = f"{self.host}/api/tags"
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                req = urllib.request.Request(tags_endpoint, headers={"User-Agent": "AIDesktopFriend/0.1.0"})
                with opener.open(req, timeout=timeout) as resp:
                    return resp.status == 200
            except Exception:
                return False

    def start_service(self) -> bool:
        """Attempt to launch Ollama daemon in the background."""
        if self.is_running():
            logger.info("Ollama is already running.")
            return True

        exe = self.get_executable_path()
        if not exe:
            logger.warning("Cannot start Ollama: executable not found.")
            return False

        try:
            logger.info("Starting Ollama service from: %s", exe)
            creation_flags = 0
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creation_flags = (
                    subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                )

            subprocess.Popen(
                [str(exe), "serve"],
                creationflags=creation_flags,
                startupinfo=startupinfo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            logger.error("Failed to start Ollama daemon: %s", e)
            return False

    def list_installed_models(self, timeout: float = 3.0) -> List[str]:
        """Query Ollama for a list of locally installed model names."""
        endpoint = f"{self.host}/api/tags"
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(endpoint, headers={"User-Agent": "AIDesktopFriend/0.1.0"})
            with opener.open(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                names = []
                for m in models:
                    name = m.get("name", "")
                    if name:
                        names.append(name)
                return names
        except Exception as e:
            logger.debug("Failed to list installed models: %s", e)
            return []

    def is_model_available(self, model_name: str) -> bool:
        """Check if the given model is downloaded and ready for use."""
        models = self.list_installed_models()
        clean_target = model_name.strip().lower()
        target_base = clean_target.split(":")[0]

        for m in models:
            m_lower = m.lower()
            if m_lower == clean_target:
                return True
            if m_lower.startswith(f"{clean_target}:"):
                return True
            if clean_target.endswith(":latest") and m_lower == target_base:
                return True
            if ":" not in clean_target and m_lower.startswith(f"{clean_target}:"):
                return True

        return False

    def pull_model_stream(
        self,
        model_name: str,
        progress_callback: Optional[Callable[[Dict], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Pull a model from Ollama registry with streaming progress updates.
        
        Args:
            model_name: Name of model (e.g. 'qwen3:1.7b' or 'qwen2.5:1.5b')
            progress_callback: Called with parsed JSON dict for each line from Ollama
            cancel_check: Optional callable returning True if pull should be aborted
            
        Returns:
            True if pull completed successfully, False otherwise.
        """
        endpoint = f"{self.host}/api/pull"
        payload = json.dumps({"name": model_name, "stream": True}).encode("utf-8")

        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(
                endpoint,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "AIDesktopFriend/0.1.0"},
                method="POST",
            )
            with opener.open(req, timeout=300) as resp:
                for line in resp:
                    if cancel_check and cancel_check():
                        logger.info("Model pull cancelled by user.")
                        return False
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8").strip())
                        if progress_callback:
                            progress_callback(chunk)
                        if chunk.get("status") == "success":
                            return True
                    except Exception:
                        continue
            return self.is_model_available(model_name)
        except Exception as e:
            logger.error("Error pulling model %s: %s", model_name, e)
            return False

    @staticmethod
    def open_download_page():
        """Open official Ollama download page in default browser."""
        webbrowser.open(OLLAMA_DOWNLOAD_URL)
