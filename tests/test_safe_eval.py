"""Tests for SafeExpressionEvaluator — safe replacement for eval()."""

from __future__ import annotations

import pytest

from src.omni.orchestration.safe_eval import (
    SafeExpressionEvaluator,
    UnsafeExpressionError,
)


@pytest.fixture
def evaluator() -> SafeExpressionEvaluator:
    return SafeExpressionEvaluator()


# ---------------------------------------------------------------------------
# Basic constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_true(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("True") is True

    def test_false(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("False") is False

    def test_none(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("None") is None

    def test_integer(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("42") == 42

    def test_float(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("3.14") == pytest.approx(3.14)

    def test_string(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("'hello'") == "hello"


# ---------------------------------------------------------------------------
# Variable lookups
# ---------------------------------------------------------------------------


class TestVariables:
    def test_simple_variable(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x", {"x": True}) is True

    def test_variable_value(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x", {"x": 42}) == 42

    def test_undefined_variable_raises(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(NameError, match="Undefined variable"):
            evaluator.evaluate("x", {})


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------


class TestComparisons:
    def test_greater_than(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x > 5", {"x": 10}) is True
        assert evaluator.evaluate("x > 5", {"x": 3}) is False

    def test_less_than(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x < 5", {"x": 3}) is True

    def test_equal(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x == 'hello'", {"x": "hello"}) is True
        assert evaluator.evaluate("x == 'hello'", {"x": "world"}) is False

    def test_not_equal(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x != 5", {"x": 3}) is True

    def test_greater_equal(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x >= 5", {"x": 5}) is True

    def test_less_equal(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x <= 5", {"x": 5}) is True

    def test_in_operator(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x in [1, 2, 3]", {"x": 2}) is True
        assert evaluator.evaluate("x in [1, 2, 3]", {"x": 4}) is False

    def test_not_in_operator(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x not in [1, 2, 3]", {"x": 4}) is True

    def test_chained_comparison(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("1 < x < 10", {"x": 5}) is True
        assert evaluator.evaluate("1 < x < 10", {"x": 15}) is False


# ---------------------------------------------------------------------------
# Logical operators
# ---------------------------------------------------------------------------


class TestLogicalOperators:
    def test_and(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x and y", {"x": True, "y": True}) is True
        assert evaluator.evaluate("x and y", {"x": True, "y": False}) is False

    def test_or(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x or y", {"x": False, "y": True}) is True
        assert evaluator.evaluate("x or y", {"x": False, "y": False}) is False

    def test_not(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("not x", {"x": False}) is True
        assert evaluator.evaluate("not x", {"x": True}) is False


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------


class TestArithmetic:
    def test_addition(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x + y", {"x": 3, "y": 7}) == 10

    def test_subtraction(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x - y", {"x": 10, "y": 3}) == 7

    def test_multiplication(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x * y", {"x": 4, "y": 5}) == 20

    def test_division(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x / y", {"x": 10, "y": 2}) == pytest.approx(5.0)

    def test_arithmetic_in_comparison(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x + y > 10", {"x": 7, "y": 5}) is True
        assert evaluator.evaluate("x + y > 10", {"x": 3, "y": 5}) is False

    def test_unary_minus(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("-x", {"x": 5}) == -5


# ---------------------------------------------------------------------------
# Nested / complex expressions
# ---------------------------------------------------------------------------


class TestNestedExpressions:
    def test_nested_comparison_and(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("(x > 5) and (y < 10)", {"x": 7, "y": 3}) is True
        assert evaluator.evaluate("(x > 5) and (y < 10)", {"x": 3, "y": 3}) is False

    def test_nested_comparison_or(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("(x > 5) or (y < 10)", {"x": 3, "y": 3}) is True

    def test_complex_expression(self, evaluator: SafeExpressionEvaluator) -> None:
        expr = "(x + y > 10) and (z == 'active')"
        ctx = {"x": 7, "y": 5, "z": "active"}
        assert evaluator.evaluate(expr, ctx) is True

    def test_subscript_access(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("data['key']", {"data": {"key": 42}}) == 42

    def test_list_subscript(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("items[0]", {"items": [10, 20, 30]}) == 10

    def test_tuple_literal(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("(1, 2, 3)") == (1, 2, 3)

    def test_list_literal(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("[1, 2, 3]") == [1, 2, 3]

    def test_dict_literal(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("{'a': 1}") == {"a": 1}


# ---------------------------------------------------------------------------
# SECURITY: These must all be REJECTED
# ---------------------------------------------------------------------------


class TestSecurityRejections:
    """Verify that dangerous expressions are rejected with UnsafeExpressionError."""

    def test_reject_import(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(UnsafeExpressionError):
            evaluator.evaluate("__import__('os').system('echo hacked')")

    def test_reject_open(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(UnsafeExpressionError):
            evaluator.evaluate("open('/etc/passwd').read()")

    def test_reject_class_traversal(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(UnsafeExpressionError):
            evaluator.evaluate("().__class__.__bases__[0].__subclasses__()")

    def test_reject_eval(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(UnsafeExpressionError):
            evaluator.evaluate("eval('1+1')")

    def test_reject_exec(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises((UnsafeExpressionError, ValueError)):
            evaluator.evaluate("exec('import os')")

    def test_reject_lambda(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(UnsafeExpressionError):
            evaluator.evaluate("(lambda: 1)()")

    def test_reject_list_comprehension(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(UnsafeExpressionError):
            evaluator.evaluate("[x for x in range(10)]")

    def test_reject_getattr_call(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(UnsafeExpressionError):
            evaluator.evaluate("getattr(__builtins__, 'eval')('1')")

    def test_reject_type_call(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(UnsafeExpressionError):
            evaluator.evaluate("type('X', (), {})")

    def test_reject_nested_function_call(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(UnsafeExpressionError):
            evaluator.evaluate("print('pwned')")

    def test_reject_dunder_access_with_call(
        self, evaluator: SafeExpressionEvaluator
    ) -> None:
        with pytest.raises(UnsafeExpressionError):
            evaluator.evaluate("''.__class__.__mro__[1].__subclasses__()")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_context(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("True") is True

    def test_none_context(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("42", None) == 42

    def test_invalid_syntax(self, evaluator: SafeExpressionEvaluator) -> None:
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            evaluator.evaluate("if x:")

    def test_is_operator(self, evaluator: SafeExpressionEvaluator) -> None:
        assert evaluator.evaluate("x is None", {"x": None}) is True
        assert evaluator.evaluate("x is not None", {"x": 42}) is True
