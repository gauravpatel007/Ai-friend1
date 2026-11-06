"""Ollama Process Supervisor & Auto-Launcher (Bug 7 Fix).

Automatically discovers, launches, and monitors the local Ollama background
daemon ('ollama serve') so that users can converse with their AI Friend without
having to manually open terminal commands first.
"""

from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


class OllamaSupervisor:
    """Supervises the local Ollama daemon lifecycle."""

    def __init__(self, config_manager: Optional[Any] = None) -> None:
        self.config_manager = config_manager
        self._process: Optional[subprocess.Popen] = None
        self._started_by_supervisor: bool = False
        self._lock = threading.Lock()
        self._custom_exe_path: Optional[Path] = None

        # Register cleanup on exit
        atexit.register(self.stop_server)

    def set_executable_path(self, path: Path | str) -> None:
        """Manually override path to ollama binary."""
        self._custom_exe_path = Path(path)

    def find_ollama_executable(self) -> Optional[Path]:
        """Locate the Ollama executable on the system across common install paths."""
        # 1. Custom configured path in settings
        if self._custom_exe_path and self._custom_exe_path.is_file():
            return self._custom_exe_path

        if self.config_manager:
            try:
                cfg_path = self.config_manager.get("ai.ollama_path", "")
                if cfg_path and Path(cfg_path).is_file():
                    return Path(cfg_path)
            except Exception:
                pass

        # 2. Environment override
        env_path = os.environ.get("OLLAMA_EXE_PATH")
        if env_path and Path(env_path).is_file():
            return Path(env_path)

        # 3. Standard system PATH
        which_ollama = shutil.which("ollama") or shutil.which("ollama.exe")
        if which_ollama:
            return Path(which_ollama)

        # 4. Standard Windows install locations
        if sys.platform == "win32":
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            prog_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            prog_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")

            candidates = [
                Path(local_appdata) / "Programs" / "Ollama" / "ollama.exe" if local_appdata else None,
                Path(local_appdata) / "Programs" / "Ollama" / "ollama app.exe" if local_appdata else None,
                Path(prog_files) / "Ollama" / "ollama.exe",
                Path(prog_files_x86) / "Ollama" / "ollama.exe",
            ]
            for cand in candidates:
                try:
                    if cand and cand.is_file():
                        return cand
                except (PermissionError, OSError):
                    continue

        # 5. Standard POSIX / macOS paths
        else:
            posix_candidates = [
                Path("/usr/local/bin/ollama"),
                Path("/opt/homebrew/bin/ollama"),
                Path("/usr/bin/ollama"),
                Path.home() / ".ollama" / "bin" / "ollama",
            ]
            for cand in posix_candidates:
                try:
                    if cand and cand.is_file():
                        return cand
                except (PermissionError, OSError):
                    continue

        return None

    def is_server_reachable(self, base_url: str = DEFAULT_OLLAMA_HOST, timeout: float = 1.5) -> bool:
        """Check if local Ollama daemon is currently running and responding.

        Probes the ultra-fast root endpoint first (~10ms), falling back to /api/tags.
        """
        clean_base = base_url.rstrip("/")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        # 1. Fast path: root endpoint (Ollama daemon returns 200 "Ollama is running")
        try:
            req_root = urllib.request.Request(f"{clean_base}/", method="GET")
            with opener.open(req_root, timeout=timeout) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass

        # 2. Fallback: /api/tags endpoint
        try:
            req_tags = urllib.request.Request(f"{clean_base}/api/tags", method="GET")
            with opener.open(req_tags, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    @classmethod
    def resolve_ollama_models_dir(cls) -> Optional[str]:
        """Resolve OLLAMA_MODELS directory across environment, Windows Registry, and custom drives."""
        # 1. Direct process environment
        env_val = os.environ.get("OLLAMA_MODELS")
        if env_val and os.path.exists(env_val):
            return env_val

        # 2. Windows Registry (HKCU / HKLM)
        if sys.platform == "win32":
            try:
                import winreg
                for root, subkey in [
                    (winreg.HKEY_CURRENT_USER, r"Environment"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                ]:
                    try:
                        with winreg.OpenKey(root, subkey) as key:
                            val, _ = winreg.QueryValueEx(key, "OLLAMA_MODELS")
                            if val and os.path.exists(val):
                                return str(val)
                    except (FileNotFoundError, OSError):
                        continue
            except Exception:
                pass

        # 3. Known drive search (e.g. F:\.ollama\models, D:\.ollama\models, etc.)
        for drive in ("F:", "D:", "E:", "G:"):
            cand = Path(f"{drive}/.ollama/models")
            if cand.exists():
                return str(cand)

        return None

    def ensure_server_running(
        self,
        base_url: str = DEFAULT_OLLAMA_HOST,
        timeout: float = 8.0,
    ) -> bool:
        """Ensure Ollama daemon is running, auto-spawning it in background if reachable."""
        # 1. Quick probe
        if self.is_server_reachable(base_url, timeout=1.0):
            return True

        # 2. Locate executable
        exe_path = self.find_ollama_executable()
        if not exe_path:
            logger.info("Ollama executable not found on system. Auto-launch cannot proceed.")
            return False

        # 3. Spawn 'ollama serve'
        cmd = [str(exe_path), "serve"]
        models_dir = self.resolve_ollama_models_dir()
        env = os.environ.copy()
        if models_dir:
            env["OLLAMA_MODELS"] = models_dir
            os.environ["OLLAMA_MODELS"] = models_dir
            logger.info("Ollama supervisor configured OLLAMA_MODELS=%s", models_dir)

        kwargs: Dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "env": env,
        }

        if sys.platform == "win32":
            # On Windows, DETACHED_PROCESS (0x00000008) and CREATE_NO_WINDOW (0x08000000)
            # are mutually exclusive Win32 flags. When DETACHED_PROCESS is used, the process
            # has no console, causing Windows conhost.exe to pop open a visible console window
            # for EVERY runner capability probe Ollama executes during discovery (e.g. 10-15
            # ggml-cpu-* and GPU runners flashing on screen).
            # Using CREATE_NO_WINDOW (0x08000000) with SW_HIDE and CREATE_NEW_PROCESS_GROUP
            # guarantees that Ollama and all child probes run completely headless with 0 console windows.
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            )

        with self._lock:
            if self._process is None or self._process.poll() is not None:
                logger.info("🚀 Auto-launching Ollama daemon: '%s serve'", exe_path)
                try:
                    self._process = subprocess.Popen(cmd, **kwargs)
                    self._started_by_supervisor = True
                except Exception as e:
                    logger.error("Failed to auto-spawn Ollama process: %s", e)
                    return False

        # 4. Wait for server to become responsive
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            if self.is_server_reachable(base_url, timeout=0.8):
                logger.info("✅ Ollama background daemon is ready at %s (took %.2fs).", base_url, time.time() - start_time)
                return True
            time.sleep(0.35)

        logger.warning("Ollama daemon spawned but did not respond on %s within %.1fs.", base_url, timeout)
        return False

    def stop_server(self) -> None:
        """Stop Ollama daemon if it was started by this supervisor instance."""
        with self._lock:
            if self._started_by_supervisor and self._process:
                if self._process.poll() is None:
                    logger.info("Shutting down Ollama daemon started by AI Friend...")
                    try:
                        self._process.terminate()
                        self._process.wait(timeout=2.0)
                    except Exception:
                        try:
                            self._process.kill()
                        except Exception:
                            pass
                self._process = None
                self._started_by_supervisor = False

    def get_status(self, base_url: str = DEFAULT_OLLAMA_HOST) -> Dict[str, Any]:
        """Return diagnostic status of Ollama installation and execution."""
        exe = self.find_ollama_executable()
        running = self.is_server_reachable(base_url)
        return {
            "installed": exe is not None,
            "executable_path": str(exe) if exe else None,
            "running": running,
            "managed_by_supervisor": self._started_by_supervisor,
        }
