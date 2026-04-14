
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd


DEFAULT_INPUT_DIR = Path("data/generated")
DEFAULT_OUTPUT_PATH = DEFAULT_INPUT_DIR / "model_mt.csv"
DEFAULT_ID_COL = "client_id"


def _read_required_csv(input_dir: Path, table_name: str) -> pd.DataFrame:
    path = input_dir / f"{table_name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo requerido: {path}")
    return pd.read_csv(path)


def _safe_mode(series: pd.Series):
    non_null = series.dropna()
    if non_null.empty:
        return pd.NA
    mode = non_null.mode(dropna=True)
    if mode.empty:
        return pd.NA
    return mode.iloc[0]


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join(str(part) for part in col if part not in ("", None)).strip("_")
            for col in df.columns.to_flat_index()
        ]
    else:
        df.columns = [str(col) for col in df.columns]
    return df


def _detect_column_groups(
    df: pd.DataFrame,
    id_col: str,
    technical_id_columns: Iterable[str] | None = None,
) -> Tuple[List[str], List[str], List[str]]:
    technical_id_columns = set(technical_id_columns or [])
    technical_id_columns.add(id_col)

    value_columns = [c for c in df.columns if c not in technical_id_columns]

    numeric_cols: List[str] = []
    categorical_cols: List[str] = []
    datetime_cols: List[str] = []

    for col in value_columns:
        series = df[col]

        if pd.api.types.is_datetime64_any_dtype(series):
            datetime_cols.append(col)
            continue

        if pd.api.types.is_bool_dtype(series) or pd.api.types.is_numeric_dtype(series):
            numeric_cols.append(col)
            continue

        parsed = pd.to_datetime(series, errors="coerce")
        parse_ratio = parsed.notna().mean() if len(series) else 0.0
        if parse_ratio >= 0.90:
            df[col] = parsed
            datetime_cols.append(col)
        else:
            categorical_cols.append(col)

    return numeric_cols, categorical_cols, datetime_cols


def _aggregate_one_to_many(
    df: pd.DataFrame,
    table_name: str,
    id_col: str,
) -> pd.DataFrame:
    technical_id_candidates = {
        id_col,
        "session_id",
        "tx_id",
        "payment_id",
        "application_id",
        "loan_id",
    }

    working_df = df.copy()
    numeric_cols, categorical_cols, datetime_cols = _detect_column_groups(
        working_df,
        id_col=id_col,
        technical_id_columns=technical_id_candidates,
    )

    agg_spec: Dict[str, List] = {}

    for col in numeric_cols:
        agg_spec[col] = ["count", "mean", "max", "min", "sum"]

    for col in categorical_cols:
        agg_spec[col] = ["nunique", _safe_mode]

    for col in datetime_cols:
        agg_spec[col] = ["min", "max"]

    if not agg_spec:
        out = working_df[[id_col]].drop_duplicates().copy()
        return out.rename(columns={id_col: id_col})

    aggregated = working_df.groupby(id_col, dropna=False).agg(agg_spec).reset_index()
    aggregated = _flatten_columns(aggregated)

    rename_map = {}
    for col in aggregated.columns:
        if col == id_col:
            continue
        new_name = f"{table_name}__{col}"
        new_name = new_name.replace("<lambda>", "custom")
        new_name = new_name.replace("_safe_mode", "mode")
        rename_map[col] = new_name

    aggregated = aggregated.rename(columns=rename_map)
    return aggregated


def _merge_one_to_one(
    base_df: pd.DataFrame,
    other_df: pd.DataFrame,
    table_name: str,
    id_col: str,
) -> pd.DataFrame:
    if id_col not in other_df.columns:
        raise KeyError(f"La tabla '{table_name}' no contiene la columna '{id_col}'.")

    if not other_df[id_col].is_unique:
        raise ValueError(
            f"La tabla '{table_name}' no es 1:1 por '{id_col}'. "
            "No debe entrar por el flujo de merge directo."
        )

    rename_map = {
        col: f"{table_name}__{col}"
        for col in other_df.columns
        if col != id_col and col in base_df.columns
    }
    prepared = other_df.rename(columns=rename_map)
    return base_df.merge(prepared, on=id_col, how="left")


def build_model_mt(
    input_dir: str | Path = DEFAULT_INPUT_DIR,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    id_col: str = DEFAULT_ID_COL,
) -> pd.DataFrame:
    input_dir = Path(input_dir)
    output_path = Path(output_path)

    clients = _read_required_csv(input_dir, "clients")
    demographics = _read_required_csv(input_dir, "demographics")
    digital_sessions = _read_required_csv(input_dir, "digital_sessions")
    transactions = _read_required_csv(input_dir, "transactions")
    loan_applications = _read_required_csv(input_dir, "loan_applications")
    payments = _read_required_csv(input_dir, "payments")
    risk_features = _read_required_csv(input_dir, "risk_features")
    target = _read_required_csv(input_dir, "target")

    if id_col not in clients.columns:
        raise KeyError(f"La tabla base 'clients' no contiene '{id_col}'.")

    model_mt = clients.copy()

    one_to_one_tables = {
        "demographics": demographics,
        "risk_features": risk_features,
        "target": target,
    }

    for table_name, df in one_to_one_tables.items():
        model_mt = _merge_one_to_one(
            base_df=model_mt,
            other_df=df,
            table_name=table_name,
            id_col=id_col,
        )

    one_to_many_tables = {
        "digital_sessions": digital_sessions,
        "transactions": transactions,
        "loan_applications": loan_applications,
        "payments": payments,
    }

    for table_name, df in one_to_many_tables.items():
        if id_col not in df.columns:
            raise KeyError(f"La tabla '{table_name}' no contiene '{id_col}'.")
        aggregated = _aggregate_one_to_many(df=df, table_name=table_name, id_col=id_col)
        model_mt = model_mt.merge(aggregated, on=id_col, how="left")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    model_mt.to_csv(output_path, index=False)

    return model_mt


def main():
    parser = argparse.ArgumentParser(
        description="Construye la master table model_mt a partir de los CSV generados."
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="Directorio donde viven los CSV generados por el pipeline.",
    )
    parser.add_argument(
        "--output-path",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Ruta del CSV de salida para model_mt.",
    )
    parser.add_argument(
        "--id-col",
        default=DEFAULT_ID_COL,
        help="Columna llave para consolidar la MT.",
    )

    args = parser.parse_args()

    model_mt = build_model_mt(
        input_dir=args.input_dir,
        output_path=args.output_path,
        id_col=args.id_col,
    )

    print(f"model_mt creada exitosamente con shape: {model_mt.shape}")
    print(f"Archivo guardado en: {Path(args.output_path).resolve()}")


if __name__ == "__main__":
    main()
