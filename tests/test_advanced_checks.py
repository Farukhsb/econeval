from pathlib import Path

import numpy as np
import pytest

from econeval.config import EconomicCheck, StressTest
from econeval.invariants import evaluate_expression
from econeval.scenarios import (
    economic_suite_passed,
    run_economic_check,
    run_fairness_checks,
    run_stress_test,
)


class AdvancedModel:
    def __init__(self) -> None:
        self.input_data = {"unemployment_rate": 0.05, "energy_costs": 1.0}
        self.elasticity = -0.35
        self.policy_score = 1.0
        self.consumption = 6.0
        self.investment = 2.0
        self.government = 1.0
        self.net_exports = 1.0
        self.gdp = self.consumption + self.investment + self.government + self.net_exports

    def predict(self, features: dict[str, float]) -> float:
        shock = float(features.get("shock", 0.0))
        return 1.0 + (2.0 * shock)

    def demand(self, price: float) -> float:
        return max(0.0, 12.0 - (2.0 * price))

    @property
    def predicted_gdp_growth(self) -> float:
        unemployment_rate = float(self.input_data["unemployment_rate"])
        energy_costs = float(self.input_data["energy_costs"])
        return 0.02 - (0.15 * unemployment_rate) - (0.02 * (energy_costs - 1.0))

    def solve(self) -> bool:
        return True


def test_accounting_identity_check_passes() -> None:
    model = AdvancedModel()
    check = EconomicCheck(
        name="gdp_accounting_identity",
        kind="accounting_identity",
        left_expression="model.gdp",
        right_expression=(
            "model.consumption + model.investment + model.government + model.net_exports"
        ),
        tolerance=1e-9,
    )

    result = run_economic_check(model, check)

    assert result.passed is True
    assert result.value == 0.0
    assert economic_suite_passed([result]) is True


def test_monotonicity_check_passes() -> None:
    model = AdvancedModel()
    check = EconomicCheck(
        name="demand_curve_monotonicity",
        kind="monotonicity",
        method="demand",
        variable="price",
        lower=1.0,
        upper=5.0,
        steps=5,
        direction="nonincreasing",
    )

    result = run_economic_check(model, check)

    assert result.passed is True
    assert result.observations == [10.0, 8.0, 6.0, 4.0, 2.0]


def test_convergence_check_passes() -> None:
    model = AdvancedModel()
    check = EconomicCheck(
        name="solver_converges",
        kind="convergence",
        method="solve",
        initial_states=[{"supply": 6.0}, {"supply": 8.0}, {"supply": 10.0}],
    )

    result = run_economic_check(model, check)

    assert result.passed is True
    assert result.value == 0.0
    assert result.observations == [1.0, 1.0, 1.0]


def test_convergence_check_reports_worst_state() -> None:
    class FailingModel(AdvancedModel):
        def solve(self) -> bool:
            return self.supply < 9.0

    model = FailingModel()
    check = EconomicCheck(
        name="solver_converges",
        kind="convergence",
        method="solve",
        initial_states=[{"supply": 6.0}, {"supply": 8.0}, {"supply": 10.0}],
    )

    result = run_economic_check(model, check)

    assert result.passed is False
    assert result.worst_state == {"supply": 10.0}


def test_boundary_condition_check_samples_initial_states() -> None:
    model = AdvancedModel()
    check = EconomicCheck(
        name="supply_stays_bounded",
        kind="boundary_condition",
        expression="model.supply",
        lower=0.0,
        upper=20.0,
        initial_states=[{"supply": 6.0}, {"supply": 8.0}, {"supply": 10.0}],
    )

    result = run_economic_check(model, check)

    assert result.passed is True
    assert result.value == 0.0
    assert result.observations == [6.0, 8.0, 10.0]


def test_boundary_condition_check_reports_worst_state() -> None:
    model = AdvancedModel()
    check = EconomicCheck(
        name="supply_out_of_bounds",
        kind="boundary_condition",
        expression="model.supply",
        lower=0.0,
        upper=20.0,
        initial_states=[{"supply": 6.0}, {"supply": 25.0}, {"supply": 10.0}],
    )

    result = run_economic_check(model, check)

    assert result.passed is False
    assert result.worst_state == {"supply": 25.0}
    assert result.worst_value == 25.0


def test_scan_check_detects_monotonic_response() -> None:
    model = AdvancedModel()
    check = EconomicCheck(
        name="price_elasticity_scan",
        kind="scan",
        method="demand",
        input_variable="price",
        output_variable="quantity",
        expected_direction="nonincreasing",
        perturbations=[0.01, 0.05, 0.1],
    )

    result = run_economic_check(model, check)

    assert result.passed is True
    assert result.scan_inputs == [1.0, 1.01, 1.05, 1.1]
    assert result.observations == [10.0, 9.98, 9.9, 9.8]


def test_scan_check_detects_elasticity_sign() -> None:
    model = AdvancedModel()
    check = EconomicCheck(
        name="price_elasticity_scan",
        kind="scan",
        scan_kind="elasticity",
        method="demand",
        input_variable="price",
        output_variable="quantity",
        expected_direction="nonincreasing",
        perturbations=[0.01, 0.05, 0.1],
    )

    result = run_economic_check(model, check)

    assert result.passed is True
    assert result.observations == pytest.approx([-0.2, -0.2, -0.2])


def test_synthetic_stress_test_passes() -> None:
    model = AdvancedModel()
    test = StressTest(
        name="synthetic_shock_response",
        metric="relative_change",
        threshold=0.5,
        kind="synthetic",
        variable="shock",
        shock_type="multiplier",
        value=1.5,
    )

    result = run_stress_test(model, test)

    assert result.passed is True
    assert result.value == 1 / 3


def test_parameter_shock_stress_test_passes() -> None:
    model = AdvancedModel()
    test = StressTest(
        name="policy_parameter_shock",
        kind="parameter_shock",
        metric="invariants",
        threshold=0.0,
        manipulations=[
            {"variable": "elasticity", "action": "add", "value": 0.05},
        ],
        invariants=[
            {"name": "elasticity_stays_negative", "expression": "model.elasticity < 0"},
        ],
    )

    result = run_stress_test(model, test)

    assert result.passed is True
    assert result.value == 0.0
    assert result.failure_count == 0
    assert result.manipulations == [
        {"variable": "elasticity", "action": "add", "value": 0.05},
    ]
    assert result.invariants and result.invariants[0]["passed"] is True


def test_monte_carlo_stress_test_passes() -> None:
    model = AdvancedModel()
    test = StressTest(
        name="elasticity_monte_carlo",
        kind="monte_carlo",
        metric="invariants",
        threshold=0.0,
        samples=12,
        seed=7,
        manipulations=[
            {"variable": "elasticity", "action": "add", "value": 0.0, "sigma": 0.02},
        ],
        invariants=[
            {"name": "elasticity_remains_reasonable", "expression": "model.elasticity < 0.5"},
        ],
    )

    result = run_stress_test(model, test)

    assert result.passed is True
    assert result.samples == 12
    assert result.failure_count == 0
    assert result.percentiles == {"p10": 0.0, "p50": 0.0, "p90": 0.0}
    assert result.value == 0.0


def test_monte_carlo_with_correlated_shocks_passes() -> None:
    model = AdvancedModel()
    test = StressTest(
        name="correlated_monte_carlo",
        kind="monte_carlo",
        metric="invariants",
        threshold=0.0,
        samples=8,
        seed=11,
        percentile_cutoffs=[5, 50, 95],
        manipulations=[
            {
                "variable": "elasticity",
                "action": "add",
                "value": 0.0,
                "sigma": 0.02,
                "correlation_group": "policy",
                "correlation": 0.75,
            },
            {
                "variable": "policy_score",
                "action": "add",
                "value": 0.0,
                "sigma": 0.05,
                "correlation_group": "policy",
                "correlation": 0.75,
            },
        ],
        invariants=[
            {"name": "elasticity_remains_reasonable", "expression": "model.elasticity < 0.5"},
            {"name": "policy_score_stays_non_negative", "expression": "model.policy_score >= 0"},
        ],
    )

    result = run_stress_test(model, test)

    assert result.passed is True
    assert result.samples == 8
    assert result.failure_count == 0
    assert set(result.percentiles or {}) == {"p5", "p50", "p95"}
    assert result.worst_sample is not None
    assert result.worst_sample["failed_invariants"] == 0


def test_grid_stress_test_detects_broad_parameter_sweep() -> None:
    model = AdvancedModel()
    test = StressTest(
        name="policy_grid_sweep",
        kind="grid",
        metric="invariants",
        threshold=0.5,
        sweep_axes=[
            {"variable": "supply", "values": [6.0, 8.0, 12.0]},
            {"variable": "policy_score", "values": [0.5, 1.0, 1.5]},
        ],
        invariants=[
            {"name": "supply_stays_reasonable", "expression": "model.supply < 11"},
            {"name": "policy_score_stays_positive", "expression": "model.policy_score > 0"},
        ],
    )

    result = run_stress_test(model, test)

    assert result.passed is True
    assert result.samples == 9
    assert result.grid_points == 9
    assert result.failure_count == 3
    assert result.worst_sample is not None
    assert result.worst_sample["failed_invariants"] == 1
    assert result.percentiles == {"p10": 0.0, "p50": 0.0, "p90": 0.5}


def test_fairness_checks_support_inequality_metrics(tmp_path: Path) -> None:
    dataset = tmp_path / "fairness.csv"
    dataset.write_text(
        "group,signal,actual\na,0.0,1.0\na,1.0,2.0\nb,0.5,1.5\nb,1.5,2.5\n",
        encoding="utf-8",
    )

    model = AdvancedModel()
    results = run_fairness_checks(
        model,
        str(dataset),
        ["gini", "atkinson"],
        group_column="group",
        positive_threshold=1.5,
    )

    assert [result.metric for result in results] == ["gini", "atkinson"]
    assert all(result.passed for result in results)


def test_numexpr_backend_handles_vectorized_arrays() -> None:
    result = evaluate_expression(
        "supply >= demand",
        {
            "supply": np.array([3.0, 4.0, 5.0]),
            "demand": np.array([2.0, 4.0, 1.0]),
        },
        backend="numexpr",
    )

    assert result.tolist() == [True, True, True]
