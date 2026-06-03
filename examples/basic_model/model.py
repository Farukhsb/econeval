"""Example model placeholder for EconEval."""


class DemoModel:
    def __init__(self) -> None:
        self.elasticity = -0.4
        self.supply = 10.0
        self.consumption = 6.0
        self.investment = 2.0
        self.government = 1.0
        self.net_exports = 1.0
        self.gdp = self.consumption + self.investment + self.government + self.net_exports

    def predict(self, features: dict[str, float]) -> float:
        shock = float(features.get("shock", 0.0))
        return 1.0 + 2.0 * shock

    def demand(self, price: float) -> float:
        return max(0.0, 12.0 - (2.0 * price))

    def solve(self) -> bool:
        return True
