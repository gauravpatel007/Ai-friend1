"""Tests for Bug #11: Math Expression Evaluator Date Rejection & Operator Spacing Rules.

Verifies:
1. Slashed and hyphenated dates (YYYY/MM/DD, YYYY-MM-DD, MM/DD/YYYY, DD-MM-YYYY) are rejected and not evaluated as arithmetic.
2. Queries containing dates ("What events happened on 2026/10/30?", "Remind me on 12/25/2024") return None.
3. Dates are rejected even if preceded by query prefix keywords ("what is 2026/10/30", "solve 2024-11-15").
4. Unspaced / and - operators require explicit calculation intent verbs ("what is", "calculate", "solve").
5. Spaced / and - operators evaluate cleanly even without intent verbs.
6. Operators other than / and - (+, *, **) continue to evaluate cleanly without spaces.
7. Mixed queries with both a date and a legitimate math question extract only the math question.
8. extract_and_evaluate() alias operates identically to extract_and_solve().
"""

from __future__ import annotations

import pytest
from app.ai.math_evaluator import MathExpressionEvaluator


def test_date_expressions_rejected_standalone():
    """Verify raw date strings in slash or hyphen format evaluate to None."""
    assert MathExpressionEvaluator.extract_and_solve("2026/10/30") is None
    assert MathExpressionEvaluator.extract_and_solve("2024-11-15") is None
    assert MathExpressionEvaluator.extract_and_solve("12/25/2024") is None
    assert MathExpressionEvaluator.extract_and_solve("31-12-2024") is None
    assert MathExpressionEvaluator.extract_and_solve("01/05/26") is None
    assert MathExpressionEvaluator.extract_and_solve("1/5/2026") is None

    # Also directly in safe_evaluate()
    assert MathExpressionEvaluator.safe_evaluate("2026/10/30") is None
    assert MathExpressionEvaluator.safe_evaluate("2024-11-15") is None
    assert MathExpressionEvaluator.safe_evaluate("12/25/2024") is None


def test_natural_language_date_queries_rejected():
    """Verify natural language queries mentioning dates are not hijacked as arithmetic."""
    # User problem statement exact examples:
    assert MathExpressionEvaluator.extract_and_solve("What events happened on 2026/10/30?") is None
    assert MathExpressionEvaluator.extract_and_solve("Remind me on 12/25/2024") is None
    assert MathExpressionEvaluator.extract_and_solve("My appointment is on 2024-11-15") is None
    assert MathExpressionEvaluator.extract_and_solve("I was born on 1995-04-12") is None
    assert MathExpressionEvaluator.extract_and_solve("Meeting is on 05/11/2024 please") is None


def test_dates_with_calc_prefixes_still_rejected():
    """Verify date formats are rejected even when preceded by 'what is' or 'solve'."""
    assert MathExpressionEvaluator.extract_and_solve("what is 2026/10/30") is None
    assert MathExpressionEvaluator.extract_and_solve("solve 2024-11-15") is None
    assert MathExpressionEvaluator.extract_and_solve("calculate 12/25/2024") is None


def test_unspaced_slash_and_hyphen_require_calc_intent_verb():
    """Verify unspaced / or - without intent verb are rejected, but accepted with intent verb."""
    # No calculation intent verb -> Rejected
    assert MathExpressionEvaluator.extract_and_solve("100/4") is None
    assert MathExpressionEvaluator.extract_and_solve("50-20") is None
    assert MathExpressionEvaluator.extract_and_solve("10-12") is None

    # With calculation intent verb ("what is", "calculate", "solve") -> Accepted
    res_div = MathExpressionEvaluator.extract_and_solve("what is 100/4")
    assert res_div is not None
    assert res_div[1] == 25

    res_sub = MathExpressionEvaluator.extract_and_solve("calculate 50-20")
    assert res_sub is not None
    assert res_sub[1] == 30

    res_solve = MathExpressionEvaluator.extract_and_solve("solve 10/2")
    assert res_solve is not None
    assert res_solve[1] == 5


def test_spaced_slash_and_hyphen_evaluate_without_intent_verb():
    """Verify / and - with spaces evaluate cleanly even without intent verbs."""
    res_div = MathExpressionEvaluator.extract_and_solve("100 / 4")
    assert res_div is not None
    assert res_div[1] == 25

    res_sub = MathExpressionEvaluator.extract_and_solve("50 - 20")
    assert res_sub is not None
    assert res_sub[1] == 30

    res_multistep = MathExpressionEvaluator.extract_and_solve("100 - 50 - 20")
    assert res_multistep is not None
    assert res_multistep[1] == 30


def test_other_operators_do_not_require_spaces():
    """Verify +, *, ** work without spaces even without intent verbs."""
    res_add = MathExpressionEvaluator.extract_and_solve("100000+5698")
    assert res_add is not None
    assert res_add[1] == 105698

    res_mul = MathExpressionEvaluator.extract_and_solve("25*40")
    assert res_mul is not None
    assert res_mul[1] == 1000

    res_pow = MathExpressionEvaluator.extract_and_solve("2^10")
    assert res_pow is not None
    assert res_pow[1] == 1024


def test_mixed_query_with_date_and_math():
    """Verify mixed query extracts only the legitimate math expression, ignoring the date."""
    res = MathExpressionEvaluator.extract_and_solve("On 2026/10/30, what is 5 + 5?")
    assert res is not None
    assert res[1] == 10


def test_extract_and_evaluate_alias():
    """Verify extract_and_evaluate alias matches extract_and_solve behavior."""
    assert MathExpressionEvaluator.extract_and_evaluate("What events happened on 2026/10/30?") is None
    assert MathExpressionEvaluator.extract_and_evaluate("100/4") is None

    res = MathExpressionEvaluator.extract_and_evaluate("what is 100/4")
    assert res is not None
    assert res[1] == 25
