from dataclasses import dataclass
from pathlib import Path

import pytest

from econeval.config import DriftTest, StressTest
from econeval.scenarios import (
    fairness_suite_passed,
    drift_suite_passed,
    run_drift_suite,
    run_fairness_checks,
    run_stress_test,
    suite_passed,
)


@dataclass
class DemoModel:
    def predict(self, features: dict[str, float]) -> float:
        shock = float(features.get("shock", 0.0))
        return 1.0 + 2.0 * shock


def test_run_stress_test_passes_on_matching_dataset() -> None:
    root = Path(__file__).resolve().parents[1]
    model = DemoModel()
    test = StressTest(
        name="stagflation_shock",
        dataset=str(root / "examples" / "basic_model" / "data" / "stagflation.csv"),
        metric="mape",
        threshold=0.01,
    )

    result = run_stress_test(model, test)

    assert result.passed is True
    assert result.value == 0.0
    assert suite_passed([result]) is True


def test_run_stress_test_fails_when_predictions_drift() -> None:
    root = Path(__file__).resolve().parents[1]
    model = DemoModel()
    test = StressTest(
        name="broken_shock",
        dataset=str(root / "examples" / "broken_model" / "data" / "stagflation.csv"),
        metric="mape",
        threshold=0.01,
    )

    result = run_stress_test(model, test)

    assert result.passed is False
    assert result.value > test.threshold
    assert suite_passed([result]) is False


def test_run_drift_suite_passes_for_small_shift() -> None:
    root = Path(__file__).resolve().parents[1]
    test = DriftTest(
        name="shock_feature_stability",
        baseline_dataset=str(root / "examples" / "basic_model" / "data" / "baseline.csv"),
        dataset=str(root / "examples" / "basic_model" / "data" / "current.csv"),
        feature="shock",
        threshold=0.05,
    )

    results = run_drift_suite([test])

    assert results[0].passed is True
    assert results[0].value == pytest.approx(0.01)
    assert drift_suite_passed(results) is True


def test_run_fairness_checks_pass_for_balanced_groups() -> None:
    root = Path(__file__).resolve().parents[1]
    model = DemoModel()
    results = run_fairness_checks(
        model,
        dataset=str(root / "examples" / "basic_model" / "data" / "fairness.csv"),
        metrics=["demographic_parity_difference", "disparate_impact_ratio"],
        group_column="group",
        positive_threshold=1.5,
    )

    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is True
    assert fairness_suite_passed(results) is True
