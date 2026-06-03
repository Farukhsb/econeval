"""Invariant evaluation helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from .config import InvariantRule
from .traceability import collect_invariant_blame

_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Constant,
)

_ALLOWED_BINOPS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
)

_ALLOWED_BOOL_OPS = (ast.And, ast.Or)

_ALLOWED_UNARY_OPS = (ast.Not, ast.UAdd, ast.USub)

_ALLOWED_COMPARE_OPS = (
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
)


@dataclass(slots=True)
class InvariantResult:
    name: str
    expression: str
    passed: bool
    value: Any | None = None
    trace: str | None = None
    blame: list[dict[str, Any]] | None = None
    detail: str | None = None
    error: str | None = None
    error_type: str | None = None


def run_invariant(expression: str, context: dict[str, Any]) -> bool:
    """Evaluate a single invariant expression against a context."""

    return _as_bool(evaluate_expression(expression, context))


def evaluate_expression(
    expression: str,
    context: dict[str, Any],
    backend: str = "auto",
) -> Any:
    """Evaluate a restricted expression and return its raw value."""

    tree = _validate_expression(expression)
    selected_backend = _select_backend(expression, context, backend)
    if selected_backend == "numexpr":
        return _evaluate_numexpr(expression, context, tree)
    return _evaluate_python_ast(expression, context, tree)


def run_invariant_suite(
    model: Any,
    rules: list[InvariantRule],
    *,
    trace_failures: bool = False,
) -> list[InvariantResult]:
    """Run a list of invariant rules against a model object."""

    context = {"model": model}
    results: list[InvariantResult] = []

    for rule in rules:
        try:
            value = evaluate_expression(rule.expression, context, backend=rule.backend)
            passed = _as_bool(value)
            results.append(
                InvariantResult(
                    name=rule.name,
                    expression=rule.expression,
                    passed=passed,
                    value=value,
                    trace=None if passed else _describe_failure_trace(rule, context, value),
                    blame=(
                        None
                        if passed or not trace_failures
                        else collect_invariant_blame(model, rule)
                    ),
                    detail=None if passed else _describe_failed_expression(rule, context),
                )
            )
        except SyntaxError as exc:
            results.append(
                InvariantResult(
                    name=rule.name,
                    expression=rule.expression,
                    passed=False,
                    error=_format_rule_error(rule, f"syntax error: {exc.msg}"),
                    error_type="expression",
                )
            )
        except ValueError as exc:
            results.append(
                InvariantResult(
                    name=rule.name,
                    expression=rule.expression,
                    passed=False,
                    error=_format_rule_error(rule, str(exc)),
                    error_type="expression",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            results.append(
                InvariantResult(
                    name=rule.name,
                    expression=rule.expression,
                    passed=False,
                    error=_format_rule_error(rule, str(exc)),
                    error_type="runtime",
                )
            )

    return results


def suite_passed(results: list[InvariantResult]) -> bool:
    return all(result.passed for result in results)


def _format_rule_error(rule: InvariantRule, message: str) -> str:
    return f"{message} [name={rule.name}, backend={rule.backend}, expression={rule.expression}]"


def _describe_failed_expression(rule: InvariantRule, context: dict[str, Any]) -> str:
    try:
        tree = _validate_expression(rule.expression)
    except SyntaxError:
        return _format_rule_error(rule, "expression evaluated to False")

    detail = _describe_compare_failure(tree.body, context)
    if detail is not None:
        return _format_rule_error(rule, detail)

    try:
        value = _evaluate_node(tree.body, context)
    except Exception:
        return _format_rule_error(rule, "expression evaluated to False")

    return _format_rule_error(rule, f"expression evaluated to False (value={value!r})")


def _describe_failure_trace(
    rule: InvariantRule,
    context: dict[str, Any],
    value: Any,
) -> str:
    try:
        tree = _validate_expression(rule.expression)
    except SyntaxError:
        return _format_rule_error(rule, f"failed with value={value!r}")

    detail = _describe_compare_trace(tree.body, context, value)
    if detail is not None:
        return _format_rule_error(rule, detail)

    return _format_rule_error(rule, f"expression value={value!r} (failed)")


def _describe_compare_trace(
    node: ast.AST,
    context: dict[str, Any],
    value: Any,
) -> str | None:
    if not isinstance(node, ast.Compare):
        return None

    left_node = node.left
    left_text = _safe_unparse(left_node)
    left_value = _evaluate_node(left_node, context)

    for operator, comparator in zip(node.ops, node.comparators, strict=True):
        right_text = _safe_unparse(comparator)
        right_value = _evaluate_node(comparator, context)
        if not _compare(operator, left_value, right_value):
            symbol = _operator_symbol(operator)
            return (
                f"{left_text}={left_value!r} (failed); "
                f"expected {symbol} {right_text} (got {right_value!r}); "
                f"expression value={value!r}"
            )
        left_text = right_text
        left_value = right_value

    return None


def _describe_compare_failure(node: ast.AST, context: dict[str, Any]) -> str | None:
    if not isinstance(node, ast.Compare):
        return None

    left_node = node.left
    left_text = _safe_unparse(left_node)
    left_value = _evaluate_node(left_node, context)

    for operator, comparator in zip(node.ops, node.comparators, strict=True):
        right_text = _safe_unparse(comparator)
        right_value = _evaluate_node(comparator, context)
        if not _compare(operator, left_value, right_value):
            symbol = _operator_symbol(operator)
            return (
                f"{left_text} evaluated to {left_value!r}; "
                f"expected {symbol} {right_text} (got {right_value!r})"
            )
        left_text = right_text
        left_value = right_value

    return None


def _safe_unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive fallback
        return type(node).__name__


def _operator_symbol(operator: ast.cmpop) -> str:
    if isinstance(operator, ast.Eq):
        return "=="
    if isinstance(operator, ast.NotEq):
        return "!="
    if isinstance(operator, ast.Lt):
        return "<"
    if isinstance(operator, ast.LtE):
        return "<="
    if isinstance(operator, ast.Gt):
        return ">"
    if isinstance(operator, ast.GtE):
        return ">="
    if isinstance(operator, ast.In):
        return "in"
    if isinstance(operator, ast.NotIn):
        return "not in"
    if isinstance(operator, ast.Is):
        return "is"
    if isinstance(operator, ast.IsNot):
        return "is not"
    return type(operator).__name__


def _evaluate_python_ast(
    expression: str,
    context: dict[str, Any],
    tree: ast.Expression | None = None,
) -> Any:
    parsed = tree or _validate_expression(expression)
    return _evaluate_python_ast_tree(parsed, context)


def _evaluate_python_ast_tree(tree: ast.Expression, context: dict[str, Any]) -> Any:
    return _evaluate_node(tree.body, context)


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
    raise ValueError(f"unsupported expression: {type(node).__name__}")


def _validate_expression(expression: str) -> ast.Expression:
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            raise ValueError("subscript access is not allowed in invariant expressions")

        if not isinstance(
            node,
            _ALLOWED_NODES
            + _ALLOWED_BINOPS
            + _ALLOWED_BOOL_OPS
            + _ALLOWED_UNARY_OPS
            + _ALLOWED_COMPARE_OPS,
        ):
            raise ValueError(f"unsupported syntax: {type(node).__name__}")

        if isinstance(node, ast.BinOp) and not isinstance(node.op, _ALLOWED_BINOPS):
            raise ValueError(f"unsupported binary operator: {type(node.op).__name__}")

        if isinstance(node, ast.BoolOp) and not isinstance(node.op, _ALLOWED_BOOL_OPS):
            raise ValueError(f"unsupported boolean operator: {type(node.op).__name__}")

        if isinstance(node, ast.UnaryOp) and not isinstance(node.op, _ALLOWED_UNARY_OPS):
            raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")

        if isinstance(node, ast.Compare):
            for operator in node.ops:
                if not isinstance(operator, _ALLOWED_COMPARE_OPS):
                    raise ValueError(f"unsupported comparator: {type(operator).__name__}")

        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError("private attributes are not allowed")

        if isinstance(
            node,
            ast.Dict
            | ast.Set
            | ast.Lambda
            | ast.ListComp
            | ast.SetComp
            | ast.DictComp
            | ast.GeneratorExp
            | ast.List
            | ast.Tuple
            | ast.Call,
        ):
            raise ValueError(f"unsupported syntax: {type(node).__name__}")

    return tree


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


def _evaluate_numexpr(
    expression: str,
    context: dict[str, Any],
    tree: ast.Expression,
) -> Any:
    try:
        import numexpr as ne
    except ImportError as exc:
        raise RuntimeError("numexpr is required for numeric expression evaluation") from exc

    try:
        return ne.evaluate(expression, local_dict=context)
    except Exception as exc:
        raise ValueError(f"numexpr evaluation failed: {exc}") from exc


def _select_backend(expression: str, context: dict[str, Any], backend: str) -> str:
    if backend == "numexpr":
        if not _is_numexpr_candidate(expression, context):
            raise ValueError("expression is not compatible with the numexpr backend")
        return backend
    if backend != "auto":
        raise ValueError(f"unsupported backend: {backend}")
    if _is_numexpr_candidate(expression, context):
        return "numexpr"
    return "python"


def _is_numexpr_candidate(expression: str, context: dict[str, Any]) -> bool:
    try:
        tree = _validate_expression(expression)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return False

    return all(_is_numexpr_value(value) for value in context.values())


def _is_numexpr_value(value: Any) -> bool:
    if isinstance(value, bool | int | float | complex):
        return True
    if isinstance(value, list | tuple):
        return all(_is_numexpr_value(item) for item in value)
    return hasattr(value, "__array__")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float | complex):
        return bool(value)
    if isinstance(value, list | tuple | set | frozenset):
        return all(_as_bool(item) for item in value)
    if hasattr(value, "all") and callable(value.all):
        return bool(value.all())
    return bool(value)
