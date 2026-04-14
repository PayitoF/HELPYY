# 🗺️ Próximos Pasos — Helpyy Hand

> Última actualización: 2026-04-14
> Este documento contiene los prompts listos para ejecutar en Kiro, organizados por fase.
> Cada prompt es autocontenido y ejecutable secuencialmente.

---

## 📌 Contexto Importante

### MLRepo Actualizado (2026-04-14)
El equipo ML actualizó su repositorio (`MLRepo/`) con cambios significativos:

- **Modelo entrenado:** Logistic Regression (scikit-learn Pipeline con preprocessing)
- **Modo:** `selected` (12 features de entrada, 5 top features)
- **Métricas:** AUC 0.691, F1 0.766, Precision 0.844, Recall 0.701
- **API real del equipo ML:** FastAPI con endpoints `/health`, `/model-info`, `/risk-score`
- **Contrato real (RiskRequest):**
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
- **Respuesta (RiskResponse):**
  ```json
  {
    "probability_of_default": 0.42,
    "risk_category": "MEDIUM",
    "decision": "REVIEW",
    "top_features": ["on_time_rate", "is_banked", "pct_conversion", "city_type_rural", "overdue_rate"]
  }
  ```
- **Thresholds del modelo real:**
  - `p_default < 0.30` → LOW risk
  - `0.30 ≤ p_default < 0.60` → MEDIUM risk
  - `p_default ≥ 0.60` → HIGH risk
  - `p_default < 0.40` → APPROVE
  - `0.40 ≤ p_default < 0.65` → REVIEW
  - `p_default ≥ 0.65` → REJECT

Esto impacta directamente la Fase 7 y 8 porque ahora tenemos un contrato ML real contra el cual alinear nuestro `ml_client/`.

### Archivos de referencia
- `CLAUDE.md` — Arquitectura objetivo y diseño de agentes
- `ESTADO_ACTUAL.md` — Estado real de implementación
- `README.md` — Documentación general del proyecto
- `MLRepo/src/api/` — API real del equipo ML (schemas, predictor, app)
- `MLRepo/src/config/config.ini` — Configuración del modelo
- `MLRepo/models/logistic_regression/selected/` — Modelo entrenado + artefactos

---

## FASE 7 — INFRAESTRUCTURA AWS

### Prompt 7.0 — Alineación ML Client con API Real del Equipo ML

> **Ejecutar ANTES de la infra AWS.** El equipo ML ya tiene su API real y debemos alinear nuestro adaptador.

```
Lee el repositorio MLRepo/ completo, especialmente:
- MLRepo/src/api/app.py (endpoints reales)
- MLRepo/src/api/schemas.py (RiskRequest y RiskResponse reales)
- MLRepo/src/api/predictor.py (lógica de predicción y thresholds)
- MLRepo/src/config/config.ini (features seleccionadas)
- MLRepo/models/logistic_regression/selected/runs/2026-04-10_163938/ (métricas y artefactos)

Luego lee nuestro adaptador actual:
- backend/ml_client/client.py
- backend/ml_client/schemas.py
- backend/ml_client/mock_server.py
- backend/ml_client/contract.py

Ahora ALINEA nuestro ml_client con el contrato REAL del equipo ML:

1. Actualiza backend/ml_client/schemas.py:
   - RiskRequest debe coincidir EXACTAMENTE con MLRepo/src/api/schemas.py
   - RiskResponse debe coincidir EXACTAMENTE
   - Mantén nuestros modelos internos (CreditPrediction, etc.) como wrappers

2. Actualiza backend/ml_client/client.py:
   - El endpoint real es POST /risk-score (no /api/ml/predict)
   - GET /health y GET /model-info también existen
   - Adapta el MLClient para consumir estos endpoints reales
   - Mantén retry logic y exponential backoff

3. Actualiza backend/ml_client/mock_server.py:
   - Debe replicar EXACTAMENTE los endpoints del equipo ML
   - POST /risk-score con el mismo schema
   - GET /health con model_loaded y model_path
   - GET /model-info con la estructura real
   - Las respuestas mock deben usar los mismos thresholds:
     p_default < 0.30 → LOW, < 0.60 → MEDIUM, >= 0.60 → HIGH
     p_default < 0.40 → APPROVE, < 0.65 → REVIEW, >= 0.65 → REJECT

4. Actualiza backend/ml_client/contract.py:
   - Refleja el contrato OpenAPI real

5. Actualiza los contract tests en tests/contract/test_ml_contract.py:
   - Deben validar contra el schema real del equipo ML

6. Actualiza los agentes que consumen el MLClient:
   - backend/agents/onboarding_agent.py
   - backend/agents/credit_evaluator_agent.py
   - backend/agents/persistent_monitor_agent.py
   - Asegúrate de que mapeen correctamente los nuevos campos

7. Corre make test y asegúrate de que TODOS los tests pasen.

IMPORTANTE:
- Los thresholds del modelo real son DIFERENTES a los que teníamos en el mock
- El endpoint cambió de /api/ml/predict a /risk-score
- Los campos del request cambiaron (ej: declared_income en vez de income)
- Nuestro mock server debe ser un espejo fiel de la API real del equipo ML
```

### Prompt 7.1 — CDK Stacks

```
Implementa la infraestructura como código con AWS CDK en infra/aws/cdk/.

Lee primero:
- CLAUDE.md (sección "CAPA DE DATOS / AWS")
- ESTADO_ACTUAL.md (sección "PENDIENTE / PRÓXIMOS PASOS")
- docker-compose.yml (para entender los servicios actuales)
- .env.example (variables de entorno)

Crea los siguientes stacks:

1. infra/aws/cdk/stacks/compute_stack.py:
   - ECS Fargate para la API FastAPI (backend/api/main.py)
   - ALB con HTTPS (certificado ACM)
   - API Gateway para WebSocket (/api/v1/ws/chat/{session_id})
   - Lambda para el agente monitor (cron via EventBridge, configurable con MONITOR_INTERVAL_HOURS)
   - Auto-scaling: min 1, max 4 tasks, target CPU 70%

2. infra/aws/cdk/stacks/data_stack.py:
   - DynamoDB tablas:
     - Users (PK: user_id, GSI: cedula)
     - Sessions (PK: session_id, TTL: 24h)
     - Notifications (PK: user_id, SK: timestamp)
     - PIIVault (PK: token, TTL: PII_VAULT_TTL_HOURS desde .env)
     - MissionProgress (PK: user_id, SK: mission_id)
   - S3 bucket para modelos ML y artefactos (versionado habilitado)
   - Todas las tablas con billing mode PAY_PER_REQUEST

3. infra/aws/cdk/stacks/ml_stack.py:
   - SageMaker endpoint para el modelo de scoring (Logistic Regression del equipo ML)
   - SageMaker Pipeline para reentrenamiento automático
   - Step Functions para orquestar el pipeline MLOps
   - Nota: el modelo real está en MLRepo/models/logistic_regression/selected/

4. infra/aws/cdk/stacks/security_stack.py:
   - KMS key para cifrado de PII (usado por PIIVault)
   - IAM roles con least-privilege para cada servicio
   - WAF rules en API Gateway (rate limiting, geo-blocking, SQL injection)
   - VPC con subnets privadas para ECS y DynamoDB VPC endpoints
   - Secrets Manager para: JWT_SECRET_KEY, BEDROCK credentials, ML_SERVICE_URL

5. infra/aws/cdk/stacks/monitoring_stack.py:
   - CloudWatch dashboards:
     - API: latencia P50/P99, error rate, requests/min
     - LLM: tokens consumidos, latencia por agente, costo estimado
     - ML: llamadas al servicio, latencia, tasa de aprobación
   - Alarmas:
     - Error rate > 5% → SNS notification
     - Latencia P99 > 3s → SNS notification
     - ML service unhealthy → SNS notification
   - X-Ray tracing habilitado en ECS y Lambda

6. infra/aws/cdk/app.py:
   - Orquesta todos los stacks con dependencias correctas
   - Parámetros de entorno: dev, staging, prod
   - Tags: project=helpyy-hand, environment={env}

Asegúrate de que:
- Todo se pueda desplegar con `cdk deploy --all`
- Exista un cdk.json con la configuración correcta
- Los stacks tengan outputs para URLs, ARNs, y endpoints
- requirements.txt del CDK incluya aws-cdk-lib y constructs
```

---

## FASE 8 — MLOps + LLMOps

### Prompt 8.1 — LLMOps + Observabilidad

```
Implementa la capa de observabilidad y LLMOps.

Lee primero:
- CLAUDE.md (secciones de agentes y LLM Gateway)
- backend/agents/ (todos los agentes)
- backend/llm/ (providers)
- backend/ml_client/client.py (adaptador ML)

1. LLMOps — Gestión de prompts y agentes:

   a) Versionamiento de system prompts:
      - Mueve los system prompts de cada agente a archivos .txt en backend/agents/prompts/
      - Formato: {agent_name}_v{version}.txt (ej: onboarding_v1.txt)
      - Cada agente carga su prompt desde archivo, no hardcoded
      - Variable de entorno por agente para A/B testing:
        ONBOARDING_PROMPT_VERSION=1, CREDIT_EVAL_PROMPT_VERSION=1, etc.

   b) Logging estructurado de interacciones LLM (SIN PII):
      - Crea backend/observability/llm_logger.py
      - Formato JSON por interacción:
        {timestamp, session_id, agent, intent, tokens_in, tokens_out, latency_ms, model, prompt_version}
      - Integra en BaseAgent para que TODOS los agentes logueen automáticamente
      - Los logs van a un archivo rotativo + stdout (para CloudWatch)

   c) Métricas por agente:
      - Crea backend/observability/metrics.py
      - Contadores: requests por agente, handoffs, errores
      - Histogramas: latencia P50/P99, tokens por request
      - Endpoint GET /api/v1/metrics (formato Prometheus-compatible)

   d) Alertas (preparadas para CloudWatch):
      - Si latencia de un agente > 5s en P99 → log WARNING
      - Si tasa de error de un agente > 5% en ventana de 5 min → log CRITICAL
      - Si un agente no responde en 30s → timeout + log ERROR

2. Observabilidad del servicio ML (como CONSUMIDORES):

   a) Health check del ML service:
      - Crea backend/observability/ml_health.py
      - Check cada 30s (configurable via ML_HEALTH_CHECK_INTERVAL)
      - Log de estado: {timestamp, status, latency_ms, model_loaded}
      - Si falla 3 veces consecutivas → log CRITICAL

   b) Log de cada llamada al MLClient:
      - Integra en backend/ml_client/client.py
      - {timestamp, endpoint, latency_ms, status_code, risk_category, decision}
      - NUNCA loguear features con PII (usar tokens)

   c) Métricas de negocio:
      - Tasa de aprobación (APPROVE / total)
      - Distribución de risk_category (LOW/MEDIUM/HIGH)
      - Conversion funnel: onboarding → scoring → aprobado → cuenta creada

3. Contract monitoring en producción:

   a) Crea backend/observability/contract_monitor.py:
      - Ejecuta contract tests contra el servicio ML real cada hora
      - Si un test falla → log CRITICAL + alerta
      - Dashboard de compatibilidad: último check, status, cambios detectados
      - Endpoint GET /api/v1/contract-status

4. Costo tracking:

   a) Crea backend/observability/cost_tracker.py:
      - Estima costo por conversación:
        - Tokens LLM (input + output) × precio por token del modelo
        - Llamadas ML × costo por invocación
        - Storage (DynamoDB reads/writes)
      - Acumula por sesión y por día
      - Endpoint GET /api/v1/cost-report (últimos 7 días)
      - Log WARNING si costo diario > umbral configurable (DAILY_COST_ALERT_USD)

Corre make test después de cada módulo. Todos los tests existentes deben seguir pasando.
```

### Prompt 8.2 — Recomendaciones para el Equipo ML

```
Genera un documento docs/ML_TEAM_RECOMMENDATIONS.md completo y ejecutable.

Lee primero:
- MLRepo/ completo (especialmente src/api/, src/training/, src/config/)
- backend/ml_client/ (nuestro adaptador y contract tests)
- MLRepo/models/logistic_regression/selected/runs/2026-04-10_163938/ (métricas actuales)

El documento debe contener:

1. CONTRATO DE API COMPLETO
   - Copia legible del contrato que nuestro sistema espera
   - Endpoints: POST /risk-score, GET /health, GET /model-info
   - Schemas exactos de request y response (con ejemplos)
   - Códigos de error esperados (400, 422, 500)
   - Headers requeridos (Content-Type, X-Request-ID para tracing)
   - Rate limits recomendados

2. CONTRACT TESTS
   - Instrucciones para que el equipo ML ejecute nuestros contract tests contra su servicio
   - Comando exacto: pytest tests/contract/test_ml_contract.py -v --ml-url=http://su-servicio:puerto
   - Qué valida cada test y qué hacer si falla
   - Cómo agregar el contract test a su CI/CD

3. RECOMENDACIONES DE MLOps PARA SU PIPELINE
   - Cómo exponer el modelo como FastAPI service (ya lo tienen, validar buenas prácticas)
   - Versionamiento de modelos: convención de nombres, cómo manejar rollback
   - Champion/Challenger en SageMaker: cómo hacer A/B testing de modelos
   - Monitoreo de drift: cómo detectar cuando el modelo se degrada
     - Data drift: distribución de features cambia vs. entrenamiento
     - Concept drift: relación features→target cambia
     - Métricas a monitorear: PSI (Population Stability Index), KS test
   - Reentrenamiento automático: trigger por drift o por calendario
   - Métricas actuales del modelo y benchmarks mínimos:
     - AUC actual: 0.691 (benchmark mínimo: 0.65)
     - F1 actual: 0.766
     - Precision actual: 0.844
     - Recall actual: 0.701

4. GUÍA DE INTEGRACIÓN
   - Diagrama de flujo completo:
     dato del usuario → PII Tokenizer → Agente → MLClient → su API → predicción → respuesta
   - Variables de entorno que deben configurar:
     MODEL_PATH, MODEL_LOGS_PATH, SELECTED_FEATURES_PATH
   - Cómo ejecutar los contract tests contra su servicio
   - Cómo conectar su servicio con nuestro sistema de agentes
   - Formato de logs que esperamos para correlación (X-Request-ID)

5. DIAGRAMA DE DESPLIEGUE
   - Cómo se conectan los servicios en AWS:
     ECS (nuestra API) → SageMaker Endpoint (su modelo) o ECS (su FastAPI)
   - VPC peering / service discovery
   - Secrets compartidos (Secrets Manager)

El documento debe ser claro, completo, y ejecutable sin explicación verbal.
Es el "handoff" oficial al equipo ML.
```

---

## 📌 Notas de Ejecución

### Orden de ejecución
```
7.0 → 7.1 → 8.1 → 8.2
```

El prompt 7.0 es CRÍTICO ejecutarlo primero porque alinea nuestro adaptador ML con la API real del equipo ML. Sin esto, los tests de contrato fallarán y la integración no funcionará.

### Antes de cada prompt
```bash
make test    # Verificar que todo pasa antes de empezar
```

### Después de cada prompt
```bash
make test    # Verificar que nada se rompió
make lint    # Verificar estilo de código
```

### Git workflow
```bash
# Después de cada fase completada y verificada:
git add -A
git commit -m "feat(fase-X.Y): descripción breve"

# NUNCA commitear:
# - .env (secrets)
# - modelos binarios grandes (usar .gitignore)
# - datos con PII
```

### Prioridades si hay problemas
1. **PII** → NUNCA comprometer seguridad por velocidad
2. **ML Client alineado** → Sin esto, los agentes no funcionan con el modelo real
3. **LLM Gateway** → Si no funciona local, nada más funciona
4. **Orquestador** → Es el cerebro, debe ser robusto
5. **Observabilidad** → Necesaria para producción pero no bloquea desarrollo
6. **AWS Infra** → Se implementa al final, cuando todo funcione local

### Variables de entorno clave
```bash
# .env
LLM_PROVIDER=local
OLLAMA_MODEL=gemma4:e4b
OLLAMA_URL=http://localhost:11434
BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-20250514-v1:0
AWS_REGION=us-east-1
ML_SERVICE_URL=http://localhost:8001
MONITOR_INTERVAL_HOURS=6
PII_VAULT_TTL_HOURS=24
DATABASE_TYPE=sqlite
LOG_LEVEL=DEBUG
```
