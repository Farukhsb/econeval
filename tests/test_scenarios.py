from dataclasses import dataclass
from pathlib import Path

import pytest

from econeval.config import DriftTest, EconomicDriftTest, StressTest
from econeval.scenarios import (
    drift_suite_passed,
    economic_drift_suite_passed,
    fairness_suite_passed,
    run_drift_suite,
    run_economic_drift_suite,
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
    assert result.visual is not None
    assert suite_passed([result]) is False


def test_run_stress_test_contains_dataset_errors(tmp_path: Path) -> None:
    dataset = tmp_path / "invalid_stress.csv"
    dataset.write_text("shock,prediction\n0.1,1.2\n", encoding="utf-8")

    model = DemoModel()
    test = StressTest(
        name="malformed_dataset",
        dataset=str(dataset),
        metric="mape",
        threshold=0.1,
    )

    result = run_stress_test(model, test)

    assert result.passed is False
    assert result.error_type == "dataset_or_metric"
    assert result.error is not None
    assert "actual" in result.error
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


def test_run_drift_suite_passes_for_trend_shift() -> None:
    root = Path(__file__).resolve().parents[1]
    test = DriftTest(
        name="shock_feature_trend_shift",
        baseline_dataset=str(root / "examples" / "drift_model" / "data" / "trend_baseline.csv"),
        dataset=str(root / "examples" / "drift_model" / "data" / "trend_current.csv"),
        feature="shock",
        threshold=0.02,
        mode="trend",
        time_column="period",
    )

    results = run_drift_suite([test])

    assert results[0].passed is True
    assert results[0].mode == "trend"
    assert results[0].time_column == "period"
    assert results[0].baseline_value == pytest.approx(0.02)
    assert results[0].current_value == pytest.approx(0.03)
    assert results[0].value == pytest.approx(0.01)


def test_run_drift_suite_passes_for_regression_shift() -> None:
    root = Path(__file__).resolve().parents[1]
    test = DriftTest(
        name="shock_feature_regression_shift",
        baseline_dataset=str(root / "examples" / "drift_model" / "data" / "trend_baseline.csv"),
        dataset=str(root / "examples" / "drift_model" / "data" / "trend_current.csv"),
        feature="shock",
        threshold=0.02,
        mode="regression",
        time_column="period",
    )

    results = run_drift_suite([test])

    assert results[0].passed is True
    assert results[0].mode == "regression"
    assert results[0].backend in {"manual", "statsmodels"}
    assert results[0].value == pytest.approx(0.01)


def test_run_economic_drift_suite_passes_for_small_output_shift() -> None:
    root = Path(__file__).resolve().parents[1]

    class EconomicDriftModel(DemoModel):
        def predict(self, features: dict[str, float]) -> float:
            shock = float(features.get("shock", 0.0))
            return 1.0 + shock

    test = EconomicDriftTest(
        name="predicted_mean_shift",
        baseline_dataset=str(root / "examples" / "advanced_model" / "data" / "baseline.csv"),
        dataset=str(root / "examples" / "advanced_model" / "data" / "current.csv"),
        output="mean_prediction",
        metric="relative_change",
        threshold=0.02,
    )

    results = run_economic_drift_suite(EconomicDriftModel(), [test])

    assert results[0].passed is True
    assert economic_drift_suite_passed(results) is True


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
    assert results[0].severity == "pass"
    assert results[1].passed is True
    assert results[1].severity == "pass"
    assert fairness_suite_passed(results) is True


def test_run_fairness_checks_marks_borderline_ratio_as_warn(tmp_path: Path) -> None:
    dataset = tmp_path / "borderline_fairness.csv"
    dataset.write_text(
        "group,signal,actual\na,0.9,1.0\na,0.8,1.0\na,0.7,0.0\na,0.1,0.0\nb,0.9,1.0\nb,0.8,1.0\nb,0.1,0.0\nb,0.2,0.0\n",
        encoding="utf-8",
    )

    class SignalModel:
        def predict(self, features: dict[str, float]) -> float:
            return float(features.get("signal", 0.0))

    results = run_fairness_checks(
        SignalModel(),
        dataset=str(dataset),
        metrics=["demographic_parity_difference"],
        group_column="group",
        positive_threshold=0.5,
        actual_threshold=0.5,
    )

    assert results[0].passed is False
    assert results[0].severity == "warn"
    assert fairness_suite_passed(results) is True


def test_run_fairness_checks_support_equal_opportunity_and_odds(tmp_path: Path) -> None:
    dataset = tmp_path / "fairness.csv"
    dataset.write_text(
        "group,signal,actual\na,0.1,0.0\na,0.9,1.0\nb,0.2,0.0\nb,0.8,1.0\n",
        encoding="utf-8",
    )

    class SignalModel:
        def predict(self, features: dict[str, float]) -> float:
            return float(features.get("signal", 0.0))

    results = run_fairness_checks(
        SignalModel(),
        dataset=str(dataset),
        metrics=[
            "equal_opportunity_difference",
            "equalized_odds_difference",
        ],
        group_column="group",
        positive_threshold=0.5,
        actual_threshold=0.5,
    )

    assert [result.metric for result in results] == [
        "equal_opportunity_difference",
        "equalized_odds_difference",
    ]
    assert all(result.passed for result in results)
    assert fairness_suite_passed(results) is True


def test_run_fairness_checks_accepts_dataframe_like_inputs() -> None:
    class FakeFrame:
        def __init__(self, rows: list[dict[str, float]]) -> None:
            self._rows = rows

        def to_dict(self, orient: str = "records") -> list[dict[str, float]]:
            assert orient == "records"
            return self._rows

    class SignalModel:
        def predict(self, features: dict[str, float]) -> float:
            return float(features.get("signal", 0.0))

    dataset = FakeFrame(
        [
            {"group": "a", "signal": 0.1, "actual": 0.0},
            {"group": "a", "signal": 0.9, "actual": 1.0},
            {"group": "b", "signal": 0.2, "actual": 0.0},
            {"group": "b", "signal": 0.8, "actual": 1.0},
        ]
    )

    results = run_fairness_checks(
        SignalModel(),
        dataset=dataset,  # type: ignore[arg-type]
        metrics=["demographic_parity_difference"],
        group_column="group",
        positive_threshold=0.5,
        actual_threshold=0.5,
    )

    assert results[0].passed is True
