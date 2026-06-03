from dataclasses import dataclass

from econeval.config import InvariantRule
from econeval.invariants import run_invariant, run_invariant_suite, suite_passed


@dataclass
class DemoModel:
    elasticity: float = -0.4
    supply: float = 10.0


def test_run_invariant_evaluates_expression_against_context() -> None:
    model = DemoModel()

    assert run_invariant("model.elasticity < 0", {"model": model}) is True
    assert run_invariant("model.supply >= 0", {"model": model}) is True


def test_run_invariant_suite_marks_failed_rules() -> None:
    model = DemoModel(elasticity=0.25)
    rules = [
        InvariantRule(name="elasticity_must_be_negative", expression="model.elasticity < 0"),
        InvariantRule(name="supply_must_be_non_negative", expression="model.supply >= 0"),
    ]

    results = run_invariant_suite(model, rules)

    assert results[0].passed is False
    assert results[1].passed is True
    assert suite_passed(results) is False
    assert "elasticity_must_be_negative" in results[0].detail
    assert "model.elasticity < 0" in results[0].detail
