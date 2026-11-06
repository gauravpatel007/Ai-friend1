"""Tests for Phase 1: Reliable and Complete Response Generation.

Verifies:
- Task-based token budgeting (num_predict dynamic scaling)
- Context window expansion (num_ctx)
- Continuation on length limits without text duplication
- Metadata extraction (done_reason, eval_count)
- Preserving partial output and respecting cancellation
"""

from app.ai.generation_controls import GenerationConfig
from app.ai.ai_service import deduplicate_continuation_prefix, _InferenceWorker, _WorkerSignals
from app.ai.cancellation import CancellationToken
from app.ai.ollama_client import OllamaClient


def test_token_budget_estimation_all_phase1_categories():
    """Verify task-complexity token estimation produces appropriate output budgets."""
    # 1. Greetings (Very Small: ~80-150)
    assert GenerationConfig.estimate_task_token_budget("Hello!") <= 150
    assert GenerationConfig.estimate_task_token_budget("Hi there") <= 150
    assert GenerationConfig.estimate_task_token_budget("Good morning") <= 150

    # 2. Sequence 1 to 100 (Enough for all 100 numbers: >= 600)
    budget_100 = GenerationConfig.estimate_task_token_budget("Write numbers from 1 to 100.")
    assert budget_100 >= 600

    # 3. Sequence 1 to 500 (Large sequence: >= 3000)
    budget_500 = GenerationConfig.estimate_task_token_budget("Write numbers from 1 to 500.")
    assert budget_500 >= 3000

    # 4. Detailed explanation (Large: >= 2500)
    budget_detail = GenerationConfig.estimate_task_token_budget(
        "Explain supervised and unsupervised learning in detail."
    )
    assert budget_detail >= 2500

    # 5. Coding task (Large: >= 2500)
    budget_code = GenerationConfig.estimate_task_token_budget(
        "Write a Python program with complete code for a web scraper."
    )
    assert budget_code >= 2500

    # 6. JSON / Structured data (Large: >= 2000)
    budget_json = GenerationConfig.estimate_task_token_budget(
        "Generate valid JSON containing multiple objects for users and orders."
    )
    assert budget_json >= 2000

    # 7. Document summary (Medium-Large: >= 1500)
    budget_summary = GenerationConfig.estimate_task_token_budget(
        "Summarize this long document and provide the main key takeaways."
    )
    assert budget_summary >= 1500

    # 8. Voice request conciseness (Snappy: <= 350)
    budget_voice = GenerationConfig.estimate_task_token_budget("Tell me a story", is_voice=True)
    assert budget_voice <= 350


def test_deduplicate_continuation_prefix():
    """Verify deduplication removes repeated prefixes at continuation boundaries."""
    # Suffix-prefix exact overlap
    prev = "Here are the numbers:\n1, 2, 3, 4, 5, 6, 7, 8, 9, 10,"
    new_chunk = "10, 11, 12, 13, 14"
    cleaned = deduplicate_continuation_prefix(prev, new_chunk)
    assert cleaned == " 11, 12, 13, 14"

    # Whitespace variation overlap
    prev2 = "Result: [item1, item2,"
    new_chunk2 = " item2, item3, item4]"
    cleaned2 = deduplicate_continuation_prefix(prev2, new_chunk2)
    assert cleaned2 == " item3, item4]"

    # Code block overlap
    prev3 = "def factorial(n):\n    if n <= 1:\n        return 1\n    return n *"
    new_chunk3 = " return n * factorial(n - 1)"
    cleaned3 = deduplicate_continuation_prefix(prev3, new_chunk3)
    assert cleaned3 == " factorial(n - 1)"

    # No overlap preserved
    prev4 = "Chapter 1 completed.\n"
    new_chunk4 = "Chapter 2 begins here."
    cleaned4 = deduplicate_continuation_prefix(prev4, new_chunk4)
    assert cleaned4 == "Chapter 2 begins here."


def test_inference_worker_seamless_continuation(qapp_instance):
    """Verify that _InferenceWorker continues generation when Ollama reports done_reason='length'."""
    call_count = 0

    class MockOllamaClient:
        def chat_stream(self, messages, model, options=None, keep_alive=None, cancellation_token=None, on_metadata=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First pass hits length limit
                if on_metadata:
                    on_metadata({"done": True, "done_reason": "length", "eval_count": 50})
                yield "Part 1: Numbers 1 to 50. "
            else:
                # Continuation completes successfully
                if on_metadata:
                    on_metadata({"done": True, "done_reason": "stop", "eval_count": 50})
                yield "Part 2: Numbers 51 to 100."

    signals = _WorkerSignals()
    chunks = []
    completed = []
    signals.chunk_received.connect(lambda gid, c: chunks.append(c))
    signals.completed.connect(lambda gid, full: completed.append(full))

    worker = _InferenceWorker(
        generation_id=101,
        client=MockOllamaClient(),
        model="llama3.2:3b",
        messages=[{"role": "user", "content": "Write numbers from 1 to 100."}],
        options={"num_predict": 50, "max_continuations": 2},
        cancellation_token=CancellationToken(),
        signals=signals,
    )

    worker.run()

    # Worker should have triggered continuation
    assert call_count == 2
    assert len(completed) == 1
    assert "Part 1: Numbers 1 to 50. Part 2: Numbers 51 to 100." in completed[0]
    assert worker.metadata.get("continuations") == 1
    assert worker.metadata.get("truncated") is False
    assert worker.metadata.get("done_reason") == "stop"


def test_inference_worker_cancellation_during_generation(qapp_instance):
    """Verify worker halts immediately and emits cancelled signal on user cancellation."""
    token = CancellationToken()

    class StalledOllamaClient:
        def chat_stream(self, messages, model, options=None, keep_alive=None, cancellation_token=None, on_metadata=None):
            yield "Beginning of output..."
            token.cancel()
            yield "This should be discarded after cancel"

    signals = _WorkerSignals()
    cancelled = []
    signals.cancelled.connect(lambda gid: cancelled.append(gid))

    worker = _InferenceWorker(
        generation_id=202,
        client=StalledOllamaClient(),
        model="llama3.2:3b",
        messages=[{"role": "user", "content": "Long task"}],
        options={"num_predict": 1000},
        cancellation_token=token,
        signals=signals,
    )

    worker.run()

    assert len(cancelled) == 1
    assert cancelled[0] == 202
