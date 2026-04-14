
# HelpyHand FastAPI endpoint

## Archivos
- `src/api/app.py`
- `src/api/schemas.py`
- `src/api/predictor.py`

## Variables opcionales
Puedes sobreescribir rutas con variables de entorno:

- `MODEL_PATH`
- `MODEL_LOGS_PATH`
- `SELECTED_FEATURES_PATH`

## Ejecutar
```bash
uvicorn src.api.app:app --reload
```

## Endpoints
- `GET /health`
- `GET /model-info`
- `POST /risk-score`

## Ejemplo de request
```json
{
  "declared_income": 1200000,
  "is_banked": 0,
  "employment_type": "informal",
  "age": 32,
  "city_type": "rural",
  "total_sessions": 15,
  "pct_conversion": 0.30,
  "tx_income_pct": 0.60,
  "payments_count": 8,
  "on_time_rate": 0.70,
  "overdue_rate": 0.20,
  "avg_decision_score": 0.55
}
```
