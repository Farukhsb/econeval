"""Example model focused on fairness checks."""


class FairnessModel:
    def __init__(self) -> None:
        self.elasticity = -0.3
        self.supply = 7.0

    def predict(self, features: dict[str, float]) -> float:
        signal = float(features.get("signal", 0.0))
        return 1.0 + signal

