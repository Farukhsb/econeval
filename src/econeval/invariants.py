"""Invariant evaluation helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from .config import InvariantRule

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
    ast.List,
    ast.Tuple,
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

_SAFE_FUNCTIONS = {
    "abs": abs,
    "all": all,
    "any": any,
    "len": len,
    "max": max,
    "min": min,
    "round": round,
    "sum": sum,
}

_NUMEXPR_FUNCTIONS = {
    "abs",
    "arccos",
    "arccosh",
    "arcsin",
    "arcsinh",
    "arctan",
    "arctan2",
    "arctanh",
    "cos",
    "cosh",
    "copysign",
    "exp",
    "expm1",
    "fabs",
    "floor",
    "fmod",
    "hypot",
    "imag",
    "isfinite",
    "isinf",
    "isnan",
    "log",
    "log10",
    "log1p",
    "maximum",
    "minimum",
    "nextafter",
    "pow",
    "real",
    "round",
    "sign",
    "signbit",
    "sin",
    "sinh",
    "sqrt",
    "tan",
    "tanh",
    "where",
}


@dataclass(slots=True)
class InvariantResult:
    name: str
    expression: str
    passed: bool
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

    selected_backend = _select_backend(expression, context, backend)
    if selected_backend == "numexpr":
        return _evaluate_numexpr(expression, context)
    if selected_backend == "asteval":
        return _evaluate_asteval(expression, context)
    return _evaluate_python_ast(expression, context)


def run_invariant_suite(model: Any, rules: list[InvariantRule]) -> list[InvariantResult]:
    """Run a list of invariant rules against a model object."""

    context = {"model": model}
    results: list[InvariantResult] = []

    for rule in rules:
        try:
            passed = _as_bool(evaluate_expression(rule.expression, context, backend=rule.backend))
            results.append(
                InvariantResult(
                    name=rule.name,
                    expression=rule.expression,
                    passed=passed,
                    detail=(
                        None
                        if passed
                        else _format_rule_error(
                            rule,
                            "expression evaluated to False",
                        )
                    ),
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


def _evaluate_python_ast(expression: str, context: dict[str, Any]) -> Any:
    tree = ast.parse(expression, mode="eval")
    _validate_expression(tree)
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

    if isinstance(node, ast.Call):
        return _evaluate_call(node, context)

    if isinstance(node, ast.List):
        return [_evaluate_node(element, context) for element in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_evaluate_node(element, context) for element in node.elts)

    raise ValueError(f"unsupported expression: {type(node).__name__}")


def _validate_expression(tree: ast.Expression) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            raise ValueError("subscript access is not allowed in invariant expressions")

        if isinstance(node, ast.Call):
            _validate_call(node)
            continue

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
            | ast.GeneratorExp,
        ):
            raise ValueError(f"unsupported syntax: {type(node).__name__}")


def _validate_call(node: ast.Call) -> None:
    if not isinstance(node.func, ast.Name):
        raise ValueError("only simple function calls are allowed in invariant expressions")

    if node.func.id not in _SAFE_FUNCTIONS:
        raise ValueError(f"function {node.func.id!r} is not allowed in invariant expressions")


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


def _evaluate_call(node: ast.Call, context: dict[str, Any]) -> Any:
    name = _call_name(node)
    func = _SAFE_FUNCTIONS[name]
    args = [_evaluate_node(arg, context) for arg in node.args]
    kwargs = {keyword.arg: _evaluate_node(keyword.value, context) for keyword in node.keywords}
    return func(*args, **kwargs)


def _call_name(node: ast.Call) -> str:
    if not isinstance(node.func, ast.Name):
        raise ValueError("only simple function calls are allowed in invariant expressions")
    return node.func.id


def _evaluate_numexpr(expression: str, context: dict[str, Any]) -> Any:
    try:
        import numexpr as ne
    except ImportError:
        return _evaluate_asteval(expression, context)

    try:
        return ne.evaluate(expression, local_dict=context)
    except Exception as exc:
        raise ValueError(f"numexpr evaluation failed: {exc}") from exc


def _evaluate_asteval(expression: str, context: dict[str, Any]) -> Any:
    try:
        from asteval import Interpreter
    except ImportError:
        return _evaluate_python_ast(expression, context)

    interpreter = Interpreter(symtable={**_SAFE_FUNCTIONS, **context}, minimal=True, use_numpy=True)
    result = interpreter(expression)
    if getattr(interpreter, "error", None):
        message = getattr(interpreter.error[0], "get_error", lambda: str(interpreter.error[0]))()
        raise ValueError(str(message))
    return result


def _select_backend(expression: str, context: dict[str, Any], backend: str) -> str:
    if backend != "auto":
        return backend
    if _is_numexpr_candidate(expression, context):
        return "numexpr"
    return "asteval"


def _is_numexpr_candidate(expression: str, context: dict[str, Any]) -> bool:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.Attribute,
                ast.Subscript,
                ast.Dict,
                ast.Set,
                ast.Lambda,
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
            ),
        ):
            return False

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return False

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _NUMEXPR_FUNCTIONS:
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
