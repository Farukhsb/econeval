from dataclasses import dataclass

import pytest

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
    assert results[0].detail is not None
    assert "model.elasticity evaluated to 0.25" in results[0].detail
    assert "expected < 0" in results[0].detail
    assert "elasticity_must_be_negative" in results[0].detail
    assert "model.elasticity < 0" in results[0].detail
    assert results[0].value is False
    assert results[0].trace is not None
    assert "model.elasticity=0.25" in results[0].trace
    assert "(failed)" in results[0].trace


def test_run_invariant_suite_scales_to_many_rules() -> None:
    model = DemoModel()
    rules = [
        InvariantRule(name=f"elasticity_rule_{idx}", expression="model.elasticity < 0")
        for idx in range(100)
    ]

    results = run_invariant_suite(model, rules)

    assert len(results) == 100
    assert all(result.passed for result in results)


def test_run_invariant_suite_includes_blame_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = DemoModel(elasticity=0.25)
    rules = [
        InvariantRule(name="elasticity_must_be_negative", expression="model.elasticity < 0"),
    ]

    monkeypatch.setattr(
        "econeval.invariants.collect_invariant_blame",
        lambda model, rule: [
            {
                "path": "models/demo.py",
                "line": 12,
                "commit": "abc123def456",
                "author": "Ada Lovelace",
                "summary": "Tune elasticity rule",
                "pull_request": 42,
            }
        ],
    )

    results = run_invariant_suite(model, rules, trace_failures=True)

    assert results[0].passed is False
    assert results[0].blame is not None
    assert results[0].blame[0]["commit"] == "abc123def456"
    assert results[0].blame[0]["pull_request"] == 42
