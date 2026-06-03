"""Example model focused on policy and fairness checks."""


class PolicyModel:
    def __init__(self) -> None:
        self.elasticity = -0.2
        self.policy_score = 1.0
        self.redistribution_index = 0.6

    def predict(self, features: dict[str, float]) -> float:
        income = float(features.get("income", 0.0))
        policy_shift = float(features.get("policy_shift", 0.0))
        support_level = float(features.get("support_level", 0.0))
        return 0.65 + (0.01 * income) + (0.4 * policy_shift) + (0.05 * support_level)
