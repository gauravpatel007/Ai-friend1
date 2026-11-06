"""Unit and integration tests for Model Benchmark Service (Phase 3)."""

from datetime import datetime, timezone
import json
import pytest
from unittest.mock import MagicMock, patch

from app.ai.model_benchmark_service import (
    BenchmarkCategory,
    BenchmarkRecord,
    BenchmarkRepository,
    ModelBenchmarkRunner,
    compute_benchmark_recommendations,
    evaluate_simple_conversation,
    evaluate_general_knowledge,
    evaluate_complex_reasoning,
    evaluate_coding,
    evaluate_document_summarization,
    evaluate_structured_json,
    evaluate_vision,
    get_model_benchmark_runner,
)
from app.ai.model_capability_registry import ModelCapability, ModelCapabilityRegistry, ModelProfile
from app.ai.model_manager import ModelManager
from app.memory.database import DatabaseManager


class TestBenchmarkCategoriesAndRecord:
    """Verify benchmark category enumeration and data serialization."""

    def test_all_seven_categories_present(self):
        expected = {
            "simple_conversation",
            "general_knowledge",
            "complex_reasoning",
            "coding",
            "document_summarization",
            "structured_json",
            "vision",
        }
        actual = {c.value for c in BenchmarkCategory}
        assert expected == actual

    def test_benchmark_record_to_dict_and_from_row(self):
        rec = BenchmarkRecord(
            id=1,
            model_id="llama3.2:3b",
            digest="sha256:123456",
            category="coding",
            run_type="warm",
            ttft_ms=350.5,
            tokens_per_sec=42.8,
            total_duration_ms=1200.0,
            eval_count=52,
            model_load_ms=15.0,
            peak_ram_mb=3200.0,
            peak_gpu_mb=2100.0,
            context_capacity=131072,
            quality_score=1.0,
            quality_details={"tests_passed": 6, "total_tests": 6},
            raw_response="def is_palindrome(s): ...",
            test_outcome="passed",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        d = rec.to_dict()
        assert d["model_id"] == "llama3.2:3b"
        assert d["ttft_ms"] == 350.5
        assert d["quality_score"] == 1.0

        # Mock SQLite row dictionary
        mock_row = {
            "id": 1,
            "model_id": "llama3.2:3b",
            "digest": "sha256:123456",
            "category": "coding",
            "run_type": "warm",
            "ttft_ms": 350.5,
            "tokens_per_sec": 42.8,
            "total_duration_ms": 1200.0,
            "eval_count": 52,
            "model_load_ms": 15.0,
            "peak_ram_mb": 3200.0,
            "peak_gpu_mb": 2100.0,
            "context_capacity": 131072,
            "quality_score": 1.0,
            "quality_details": json.dumps({"tests_passed": 6, "total_tests": 6}),
            "raw_response": "def is_palindrome(s): ...",
            "test_outcome": "passed",
            "created_at": d["created_at"],
        }
        restored = BenchmarkRecord.from_db_row(mock_row)
        assert restored.model_id == "llama3.2:3b"
        assert restored.quality_details["tests_passed"] == 6


class TestObjectiveQualityEvaluators:
    """Verify rigorous, formula-based task quality evaluation."""

    def test_evaluate_simple_conversation(self):
        good = "Hello! I am doing wonderfully today, thank you. How can I help you?"
        score, details = evaluate_simple_conversation(good)
        assert score >= 0.8
        assert details["friendly_token"] is True

        empty_score, _ = evaluate_simple_conversation("")
        assert empty_score == 0.0

    def test_evaluate_general_knowledge(self):
        good = "The speed of light in vacuum is approximately 300,000 km/s, established by Albert Einstein's theory of special relativity."
        score, details = evaluate_general_knowledge(good)
        assert score == 1.0
        assert details["speed_of_light_accurate"] is True
        assert details["theory_of_relativity_referenced"] is True

        partial = "The speed of light is 300,000 km/s."
        score_part, _ = evaluate_general_knowledge(partial)
        assert score_part == 0.5

    def test_evaluate_complex_reasoning(self):
        correct = (
            "Comparing 9.11 and 9.9:\n"
            "Look at the tenths place: 9.9 has a 9 in the tenths place (9.90), "
            "whereas 9.11 has a 1 in the tenths place. Since 9 is greater than 1, "
            "9.9 is larger than 9.11."
        )
        score, details = evaluate_complex_reasoning(correct)
        assert score == 1.0
        assert details["correct_conclusion"] is True
        assert details["incorrect_conclusion"] is False

        incorrect = "9.11 is larger because 11 is greater than 9."
        score_bad, details_bad = evaluate_complex_reasoning(incorrect)
        assert score_bad == 0.0
        assert details_bad["incorrect_conclusion"] is True

    def test_evaluate_coding_valid_palindrome(self):
        valid_code = (
            "```python\n"
            "def is_palindrome(s: str) -> bool:\n"
            "    cleaned = [c.lower() for c in s if c.isalnum()]\n"
            "    return cleaned == cleaned[::-1]\n"
            "```"
        )
        score, details = evaluate_coding(valid_code)
        assert score == 1.0
        assert details["syntax_valid"] is True
        assert details["tests_passed"] == details["total_tests"]

    def test_evaluate_coding_syntax_error(self):
        bad_code = "def is_palindrome(s: return s == s"
        score, details = evaluate_coding(bad_code)
        assert score == 0.0
        assert details["syntax_valid"] is False

    def test_evaluate_document_summarization(self):
        good_summary = (
            "- In 1928, Alexander Fleming discovered penicillin at St. Mary's Hospital.\n"
            "- Howard Florey and Ernst Chain successfully isolated penicillin in 1940.\n"
            "- Large-scale WWII fermentation enabled mass antibiotic production, saving millions of lives."
        )
        score, details = evaluate_document_summarization(good_summary)
        assert score >= 0.8
        assert details["bullet_count"] == 3
        assert details["entities_covered"]["fleming"] is True
        assert details["entities_covered"]["penicillin"] is True

    def test_evaluate_structured_json(self):
        valid_json = json.dumps(
            {
                "status": "success",
                "model_tier": "local",
                "item_count": 3,
                "tags": ["quick", "local", "companion"],
            }
        )
        score, details = evaluate_structured_json(valid_json)
        assert score == 1.0

        invalid_json = "status: success, item_count: 3"
        score_bad, details_bad = evaluate_structured_json(invalid_json)
        assert score_bad == 0.0
        assert "json_parse_error" in details_bad

    def test_evaluate_vision(self):
        resp = "I see a blue background with a red circle shape in the center."
        score, details = evaluate_vision(resp)
        assert score == 1.0
        assert "blue" in details["colors_identified"]
        assert "red" in details["colors_identified"]
        assert "circle" in details["shapes_identified"]


class TestBenchmarkRepository:
    """Verify SQLite persistence and summary aggregations."""

    @pytest.fixture
    def test_repo(self, tmp_path):
        db_path = tmp_path / "test_benchmarks.db"
        db = DatabaseManager(db_path=db_path)
        return BenchmarkRepository(db_manager=db)

    def test_save_and_retrieve_records(self, test_repo):
        rec = BenchmarkRecord(
            model_id="llama3.2:3b",
            category="simple_conversation",
            run_type="warm",
            ttft_ms=310.0,
            tokens_per_sec=45.0,
            total_duration_ms=650.0,
            eval_count=28,
            model_load_ms=0.0,
            peak_ram_mb=3100.0,
            peak_gpu_mb=2100.0,
            context_capacity=131072,
            quality_score=0.95,
            quality_details={"test": "ok"},
            raw_response="Hi!",
            test_outcome="passed",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        row_id = test_repo.save_record(rec)
        assert row_id > 0

        records = test_repo.get_records(model_id="llama3.2:3b")
        assert len(records) == 1
        assert records[0].model_id == "llama3.2:3b"
        assert records[0].ttft_ms == 310.0

    def test_model_summary_aggregation(self, test_repo):
        # Insert cold record
        test_repo.save_record(
            BenchmarkRecord(
                model_id="deepseek-r1:7b",
                category="simple_conversation",
                run_type="cold",
                ttft_ms=1850.0,
                model_load_ms=1200.0,
                quality_score=0.9,
                created_at="2026-11-04T10:00:00Z",
            )
        )
        # Insert warm records
        test_repo.save_record(
            BenchmarkRecord(
                model_id="deepseek-r1:7b",
                category="coding",
                run_type="warm",
                ttft_ms=450.0,
                tokens_per_sec=32.0,
                quality_score=1.0,
                created_at="2026-11-04T10:01:00Z",
            )
        )
        test_repo.save_record(
            BenchmarkRecord(
                model_id="deepseek-r1:7b",
                category="complex_reasoning",
                run_type="warm",
                ttft_ms=520.0,
                tokens_per_sec=28.0,
                quality_score=1.0,
                created_at="2026-11-04T10:02:00Z",
            )
        )

        summary = test_repo.get_model_summary("deepseek-r1:7b")
        assert summary["model_id"] == "deepseek-r1:7b"
        assert summary["cold_start"]["load_duration_ms"] == 1200.0
        assert summary["cold_start"]["ttft_ms"] == 1850.0
        assert summary["warm_performance"]["avg_quality_score"] == 1.0
        assert summary["category_scores"]["coding"] == 1.0


class TestRecommendationEngine:
    """Verify transparent derivation of recommendations from benchmark data."""

    def test_compute_recommendations(self):
        summaries = {
            "llama3.2:3b": {
                "warm_performance": {"avg_ttft_ms": 280.0, "avg_tokens_per_sec": 48.0, "avg_quality_score": 0.88},
                "resource_usage": {"peak_ram_mb": 2600.0},
                "context_capacity": 131072,
                "category_scores": {"simple_conversation": 0.95, "general_knowledge": 0.85, "coding": 0.6},
            },
            "deepseek-r1:7b": {
                "warm_performance": {"avg_ttft_ms": 580.0, "avg_tokens_per_sec": 30.0, "avg_quality_score": 0.98},
                "resource_usage": {"peak_ram_mb": 5600.0},
                "context_capacity": 131072,
                "category_scores": {"coding": 1.0, "complex_reasoning": 1.0, "document_summarization": 0.9},
            },
            "gemma3:4b": {
                "warm_performance": {"avg_ttft_ms": 380.0, "avg_tokens_per_sec": 38.0, "avg_quality_score": 0.92},
                "resource_usage": {"peak_ram_mb": 4100.0},
                "context_capacity": 131072,
                "category_scores": {"vision": 0.95, "simple_conversation": 0.9},
            },
        }

        # Mock registry with vision verification for gemma3
        mock_reg = MagicMock()
        mock_reg.is_vision_capable.side_effect = lambda m: m == "gemma3:4b"

        recs = compute_benchmark_recommendations(summaries, registry=mock_reg)
        assert recs["models_tested"] == 3

        # Fastest model should be llama3.2:3b
        assert recs["fastest_model"]["model_id"] == "llama3.2:3b"

        # Best coding model should be deepseek-r1:7b
        assert recs["best_coding"]["model_id"] == "deepseek-r1:7b"

        # Best vision model should be gemma3:4b
        assert recs["best_vision"]["model_id"] == "gemma3:4b"

        # Best balanced model
        assert recs["best_balanced"]["model_id"] in ["llama3.2:3b", "gemma3:4b"]
        assert "composite_score" in recs["best_balanced"]


class TestModelBenchmarkRunner:
    """Verify background benchmark runner, isolation, and cooperative cancellation."""

    @pytest.fixture
    def mock_ollama_client(self):
        cli = MagicMock()
        cli.list_models.return_value = [
            {
                "name": "llama3.2:3b",
                "size": int(1.88 * (1024 ** 3)),
                "details": {"family": "llama", "parameter_size": "3.2B"},
            }
        ]
        cli.show_model.return_value = {"model_info": {"llama.context_length": 131072}}

        def fake_chat_stream(messages, model, on_metadata=None, **kwargs):
            if on_metadata:
                on_metadata({"eval_count": 10, "load_duration": 15000000, "eval_duration": 250000000})
            yield "Hello! "
            yield "I am Bond. "
            yield "Ready to assist!"

        cli.chat_stream.side_effect = fake_chat_stream
        cli.chat.return_value = "Hello! I am Bond. Ready to assist!"
        cli.unload_model.return_value = True
        return cli

    def test_runner_start_and_complete(self, mock_ollama_client, tmp_path):
        db = DatabaseManager(db_path=tmp_path / "test_runner.db")
        repo = BenchmarkRepository(db_manager=db)

        runner = ModelBenchmarkRunner(client=mock_ollama_client, repository=repo)
        progress_events = []

        started = runner.start_benchmark(
            models=["llama3.2:3b"],
            categories=["simple_conversation"],
            on_progress=lambda p: progress_events.append(dict(p)),
        )
        assert started is True
        assert runner.is_running is True

        # Wait for completion
        runner._thread.join(timeout=10.0)
        assert runner.is_running is False
        assert len(progress_events) > 0

        records = repo.get_records(model_id="llama3.2:3b")
        assert len(records) >= 1

    def test_runner_cancellation(self, mock_ollama_client, tmp_path):
        db = DatabaseManager(db_path=tmp_path / "test_cancel.db")
        repo = BenchmarkRepository(db_manager=db)

        runner = ModelBenchmarkRunner(client=mock_ollama_client, repository=repo)
        runner.start_benchmark(models=["llama3.2:3b"])
        assert runner.is_running is True

        cancelled = runner.cancel()
        assert cancelled is True
        runner._thread.join(timeout=10.0)
        assert runner.is_running is False
        assert runner.get_progress()["cancelled"] is True


class TestModelManagerBenchmarkIntegration:
    """Verify ModelManager integration with ModelBenchmarkRunner and BenchmarkRepository."""

    def test_model_manager_benchmark_helpers(self, tmp_path):
        mock_cli = MagicMock()
        mock_cli.list_models.return_value = [
            {
                "name": "llama3.2:3b",
                "size": int(1.88 * (1024 ** 3)),
                "details": {"family": "llama", "parameter_size": "3.2B"},
            }
        ]
        mock_cli.show_model.return_value = {"model_info": {"llama.context_length": 131072}}

        mgr = ModelManager(client=mock_cli, default_model="llama3.2:3b")
        assert mgr.benchmark_runner is not None

        progress = mgr.get_benchmark_progress()
        assert "is_running" in progress
        assert progress["is_running"] is False

        status = mgr.get_status()
        assert "benchmark_status" in status
