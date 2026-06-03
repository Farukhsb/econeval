import builtins
from dataclasses import dataclass

import pytest

from econeval.invariants import evaluate_expression, run_invariant


@dataclass
class DemoModel:
    elasticity: float = -0.4


def test_run_invariant_rejects_function_calls() -> None:
    with pytest.raises(ValueError, match="unsupported syntax: Call"):
        run_invariant("__import__('os').system('echo hi')", {"model": DemoModel()})


def test_run_invariant_rejects_subscripts() -> None:
    with pytest.raises(ValueError, match="subscript access is not allowed"):
        run_invariant("model.values[0] > 0", {"model": DemoModel()})


def test_run_invariant_rejects_dunder_attribute_chains() -> None:
    with pytest.raises(ValueError):
        run_invariant("model.__class__.__bases__[0].__subclasses__()", {"model": DemoModel()})


def test_numexpr_backend_rejects_dangerous_ast() -> None:
    with pytest.raises(ValueError, match="unsupported syntax: Call"):
        evaluate_expression(
            "model.__class__.__bases__[0].__subclasses__()",
            {"model": DemoModel()},
            backend="numexpr",
        )


def test_numexpr_backend_requires_numexpr(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "numexpr":
            raise ImportError("numexpr missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="numexpr is required for numeric expression evaluation"):
        evaluate_expression("value + 1", {"value": 1.0}, backend="numexpr")
