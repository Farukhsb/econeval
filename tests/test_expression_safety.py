from dataclasses import dataclass

import pytest

from econeval.invariants import evaluate_expression


@dataclass
class DemoModel:
    elasticity: float = -0.4
    supply: float = 10.0
    growth: float = 0.02


@pytest.mark.parametrize(
    ("expression", "expected_message"),
    [
        ("abs(model.elasticity)", "unsupported syntax: Call"),
        ("model.history[0]", "subscript access is not allowed"),
        ("[x for x in range(3)]", "unsupported syntax: ListComp"),
        ("lambda x: x + 1", "unsupported syntax: Lambda"),
        ("model.__class__", "private attributes are not allowed"),
        ("model.elasticity <", "invalid syntax"),
    ],
)
def test_rejected_expressions_raise_clear_errors(
    expression: str,
    expected_message: str,
) -> None:
    model = DemoModel()

    with pytest.raises((SyntaxError, ValueError)) as exc_info:
        evaluate_expression(expression, {"model": model})

    assert expected_message in str(exc_info.value)


def test_very_long_expression_is_rejected() -> None:
    model = DemoModel()
    expression = "model.elasticity < 0 and " * 200 + "model.supply >= 0"

    with pytest.raises(ValueError) as exc_info:
        evaluate_expression(expression, {"model": model})

    assert "expression is too long" in str(exc_info.value)


@pytest.mark.parametrize(
    "expression",
    [
        "model.elasticity < 0",
        "model.elasticity < 0 and model.supply >= 0",
        "(model.elasticity < 0) or (model.growth > 0)",
        "model.supply + 2 >= 12",
        "not (model.growth < 0)",
    ],
)
def test_allowed_expressions_still_evaluate(expression: str) -> None:
    model = DemoModel()

    result = evaluate_expression(expression, {"model": model})

    assert result is not None


def test_allowed_arithmetic_and_boolean_expression_returns_true() -> None:
    model = DemoModel()

    result = evaluate_expression(
        "(model.elasticity < 0 and model.supply >= 0) or model.growth > 0",
        {"model": model},
    )

    assert result is True
