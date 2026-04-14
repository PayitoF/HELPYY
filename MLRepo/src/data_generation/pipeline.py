import os
import pandas as pd
from . import (
    generate_clients,
    generate_demographics,
    generate_digital_sessions,
    generate_transactions,
    generate_loan_applications,
    generate_payments,
    build_risk_features,
    build_target,
    validate_datasets,
)


def run_data_generation_pipeline(
    n_clients: int = 20000,
    seed: int = 42,
    base_rate: float = 0.15,
    output_dir: str = "data/generated",
    save_csv: bool = True,
) -> dict:
    """Ejecuta el pipeline completo de generación de datos sintéticos.

    Returns
    -------
    dict
        Diccionario con todas las tablas generadas.
    """
    os.makedirs(output_dir, exist_ok=True)

    print("Generando clients...")
    clients = generate_clients(n_clients=n_clients, seed=seed)

    print("Generando demographics...")
    demographics = generate_demographics(clients)

    print("Generando digital_sessions...")
    digital_sessions = generate_digital_sessions(clients, seed=seed)

    print("Generando loan_applications...")
    loan_applications = generate_loan_applications(clients, seed=seed)

    print("Generando transactions...")
    transactions = generate_transactions(clients, seed=seed)

    print("Generando payments...")
    payments = generate_payments(clients, loan_applications, seed=seed)

    print("Construyendo risk_features...")
    risk_features = build_risk_features(
        clients, demographics, digital_sessions, transactions, payments, loan_applications
    )

    print("Construyendo target...")
    target = build_target(risk_features, base_rate=base_rate, seed=seed)

    print("Validando datasets...")
    validation = validate_datasets(
        clients, demographics, digital_sessions, transactions, payments, loan_applications, risk_features
    )

    datasets = {
        "clients": clients,
        "demographics": demographics,
        "digital_sessions": digital_sessions,
        "transactions": transactions,
        "loan_applications": loan_applications,
        "payments": payments,
        "risk_features": risk_features,
        "target": target,
        "validation": validation,
    }

    if save_csv:
        for name, df in datasets.items():
            if name == "validation":
                continue
            path = os.path.join(output_dir, f"{name}.csv")
            df.to_csv(path, index=False)
            print(f"Guardado: {path}")

    print("Pipeline completado exitosamente.")
    return datasets


if __name__ == "__main__":
    # Ejemplo de uso
    datasets = run_data_generation_pipeline(n_clients=5000, save_csv=True)
    print("Ejemplo de risk_features:")
    print(datasets["risk_features"].head())
    print(f"Tasa de default: {datasets['target']['default'].mean():.3f}")