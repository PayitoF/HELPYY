import numpy as np
import pandas as pd


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def build_target(risk_features: pd.DataFrame, base_rate: float = 0.15, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = risk_features.copy()

    logits = (
        -np.log(1 / base_rate - 1)
        + 4.0 * df["risk_index"]
        + 2.0 * (1 - df["on_time_rate"])
        + 1.5 * df["overdue_rate"]
        + 1.8 * df["rejection_rate"]
        - 0.8 * df["pct_conversion"]
    )

    df["p_default"] = _sigmoid(logits)
    df["default"] = rng.random(len(df)) < df["p_default"]

    return df
