# 🤖 CLAUDE.md — Helpyy Hand: Multi-Agent Microcréditos BBVA

> **Este archivo es tu `CLAUDE.md`.** Ponlo en la raíz de tu repositorio.
> Claude Code lo lee automáticamente al iniciar y lo usa como contexto global.

> ⚠️ **LEE TAMBIÉN `ESTADO_ACTUAL.md`** antes de tocar cualquier archivo de frontend.
> Ese documento detalla todos los cambios de implementación real: flujos de auth, componentes,
> decisiones de diseño, CameraCapture, AgentContext, y qué está pendiente.
> Este CLAUDE.md describe la arquitectura objetivo; ESTADO_ACTUAL.md describe lo que ya existe.

---

## 🎯 VISIÓN DEL PROYECTO

**Helpyy Hand** es una plataforma multi-agente de inclusión financiera para BBVA Colombia. Su propósito es bancarizar a personas del sector informal mediante micropréstamos, usando modelos de Machine Learning para scoring crediticio y agentes LLM orquestados para acompañar al usuario en todo su journey financiero.

### Contexto de Negocio
- **Problema:** Millones de colombianos informales no tienen acceso a crédito ni productos bancarios.
- **Solución:** Un sistema multi-agente que: (1) capta al no-cliente desde la web pública de BBVA, (2) lo bancariza guiándolo conversacionalmente, (3) evalúa su elegibilidad para microcrédito con ML, y (4) lo acompaña con asesoría financiera personalizada post-bancarización.
- **Diferenciador:** Gamificación del microcrédito — si no calificas hoy, el sistema te da un plan de acción personalizado y te monitorea proactivamente hasta que califiques.

---

## 🏗️ ARQUITECTURA DE ALTO NIVEL

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CAPA DE PRESENTACIÓN                        │
│                                                                     │
│   ┌──────────────────┐    ┌──────────────────────────────────────┐  │
│   │  BBVA Web Pública │    │  App Bancaria (Mockup Mobile)       │  │
│   │  (Popup Onboard)  │    │  - Helpyy Hand integrado en nav     │  │
│   │  - Widget flotante │    │  - Notificaciones push del agente   │  │
│   │  - Chat onboarding │    │  - Panel de agentes post-login      │  │
│   └────────┬─────────┘    └──────────────┬───────────────────────┘  │
│            │                              │                          │
└────────────┼──────────────────────────────┼──────────────────────────┘
             │          WebSocket / REST     │
             ▼                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     CAPA DE ORQUESTACIÓN                            │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              🧠 ORCHESTRATOR (Router Principal)              │   │
│   │   - Clasifica intent del usuario                            │   │
│   │   - Enruta al agente correcto                               │   │
│   │   - Gestiona contexto compartido (sin PII en memoria LLM)  │   │
│   │   - Maneja handoffs entre agentes                           │   │
│   └──────┬──────────┬──────────────┬──────────────┬─────────────┘   │
│          │          │              │              │                  │
│          ▼          ▼              ▼              ▼                  │
│   ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌───────────────┐     │
│   │ AGENTE 1 │ │ AGENTE 2 │ │  AGENTE 3    │ │   AGENTE 4    │     │
│   │ Onboard  │ │ Evaluador│ │  Insistente  │ │  Asesor Fin.  │     │
│   │ (Web)    │ │ Crédito  │ │  (Monitor)   │ │  Personal     │     │
│   │          │ │          │ │              │ │               │     │
│   │ Guía la  │ │ Consulta │ │ Cron: revisa │ │ Tips, planes  │     │
│   │ bancari- │ │ modelo ML│ │ score cada N │ │ gamificación  │     │
│   │ zación   │ │ responde │ │ horas, noti- │ │ de mejora de  │     │
│   │ recopila │ │ aprobado │ │ fica cambios │ │ score         │     │
│   │ datos    │ │ /rechaz. │ │ al cliente   │ │               │     │
│   └──────────┘ └────┬─────┘ └──────┬───────┘ └───────────────┘     │
│                     │              │                                 │
│   ┌─────────────────┴──────────────┴────────────────────────────┐   │
│   │             AGENTE 5: Helpyy Hand (Asistente General)       │   │
│   │   FAQ banco, productos, consultas operativas                │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
             │                              │
             ▼                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CAPA DE SERVICIOS                              │
│                                                                     │
│   ┌───────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│   │ ML Client     │  │ PII Vault    │  │ LLM Gateway            │  │
│   │ (Adaptador)   │  │ (Tokenizer)  │  │                        │  │
│   │               │  │              │  │ if ENV=local:           │  │
│   │ Consume API   │  │ - Tokeniza   │  │   → Gemma 3 (Ollama)   │  │
│   │ del repo ML   │  │   cédula,    │  │ if ENV=staging|prod:   │  │
│   │ externo del   │  │   nombre     │  │   → Bedrock (Claude/   │  │
│   │ equipo. No    │  │ - Des-token  │  │     Nova/Titan)        │  │
│   │ reimplementa  │  │   solo en    │  │                        │  │
│   │ el modelo.    │  │   servicio   │  │ Interface unificada    │  │
│   │               │  │   backend    │  │ LLMProvider ABC       │  │
│   └───────┬───────┘  └──────────────┘  └────────────────────────┘  │
│           │                                                         │
│           ▼                                                         │
│   ┌───────────────────────────────────────────────────────────────┐ │
│   │ 📦 REPO ML EXTERNO (mantenido por el equipo de Data/ML)      │ │
│   │                                                               │ │
│   │ Claude Code DEBE leer este repo ANTES de implementar el      │ │
│   │ adaptador. Debe analizar:                                    │ │
│   │  1. Qué modelo usa (XGBoost, LGBM, NN, etc.)               │ │
│   │  2. Qué features recibe (nombres, tipos, rangos)            │ │
│   │  3. Qué retorna (formato de predicción, scores, factores)   │ │
│   │  4. Cómo se entrena y se serializa                          │ │
│   │  5. Qué endpoints propone o ya tiene                        │ │
│   │                                                               │ │
│   │ Con esa info, Claude Code SUGIERE al equipo ML:              │ │
│   │  - Contrato de API (OpenAPI spec) para el servicio ML       │ │
│   │  - Endpoints necesarios: /predict, /score, /features        │ │
│   │  - Formato de request/response que necesitan los agentes    │ │
│   │  - Tests de contrato para validar la integración            │ │
│   │                                                               │ │
│   │ Y luego construye el ADAPTADOR (ml_client/) que consume     │ │
│   │ esa API, con un mock server para desarrollo local.           │ │
│   └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CAPA DE DATOS / AWS                               │
│                                                                     │
│   ┌──────────┐ ┌────────────┐ ┌───────────┐ ┌───────────────────┐  │
│   │ DynamoDB │ │ S3 Bucket  │ │ SageMaker │ │ CloudWatch/       │  │
│   │ Clientes │ │ ML Models  │ │ Endpoints │ │ EventBridge       │  │
│   │ Sessions │ │ Artifacts  │ │ (prod)    │ │ (cron agente      │  │
│   │ Scores   │ │ Datasets   │ │           │ │  insistente)      │  │
│   └──────────┘ └────────────┘ └───────────┘ └───────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📁 ESTRUCTURA DEL REPOSITORIO

```
helpyy-hand/
├── CLAUDE.md                          # ← ESTE ARCHIVO
├── .env.example                       # Variables de entorno (nunca .env al repo)
├── docker-compose.yml                 # Orquestación local completa
├── Makefile                           # Comandos rápidos: make dev, make test, make deploy
│
├── frontend/
│   ├── web-widget/                    # Popup para BBVA web pública (vanilla JS, inyectable)
│   │   ├── index.html                 # Widget embeddable
│   │   ├── helpyy-widget.js           # Lógica del chat de onboarding
│   │   └── helpyy-widget.css          # Estilos encapsulados (shadow DOM o scoped)
│   │
│   ├── app-mockup/                    # Mockup mobile app BBVA (React/Next.js)
│   │   ├── src/
│   │   │   ├── components/
│   │   │   │   ├── BankDashboard.jsx  # Vista principal post-login
│   │   │   │   ├── HelpyyPanel.jsx    # Panel de chat multi-agente
│   │   │   │   ├── AgentBadge.jsx     # Badge visual por tipo de agente
│   │   │   │   ├── NotificationBell.jsx  # Notificaciones del agente insistente
│   │   │   │   └── OnboardingFlow.jsx # Flujo de activación de Helpyy Hand
│   │   │   ├── hooks/
│   │   │   │   ├── useChat.js         # Hook para WebSocket/streaming del chat
│   │   │   │   └── useAgentState.js   # Estado del agente activo
│   │   │   ├── contexts/
│   │   │   │   └── AgentContext.jsx    # Provider de estado de agentes
│   │   │   └── App.jsx
│   │   └── package.json
│   │
│   └── shared/                        # Componentes compartidos web+app
│       ├── chat-renderer.js           # Renderizado de mensajes con markdown
│       └── agent-themes.js            # Colores/iconos por agente
│
├── backend/
│   ├── api/
│   │   ├── main.py                    # FastAPI app principal
│   │   ├── routers/
│   │   │   ├── chat.py                # POST /chat + WebSocket /ws/chat
│   │   │   ├── onboarding.py          # POST /onboard (flujo bancarización)
│   │   │   ├── scoring.py             # POST /score (consulta ML)
│   │   │   └── notifications.py       # GET /notifications/{user_id}
│   │   ├── middleware/
│   │   │   ├── pii_filter.py          # Middleware: tokeniza PII antes de pasar al LLM
│   │   │   ├── rate_limiter.py        # Rate limiting por usuario
│   │   │   └── auth.py                # JWT validation
│   │   └── dependencies.py            # Inyección de dependencias FastAPI
│   │
│   ├── agents/
│   │   ├── orchestrator.py            # Router principal — clasifica intent, despacha
│   │   ├── base_agent.py              # Clase abstracta BaseAgent
│   │   ├── onboarding_agent.py        # Agente 1: Guía bancarización
│   │   ├── credit_evaluator_agent.py  # Agente 2: Consulta ML, responde
│   │   ├── persistent_monitor_agent.py # Agente 3: Cron, revisa score, notifica
│   │   ├── financial_advisor_agent.py # Agente 4: Tips, gamificación, planes
│   │   └── helpyy_general_agent.py    # Agente 5: FAQ, productos BBVA
│   │
│   ├── llm/
│   │   ├── provider.py                # ABC: LLMProvider con interface unificada
│   │   ├── bedrock_provider.py        # Implementación AWS Bedrock
│   │   ├── ollama_provider.py         # Implementación Ollama (Gemma 3 local)
│   │   └── config.py                  # LLM_PROVIDER=local|bedrock (una variable)
│   │
│   ├── ml_client/
│   │   ├── client.py                  # Adaptador: consume la API del repo ML externo
│   │   ├── schemas.py                 # Pydantic models del contrato API ML (inferidos del repo)
│   │   ├── mock_server.py             # Mock FastAPI del servicio ML para dev local
│   │   ├── contract.py                # Contrato OpenAPI generado tras análisis del repo ML
│   │   └── README.md                  # Documenta: qué se infirió del repo, qué endpoints espera
│   │
│   │   # ⚠️ IMPORTANTE: Este módulo NO reimplementa el modelo.
│   │   # El equipo de ML mantiene su propio repo con el modelo real.
│   │   # Claude Code analiza ese repo y construye:
│   │   #   1. El contrato de API (qué endpoints, qué reciben, qué retornan)
│   │   #   2. El mock server (para que el equipo de agentes pueda trabajar sin depender del ML)
│   │   #   3. El client adapter (interfaz limpia que los agentes consumen)
│   │   #   4. Contract tests (verifican que el servicio ML real cumple el contrato)
│   │
│   ├── security/
│   │   ├── pii_tokenizer.py           # Tokeniza: cédula → TOK_CC_xxxx, nombre → TOK_NAME_xxxx
│   │   ├── pii_detokenizer.py         # Solo accesible desde servicio backend, nunca LLM
│   │   └── audit_logger.py            # Log de accesos a PII (compliance)
│   │
│   └── data/
│       ├── schemas.py                 # Pydantic models: User, Score, ChatMessage, etc.
│       ├── database.py                # Conexión DynamoDB / SQLite local
│       └── seed_data.py               # Datos sintéticos para pruebas
│
├── infra/
│   ├── aws/
│   │   ├── cdk/                       # AWS CDK (IaC)
│   │   │   ├── stacks/
│   │   │   │   ├── compute_stack.py   # ECS/Lambda + API Gateway
│   │   │   │   ├── data_stack.py      # DynamoDB, S3
│   │   │   │   ├── ml_stack.py        # SageMaker endpoints
│   │   │   │   └── security_stack.py  # IAM, KMS, WAF
│   │   │   └── app.py
│   │   └── bedrock/
│   │       └── model_config.json      # IDs de modelos, guardrails Bedrock
│   │
│   └── docker/
│       ├── Dockerfile.api             # Backend FastAPI
│       ├── Dockerfile.frontend        # Frontend React (build estático)
│       └── docker-compose.local.yml   # Stack local con Ollama incluido
│
├── tests/
│   ├── unit/
│   │   ├── test_orchestrator.py
│   │   ├── test_credit_evaluator.py
│   │   ├── test_pii_tokenizer.py
│   │   └── test_ml_client.py          # Tests del adaptador ML (contra mock server)
│   ├── contract/
│   │   └── test_ml_contract.py        # Contract tests: valida que el servicio ML real cumple
│   ├── integration/
│   │   ├── test_chat_flow.py          # E2E: mensaje → orquestador → agente → respuesta
│   │   └── test_onboarding_flow.py
│   └── conftest.py                    # Fixtures compartidos
│
├── scripts/
│   ├── seed_db.py                     # Poblar BD con datos sintéticos
│   ├── run_local.sh                   # Levantar todo localmente
│   └── deploy.sh                      # Deploy a AWS
│
└── docs/
    ├── ARCHITECTURE.md                # Este diagrama expandido
    ├── AGENT_DESIGN.md                # Prompts de sistema de cada agente
    ├── PII_POLICY.md                  # Política de manejo de datos sensibles
    └── API_REFERENCE.md               # OpenAPI docs
```

---

## 🔐 POLÍTICA DE SEGURIDAD Y PII — CRÍTICO

### Principio Fundamental
> **NINGÚN LLM (ni local ni en Bedrock) debe ver datos PII en texto plano.**

### Flujo de PII
```
Usuario dice: "Mi cédula es 1234567890, soy Juan Pérez"
          │
          ▼
   ┌─────────────────┐
   │  PII Tokenizer   │  cédula → [TOK_CC_a1b2]
   │  (Backend only)  │  nombre → [TOK_NAME_c3d4]
   └────────┬────────┘
            ▼
   LLM recibe: "Mi cédula es [TOK_CC_a1b2], soy [TOK_NAME_c3d4]"
            │
            ▼
   LLM responde: "Hola [TOK_NAME_c3d4], revisé tu score..."
            │
            ▼
   ┌──────────────────┐
   │  PII Detokenizer  │  [TOK_NAME_c3d4] → "Juan"
   │  (Backend only)   │  Solo nombre de pila para UX
   └────────┬─────────┘
            ▼
   Usuario ve: "Hola Juan, revisé tu score..."
```

### Reglas de Implementación
1. **Tokenización** ocurre en middleware FastAPI ANTES de llegar al agente
2. **Detokenización** ocurre DESPUÉS de que el agente responde, ANTES de enviar al frontend
3. El **mapping token↔valor** se almacena en DynamoDB con TTL y cifrado KMS
4. Los **logs de auditoría** registran cada acceso a PII con timestamp y razón
5. En modo local, usar SQLite cifrado para el vault de PII

---

## 🔬 INTEGRACIÓN CON REPO ML EXTERNO — WORKFLOW CRÍTICO

### Contexto
El equipo de Data/ML mantiene un repositorio separado con el modelo de scoring
crediticio. **Claude Code NO debe reimplementar el modelo.** En cambio, debe:

### Paso 1: Análisis del Repo ML (OBLIGATORIO antes de implementar agentes)
Cuando se le pase el repo ML, Claude Code debe analizarlo y generar un reporte:

```
📦 REPORTE DE ANÁLISIS — REPO ML SCORING CREDITICIO
═══════════════════════════════════════════════════

1. MODELO IDENTIFICADO:
   - Tipo: [XGBoost / LightGBM / RandomForest / NeuralNet / ...]
   - Archivo: [ruta al script de entrenamiento]
   - Serialización: [.joblib / .pkl / .h5 / .onnx / ...]

2. FEATURES DE ENTRADA (lo que el modelo NECESITA recibir):
   ┌──────────────────────┬──────────┬───────────────────────────┐
   │ Feature              │ Tipo     │ Rango/Valores esperados   │
   ├──────────────────────┼──────────┼───────────────────────────┤
   │ ingreso_mensual      │ float    │ 0 - 10,000,000           │
   │ tipo_empleo          │ category │ informal/formal/indep     │
   │ ...                  │ ...      │ ...                       │
   └──────────────────────┴──────────┴───────────────────────────┘

3. OUTPUT DEL MODELO (lo que RETORNA):
   - Predicción: [0/1 | probabilidad | score continuo]
   - Feature importances: [sí/no, formato]
   - Threshold de decisión: [valor]
   - Metadatos adicionales: [...]

4. DEPENDENCIAS:
   - Python: [versión]
   - Librerías: [scikit-learn==X, xgboost==Y, ...]

5. ENDPOINTS SUGERIDOS PARA APIFICAR:
   (Claude Code propone al equipo ML qué API construir)

   POST /api/ml/predict
   Request:  { features: { ingreso_mensual: float, ... } }
   Response: { eligible: bool, score: float, confidence: float,
               factors: [{ name: str, impact: str, value: float }] }

   POST /api/ml/score-history/{user_id}
   Response: { scores: [{ date: str, score: float }], trend: str }

   GET /api/ml/features-spec
   Response: { features: [{ name, type, required, range }] }

   GET /api/ml/model-info
   Response: { model_type, version, last_trained, metrics: { auc, precision, recall } }

6. OBSERVACIONES Y RECOMENDACIONES:
   - [Lo que Claude Code note: data leakage, features faltantes, etc.]
   - [Sugerencias de mejora para el equipo ML]
```

### Paso 2: Generar Contrato de API (OpenAPI Spec)
Con la info del análisis, Claude Code genera un archivo `ml_contract.yaml` con
la especificación OpenAPI exacta que el equipo ML debe implementar.

### Paso 3: Construir Mock Server
Claude Code crea un mock server FastAPI (`ml_client/mock_server.py`) que:
- Implementa los endpoints del contrato
- Retorna respuestas realistas basadas en los rangos del modelo real
- Permite al equipo de agentes trabajar en paralelo sin depender del ML

### Paso 4: Construir Client Adapter
Claude Code crea el adaptador (`ml_client/client.py`) con:
```python
class MLClient:
    """Consume la API del servicio ML. Misma interfaz para mock y real."""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.getenv("ML_SERVICE_URL", "http://localhost:8001")

    async def predict(self, features: dict) -> CreditPrediction: ...
    async def get_score_history(self, user_id: str) -> list[ScoreEntry]: ...
    async def get_feature_spec(self) -> list[FeatureSpec]: ...
    async def get_improvement_factors(self, user_id: str) -> list[ImprovementFactor]: ...
```

### Paso 5: Contract Tests
Tests que se ejecutan contra el servicio ML real para verificar que cumple:
```python
# test_ml_contract.py
def test_predict_returns_expected_schema():
    """El endpoint /predict retorna el formato que los agentes esperan."""

def test_predict_handles_edge_cases():
    """Ingreso=0, datos faltantes, valores extremos."""

def test_feature_spec_matches_contract():
    """Las features del modelo real coinciden con el contrato."""
```

### Variables de entorno
```bash
ML_SERVICE_URL=http://localhost:8001   # Mock local
# ML_SERVICE_URL=https://ml-api.internal.bbva.co  # Producción
```

---

## 🤖 DISEÑO DE AGENTES — SYSTEM PROMPTS

### Agente 1: Onboarding (Web Pública)
```
Eres el asistente de bienvenida de BBVA Colombia. Tu misión es guiar a personas
que AÚN NO son clientes del banco para que abran su primera cuenta de forma
rápida y amigable.

PERSONALIDAD: Cercano, colombiano, usa lenguaje sencillo. Tuteas al usuario.
Eres paciente y celebras cada paso que el usuario completa.

FLUJO:
1. Saluda cálidamente, pregunta el nombre
2. Explica brevemente los beneficios de bancarizarse (en 2-3 frases máximo)
3. Recopila datos mínimos: nombre completo, cédula, ingreso promedio mensual
4. Confirma los datos con el usuario antes de enviar
5. Ejecuta tool: check_credit_score(datos) → obtiene resultado del modelo ML
6. Si APROBADO: felicita, guía a abrir cuenta, pregunta si quiere activar Helpyy Hand
7. Si RECHAZADO: con empatía, explica que aún no califica pero que lo ayudarás a mejorar

TOOLS DISPONIBLES:
- check_credit_score(name_token, cc_token, income) → {approved: bool, score: float, factors: [...]}
- create_account(user_token) → {account_id, status}
- enable_helpyy_hand(user_id) → {enabled: bool}

RESTRICCIONES:
- NUNCA muestres el score numérico al usuario
- NUNCA menciones tokens o IDs internos
- Si el usuario te da información sensible, confirma que está segura
- Máximo 3 mensajes para recopilar datos, no seas repetitivo
```

### Agente 2: Evaluador de Crédito
```
Eres el evaluador de crédito de Helpyy Hand. Tu trabajo es consultar el modelo
de Machine Learning y traducir el resultado en una respuesta clara y empática.

CUANDO RECIBES UNA CONSULTA:
1. Ejecuta tool: get_credit_prediction(user_token)
2. Analiza los factores del modelo (feature importances)
3. Si APROBADO: presenta montos, plazos y cuotas estimadas
4. Si RECHAZADO: lista los 3 factores principales que lo impiden y sugiere acciones

PERSONALIDAD: Profesional pero accesible. Usa analogías simples para explicar
conceptos financieros. Nunca seas condescendiente.

TOOLS:
- get_credit_prediction(user_token) → {eligible, score_band, max_amount, factors}
- get_loan_simulation(amount, term_months) → {monthly_payment, total_cost, rate}

RESTRICCIONES:
- NUNCA reveles el score numérico exacto
- NUNCA menciones el nombre del modelo o sus variables internas
- Siempre enmarca el rechazo como "aún no" y no como "no"
```

### Agente 3: Monitor Insistente (Cron/Background)
```
Eres el monitor proactivo de Helpyy Hand. Tu trabajo es revisar periódicamente
el score de clientes que fueron rechazados y notificarles cuando haya mejoras.

COMPORTAMIENTO:
- Cada N horas (configurable), consultas el modelo ML para usuarios en estado "pendiente"
- Si el score mejoró → genera notificación positiva con el progreso
- Si el score no cambió → genera tip motivacional contextualizado
- Si el score empeoró → genera alerta suave con recomendación

FORMATO DE NOTIFICACIÓN:
{
  "user_id": "...",
  "type": "score_update|tip|alert",
  "title": "string corto para push notification",
  "body": "mensaje expandido para cuando abran la notificación",
  "action": "deep_link a Helpyy Hand en la app"
}

TONO: Motivador, como un coach. Usa emojis con moderación (1-2 por mensaje).
```

### Agente 4: Asesor Financiero Personal
```
Eres el asesor financiero personal de Helpyy Hand. Tu misión es ayudar al
usuario a mejorar su salud financiera para que eventualmente califique a un
microcrédito (o para que maneje mejor sus finanzas si ya calificó).

CAPACIDADES:
1. DIAGNÓSTICO: Analiza las variables del modelo ML que afectan al usuario
2. PLAN DE ACCIÓN: Crea un plan personalizado basado en su situación
   - Si vende arepas → plan para maximizar ingresos de venta informal
   - Si es trabajador por días → plan para estabilizar ingresos
3. GAMIFICACIÓN: Presenta el plan como misiones/retos con progreso visible
   - "Misión 1: Deposita tus ingresos de la semana en tu cuenta → +15 puntos"
   - "Misión 2: Mantén saldo > $200.000 por 2 semanas → +25 puntos"
4. SEGUIMIENTO: Revisa el progreso y celebra los logros

TOOLS:
- get_user_profile(user_token) → {income_pattern, expense_pattern, balance_history}
- get_improvement_factors(user_token) → [{factor, current, target, weight}]
- update_mission_progress(user_token, mission_id, completed) → {new_score, badges}

TONO: Coach motivacional pero realista. Celebra logros genuinamente.
No prometas resultados que no puedes garantizar.
```

### Agente 5: Helpyy Hand General
```
Eres Helpyy Hand, el asistente general de BBVA Colombia dentro de la app.
Ayudas con preguntas frecuentes, productos del banco y consultas operativas.

CONOCIMIENTO:
- Productos BBVA Colombia: cuentas de ahorro, tarjetas, CDTs, seguros
- Operaciones: transferencias, pagos de servicios, Bre-B, retiro sin tarjeta
- Horarios, sucursales, canales de atención
- Tarifas y comisiones básicas

COMPORTAMIENTO:
- Si la consulta es sobre microcrédito o finanzas personales → handoff al agente correspondiente
- Si la consulta es sobre onboarding → handoff al agente de onboarding
- Responde de forma directa y concisa
- Si no sabes algo, dilo honestamente y sugiere un canal de atención

TONO: Amable, eficiente, colombiano. Como un amigo que trabaja en el banco.
```

---

## 🔄 ORQUESTADOR — LÓGICA DE ROUTING

```python
# Pseudocódigo del orchestrator
class Orchestrator:
    def route(self, message: str, user_state: UserState) -> Agent:
        # 1. Si el usuario NO está bancarizado → Onboarding Agent
        if not user_state.is_banked:
            return OnboardingAgent()

        # 2. Clasificar intent del mensaje
        intent = self.classify_intent(message)

        match intent:
            case "credit_inquiry" | "loan_request":
                return CreditEvaluatorAgent()
            case "financial_advice" | "improve_score" | "budget":
                return FinancialAdvisorAgent()
            case "bank_faq" | "product_info" | "operations":
                return HelpyyGeneralAgent()
            case _:
                return HelpyyGeneralAgent()  # default

    def classify_intent(self, message: str) -> str:
        # Usa el LLM con un prompt de clasificación ligero
        # Retorna una de las categorías definidas
        ...
```

---

## ⚡ LLM GATEWAY — CAMBIO LOCAL ↔ PRODUCCIÓN

```python
# backend/llm/config.py
import os

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local")  # "local" | "bedrock"

# backend/llm/provider.py
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict], tools: list | None = None) -> str:
        ...

    @abstractmethod
    async def generate_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        ...

# backend/llm/ollama_provider.py
class OllamaProvider(LLMProvider):
    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "gemma3:4b")
        self.base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    # ...

# backend/llm/bedrock_provider.py
class BedrockProvider(LLMProvider):
    def __init__(self):
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-20250514-v1:0")
        self.region = os.getenv("AWS_REGION", "us-east-1")
    # ...

# Factory
def get_llm_provider() -> LLMProvider:
    if LLM_PROVIDER == "local":
        return OllamaProvider()
    elif LLM_PROVIDER == "bedrock":
        return BedrockProvider()
```

---

## 🧪 ESTRATEGIA DE TESTING

### Niveles
1. **Unit tests**: Cada agente aislado con mocks del LLM
2. **Integration tests**: Orquestador + agentes con LLM real (local)
3. **E2E tests**: Frontend → API → Orquestador → Agente → ML → Respuesta
4. **PII tests**: Verificar que NINGÚN dato PII llega al LLM

### Comando
```bash
make test          # Todos los tests
make test-unit     # Solo unitarios
make test-pii      # Solo tests de seguridad PII
make test-agents   # Tests de agentes con LLM local
```

---

## 📋 CONVENCIONES DE CÓDIGO

- **Python**: 3.12+, type hints obligatorios, ruff para linting, black para formato
- **Frontend**: React 18+, TypeScript si es posible, Tailwind CSS
- **Commits**: Conventional Commits (feat:, fix:, refactor:, docs:, test:)
- **Branches**: feature/agent-{nombre}, fix/{descripción}, infra/{componente}
- **Docstrings**: Google style en todo método público
- **Secrets**: NUNCA hardcoded. Siempre .env → os.getenv() con defaults seguros

---

## 🚀 WORKFLOW DE DESARROLLO CON CLAUDE CODE

### Comandos de inicio
```bash
# Clonar e instalar
git clone <repo>
cd helpyy-hand
cp .env.example .env  # Configurar variables

# Levantar stack local
make setup             # Instala dependencias Python + Node
make ollama-pull       # Descarga Gemma 3 4B
make dev               # Levanta todo: API + frontend + Ollama

# Verificar
make health            # Healthcheck de todos los servicios
```

---

## 🎨 PRINCIPIOS DE UX — EFECTO "WOW"

1. **Transiciones suaves** entre estados del agente (badge cambia con animación)
2. **Typing indicator** realista (variable, no fijo)
3. **Streaming** de respuestas palabra por palabra
4. **Notificaciones** del agente insistente con sonido sutil y vibración
5. **Gamificación visual**: barra de progreso hacia el microcrédito, badges, confetti al completar misiones
6. **Onboarding**: el popup en la web debe sentirse como WhatsApp, no como un formulario bancario
7. **Dark/Light** mode en la app
8. **Micro-animaciones** en cada interacción (mensajes que aparecen con spring animation)