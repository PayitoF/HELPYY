
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd


def extract_logistic_feature_importance(
    feature_names: List[str],
    coefficients: np.ndarray,
    top_k: int = 5,
) -> pd.DataFrame:
    coef = np.asarray(coefficients).ravel()
    importance_df = pd.DataFrame(
        {
            "feature": feature_names,
            "coefficient": coef,
            "abs_coefficient": np.abs(coef),
        }
    ).sort_values("abs_coefficient", ascending=False)

    importance_df["rank"] = range(1, len(importance_df) + 1)
    return importance_df.head(top_k).reset_index(drop=True)


def extract_full_logistic_feature_importance(
    feature_names: List[str],
    coefficients: np.ndarray,
) -> pd.DataFrame:
    coef = np.asarray(coefficients).ravel()
    importance_df = pd.DataFrame(
        {
            "feature": feature_names,
            "coefficient": coef,
            "abs_coefficient": np.abs(coef),
        }
    ).sort_values("abs_coefficient", ascending=False)

    importance_df["rank"] = range(1, len(importance_df) + 1)
    return importance_df.reset_index(drop=True)


def build_feature_origin_map(selected_features: List[str]) -> List[Dict[str, str]]:
    mapped = []
    for feature in selected_features:
        if "__" in feature:
            source_table = feature.split("__", 1)[0]
        else:
            source_table = "clients"
        mapped.append(
            {
                "feature": feature,
                "source_table": source_table,
            }
        )
    return mapped
