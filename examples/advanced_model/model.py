"""Example model covering the advanced EconEval checks."""


class AdvancedModel:
    def __init__(self) -> None:
        self.input_data = {
            "unemployment_rate": 0.05,
            "energy_costs": 1.0,
        }
        self.elasticity = -0.35
        self.policy_score = 1.0
        self.supply = 8.0
        self.coefficients = [1.0, 0.5]
        self.consumption = 5.0
        self.investment = 2.0
        self.government = 1.0
        self.net_exports = 1.0
        self.gdp = self.consumption + self.investment + self.government + self.net_exports

    def predict(self, features: dict[str, float]) -> float:
        shock = float(features.get("shock", 0.0))
        signal = float(features.get("signal", 0.0))
        return 1.0 + (0.8 * shock) + (0.5 * signal)

    @property
    def predicted_gdp_growth(self) -> float:
        unemployment_rate = float(self.input_data["unemployment_rate"])
        energy_costs = float(self.input_data["energy_costs"])
        return 0.02 - (0.15 * unemployment_rate) - (0.02 * (energy_costs - 1.0))

    def demand(self, price: float) -> float:
        return max(0.0, 11.0 - (1.5 * price))

    def solve(self) -> bool:
        return self.supply >= 0
