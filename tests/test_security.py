from dataclasses import dataclass

import pytest

from econeval.invariants import run_invariant


@dataclass
class DemoModel:
    elasticity: float = -0.4


def test_run_invariant_rejects_function_calls() -> None:
    with pytest.raises(ValueError, match="function calls are not allowed"):
        run_invariant("__import__('os').system('echo hi')", {"model": DemoModel()})


def test_run_invariant_rejects_subscripts() -> None:
    with pytest.raises(ValueError, match="subscript access is not allowed"):
        run_invariant("model.values[0] > 0", {"model": DemoModel()})

