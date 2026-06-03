"""Example model focused on drift checks."""


class DriftModel:
    def __init__(self) -> None:
        self.elasticity = -0.2
        self.supply = 5.0

    def predict(self, features: dict[str, float]) -> float:
        shock = float(features.get("shock", 0.0))
        return 1.0 + 2.0 * shock
