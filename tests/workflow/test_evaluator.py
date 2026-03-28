"""
Tests for expression evaluator.
"""

import pytest

from src.omni.workflow.context import WorkflowContext
from src.omni.workflow.evaluator import ExpressionEvaluator, evaluate_condition, evaluate_collection
from src.omni.workflow.nodes import Condition, ConditionEvaluationError


def _ctx(variables=None, node_results=None) -> WorkflowContext:
    return WorkflowContext(
        workflow_id="test",
        execution_id="test",
        variables=variables or {},
    )


class TestExpressionEvaluator:
    """Tests for ExpressionEvaluator class."""

    def test_evaluate_simple_condition_true(self):
        ev = ExpressionEvaluator()
        ctx = _ctx(variables={"x": 10})
        cond = Condition("variables['x'] > 5")
        assert ev.evaluate_condition(cond, ctx) is True

    def test_evaluate_simple_condition_false(self):
        ev = ExpressionEvaluator()
        ctx = _ctx(variables={"x": 3})
        cond = Condition("variables['x'] > 5")
        assert ev.evaluate_condition(cond, ctx) is False

    def test_evaluate_with_node_results(self):
        ev = ExpressionEvaluator()
        ctx = _ctx(variables={"score": 0.9})
        cond = Condition("variables['score'] > 0.8")
        assert ev.evaluate_condition(cond, ctx) is True

    def test_evaluate_collection(self):
        ev = ExpressionEvaluator()
        ctx = _ctx(variables={"items": [1, 2, 3]})
        result = ev.evaluate_collection("variables['items']", ctx)
        assert result == [1, 2, 3]

    def test_evaluate_collection_range(self):
        ev = ExpressionEvaluator()
        ctx = _ctx()
        result = ev.evaluate_collection("range(5)", ctx)
        assert result == [0, 1, 2, 3, 4]

    def test_evaluate_invalid_expression(self):
        ev = ExpressionEvaluator()
        ctx = _ctx(variables={"x": 1})
        cond = Condition("variables.missing > 0")
        with pytest.raises(ConditionEvaluationError):
            ev.evaluate_condition(cond, ctx)

    def test_evaluate_collection_non_iterable(self):
        ev = ExpressionEvaluator()
        ctx = _ctx(variables={"x": 42})
        with pytest.raises(ConditionEvaluationError):
            ev.evaluate_collection("variables['x']", ctx)

    def test_safe_builtins_available(self):
        ev = ExpressionEvaluator()
        ctx = _ctx(variables={"items": [3, 1, 2]})
        cond = Condition("len(variables['items']) == 3")
        assert ev.evaluate_condition(cond, ctx) is True

        cond2 = Condition("sorted(variables['items']) == [1, 2, 3]")
        assert ev.evaluate_condition(cond2, ctx) is True

        cond3 = Condition("sum(variables['items']) == 6")
        assert ev.evaluate_condition(cond3, ctx) is True

    def test_unsafe_builtins_blocked(self):
        ev = ExpressionEvaluator()
        ctx = _ctx()
        # __import__ is not available
        cond = Condition("__import__('os')")
        with pytest.raises(ConditionEvaluationError):
            ev.evaluate_condition(cond, ctx)

    def test_validate_expression_syntax(self):
        ev = ExpressionEvaluator()
        assert ev.validate_expression("variables['x'] > 0") == []
        issues = ev.validate_expression("variables['x' > ")
        assert len(issues) == 1

    def test_additional_safe_globals(self):
        ev = ExpressionEvaluator(additional_safe_globals={"custom_fn": lambda x: x * 2})
        ctx = _ctx(variables={"x": 5})
        cond = Condition("custom_fn(variables['x']) == 10")
        assert ev.evaluate_condition(cond, ctx) is True

    def test_evaluate_expression_general(self):
        ev = ExpressionEvaluator()
        ctx = _ctx(variables={"x": 3, "y": 4})
        result = ev.evaluate_expression("variables['x'] + variables['y']", ctx)
        assert result == 7

    def test_convenience_function_evaluate_condition(self):
        ctx = _ctx(variables={"go": True})
        cond = Condition("variables['go']")
        assert evaluate_condition(cond, ctx) is True

    def test_convenience_function_evaluate_collection(self):
        ctx = _ctx(variables={"items": [10, 20]})
        result = evaluate_collection("variables['items']", ctx)
        assert result == [10, 20]

    def test_iteration_in_context(self):
        ev = ExpressionEvaluator()
        ctx = _ctx()
        ctx.increment_iteration("loop1")
        ctx.increment_iteration("loop1")
        cond = Condition("iteration >= 2")
        assert ev.evaluate_condition(cond, ctx, "loop1") is True
