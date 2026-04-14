# ESTADO ACTUAL DEL PROYECTO — Helpyy Hand
> Última actualización: 2026-04-10  
> Este documento complementa CLAUDE.md con todos los cambios de implementación real realizados en las sesiones de desarrollo. Léelo **junto** a CLAUDE.md para tener el contexto completo.

---

## 1. RESUMEN EJECUTIVO

El frontend del mockup de la app bancaria BBVA y el widget web están completamente implementados y funcionales. El backend (FastAPI) ya existe y tiene los endpoints de onboarding operativos. Lo que queda pendiente es el backend de agentes LLM y la integración ML.

**Stack actual:**
- Frontend app: React 18 + Vite + Framer Motion (sin TypeScript, plain JSX)
- Frontend web widget: HTML/CSS/JS vanilla (inyectable como widget)
- Backend: FastAPI (Python) — ver `/backend/`
- Auth: localStorage-based (PIN + cédula, sin JWT — es mockup)

---

## 2. ESTRUCTURA REAL DEL FRONTEND (lo que existe hoy)

```
frontend/
├── web-widget/
│   └── index.html          ← Página BBVA pública completa + widget chat flotante
│
└── app-mockup/
    └── src/
        ├── App.jsx                          ← Entry point, router isBanked
        ├── contexts/
        │   └── AgentContext.jsx             ← Estado global (auth, chat, agentes)
        ├── hooks/
        │   ├── useChat.js                   ← WebSocket streaming al backend
        │   └── useAgentState.js             ← Estado del agente activo
        └── components/
            ├── PreLoginScreen.jsx           ← Pantalla pre-login (5 vistas)
            ├── BankDashboard.jsx            ← Dashboard post-login
            ├── CameraCapture.jsx            ← Cámara real (getUserMedia)
            ├── HelpyyPanel.jsx              ← Panel de chat con agentes
            ├── OnboardingFlow.jsx           ← Flujo de activación Helpyy
            ├── AgentBadge.jsx               ← Badge visual por tipo de agente
            └── NotificationBell.jsx         ← Notificaciones del agente monitor
```

---

## 3. FLUJOS DE AUTENTICACIÓN IMPLEMENTADOS

### 3.1 Estructura de cuenta en localStorage

```javascript
// key: 'helpyy_account'
{
  accountId: "ACC-XXXXXXXX",   // viene del backend
  displayName: "Juan",          // nombre a mostrar
  pin: "1234",                  // 4 dígitos, plain text (mockup)
  cedula: "1234567890",         // vacío si activó con código web
  helpyyActive: false,          // true = muestra gamificación microcrédito
  isFreshAccount: true          // true = saldo $0, sin transacciones
}
```

### 3.2 Flujo A — Registro directo en la app (nuevo usuario)
```
welcome → "Crear cuenta" → in-app-register (4 pasos) → pin-setup → BankDashboard
```
1. **in-app-register paso 1**: nombre completo, cédula, ingreso mensual
2. **in-app-register paso 2**: selfie con `CameraCapture` (modo liveness facial)
3. **in-app-register paso 3**: foto cédula frontal con `CameraCapture` (modo documento)
4. **in-app-register paso 4**: foto cédula posterior + `POST /api/v1/onboarding/create-account`
5. Backend devuelve `{ success, display_name, account_id }` → `preparePinSetup()`
6. **pin-setup**: crear PIN de 4 dígitos (2 pasos: crear → confirmar) → `savePinAndLogin()`
7. Entra al dashboard con `isFreshAccount: true`, `helpyyActive: false`

### 3.3 Flujo B — Activación con código (usuario que vino del widget web)
```
welcome → "Tengo un código" → code-input → pin-setup → BankDashboard
```
1. Ingresa código `HLP-XXXXXX` → `POST /api/v1/onboarding/activate`
2. Si válido: importa historial de chat de la sesión web → `preparePinSetup({ helpyyActive: true })`
3. **pin-setup**: igual que arriba
4. Entra al dashboard con `helpyyActive: true` (tarjeta Helpyy gamificación VISIBLE)
5. **Nota**: estos usuarios NO tienen `cedula` guardada → el login solo valida PIN

### 3.4 Flujo C — Usuario regresante (PIN login)
```
welcome → "Iniciar sesión" → pin-login → BankDashboard
```
1. Detecta `hasStoredAccount` en `AgentContext` (lee localStorage al montar)
2. Muestra nombre del usuario guardado + sus iniciales
3. Pide cédula + PIN de 4 dígitos
4. `loginWithPin(cedula, pin)` — lógica:
   - Si la cuenta tiene `cedula` guardada: valida cedula Y pin
   - Si la cuenta NO tiene `cedula` (activó con código web): solo valida pin
5. Opción "¿No eres tú? Cambiar cuenta" → `clearStoredAccount()` + vuelve a welcome

### 3.5 Logout
Desde `BankDashboard`, hay dos formas:
- Botón "Cambiar usuario" en la welcome card
- Menú lateral (hamburger) → "Cerrar sesión"
Ambos llaman `logout()` del contexto → limpia sesión PERO conserva localStorage (el usuario puede volver a loguearse sin recrear cuenta).

---

## 4. AGENTCONTEXT — ESTADO GLOBAL

**Archivo**: `frontend/app-mockup/src/contexts/AgentContext.jsx`

### Variables de estado clave
| Variable | Tipo | Descripción |
|---|---|---|
| `isBanked` | bool | true = usuario autenticado → muestra BankDashboard |
| `hasStoredAccount` | bool | true = hay cuenta en localStorage (cargado al montar) |
| `isFreshAccount` | bool | true = cuenta nueva → saldo $0, sin transacciones |
| `helpyyActive` | bool | true = muestra gamificación microcrédito en dashboard |
| `userProfile` | `{name, accountId}` | Datos del usuario actual |
| `pendingProfile` | object o null | Perfil en vuelo mientras se crea el PIN |
| `helpyyPanelOpen` | bool | Controla visibilidad del panel de chat |
| `showActivationModal` | bool | Modal de activación de Helpyy Hand |

### Métodos del contexto
```javascript
preparePinSetup(profile)        // Guarda perfil en pendingProfile, espera PIN
savePinAndLogin(pin)            // Persiste en localStorage, setea isBanked=true
loginWithPin(cedula, pin)       // Retorna bool, valida contra localStorage
logout()                        // Limpia sesión, preserva localStorage
clearStoredAccount()            // Borra localStorage + resetea hasStoredAccount
activateHelpyy()                // Setea helpyyActive=true + persiste en localStorage
triggerActivation()             // Abre modal de activación
activateFromCode(profile)       // Legacy alias → llama preparePinSetup
```

### onMetadata (callback del chat)
Cuando el backend devuelve metadata en el stream de chat:
```javascript
onMetadata: (meta) => {
  if (meta.display_name || meta.account_id) → actualiza userProfile
  if (meta.helpyy_enabled) → setHelpyyActive(true) + persiste en localStorage
  if (meta.account_id && !meta.helpyy_enabled) → setIsBanked(true)
}
```
Esto significa que si el usuario pregunta por microcrédito en el chat y el backend responde con `helpyy_enabled: true`, la tarjeta de gamificación aparece automáticamente.

---

## 5. PRELOGINSCREEN — DISEÑO Y VISTAS

**Archivo**: `frontend/app-mockup/src/components/PreLoginScreen.jsx`

### Frame del teléfono
```javascript
// Contenedor principal
width: 390, minHeight: 844,
borderRadius: 38,
background: 'linear-gradient(180deg, #7fb3e7 0%, #78aee4 42%, #dfe7f2 100%)'
```

### Componentes internos
- **`CityBackground()`**: Arte CSS de skyline urbano con `clip-path`. Sin SVGs externos. Gradiente de cielo azul BBVA como fondo. 3 edificios: spire central, bloque izquierdo complejo, edificio derecho angular.
- **`StatusBar()`**: Hora en tiempo real (HH:MM), barras de señal, WiFi, batería. Todo CSS puro.
- **`PinKeypad()`**: Grid 3×4, botones de 64px con glass effect, indicadores de 18px.
- **`PhotoStep()`**: Ver sección 6 (CameraCapture).
- **`StepDots()`**: Indicador de pasos con punto expandido para el activo.

### Sistema de vistas (estado `view`)
```javascript
// Posibles valores
'welcome'         // Pantalla inicial
'pin-login'       // Login usuario existente
'in-app-register' // Registro nuevo usuario (4 pasos internos via regStep)
'pin-setup'       // Creación de PIN (2 pasos: create → confirm)
'code-input'      // Ingreso de código HLP-XXXXXX
```

### Animaciones entre vistas
```javascript
const slide = {
  enter: { opacity: 0, x: 40 },
  center: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -40 },
};
// Envuelto en <AnimatePresence mode="wait">
```

### Glass card (estilo base de todas las cards)
```javascript
const glassCard = {
  background: 'rgba(255,255,255,0.92)',
  backdropFilter: 'blur(12px)',
  borderRadius: 30,
  boxShadow: '0 14px 28px rgba(10, 29, 110, 0.1)',
  padding: '28px 24px',
};
```

### Tipografía Georgia (headings BBVA)
```javascript
fontFamily: 'Georgia, "Times New Roman", serif'
// fontSize según el nivel: 42px (hero), 36px (login), 28px (secciones)
// color: #08145d (azul oscuro BBVA)
// letterSpacing: -1.2px (hero), -1px (normal)
```

---

## 6. CAMERACAPTURE — CÁMARA REAL CON LIVENESS

**Archivo**: `frontend/app-mockup/src/components/CameraCapture.jsx`

### Por qué existe
El atributo `capture` de `<input type="file">` solo abre la cámara en móvil. En desktop siempre abre el file picker. `CameraCapture` usa `getUserMedia` → funciona en desktop Y móvil, con control total del stream.

### Props
```javascript
<CameraCapture
  mode="selfie"     // 'selfie' | 'document'
  onCapture={fn}    // fn(dataUrl: string) — JPEG base64
  onClose={fn}      // fn() — cerrar sin capturar
/>
```

### Modo Selfie — Liveness Detection
5 pasos secuenciales con timer automático:
```javascript
const SELFIE_STEPS = [
  { id: 'center', label: 'Mira de frente',      emoji: '😐', duration: 3000 },
  { id: 'left',   label: 'Gira a la izquierda', emoji: '👈', duration: 3000 },
  { id: 'right',  label: 'Gira a la derecha',   emoji: '👉', duration: 3000 },
  { id: 'up',     label: 'Mira hacia arriba',    emoji: '👆', duration: 2800 },
  { id: 'smile',  label: '¡Sonríe!',             emoji: '😁', duration: 2500 },
];
```
- Cada paso avanza automáticamente al terminar su `duration`
- Anillo SVG de progreso verde alrededor del oval de la cara
- Al completar el último paso → auto-captura + flash blanco
- Video mirrored (`scaleX(-1)`) para selfie natural; captura des-mirrorada
- `scheduleNextStep` / `advanceStep` usan un ref intermedio para evitar dependencia circular en `useCallback`

### Modo Document — Detección de ID
Análisis de píxeles por canvas cada frame (RAF):
```javascript
function scoreDoc(ctx, x, y, w, h) {
  // Muestrea la región guía (72% del ancho x 45% del alto, centrada)
  // Calcula desviación estándar de luminosidad (escala de grises)
  // Score = min(1, stdDev / 42) * brightOk
  // brightOk = 1 si mean entre 55-225, sino 0.2 (penaliza sobre/sub exposición)
  // Retorna float 0-1
}
```
- Score ≥ 0.55 → documento detectado → inicia timer de estabilidad
- Timer de estabilidad: `DOC_STABLE_MS = 10000` ms (10 segundos estable antes de capturar)
- Barra de progreso amarilla/verde durante el conteo
- Si el score cae antes de completar → timer se reinicia
- Marcadores de esquina del frame cambian de blanco a verde cuando hay documento

### Captura
```javascript
function doCapture() {
  // 1. Flash blanco (opacity 1 → 0 en 250ms)
  // 2. Dibuja video en canvas offscreen
  // 3. Para el stream (getTracks().forEach(t => t.stop()))
  // 4. Cancela RAF y timers
  // 5. onCapture(dataUrl) después de 500ms (para que se vea el flash)
}
```

### Fallback manual
Botón "Capturar manualmente" siempre visible mientras no se haya capturado, por si la detección automática no funciona.

### Uso en PhotoStep
```javascript
// En PreLoginScreen.jsx
function PhotoStep({ subtitle, capture, photo, onPhoto, onSimulate }) {
  const [showCamera, setShowCamera] = useState(false);
  const cameraMode = capture === 'user' ? 'selfie' : 'document';

  return (
    <div>
      {showCamera && (
        <CameraCapture
          mode={cameraMode}
          onCapture={(dataUrl) => { onPhoto(dataUrl); setShowCamera(false); }}
          onClose={() => setShowCamera(false)}
        />
      )}
      {/* Botón "Cámara" → setShowCamera(true) */}
      {/* Botón "Archivo" → <input type="file" sin capture> */}
      {/* Link "Simular captura (demo)" → foto placeholder */}
    </div>
  );
}
```

---

## 7. BANKDASHBOARD — DISEÑO POST-LOGIN

**Archivo**: `frontend/app-mockup/src/components/BankDashboard.jsx`

### Frame
```javascript
width: 390, minHeight: 844,
borderRadius: 38,
background: '#dfe7f5'
```

### Secciones principales
1. **Header** (260px): gradiente de cielo azul BBVA idéntico al PreLoginScreen + edificios CSS
   - Logo "BBVA" (Georgia, 48px, blanco)
   - Botón hamburger (círculo negro #081468, 64px) → abre drawer lateral
   - Botón campana de notificaciones (`NotificationBell`)
2. **Welcome card** (glass morphism): muestra nombre, saldo, últimos 4 del accountId
   - Botón "Cambiar usuario" → `logout()`
3. **Helpyy progress card**: `{helpyyActive && <ProgressCard />}` — condicional
4. **Acciones rápidas**: Transferir, Pagar, Bre-B, Retiro sin tarjeta
5. **Cuentas**: muestra saldo ($0 si `isFreshAccount`, else $1.245.800 mock)
6. **Últimos movimientos**: vacío si `isFreshAccount`, else transacciones mock
7. **Bottom nav**: Home, Operar, Contratar, Helpyy, Bell

### Saldo y transacciones condicionales
```javascript
const { isFreshAccount, helpyyActive, userProfile } = useAgent();
const balance = isFreshAccount ? 0 : 1245800;
const transactions = isFreshAccount ? [] : MOCK_TRANSACTIONS;
const accountLastFour = isFreshAccount
  ? userProfile.accountId?.slice(-4) || '0000'
  : '4521';
```

### Logout
```javascript
const { logout } = useAgent();

// En el drawer lateral:
<button onClick={() => { setDrawerOpen(false); logout(); }}>
  Cerrar sesión
</button>

// En la welcome card:
<button onClick={logout}>Cambiar usuario</button>
```

### Helpyy panel
Botón en bottom nav → `setHelpyyPanelOpen(true)` → renderiza `<HelpyyPanel>` como overlay.

---

## 8. WEB WIDGET — index.html

**Archivo**: `frontend/web-widget/index.html`

### Propósito
Página standalone que simula la web pública de BBVA Colombia, con:
1. Página de marketing completa (nav, hero, sección préstamos, features, footer)
2. Widget de chat flotante (Helpyy Hand) inyectado como script en la página

### Diseño BBVA
```css
--bbva-blue: #0727b5;
--bbva-dark: #0b1650;
/* Nav con bordes redondeados (nav-shell, border-radius: 22px) */
/* Hero en grid 2 columnas: texto oscuro izquierda, visual azul derecha */
/* Cards con border-radius: 22px, background: #f8f8fb */
/* Footer oscuro + barra azul bottom */
```

### Widget de chat
- Botón flotante en la esquina inferior derecha
- Al abrirse: panel de chat con el agente de onboarding
- Conecta al backend via WebSocket/REST igual que la app
- Al completar el onboarding, genera un código `HLP-XXXXXX` para usar en la app
- Botones que abren el widget: `#main-cta`, `#hero-cta`, `#loan-cta`, `#open-helpyy-btn`

---

## 9. BACKEND — ENDPOINTS RELEVANTES PARA EL FRONTEND

El backend ya está implementado. Los endpoints que el frontend consume:

```
POST /api/v1/onboarding/create-account
  Body: { session_id, name, cedula, income }
  Response: { success, display_name, account_id, credit_eligible }

POST /api/v1/onboarding/activate
  Body: { code }  ← código HLP-XXXXXX del widget web
  Response: { valid, display_name, account_id, session_id }

GET /api/v1/onboarding/chat-history/{session_id}
  Response: { messages: [{ role, content, agent }] }

POST /api/v1/chat  (o WebSocket /ws/chat)
  Para el panel de agentes dentro de la app
  Body: { session_id, message, is_banked }
  Response stream: chunks con texto + metadata opcional
```

### Metadata del stream de chat
El backend puede enviar metadata especial en el stream:
```json
{ "metadata": { "helpyy_enabled": true, "display_name": "Juan", "account_id": "ACC-XXX" } }
```
Esto lo procesa `onMetadata` en `AgentContext` para actualizar estado de la UI.

---

## 10. DECISIONES DE DISEÑO RELEVANTES

### Por qué PIN + Cédula (no contraseña)
La cédula colombiana es el identificador universal del ciudadano. Es lo que cualquier colombiano sabe de memoria. El PIN de 4 dígitos es familiar (igual que tarjetas débito/crédito). Juntos forman un auth lo suficientemente seguro para el mockup sin necesidad de JWT ni sesiones de servidor.

### Por qué helpyyActive es false por defecto en registro directo
Si alguien crea cuenta directamente desde la app, no necesariamente quiere un microcrédito — quizás solo quiere bancarizarse. La tarjeta de gamificación solo aparece si:
- Vino del widget web (pasó por el flujo Helpyy de onboarding) → `helpyyActive: true`
- O pregunta explícitamente por microcrédito en el chat → el backend envía `helpyy_enabled: true`

### Por qué CameraCapture usa timer y no FaceDetector API
`FaceDetector` es experimental y solo funciona en Chrome. El timer-based progression (5 pasos × duración fija) es:
- Compatible con todos los navegadores
- No requiere permisos adicionales
- Suficientemente convincente para el demo
- La detección real se haría en el backend (al enviar la foto)

### Por qué la cuenta se guarda en localStorage (no cookies/sesión)
Es un mockup de app bancaria. En producción usarían biometría del SO + secure enclave. Para el demo, localStorage permite simular la experiencia de "usuario regresante" sin infraestructura de sesiones.

---

## 11. ARCHIVOS DE BACKUP

Antes de los cambios mayores de diseño se crearon backups:
```
frontend/app-mockup/src/components/PreLoginScreen.jsx.bak
frontend/app-mockup/src/components/BankDashboard.jsx.bak
frontend/web-widget/index.html.bak
```

---

## 12. PENDIENTE / PRÓXIMOS PASOS

### Frontend
- [ ] Integrar fotos de KYC con el backend (actualmente se capturan pero no se envían)
- [ ] Notificaciones push reales del Agente Monitor (actualmente mock)
- [ ] Dark mode
- [ ] El widget web debería usar el mismo `CameraCapture` pattern para el KYC si se implementa en el futuro

### Backend / Agentes
- [ ] Implementar los 5 agentes LLM (Orchestrator, Onboarding, Credit Evaluator, Monitor, Advisor, General)
- [ ] Integrar el modelo ML de scoring crediticio (ver `backend/ml_client/`)
- [ ] Implementar el cron del Agente Monitor (revisar scores periódicamente)
- [ ] PII tokenizer middleware

### Infraestructura
- [ ] Configurar AWS Bedrock como LLM provider (actualmente usa Ollama local)
- [ ] Deploy a ECS/Lambda
- [ ] DynamoDB para persistencia real (reemplaza localStorage)
