import pandas as pd


def build_risk_features(
    clients: pd.DataFrame,
    demographics: pd.DataFrame,
    digital_sessions: pd.DataFrame,
    transactions: pd.DataFrame,
    payments: pd.DataFrame,
    loan_applications: pd.DataFrame,
) -> pd.DataFrame:
    # clients direct signals
    features = clients[["client_id", "declared_income", "employment_type", "is_banked", "base_risk_score"]].copy()

    # demographics
    features = features.merge(
        demographics[["client_id", "age", "city_type", "education_level", "household_size"]],
        on="client_id",
        how="left",
    )

    # digital
    ds_agg = digital_sessions.groupby("client_id").agg(
        total_sessions=("session_id", "count"),
        avg_duration=("session_duration_sec", "mean"),
        pct_conversion=("conversion", "mean"),
        avg_steps=("steps_completed", "mean"),
    )

    # transactions
    tx_agg = transactions.groupby("client_id").agg(
        tx_count=("tx_id", "count"),
        tx_avg_amount=("amount", "mean"),
        tx_std_amount=("amount", "std"),
        tx_income_pct=("tx_type", lambda x: (x == "income").mean()),
    )
    tx_agg["tx_std_amount"] = tx_agg["tx_std_amount"].fillna(0)

    # payments
    pay_agg = payments.groupby("client_id").agg(
        payments_count=("payment_id", "count"),
        on_time_rate=("dpd", lambda x: (x <= 0).mean()),
        overdue_rate=("dpd", lambda x: (x > 30).mean()),
        max_dpd=("dpd", "max"),
    )

    # loan apps
    loan_agg = loan_applications.groupby("client_id").agg(
        apps_count=("application_id", "count"),
        approved_count=("decision", lambda x: (x == "approved").sum()),
        avg_decision_score=("decision_score", "mean"),
    )
    loan_agg["rejection_rate"] = 1 - loan_agg["approved_count"] / loan_agg["apps_count"]

    # Consolidate
    features = features.merge(ds_agg, on="client_id", how="left")
    features = features.merge(tx_agg, on="client_id", how="left")
    features = features.merge(pay_agg, on="client_id", how="left")
    features = features.merge(loan_agg, on="client_id", how="left")

    # Fill na with defaults
    features["total_sessions"] = features["total_sessions"].fillna(0)
    features["avg_duration"] = features["avg_duration"].fillna(0)
    features["pct_conversion"] = features["pct_conversion"].fillna(0)
    features["avg_steps"] = features["avg_steps"].fillna(0)
    features["tx_count"] = features["tx_count"].fillna(0)
    features["on_time_rate"] = features["on_time_rate"].fillna(0)
    features["overdue_rate"] = features["overdue_rate"].fillna(0)
    features["max_dpd"] = features["max_dpd"].fillna(0)
    features["apps_count"] = features["apps_count"].fillna(0)
    features["rejection_rate"] = features["rejection_rate"].fillna(0)

    # Derivados de riesgo
    features["risk_index"] = (
        0.2 * (1 / (1 + features["declared_income"]))
        + 0.6 * (1 - features["on_time_rate"])
        + 0.4 * features["overdue_rate"]
        + 0.3 * features["rejection_rate"]
        + 0.2 * (1 - features["pct_conversion"])
        + 0.2 * (1 - features["is_banked"].astype(int))
        + 0.25 * features["base_risk_score"]
    )

    features["risk_index"] = (features["risk_index"] - features["risk_index"].min()) / (
        features["risk_index"].max() - features["risk_index"].min()
    )

    return features
