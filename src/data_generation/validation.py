import pandas as pd


def validate_datasets(
    clients: pd.DataFrame,
    demographics: pd.DataFrame,
    digital_sessions: pd.DataFrame,
    transactions: pd.DataFrame,
    payments: pd.DataFrame,
    loan_applications: pd.DataFrame,
    risk_features: pd.DataFrame,
):
    checks = []

    checks.append(("clients_pk_unique", clients["client_id"].is_unique))
    checks.append(("demographics_fk", demographics["client_id"].isin(clients["client_id"]).all()))
    checks.append(("digital_sessions_fk", digital_sessions["client_id"].isin(clients["client_id"]).all()))
    checks.append(("transactions_fk", transactions["client_id"].isin(clients["client_id"]).all()))
    checks.append(("payments_fk", payments["client_id"].isin(clients["client_id"]).all()))
    checks.append(("loan_applications_fk", loan_applications["client_id"].isin(clients["client_id"]).all()))
    checks.append(("risk_features_fk", risk_features["client_id"].isin(clients["client_id"]).all()))

    checks.append(("clients_not_na", clients["declared_income"].notna().all()))
    checks.append(("positive_income", (clients["declared_income"] > 0).all()))
    checks.append(("payments_amount", (payments["amount_paid"] >= 0).all()))
    checks.append(("dpd_consistency", (payments["dpd"] >= 0).all()))

    summary = {k: v for k, v in checks}
    if not all(summary.values()):
        failed = [k for k, v in summary.items() if not v]
        raise ValueError(f"Validation failed: {failed}")
    return summary
