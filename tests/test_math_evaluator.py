"""Unit and integration tests for MathExpressionEvaluator and arithmetic calculation accuracy."""

import pytest
from app.ai.math_evaluator import MathExpressionEvaluator
from app.ai.offline_companion import OfflineCompanionEngine


def test_pure_arithmetic_expressions():
    """Verify standard arithmetic operations evaluate accurately."""
    # Addition from user screenshot
    assert MathExpressionEvaluator.safe_evaluate("100000+5698") == 105698
    assert MathExpressionEvaluator.safe_evaluate("100000 + 5698") == 105698

    # Multiplication
    assert MathExpressionEvaluator.safe_evaluate("25 * 40") == 1000
    assert MathExpressionEvaluator.safe_evaluate("25 x 40") == 1000

    # Subtraction and negative numbers
    assert MathExpressionEvaluator.safe_evaluate("5000 - 1234") == 3766
    assert MathExpressionEvaluator.safe_evaluate("-10 + 35") == 25

    # Division & Floating point
    assert MathExpressionEvaluator.safe_evaluate("100 / 4") == 25
    assert MathExpressionEvaluator.safe_evaluate("7 / 2") == 3.5

    # Exponents (within safe limits)
    assert MathExpressionEvaluator.safe_evaluate("2 ** 10") == 1024
    assert MathExpressionEvaluator.safe_evaluate("2 ^ 10") == 1024


def test_dos_and_unsafe_ast_rejections():
    """Verify dangerous operations, variable injections, and oversized powers are rejected."""
    # Disallow giant powers
    assert MathExpressionEvaluator.safe_evaluate("9999 ** 99999") is None

    # Disallow division by zero
    assert MathExpressionEvaluator.safe_evaluate("100 / 0") is None

    # Disallow variable names and function calls
    assert MathExpressionEvaluator.safe_evaluate("__import__('os').system('calc')") is None
    assert MathExpressionEvaluator.safe_evaluate("open('/etc/passwd')") is None
    assert MathExpressionEvaluator.safe_evaluate("x + 5") is None


def test_extract_and_solve_patterns():
    """Verify natural language math query extraction and formatted results."""
    # User screenshot exact prompt: "100000+5698"
    res1 = MathExpressionEvaluator.extract_and_solve("100000+5698")
    assert res1 is not None
    expr, val, formatted = res1
    assert expr == "100000+5698"
    assert val == 105698
    assert formatted == "105,698"

    # With question prefix & suffix (English, Hindi, Gujarati)
    res2 = MathExpressionEvaluator.extract_and_solve("what is 100000+5698 bolo")
    assert res2 is not None
    assert res2[1] == 105698

    res3 = MathExpressionEvaluator.extract_and_solve("calculate 50 * 200 please")
    assert res3 is not None
    assert res3[1] == 10000

    res4 = MathExpressionEvaluator.extract_and_solve("100000+5698 kitna hota hai")
    assert res4 is not None
    assert res4[1] == 105698

    # Non-math query
    assert MathExpressionEvaluator.extract_and_solve("Can you recommend a good movie?") is None


def test_offline_companion_engine_math_response():
    """Verify OfflineCompanionEngine answers arithmetic queries deterministically."""
    engine = OfflineCompanionEngine(companion_name="Buddy", personality="playful")
    resp = engine.generate_response("100000+5698")
    # Verify exact sum is in the response and not hallucinated
    assert "105,698" in resp or "105698" in resp
    assert "1009868" not in resp

    engine.personality = "friendly"
    resp2 = engine.generate_response("what is 25 * 40 bolo")
    assert "1,000" in resp2 or "1000" in resp2
