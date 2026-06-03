"""Scenario, drift, and backtest helpers."""

from __future__ import annotations

import copy
import csv
import itertools
import math
import random
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Protocol, runtime_checkable

from .config import DriftTest, EconomicCheck, EconomicDriftTest, StressManipulation, StressTest
from .interop import resolve_model_runtime
from .invariants import evaluate_expression

_CONVERGED_STATUSES = {
    "converged",
    "optimal",
    "solved",
    "success",
    "feasible",
    "ok",
}


@dataclass(slots=True)
class ScenarioResult:
    name: str
    dataset: str
    metric: str
    threshold: float
    value: float
    passed: bool
    detail: str | None = None
    manipulations: list[dict[str, object]] | None = None
    invariants: list[dict[str, object]] | None = None
    samples: int | None = None
    grid_points: int | None = None
    failure_count: int | None = None
    percentiles: dict[str, float] | None = None
    worst_sample: dict[str, object] | None = None
    visual: str | None = None
    error: str | None = None
    error_type: str | None = None


@dataclass(slots=True)
class DriftResult:
    name: str
    baseline_dataset: str
    dataset: str
    feature: str
    statistic: str
    mode: str
    backend: str
    threshold: float
    baseline_value: float
    current_value: float
    value: float
    passed: bool
    time_column: str | None = None
    visual: str | None = None
    detail: str | None = None
    error: str | None = None
    error_type: str | None = None


@dataclass(slots=True)
class EconomicDriftResult:
    name: str
    baseline_dataset: str
    dataset: str
    metric: str
    output: str
    threshold: float
    baseline_value: float
    current_value: float
    value: float
    passed: bool
    visual: str | None = None
    detail: str | None = None
    error: str | None = None
    error_type: str | None = None


@dataclass(slots=True)
class FairnessResult:
    name: str
    dataset: str
    metric: str
    threshold: float
    value: float
    passed: bool
    severity: str = "pass"
    visual: str | None = None
    error: str | None = None
    error_type: str | None = None


@dataclass(slots=True)
class EconomicCheckResult:
    name: str
    kind: str
    passed: bool
    value: float | None = None
    tolerance: float | None = None
    detail: str | None = None
    observations: list[float] | None = None
    scan_inputs: list[float] | None = None
    states: int | None = None
    worst_state: dict[str, Any] | None = None
    worst_value: float | None = None
    visual: str | None = None
    error: str | None = None
    error_type: str | None = None


EconomicCheckHandler = Callable[[object, EconomicCheck], EconomicCheckResult]
_ECONOMIC_CHECK_HANDLERS: dict[str, EconomicCheckHandler] = {}


@runtime_checkable
class SupportsToDictRecords(Protocol):
    def to_dict(self, orient: str = "records") -> list[dict[str, object]]: ...


DatasetSource = Path | str | SupportsToDictRecords


@runtime_checkable
class SupportsSuccess(Protocol):
    success: bool


@runtime_checkable
class SupportsConverged(Protocol):
    converged: bool


def register_economic_check_handler(kind: str, handler: EconomicCheckHandler) -> None:
    """Register a custom handler for an economic check kind."""

    if not kind:
        raise ValueError("economic check kind must be a non-empty string")
    _ECONOMIC_CHECK_HANDLERS[kind] = handler


def unregister_economic_check_handler(kind: str) -> None:
    """Remove a previously registered custom economic check handler."""

    _ECONOMIC_CHECK_HANDLERS.pop(kind, None)


def run_stress_test(
    model: Any,
    test: StressTest,
    base_path: str | Path | None = None,
) -> ScenarioResult:
    """Run a stress test against a dataset and compute a metric.

    The current contract is intentionally small:

    - the model exposes ``predict(features)``;
    - the dataset contains an ``actual`` column;
    - all other columns are passed to the model as features.
    """

    try:
        threshold = test.threshold if test.threshold is not None else 0.0
        if test.kind == "monte_carlo":
            result = _run_monte_carlo_stress_test(model, test, threshold)
        elif test.kind == "grid":
            result = _run_grid_stress_test(model, test, threshold)
        elif test.kind in {"synthetic", "parameter_shock"} and test.manipulations:
            result = _run_manipulation_stress_test(model, test, threshold)
        elif test.kind == "synthetic" or test.variable or test.value is not None:
            value = _run_synthetic_stress_test(model, test)
            result = ScenarioResult(
                name=test.name,
                dataset=test.dataset or "",
                metric=test.metric,
                threshold=threshold,
                value=value,
                passed=value <= threshold,
                detail=f"metric={test.metric}",
                visual=_failure_visual(value, threshold, value <= threshold),
            )
        else:
            value = _run_dataset_stress_test(model, test, base_path=base_path)
            result = ScenarioResult(
                name=test.name,
                dataset=test.dataset or "",
                metric=test.metric,
                threshold=threshold,
                value=value,
                passed=value <= threshold,
                detail=f"metric={test.metric}",
                visual=_failure_visual(value, threshold, value <= threshold),
            )
        return result
    except Exception as exc:
        return ScenarioResult(
            name=test.name,
            dataset=test.dataset or "",
            metric=test.metric,
            threshold=test.threshold if test.threshold is not None else 0.0,
            value=math.inf,
            passed=False,
            error=str(exc),
            error_type="dataset_or_metric",
        )


def run_stress_suite(
    model: Any,
    tests: Iterable[StressTest],
    base_path: str | Path | None = None,
) -> list[ScenarioResult]:
    return [run_stress_test(model, test, base_path=base_path) for test in tests]


def run_drift_test(
    test: DriftTest,
    base_path: str | Path | None = None,
) -> DriftResult:
    try:
        baseline_rows = _load_rows(_resolve_dataset_source(base_path, test.baseline_dataset))
        current_rows = _load_rows(_resolve_dataset_source(base_path, test.dataset))
        if test.statistic == "psi":
            baseline_value = _feature_statistic(baseline_rows, test.feature, "mean")
            current_value = _feature_statistic(current_rows, test.feature, "mean")
            backend = "distribution"
            value = _population_stability_index(baseline_rows, current_rows, test.feature)
        elif test.mode == "trend":
            baseline_value = _feature_trend_slope(baseline_rows, test.feature, test.time_column)
            current_value = _feature_trend_slope(current_rows, test.feature, test.time_column)
            backend = "manual"
            value = abs(current_value - baseline_value)
        elif test.mode == "regression":
            baseline_value, backend = _feature_regression_slope(
                baseline_rows, test.feature, test.time_column
            )
            current_value, backend = _feature_regression_slope(
                current_rows, test.feature, test.time_column
            )
            value = abs(current_value - baseline_value)
        else:
            baseline_value = _feature_statistic(baseline_rows, test.feature, test.statistic)
            current_value = _feature_statistic(current_rows, test.feature, test.statistic)
            backend = "statistic"
            value = abs(current_value - baseline_value)
        detail = (
            f"mode={test.mode}, backend={backend}, "
            f"baseline={baseline_value}, current={current_value}"
        )
        if test.statistic == "psi":
            detail = f"{detail}, statistic=psi"
        if test.time_column:
            detail = f"{detail}, time_column={test.time_column}"
        return DriftResult(
            name=test.name,
            baseline_dataset=test.baseline_dataset,
            dataset=test.dataset,
            feature=test.feature,
            statistic=test.statistic,
            mode=test.mode,
            backend=backend,
            threshold=test.threshold,
            baseline_value=baseline_value,
            current_value=current_value,
            value=value,
            passed=value <= test.threshold,
            visual=_failure_visual(value, test.threshold, value <= test.threshold),
            time_column=test.time_column,
            detail=detail,
        )
    except Exception as exc:
        return DriftResult(
            name=test.name,
            baseline_dataset=test.baseline_dataset,
            dataset=test.dataset,
            feature=test.feature,
            statistic=test.statistic,
            mode=test.mode,
            backend="error",
            threshold=test.threshold,
            baseline_value=math.inf,
            current_value=math.inf,
            value=math.inf,
            passed=False,
            error=str(exc),
            error_type="drift",
            time_column=test.time_column,
        )


def run_drift_suite(
    tests: Iterable[DriftTest],
    base_path: str | Path | None = None,
) -> list[DriftResult]:
    return [run_drift_test(test, base_path=base_path) for test in tests]


def run_economic_drift_test(
    model: Any,
    test: EconomicDriftTest,
    base_path: str | Path | None = None,
) -> EconomicDriftResult:
    try:
        baseline_rows = _load_rows(_resolve_dataset_source(base_path, test.baseline_dataset))
        current_rows = _load_rows(_resolve_dataset_source(base_path, test.dataset))
        baseline_value = _economic_output_value(model, baseline_rows, test)
        current_value = _economic_output_value(model, current_rows, test)
        value = abs(current_value - baseline_value)
        if test.metric == "relative_change":
            denominator = max(abs(baseline_value), 1e-12)
            value /= denominator
        passed = value <= test.threshold
        return EconomicDriftResult(
            name=test.name,
            baseline_dataset=test.baseline_dataset,
            dataset=test.dataset,
            metric=test.metric,
            output=test.output,
            threshold=test.threshold,
            baseline_value=baseline_value,
            current_value=current_value,
            value=value,
            passed=passed,
            visual=_failure_visual(value, test.threshold, passed),
            detail=f"baseline={baseline_value}, current={current_value}",
        )
    except Exception as exc:
        return EconomicDriftResult(
            name=test.name,
            baseline_dataset=test.baseline_dataset,
            dataset=test.dataset,
            metric=test.metric,
            output=test.output,
            threshold=test.threshold,
            baseline_value=math.inf,
            current_value=math.inf,
            value=math.inf,
            passed=False,
            error=str(exc),
            error_type="economic_drift",
        )


def run_economic_drift_suite(
    model: Any,
    tests: Iterable[EconomicDriftTest],
    base_path: str | Path | None = None,
) -> list[EconomicDriftResult]:
    return [run_economic_drift_test(model, test, base_path=base_path) for test in tests]


def run_economic_check(model: Any, check: EconomicCheck) -> EconomicCheckResult:
    try:
        handler = _ECONOMIC_CHECK_HANDLERS.get(check.kind)
        if handler is not None:
            return handler(model, check)
        if check.kind == "accounting_identity":
            return _run_accounting_identity_check(model, check)
        if check.kind == "monotonicity":
            return _run_monotonicity_check(model, check)
        if check.kind == "boundary_condition":
            return _run_boundary_condition_check(model, check)
        if check.kind == "convergence":
            return _run_convergence_check(model, check)
        if check.kind == "scan":
            return _run_scan_check(model, check)
        raise ValueError(f"unsupported economic check kind: {check.kind}")
    except Exception as exc:
        return EconomicCheckResult(
            name=check.name,
            kind=check.kind,
            passed=False,
            value=math.inf,
            tolerance=check.tolerance,
            error=str(exc),
            error_type="economic_check",
        )


def run_economic_suite(model: Any, checks: Iterable[EconomicCheck]) -> list[EconomicCheckResult]:
    return [run_economic_check(model, check) for check in checks]


def run_fairness_checks(
    model: Any,
    dataset: str,
    metrics: list[str],
    group_column: str = "group",
    positive_threshold: float = 0.5,
    actual_threshold: float = 0.5,
    base_path: str | Path | None = None,
) -> list[FairnessResult]:
    try:
        runtime = resolve_model_runtime(model)
        rows = _load_dataset(_resolve_dataset_source(base_path, dataset))
        groups: dict[str, list[float]] = {}
        outcomes: dict[str, list[bool]] = {}

        for row in rows:
            if group_column not in row:
                raise ValueError(f"fairness dataset must include a '{group_column}' column")
            group = row[group_column]
            features = {
                key: _to_feature_value(value)
                for key, value in row.items()
                if key not in {group_column, "actual"}
            }
            score = _to_float(runtime.predict(features), "prediction")
            groups.setdefault(group, []).append(score)
            actual_value = _to_float(row.get("actual", 0.0), "actual")
            outcomes.setdefault(group, []).append(actual_value >= actual_threshold)
        all_scores = [score for scores in groups.values() for score in scores]

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
            elif metric_name == "gini":
                value = _gini_coefficient(all_scores)
                threshold = 0.3
            elif metric_name == "atkinson":
                value = _atkinson_index(all_scores)
                threshold = 0.2
            elif metric_name == "equal_opportunity_difference":
                tprs = [
                    _true_positive_rate(scores, labels, positive_threshold)
                    for scores, labels in zip(groups.values(), outcomes.values(), strict=True)
                ]
                value = max(tprs) - min(tprs)
                threshold = 0.2
            elif metric_name == "equalized_odds_difference":
                tprs = []
                fprs = []
                for scores, labels in zip(groups.values(), outcomes.values(), strict=True):
                    tprs.append(_true_positive_rate(scores, labels, positive_threshold))
                    fprs.append(_false_positive_rate(scores, labels, positive_threshold))
                value = max(max(tprs) - min(tprs), max(fprs) - min(fprs))
                threshold = 0.2
            else:
                raise ValueError(f"unsupported fairness metric: {metric}")

            passed = (
                value <= threshold
                if metric_name
                in {
                    "demographic_parity_difference",
                    "gini",
                    "atkinson",
                    "equal_opportunity_difference",
                    "equalized_odds_difference",
                }
                else value >= threshold
            )
            severity = _fairness_severity(metric_name, value, threshold, passed)

            results.append(
                FairnessResult(
                    name=metric_name,
                    dataset=dataset,
                    metric=metric_name,
                    threshold=threshold,
                    value=value,
                    passed=passed,
                    severity=severity,
                    visual=_failure_visual(value, threshold, passed),
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
                severity="fail",
                error=str(exc),
                error_type="fairness",
            )
            for metric in metrics
        ]


def _run_dataset_stress_test(
    model: Any,
    test: StressTest,
    base_path: str | Path | None = None,
) -> float:
    if not test.dataset:
        raise ValueError("dataset stress tests must include a dataset path")

    dataset_path = Path(base_path) / test.dataset if base_path else Path(test.dataset)
    runtime = resolve_model_runtime(model)
    rows = _load_dataset(dataset_path)
    actuals: list[float] = []
    predictions: list[float] = []

    for row in rows:
        actuals.append(_to_float(row["actual"], "actual"))
        features = {key: _to_feature_value(value) for key, value in row.items() if key != "actual"}
        predictions.append(_to_float(runtime.predict(features), "prediction"))

    return _compute_metric(test.metric, actuals, predictions)


def _run_manipulation_stress_test(
    model: Any,
    test: StressTest,
    threshold: float,
) -> ScenarioResult:
    manipulations = [_manipulation_dict(manipulation) for manipulation in test.manipulations]
    invariant_results: list[dict[str, Any]] = []

    with _temporary_manipulations(model, test.manipulations):
        failures = 0
        for invariant in test.invariants:
            try:
                result = evaluate_expression(
                    invariant.expression,
                    {"model": model},
                    backend=invariant.backend,
                )
                passed = bool(result)
                detail = None
            except Exception as exc:
                passed = False
                detail = str(exc)

            if not passed:
                failures += 1

            invariant_results.append(
                {
                    "name": invariant.name,
                    "passed": passed,
                    "expression": invariant.expression,
                    "backend": invariant.backend,
                    "detail": detail,
                }
            )

    passed = failures == 0
    detail = f"manipulations={len(manipulations)}, invariants={len(test.invariants)}"
    if failures:
        detail = f"{detail}, failures={failures}"

    return ScenarioResult(
        name=test.name,
        dataset=test.dataset or "",
        metric=test.metric,
        threshold=threshold,
        value=float(failures),
        passed=passed,
        detail=detail,
        manipulations=manipulations,
        invariants=invariant_results,
        failure_count=failures,
        visual=_failure_visual(float(failures), threshold, passed),
    )


def _run_monte_carlo_stress_test(
    model: Any,
    test: StressTest,
    threshold: float,
) -> ScenarioResult:
    if not test.manipulations:
        raise ValueError("monte carlo stress tests must define manipulations")
    if not test.invariants:
        raise ValueError("monte carlo stress tests must define invariants")

    rng = random.Random(test.seed)
    failures = 0
    sample_scores: list[float] = []
    worst_sample: dict[str, Any] | None = None
    worst_sample_score = -1.0

    for _ in range(test.samples):
        sampled_manipulations = _sample_manipulations(test.manipulations, rng)
        with _temporary_manipulations(model, sampled_manipulations):
            failed_in_sample = 0
            for invariant in test.invariants:
                try:
                    result = evaluate_expression(
                        invariant.expression,
                        {"model": model},
                        backend=invariant.backend,
                    )
                    passed = bool(result)
                except Exception:
                    passed = False
                if not passed:
                    failed_in_sample += 1
            sample_score = failed_in_sample / max(len(test.invariants), 1)
            sample_scores.append(sample_score)
            if sample_score > worst_sample_score:
                worst_sample_score = sample_score
                worst_sample = {
                    "score": sample_score,
                    "failed_invariants": failed_in_sample,
                    "manipulations": [
                        _manipulation_dict(manipulation) for manipulation in sampled_manipulations
                    ],
                }
            if failed_in_sample:
                failures += 1

    failure_rate = failures / test.samples
    percentiles = _percentile_summary(sample_scores, test.percentile_cutoffs)
    passed = failure_rate <= threshold
    detail = f"samples={test.samples}, failures={failures}, failure_rate={failure_rate:.4g}"
    if percentiles:
        detail = f"{detail}, percentiles={percentiles}"
    if worst_sample:
        detail = f"{detail}, worst_sample_score={worst_sample_score:.4g}"
    return ScenarioResult(
        name=test.name,
        dataset=test.dataset or "",
        metric=test.metric,
        threshold=threshold,
        value=failure_rate,
        passed=passed,
        detail=detail,
        manipulations=[_manipulation_dict(manipulation) for manipulation in test.manipulations],
        invariants=[
            {
                "name": invariant.name,
                "expression": invariant.expression,
                "backend": invariant.backend,
            }
            for invariant in test.invariants
        ],
        samples=test.samples,
        failure_count=failures,
        percentiles=percentiles,
        worst_sample=worst_sample,
        visual=_failure_visual(failure_rate, threshold, passed),
    )


def _run_grid_stress_test(
    model: Any,
    test: StressTest,
    threshold: float,
) -> ScenarioResult:
    if not test.sweep_axes:
        raise ValueError("grid stress tests must define sweep_axes")
    if not test.invariants:
        raise ValueError("grid stress tests must define invariants")

    axis_names = [axis.variable for axis in test.sweep_axes]
    axis_values = [axis.values for axis in test.sweep_axes]
    total_points = 0
    failure_count = 0
    failure_rate = 0.0
    worst_case: dict[str, Any] | None = None
    worst_case_score = -1.0
    points: list[dict[str, Any]] = []

    for combination in itertools.product(*axis_values):
        total_points += 1
        state = dict(zip(axis_names, combination, strict=True))
        with _temporary_model_state(model, state):
            failed_invariants = 0
            observed = []
            for invariant in test.invariants:
                try:
                    result = evaluate_expression(
                        invariant.expression,
                        {"model": model},
                        backend=invariant.backend,
                    )
                    passed = bool(result)
                except Exception:
                    passed = False
                observed.append({"name": invariant.name, "passed": passed})
                if not passed:
                    failed_invariants += 1
            point_score = failed_invariants / max(len(test.invariants), 1)
            if failed_invariants:
                failure_count += 1
            if point_score > worst_case_score:
                worst_case_score = point_score
                worst_case = {
                    "state": state,
                    "failed_invariants": failed_invariants,
                    "score": point_score,
                }
            points.append(
                {
                    "state": state,
                    "failed_invariants": failed_invariants,
                    "score": point_score,
                    "invariants": observed,
                }
            )

    if total_points:
        failure_rate = failure_count / total_points
    passed = failure_rate <= threshold
    detail = (
        f"grid_points={total_points}, failures={failure_count}, failure_rate={failure_rate:.4g}"
    )
    return ScenarioResult(
        name=test.name,
        dataset=test.dataset or "",
        metric=test.metric,
        threshold=threshold,
        value=failure_rate,
        passed=passed,
        detail=detail,
        manipulations=[
            {
                "variable": axis.variable,
                "action": "set",
                "values": axis.values,
            }
            for axis in test.sweep_axes
        ],
        invariants=[
            {
                "name": invariant.name,
                "expression": invariant.expression,
                "backend": invariant.backend,
            }
            for invariant in test.invariants
        ],
        samples=total_points,
        grid_points=total_points,
        failure_count=failure_count,
        worst_sample=worst_case,
        percentiles=_percentile_summary([point["score"] for point in points], [10.0, 50.0, 90.0]),
        visual=_failure_visual(failure_rate, threshold, passed),
    )


def _run_synthetic_stress_test(model: Any, test: StressTest) -> float:
    if not test.variable:
        raise ValueError("synthetic stress tests must define a variable")

    runtime = resolve_model_runtime(model)
    baseline_value = test.baseline_value
    shock_value = _apply_shock(test.shock_type, baseline_value, test.value)

    baseline_features = {test.variable: baseline_value}
    shocked_features = {test.variable: shock_value}
    baseline_prediction = _to_float(runtime.predict(baseline_features), "prediction")
    shocked_prediction = _to_float(runtime.predict(shocked_features), "prediction")

    metric_name = test.metric.lower()
    if metric_name in {"delta", "absolute_change"}:
        return abs(shocked_prediction - baseline_prediction)
    if metric_name == "relative_change":
        denominator = max(abs(baseline_prediction), 1e-12)
        return abs(shocked_prediction - baseline_prediction) / denominator

    raise ValueError(f"unsupported synthetic stress metric: {test.metric}")


def _apply_shock(shock_type: str, baseline_value: float, shock_value: float | None) -> float:
    if shock_value is None:
        raise ValueError("synthetic stress tests must define a value")

    shock_name = shock_type.lower()
    if shock_name == "multiplier":
        return baseline_value * shock_value
    if shock_name == "additive":
        return baseline_value + shock_value
    if shock_name == "absolute":
        return shock_value
    raise ValueError(f"unsupported shock type: {shock_type}")


def _run_accounting_identity_check(model: Any, check: EconomicCheck) -> EconomicCheckResult:
    if not check.left_expression or not check.right_expression:
        raise ValueError("accounting identity checks require left_expression and right_expression")

    context = {"model": model}
    left = _to_float(evaluate_expression(check.left_expression, context), "left_expression")
    right = _to_float(evaluate_expression(check.right_expression, context), "right_expression")
    value = abs(left - right)
    return EconomicCheckResult(
        name=check.name,
        kind=check.kind,
        passed=value <= check.tolerance,
        value=value,
        tolerance=check.tolerance,
        detail=f"left={left}, right={right}",
        visual=_failure_visual(value, check.tolerance, value <= check.tolerance),
    )


def _run_boundary_condition_check(model: Any, check: EconomicCheck) -> EconomicCheckResult:
    if not check.expression or check.lower is None or check.upper is None:
        raise ValueError("boundary condition checks require expression, lower, and upper")

    states = _initial_states(check)
    observations: list[float] = []
    max_violation = 0.0
    worst_state: dict[str, Any] | None = None
    worst_value: float | None = None
    for state in states:
        with _temporary_model_state(model, state):
            value = _to_float(evaluate_expression(check.expression, {"model": model}), "expression")
        observations.append(value)
        violation = max(0.0, check.lower - value, value - check.upper)
        if violation > max_violation:
            max_violation = violation
            worst_state = dict(state)
            worst_value = value

    passed = max_violation <= check.tolerance
    detail = f"lower={check.lower}, upper={check.upper}"
    if len(states) > 1:
        detail = f"{detail}, states={len(states)}"
    return EconomicCheckResult(
        name=check.name,
        kind=check.kind,
        passed=passed,
        value=max_violation,
        tolerance=check.tolerance,
        detail=detail,
        observations=observations,
        states=len(states),
        worst_state=worst_state,
        worst_value=worst_value,
        visual=(_sparkline(observations) if observations and not passed else None),
    )


def _run_convergence_check(model: Any, check: EconomicCheck) -> EconomicCheckResult:
    method_name = check.method or "solve"
    runtime = resolve_model_runtime(model)
    method = getattr(runtime.model, method_name, None)
    solver_result = None
    if method is None:
        if method_name == "solve" and _solve_result_passed(runtime.model):
            solver_result = runtime.model
        else:
            raise ValueError(f"model does not define {method_name}")

    states = _initial_states(check)
    observations: list[float] = []
    failed_states = 0
    worst_state: dict[str, object] | None = None
    for state in states:
        with _temporary_model_state(model, state):
            result = solver_result if solver_result is not None else method()
        passed = _solve_result_passed(result)
        observations.append(1.0 if passed else 0.0)
        if not passed:
            failed_states += 1
            worst_state = dict(state)

    detail = f"method={method_name}"
    if len(states) > 1:
        detail = f"{detail}, states={len(states)}"

    return EconomicCheckResult(
        name=check.name,
        kind=check.kind,
        passed=failed_states == 0,
        value=float(failed_states),
        tolerance=check.tolerance,
        detail=detail,
        observations=observations,
        states=len(states),
        worst_state=worst_state,
        visual=_sparkline(observations) if failed_states else None,
    )


def _run_monotonicity_check(model: Any, check: EconomicCheck) -> EconomicCheckResult:
    if not check.method or not check.variable or check.lower is None or check.upper is None:
        raise ValueError("monotonicity checks require method, variable, lower, and upper")
    if check.steps < 2:
        raise ValueError("monotonicity checks require at least two steps")

    method = getattr(model, check.method, None)
    if method is None:
        raise ValueError(f"model does not define {check.method}")

    grid = _generate_grid(check.lower, check.upper, check.steps)
    observations: list[float] = []
    for value in grid:
        try:
            observations.append(_to_float(method(value), "monotonicity observation"))
        except TypeError:
            observations.append(
                _to_float(
                    method(**{check.variable: value}),
                    "monotonicity observation",
                )
            )

    max_violation = _monotonicity_violation(observations, check.direction, check.tolerance)
    return EconomicCheckResult(
        name=check.name,
        kind=check.kind,
        passed=max_violation <= check.tolerance,
        value=max_violation,
        tolerance=check.tolerance,
        detail=f"direction={check.direction}, method={check.method}",
        observations=observations,
        visual=(
            _sparkline(observations) if observations and max_violation > check.tolerance else None
        ),
    )


def _run_scan_check(model: Any, check: EconomicCheck) -> EconomicCheckResult:
    if not check.method or not check.input_variable or not check.output_variable:
        raise ValueError("scan checks require method, input_variable, and output_variable")
    if check.expected_direction is None:
        raise ValueError("scan checks require expected_direction")
    if not check.perturbations:
        raise ValueError("scan checks require perturbations")

    method = getattr(model, check.method, None)
    if method is None:
        raise ValueError(f"model does not define {check.method}")

    baseline_value = getattr(model, check.input_variable, 1.0)
    if isinstance(baseline_value, bool):
        baseline_value = 1.0
    baseline_value = _to_float(baseline_value, check.input_variable)

    inputs = [baseline_value]
    outputs: list[float] = []

    baseline_output = _invoke_scan_method(
        method, check.input_variable, baseline_value, check.output_variable
    )

    for perturbation in check.perturbations:
        if perturbation <= 0:
            raise ValueError("scan perturbations must be positive")
        if perturbation < 1:
            input_value = baseline_value * (1.0 + perturbation)
        else:
            input_value = baseline_value + perturbation
        inputs.append(input_value)
        raw_output = _invoke_scan_method(
            method, check.input_variable, input_value, check.output_variable
        )
        if check.scan_kind == "elasticity":
            input_change = (input_value - baseline_value) / max(abs(baseline_value), 1e-12)
            output_change = (raw_output - baseline_output) / max(abs(baseline_output), 1e-12)
            outputs.append(output_change / max(abs(input_change), 1e-12))
        else:
            outputs.append(raw_output)

    if check.scan_kind == "elasticity":
        max_violation = _elasticity_sign_violation(
            outputs,
            check.expected_direction,
            check.tolerance,
        )
    else:
        outputs = [baseline_output, *outputs]
        max_violation = _monotonicity_violation(outputs, check.expected_direction, check.tolerance)
    return EconomicCheckResult(
        name=check.name,
        kind=check.kind,
        passed=max_violation <= check.tolerance,
        value=max_violation,
        tolerance=check.tolerance,
        detail=(
            f"method={check.method}, input={check.input_variable}, "
            f"output={check.output_variable}, baseline={baseline_value}, "
            f"baseline_output={baseline_output}, scan={check.scan_kind}"
        ),
        observations=outputs,
        scan_inputs=inputs,
        visual=(_sparkline(outputs) if outputs and max_violation > check.tolerance else None),
    )


def suite_passed(results: list[ScenarioResult]) -> bool:
    return all(result.passed for result in results)


def drift_suite_passed(results: list[DriftResult]) -> bool:
    return all(result.passed for result in results)


def fairness_suite_passed(results: list[FairnessResult]) -> bool:
    return all(result.severity != "fail" and result.error is None for result in results)


def economic_drift_suite_passed(results: list[EconomicDriftResult]) -> bool:
    return all(result.passed for result in results)


def economic_suite_passed(results: list[EconomicCheckResult]) -> bool:
    return all(result.passed for result in results)


def _load_rows(source: DatasetSource) -> list[dict[str, str]]:
    if hasattr(source, "to_dict"):
        rows = source.to_dict(orient="records")
        if not isinstance(rows, list) or not rows:
            raise ValueError("dataframe source is empty")
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError("dataframe source must produce row mappings")
        return [{str(key): str(value) for key, value in row.items()} for row in rows]

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"stress test dataset not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    if not rows:
        raise ValueError(f"stress test dataset is empty: {path}")

    return rows


def _resolve_dataset_source(base_path: str | Path | None, dataset: DatasetSource) -> DatasetSource:
    if isinstance(dataset, SupportsToDictRecords):
        return dataset
    return Path(base_path) / dataset if base_path else Path(dataset)


def _initial_states(check: EconomicCheck) -> list[dict[str, Any]]:
    return check.initial_states or [{}]


@contextmanager
def _temporary_manipulations(
    model: Any,
    manipulations: Iterable[StressManipulation],
):
    roots: dict[str, object] = {}
    try:
        for manipulation in manipulations:
            root_name = manipulation.variable.split(".", 1)[0]
            if root_name not in roots:
                roots[root_name] = copy.deepcopy(_get_path_value(model, root_name))
        for manipulation in manipulations:
            _apply_manipulation(model, manipulation)
        yield
    finally:
        for root_name, value in roots.items():
            _set_path_value(model, root_name, value)


@contextmanager
def _temporary_model_state(model: Any, state: dict[str, Any]):
    previous: dict[str, tuple[bool, object]] = {}
    try:
        for key, value in state.items():
            had_attr = hasattr(model, key)
            previous[key] = (had_attr, getattr(model, key) if had_attr else None)
            setattr(model, key, value)
        yield
    finally:
        for key, (had_attr, old_value) in previous.items():
            if had_attr:
                setattr(model, key, old_value)
            else:
                delattr(model, key)


def _apply_manipulation(model: Any, manipulation: StressManipulation) -> None:
    current_value = _to_float(_get_path_value(model, manipulation.variable), manipulation.variable)
    if manipulation.action == "add":
        next_value = current_value + manipulation.value
    elif manipulation.action == "multiply":
        next_value = current_value * manipulation.value
    elif manipulation.action == "set":
        next_value = manipulation.value
    else:
        raise ValueError(f"unsupported manipulation action: {manipulation.action}")
    _set_path_value(model, manipulation.variable, next_value)


def _solve_result_passed(result: object) -> bool:
    if isinstance(result, bool):
        return result
    if isinstance(result, SupportsSuccess):
        return bool(result.success)
    if isinstance(result, SupportsConverged):
        return bool(result.converged)
    if isinstance(result, dict):
        for key in ("success", "converged", "status", "solve_status", "model_status"):
            if key in result:
                if key == "success":
                    return bool(result[key])
                return _status_passed(result[key])
    for key in ("success", "status", "solve_status", "model_status"):
        if hasattr(result, key):
            if key == "success":
                return bool(getattr(result, key))
            return _status_passed(getattr(result, key))
    return bool(result)


def _status_passed(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in _CONVERGED_STATUSES
    return bool(value)


def _invoke_scan_method(
    method: object,
    input_variable: str,
    value: float,
    output_variable: str,
) -> float:
    try:
        result = method(**{input_variable: value})
    except TypeError:
        result = method(value)

    if isinstance(result, dict) and output_variable in result:
        return _to_float(result[output_variable], output_variable)
    if hasattr(result, output_variable):
        return _to_float(getattr(result, output_variable), output_variable)
    return _to_float(result, output_variable)


def _manipulation_dict(manipulation: StressManipulation) -> dict[str, object]:
    payload = {
        "variable": manipulation.variable,
        "action": manipulation.action,
        "value": manipulation.value,
    }
    if getattr(manipulation, "sigma", None) is not None:
        payload["sigma"] = manipulation.sigma
    return payload


def _sample_manipulation(
    manipulation: StressManipulation,
    rng: random.Random,
) -> StressManipulation:
    sampled = copy.deepcopy(manipulation)
    if getattr(manipulation, "sigma", None) is not None:
        sampled.value = rng.normalvariate(manipulation.value, manipulation.sigma)
    return sampled


def _sample_manipulations(
    manipulations: list[StressManipulation],
    rng: random.Random,
) -> list[StressManipulation]:
    grouped: dict[str, list[StressManipulation]] = {}
    for manipulation in manipulations:
        group_name = getattr(manipulation, "correlation_group", None) or manipulation.variable
        grouped.setdefault(group_name, []).append(manipulation)

    sampled: list[StressManipulation] = []
    for _group_name, group_manipulations in grouped.items():
        shared_z = rng.normalvariate(0.0, 1.0)
        for manipulation in group_manipulations:
            sampled.append(_sample_correlated_manipulation(manipulation, rng, shared_z))
    return sampled


def _sample_correlated_manipulation(
    manipulation: StressManipulation,
    rng: random.Random,
    shared_z: float,
) -> StressManipulation:
    sampled = copy.deepcopy(manipulation)
    sigma = getattr(manipulation, "sigma", None)
    if sigma is None:
        return sampled

    correlation = getattr(manipulation, "correlation", None) or 0.0
    correlation = max(-1.0, min(1.0, correlation))
    independent = rng.normalvariate(0.0, 1.0)
    combined = (correlation * shared_z) + (math.sqrt(1 - (correlation**2)) * independent)
    sampled.value = manipulation.value + (sigma * combined)
    return sampled


def _percentile_summary(values: list[float], cutoffs: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {f"p{int(cutoff)}": _percentile(values, cutoff) for cutoff in cutoffs}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (percentile / 100) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    lower_value = ordered[lower]
    upper_value = ordered[upper]
    fraction = rank - lower
    return lower_value + ((upper_value - lower_value) * fraction)


def _elasticity_sign_violation(
    values: list[float],
    direction: str,
    tolerance: float,
) -> float:
    if not values:
        return 0.0

    direction_name = direction.lower()
    if direction_name in {"nonincreasing", "strictly_nonincreasing"}:
        return max(max(0.0, value + tolerance) for value in values)
    if direction_name in {"nondecreasing", "strictly_nondecreasing"}:
        return max(max(0.0, -value + tolerance) for value in values)
    raise ValueError(f"unsupported monotonicity direction: {direction}")


def _load_dataset(path: Path) -> list[dict[str, str]]:
    rows = _load_rows(path)

    if "actual" not in rows[0]:
        raise ValueError(f"stress test dataset must include an 'actual' column: {path}")

    return rows


def _compute_metric(metric: str, actuals: list[float], predictions: list[float]) -> float:
    if len(actuals) != len(predictions):
        raise ValueError("actuals and predictions must have the same length")

    metric_name = metric.lower()
    if metric_name == "rmse":
        return math.sqrt(
            sum((pred - actual) ** 2 for actual, pred in zip(actuals, predictions, strict=True))
            / len(actuals)
        )
    if metric_name == "mae":
        return sum(
            abs(pred - actual) for actual, pred in zip(actuals, predictions, strict=True)
        ) / len(actuals)
    if metric_name == "mape":
        total = 0.0
        for actual, pred in zip(actuals, predictions, strict=True):
            if actual == 0:
                raise ValueError("mape cannot be computed when actual values contain zero")
            total += abs((actual - pred) / actual)
        return total / len(actuals)

    raise ValueError(f"unsupported metric: {metric}")


def _feature_mean(rows: list[dict[str, str]], feature: str) -> float:
    return _feature_statistic(rows, feature, "mean")


def _feature_statistic(rows: list[dict[str, str]], feature: str, statistic: str) -> float:
    if feature not in rows[0]:
        raise ValueError(f"drift dataset must include a '{feature}' column")
    values = [_to_float(row[feature], feature) for row in rows]
    statistic_name = statistic.lower()
    if statistic_name == "mean":
        return mean(values)
    if statistic_name == "median":
        return median(values)
    raise ValueError(f"unsupported drift statistic: {statistic}")


def _feature_trend_slope(
    rows: list[dict[str, str]],
    feature: str,
    time_column: str | None,
) -> float:
    if not time_column:
        raise ValueError("trend drift checks require time_column")
    if feature not in rows[0]:
        raise ValueError(f"drift dataset must include a '{feature}' column")
    if time_column not in rows[0]:
        raise ValueError(f"drift dataset must include a '{time_column}' column")

    points = sorted(
        (
            _to_float(row[time_column], time_column),
            _to_float(row[feature], feature),
        )
        for row in rows
    )
    if len(points) < 2:
        raise ValueError("trend drift checks require at least two points")

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_mean = mean(xs)
    y_mean = mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in points)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        raise ValueError("trend drift checks require varying time values")
    return numerator / denominator


def _feature_regression_slope(
    rows: list[dict[str, str]],
    feature: str,
    time_column: str | None,
) -> tuple[float, str]:
    if not time_column:
        raise ValueError("regression drift checks require time_column")
    if feature not in rows[0]:
        raise ValueError(f"drift dataset must include a '{feature}' column")
    if time_column not in rows[0]:
        raise ValueError(f"drift dataset must include a '{time_column}' column")

    points = sorted(
        (
            _to_float(row[time_column], time_column),
            _to_float(row[feature], feature),
        )
        for row in rows
    )
    if len(points) < 2:
        raise ValueError("regression drift checks require at least two points")

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    try:
        import numpy as np
        import statsmodels.api as sm

        design = sm.add_constant(np.asarray(xs, dtype=float))
        fitted = sm.OLS(np.asarray(ys, dtype=float), design).fit()
        return float(fitted.params[1]), "statsmodels"
    except Exception:
        x_mean = mean(xs)
        y_mean = mean(ys)
        denominator = sum((x - x_mean) ** 2 for x in xs)
        if denominator == 0:
            raise ValueError("regression drift checks require varying time values") from None
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in points)
        return numerator / denominator, "manual"


def _population_stability_index(
    baseline_rows: list[dict[str, str]],
    current_rows: list[dict[str, str]],
    feature: str,
    bins: int = 10,
) -> float:
    if feature not in baseline_rows[0]:
        raise ValueError(f"drift dataset must include a '{feature}' column")
    if feature not in current_rows[0]:
        raise ValueError(f"drift dataset must include a '{feature}' column")

    baseline_values = [_to_float(row[feature], feature) for row in baseline_rows]
    current_values = [_to_float(row[feature], feature) for row in current_rows]
    combined = baseline_values + current_values
    if len(combined) < 2:
        raise ValueError("psi drift checks require at least two points")
    if len(set(baseline_values)) < 2:
        raise ValueError("psi drift checks require varying baseline values")

    bucket_count = max(2, min(bins, len(baseline_values)))
    edges = _quantile_edges(baseline_values, bucket_count)
    if len(edges) < 2:
        raise ValueError("psi drift checks require varying baseline values")

    baseline_hist = _bucket_histogram(baseline_values, edges)
    current_hist = _bucket_histogram(current_values, edges)
    epsilon = 1e-12
    psi = 0.0
    for baseline_count, current_count in zip(baseline_hist, current_hist, strict=True):
        baseline_pct = max(baseline_count / len(baseline_values), epsilon)
        current_pct = max(current_count / len(current_values), epsilon)
        psi += (current_pct - baseline_pct) * math.log(current_pct / baseline_pct)
    return psi


def _quantile_edges(values: list[float], bins: int) -> list[float]:
    if bins < 2:
        return [min(values), max(values)]

    ordered = sorted(values)
    edges = [ordered[0]]
    for index in range(1, bins):
        quantile = index / bins
        edges.append(_quantile_value(ordered, quantile))
    edges.append(ordered[-1])

    deduped: list[float] = []
    for edge in edges:
        if not deduped or edge > deduped[-1]:
            deduped.append(edge)
    return deduped


def _quantile_value(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if quantile <= 0:
        return values[0]
    if quantile >= 1:
        return values[-1]

    index = (len(values) - 1) * quantile
    lower = int(math.floor(index))
    upper = int(math.ceil(index))
    if lower == upper:
        return values[lower]
    weight = index - lower
    return values[lower] + ((values[upper] - values[lower]) * weight)


def _bucket_histogram(values: list[float], edges: list[float]) -> list[int]:
    if len(edges) < 2:
        raise ValueError("psi drift checks require at least two bucket edges")

    counts = [0 for _ in range(len(edges) - 1)]
    for value in values:
        for index in range(len(edges) - 1):
            left = edges[index]
            right = edges[index + 1]
            is_last = index == len(edges) - 2
            if (left <= value < right) or (is_last and value <= right):
                counts[index] += 1
                break
        else:
            counts[-1] += 1
    return counts


def _economic_output_value(
    model: Any,
    rows: list[dict[str, str]],
    test: EconomicDriftTest,
) -> float:
    runtime = resolve_model_runtime(model)
    outputs: list[float] = []
    for row in rows:
        features = {
            key: _to_feature_value(value) for key, value in row.items() if key not in {"actual"}
        }
        prediction = _to_float(runtime.predict(features), "prediction")
        outputs.append(prediction)

    if test.output == "mean_prediction":
        return mean(outputs)
    if test.output == "median_prediction":
        return median(outputs)
    if test.output == "positive_rate":
        return _positive_rate(outputs, test.positive_threshold)

    raise ValueError(f"unsupported economic drift output: {test.output}")


def _positive_rate(scores: list[float], threshold: float) -> float:
    if not scores:
        return 0.0
    return sum(1 for score in scores if score >= threshold) / len(scores)


def _fairness_severity(metric: str, value: float, threshold: float, passed: bool) -> str:
    if passed:
        return "pass"

    if not math.isfinite(value):
        return "fail"

    if metric == "disparate_impact_ratio":
        warn_floor = max(0.0, threshold - 0.1)
        return "warn" if value >= warn_floor else "fail"

    warn_ceiling = threshold + 0.1
    return "warn" if value <= warn_ceiling else "fail"


def _true_positive_rate(
    scores: list[float],
    labels: list[bool],
    threshold: float,
) -> float:
    positives = [score for score, label in zip(scores, labels, strict=True) if label]
    if not positives:
        return 0.0
    return _positive_rate(positives, threshold)


def _false_positive_rate(
    scores: list[float],
    labels: list[bool],
    threshold: float,
) -> float:
    negatives = [score for score, label in zip(scores, labels, strict=True) if not label]
    if not negatives:
        return 0.0
    return _positive_rate(negatives, threshold)


def _gini_coefficient(values: list[float]) -> float:
    if not values:
        return 0.0
    adjusted = _nonnegative_values(values)
    total = sum(adjusted)
    if total == 0:
        return 0.0
    ordered = sorted(adjusted)
    n = len(ordered)
    weighted = sum((index + 1) * value for index, value in enumerate(ordered))
    return (2 * weighted) / (n * total) - (n + 1) / n


def _atkinson_index(values: list[float], epsilon: float = 0.5) -> float:
    if not values:
        return 0.0
    adjusted = _nonnegative_values(values)
    if all(value == 0 for value in adjusted):
        return 0.0
    mean_value = sum(adjusted) / len(adjusted)
    if mean_value == 0:
        return 0.0
    power = 1.0 - epsilon
    if abs(power) < 1e-12:
        geometric_mean = math.exp(
            sum(math.log(max(value, 1e-12)) for value in adjusted) / len(adjusted)
        )
        return 1.0 - (geometric_mean / mean_value)
    mean_power = sum(value**power for value in adjusted) / len(adjusted)
    equally_distributed_equivalent = mean_power ** (1.0 / power)
    return 1.0 - (equally_distributed_equivalent / mean_value)


def _nonnegative_values(values: list[float]) -> list[float]:
    minimum = min(values)
    if minimum >= 0:
        return list(values)
    offset = abs(minimum)
    return [value + offset for value in values]


def _get_path_value(target: object, path: str) -> object:
    current = target
    for segment in path.split("."):
        current = current[segment] if isinstance(current, dict) else getattr(current, segment)
    return current


def _set_path_value(target: object, path: str, value: object) -> None:
    segments = path.split(".")
    parent = target
    for segment in segments[:-1]:
        parent = parent[segment] if isinstance(parent, dict) else getattr(parent, segment)
    leaf = segments[-1]
    if isinstance(parent, dict):
        parent[leaf] = value
    else:
        setattr(parent, leaf, value)


def _failure_visual(value: float, threshold: float, passed: bool) -> str | None:
    if passed:
        return None
    if not math.isfinite(value) or not math.isfinite(threshold):
        return f"value={value:.4g}, threshold={threshold:.4g}"
    if threshold <= 0:
        return f"value={value:.4g}, threshold={threshold:.4g}"

    width = 12
    ratio = max(0.0, min(value / threshold, 2.0))
    filled = min(width, max(1, round(ratio * width / 2)))
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] value={value:.4g} threshold={threshold:.4g}"


def _sparkline(values: list[float]) -> str:
    if not values:
        return ""

    palette = ".:-=+*#%@"
    low = min(values)
    high = max(values)
    if high == low:
        return palette[-1] * len(values)

    scale = len(palette) - 1
    return "".join(palette[round(((value - low) / (high - low)) * scale)] for value in values)


def _to_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise ValueError(f"{field_name} must be numeric")


def _to_feature_value(value: str) -> object:
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


def _generate_grid(lower: float, upper: float, steps: int) -> list[float]:
    if steps < 2:
        raise ValueError("steps must be at least 2")
    if steps == 2:
        return [lower, upper]

    step = (upper - lower) / (steps - 1)
    return [lower + (step * index) for index in range(steps)]


def _monotonicity_violation(values: list[float], direction: str, tolerance: float) -> float:
    if len(values) < 2:
        return 0.0

    direction_name = direction.lower()
    violations: list[float] = []
    for previous, current in zip(values, values[1:], strict=False):
        if direction_name == "nonincreasing":
            violations.append(max(0.0, current - previous))
        elif direction_name == "nondecreasing":
            violations.append(max(0.0, previous - current))
        elif direction_name == "strictly_nonincreasing":
            violations.append(max(0.0, current - previous + tolerance))
        elif direction_name == "strictly_nondecreasing":
            violations.append(max(0.0, previous - current + tolerance))
        else:
            raise ValueError(f"unsupported monotonicity direction: {direction}")

    return max(violations, default=0.0)
