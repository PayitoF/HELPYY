# ML Client — Análisis del MLRepo y Contrato de API

## Overview

This module provides a clean interface for the agent platform to consume
the ML scoring service maintained by the Data/ML team.

## Hallazgo Crítico

**El MLRepo NO contiene un modelo ML entrenado.** No existen archivos `.pkl`, `.joblib`,
`.h5` ni código de entrenamiento con sklearn/xgboost/lightgbm. El "modelo" es un
**Risk Generating Process (RGP)** basado enteramente en fórmulas matemáticas heurísticas
(combinaciones lineales ponderadas + sigmoide logístico).

Esto significa que:
1. El mock server puede replicar la lógica **exacta** del MLRepo
2. No hay model artifacts que deserializar
3. Los pesos/coeficientes son constantes hardcodeadas, no aprendidos

## Architecture

- `schemas.py` — Pydantic models defining the API contract (source of truth)
- `contract.py` — Constants: weights, coefficients, ranges, endpoints, score bands
- `client.py` — Async HTTP client adapter (same interface for mock and real)
- `mock_server.py` — FastAPI mock that simulates the real ML service

## Usage

```python
from backend.ml_client.client import MLClient
from backend.ml_client.schemas import PredictRequest, EmploymentType, CityType, EducationLevel

client = MLClient()  # reads ML_SERVICE_URL from env
prediction = await client.predict(PredictRequest(
    declared_income=1_500_000,
    employment_type=EmploymentType.informal,
    is_banked=False,
    age=32,
    city_type=CityType.urban,
    education_level=EducationLevel.secondary,
    household_size=3,
))

print(prediction.p_default)       # 0.0 - 1.0
print(prediction.score_band)      # low_risk | medium_risk | high_risk
print(prediction.eligible)        # True/False
print(prediction.max_amount)      # Max COP amount
print(prediction.factors)         # Contributing risk factors
```

## MLRepo Architecture

```
MLRepo/
├── src/data_generation/
│   ├── clients_generator.py        → Genera clientes + base_risk_score
│   ├── demographics_generator.py   → Extrae tabla demographics de clients
│   ├── digital_sessions_generator.py → Sesiones digitales condicionadas por riesgo
│   ├── transactions_generator.py   → Transacciones condicionadas por riesgo
│   ├── loan_applications_generator.py → Aplicaciones de crédito
│   ├── payments_generator.py       → Pagos por cuota, mora condicionada por riesgo
│   ├── risk_feature_builder.py     → Agrega todas las tablas → risk_index
│   ├── target_builder.py           → risk_index → p_default (sigmoid)
│   ├── validation.py               → Validaciones de integridad referencial
│   └── pipeline.py                 → Orquesta todo el pipeline
├── notebooks/
│   └── 01_data_model_and_synthetic_design.ipynb
├── descriptives/
│   └── app.py                      → Streamlit dashboard
├── data/generated/                  → CSVs generados (8 tablas)
└── requirements.txt                 → numpy, pandas, matplotlib, seaborn, plotly, streamlit
```

## Risk Generating Process (RGP) — 3 Etapas

### Etapa 1: `base_risk_score` (clients_generator.py)

Score demográfico base calculado como combinación lineal:

```
base_risk_score = 1.1*f_income + 1.0*f_emp + 0.8*f_banked + 0.7*f_age + 0.4*f_city + 0.5*f_edu
```

| Factor | Cálculo | Peso |
|--------|---------|------|
| f_income | (max_log - log_income) / max_log | 1.1 |
| f_employment | informal=1.0, independent=0.65, formal=0.0 | 1.0 |
| f_banked | no=0.8, yes=0.0 | 0.8 |
| f_age | <22=0.7, >60=0.5, else=0.0 | 0.7 |
| f_education | none=0.6, primary=0.4, secondary=0.2, else=0.0 | 0.5 |
| f_city | rural=0.3, urban=0.0 | 0.4 |

Normalizado a [0, 1].

### Etapa 2: `risk_index` (risk_feature_builder.py)

Índice compuesto que combina demographic score + behavioral features:

```
risk_index = 0.6*(1-on_time_rate) + 0.4*overdue_rate + 0.3*rejection_rate
           + 0.25*base_risk_score + 0.2*(1/(1+income)) + 0.2*(1-pct_conversion)
           + 0.2*(1-is_banked)
```

Normalizado a [0, 1].

### Etapa 3: `p_default` (target_builder.py)

Probabilidad de default via sigmoide logístico:

```
intercept = -log(1/base_rate - 1)    # base_rate default = 0.15
logits = intercept + 4.0*risk_index + 2.0*(1-on_time_rate)
       + 1.5*overdue_rate + 1.8*rejection_rate - 0.8*pct_conversion
p_default = 1 / (1 + exp(-logits))
```

## Feature Importances (Combined)

| Feature | Peso risk_index | Coef p_default | Impacto | Tipo |
|---------|----------------|----------------|---------|------|
| on_time_rate | 0.60 | 2.0 | **MUY ALTO** | behavioral |
| rejection_rate | 0.30 | 1.8 | **ALTO** | behavioral |
| overdue_rate | 0.40 | 1.5 | **ALTO** | behavioral |
| pct_conversion | 0.20 | -0.8 | **MEDIO** (protector) | behavioral |
| base_risk_score | 0.25 | — (via risk_index) | **MEDIO** | demographic |
| declared_income | 0.20 | — (via risk_index) | **BAJO** | demographic |
| is_banked | 0.20 | — (via risk_index) | **BAJO** | demographic |

## API Contract — 4 Endpoints

### `POST /api/ml/predict`

Scoring de elegibilidad crediticia.

**Request (`PredictRequest`):**
- Demográficos (requeridos): `declared_income`, `employment_type`, `is_banked`, `age`,
  `city_type`, `education_level`, `household_size`
- Comportamentales (opcionales): `on_time_rate`, `overdue_rate`, `rejection_rate`,
  `pct_conversion`, `total_sessions`, `tx_count`, `apps_count`

**Response (`CreditPrediction`):**
- `eligible`: bool
- `p_default`: float [0-1]
- `risk_index`: float [0-1]
- `score_band`: low_risk (<0.20) | medium_risk (<0.50) | high_risk (>=0.50)
- `max_amount`: float COP (if eligible)
- `recommended_product`: nano | micro | reload
- `confidence`: float [0-1]
- `factors`: list of RiskFactor

### `GET /api/ml/score-history/{client_id}`

Historical scores. Response: `list[ScoreEntry]`

### `GET /api/ml/features-spec`

Feature specification. Response: `list[FeatureSpec]`

### `GET /api/ml/model-info`

Model metadata. Response: `ModelInfo`

## Data Ranges

| Feature | Min | Max | Unit |
|---------|-----|-----|------|
| declared_income | 300,000 | 15,000,000 | COP |
| age | 18 | 74 | years |
| household_size | 1 | 7 | people |
| on_time_rate | 0.0 | 1.0 | ratio |
| overdue_rate | 0.0 | 1.0 | ratio |
| rejection_rate | 0.0 | 1.0 | ratio |
| pct_conversion | 0.0 | 1.0 | ratio |

## Credit Products

| Product | Min Amount | Max Amount | Proportion |
|---------|-----------|-----------|------------|
| nano | 100,000 COP | 500,000 COP | 55% |
| micro | 500,000 COP | 2,000,000 COP | 35% |
| reload | 50,000 COP | 1,000,000 COP | 10% |

## Population Distributions (from generator)

- Employment: informal 55%, formal 30%, independent 15%
- City: urban 75%, rural 25%
- Education: none 5%, primary 25%, secondary 35%, technical 20%, university 15%
- Sex: M 52%, F 48%
- Residence: owned 35%, rented 45%, family 15%, other 5%
