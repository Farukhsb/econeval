from __future__ import annotations

import pytest

from econeval.config import EconomicCheck, StressTest
from econeval.interop import describe_model_interface, resolve_model_runtime
from econeval.scenarios import run_economic_check, run_stress_test


class CallableModel:
    def __call__(self, features: dict[str, float]) -> float:
        shock = float(features.get("shock", 0.0))
        return 1.0 + shock


class PymcLikeModel:
    def sample_posterior_predictive(self, features: dict[str, float]) -> dict[str, list[float]]:
        shock = float(features.get("shock", 0.0))
        return {"prediction": [1.0 + shock, 1.5 + shock, 2.0 + shock]}


class GamsLikeModel:
    def run(self) -> dict[str, str]:
        return {"model_status": "Optimal"}


class SklearnLikeModel:
    feature_names_in_ = ("shock", "demand")

    def predict(self, rows: list[list[float]] | object) -> list[float]:
        if hasattr(rows, "iloc"):
            row = rows.iloc[0]
            values = [float(value) for value in row.tolist()]
        else:
            row = rows[0]
            values = [float(value) for value in row]
        return [sum(values)]


class StatsmodelsLikeModel:
    exog_names = ("const", "shock")

    def predict(self, rows: list[list[float]] | object) -> list[float]:
        if hasattr(rows, "iloc"):
            row = rows.iloc[0]
            values = [float(value) for value in row.tolist()]
        else:
            row = rows[0]
            values = [float(value) for value in row]
        return [sum(values)]


def test_callable_model_supports_stress_checks() -> None:
    model = CallableModel()
    test = StressTest(
        name="callable_model",
        kind="synthetic",
        metric="relative_change",
        threshold=1.0,
        variable="shock",
        shock_type="absolute",
        baseline_value=0.0,
        value=0.5,
    )

    result = run_stress_test(model, test)

    assert result.passed is True
    assert result.value == 0.5


def test_pymc_style_predictive_sampling_is_normalized() -> None:
    model = PymcLikeModel()
    runtime = resolve_model_runtime(model, prediction_key="prediction")

    assert "sample_posterior_predictive" in describe_model_interface(model)
    assert runtime.predict({"shock": 0.5}) == pytest.approx(2.0)


def test_solver_status_strings_are_recognized() -> None:
    model = GamsLikeModel()
    check = EconomicCheck(
        name="solver_converges",
        kind="convergence",
        method="run",
        initial_states=[{}],
    )

    result = run_economic_check(model, check)

    assert result.passed is True
    assert result.value == 0.0


def test_sklearn_style_estimators_receive_tabular_inputs() -> None:
    model = SklearnLikeModel()
    runtime = resolve_model_runtime(model)

    assert runtime.predict({"shock": 0.5, "demand": 1.5}) == pytest.approx(2.0)


def test_statsmodels_style_estimators_receive_intercept_and_features() -> None:
    model = StatsmodelsLikeModel()
    runtime = resolve_model_runtime(model)

    assert runtime.predict({"shock": 0.5}) == pytest.approx(1.5)
