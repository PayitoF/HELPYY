import pandas as pd

def generate_demographics(clients: pd.DataFrame) -> pd.DataFrame:
    """Generate demographics table for each client.

    clients already includes demographics fields, but separamos en tabla dedicada.
    """
    # Asumiendo we already have age/sex/city_type/education in clients
    df = clients[
        [
            "client_id",
            "age",
            "sex",
            "city_type",
            "education_level",
            "household_size",
            "residence_type",
        ]
    ].copy()
    df["marital_status"] = pd.cut(
        df["age"],
        bins=[17, 24, 34, 44, 54, 64, 100],
        labels=["single", "young_family", "mid_family", "senior_family", "pre_mature", "mature"],
        right=True,
    ).astype(str)
    df["dependents_count"] = (df["household_size"] - 1).clip(lower=0)

    return df
