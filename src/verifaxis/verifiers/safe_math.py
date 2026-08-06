"""Deterministic arithmetic checking with a small AST whitelist."""

from __future__ import annotations

import ast
import math
import operator
import re
from collections.abc import Callable

from ..types import (
    Candidate,
    EvidencePacket,
    EvidenceStatus,
    IndependenceClassification,
    JSONValue,
)

Number = int | float
_BINARY_OPERATORS: dict[type[ast.operator], Callable[[Number, Number], Number]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Number], Number]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_ARITHMETIC_RUN = re.compile(r"[0-9.()+\-*/%^\s]+")
_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_QUOTED_TEXT = re.compile(r"(['\"])(?:\\.|(?!\1).)*\1")


def evaluate_arithmetic_expression(expression: str) -> Number:
    """Safely evaluate a bounded numeric expression; never call ``eval``."""

    if len(expression) > 500:
        raise ValueError("expression is too long")
    expression = expression.strip().replace("^", "**")
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError("expression is too complex")

    def visit(node: ast.AST) -> Number:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int | float):
                raise ValueError("only numeric constants are allowed")
            value: Number = node.value
            if not math.isfinite(float(value)):
                raise ValueError("non-finite constants are not allowed")
            return value
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[type(node.op)](visit(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left = visit(node.left)
            right = visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(float(right)) > 1_000:
                raise ValueError("exponent exceeds the safety limit")
            result = _BINARY_OPERATORS[type(node.op)](left, right)
            if not isinstance(result, int | float) or not math.isfinite(float(result)):
                raise ValueError("expression result is not a finite number")
            if isinstance(result, int) and result.bit_length() > 4096:
                raise ValueError("integer result exceeds the safety limit")
            return result
        raise ValueError(f"disallowed arithmetic syntax: {type(node).__name__}")

    return visit(tree)


def _extract_expression(task: str) -> str:
    stripped = task.strip().rstrip("?= ")
    try:
        evaluate_arithmetic_expression(stripped)
        return stripped
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        pass

    valid: list[str] = []
    # Numeric-looking paths or payloads inside quoted call arguments are not
    # arithmetic claims. Removing quoted spans also keeps injection fixtures
    # from being misidentified as a valid task expression.
    searchable = _QUOTED_TEXT.sub(" ", task)
    for match in _ARITHMETIC_RUN.finditer(searchable):
        expression = match.group(0).strip(" .")
        if not expression or not any(symbol in expression for symbol in "+-*/%^()"):
            continue
        try:
            evaluate_arithmetic_expression(expression)
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
            continue
        valid.append(expression)
    if not valid:
        raise ValueError("no supported arithmetic expression found in task")
    return max(valid, key=len)


def evaluate_arithmetic_task(task: str) -> Number:
    """Extract and safely evaluate the arithmetic expression in a text task."""

    return evaluate_arithmetic_expression(_extract_expression(task))


def _extract_candidate_number(content: str) -> Number:
    if len(content) > 20_000:
        raise ValueError("candidate is too long")
    cleaned = content.replace(",", "").strip()
    segments = [cleaned]
    if "=" in cleaned:
        segments.insert(0, cleaned.rsplit("=", 1)[-1].strip())
    for segment in segments:
        try:
            return evaluate_arithmetic_expression(segment)
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
            continue
    matches = _NUMBER.findall(cleaned)
    if not matches:
        raise ValueError("candidate contains no numeric answer")
    token = matches[-1]
    return float(token) if any(character in token.lower() for character in ".e") else int(token)


class SafeMathVerifier:
    """Check a numeric answer against a safely evaluated task expression."""

    verifier_type = "safe_math_ast"
    verifier_version = "1.0"

    def verify(self, *, task: str, candidate: Candidate) -> EvidencePacket:
        try:
            expression = _extract_expression(task)
            expected = evaluate_arithmetic_expression(expression)
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as error:
            return EvidencePacket.create(
                verifier_type=self.verifier_type,
                verifier_version=self.verifier_version,
                status=EvidenceStatus.UNKNOWN,
                checked_claim="task contains a supported deterministic arithmetic expression",
                counterexample={"error": type(error).__name__, "message": str(error)[:200]},
                provenance={"method": "python-ast-whitelist"},
                independence=IndependenceClassification.INDEPENDENT,
                reliability={"deterministic": True, "expression_recovered": False},
                raw_artifact_ref="inline://task",
                llm_produced=False,
            )

        checked_claim = f"candidate equals the deterministic value of {expression!r}"
        try:
            observed = _extract_candidate_number(candidate.content)
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as error:
            return EvidencePacket.create(
                verifier_type=self.verifier_type,
                verifier_version=self.verifier_version,
                status=EvidenceStatus.FAIL,
                checked_claim=checked_claim,
                counterexample={
                    "expression": expression,
                    "expected": expected,
                    "observed": None,
                    "error": str(error)[:200],
                },
                provenance={"method": "python-ast-whitelist", "expression": expression},
                independence=IndependenceClassification.INDEPENDENT,
                reliability={"deterministic": True, "tolerance": 0.0},
                raw_artifact_ref="inline://candidate",
                llm_produced=False,
            )

        passed = observed == expected
        counterexample: JSONValue = None
        if not passed:
            counterexample = {
                "expression": expression,
                "expected": expected,
                "observed": observed,
                "difference": observed - expected,
            }
        return EvidencePacket.create(
            verifier_type=self.verifier_type,
            verifier_version=self.verifier_version,
            status=EvidenceStatus.PASS if passed else EvidenceStatus.FAIL,
            checked_claim=checked_claim,
            counterexample=counterexample,
            provenance={"method": "python-ast-whitelist", "expression": expression},
            independence=IndependenceClassification.INDEPENDENT,
            reliability={"deterministic": True, "tolerance": 0.0},
            raw_artifact_ref="inline://candidate",
            llm_produced=False,
        )
