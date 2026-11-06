"""Unit tests for PerformanceMonitor (Phase 11.1)."""

import time
from unittest.mock import MagicMock, patch

import pytest
from app.core.performance_monitor import PerformanceMonitor, get_performance_monitor


def test_performance_monitor_singleton(qapp_instance):
    mon1 = get_performance_monitor()
    mon2 = get_performance_monitor()
    assert mon1 is mon2


def test_system_snapshot_structure(qapp_instance):
    monitor = PerformanceMonitor()
    snapshot = monitor.get_system_snapshot()

    assert hasattr(snapshot, "timestamp")
    assert hasattr(snapshot, "cpu_percent")
    assert hasattr(snapshot, "ram_used_bytes")
    assert hasattr(snapshot, "ram_total_bytes")
    assert hasattr(snapshot, "ram_percent")
    assert hasattr(snapshot, "process_rss_bytes")
    assert hasattr(snapshot, "is_low_ram_system")

    # Basic physical sanity checks
    assert snapshot.ram_total_bytes > 0
    assert snapshot.process_rss_bytes > 0
    assert 0.0 <= snapshot.ram_percent <= 100.0


def test_latency_tracking(qapp_instance):
    monitor = PerformanceMonitor()
    monitor.clear_history()

    # Track AI latency
    monitor.record_ai_latency(first_token_sec=0.25, total_sec=1.10)
    # Track STT duration
    monitor.record_stt_duration(0.35)
    # Track TTS duration
    monitor.record_tts_duration(0.18)
    # Track model load time
    monitor.record_model_load_time("test_model", 1.85)
    # Track audio queue length
    monitor.record_audio_queue_length(3)

    metrics = monitor.get_summary_metrics()

    assert metrics["ai_latency"]["count"] == 1
    assert metrics["ai_latency"]["avg_first_token_sec"] == pytest.approx(0.25, rel=1e-2)
    assert metrics["ai_latency"]["avg_total_sec"] == pytest.approx(1.10, rel=1e-2)

    assert metrics["stt_duration"]["count"] == 1
    assert metrics["stt_duration"]["avg_sec"] == pytest.approx(0.35, rel=1e-2)

    assert metrics["tts_duration"]["count"] == 1
    assert metrics["tts_duration"]["avg_sec"] == pytest.approx(0.18, rel=1e-2)

    assert "test_model" in metrics["model_load_times"]
    assert metrics["model_load_times"]["test_model"] == pytest.approx(1.85, rel=1e-2)

    assert metrics["audio_queue_depth"]["latest"] == 3


def test_low_ram_system_detection(qapp_instance):
    monitor = PerformanceMonitor()

    # Mock total RAM to 7.8 GB (typical 8 GB laptop with integrated GPU sharing)
    with patch("psutil.virtual_memory") as mock_vm:
        mock_vm.return_value = MagicMock(
            total=int(7.8 * 1024 ** 3),
            available=int(2.0 * 1024 ** 3),
            percent=74.3,
            used=int(5.8 * 1024 ** 3),
        )
        snapshot = monitor.get_system_snapshot()
        assert snapshot.is_low_ram_system is True

    # Mock total RAM to 16 GB
    with patch("psutil.virtual_memory") as mock_vm:
        mock_vm.return_value = MagicMock(
            total=int(16.0 * 1024 ** 3),
            available=int(8.0 * 1024 ** 3),
            percent=50.0,
            used=int(8.0 * 1024 ** 3),
        )
        snapshot = monitor.get_system_snapshot()
        assert snapshot.is_low_ram_system is False


def test_monitoring_timer_start_stop(qapp_instance):
    monitor = PerformanceMonitor()
    assert not monitor._timer.isActive()

    monitor.start_monitoring(interval_ms=100)
    assert monitor._timer.isActive()

    monitor.stop_monitoring()
    assert not monitor._timer.isActive()
