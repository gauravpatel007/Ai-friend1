"""Deterministic Safe Math & Arithmetic Expression Evaluator.

Provides AST-based safe evaluation of mathematical expressions without eval() or exec() security risks.
Prevents mental arithmetic hallucinations by small quantized local LLMs (e.g., 100000+5698 -> 105698).
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any, Dict, Optional, Tuple, Union

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Safe binary operators mapping
SAFE_OPERATORS: Dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Regex to detect math query intents across English, Hindi, and Gujarati
MATH_QUERY_PREFIX = re.compile(
    r"^(?:what\s+is|calculate|solve|evaluate|compute|how\s+much\s+is|tell\s+me|tell|bolo|કહો|ગણતરી\s+કરો|ગણો|હિસાબ\s+કરો|kitna\s+hota\s+hai|kitna\s+hai|kitne\s+hue|batao|bol)\s+",
    re.IGNORECASE,
)

MATH_QUERY_SUFFIX = re.compile(
    r"\s*(?:please|now|buddy|bolo|batao|kitna\s+hai|kitna\s+hota\s+hai|ketla\s+thay|ketlu\s+thay|\?+|!+)$",
    re.IGNORECASE,
)

# Explicit calculation intent verbs (English, Hindi, Gujarati)
CALC_INTENT_PATTERN = re.compile(
    r"\b(?:what\s+is|calculate|evaluate|solve|compute|how\s+much\s+is|ગણતરી\s+કરો|ગણો|હિસાબ\s+કરો|kitna\s+hota\s+hai)\b",
    re.IGNORECASE,
)

# Date rejection filters: slashed or hyphenated dates (YYYY/MM/DD, MM/DD/YYYY, DD/MM/YYYY, etc.)
DATE_REJECTION_PATTERNS = [
    re.compile(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b"),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
]

# Pattern detecting unspaced division or subtraction operators between numbers (e.g. 100/4 or 50-20)
UNSPACED_DIV_OR_SUB = re.compile(
    r"(?<=\d)[/-](?=\d)|(?<=\d)[/-]\s+(?=\d)|(?<=\d)\s+[/-](?=\d)"
)

# Pattern capturing potential standalone arithmetic expressions with numbers and operators
ARITHMETIC_EXPR_PATTERN = re.compile(
    r"^\s*[-+]?\d+(?:\.\d+)?\s*(?:[-+*/%^]|\*\*)\s*[-+]?\d+(?:\.\d+)?(?:\s*(?:[-+*/%^]|\*\*)\s*[-+]?\d+(?:\.\d+)?)*\s*$"
)


class MathExpressionEvaluator:
    """Safely evaluates arithmetic expressions using Python AST."""

    @classmethod
    def _eval_node(cls, node: ast.AST) -> Union[int, float]:
        """Recursively evaluate an AST node strictly restricted to safe arithmetic."""
        if isinstance(node, ast.Expression):
            return cls._eval_node(node.body)

        # Python constants (numbers, floats)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value)}")

        # Unary operations (e.g. -5, +3)
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type in SAFE_OPERATORS:
                operand = cls._eval_node(node.operand)
                return SAFE_OPERATORS[op_type](operand)
            raise ValueError(f"Unsupported unary operator: {op_type}")

        # Binary operations (e.g. 100000 + 5698, 5 * 25)
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise ValueError(f"Unsupported binary operator: {op_type}")

            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)

            # Prevent DOS via massive exponents (e.g. 9999 ** 99999)
            if op_type is ast.Pow:
                if abs(right) > 100:
                    raise ValueError(f"Exponent too large: {right}")

            # Prevent Division by Zero
            if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                raise ZeroDivisionError("Division by zero")

            return SAFE_OPERATORS[op_type](left, right)

        raise ValueError(f"Disallowed AST node: {type(node)}")

    @classmethod
    def is_date(cls, text: str) -> bool:
        """Check if string contains or matches a slashed or hyphenated date format."""
        if not text:
            return False
        clean = text.strip()
        return any(bool(pattern.search(clean)) for pattern in DATE_REJECTION_PATTERNS)

    @classmethod
    def safe_evaluate(cls, expression_str: str) -> Optional[Union[int, float]]:
        """Parse and evaluate an arithmetic string expression.

        Returns:
            Computed numerical value (int or float) if valid, or None.
        """
        if not expression_str or not expression_str.strip():
            return None

        # Clean expression
        clean_expr = expression_str.strip()

        # Date rejection filter
        if cls.is_date(clean_expr):
            return None

        # Replace ^ with ** for power
        clean_expr = re.sub(r"(?<!\*)\^(?!\*)", "**", clean_expr)
        # Replace x or X or × with * if between numbers or spaces
        clean_expr = re.sub(r"(\d)\s*[xX×]\s*(\d)", r"\1 * \2", clean_expr)

        try:
            tree = ast.parse(clean_expr, mode="eval")
            res = cls._eval_node(tree)
            # Format clean int if whole number
            if isinstance(res, float) and res.is_integer():
                res = int(res)
            return res
        except Exception as e:
            logger.debug("Expression '%s' is not a valid safe arithmetic expression: %s", clean_expr, e)
            return None

    @classmethod
    def extract_and_solve(cls, text: str) -> Optional[Tuple[str, Union[int, float], str]]:
        """Inspect user query for arithmetic expressions and compute exact solution.

        Returns:
            Tuple of (extracted_expr_str, numeric_result, formatted_result_str) or None.
        """
        if not text or not text.strip():
            return None

        raw = text.strip()

        # Check explicit calculation intent verbs (e.g. "what is", "calculate", "solve")
        has_calc_intent = bool(CALC_INTENT_PATTERN.search(raw))

        def is_allowed_expression(expr_candidate: str) -> bool:
            clean = expr_candidate.strip()
            # 1. Date rejection filter: ignore strings matching date formats
            if cls.is_date(clean):
                return False
            # 2. Require spaces around / or - operators unless explicitly preceded by calculation intent verbs
            if not has_calc_intent and UNSPACED_DIV_OR_SUB.search(clean):
                return False
            return True

        # Check direct expression first: e.g. "100000+5698" or "100 / 4"
        if ARITHMETIC_EXPR_PATTERN.match(raw):
            if is_allowed_expression(raw):
                val = cls.safe_evaluate(raw)
                if val is not None:
                    formatted = f"{val:,}" if isinstance(val, int) else f"{val:,.4f}".rstrip("0").rstrip(".")
                    return raw, val, formatted
            return None

        # Mask dates out of query so dates are never mistaken for arithmetic expressions
        masked_text = raw
        for pattern in DATE_REJECTION_PATTERNS:
            masked_text = pattern.sub(" ", masked_text)

        # Normalize verbal arithmetic operators (e.g. "15 multiplied by 7", "20 times 5", "100 divided by 4")
        normalized = re.sub(r"\bmultiplied\s+by\b|\btimes\b|\binto\b", "*", masked_text, flags=re.IGNORECASE)
        normalized = re.sub(r"\bdivided\s+by\b", " / ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bplus\b", " + ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bminus\b", " - ", normalized, flags=re.IGNORECASE)

        # Check conversational queries: e.g. "what is 100000+5698", "calculate 25 * 4", "what is 100/4"
        candidate = MATH_QUERY_PREFIX.sub("", normalized).strip()
        candidate = MATH_QUERY_SUFFIX.sub("", candidate).strip()

        if ARITHMETIC_EXPR_PATTERN.match(candidate):
            if is_allowed_expression(candidate):
                val = cls.safe_evaluate(candidate)
                if val is not None:
                    formatted = f"{val:,}" if isinstance(val, int) else f"{val:,.4f}".rstrip("0").rstrip(".")
                    return candidate, val, formatted

        # Look for isolated expressions inside query: "can you tell me 100000 + 5698 please"
        for match in re.finditer(
            r"\b\d+(?:\.\d+)?\s*(?:[-+*/%^]|\*\*)\s*[-+]?\d+(?:\.\d+)?(?:\s*(?:[-+*/%^]|\*\*)\s*[-+]?\d+(?:\.\d+)?)*\b",
            normalized,
        ):
            expr_match = match.group(0).strip()
            if is_allowed_expression(expr_match):
                val = cls.safe_evaluate(expr_match)
                if val is not None:
                    formatted = f"{val:,}" if isinstance(val, int) else f"{val:,.4f}".rstrip("0").rstrip(".")
                    return expr_match, val, formatted

        return None

    @classmethod
    def extract_and_evaluate(cls, text: str) -> Optional[Tuple[str, Union[int, float], str]]:
        """Alias for extract_and_solve."""
        return cls.extract_and_solve(text)
