def binary_reward(evaluation: dict) -> float:
    return 1.0 if evaluation.get("passed") else 0.0
