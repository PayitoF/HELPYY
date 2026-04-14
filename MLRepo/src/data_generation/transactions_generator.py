import numpy as np
import pandas as pd


def generate_transactions(clients: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    tx_id = 1

    for _, row in clients.iterrows():
        risk = row["base_risk_score"]
        mean_txs = int(np.interp(risk, [0, 1], [18, 8]))
        n_txs = rng.poisson(lam=max(mean_txs, 4))
        n_txs = np.clip(n_txs, 4, 60)

        last_balance = 0.0
        for i in range(n_txs):
            amount = float(np.clip(rng.normal(loc=150_000 - 75_000 * risk, scale=70_000), 10_000, 600_000))
            if rng.random() < 0.35 + 0.3 * risk:
                tx_type = "expense"
                last_balance -= amount
            else:
                tx_type = "income"
                last_balance += amount
            rows.append(
                {
                    "tx_id": tx_id,
                    "client_id": row["client_id"],
                    "tx_date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=rng.integers(0, 365)),
                    "amount": amount,
                    "tx_type": tx_type,
                    "balance": last_balance,
                    "merchant_category": rng.choice(["food", "transport", "retail", "services", "utilities"]),
                }
            )
            tx_id += 1

    return pd.DataFrame(rows).sort_values(["client_id", "tx_date"]).reset_index(drop=True)
