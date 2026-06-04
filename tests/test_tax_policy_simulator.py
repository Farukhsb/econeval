from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


def _load_tax_policy_model() -> type:
    model_path = Path("examples/tax_policy_simulator/model.py")
    spec = importlib.util.spec_from_file_location("tax_policy_simulator_model", model_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TaxPolicyModel


def test_tax_policy_sample_matches_model_outputs() -> None:
    model_cls = _load_tax_policy_model()
    model = model_cls()
    sample_path = Path("examples/tax_policy_simulator/data/sample_income.csv")

    with sample_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert 10 <= len(rows) <= 50
    assert {row["income_bracket"] for row in rows} == {"<=50K", ">50K"}

    predictions = [round(model.predict(row), 2) for row in rows]
    actuals = [round(float(row["actual"]), 2) for row in rows]
    assert predictions == actuals


def test_tax_liability_is_monotonic_in_income() -> None:
    model_cls = _load_tax_policy_model()
    model = model_cls()

    values = [model.tax_liability_at(income) for income in [0.0, 20_000.0, 60_000.0, 120_000.0]]

    assert values == sorted(values)
