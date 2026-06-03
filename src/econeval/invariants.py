"""Invariant evaluation helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from .config import InvariantRule


@dataclass(slots=True)
class InvariantResult:
    name: str
    expression: str
    passed: bool
    error: str | None = None


def check_invariant(name: str, passed: bool) -> dict[str, object]:
    """Return a normalized invariant payload."""

    return {
        "name": name,
        "passed": passed,
    }


def run_invariant(expression: str, context: dict[str, Any]) -> bool:
    """Evaluate a single invariant expression against a context."""

    tree = ast.parse(expression, mode="eval")
    return bool(_evaluate_node(tree.body, context))


def run_invariant_suite(model: Any, rules: list[InvariantRule]) -> list[InvariantResult]:
    """Run a list of invariant rules against a model object."""

    context = {"model": model}
    results: list[InvariantResult] = []

    for rule in rules:
        try:
            passed = run_invariant(rule.expression, context)
            results.append(
                InvariantResult(
                    name=rule.name,
                    expression=rule.expression,
                    passed=passed,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            results.append(
                InvariantResult(
                    name=rule.name,
                    expression=rule.expression,
                    passed=False,
                    error=str(exc),
                )
            )

    return results


def suite_passed(results: list[InvariantResult]) -> bool:
    return all(result.passed for result in results)


def _evaluate_node(node: ast.AST, context: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id not in context:
            raise ValueError(f"unknown name: {node.id}")
        return context[node.id]

    if isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise ValueError("private attributes are not allowed")
        base = _evaluate_node(node.value, context)
        return getattr(base, node.attr)

    if isinstance(node, ast.Compare):
        left = _evaluate_node(node.left, context)
        for operator, comparator in zip(node.ops, node.comparators, strict=True):
            right = _evaluate_node(comparator, context)
            if not _compare(operator, left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(bool(_evaluate_node(value, context)) for value in node.values)
        if isinstance(node.op, ast.Or):
            return any(bool(_evaluate_node(value, context)) for value in node.values)
        raise ValueError(f"unsupported boolean operator: {type(node.op).__name__}")

    if isinstance(node, ast.UnaryOp):
        operand = _evaluate_node(node.operand, context)
        if isinstance(node.op, ast.Not):
            return not bool(operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        left = _evaluate_node(node.left, context)
        right = _evaluate_node(node.right, context)
        return _apply_binop(node.op, left, right)

    if isinstance(node, ast.List):
        return [_evaluate_node(element, context) for element in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_evaluate_node(element, context) for element in node.elts)

    raise ValueError(f"unsupported expression: {type(node).__name__}")


def _compare(operator: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(operator, ast.Eq):
        return left == right
    if isinstance(operator, ast.NotEq):
        return left != right
    if isinstance(operator, ast.Lt):
        return left < right
    if isinstance(operator, ast.LtE):
        return left <= right
    if isinstance(operator, ast.Gt):
        return left > right
    if isinstance(operator, ast.GtE):
        return left >= right
    if isinstance(operator, ast.In):
        return left in right
    if isinstance(operator, ast.NotIn):
        return left not in right
    if isinstance(operator, ast.Is):
        return left is right
    if isinstance(operator, ast.IsNot):
        return left is not right
    raise ValueError(f"unsupported comparator: {type(operator).__name__}")


def _apply_binop(operator: ast.operator, left: Any, right: Any) -> Any:
    if isinstance(operator, ast.Add):
        return left + right
    if isinstance(operator, ast.Sub):
        return left - right
    if isinstance(operator, ast.Mult):
        return left * right
    if isinstance(operator, ast.Div):
        return left / right
    if isinstance(operator, ast.FloorDiv):
        return left // right
    if isinstance(operator, ast.Mod):
        return left % right
    if isinstance(operator, ast.Pow):
        return left**right
    raise ValueError(f"unsupported binary operator: {type(operator).__name__}")
