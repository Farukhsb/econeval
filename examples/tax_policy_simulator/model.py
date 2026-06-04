"""Adult Census Income inspired tax policy simulator.

The model turns a few income-related Adult dataset fields into a taxable
income estimate, then applies a small progressive tax schedule.
"""

from __future__ import annotations

from collections.abc import Mapping


class TaxPolicyModel:
    base_deduction = 12_000.0
    low_rate = 0.10
    middle_rate = 0.20
    top_rate = 0.28
    first_band = 15_000.0
    second_band = 45_000.0

    def __init__(self) -> None:
        self.age = 0.0
        self.education_num = 0.0
        self.hours_per_week = 0.0
        self.capital_gain = 0.0
        self.capital_loss = 0.0
        self.income_bracket = "<=50K"

    def predict(self, features: Mapping[str, object]) -> float:
        return self.tax_liability_for_features(features)

    def tax_liability_at(self, income: float) -> float:
        taxable_income = max(0.0, float(income))
        if taxable_income <= self.first_band:
            return round(taxable_income * self.low_rate, 2)

        if taxable_income <= self.second_band:
            return round(
                (self.first_band * self.low_rate)
                + ((taxable_income - self.first_band) * self.middle_rate),
                2,
            )

        return round(
            (self.first_band * self.low_rate)
            + ((self.second_band - self.first_band) * self.middle_rate)
            + ((taxable_income - self.second_band) * self.top_rate),
            2,
        )

    def tax_liability_for_features(self, features: Mapping[str, object]) -> float:
        return self.tax_liability_at(self.taxable_income_for_features(features))

    @property
    def taxable_income(self) -> float:
        return self.taxable_income_for_features(self._current_features())

    @property
    def tax_liability(self) -> float:
        return self.tax_liability_at(self.taxable_income)

    @property
    def effective_tax_rate(self) -> float:
        taxable_income = self.taxable_income
        if taxable_income <= 0:
            return 0.0
        return round(self.tax_liability / taxable_income, 6)

    def taxable_income_for_features(self, features: Mapping[str, object]) -> float:
        base_income = 18_000.0 if self._income_bracket(features) == "<=50K" else 52_000.0
        education_num = self._float_feature(features, "education_num")
        hours_per_week = self._float_feature(features, "hours_per_week")
        age = self._float_feature(features, "age")
        capital_gain = self._float_feature(features, "capital_gain")
        capital_loss = self._float_feature(features, "capital_loss")

        education_bonus = max(0.0, education_num - 9.0) * 1_800.0
        hours_bonus = max(0.0, hours_per_week - 40.0) * 150.0
        age_bonus = max(0.0, age - 25.0) * 40.0
        capital_bonus = (capital_gain * 0.03) - (capital_loss * 0.01)

        gross_income = base_income + education_bonus + hours_bonus + age_bonus + capital_bonus
        return round(max(0.0, gross_income - self.base_deduction), 2)

    def _current_features(self) -> dict[str, object]:
        return {
            "age": self.age,
            "education_num": self.education_num,
            "hours_per_week": self.hours_per_week,
            "capital_gain": self.capital_gain,
            "capital_loss": self.capital_loss,
            "income_bracket": self.income_bracket,
        }

    def _income_bracket(self, features: Mapping[str, object]) -> str:
        bracket = features.get("income_bracket", features.get("income", "<=50K"))
        return str(bracket).strip()

    def _float_feature(self, features: Mapping[str, object], key: str) -> float:
        value = features.get(key, 0.0)
        if value in ("", None):
            return 0.0
        return float(value)
