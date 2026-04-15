
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
import warnings

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler


@dataclass
class PreprocessArtifacts:
    preprocessor: ColumnTransformer
    numeric_features: List[str]
    categorical_features: List[str]
    datetime_features: List[str]


def _try_parse_datetime(series: pd.Series) -> pd.Series:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        try:
            return pd.to_datetime(series, errors="coerce", format="mixed")
        except TypeError:
            return pd.to_datetime(series, errors="coerce")


def _detect_datetime_string_columns(df: pd.DataFrame, candidate_columns: List[str]) -> List[str]:
    datetime_columns: List[str] = []

    for col in candidate_columns:
        series = df[col]

        if pd.api.types.is_datetime64_any_dtype(series):
            datetime_columns.append(col)
            continue

        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            continue

        parsed = _try_parse_datetime(series)
        parse_ratio = parsed.notna().mean() if len(series) else 0.0

        if parse_ratio >= 0.95:
            df[col] = parsed
            datetime_columns.append(col)

    return datetime_columns


def split_feature_types(df: pd.DataFrame) -> Tuple[List[str], List[str], List[str]]:
    working_df = df.copy()

    numeric_features = working_df.select_dtypes(include=["number", "bool"]).columns.tolist()
    remaining = [col for col in working_df.columns if col not in numeric_features]

    datetime_features = _detect_datetime_string_columns(working_df, remaining)
    categorical_features = [
        col for col in working_df.columns
        if col not in numeric_features and col not in datetime_features
    ]

    return numeric_features, categorical_features, datetime_features


def _datetime_to_ordinal_days(x):
    if isinstance(x, pd.DataFrame):
        out = x.copy()
        for col in out.columns:
            series = _try_parse_datetime(out[col])
            out[col] = series.map(lambda v: v.toordinal() if pd.notna(v) else float("nan"))
        return out

    arr = pd.DataFrame(x)
    for col in arr.columns:
        series = _try_parse_datetime(arr[col])
        arr[col] = series.map(lambda v: v.toordinal() if pd.notna(v) else float("nan"))
    return arr.values


def build_preprocessor(df: pd.DataFrame, scale_numeric: bool = True, scale_datetime: bool = True) -> PreprocessArtifacts:
    working_df = df.copy()
    numeric_features, categorical_features, datetime_features = split_feature_types(working_df)

    numeric_steps = [
        ("imputer", SimpleImputer(strategy="median")),
    ]
    if scale_numeric:
        numeric_steps.append(("scaler", StandardScaler()))
    numeric_transformer = Pipeline(steps=numeric_steps)

    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    datetime_steps = [
        (
            "to_ordinal_days",
            FunctionTransformer(
                _datetime_to_ordinal_days,
                validate=False,
                feature_names_out="one-to-one",
            ),
        ),
        ("imputer", SimpleImputer(strategy="median")),
    ]
    if scale_datetime:
        datetime_steps.append(("scaler", StandardScaler()))
    datetime_transformer = Pipeline(steps=datetime_steps)

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, numeric_features),
            ("cat", categorical_transformer, categorical_features),
            ("dt", datetime_transformer, datetime_features),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )

    return PreprocessArtifacts(
        preprocessor=preprocessor,
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        datetime_features=datetime_features,
    )
