
from __future__ import annotations

import configparser
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from src.training.feature_selection import (
    build_feature_origin_map,
    extract_full_logistic_feature_importance,
    extract_logistic_feature_importance,
)
from src.training.preprocess import build_preprocessor


CONFIG_PATH = Path("src/config/config.ini")


def load_config(config_path: Path = CONFIG_PATH) -> configparser.ConfigParser:
    if not config_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de configuración: {config_path}")
    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8")
    return config


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "si"}


def _parse_csv_list(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_multiline_csv_list(value: str) -> List[str]:
    if not value:
        return []
    normalized = value.replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _resolve_run_dir(models_dir: str, model_name: str, training_mode: str) -> Path:
    base_dir = Path(models_dir) / model_name / training_mode / "runs"
    base_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir = base_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _build_metrics(y_true: pd.Series, y_pred: pd.Series, y_prob: pd.Series) -> Dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_prob)),
    }


def _resolve_training_columns_full(
    df: pd.DataFrame,
    id_column: str,
    target_column: str,
    exclude_columns: List[str],
    exclude_prefixes: List[str],
) -> List[str]:
    excluded_exact = set([id_column, target_column, *exclude_columns])

    selected_columns: List[str] = []
    for col in df.columns:
        if col in excluded_exact:
            continue
        if any(col.startswith(prefix) for prefix in exclude_prefixes):
            continue
        selected_columns.append(col)

    return selected_columns


def _resolve_training_columns_selected(df: pd.DataFrame, selected_training_features: List[str]) -> List[str]:
    missing = [col for col in selected_training_features if col not in df.columns]
    if missing:
        raise KeyError(f"Las siguientes features seleccionadas no existen en model_mt: {missing}")
    return selected_training_features


def train_model(config_path: Path = CONFIG_PATH) -> Dict[str, Any]:
    config = load_config(config_path)

    input_path = Path(config["DATA"]["input_path"])
    target_column = config["DATA"]["target_column"]
    id_column = config["DATA"]["id_column"]

    test_size = float(config["TRAINING"]["test_size"])
    random_state = int(config["TRAINING"]["random_state"])
    max_iter = int(config["TRAINING"]["max_iter"])
    solver = config["TRAINING"]["solver"]
    class_weight_value = config["TRAINING"].get("class_weight", "balanced")
    class_weight = None if class_weight_value.lower() == "none" else class_weight_value
    training_mode = config["TRAINING"].get("training_mode", "full").strip().lower()

    scale_numeric = _parse_bool(config["PREPROCESSING"].get("scale_numeric", "true"))
    scale_datetime = _parse_bool(config["PREPROCESSING"].get("scale_datetime", "true"))

    top_k_features = int(config["FEATURES"]["top_k_features"])
    exclude_columns = _parse_csv_list(config["FEATURES"].get("exclude_columns", ""))
    exclude_prefixes = _parse_csv_list(config["FEATURES"].get("exclude_prefixes", ""))
    selected_training_features = _parse_multiline_csv_list(
        config["FEATURES"].get("selected_training_features", "")
    )

    models_dir = config["OUTPUT"]["models_dir"]
    model_name = config["OUTPUT"]["model_name"]
    export_design_matrix = _parse_bool(config["OUTPUT"].get("export_design_matrix", "false"))

    if not input_path.exists():
        raise FileNotFoundError(f"No se encontró la master table: {input_path}")

    df = pd.read_csv(input_path)

    required_columns = {id_column, target_column}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise KeyError(f"Faltan columnas requeridas en model_mt: {sorted(missing_columns)}")

    if training_mode == "full":
        training_columns = _resolve_training_columns_full(
            df=df,
            id_column=id_column,
            target_column=target_column,
            exclude_columns=exclude_columns,
            exclude_prefixes=exclude_prefixes,
        )
    elif training_mode == "selected":
        if not selected_training_features:
            raise ValueError(
                "training_mode='selected' requiere definir selected_training_features en config.ini"
            )
        training_columns = _resolve_training_columns_selected(
            df=df,
            selected_training_features=selected_training_features,
        )
    else:
        raise ValueError("training_mode debe ser 'full' o 'selected'.")

    X = df[training_columns].copy()
    y = df[target_column].astype(int)

    preprocess_artifacts = build_preprocessor(
        X,
        scale_numeric=scale_numeric,
        scale_datetime=scale_datetime,
    )

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )

    model = LogisticRegression(
        max_iter=max_iter,
        solver=solver,
        class_weight=class_weight,
        random_state=random_state,
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocess_artifacts.preprocessor),
            ("model", model),
        ]
    )

    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    y_prob = pipeline.predict_proba(X_test)[:, 1]
    metrics = _build_metrics(y_test, y_pred, y_prob)

    fitted_preprocessor = pipeline.named_steps["preprocessor"]
    feature_names = fitted_preprocessor.get_feature_names_out().tolist()
    coefficients = pipeline.named_steps["model"].coef_[0]

    full_importance_df = extract_full_logistic_feature_importance(
        feature_names=feature_names,
        coefficients=coefficients,
    )

    top_importance_df = extract_logistic_feature_importance(
        feature_names=feature_names,
        coefficients=coefficients,
        top_k=top_k_features,
    )

    selected_features = top_importance_df["feature"].tolist()
    feature_origin = build_feature_origin_map(selected_features)

    run_dir = _resolve_run_dir(
        models_dir=models_dir,
        model_name=model_name,
        training_mode=training_mode,
    )

    model_path = run_dir / "model.pkl"
    logs_path = run_dir / "model_logs.json"
    metrics_path = run_dir / "metrics.json"
    feature_importance_path = run_dir / "feature_importance.json"
    feature_importance_full_path = run_dir / "feature_importance_full.json"
    train_columns_path = run_dir / "train_columns.json"
    selected_features_path = run_dir / "selected_features.json"

    joblib.dump(pipeline, model_path)

    metrics_payload = {
        "model_name": model_name,
        "training_mode": training_mode,
        "metrics": metrics,
    }
    metrics_path.write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    feature_importance_payload = top_importance_df.to_dict(orient="records")
    feature_importance_path.write_text(
        json.dumps(feature_importance_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    feature_importance_full_payload = full_importance_df.to_dict(orient="records")
    feature_importance_full_path.write_text(
        json.dumps(feature_importance_full_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    train_columns_payload = {
        "training_mode": training_mode,
        "input_columns_before_preprocessing": training_columns,
        "numeric_columns": preprocess_artifacts.numeric_features,
        "categorical_columns": preprocess_artifacts.categorical_features,
        "datetime_columns": preprocess_artifacts.datetime_features,
        "encoded_columns_used_by_model": feature_names,
    }
    train_columns_path.write_text(json.dumps(train_columns_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    selected_features_payload = {
        "training_mode": training_mode,
        "top_k": top_k_features,
        "selected_features": selected_features,
        "feature_origin": feature_origin,
    }
    selected_features_path.write_text(
        json.dumps(selected_features_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logs_payload = {
        "run_timestamp": datetime.now().isoformat(),
        "model_name": model_name,
        "training_mode": training_mode,
        "input_path": str(input_path),
        "run_dir": str(run_dir),
        "target_column": target_column,
        "id_column": id_column,
        "excluded_columns": exclude_columns,
        "excluded_prefixes": exclude_prefixes,
        "selected_training_features": selected_training_features,
        "scale_numeric": scale_numeric,
        "scale_datetime": scale_datetime,
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "n_input_features": int(X.shape[1]),
        "n_encoded_features": int(len(feature_names)),
        "test_size": test_size,
        "random_state": random_state,
        "max_iter": max_iter,
        "solver": solver,
        "class_weight": class_weight,
        "export_design_matrix": export_design_matrix,
        "artifacts": {
            "model": str(model_path),
            "logs": str(logs_path),
            "metrics": str(metrics_path),
            "feature_importance": str(feature_importance_path),
            "feature_importance_full": str(feature_importance_full_path),
            "train_columns": str(train_columns_path),
            "selected_features": str(selected_features_path),
        },
    }
    logs_path.write_text(json.dumps(logs_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if export_design_matrix:
        X_full_transformed = fitted_preprocessor.transform(X)
        X_design_df = pd.DataFrame(X_full_transformed, columns=feature_names)
        X_design_path = run_dir / "X_design_matrix.csv"
        X_design_df.to_csv(X_design_path, index=False)

    return {
        "run_dir": str(run_dir),
        "model_path": str(model_path),
        "training_mode": training_mode,
        "metrics": metrics,
        "selected_features": selected_features,
    }


def main() -> None:
    result = train_model()
    print("Entrenamiento completado.")
    print(f"Training mode: {result['training_mode']}")
    print(f"Run dir: {result['run_dir']}")
    print(f"Model path: {result['model_path']}")
    print(f"Metrics: {result['metrics']}")
    print(f"Top features: {result['selected_features']}")


if __name__ == "__main__":
    main()
