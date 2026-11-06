"""Performance Monitor.

Tracks real-time system and process resource consumption, model latencies,
speech recognition durations, TTS synthesis latencies, and audio queue depths.
Optimized for resource-constrained systems (e.g. 8 GB RAM).
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import os
import threading
import time
from typing import Any, Deque, Dict, List, Optional

import psutil
from PySide6.QtCore import QObject, QTimer, Signal

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Constants
LOW_RAM_THRESHOLD_BYTES = 8.5 * (1024 ** 3)  # <= 8.5 GB is considered an 8GB or lower system
HIGH_RAM_WARNING_PERCENT = 94.0
HIGH_CPU_WARNING_PERCENT = 92.0
METRICS_HISTORY_LENGTH = 30


@dataclass
class PerformanceSnapshot:
    """Snapshot of current system and application performance metrics."""
    timestamp: float
    process_cpu_percent: float
    system_cpu_percent: float
    process_rss_mb: float
    process_vms_mb: float
    process_ram_percent: float
    system_total_ram_gb: float
    system_available_ram_gb: float
    system_ram_percent: float
    audio_queue_length: int = 0
    avg_ai_latency_sec: float = 0.0
    last_ai_first_token_sec: float = 0.0
    avg_stt_duration_sec: float = 0.0
    avg_tts_duration_sec: float = 0.0
    last_model_load_sec: float = 0.0
    is_low_ram_system: bool = False

    @property
    def cpu_percent(self) -> float:
        return self.process_cpu_percent

    @property
    def ram_used_bytes(self) -> int:
        return int(self.process_rss_mb * 1024 * 1024)

    @property
    def ram_total_bytes(self) -> int:
        return int(self.system_total_ram_gb * 1024 * 1024 * 1024)

    @property
    def ram_percent(self) -> float:
        return self.system_ram_percent

    @property
    def process_rss_bytes(self) -> int:
        return int(self.process_rss_mb * 1024 * 1024)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["cpu_percent"] = self.cpu_percent
        d["ram_used_bytes"] = self.ram_used_bytes
        d["ram_total_bytes"] = self.ram_total_bytes
        d["ram_percent"] = self.ram_percent
        d["process_rss_bytes"] = self.process_rss_bytes
        return d


class PerformanceMonitor(QObject):
    """Monitors process and system performance, latency, and resource limits."""

    # Emitted when periodic metrics are updated
    metrics_updated = Signal(dict)
    # Emitted when resource usage exceeds safety threshold: (resource_name, current_val)
    high_resource_warning = Signal(str, float)

    _instance: Optional["PerformanceMonitor"] = None

    def __init__(self, sample_interval_ms: int = 3000, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.sample_interval_ms = sample_interval_ms
        self._lock = threading.Lock()

        # Initialize process handle
        try:
            self._process = psutil.Process(os.getpid())
            # Initialize CPU percent measurement
            self._process.cpu_percent(interval=None)
        except Exception as e:
            logger.warning("Could not obtain current psutil Process: %s", e)
            self._process = None

        # Total system physical RAM in bytes
        try:
            self.total_physical_ram_bytes = psutil.virtual_memory().total
        except Exception:
            self.total_physical_ram_bytes = 8 * (1024 ** 3)

        self._is_low_ram = self.total_physical_ram_bytes <= LOW_RAM_THRESHOLD_BYTES
        if self._is_low_ram:
            logger.info(
                "PerformanceMonitor: Detected low-memory system (%.2f GB RAM). Eco/Balanced optimizations recommended.",
                self.total_physical_ram_bytes / (1024 ** 3),
            )

        # Metric trackers
        self._audio_queue_length = 0
        self._ai_latencies: Deque[float] = deque(maxlen=METRICS_HISTORY_LENGTH)
        self._ai_first_token_latencies: Deque[float] = deque(maxlen=METRICS_HISTORY_LENGTH)
        self._stt_durations: Deque[float] = deque(maxlen=METRICS_HISTORY_LENGTH)
        self._tts_durations: Deque[float] = deque(maxlen=METRICS_HISTORY_LENGTH)
        self._model_load_times: Dict[str, float] = {}
        self._last_model_load_sec: float = 0.0
        self._last_ram_warning_time: float = 0.0
        self._last_cpu_warning_time: float = 0.0

        # Periodic timer for metric sampling
        self._timer = QTimer(self)
        self._timer.setInterval(self.sample_interval_ms)
        self._timer.timeout.connect(self._on_sample_timer)

    @classmethod
    def get_instance(cls) -> "PerformanceMonitor":
        """Access singleton monitor instance."""
        if cls._instance is None:
            cls._instance = PerformanceMonitor()
        return cls._instance

    def start_monitoring(self, interval_ms: Optional[int] = None) -> None:
        """Start periodic sampling timer."""
        if interval_ms:
            self.sample_interval_ms = interval_ms
            self._timer.setInterval(interval_ms)
        if not self._timer.isActive():
            self._timer.start()
            logger.debug("Performance monitoring timer started (interval: %dms).", self.sample_interval_ms)

    def stop_monitoring(self) -> None:
        """Stop periodic sampling timer."""
        if self._timer.isActive():
            self._timer.stop()
            logger.debug("Performance monitoring timer stopped.")

    # -------------------------------------------------------------------------
    # Hardware & System Checks
    # -------------------------------------------------------------------------

    @property
    def is_low_ram_system(self) -> bool:
        """Check if machine has 8 GB or less physical RAM."""
        return self._is_low_ram

    def get_total_ram_gb(self) -> float:
        """Total installed physical RAM in Gigabytes."""
        return round(self.total_physical_ram_bytes / (1024 ** 3), 2)

    # -------------------------------------------------------------------------
    # Latency & Duration Recording Methods
    # -------------------------------------------------------------------------

    def record_model_load_time(self, model_name: str, duration_sec: float) -> None:
        """Record model initialization/loading duration."""
        with self._lock:
            self._model_load_times[model_name] = duration_sec
            self._last_model_load_sec = duration_sec
        logger.info("Performance: Model '%s' load time: %.2fs", model_name, duration_sec)

    def record_ai_latency(self, first_token_sec: float, total_sec: float, tokens: int = 0) -> None:
        """Record AI response generation latency."""
        with self._lock:
            self._ai_first_token_latencies.append(first_token_sec)
            self._ai_latencies.append(total_sec)
        logger.debug(
            "Performance: AI response latency - first_token: %.2fs, total: %.2fs (tokens: %d)",
            first_token_sec,
            total_sec,
            tokens,
        )

    def record_stt_duration(self, duration_sec: float, audio_len_sec: float = 0.0) -> None:
        """Record Whisper STT speech recognition duration."""
        with self._lock:
            self._stt_durations.append(duration_sec)
        logger.debug(
            "Performance: STT duration: %.2fs (audio len: %.2fs, RTF: %.2f)",
            duration_sec,
            audio_len_sec,
            (duration_sec / audio_len_sec) if audio_len_sec > 0 else 0.0,
        )

    def record_tts_duration(self, engine_or_duration: Any, duration_sec: Optional[float] = None, char_count: int = 0) -> None:
        """Record Piper/Kokoro TTS synthesis duration."""
        if isinstance(engine_or_duration, (int, float)):
            dur = float(engine_or_duration)
            engine_name = "default"
        else:
            engine_name = str(engine_or_duration)
            dur = float(duration_sec or 0.0)

        with self._lock:
            self._tts_durations.append(dur)
        logger.debug(
            "Performance: TTS (%s) duration: %.2fs for %d chars",
            engine_name,
            dur,
            char_count,
        )

    def update_audio_queue_length(self, length: int) -> None:
        """Update current depth of the audio streaming playback queue."""
        with self._lock:
            self._audio_queue_length = max(0, int(length))

    def record_audio_queue_length(self, length: int) -> None:
        """Alias for update_audio_queue_length."""
        self.update_audio_queue_length(length)

    def clear_history(self) -> None:
        """Reset historical latency and duration queues."""
        with self._lock:
            self._ai_latencies.clear()
            self._ai_first_token_latencies.clear()
            self._stt_durations.clear()
            self._tts_durations.clear()
            self._model_load_times.clear()
            self._audio_queue_length = 0

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Return aggregated summary metrics for testing and logging."""
        with self._lock:
            ai_lat_list = list(self._ai_latencies)
            first_tok_list = list(self._ai_first_token_latencies)
            stt_list = list(self._stt_durations)
            tts_list = list(self._tts_durations)
            return {
                "ai_latency": {
                    "count": len(ai_lat_list),
                    "avg_first_token_sec": sum(first_tok_list) / len(first_tok_list) if first_tok_list else 0.0,
                    "avg_total_sec": sum(ai_lat_list) / len(ai_lat_list) if ai_lat_list else 0.0,
                },
                "stt_duration": {
                    "count": len(stt_list),
                    "avg_sec": sum(stt_list) / len(stt_list) if stt_list else 0.0,
                },
                "tts_duration": {
                    "count": len(tts_list),
                    "avg_sec": sum(tts_list) / len(tts_list) if tts_list else 0.0,
                },
                "model_load_times": dict(self._model_load_times),
                "audio_queue_depth": {
                    "latest": self._audio_queue_length,
                },
            }

    def get_system_snapshot(self) -> PerformanceSnapshot:
        """Alias for get_snapshot()."""
        return self.get_snapshot()

    # -------------------------------------------------------------------------
    # Metric Extraction & Snapshots
    # -------------------------------------------------------------------------

    def get_snapshot(self) -> PerformanceSnapshot:
        """Capture and return current instantaneous performance snapshot."""
        now = time.time()
        proc_cpu = 0.0
        proc_rss_mb = 0.0
        proc_vms_mb = 0.0
        proc_ram_pct = 0.0

        if self._process:
            try:
                proc_cpu = self._process.cpu_percent(interval=None)
                mem_info = self._process.memory_info()
                proc_rss_mb = round(mem_info.rss / (1024 * 1024), 2)
                proc_vms_mb = round(mem_info.vms / (1024 * 1024), 2)
                proc_ram_pct = round(self._process.memory_percent(), 2)
            except Exception:
                pass

        sys_cpu = 0.0
        sys_tot_gb = 0.0
        sys_avail_gb = 0.0
        sys_ram_pct = 0.0

        try:
            sys_cpu = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            sys_tot_gb = round(vm.total / (1024 ** 3), 2)
            sys_avail_gb = round(vm.available / (1024 ** 3), 2)
            sys_ram_pct = round(vm.percent, 2)
        except Exception:
            pass

        with self._lock:
            q_len = self._audio_queue_length
            avg_ai = round(sum(self._ai_latencies) / len(self._ai_latencies), 3) if self._ai_latencies else 0.0
            last_first_tok = self._ai_first_token_latencies[-1] if self._ai_first_token_latencies else 0.0
            avg_stt = round(sum(self._stt_durations) / len(self._stt_durations), 3) if self._stt_durations else 0.0
            avg_tts = round(sum(self._tts_durations) / len(self._tts_durations), 3) if self._tts_durations else 0.0
            last_load = self._last_model_load_sec

        return PerformanceSnapshot(
            timestamp=now,
            process_cpu_percent=proc_cpu,
            system_cpu_percent=sys_cpu,
            process_rss_mb=proc_rss_mb,
            process_vms_mb=proc_vms_mb,
            process_ram_percent=proc_ram_pct,
            system_total_ram_gb=sys_tot_gb,
            system_available_ram_gb=sys_avail_gb,
            system_ram_percent=sys_ram_pct,
            audio_queue_length=q_len,
            avg_ai_latency_sec=avg_ai,
            last_ai_first_token_sec=last_first_tok,
            avg_stt_duration_sec=avg_stt,
            avg_tts_duration_sec=avg_tts,
            last_model_load_sec=last_load,
            is_low_ram_system=(sys_tot_gb * (1024 ** 3)) <= LOW_RAM_THRESHOLD_BYTES if sys_tot_gb > 0 else self._is_low_ram,
        )

    def _on_sample_timer(self) -> None:
        """Periodic sampling callback to emit metrics and check thresholds."""
        snapshot = self.get_snapshot()
        data = snapshot.to_dict()
        self.metrics_updated.emit(data)

        now = time.monotonic()
        # High resource safety warnings (rate-limited to avoid log flooding)
        if snapshot.system_ram_percent >= HIGH_RAM_WARNING_PERCENT:
            if now - self._last_ram_warning_time > 60.0:
                self._last_ram_warning_time = now
                logger.warning(
                    "System RAM high: %.1f%% total in use across machine (App RSS: %.1f MB).",
                    snapshot.system_ram_percent,
                    snapshot.process_rss_mb,
                )
                self.high_resource_warning.emit("system_ram", snapshot.system_ram_percent)

        cpu_cores = psutil.cpu_count() or 1
        normalized_cpu_pct = snapshot.process_cpu_percent / cpu_cores

        if normalized_cpu_pct >= HIGH_CPU_WARNING_PERCENT:
            if now - self._last_cpu_warning_time > 30.0:
                self._last_cpu_warning_time = now
                logger.warning("Process CPU usage high: %.1f%% (normalized: %.1f%% across %d cores)",
                               snapshot.process_cpu_percent, normalized_cpu_pct, cpu_cores)
                self.high_resource_warning.emit("process_cpu", snapshot.process_cpu_percent)


def get_performance_monitor() -> PerformanceMonitor:
    """Helper to access singleton PerformanceMonitor."""
    return PerformanceMonitor.get_instance()
