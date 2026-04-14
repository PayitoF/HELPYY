# Guia de Uso Local — Helpyy Hand

Guia paso a paso para levantar todo el stack localmente y hacer la demo.

---

## Prerequisitos

- **Python 3.12+** (`python3 --version`)
- **Node.js 18+** y npm (`node --version`)
- **Ollama** (opcional, para LLM local): https://ollama.com/download
- **Docker** (opcional, alternativa con `docker compose up`)

---

## 1. Instalacion rapida (sin Docker)

```bash
# Clonar y entrar al proyecto
cd helpyy-hand

# Copiar variables de entorno
cp .env.example .env

# Instalar dependencias Python (backend + tests)
pip install -e ".[dev]"

# Instalar dependencias frontend
cd frontend/app-mockup && npm install && cd ../..
```

---

## 2. Levantar los servicios

Necesitas **3 terminales** (o usa `&` para background):

### Terminal 1 — Backend API (puerto 8000)

```bash
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Verifica: `curl http://localhost:8000/health` → `{"status":"ok","service":"helpyy-hand-api"}`

### Terminal 2 — ML Mock Server (puerto 8001)

```bash
uvicorn backend.ml_client.mock_server:app --host 0.0.0.0 --port 8001 --reload
```

Verifica: `curl http://localhost:8001/health` → respuesta OK

### Terminal 3 — Frontend React (puerto 5173)

```bash
cd frontend/app-mockup
npm run dev
```

Abre: **http://localhost:5173**

> El frontend tiene proxy configurado en `vite.config.js` — las llamadas a `/api/*` y `/ws/*` se redirigen automaticamente al backend en `localhost:8000`.

### (Opcional) Terminal 4 — Ollama LLM Local

Si quieres respuestas reales del LLM (no solo las respuestas del mock):

```bash
ollama pull gemma3:4b
ollama serve
```

Verifica `.env` tiene `LLM_PROVIDER=local` y `OLLAMA_MODEL=gemma3:4b`.

---

## 3. Alternativa con Docker

```bash
cp .env.example .env
docker compose up
```

Esto levanta: API (:8000), ML Mock (:8001), Frontend (:5173), Ollama (:11434).

---

## 4. Alternativa con Makefile

```bash
make setup        # Instala Python + Node deps
make ollama-pull  # Descarga Gemma 3 (opcional)
make dev          # Levanta todo (usa docker para ollama + ml-mock)
make health       # Verifica que todo esta arriba
```

---

## 5. Correr los tests

```bash
# Todos (390 tests)
python3 -m pytest tests/ -v

# Solo unitarios
python3 -m pytest tests/unit/ -v

# Solo integracion (WebSocket, streaming)
python3 -m pytest tests/integration/ -v

# Solo E2E (3 escenarios completos)
python3 -m pytest tests/integration/test_e2e_scenarios.py -v

# Solo tests de PII
python3 -m pytest tests/unit/test_pii_tokenizer.py -v

# Solo contract tests del ML
python3 -m pytest tests/contract/ -v

# Con coverage
python3 -m pytest tests/ -v --cov=backend
```

> Los tests NO requieren Ollama ni Docker. Usan mocks internos (SpyLLM, FakeLLM).

---

## 6. Demo — Que mostrar y como

### Demo A: Web Widget (Onboarding no-cliente)

1. Abre `frontend/web-widget/index.html` directamente en el navegador (doble-click)
2. Aparece una pagina simulada de BBVA Colombia
3. Click en el boton flotante verde "Helpyy Hand" (esquina inferior derecha)
4. Se abre el popup de chat de onboarding
5. **Flujo a mostrar:**
   - El bot saluda y pregunta el nombre
   - Escribe: "Me llamo Carlos Perez"
   - Te pide cedula e ingresos
   - Escribe: "Mi cedula es 1234567890 y gano 1500000"
   - Confirma los datos → evaluacion ML → aprobado (income >= $1.2M)

> **Nota:** El widget funciona standalone con respuestas mockeadas. Para conectarlo al backend real, asegurate de que el API este corriendo y ajusta la URL en `helpyy-widget.js`.

### Demo B: App Bancaria (Cliente bancarizado)

1. Abre **http://localhost:5173** (requiere backend corriendo)
2. Ves el dashboard bancario estilo app movil (frame 430x932)
3. **Flujo pre-activacion:**
   - El icono de Helpyy Hand aparece gris en la barra inferior
   - Click en el icono → se abre modal de activacion
   - Click "Activar" → animacion de confetti + checkmark
4. **Flujo post-activacion:**
   - El icono aparece verde con gradiente (animacion spring)
   - Click → se abre el panel de chat
   - Escribe "Quiero un microprestamo" → se enruta al Evaluador de Credito
   - Escribe "Mejorar mi puntaje" → se enruta al Asesor Financiero
   - Observa los badges de agente que cambian con animacion
5. **Tab Mi Progreso:**
   - Click en la pestana "Mi Progreso" dentro del chat
   - Muestra nivel, puntos y misiones de gamificacion

### Demo C: Tests en vivo

```bash
# Mostrar que los 390 tests pasan
python3 -m pytest tests/ -v --tb=short

# Mostrar E2E especificos
python3 -m pytest tests/integration/test_e2e_scenarios.py -v -s
```

**Escenarios E2E que se validan:**

| Escenario | Que prueba |
|-----------|-----------|
| 1. Onboarding exitoso | Nombre → cedula → income $1.5M → ML aprueba → cuenta → Helpyy → evaluacion de credito con 3 opciones de plazo |
| 2. Rechazo + gamificacion | Income $300K → ML rechaza → handoff a asesor financiero → plan de 4 semanas → monitor genera notificacion |
| 3. PII nunca llega al LLM | Cedula, nombre, email, telefono → todo tokenizado antes del LLM → detokenizado despues |

---

## 7. Arquitectura de lo que estas viendo

```
Browser (:5173)
    │
    ├─ /api/* ──proxy──► FastAPI (:8000)
    │                        │
    │                        ├─ PII Tokenizer (middleware)
    │                        ├─ Orchestrator (clasifica intent)
    │                        │     ├─ Onboarding Agent
    │                        │     ├─ Credit Evaluator Agent ──► ML Mock (:8001)
    │                        │     ├─ Financial Advisor Agent
    │                        │     └─ Helpyy General Agent
    │                        └─ PII Detokenizer
    │
    └─ /ws/* ──proxy──► WebSocket (:8000/api/v1/ws/chat/{session})
                            └─ Streaming token-by-token
```

---

## 8. Troubleshooting

| Problema | Solucion |
|----------|----------|
| `ModuleNotFoundError: backend` | Ejecuta `pip install -e ".[dev]"` desde la raiz |
| Frontend no conecta al backend | Verifica que el API corre en `:8000` y que Vite tiene proxy (`vite.config.js`) |
| WebSocket "Reconectando..." | El backend no esta corriendo o hay error de CORS |
| Tests fallan con `ImportError` | Asegurate de instalar con `pip install -e ".[dev]"` (las dependencias dev incluyen pytest) |
| `Connection refused :8001` | El ML mock server no esta corriendo. Los tests no lo necesitan (usan mocks internos) |
| Ollama no responde | Solo necesario si `LLM_PROVIDER=local` en `.env`. Los tests funcionan sin Ollama |

---

## 9. Estructura de archivos clave

```
backend/
  api/main.py              # FastAPI app, health check en /health
  api/routers/chat.py      # POST /api/v1/chat + WebSocket /api/v1/ws/chat/{session}
  agents/orchestrator.py   # Router de agentes, classify_intent con LLM
  agents/*_agent.py        # 5 agentes especializados
  ml_client/mock_server.py # ML mock (uvicorn ... --port 8001)
  security/pii_tokenizer.py  # Tokeniza PII antes del LLM

frontend/
  web-widget/index.html    # Widget embebible (standalone, abrir directo)
  app-mockup/              # React app (npm run dev)

tests/
  unit/                    # 350+ tests unitarios
  integration/             # WebSocket + E2E scenarios
  contract/                # Validacion del contrato ML
```
