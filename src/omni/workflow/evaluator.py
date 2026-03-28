"""
Expression evaluator for P2-15: Workflow Orchestration.

Provides safe Python expression evaluation for workflow conditions
and collection expressions.
"""

from __future__ import annotations

from typing import Any

from .context import WorkflowContext
from .nodes import Condition, ConditionEvaluationError


class ExpressionEvaluator:
    """
    Safe Python expression evaluator for workflow conditions.

    This evaluator provides a restricted execution environment for
    evaluating Python expressions in workflow conditions, collection
    expressions, and other dynamic parts of workflow definitions.

    Safety features:
    - No access to unsafe builtins (no __import__, no open, etc.)
    - No access to modules
    - Restricted to safe operations only
    """

    # Safe builtins for expression evaluation
    SAFE_BUILTINS: dict[str, Any] = {
        # Basic types and functions
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "sorted": sorted,
        "sum": sum,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "type": type,
        # Constants
        "True": True,
        "False": False,
        "None": None,
        # Data structures
        "dict": dict,
        "list": list,
        "tuple": tuple,
        "set": set,
        "frozenset": frozenset,
        # Iteration helpers
        "enumerate": enumerate,
        "zip": zip,
        "range": range,
        "reversed": reversed,
        # String operations
        "chr": chr,
        "ord": ord,
        "hex": hex,
        "oct": oct,
        "bin": bin,
        # Math operations (safe ones)
        "pow": pow,
        "divmod": divmod,
        # Boolean operations
        "all": all,
        "any": any,
    }

    def __init__(self, additional_safe_globals: dict[str, Any] | None = None):
        """
        Initialize the expression evaluator.

        Args:
            additional_safe_globals: Additional safe globals to make available
                in the evaluation context.
        """
        self.safe_globals = self.SAFE_BUILTINS.copy()
        if additional_safe_globals:
            self.safe_globals.update(additional_safe_globals)

    def evaluate_condition(
        self,
        condition: Condition,
        context: WorkflowContext,
        current_node_id: str | None = None,
    ) -> bool:
        """
        Evaluate a condition expression.

        Args:
            condition: The condition to evaluate.
            context: The workflow context for variable access.
            current_node_id: Optional ID of the current node for iteration count.

        Returns:
            True if the condition evaluates to a truthy value, False otherwise.

        Raises:
            ConditionEvaluationError: If the expression cannot be evaluated.
        """
        try:
            eval_context = context.get_evaluation_context(current_node_id)
            # Add safe globals to the context
            eval_context.update(self.safe_globals)

            result = eval(
                condition.expression,
                {"__builtins__": {}},  # No builtins at all - we add safe ones manually
                eval_context,
            )
            return bool(result)
        except Exception as e:
            raise ConditionEvaluationError(
                f"Failed to evaluate condition '{condition.expression}': {e}"
            ) from e

    def evaluate_collection(
        self,
        expression: str,
        context: WorkflowContext,
        current_node_id: str | None = None,
    ) -> list[Any]:
        """
        Evaluate a collection expression.

        Used for FOR_EACH nodes to get the iterable to loop over.

        Args:
            expression: The Python expression that should evaluate to an iterable.
            context: The workflow context for variable access.
            current_node_id: Optional ID of the current node for iteration count.

        Returns:
            The evaluated collection as a list.

        Raises:
            ConditionEvaluationError: If the expression cannot be evaluated or
                does not return an iterable.
        """
        try:
            eval_context = context.get_evaluation_context(current_node_id)
            # Add safe globals to the context
            eval_context.update(self.safe_globals)

            result = eval(
                expression,
                {"__builtins__": {}},  # No builtins at all - we add safe ones manually
                eval_context,
            )

            # Convert to list if it's iterable
            if hasattr(result, "__iter__"):
                return list(result)
            else:
                raise ConditionEvaluationError(
                    f"Expression '{expression}' did not evaluate to an iterable. "
                    f"Got type: {type(result).__name__}"
                )
        except Exception as e:
            raise ConditionEvaluationError(
                f"Failed to evaluate collection expression '{expression}': {e}"
            ) from e

    def evaluate_expression(
        self,
        expression: str,
        context: WorkflowContext,
        current_node_id: str | None = None,
    ) -> Any:
        """
        Evaluate any Python expression safely.

        Args:
            expression: The Python expression to evaluate.
            context: The workflow context for variable access.
            current_node_id: Optional ID of the current node for iteration count.

        Returns:
            The result of evaluating the expression.

        Raises:
            ConditionEvaluationError: If the expression cannot be evaluated.
        """
        try:
            eval_context = context.get_evaluation_context(current_node_id)
            # Add safe globals to the context
            eval_context.update(self.safe_globals)

            return eval(
                expression,
                {"__builtins__": {}},  # No builtins at all - we add safe ones manually
                eval_context,
            )
        except Exception as e:
            raise ConditionEvaluationError(
                f"Failed to evaluate expression '{expression}': {e}"
            ) from e

    def validate_expression(self, expression: str) -> list[str]:
        """
        Validate that an expression is syntactically valid Python.

        This does NOT evaluate the expression, just checks syntax.

        Args:
            expression: The expression to validate.

        Returns:
            List of validation issues. Empty list means valid.
        """
        issues: list[str] = []

        try:
            compile(expression, "<string>", "eval")
        except SyntaxError as e:
            issues.append(f"Syntax error in expression '{expression}': {e}")
        except Exception as e:
            issues.append(f"Error compiling expression '{expression}': {e}")

        return issues


# Default global instance
_default_evaluator = ExpressionEvaluator()


def evaluate_condition(
    condition: Condition,
    context: WorkflowContext,
    current_node_id: str | None = None,
) -> bool:
    """
    Convenience function to evaluate a condition using the default evaluator.

    Args:
        condition: The condition to evaluate.
        context: The workflow context for variable access.
        current_node_id: Optional ID of the current node for iteration count.

    Returns:
        True if the condition evaluates to a truthy value, False otherwise.
    """
    return _default_evaluator.evaluate_condition(condition, context, current_node_id)


def evaluate_collection(
    expression: str,
    context: WorkflowContext,
    current_node_id: str | None = None,
) -> list[Any]:
    """
    Convenience function to evaluate a collection expression using the default evaluator.

    Args:
        expression: The Python expression that should evaluate to an iterable.
        context: The workflow context for variable access.
        current_node_id: Optional ID of the current node for iteration count.

    Returns:
        The evaluated collection as a list.
    """
    return _default_evaluator.evaluate_collection(expression, context, current_node_id)
