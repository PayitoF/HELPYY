import numpy as np
import pandas as pd


def generate_loan_applications(clients: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    application_id = 1

    for _, client in clients.iterrows():
        risk = client["base_risk_score"]
        n_apps = int(np.clip(rng.poisson(lam=np.interp(risk, [0, 1], [1.2, 2.5])), 1, 5))

        for i in range(n_apps):
            apply_date = pd.Timestamp("2024-01-01") + pd.Timedelta(days=rng.integers(0, 365))
            amount_requested = float(np.clip(rng.normal(loc=700_000 - 250_000 * (1 - risk), scale=250_000), 100_000, 3_000_000))
            decision_score = np.clip(0.5 + 0.8 * (1 - risk) + rng.normal(0, 0.15), 0, 1)
            decision = "approved" if decision_score > np.interp(risk, [0, 1], [0.3, 0.8]) else "rejected"

            rows.append(
                {
                    "application_id": application_id,
                    "client_id": client["client_id"],
                    "apply_date": apply_date,
                    "amount_requested": amount_requested,
                    "product_type": rng.choice(["nano", "micro", "reload"], p=[0.55, 0.35, 0.1]),
                    "decision_score": decision_score,
                    "decision": decision,
                }
            )
            application_id += 1

    return pd.DataFrame(rows).sort_values(["client_id", "apply_date"]).reset_index(drop=True)
