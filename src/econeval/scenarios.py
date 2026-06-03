"""Scenario and backtest helpers."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import StressTest


@dataclass(slots=True)
class ScenarioResult:
    name: str
    dataset: str
    metric: str
    threshold: float
    value: float
    passed: bool
    error: str | None = None


def run_scenario(name: str) -> dict[str, object]:
    """Return a placeholder scenario result for compatibility."""

    return {
        "name": name,
        "status": "not_implemented",
    }


def run_stress_test(model: Any, test: StressTest, base_path: str | Path | None = None) -> ScenarioResult:
    """Run a stress test against a dataset and compute a metric.

    The current contract is intentionally small:

    - the model exposes ``predict(features)``;
    - the dataset contains an ``actual`` column;
    - all other columns are passed to the model as features.
    """

    dataset_path = Path(base_path) / test.dataset if base_path else Path(test.dataset)

    try:
        rows = _load_dataset(dataset_path)
        actuals: list[float] = []
        predictions: list[float] = []

        for row in rows:
            actuals.append(_to_float(row["actual"], "actual"))
            features = {key: _to_feature_value(value) for key, value in row.items() if key != "actual"}
            predictions.append(_to_float(model.predict(features), "prediction"))

        value = _compute_metric(test.metric, actuals, predictions)
        return ScenarioResult(
            name=test.name,
            dataset=test.dataset,
            metric=test.metric,
            threshold=test.threshold,
            value=value,
            passed=value <= test.threshold,
        )
    except Exception as exc:
        return ScenarioResult(
            name=test.name,
            dataset=test.dataset,
            metric=test.metric,
            threshold=test.threshold,
            value=math.inf,
            passed=False,
            error=str(exc),
        )


def run_stress_suite(model: Any, tests: Iterable[StressTest], base_path: str | Path | None = None) -> list[ScenarioResult]:
    return [run_stress_test(model, test, base_path=base_path) for test in tests]


def suite_passed(results: list[ScenarioResult]) -> bool:
    return all(result.passed for result in results)


def _load_dataset(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"stress test dataset not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    if not rows:
        raise ValueError(f"stress test dataset is empty: {path}")

    if "actual" not in rows[0]:
        raise ValueError(f"stress test dataset must include an 'actual' column: {path}")

    return rows


def _compute_metric(metric: str, actuals: list[float], predictions: list[float]) -> float:
    if len(actuals) != len(predictions):
        raise ValueError("actuals and predictions must have the same length")

    metric_name = metric.lower()
    if metric_name == "rmse":
        return math.sqrt(sum((pred - actual) ** 2 for actual, pred in zip(actuals, predictions, strict=True)) / len(actuals))
    if metric_name == "mae":
        return sum(abs(pred - actual) for actual, pred in zip(actuals, predictions, strict=True)) / len(actuals)
    if metric_name == "mape":
        total = 0.0
        for actual, pred in zip(actuals, predictions, strict=True):
            if actual == 0:
                raise ValueError("mape cannot be computed when actual values contain zero")
            total += abs((actual - pred) / actual)
        return total / len(actuals)

    raise ValueError(f"unsupported metric: {metric}")


def _to_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise ValueError(f"{field_name} must be numeric")


def _to_feature_value(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value

