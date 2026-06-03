from dataclasses import dataclass

from econeval.config import StressTest
from econeval.scenarios import run_stress_test, suite_passed


@dataclass
class DemoModel:
    def predict(self, features: dict[str, float]) -> float:
        shock = float(features.get("shock", 0.0))
        return 1.0 + 2.0 * shock


def test_run_stress_test_passes_on_matching_dataset() -> None:
    model = DemoModel()
    test = StressTest(
        name="stagflation_shock",
        dataset="examples/basic_model/data/stagflation.csv",
        metric="mape",
        threshold=0.01,
    )

    result = run_stress_test(model, test)

    assert result.passed is True
    assert result.value == 0.0
    assert suite_passed([result]) is True


def test_run_stress_test_fails_when_predictions_drift() -> None:
    model = DemoModel()
    test = StressTest(
        name="broken_shock",
        dataset="examples/broken_model/data/stagflation.csv",
        metric="mape",
        threshold=0.01,
    )

    result = run_stress_test(model, test)

    assert result.passed is False
    assert result.value > test.threshold
    assert suite_passed([result]) is False

