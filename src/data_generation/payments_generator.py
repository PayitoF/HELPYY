import numpy as np
import pandas as pd


def generate_payments(
    clients: pd.DataFrame,
    loan_applications: pd.DataFrame,
    seed: int = 42,
    lookback_months: int = 12,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    payment_id = 1

    # Join client risk to applications
    apps = loan_applications.merge(clients[["client_id", "base_risk_score"]], on="client_id", how="left")
    for _, app in apps.iterrows():
        # Define payment behavior depending on risk
        risk = app["base_risk_score"]
        amount = app["amount_requested"]
        # Simular plazo y cuota
        term_months = int(rng.choice([3, 6, 9, 12], p=[0.25, 0.35, 0.2, 0.2]))
        due_dates = pd.date_range(start=app["apply_date"], periods=term_months, freq="MS")
        for d in due_dates:
            # ya sea pago puntual, retrasado o no pagado
            delay_days = int(np.clip(rng.normal(loc=3 + 20 * risk, scale=8), -10, 90))
            paid_date = d + pd.Timedelta(days=max(delay_days, 0))
            due_amount = amount / term_months
            paid_amount = due_amount * (1.0 - 0.05 * risk) + rng.normal(0, 0.015 * due_amount)
            paid_amount = max(0.0, min(paid_amount, due_amount * 1.2))
            dpd = max(0, (paid_date - d).days)

            rows.append(
                {
                    "payment_id": payment_id,
                    "client_id": app["client_id"],
                    "loan_id": app["application_id"],
                    "due_date": d,
                    "paid_date": paid_date,
                    "amount_due": due_amount,
                    "amount_paid": paid_amount,
                    "dpd": dpd,
                }
            )
            payment_id += 1
    return pd.DataFrame(rows)
