"""
Safe expression evaluator using Python's ast module.

Replaces unsafe eval() usage with a whitelist-based AST evaluator that only
permits safe operations: constants, variable lookups, comparisons, logical
operators, and basic arithmetic.
"""

from __future__ import annotations

import ast
import operator
from typing import Any


class UnsafeExpressionError(Exception):
    """Raised when an expression contains disallowed AST nodes."""


class SafeExpressionEvaluator:
    """
    Evaluates simple Python expressions safely by parsing them into an AST
    and walking only whitelisted node types.

    Allowed constructs:
    - Constants: str, int, float, bool, None
    - Variable lookups from a provided context dict
    - Comparisons: ==, !=, <, <=, >, >=, in, not in, is, is not
    - Logical operators: and, or, not
    - Arithmetic: +, -, *, /
    - Subscript access: x["key"], x[0]
    - Attribute access: x.attr (single level only)
    - Tuple/List/Dict literals

    Rejected constructs:
    - Function calls (including builtins like eval, exec, open, __import__)
    - Import statements
    - Lambda expressions
    - Comprehensions
    - Assignments
    - Any node type not explicitly whitelisted
    """

    # Whitelisted AST node types
    _SAFE_NODES = frozenset({
        ast.Expression,
        ast.BoolOp,
        ast.UnaryOp,
        ast.BinOp,
        ast.Compare,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.And,
        ast.Or,
        ast.Not,
        # Comparison operators
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
        ast.Is,
        ast.IsNot,
        # Arithmetic operators
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        # Unary operators
        ast.UAdd,
        ast.USub,
        # Subscript and attribute access
        ast.Subscript,
        ast.Attribute,
        ast.Index,  # Python 3.8 compat
        # Container literals
        ast.Tuple,
        ast.List,
        ast.Dict,
    })

    # Operator mappings for evaluation
    _COMPARE_OPS = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
    }

    _BIN_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }

    _UNARY_OPS: dict[type, Any] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
        ast.Not: operator.not_,
    }

    def evaluate(self, expr: str, context: dict[str, Any] | None = None) -> Any:
        """
        Safely evaluate an expression string.

        Args:
            expr: The expression string to evaluate.
            context: Dictionary of variable names to values.

        Returns:
            The result of evaluating the expression.

        Raises:
            UnsafeExpressionError: If the expression contains disallowed constructs.
            ValueError: If the expression cannot be parsed.
        """
        if context is None:
            context = {}

        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid expression syntax: {expr}") from e

        self._validate(tree)
        return self._eval_node(tree.body, context)

    def _validate(self, tree: ast.AST) -> None:
        """Walk the AST and reject any disallowed node types."""
        for node in ast.walk(tree):
            node_type = type(node)
            if node_type not in self._SAFE_NODES:
                raise UnsafeExpressionError(
                    f"Disallowed expression element: {node_type.__name__}"
                )

    def _eval_node(self, node: ast.AST, context: dict[str, Any]) -> Any:
        """Recursively evaluate a validated AST node."""
        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            if node.id not in context:
                raise NameError(f"Undefined variable: {node.id}")
            return context[node.id]

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result = True
                for value in node.values:
                    result = self._eval_node(value, context)
                    if not result:
                        return result
                return result
            elif isinstance(node.op, ast.Or):
                result = False
                for value in node.values:
                    result = self._eval_node(value, context)
                    if result:
                        return result
                return result

        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, context)
            op_func = self._UNARY_OPS.get(type(node.op))
            if op_func is None:
                raise UnsafeExpressionError(
                    f"Unsupported unary operator: {type(node.op).__name__}"
                )
            return op_func(operand)

        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            op_func = self._BIN_OPS.get(type(node.op))
            if op_func is None:
                raise UnsafeExpressionError(
                    f"Unsupported binary operator: {type(node.op).__name__}"
                )
            return op_func(left, right)

        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            for op, comparator in zip(node.ops, node.comparators, strict=True):
                right = self._eval_node(comparator, context)
                op_func = self._COMPARE_OPS.get(type(op))
                if op_func is None:
                    raise UnsafeExpressionError(
                        f"Unsupported comparison: {type(op).__name__}"
                    )
                if not op_func(left, right):
                    return False
                left = right
            return True

        if isinstance(node, ast.Subscript):
            value = self._eval_node(node.value, context)
            # Python 3.9+ uses slice directly, 3.8 wraps in ast.Index
            if isinstance(node.slice, ast.Index):
                index = self._eval_node(node.slice.value, context)  # type: ignore[attr-defined]
            else:
                index = self._eval_node(node.slice, context)
            return value[index]

        if isinstance(node, ast.Attribute):
            value = self._eval_node(node.value, context)
            return getattr(value, node.attr)

        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt, context) for elt in node.elts)

        if isinstance(node, ast.List):
            return [self._eval_node(elt, context) for elt in node.elts]

        if isinstance(node, ast.Dict):
            keys = [self._eval_node(k, context) for k in node.keys if k is not None]
            values = [self._eval_node(v, context) for v in node.values]
            return dict(zip(keys, values, strict=True))

        raise UnsafeExpressionError(
            f"Unsupported AST node: {type(node).__name__}"
        )
