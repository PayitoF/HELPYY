import numpy as np
import pandas as pd


def _logit(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def generate_clients(
    n_clients: int = 20000,
    seed: int = 42,
    start_date: str = "2022-01-01",
    end_date: str = "2024-12-31",
) -> pd.DataFrame:
    """Generate base clients table with risk attached.

    Returns
    -------
    pd.DataFrame
        client_id, national_id, onboarding_date, declared_income, employment_type,
        is_banked, age, sex, city_type, education_level, household_size,
        residence_type, base_risk_score
    """
    rng = np.random.default_rng(seed)

    client_id = np.arange(1, n_clients + 1)
    raw_ids = rng.integers(100_000_000, 999_999_999, size=n_clients)
    national_id = [f"{x:09d}" for x in np.unique(raw_ids)]
    if len(national_id) < n_clients:
        extra = n_clients - len(national_id)
        extra_ids = rng.integers(100_000_000, 999_999_999, size=extra)
        national_id.extend([f"{x:09d}" for x in extra_ids])
    national_id = national_id[:n_clients]

    onboarding_date = pd.to_datetime(
        rng.integers(
            pd.Timestamp(start_date).value // 10**9,
            pd.Timestamp(end_date).value // 10**9,
            size=n_clients,
        ),
        unit="s",
    )

    employment_types = ["informal", "formal", "independent"]
    emp_probs = [0.55, 0.30, 0.15]
    employment_type = rng.choice(employment_types, size=n_clients, p=emp_probs)

    # Income by employment type: systematic dependence.
    means = {"informal": 13.0, "formal": 14.0, "independent": 14.5}
    scales = {"informal": 0.6, "formal": 0.45, "independent": 0.8}
    declared_income = np.zeros(n_clients, dtype=float)
    for et in employment_types:
        mask = employment_type == et
        declared_income[mask] = rng.lognormal(mean=means[et], sigma=scales[et], size=mask.sum())

    # Convert to COP pesos roughly. use clamp
    declared_income = np.clip(declared_income * 100_000, 300_000, 15_000_000)

    # Demographic base (for risk profiling)
    age = rng.integers(18, 75, size=n_clients)
    sex = rng.choice(["M", "F"], size=n_clients, p=[0.52, 0.48])
    city_type = rng.choice(["urban", "rural"], size=n_clients, p=[0.75, 0.25])
    education_level = rng.choice(
        ["none", "primary", "secondary", "technical", "university"],
        size=n_clients,
        p=[0.05, 0.25, 0.35, 0.2, 0.15],
    )
    household_size = rng.integers(1, 8, size=n_clients)
    residence_type = rng.choice(
        ["owned", "rented", "family", "other"], size=n_clients, p=[0.35, 0.45, 0.15, 0.05]
    )

    # Bancarización con signal: ingreso y empleo
    log_income = np.log(declared_income + 1)
    is_banked_score = -7.5 + 0.8 * log_income + 1.0 * (employment_type == "formal") + 0.5 * (
        employment_type == "independent"
    )
    is_banked_prob = _logit(is_banked_score)
    is_banked = rng.random(n_clients) < is_banked_prob

    # Risk base
    f_income = (np.max(log_income) - log_income) / np.max(log_income)
    f_emp = np.select([employment_type == "informal", employment_type == "independent"], [1.0, 0.65], 0.0)
    f_banked = np.where(is_banked, 0.0, 0.8)
    f_age = np.select([age < 22, age > 60], [0.7, 0.5], 0.0)
    f_city = np.where(city_type == "rural", 0.3, 0.0)
    f_edu = np.select(
        [education_level == "none", education_level == "primary", education_level == "secondary"],
        [0.6, 0.4, 0.2],
        0.0,
    )
    base_risk_score = (1.1 * f_income + 1.0 * f_emp + 0.8 * f_banked + 0.7 * f_age + 0.4 * f_city + 0.5 * f_edu)
    base_risk_score = (base_risk_score - np.min(base_risk_score)) / (np.max(base_risk_score) - np.min(base_risk_score))

    df = pd.DataFrame(
        {
            "client_id": client_id,
            "national_id": national_id,
            "onboarding_date": onboarding_date,
            "declared_income": declared_income,
            "employment_type": employment_type,
            "is_banked": is_banked,
            "age": age,
            "sex": sex,
            "city_type": city_type,
            "education_level": education_level,
            "household_size": household_size,
            "residence_type": residence_type,
            "base_risk_score": base_risk_score,
            "banked_probability": is_banked_prob,
        }
    )

    return df
