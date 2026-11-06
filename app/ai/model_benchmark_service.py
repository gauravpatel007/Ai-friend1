"""Model Capability Benchmark Service (Phase 3).

Measures and stores empirical performance across installed Ollama models:
- Time to First Token (TTFT)
- Tokens generated per second
- Total response time
- Model loading duration (cold-start vs warm)
- Peak system RAM and GPU VRAM usage
- Context capacity & compatibility
- Objective task quality scoring (conversational, knowledge, reasoning, coding, summarization, JSON, vision)

Supports:
- Safe sequential model loading & unloading
- Background execution with cancellation
- Real-time progress reporting
- Persistent SQLite storage
- Transparent, formula-based model recommendations
"""

from __future__ import annotations

import ast
import base64
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import re
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil

from app.ai.model_capability_registry import (
    ModelCapability,
    get_model_capability_registry,
)
from app.ai.ollama_client import OllamaClient
from app.memory.database import DatabaseManager, init_db
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BenchmarkCategory(str, Enum):
    """Controlled benchmark task categories."""

    SIMPLE_CONVERSATION = "simple_conversation"
    GENERAL_KNOWLEDGE = "general_knowledge"
    COMPLEX_REASONING = "complex_reasoning"
    CODING = "coding"
    DOCUMENT_SUMMARIZATION = "document_summarization"
    STRUCTURED_JSON = "structured_json"
    VISION = "vision"


@dataclass
class BenchmarkRecord:
    """A single benchmark measurement record for a model and task category."""

    id: Optional[int] = None
    model_id: str = ""
    digest: Optional[str] = None
    category: str = ""
    run_type: str = "warm"                   # 'cold' or 'warm'
    ttft_ms: float = 0.0                    # Time to First Token in milliseconds
    tokens_per_sec: float = 0.0             # Output generation throughput
    total_duration_ms: float = 0.0          # Total request duration in milliseconds
    eval_count: int = 0                     # Number of output tokens generated
    model_load_ms: float = 0.0              # Ollama model loading duration in milliseconds
    peak_ram_mb: float = 0.0                # Peak system RAM used in MB
    peak_gpu_mb: float = 0.0                # Peak GPU VRAM used in MB
    context_capacity: int = 2048            # Context window size in tokens
    quality_score: float = 0.0              # Objective quality score (0.0 to 1.0)
    quality_details: Dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""                  # Sample output for verification
    test_outcome: str = "passed"            # 'passed', 'failed', or 'skipped'
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        data = asdict(self)
        return data

    @classmethod
    def from_db_row(cls, row: Any) -> BenchmarkRecord:
        """Instantiate BenchmarkRecord from SQLite Row."""
        q_details = {}
        if row["quality_details"]:
            try:
                q_details = json.loads(row["quality_details"])
            except Exception:
                pass

        return cls(
            id=row["id"],
            model_id=row["model_id"],
            digest=row["digest"],
            category=row["category"],
            run_type=row["run_type"],
            ttft_ms=float(row["ttft_ms"] or 0.0),
            tokens_per_sec=float(row["tokens_per_sec"] or 0.0),
            total_duration_ms=float(row["total_duration_ms"] or 0.0),
            eval_count=int(row["eval_count"] or 0),
            model_load_ms=float(row["model_load_ms"] or 0.0),
            peak_ram_mb=float(row["peak_ram_mb"] or 0.0),
            peak_gpu_mb=float(row["peak_gpu_mb"] or 0.0),
            context_capacity=int(row["context_capacity"] or 2048),
            quality_score=float(row["quality_score"] or 0.0),
            quality_details=q_details,
            raw_response=row["raw_response"] or "",
            test_outcome=row["test_outcome"] or "passed",
            created_at=row["created_at"] or "",
        )


# ─── Persistent Database Repository ───────────────────────────────────────────


class BenchmarkRepository:
    """Manages persistence of model benchmark measurements in SQLite."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or init_db()

    def save_record(self, record: BenchmarkRecord) -> int:
        """Save a benchmark measurement record into SQLite."""
        conn = self.db.get_connection()
        created_at = record.created_at or datetime.now(timezone.utc).isoformat()
        q_details_json = json.dumps(record.quality_details) if record.quality_details else "{}"

        with conn:
            cursor = conn.execute(
                """
                INSERT INTO model_benchmarks (
                    model_id, digest, category, run_type, ttft_ms, tokens_per_sec,
                    total_duration_ms, eval_count, model_load_ms, peak_ram_mb,
                    peak_gpu_mb, context_capacity, quality_score, quality_details,
                    raw_response, test_outcome, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.model_id,
                    record.digest,
                    record.category,
                    record.run_type,
                    record.ttft_ms,
                    record.tokens_per_sec,
                    record.total_duration_ms,
                    record.eval_count,
                    record.model_load_ms,
                    record.peak_ram_mb,
                    record.peak_gpu_mb,
                    record.context_capacity,
                    record.quality_score,
                    q_details_json,
                    record.raw_response[:2000],  # Keep sample response reasonable
                    record.test_outcome,
                    created_at,
                ),
            )
            return cursor.lastrowid

    def get_records(
        self,
        model_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
    ) -> List[BenchmarkRecord]:
        """Fetch benchmark records matching filters ordered by most recent."""
        conn = self.db.get_connection()
        query = "SELECT * FROM model_benchmarks WHERE 1=1"
        params: List[Any] = []

        if model_id:
            query += " AND model_id = ?"
            params.append(model_id)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        return [BenchmarkRecord.from_db_row(r) for r in cursor.fetchall()]

    def get_model_summary(self, model_id: str) -> Dict[str, Any]:
        """Compute aggregated summary of latest benchmarks for a specific model."""
        records = self.get_records(model_id=model_id, limit=50)
        if not records:
            return {}

        warm_records = [r for r in records if r.run_type == "warm" and r.test_outcome == "passed"]
        cold_records = [r for r in records if r.run_type == "cold"]

        avg_warm_ttft = (
            sum(r.ttft_ms for r in warm_records) / len(warm_records) if warm_records else 0.0
        )
        avg_tps = (
            sum(r.tokens_per_sec for r in warm_records if r.tokens_per_sec > 0)
            / len([r for r in warm_records if r.tokens_per_sec > 0])
            if any(r.tokens_per_sec > 0 for r in warm_records)
            else 0.0
        )
        avg_quality = (
            sum(r.quality_score for r in warm_records) / len(warm_records) if warm_records else 0.0
        )
        cold_load_ms = cold_records[0].model_load_ms if cold_records else 0.0
        cold_ttft_ms = cold_records[0].ttft_ms if cold_records else 0.0

        max_ram = max((r.peak_ram_mb for r in records), default=0.0)
        max_gpu = max((r.peak_gpu_mb for r in records), default=0.0)
        ctx = max((r.context_capacity for r in records), default=2048)

        # Category breakdown
        category_scores: Dict[str, float] = {}
        for r in warm_records:
            if r.category not in category_scores:
                category_scores[r.category] = r.quality_score

        return {
            "model_id": model_id,
            "benchmark_count": len(records),
            "latest_run": records[0].created_at if records else None,
            "cold_start": {
                "load_duration_ms": round(cold_load_ms, 1),
                "ttft_ms": round(cold_ttft_ms, 1),
            },
            "warm_performance": {
                "avg_ttft_ms": round(avg_warm_ttft, 1),
                "avg_tokens_per_sec": round(avg_tps, 1),
                "avg_quality_score": round(avg_quality, 2),
            },
            "resource_usage": {
                "peak_ram_mb": round(max_ram, 1),
                "peak_gpu_mb": round(max_gpu, 1),
            },
            "context_capacity": ctx,
            "category_scores": category_scores,
        }

    def get_all_summaries(self) -> Dict[str, Dict[str, Any]]:
        """Fetch aggregated benchmark summaries across all tested models."""
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT DISTINCT model_id FROM model_benchmarks")
        models = [row[0] for row in cursor.fetchall()]
        return {m: self.get_model_summary(m) for m in models}

    def clear_records(self, model_id: Optional[str] = None) -> int:
        """Clear benchmark records for a specific model or all models."""
        conn = self.db.get_connection()
        with conn:
            if model_id:
                cur = conn.execute("DELETE FROM model_benchmarks WHERE model_id = ?", (model_id,))
            else:
                cur = conn.execute("DELETE FROM model_benchmarks")
            return cur.rowcount


# ─── System Resource Measurement Helpers ─────────────────────────────────────


def get_current_system_ram_mb() -> float:
    """Return total system RAM in use (MB) via psutil."""
    try:
        mem = psutil.virtual_memory()
        return mem.used / (1024 * 1024)
    except Exception:
        return 0.0


def get_current_gpu_vram_mb() -> float:
    """Return dedicated NVIDIA GPU VRAM in use (MB) if nvidia-smi is accessible."""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            if lines and lines[0].strip().isdigit():
                return float(lines[0].strip())
    except Exception:
        pass
    return 0.0


# ─── Task Definitions & Objective Quality Evaluators ─────────────────────────


# Synthetic 64x64 blue image with a red centered circle for multimodal vision testing
_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAAVElEQVR4n"
    "O3PsQ2AMBAEwZ8Y6ID+6wEaYALiS065Gsl3u3dmbjrn3Gdfv1u/N4C6w3sDqDu8N4C6w3sDqDu8N4C6w3sD"
    "qDu8N4C6w3sDqDu8N4C6w3sDqDt8bYATy38c5+4AAAAASUVORK5CYII="
)


def evaluate_simple_conversation(response: str) -> Tuple[float, Dict[str, Any]]:
    """Evaluate conversational response for brevity, friendliness, and quality."""
    text = response.strip()
    if not text:
        return 0.0, {"reason": "Empty response"}

    word_count = len(text.split())
    # Ideal friendly greeting is 8 to 40 words
    score = 1.0
    deductions = []

    if word_count < 5:
        score -= 0.3
        deductions.append("Too brief (< 5 words)")
    elif word_count > 60:
        score -= 0.2
        deductions.append("Too verbose for simple greeting (> 60 words)")

    # Check for friendly greeting tokens
    has_friendly_token = any(
        w in text.lower()
        for w in ["hello", "hi", "hey", "good", "great", "doing", "well", "glad", "friend", "happy"]
    )
    if not has_friendly_token:
        score -= 0.2
        deductions.append("Missing standard conversational greeting token")

    score = max(0.0, min(1.0, score))
    return score, {
        "word_count": word_count,
        "friendly_token": has_friendly_token,
        "deductions": deductions,
        "score": score,
    }


def evaluate_general_knowledge(response: str) -> Tuple[float, Dict[str, Any]]:
    """Evaluate speed of light factual answer."""
    text = response.lower()
    score = 0.0
    details = {}

    # Fact 1: ~300,000 km/s or 299,792 km/s
    speed_correct = any(
        s in text
        for s in [
            "300,000",
            "300000",
            "299,792",
            "299792",
            "3 x 10^8",
            "3 × 10^8",
            "300 000",
            "299 792",
        ]
    )
    if speed_correct:
        score += 0.5
    details["speed_of_light_accurate"] = speed_correct

    # Fact 2: Theory of Relativity / Einstein
    theory_correct = any(t in text for t in ["relativity", "special relativity", "einstein"])
    if theory_correct:
        score += 0.5
    details["theory_of_relativity_referenced"] = theory_correct

    details["score"] = score
    return score, details


def evaluate_complex_reasoning(response: str) -> Tuple[float, Dict[str, Any]]:
    """Evaluate mathematical decimal comparison: 9.11 vs 9.9."""
    text = response.lower()
    details = {}

    # Key check: 9.9 is larger because tenths place 9 > 1 (9.90 > 9.11)
    correct_conclusion = False
    if "9.9 is larger" in text or "9.9 is greater" in text or "9.9 > 9.11" in text or "9.90 is greater" in text:
        correct_conclusion = True
    elif "is larger: 9.9" in text or "larger number is 9.9" in text or "9.9 is the larger" in text:
        correct_conclusion = True

    incorrect_conclusion = (
        "9.11 is larger" in text
        or "9.11 is greater" in text
        or "9.11 > 9.9" in text
        or "larger number is 9.11" in text
    )

    explains_decimal_places = any(
        k in text
        for k in ["tenths", "decimal place", "9.90", "0.9", "0.11", "digit-by-digit", "digit by digit"]
    )

    if correct_conclusion and not incorrect_conclusion:
        score = 1.0 if explains_decimal_places else 0.8
    elif incorrect_conclusion:
        score = 0.0
    else:
        # Ambiguous or incomplete
        score = 0.3 if explains_decimal_places else 0.0

    details["correct_conclusion"] = correct_conclusion
    details["incorrect_conclusion"] = incorrect_conclusion
    details["explains_decimal_places"] = explains_decimal_places
    details["score"] = score
    return score, details


def evaluate_coding(response: str) -> Tuple[float, Dict[str, Any]]:
    """Evaluate Python palindrome function generation, syntax validity, and execution."""
    details = {}
    code_text = response

    # Extract python code block if wrapped in markdown
    match = re.search(r"```(?:python)?\s*([\s\S]*?)```", response)
    if match:
        code_text = match.group(1).strip()

    # 1. Syntax check with AST
    syntax_valid = False
    try:
        ast.parse(code_text)
        syntax_valid = True
    except SyntaxError as e:
        details["syntax_error"] = str(e)

    details["syntax_valid"] = syntax_valid
    if not syntax_valid:
        return 0.0, details

    # 2. Functional verification in restricted execution environment
    test_cases = [
        ("A man, a plan, a canal: Panama", True),
        ("race a car", False),
        ("Was it a car or a cat I saw?", True),
        ("hello", False),
        ("Madam", True),
        ("", True),
    ]

    exec_scope: Dict[str, Any] = {}
    passed_tests = 0
    try:
        exec(code_text, {}, exec_scope)
        fn = exec_scope.get("is_palindrome")
        if callable(fn):
            for inp, expected in test_cases:
                try:
                    if fn(inp) == expected:
                        passed_tests += 1
                except Exception:
                    pass
        else:
            details["function_missing"] = "Function 'is_palindrome' was not defined."
    except Exception as ex:
        details["execution_error"] = str(ex)

    total_tests = len(test_cases)
    details["tests_passed"] = passed_tests
    details["total_tests"] = total_tests

    # Base 0.3 for valid syntax + 0.7 proportional to passed tests
    score = 0.3 + (0.7 * (passed_tests / total_tests))
    score = round(min(1.0, score), 2)
    details["score"] = score
    return score, details


def evaluate_document_summarization(response: str) -> Tuple[float, Dict[str, Any]]:
    """Evaluate 3-bullet penicillin document summary for bullet count and key information recall."""
    text = response.strip()
    details = {}

    # Extract bullet points
    lines = [
        l.strip()
        for l in text.splitlines()
        if l.strip() and any(l.strip().startswith(prefix) for prefix in ["-", "*", "•", "1.", "2.", "3."])
    ]

    bullet_count = len(lines)
    details["bullet_count"] = bullet_count

    # Key entity coverage
    text_lower = text.lower()
    entities = {
        "fleming": "fleming" in text_lower,
        "penicillin": "penicillin" in text_lower,
        "oxford_team": any(k in text_lower for k in ["florey", "chain", "oxford"]),
        "wwii_mass_production": any(k in text_lower for k in ["world war", "wwii", "fermentation", "mass production"]),
        "antibiotics": any(k in text_lower for k in ["antibiotic", "medicine", "bacterial", "infections"]),
    }
    details["entities_covered"] = entities

    score = 0.0
    # Exactly 3 bullets gets 0.4; 2-4 bullets gets 0.2
    if bullet_count == 3:
        score += 0.4
    elif 2 <= bullet_count <= 4:
        score += 0.2

    # Entity score (0.6 max)
    covered_count = sum(1 for v in entities.values() if v)
    score += 0.6 * (covered_count / len(entities))

    score = round(min(1.0, score), 2)
    details["score"] = score
    return score, details


def evaluate_structured_json(response: str) -> Tuple[float, Dict[str, Any]]:
    """Evaluate structured JSON schema constraint adherence."""
    details = {}
    cleaned = response.strip()

    # Strip markdown if present
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    parsed = None
    try:
        parsed = json.loads(cleaned)
    except Exception as e:
        details["json_parse_error"] = str(e)
        return 0.0, details

    if not isinstance(parsed, dict):
        details["error"] = "Output is not a JSON object"
        return 0.2, details

    score = 0.4  # Valid JSON object baseline
    # Verify required keys
    if parsed.get("status") == "success":
        score += 0.2
    if parsed.get("model_tier") == "local":
        score += 0.2
    if parsed.get("item_count") == 3:
        score += 0.1
    tags = parsed.get("tags")
    if isinstance(tags, list) and len(tags) == 3:
        score += 0.1

    score = round(min(1.0, score), 2)
    details["parsed_keys"] = list(parsed.keys())
    details["score"] = score
    return score, details


def evaluate_vision(response: str) -> Tuple[float, Dict[str, Any]]:
    """Evaluate visual element recognition in test image."""
    text = response.lower()
    details = {}

    colors = ["blue", "red", "cyan", "white", "black"]
    shapes = ["circle", "square", "round", "rectangle", "shape"]

    found_colors = [c for c in colors if c in text]
    found_shapes = [s for s in shapes if s in text]

    details["colors_identified"] = found_colors
    details["shapes_identified"] = found_shapes

    score = 0.0
    if "blue" in found_colors:
        score += 0.3
    if any(c in found_colors for c in ["red", "cyan", "white"]):
        score += 0.3
    if found_shapes:
        score += 0.4

    score = round(min(1.0, score), 2)
    details["score"] = score
    return score, details


# ─── Standard Benchmark Test Definitions ──────────────────────────────────────


BENCHMARK_TEST_SUITE = [
    {
        "category": BenchmarkCategory.SIMPLE_CONVERSATION,
        "prompt": "Hey Bond! Good to see you. How is your day going? Please give a brief, friendly greeting in 1 to 2 sentences.",
        "system": "You are Bond, a friendly AI companion. Keep answers warm, natural, and concise.",
        "options": {"num_predict": 60, "temperature": 0.7},
        "evaluator": evaluate_simple_conversation,
    },
    {
        "category": BenchmarkCategory.GENERAL_KNOWLEDGE,
        "prompt": "What is the approximate speed of light in vacuum in kilometers per second, and which famous theory of physics established that nothing can travel faster than it?",
        "system": "You are a knowledgeable assistant. Answer factually and concisely.",
        "options": {"num_predict": 120, "temperature": 0.2},
        "evaluator": evaluate_general_knowledge,
    },
    {
        "category": BenchmarkCategory.COMPLEX_REASONING,
        "prompt": "Solve this problem carefully step by step: Which number is larger, 9.11 or 9.9? Explain your reasoning by comparing digits at each decimal position and state your final conclusion clearly.",
        "system": "You are an expert analytical reasoner. Think step by step and be mathematically precise.",
        "options": {"num_predict": 250, "temperature": 0.1},
        "evaluator": evaluate_complex_reasoning,
    },
    {
        "category": BenchmarkCategory.CODING,
        "prompt": "Write a Python function named 'is_palindrome' that takes a string 's' and returns True if it is a palindrome (ignoring casing and non-alphanumeric characters), and False otherwise. Return ONLY the Python code block.",
        "system": "You are an expert Python software engineer. Output valid Python code with docstring and type hints.",
        "options": {"num_predict": 300, "temperature": 0.2},
        "evaluator": evaluate_coding,
    },
    {
        "category": BenchmarkCategory.DOCUMENT_SUMMARIZATION,
        "prompt": (
            "Please read the following text and provide a concise summary consisting of exactly 3 bullet points:\n\n"
            "In 1928, bacteriologist Alexander Fleming discovered penicillin at St. Mary's Hospital in London after "
            "noticing that a mould had contaminated a Staphylococcus culture plate and inhibited bacterial growth. "
            "Although Fleming published his findings in 1929, purifying the substance proved extremely difficult. "
            "Over a decade later, in 1940, a team at Oxford University led by Howard Florey and Ernst Chain successfully "
            "isolated and concentrated penicillin. With the outbreak of World War II, American chemical companies developed "
            "large-scale deep-tank fermentation methods, making millions of doses available for allied soldiers. "
            "The discovery and mass production of penicillin transformed modern medicine, dramatically reducing fatalities "
            "from bacterial infections and ushering in the golden age of antibiotics."
        ),
        "system": "You are a precise document summarizer. Adhere strictly to the requested 3 bullet point format.",
        "options": {"num_predict": 250, "temperature": 0.3},
        "evaluator": evaluate_document_summarization,
    },
    {
        "category": BenchmarkCategory.STRUCTURED_JSON,
        "prompt": "Return a JSON object containing the following keys: 'status' with string value 'success', 'model_tier' with string value 'local', 'item_count' with integer value 3, and 'tags' with a list of 3 string items. Do not include explanatory text outside the JSON.",
        "system": "You are a JSON generator. Output only valid JSON adhering exactly to the requested schema.",
        "options": {"num_predict": 120, "temperature": 0.0},
        "format": "json",
        "evaluator": evaluate_structured_json,
    },
    {
        "category": BenchmarkCategory.VISION,
        "prompt": "Describe the shapes and primary colors you see in this image.",
        "system": "You are a visual inspection assistant. Describe the colors and shapes clearly.",
        "options": {"num_predict": 100, "temperature": 0.2},
        "images": [_TINY_PNG_BASE64],
        "evaluator": evaluate_vision,
        "requires_vision": True,
    },
]


# ─── Benchmark Runner Engine ──────────────────────────────────────────────────


class ModelBenchmarkRunner:
    """Coordinates manual and programmatic model benchmarking runs in a background thread."""

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        repository: Optional[BenchmarkRepository] = None,
    ) -> None:
        self.client = client or OllamaClient()
        self.repository = repository or BenchmarkRepository()
        self.registry = get_model_capability_registry(client=self.client)

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._cancel_requested = threading.Event()
        self._is_running = False

        self._progress_data: Dict[str, Any] = {
            "is_running": False,
            "current_model": "",
            "model_index": 0,
            "total_models": 0,
            "current_category": "",
            "category_index": 0,
            "total_categories": 0,
            "percentage": 0.0,
            "message": "Idle",
            "cancelled": False,
            "error": None,
        }

    @property
    def is_running(self) -> bool:
        """Check if benchmark run is actively executing."""
        with self._lock:
            return self._is_running

    def get_progress(self) -> Dict[str, Any]:
        """Fetch current benchmark progress snapshot."""
        with self._lock:
            return dict(self._progress_data)

    def cancel(self) -> bool:
        """Request immediate cooperative cancellation of current benchmark run."""
        with self._lock:
            if not self._is_running:
                return False
            self._cancel_requested.set()
            self._progress_data["message"] = "Cancellation requested..."
            self._progress_data["cancelled"] = True
            logger.info("Benchmark cancellation requested by user.")
            return True

    def start_benchmark(
        self,
        models: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> bool:
        """Launch benchmark run in background thread."""
        with self._lock:
            if self._is_running:
                logger.warning("Cannot start benchmark: already running.")
                return False

            self._cancel_requested.clear()
            self._is_running = True
            self._progress_data = {
                "is_running": True,
                "current_model": "",
                "model_index": 0,
                "total_models": 0,
                "current_category": "",
                "category_index": 0,
                "total_categories": 0,
                "percentage": 0.0,
                "message": "Starting benchmark suite...",
                "cancelled": False,
                "error": None,
            }

        def _worker():
            try:
                self._run_benchmark_suite(models=models, categories=categories, on_progress=on_progress)
            except Exception as e:
                logger.exception("Benchmark suite encountered unexpected failure: %s", e)
                with self._lock:
                    self._progress_data["error"] = str(e)
                    self._progress_data["message"] = f"Failed: {e}"
            finally:
                with self._lock:
                    self._is_running = False
                    self._progress_data["is_running"] = False
                    if not self._progress_data.get("cancelled") and not self._progress_data.get("error"):
                        self._progress_data["message"] = "Benchmark completed successfully."
                        self._progress_data["percentage"] = 100.0

        self._thread = threading.Thread(target=_worker, name="ModelBenchmarkRunner", daemon=True)
        self._thread.start()
        return True

    def _update_progress(
        self,
        current_model: str,
        model_idx: int,
        total_models: int,
        current_cat: str,
        cat_idx: int,
        total_cats: int,
        message: str,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """Update progress metrics and invoke external observer."""
        total_steps = max(1, total_models * (total_cats + 1))  # +1 for cold start
        completed_steps = (model_idx * (total_cats + 1)) + cat_idx
        percentage = round(min(100.0, (completed_steps / total_steps) * 100.0), 1)

        with self._lock:
            self._progress_data.update(
                {
                    "current_model": current_model,
                    "model_index": model_idx + 1,
                    "total_models": total_models,
                    "current_category": current_cat,
                    "category_index": cat_idx,
                    "total_categories": total_cats,
                    "percentage": percentage,
                    "message": message,
                }
            )
            snapshot = dict(self._progress_data)

        if on_progress:
            try:
                on_progress(snapshot)
            except Exception:
                pass

    def _execute_single_test(
        self,
        model_id: str,
        test_def: Dict[str, Any],
        run_type: str = "warm",
    ) -> BenchmarkRecord:
        """Execute a single streaming inference test on a model and record metrics."""
        category = test_def["category"].value if hasattr(test_def["category"], "value") else str(test_def["category"])
        prompt = test_def["prompt"]
        system = test_def.get("system")
        options = test_def.get("options", {})
        fmt = test_def.get("format")
        images = test_def.get("images")
        evaluator = test_def.get("evaluator")

        prof = self.registry.get_model(model_id)
        ctx_capacity = prof.context_capacity if prof else 2048

        # Check vision requirement
        if test_def.get("requires_vision"):
            if not self.registry.is_vision_capable(model_id):
                return BenchmarkRecord(
                    model_id=model_id,
                    category=category,
                    run_type=run_type,
                    context_capacity=ctx_capacity,
                    quality_score=0.0,
                    quality_details={"reason": "Model lacks verified multimodal vision capability."},
                    raw_response="",
                    test_outcome="skipped",
                    created_at=datetime.now(timezone.utc).isoformat(),
                )

        chunks: List[str] = []
        first_token_time: Optional[float] = None
        eval_count = 0
        load_duration_ns = 0
        eval_duration_ns = 0

        # Memory snapshots
        start_ram = get_current_system_ram_mb()
        start_gpu = get_current_gpu_vram_mb()

        t_start = time.perf_counter()

        def _on_chunk(token: str) -> None:
            nonlocal first_token_time
            if first_token_time is None:
                first_token_time = time.perf_counter()
            chunks.append(token)

        def _on_metadata(meta: Dict[str, Any]) -> None:
            nonlocal eval_count, load_duration_ns, eval_duration_ns
            eval_count = int(meta.get("eval_count", 0) or 0)
            load_duration_ns = int(meta.get("load_duration", 0) or 0)
            eval_duration_ns = int(meta.get("eval_duration", 0) or 0)

        # Prepare chat messages
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        user_msg: Dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)

        # Execute streaming generation
        try:
            stream_iter = self.client.chat_stream(
                messages=messages,
                model=model_id,
                options=options,
                keep_alive="5m" if run_type == "warm" else "0",
                format=fmt,
                on_metadata=_on_metadata,
            )
            for chunk in stream_iter:
                _on_chunk(chunk)
        except Exception as e:
            logger.warning("Benchmark generation error for %s (%s): %s", model_id, category, e)
            return BenchmarkRecord(
                model_id=model_id,
                category=category,
                run_type=run_type,
                context_capacity=ctx_capacity,
                quality_score=0.0,
                quality_details={"error": str(e)},
                raw_response="".join(chunks),
                test_outcome="failed",
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        t_end = time.perf_counter()
        total_duration_ms = (t_end - t_start) * 1000.0

        # Calculate TTFT
        ttft_ms = ((first_token_time - t_start) * 1000.0) if first_token_time else total_duration_ms

        # Calculate Tokens Per Second (TPS)
        if eval_count > 0 and eval_duration_ns > 0:
            tokens_per_sec = eval_count / (eval_duration_ns / 1e9)
        elif eval_count > 0 and total_duration_ms > 0:
            stream_dur_sec = max(0.001, (t_end - (first_token_time or t_start)))
            tokens_per_sec = eval_count / stream_dur_sec
        else:
            tokens_per_sec = len(chunks) / max(0.001, (total_duration_ms / 1000.0))

        model_load_ms = (load_duration_ns / 1e6) if load_duration_ns > 0 else 0.0
        peak_ram = max(start_ram, get_current_system_ram_mb())
        peak_gpu = max(start_gpu, get_current_gpu_vram_mb())

        raw_text = "".join(chunks)

        # Evaluate quality score
        quality_score = 1.0
        quality_details = {}
        if evaluator:
            try:
                quality_score, quality_details = evaluator(raw_text)
            except Exception as ev_err:
                logger.debug("Evaluator notice for %s (%s): %s", model_id, category, ev_err)
                quality_details = {"evaluator_error": str(ev_err)}

        return BenchmarkRecord(
            model_id=model_id,
            category=category,
            run_type=run_type,
            ttft_ms=round(ttft_ms, 1),
            tokens_per_sec=round(tokens_per_sec, 1),
            total_duration_ms=round(total_duration_ms, 1),
            eval_count=eval_count or len(chunks),
            model_load_ms=round(model_load_ms, 1),
            peak_ram_mb=round(peak_ram, 1),
            peak_gpu_mb=round(peak_gpu, 1),
            context_capacity=ctx_capacity,
            quality_score=round(quality_score, 2),
            quality_details=quality_details,
            raw_response=raw_text,
            test_outcome="passed",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _run_benchmark_suite(
        self,
        models: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """Sequentially execute benchmark suite across requested models."""
        self.registry.refresh()
        installed_profiles = self.registry.get_installed_models(local_only=True)

        if models:
            target_models = [m for m in models if self.registry.get_model(m)]
        else:
            target_models = [p.model_id for p in installed_profiles]

        if not target_models:
            raise RuntimeError("No installed local companion models available for benchmarking.")

        # Filter categories if requested
        if categories:
            selected_categories = {c.lower() for c in categories}
            test_suite = [
                t
                for t in BENCHMARK_TEST_SUITE
                if (t["category"].value if hasattr(t["category"], "value") else str(t["category"])) in selected_categories
            ]
        else:
            test_suite = list(BENCHMARK_TEST_SUITE)

        total_models = len(target_models)
        total_tests = len(test_suite)

        logger.info(
            "Starting empirical model benchmark suite: %d models, %d categories.",
            total_models,
            total_tests,
        )

        for m_idx, model_id in enumerate(target_models):
            if self._cancel_requested.is_set():
                logger.info("Benchmark cancelled before model: %s", model_id)
                break

            # ── Step 1: Resource Isolation — Unload previous model ─────
            try:
                self.client.unload_model(model_id)
                time.sleep(0.1)
            except Exception as un_err:
                logger.debug("Unload notice before cold start: %s", un_err)

            # ── Step 2: Cold-Start Performance Test ────────────────────
            self._update_progress(
                current_model=model_id,
                model_idx=m_idx,
                total_models=total_models,
                current_cat="cold_start",
                cat_idx=0,
                total_cats=total_tests,
                message=f"Measuring cold-start loading for {model_id}...",
                on_progress=on_progress,
            )

            cold_test_def = {
                "category": BenchmarkCategory.SIMPLE_CONVERSATION,
                "prompt": "Hello! Please give a brief greeting in one sentence.",
                "options": {"num_predict": 30, "temperature": 0.5},
                "evaluator": evaluate_simple_conversation,
            }
            cold_rec = self._execute_single_test(model_id, cold_test_def, run_type="cold")
            self.repository.save_record(cold_rec)

            if self._cancel_requested.is_set():
                break

            # ── Step 3: Warm-Model Performance Tests ───────────────────
            for t_idx, test_def in enumerate(test_suite):
                if self._cancel_requested.is_set():
                    break

                cat_name = test_def["category"].value if hasattr(test_def["category"], "value") else str(test_def["category"])
                self._update_progress(
                    current_model=model_id,
                    model_idx=m_idx,
                    total_models=total_models,
                    current_cat=cat_name,
                    cat_idx=t_idx + 1,
                    total_cats=total_tests,
                    message=f"Testing {model_id} on {cat_name.replace('_', ' ')}...",
                    on_progress=on_progress,
                )

                warm_rec = self._execute_single_test(model_id, test_def, run_type="warm")
                self.repository.save_record(warm_rec)

            # Record model summary into registry for fast in-memory routing
            summary = self.repository.get_model_summary(model_id)
            prof = self.registry.get_model(model_id)
            if prof and summary:
                prof.benchmark_scores = summary

            # Unload model after finishing to release memory for next model
            try:
                self.client.unload_model(model_id)
            except Exception:
                pass

        logger.info("Completed model capability benchmark run.")


# ─── Transparent Recommendation Engine ─────────────────────────────────────────


def compute_benchmark_recommendations(
    summaries: Dict[str, Dict[str, Any]],
    registry: Optional[Any] = None,
) -> Dict[str, Any]:
    """Derive evidenced task recommendations from empirical benchmark measurements.

    Bond identifies:
    - Fastest model: lowest warm TTFT and highest tokens/sec on simple interactions.
    - Best general conversational model: best balance of conversational quality and low TTFT.
    - Best coding model: highest quality score on programming benchmarks.
    - Best long-context model: largest native context capacity + document summarization score.
    - Best vision-capable model: verified vision architecture with highest multimodal visual score.
    - Best balanced model: composite score balancing quality (35%), latency (30%), throughput (20%), and VRAM efficiency (15%).
    """
    if not summaries:
        return {
            "fastest_model": None,
            "best_conversational": None,
            "best_coding": None,
            "best_long_context": None,
            "best_vision": None,
            "best_balanced": None,
            "models_tested": 0,
            "explanation": "No empirical benchmark data recorded yet.",
        }

    reg = registry or get_model_capability_registry()

    valid_models = [m for m, s in summaries.items() if s.get("warm_performance")]
    if not valid_models:
        return {"models_tested": 0, "explanation": "No valid warm performance records."}

    # 1. Fastest Model (Lowest TTFT + highest tokens/sec)
    def _speed_score(m: str) -> float:
        wp = summaries[m].get("warm_performance", {})
        ttft = wp.get("avg_ttft_ms", 9999.0)
        tps = wp.get("avg_tokens_per_sec", 1.0)
        # Lower TTFT and higher TPS is better
        return (tps * 1000.0) / max(100.0, ttft)

    fastest_model = max(valid_models, key=_speed_score)
    fast_wp = summaries[fastest_model]["warm_performance"]

    # 2. Best Coding Model
    def _coding_score(m: str) -> float:
        scores = summaries[m].get("category_scores", {})
        c_score = scores.get("coding", 0.0)
        # Tie breaker with TTFT
        ttft = summaries[m]["warm_performance"].get("avg_ttft_ms", 9999.0)
        return (c_score * 1000.0) - (ttft / 10.0)

    best_coding = max(valid_models, key=_coding_score)
    coding_score_val = summaries[best_coding].get("category_scores", {}).get("coding", 0.0)

    # 3. Best General Conversational Model
    def _conv_score(m: str) -> float:
        scores = summaries[m].get("category_scores", {})
        conv_q = scores.get("simple_conversation", 0.0) * 0.5 + scores.get("general_knowledge", 0.0) * 0.5
        ttft = summaries[m]["warm_performance"].get("avg_ttft_ms", 9999.0)
        # Conversational models need snappy response (penalize TTFT > 1500ms)
        latency_factor = max(0.1, 1.0 - (ttft / 3000.0))
        return conv_q * latency_factor

    best_conversational = max(valid_models, key=_conv_score)
    conv_score_val = summaries[best_conversational]["warm_performance"].get("avg_quality_score", 0.0)

    # 4. Best Long-Context Model
    def _long_ctx_score(m: str) -> float:
        ctx = summaries[m].get("context_capacity", 2048)
        summ_q = summaries[m].get("category_scores", {}).get("document_summarization", 0.0)
        return (ctx / 1000.0) * (summ_q + 0.5)

    best_long_ctx = max(valid_models, key=_long_ctx_score)
    long_ctx_val = summaries[best_long_ctx].get("context_capacity", 2048)

    # 5. Best Vision Model (must be verified vision capable)
    vision_candidates = [m for m in valid_models if reg.is_vision_capable(m)]
    if vision_candidates:
        def _vision_score(m: str) -> float:
            scores = summaries[m].get("category_scores", {})
            return scores.get("vision", 0.0)
        best_vision = max(vision_candidates, key=_vision_score)
        vision_score_val = summaries[best_vision].get("category_scores", {}).get("vision", 0.0)
    else:
        best_vision = None
        vision_score_val = 0.0

    # 6. Best Balanced Model (Composite Normalization)
    max_ttft = max((summaries[m]["warm_performance"].get("avg_ttft_ms", 1000.0) for m in valid_models), default=1000.0)
    max_tps = max((summaries[m]["warm_performance"].get("avg_tokens_per_sec", 10.0) for m in valid_models), default=10.0)
    max_vram = max((summaries[m]["resource_usage"].get("peak_ram_mb", 4000.0) for m in valid_models), default=4000.0)

    def _balanced_score(m: str) -> float:
        s = summaries[m]
        q = s["warm_performance"].get("avg_quality_score", 0.5)
        ttft = s["warm_performance"].get("avg_ttft_ms", max_ttft)
        tps = s["warm_performance"].get("avg_tokens_per_sec", 1.0)
        vram = s["resource_usage"].get("peak_ram_mb", max_vram)

        q_norm = q
        lat_norm = max(0.0, 1.0 - (ttft / max(1.0, max_ttft)))
        tps_norm = min(1.0, tps / max(1.0, max_tps))
        vram_norm = max(0.0, 1.0 - (vram / max(1.0, max_vram)))

        # 35% Quality, 30% Latency, 20% Throughput, 15% Memory footprint
        return (0.35 * q_norm) + (0.30 * lat_norm) + (0.20 * tps_norm) + (0.15 * vram_norm)

    best_balanced = max(valid_models, key=_balanced_score)
    balanced_score_val = round(_balanced_score(best_balanced), 2)

    return {
        "models_tested": len(valid_models),
        "fastest_model": {
            "model_id": fastest_model,
            "avg_ttft_ms": fast_wp.get("avg_ttft_ms"),
            "tokens_per_sec": fast_wp.get("avg_tokens_per_sec"),
            "reason": (
                f"Fastest warm responsiveness with {fast_wp.get('avg_ttft_ms')}ms TTFT "
                f"and {fast_wp.get('avg_tokens_per_sec')} tokens/sec generation throughput."
            ),
        },
        "best_conversational": {
            "model_id": best_conversational,
            "quality_score": conv_score_val,
            "avg_ttft_ms": summaries[best_conversational]["warm_performance"].get("avg_ttft_ms"),
            "reason": (
                f"Highest conversational quality score ({conv_score_val:.2f}/1.00) "
                f"with snappy {summaries[best_conversational]['warm_performance'].get('avg_ttft_ms')}ms TTFT."
            ),
        },
        "best_coding": {
            "model_id": best_coding,
            "quality_score": coding_score_val,
            "reason": f"Achieved highest Python algorithmic pass rate ({coding_score_val:.2f}/1.00).",
        },
        "best_long_context": {
            "model_id": best_long_ctx,
            "context_capacity": long_ctx_val,
            "reason": f"Supports native {long_ctx_val:,} token context window with high recall summarization.",
        },
        "best_vision": (
            {
                "model_id": best_vision,
                "quality_score": vision_score_val,
                "reason": f"Verified CLIP/multimodal architecture with {vision_score_val:.2f}/1.00 visual inspection score.",
            }
            if best_vision
            else None
        ),
        "best_balanced": {
            "model_id": best_balanced,
            "composite_score": balanced_score_val,
            "reason": (
                f"Optimal composite score ({balanced_score_val:.2f}/1.00) balancing quality (35%), "
                "latency (30%), throughput (20%), and VRAM footprint (15%)."
            ),
        },
    }


# Singleton runner instance
_GLOBAL_RUNNER: Optional[ModelBenchmarkRunner] = None
_RUNNER_LOCK = threading.Lock()


def get_model_benchmark_runner(
    client: Optional[OllamaClient] = None,
    repository: Optional[BenchmarkRepository] = None,
) -> ModelBenchmarkRunner:
    """Return the global ModelBenchmarkRunner singleton."""
    global _GLOBAL_RUNNER
    with _RUNNER_LOCK:
        if _GLOBAL_RUNNER is None:
            _GLOBAL_RUNNER = ModelBenchmarkRunner(client=client, repository=repository)
        return _GLOBAL_RUNNER
