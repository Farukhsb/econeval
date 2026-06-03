"""Intentionally broken example for EconEval tests."""


class BrokenModel:
    def __init__(self) -> None:
        self.elasticity = 0.4
        self.supply = -2.0

    def predict(self, features: dict[str, float]) -> float:
        shock = float(features.get("shock", 0.0))
        return 0.5 + shock
