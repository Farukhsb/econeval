"""Scenario, drift, and backtest helpers."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .config import DriftTest, StressTest


@dataclass(slots=True)
class ScenarioResult:
    name: str
    dataset: str
    metric: str
    threshold: float
    value: float
    passed: bool
    error: str | None = None


@dataclass(slots=True)
class DriftResult:
    name: str
    baseline_dataset: str
    dataset: str
    feature: str
    threshold: float
    value: float
    passed: bool
    error: str | None = None


@dataclass(slots=True)
class FairnessResult:
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


def run_drift_test(test: DriftTest, base_path: str | Path | None = None) -> DriftResult:
    baseline_path = Path(base_path) / test.baseline_dataset if base_path else Path(test.baseline_dataset)
    current_path = Path(base_path) / test.dataset if base_path else Path(test.dataset)

    try:
        baseline_rows = _load_dataset(baseline_path)
        current_rows = _load_dataset(current_path)
        baseline_value = _feature_mean(baseline_rows, test.feature)
        current_value = _feature_mean(current_rows, test.feature)
        value = abs(current_value - baseline_value)
        return DriftResult(
            name=test.name,
            baseline_dataset=test.baseline_dataset,
            dataset=test.dataset,
            feature=test.feature,
            threshold=test.threshold,
            value=value,
            passed=value <= test.threshold,
        )
    except Exception as exc:
        return DriftResult(
            name=test.name,
            baseline_dataset=test.baseline_dataset,
            dataset=test.dataset,
            feature=test.feature,
            threshold=test.threshold,
            value=math.inf,
            passed=False,
            error=str(exc),
        )


def run_drift_suite(tests: Iterable[DriftTest], base_path: str | Path | None = None) -> list[DriftResult]:
    return [run_drift_test(test, base_path=base_path) for test in tests]


def run_fairness_checks(
    model: Any,
    dataset: str,
    metrics: list[str],
    group_column: str = "group",
    positive_threshold: float = 0.5,
    base_path: str | Path | None = None,
) -> list[FairnessResult]:
    dataset_path = Path(base_path) / dataset if base_path else Path(dataset)

    try:
        rows = _load_dataset(dataset_path)
        groups: dict[str, list[float]] = {}

        for row in rows:
            if group_column not in row:
                raise ValueError(f"fairness dataset must include a '{group_column}' column")
            group = row[group_column]
            features = {
                key: _to_feature_value(value)
                for key, value in row.items()
                if key not in {group_column, "actual"}
            }
            score = _to_float(model.predict(features), "prediction")
            groups.setdefault(group, []).append(score)

        results: list[FairnessResult] = []
        for metric in metrics:
            metric_name = metric.lower()
            if metric_name == "demographic_parity_difference":
                rates = [_positive_rate(scores, positive_threshold) for scores in groups.values()]
                value = max(rates) - min(rates)
                threshold = 0.2
            elif metric_name == "disparate_impact_ratio":
                rates = [_positive_rate(scores, positive_threshold) for scores in groups.values()]
                low = min(rates)
                high = max(rates)
                value = 0.0 if high == 0 else low / high
                threshold = 0.8
            else:
                raise ValueError(f"unsupported fairness metric: {metric}")

            results.append(
                FairnessResult(
                    name=metric_name,
                    dataset=dataset,
                    metric=metric_name,
                    threshold=threshold,
                    value=value,
                    passed=value <= threshold if metric_name == "demographic_parity_difference" else value >= threshold,
                )
            )

        return results
    except Exception as exc:
        return [
            FairnessResult(
                name=metric,
                dataset=dataset,
                metric=metric,
                threshold=0.0,
                value=math.inf,
                passed=False,
                error=str(exc),
            )
            for metric in metrics
        ]


def suite_passed(results: list[ScenarioResult]) -> bool:
    return all(result.passed for result in results)


def drift_suite_passed(results: list[DriftResult]) -> bool:
    return all(result.passed for result in results)


def fairness_suite_passed(results: list[FairnessResult]) -> bool:
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


def _feature_mean(rows: list[dict[str, str]], feature: str) -> float:
    if feature not in rows[0]:
        raise ValueError(f"drift dataset must include a '{feature}' column")
    values = [_to_float(row[feature], feature) for row in rows]
    return mean(values)


def _positive_rate(scores: list[float], threshold: float) -> float:
    if not scores:
        return 0.0
    return sum(1 for score in scores if score >= threshold) / len(scores)


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

