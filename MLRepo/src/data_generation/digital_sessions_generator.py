import numpy as np
import pandas as pd


def generate_digital_sessions(clients: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # Reducir número de sesiones por cliente según su riesgo base
    risk = clients["base_risk_score"].values
    # Clientes de bajo riesgo tienden a ser persistentes, alto riesgo one-shot o indeciso.
    session_means = np.interp(risk, [0.0, 1.0], [6, 3])
    session_counts = rng.poisson(lam=session_means)
    session_counts = np.clip(session_counts, 1, 20)

    rows = []
    session_id = 1
    for idx, client_id in enumerate(clients["client_id"]):
        n = int(session_counts[idx])
        for j in range(n):
            duration = float(np.clip(rng.normal(loc=180 - 100 * risk[idx], scale=60), 20, 600))
            conversion = rng.random() < np.interp(risk[idx], [0, 1], [0.65, 0.3])
            steps = int(np.clip(rng.normal(loc=4 - 2 * risk[idx], scale=1.2), 1, 6))
            channel = rng.choice(["organic", "ads", "referral", "partner"], p=[0.45, 0.3, 0.15, 0.1])
            referrer = rng.choice(["google", "facebook", "direct", "campaign", "wallet_app"], p=[0.3, 0.25, 0.2, 0.15, 0.1])
            device = rng.choice(["mobile", "desktop", "tablet"], p=[0.7, 0.25, 0.05])
            os = rng.choice(["android", "ios", "windows", "macos"], p=[0.55, 0.35, 0.07, 0.03])
            connection = rng.choice(["4G", "5G", "wifi", "3G"], p=[0.45, 0.2, 0.3, 0.05])
            bandwidth = np.clip(rng.normal(loc=30, scale=12), 2, 100)
            rows.append(
                {
                    "session_id": session_id,
                    "client_id": client_id,
                    "visit_time": pd.Timestamp("2024-03-01") + pd.Timedelta(days=rng.integers(0, 365)),
                    "session_duration_sec": duration,
                    "marketing_channel": channel,
                    "referrer": referrer,
                    "device_type": device,
                    "os": os,
                    "connection_type": connection,
                    "bandwidth_mbps": bandwidth,
                    "steps_completed": steps,
                    "conversion": conversion,
                }
            )
            session_id += 1
    return pd.DataFrame(rows)
