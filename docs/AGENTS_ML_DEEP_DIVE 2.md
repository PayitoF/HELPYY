# Arquitectura de Agentes y ML — Helpyy Hand
> Documento de referencia técnica para desarrollo y mejoras

---

## 1. Flujo General de una Conversación

```
Usuario → POST /api/v1/chat
  → PII Tokenizer Middleware (cédula, nombre, teléfono → tokens)
  → Orchestrator.handle_message()
    → classify_intent() [LLM ligero, caché TTL 5min]
    → route() → selecciona agente
    → agent.process(tokenized_msg, context, original_msg)
    → AgentResponse
  → PII Detokenizer Middleware
  → SSE stream al frontend
```

---

## 2. BaseAgent — Clase Abstracta

Todos los agentes heredan de `BaseAgent`. Provee:

- `process(message, context, original_message)` → `AgentResponse`
- `process_stream()` → `AsyncIterator[str]`
- `_build_messages()` → system prompt + últimos 10 turnos (solo user/assistant)
- `_run_with_tools()` → loop LLM ↔ herramientas (máx 5 iteraciones)
- `_make_response()` → envuelve texto en `AgentResponse`

**Patrón de prompt:** Los agentes NO insertan mensajes `system` en medio del historial (confunde modelos pequeños). En cambio, concatenan la instrucción de estado al system prompt inicial.

**AgentResponse:**
```python
content: str          # texto para el usuario
agent_name: str       # nombre del agente
agent_type: str       # "general" | "onboarding" | "evaluator" | "advisor"
suggested_actions: [] # quick replies para el frontend
handoff_to: str|None  # nombre del agente destino si hay transferencia
metadata: {}          # datos estructurados (account_id, plan, etc.)
```

---

## 3. Orchestrator

**Responsabilidades:**
- Mantiene `_SessionStore` (historial en memoria, máx 20 turnos)
- Mantiene `_IntentCache` (TTL 5min, máx 200 entradas)
- Clasifica intent con LLM (temperatura 0.0, prompt ligero)
- Rutea al agente correcto
- Gestiona handoffs entre agentes

**Regla de routing:**
1. Si `is_banked == False` → siempre `OnboardingAgent`
2. Clasificar intent → mapear a agente
3. Si agente no registrado → `HelpyyGeneralAgent`

**Intents:**
| Intent | Agente |
|--------|--------|
| `credit_inquiry` | CreditEvaluatorAgent |
| `financial_advice` | FinancialAdvisorAgent |
| `bank_faq` | HelpyyGeneralAgent |
| `onboarding` | OnboardingAgent |
| `greeting` | HelpyyGeneralAgent |

**Handoff:** El agente destino recibe un mensaje de transición en el historial explicando el contexto. El `handoff_count` se incrementa en el contexto.

**⚠️ Problema actual:** `handle_message_stream()` llama a `agent.process()` (no streaming real) y luego simula el stream dividiendo el texto por espacios. No es streaming token a token real.

---

## 4. OnboardingAgent

**Propósito:** Guiar a no-clientes a través del proceso de bancarización.

**Estado actual del código:** El método `process()` principal está simplificado — solo responde preguntas generales y dirige al formulario del widget. La máquina de estados completa (GREETING → COLLECTING → CONFIRMING → EVALUATING → DONE) existe en el código pero **no se usa en el flujo principal**.

**Flujo real (widget):**
```
Widget HTML form → POST /api/v1/onboarding/create-account
  → OnboardingAgent._tool_create_account()
  → OnboardingAgent._tool_check_credit()
  → OnboardingAgent._tool_enable_helpyy()
```

**Extracción de datos (regex):**
- Nombre: después de "me llamo", "soy", "mi nombre es"
- Cédula: 8-10 dígitos standalone
- Ingreso: número + contexto ("millones", "mil", "gano", etc.)

**Herramientas:**
- `check_credit_score` → llama ML o mock
- `create_account` → genera `ACC-XXXXXXXX`
- `enable_helpyy_hand` → activa gamificación

**⚠️ Problemas identificados:**
1. La máquina de estados está implementada pero `process()` la bypasea completamente
2. `_tool_check_credit()` usa valores hardcodeados para campos que no recopila (age=30, city_type="urban", etc.)
3. No hay persistencia real — `create_account` solo genera un UUID en memoria

---

## 5. CreditEvaluatorAgent

**Propósito:** Consultar ML, presentar opciones de crédito o rechazar empáticamente.

**Flujo:**
1. Busca `prediction_result` en contexto (puede venir del onboarding)
2. Si no existe, llama `_get_prediction(context)`
3. Si `eligible=True` → `_handle_approved()` con tabla de 3 plazos
4. Si `eligible=False` → `_handle_rejected()` + handoff a `financial_advisor`

**Simulación de préstamo:**
```
monthly_payment = P * r * (1+r)^n / ((1+r)^n - 1)
r = 0.025 (2.5% mensual = ~34.5% TEA)
Plazos: 6, 12, 18 meses
```

**Monto máximo:**
- p_default < 0.20: multiplicador 1.5-3.0x ingreso, cap $2M
- p_default 0.20-0.49: multiplicador 0.5-1.5x ingreso, cap $500K

**⚠️ Problemas identificados:**
1. `_get_prediction()` usa `context.get("user_data", {})` pero este dict raramente está poblado correctamente desde el onboarding
2. El mock fallback usa `context.get("prediction_eligible", income >= 1_200_000)` — si no hay income en contexto, siempre rechaza
3. No hay validación de que el usuario tenga cuenta antes de evaluar crédito

---

## 6. FinancialAdvisorAgent

**Propósito:** Crear planes de mejora gamificados basados en factores ML.

**Detección de intent (keywords):**
- `create_plan`: "plan", "misiones", "quiero mejorar"
- `check_progress`: "progreso", "mis puntos", "mi nivel"
- `complete_mission`: "completé", "terminé", "logré"
- Default: `general_advice`

**Sistema de gamificación:**
```
Niveles: Principiante(0) → Aprendiz(50) → Disciplinado(150) → Experto(300) → Maestro(500)
```

**Catálogo de misiones (8 templates):**
| Misión | Factor ML | Puntos | Dificultad |
|--------|-----------|--------|------------|
| Depósito Constante | on_time_rate | 15 | easy |
| Ingreso Registrado | on_time_rate | 25 | medium |
| Pago Puntual | on_time_rate | 30 | medium |
| Cero Atrasos | overdue_rate | 35 | hard |
| Explorador Digital | pct_conversion | 10 | easy |
| Pago Digital | pct_conversion | 15 | easy |
| Colchón de Seguridad | is_banked | 25 | medium |
| Hábito de Ahorro | is_banked | 40 | hard |

**Tips por ocupación:** vendedor_ambulante, trabajador_domestico, independiente, default

**⚠️ Problemas identificados:**
1. `_get_factors_from_context()` depende de que `rejection_factors` o `improvement_factors` estén en el contexto — si el handoff no los pasa, el plan es genérico
2. Las misiones no tienen verificación real — `complete_mission` completa la primera misión pendiente sin validar nada
3. El plan se guarda en `context["plan"]` (en memoria) — se pierde si la sesión expira

---

## 7. PersistentMonitorAgent

**Propósito:** Servicio background que revisa scores y genera notificaciones.

**No es un BaseAgent** — no procesa mensajes de usuario. Es un servicio.

**Ciclo de monitoreo:**
1. `get_pending_users()` → usuarios con `score_status == "pendiente_mejora"`
2. Para cada usuario: `_get_prediction()` → ML
3. Comparar `new_p_default` vs `last_p_default`
4. Clasificar cambio: `score_improved | score_same | score_decreased`
5. Generar `Notification` y guardar en `NotificationStore`
6. Generar `mission_reminder` para misiones activas

**Umbrales:**
- Mejora: delta <= -0.02 (p_default bajó 2pp)
- Deterioro: delta >= +0.02 (p_default subió 2pp)

**Infraestructura:**
- Local: APScheduler (AsyncIOScheduler), intervalo configurable
- Producción: EventBridge cron → Lambda → POST /api/v1/monitor/run

**⚠️ Problemas identificados:**
1. `InMemoryUserStore` — los usuarios se pierden al reiniciar
2. Las notificaciones no llegan al frontend en tiempo real (no hay push)
3. `_get_prediction()` usa valores hardcodeados (age=30, on_time_rate=0.5) en vez de datos reales del usuario

---

## 8. HelpyyGeneralAgent

**Propósito:** FAQ, productos BBVA, operaciones, saludos. Agente por defecto.

**Flujo:**
1. Detectar handoff por keywords → si detecta, retorna mensaje de transición sin LLM
2. Buscar en FAQ KB (TF-IDF) → si confianza >= 0.25, responder directo sin LLM
3. Si confianza 0.15-0.25, inyectar FAQ como hint en system prompt
4. Fallback: LLM con system prompt

**FAQ KB:**
- Archivo: `backend/data/faq_bbva.json`
- Scoring: TF-IDF cosine + keyword boost (max 0.45)
- Stopwords en español incluidas

**Handoff keywords:**
- → CreditEvaluator: "crédito", "préstamo", "califico", "cupo"
- → FinancialAdvisor: "mejorar", "puntaje", "misiones", "plan financiero"
- → Onboarding: "abrir cuenta", "no soy cliente", "nueva cuenta"

---

## 9. ML Client y Contrato

### RiskRequest (input al ML)
```python
declared_income: float    # ingreso mensual COP
is_banked: int            # 0 o 1
employment_type: str      # "formal" | "independent" | "informal"
age: int                  # 18-100
city_type: str            # "urban" | "rural"
total_sessions: int       # sesiones digitales
pct_conversion: float     # % sesiones con transacción
tx_income_pct: float      # transacciones / ingreso
payments_count: int       # número de pagos
on_time_rate: float       # % pagos a tiempo (0-1)
overdue_rate: float       # % pagos en mora (0-1)
avg_decision_score: float # score promedio de decisiones
```

### RiskResponse (output del ML)
```python
probability_of_default: float  # p_default (0-1)
risk_category: str             # "LOW" | "MEDIUM" | "HIGH"
decision: str                  # "APPROVE" | "REVIEW" | "REJECT"
top_features: list[str]        # features más importantes
```

### Lógica de elegibilidad (en MLClient, no en el modelo)
- `APPROVE` → eligible=True
- `REVIEW` o `REJECT` → eligible=False

### Bandas de riesgo
| p_default | Banda | Decisión |
|-----------|-------|----------|
| < 0.20 | low_risk | APPROVE |
| 0.20-0.49 | medium_risk | REVIEW |
| ≥ 0.50 | high_risk | REJECT |

### Factores de mejora (calculados en cliente, no en modelo)
El `MLClient.get_improvement_factors()` calcula client-side qué variables mejorar:
- on_time_rate: target 0.90
- overdue_rate: target 0.05
- pct_conversion: target 0.60
- is_banked: target 1.0

---

## 10. Problemas Críticos a Resolver

### P1 — Datos del usuario no fluyen entre agentes
El `context["user_data"]` raramente está poblado. Cuando el CreditEvaluator llama al ML, usa defaults (income=1M, age=30, etc.) en vez de los datos reales del usuario recopilados en onboarding.

**Fix:** El OnboardingAgent debe guardar los datos en `context["user_data"]` al completar el onboarding.

### P2 — OnboardingAgent bypasea la máquina de estados
El `process()` principal ignora la máquina de estados. El flujo conversacional de recopilación de datos no funciona.

**Fix:** Decidir si el flujo es 100% por formulario (widget) o 100% conversacional, y eliminar el código muerto.

### P3 — Streaming falso
`handle_message_stream()` divide el texto por espacios, no hace streaming real token a token.

**Fix:** Usar `agent.process_stream()` real en el orchestrator.

### P4 — Persistencia en memoria
Sesiones, notificaciones, planes de misiones — todo en memoria. Se pierde al reiniciar.

**Fix (POC):** Ya tenemos DynamoDB en AWS. Implementar adaptadores.

### P5 — Monitor usa datos hardcodeados
`_get_prediction()` en el monitor usa age=30, on_time_rate=0.5 para todos los usuarios.

**Fix:** Guardar los datos reales del usuario en `UserRecord` durante el onboarding.

---

## 11. Contexto de Sesión — Estructura

```python
context = {
    "history": [                    # últimos 20 turnos
        {"role": "user", "content": "...", "agent": "onboarding"},
        {"role": "assistant", "content": "...", "agent": "onboarding"},
    ],
    "current_agent": "onboarding",
    "handoff_count": 0,
    
    # Onboarding
    "onboarding_state": "collecting_data",
    "onboarding_data": {"name": "...", "cedula": "...", "income": 1500000},
    "account_id": "ACC-XXXXXXXX",
    "helpyy_enabled": True,
    "credit_eligible": True,
    
    # Credit
    "prediction_result": {
        "eligible": True,
        "p_default": 0.15,
        "max_amount": 2000000,
        "score_band": "low_risk",
        "factors": [...],
    },
    
    # Advisor
    "plan": [...],                  # lista de misiones
    "total_points": 0,
    "rejection_factors": [...],     # factores a mejorar
    "improvement_factors": [...],   # con sugerencias
    
    # User data (para ML)
    "user_data": {
        "income": 1500000,
        "occupation": "independiente",
        "is_banked": True,
        "age": 35,
        "city_type": "urban",
    },
}
```
