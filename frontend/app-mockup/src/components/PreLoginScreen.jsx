import React, { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAgent } from '../contexts/AgentContext';
import CameraCapture from './CameraCapture';

const API_BASE = '/api/v1/onboarding';

const INCOME_OPTIONS = [
  { label: 'Menos de $500.000', value: 300000 },
  { label: '$500.000 – $1.000.000', value: 750000 },
  { label: '$1.000.000 – $2.000.000', value: 1500000 },
  { label: '$2.000.000 – $4.000.000', value: 3000000 },
  { label: 'Más de $4.000.000', value: 5000000 },
];

/* ─── City skyline background art (matches the BBVA mobile mock) ─── */
function CityBackground() {
  return (
    <div style={{
      position: 'absolute', inset: 0, zIndex: 0, overflow: 'hidden', pointerEvents: 'none',
      background: 'linear-gradient(180deg, #7fb3e7 0%, #78aee4 42%, #dfe7f2 100%)',
    }}>
      {/* Light overlay */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(circle at 50% 16%, rgba(255,255,255,0.26), transparent 18%), linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.35) 100%)',
      }} />
      {/* Center spire */}
      <div style={{
        position: 'absolute', left: '50%', top: 112, width: 10, height: 104,
        transform: 'translateX(-50%)',
        background: 'linear-gradient(180deg, #d5d6de 0%, #8f8fa2 100%)',
        borderRadius: 10, opacity: 0.7,
      }}>
        <div style={{
          position: 'absolute', top: -18, left: '50%', width: 4, height: 24,
          transform: 'translateX(-50%)', background: '#9fa3b7', borderRadius: 4,
        }} />
      </div>
      {/* Left buildings */}
      <div style={{
        position: 'absolute', bottom: 0, left: -4, width: 198, height: 220,
        background: `linear-gradient(90deg, #b18d79 0 2%, transparent 2% 20%, #f0e6de 20% 72%, #b58e77 72% 74%, transparent 74% 100%)`,
        clipPath: 'polygon(0 30%, 18% 28%, 18% 12%, 31% 8%, 33% 0, 37% 0, 39% 8%, 54% 12%, 54% 28%, 100% 25%, 100% 100%, 0 100%)',
        opacity: 0.95,
      }} />
      {/* Right building */}
      <div style={{
        position: 'absolute', bottom: 0, right: -4, width: 124, height: 220,
        background: 'linear-gradient(180deg, #7a4b3c 0 12%, #925843 12% 14%, transparent 14% 100%)',
        clipPath: 'polygon(0 22%, 24% 0, 100% 16%, 100% 100%, 0 100%)',
        opacity: 0.95,
      }} />
    </div>
  );
}

/* ─── Status bar ─── */
function StatusBar() {
  const now = new Date();
  const h = now.getHours().toString().padStart(2, '0');
  const m = now.getMinutes().toString().padStart(2, '0');
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '24px 22px 8px', position: 'relative', zIndex: 2 }}>
      <span style={{ color: '#08145d', fontSize: 17, fontWeight: 700 }}>{h}:{m}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {/* Signal */}
        <div style={{ display: 'grid', gridAutoFlow: 'column', alignItems: 'end', gap: 2, width: 20, height: 14 }}>
          {[5, 8, 11, 14].map((h, i) => (
            <div key={i} style={{ width: 4, height: h, background: '#08145d', borderRadius: '2px 2px 0 0', opacity: i < 3 ? 0.5 + i * 0.2 : 1 }} />
          ))}
        </div>
        {/* WiFi */}
        <div style={{ width: 18, height: 14, border: '3px solid #08145d', borderColor: '#08145d transparent transparent transparent', borderRadius: '50%', transform: 'scaleX(1.15) translateY(2px)', position: 'relative' }}>
          <div style={{ position: 'absolute', left: '50%', bottom: 1, width: 4, height: 4, transform: 'translateX(-50%)', background: '#08145d', borderRadius: '50%' }} />
        </div>
        {/* Battery */}
        <div style={{ minWidth: 31, height: 22, borderRadius: 8, background: 'rgba(181,184,193,0.95)', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 800, padding: '0 7px', position: 'relative' }}>
          85
          <div style={{ position: 'absolute', top: 7, right: -3, width: 3, height: 8, background: 'rgba(181,184,193,0.95)', borderRadius: '0 2px 2px 0' }} />
        </div>
      </div>
    </div>
  );
}

/* ─── PIN Keypad ─── */
function PinKeypad({ value, onChange, maxLen = 4 }) {
  const keys = ['1','2','3','4','5','6','7','8','9','','0','⌫'];
  return (
    <div style={{ width: '100%' }}>
      {/* Dots */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 20, marginBottom: 28 }}>
        {Array.from({ length: maxLen }).map((_, i) => (
          <div key={i} style={{
            width: 18, height: 18, borderRadius: '50%',
            background: i < value.length ? '#0a1fb8' : 'transparent',
            border: `2px solid ${i < value.length ? '#0a1fb8' : '#c9cce0'}`,
            transition: 'all .15s',
          }} />
        ))}
      </div>
      {/* Keys */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {keys.map((k, i) => (
          k === '' ? <div key={i} /> : (
            <motion.button
              key={i}
              whileTap={{ scale: 0.88 }}
              onClick={() => {
                if (k === '⌫') onChange(value.slice(0, -1));
                else if (value.length < maxLen) onChange(value + k);
              }}
              style={{
                height: 64, background: k === '⌫' ? '#eef2f8' : 'rgba(255,255,255,0.7)',
                border: '1px solid rgba(201,204,224,0.5)', borderRadius: 18,
                fontFamily: 'Inter, sans-serif', fontSize: 24, fontWeight: 600,
                color: '#0b1650', cursor: 'pointer', backdropFilter: 'blur(4px)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              {k}
            </motion.button>
          )
        ))}
      </div>
    </div>
  );
}

/* ─── Photo Step (real camera via getUserMedia + file upload fallback) ─── */
function PhotoStep({ subtitle, capture, photo, onPhoto, onSimulate }) {
  const fileRef = useRef(null);
  const [showCamera, setShowCamera] = useState(false);
  const cameraMode = capture === 'user' ? 'selfie' : 'document';

  const handleFile = (file) => {
    if (file) onPhoto(URL.createObjectURL(file));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
      {showCamera && (
        <CameraCapture
          mode={cameraMode}
          onCapture={(dataUrl) => { onPhoto(dataUrl); setShowCamera(false); }}
          onClose={() => setShowCamera(false)}
        />
      )}

      <p style={{ fontSize: 13, color: '#6b7280', textAlign: 'center', margin: 0 }}>{subtitle}</p>

      {/* Preview frame */}
      <div style={{
        width: capture === 'user' ? 180 : 260,
        height: capture === 'user' ? 180 : 150,
        borderRadius: capture === 'user' ? '50%' : 16,
        border: photo ? '3px solid #00a870' : '2px dashed #c9cce0',
        background: photo ? 'transparent' : '#f8fafc',
        overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center',
        position: 'relative',
      }}>
        {photo ? (
          <img src={photo} alt="capture" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
            <svg width={40} height={40} fill="none" stroke="#9ca3af" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span style={{ fontSize: 11, color: '#9ca3af' }}>Sin foto</span>
          </div>
        )}
        {photo && (
          <div style={{ position: 'absolute', bottom: 6, right: 6, width: 28, height: 28, borderRadius: '50%', background: '#00a870', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width={16} height={16} fill="none" stroke="white" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          </div>
        )}
      </div>

      {/* Two action buttons */}
      <div style={{ display: 'flex', gap: 10, width: '100%' }}>
        <motion.button whileTap={{ scale: 0.97 }}
          onClick={() => setShowCamera(true)}
          style={{
            flex: 1, padding: '12px 8px', borderRadius: 16, border: '1.5px solid #0a1fb8',
            background: 'transparent', color: '#0a1fb8', fontWeight: 600, fontSize: 13, cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
          }}>
          <svg width={16} height={16} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Cámara
        </motion.button>
        <motion.button whileTap={{ scale: 0.97 }}
          onClick={() => fileRef.current?.click()}
          style={{
            flex: 1, padding: '12px 8px', borderRadius: 16, border: '1.5px solid #6b7280',
            background: 'transparent', color: '#6b7280', fontWeight: 600, fontSize: 13, cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
          }}>
          <svg width={16} height={16} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          Archivo
        </motion.button>
      </div>

      {/* Demo simulate link */}
      <button onClick={onSimulate} style={{ fontSize: 11, color: '#9ca3af', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
        Simular captura (demo)
      </button>

      {/* Hidden file input (no capture attribute — always opens file picker) */}
      <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
        onChange={(e) => handleFile(e.target.files?.[0])} />
    </div>
  );
}

/* ─── Step dots ─── */
function StepDots({ current, total }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', gap: 6, marginBottom: 20 }}>
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} style={{
          width: i === current ? 20 : 6, height: 6, borderRadius: 3,
          background: i <= current ? '#0a1fb8' : '#e5e7eb',
          transition: 'all .3s',
        }} />
      ))}
    </div>
  );
}

/* ─── Input field ─── */
function Field({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{ fontSize: 12, fontWeight: 600, color: '#6b7280' }}>{label}</label>
      {children}
    </div>
  );
}

const inputStyle = {
  width: '100%', borderRadius: 16, padding: '14px 16px', outline: 'none',
  background: '#f3f4f6', border: '2px solid #e5e7eb', color: '#0b1650',
  fontSize: 15, fontFamily: 'inherit',
};

/* ─── Glass card ─── */
const glassCard = {
  background: 'rgba(255,255,255,0.92)',
  backdropFilter: 'blur(12px)',
  borderRadius: 30,
  boxShadow: '0 14px 28px rgba(10, 29, 110, 0.1)',
  padding: '28px 24px',
};

/* ─── Slide animation ─── */
const slide = {
  enter: { opacity: 0, x: 40 },
  center: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -40 },
};

/* ─── Demo placeholder image ─── */
const DEMO_PHOTO = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200' viewBox='0 0 200 200'%3E%3Crect width='200' height='200' fill='%23e0f2fe'/%3E%3Ccircle cx='100' cy='75' r='35' fill='%231464a0'/%3E%3Cellipse cx='100' cy='170' rx='55' ry='40' fill='%231464a0'/%3E%3C/svg%3E";

export default function PreLoginScreen() {
  const {
    preparePinSetup,
    savePinAndLogin,
    loginWithPin,
    clearStoredAccount,
    hasStoredAccount,
    setMessages,
  } = useAgent();

  const [view, setView] = useState(hasStoredAccount ? 'pin-login' : 'welcome');

  /* ─── Code input ─── */
  const [code, setCode] = useState('');
  const [codeError, setCodeError] = useState('');
  const [activating, setActivating] = useState(false);

  /* ─── In-app registration ─── */
  const [regStep, setRegStep] = useState(1);
  const [regName, setRegName] = useState('');
  const [regCedula, setRegCedula] = useState('');
  const [regIncome, setRegIncome] = useState('');
  const [selfiePhoto, setSelfiePhoto] = useState(null);
  const [idFrontPhoto, setIdFrontPhoto] = useState(null);
  const [idBackPhoto, setIdBackPhoto] = useState(null);
  const [registering, setRegistering] = useState(false);
  const [regError, setRegError] = useState('');

  /* ─── PIN setup ─── */
  const [pinStep, setPinStep] = useState('create');
  const [pin, setPin] = useState('');
  const [pinConfirm, setPinConfirm] = useState('');
  const [pinError, setPinError] = useState('');

  /* ─── PIN login ─── */
  const [loginCedula, setLoginCedula] = useState('');
  const [loginPin, setLoginPin] = useState('');
  const [loginError, setLoginError] = useState('');

  const storedAccount = (() => {
    try { return JSON.parse(localStorage.getItem('helpyy_account') || 'null'); }
    catch { return null; }
  })();
  const storedName = storedAccount?.displayName || '';
  const storedHasCedula = !!storedAccount?.cedula;
  const initials = storedName ? storedName.split(' ').filter(Boolean).map(w => w[0]).slice(0, 2).join('').toUpperCase() : '?';

  /* ─── Handlers ─── */
  function resetRegister() {
    setRegStep(1); setRegName(''); setRegCedula(''); setRegIncome('');
    setSelfiePhoto(null); setIdFrontPhoto(null); setIdBackPhoto(null); setRegError('');
  }

  async function handleRegister() {
    setRegistering(true); setRegError('');
    try {
      const sessionId = 'app_' + Math.random().toString(36).slice(2, 10);
      const resp = await fetch(`${API_BASE}/create-account`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, name: regName.trim(), cedula: regCedula.trim(), income: parseFloat(regIncome) }),
      });
      const data = await resp.json();
      if (!data.success) { setRegError(data.error || 'Error al crear la cuenta.'); setRegistering(false); return; }
      preparePinSetup({ name: data.display_name, accountId: data.account_id, helpyyActive: false, cedula: regCedula.trim() });
      setPinStep('create'); setPin(''); setPinConfirm(''); setPinError('');
      setView('pin-setup');
    } catch {
      setRegError('Error de conexión. Intenta de nuevo.');
    } finally { setRegistering(false); }
  }

  async function handleActivate() {
    if (!code.trim()) return;
    setActivating(true); setCodeError('');
    try {
      const resp = await fetch(`${API_BASE}/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code.trim() }),
      });
      const data = await resp.json();
      if (!data.valid) { setCodeError('Código inválido o expirado.'); setActivating(false); return; }
      try {
        const histResp = await fetch(`${API_BASE}/chat-history/${data.session_id}`);
        const histData = await histResp.json();
        if (histData.messages?.length > 0) {
          const imported = histData.messages.map(m => ({ role: m.role, content: m.content, agent: m.agent }));
          imported.push({ role: 'assistant', content: `¡Bienvenido, ${data.display_name || 'amigo'}! Ya tienes tu cuenta activa. ¿En qué te puedo ayudar?`, agent: 'helpyy_general' });
          setMessages(imported);
        }
      } catch { /* not critical */ }
      preparePinSetup({ name: data.display_name, accountId: data.account_id, helpyyActive: true });
      setPinStep('create'); setPin(''); setPinConfirm(''); setPinError('');
      setView('pin-setup');
    } catch {
      setCodeError('Error de conexión.');
    } finally { setActivating(false); }
  }

  function handlePinInput(val) {
    if (pinStep === 'create') {
      setPin(val); setPinError('');
      if (val.length === 4) setTimeout(() => { setPinStep('confirm'); setPinConfirm(''); }, 200);
    } else {
      setPinConfirm(val); setPinError('');
      if (val.length === 4) {
        setTimeout(() => {
          if (val === pin) { savePinAndLogin(pin); }
          else { setPinError('Los PINs no coinciden. Intenta de nuevo.'); setPinStep('create'); setPin(''); setPinConfirm(''); }
        }, 200);
      }
    }
  }

  function handleLoginPin(val) {
    setLoginPin(val); setLoginError('');
    if (val.length === 4) {
      setTimeout(() => {
        if (!loginWithPin(loginCedula, val)) {
          setLoginError('Cédula o PIN incorrecto. Intenta de nuevo.');
          setLoginPin('');
        }
      }, 200);
    }
  }

  /* ─── Back button ─── */
  function BackBtn({ onBack }) {
    return (
      <button onClick={onBack} style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20,
        background: 'none', border: 'none', cursor: 'pointer',
        color: 'rgba(8, 20, 93, 0.65)', fontSize: 14, fontWeight: 600, padding: 0,
      }}>
        <svg width={20} height={20} fill="currentColor" viewBox="0 0 24 24">
          <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
        </svg>
        Volver
      </button>
    );
  }

  /* ─── Spinner ─── */
  function Spinner() {
    return (
      <motion.span style={{ display: 'inline-block', width: 20, height: 20, border: '3px solid rgba(255,255,255,0.3)', borderTopColor: 'white', borderRadius: '50%' }}
        animate={{ rotate: 360 }} transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }} />
    );
  }

  /* ─── Primary button ─── */
  function PrimaryBtn({ children, onClick, disabled, loading }) {
    return (
      <motion.button
        whileTap={{ scale: disabled ? 1 : 0.97 }}
        onClick={onClick}
        disabled={disabled || loading}
        style={{
          width: '100%', height: 64, border: 0, borderRadius: 16,
          background: disabled || loading ? '#b9bdd7' : '#0a1fb8',
          color: 'white', fontSize: 20, fontWeight: 700, cursor: disabled || loading ? 'not-allowed' : 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
          fontFamily: 'inherit', letterSpacing: '-0.2px',
        }}
      >
        {loading ? <><Spinner />{children}</> : children}
      </motion.button>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: '#edf2f8', display: 'grid', placeItems: 'center', padding: 24 }}>
      <div style={{
        width: 390, minHeight: 844, position: 'relative', overflow: 'hidden',
        borderRadius: 38, boxShadow: '0 24px 60px rgba(8, 20, 93, 0.18)',
        display: 'flex', flexDirection: 'column',
        background: 'linear-gradient(180deg, #7fb3e7 0%, #78aee4 42%, #dfe7f2 100%)',
      }}>

        <CityBackground />

        {/* Status bar */}
        <StatusBar />

        {/* BBVA Header */}
        <div style={{ position: 'relative', zIndex: 2, padding: '4px 24px 0', textAlign: 'center' }}>
          <h1 style={{ color: 'white', fontSize: 48, fontWeight: 500, letterSpacing: 2, margin: 0, lineHeight: 1 }}>BBVA</h1>
        </div>

        {/* Content area */}
        <div style={{ flex: 1, padding: '22px 14px 32px', position: 'relative', zIndex: 2, overflowY: 'auto' }}>
          <AnimatePresence mode="wait">

            {/* ══ WELCOME ══ */}
            {view === 'welcome' && (
              <motion.div key="welcome" variants={slide} initial="enter" animate="center" exit="exit" transition={{ duration: 0.25 }}>
                {/* Main hero card */}
                <article style={glassCard}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 14 }}>
                    <div>
                      <h2 style={{ margin: 0, fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 42, lineHeight: 0.97, letterSpacing: -1.2 }}>
                        Hola,<br />bienvenido
                      </h2>
                      <button
                        onClick={() => { resetRegister(); setView('in-app-register'); }}
                        style={{ display: 'inline-block', marginTop: 20, color: '#0a21b4', fontSize: 17, fontWeight: 700, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                        Crear cuenta →
                      </button>
                    </div>
                    <div style={{ width: 104, height: 104, borderRadius: '50%', background: '#93e1e8', display: 'grid', placeItems: 'center', flexShrink: 0, fontSize: 36, color: '#1f2872', fontWeight: 500 }}>
                      <svg width={44} height={44} fill="none" stroke="#1f2872" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                    </div>
                  </div>

                  <PrimaryBtn onClick={() => { setLoginCedula(''); setLoginPin(''); setLoginError(''); setView('pin-login'); }}>
                    Iniciar sesión
                  </PrimaryBtn>

                  {/* Quick actions */}
                  <div style={{ display: 'flex', gap: 28, marginTop: 28, paddingLeft: 2 }}>
                    {[
                      { icon: '$', label: 'PSE pagos y\nrecargas' },
                      { icon: '⌂', label: 'Puntos de\natención' },
                    ].map((a, i) => (
                      <div key={i} style={{ width: 120, textAlign: 'center', color: '#0b2cb1', fontSize: 14, fontWeight: 700, lineHeight: 1.2 }}>
                        <div style={{ width: 72, height: 72, margin: '0 auto 12px', background: '#f7f7f8', borderRadius: '50%', display: 'grid', placeItems: 'center', fontSize: 28, color: '#0a21b4' }}>
                          {a.icon}
                        </div>
                        {a.label.split('\n').map((l, j) => <div key={j}>{l}</div>)}
                      </div>
                    ))}
                  </div>
                </article>

                {/* Options card */}
                <article style={{ ...glassCard, marginTop: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                    <div>
                      <h2 style={{ margin: 0, fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 28, lineHeight: 1 }}>
                        ¿Ya eres cliente?
                      </h2>
                      <p style={{ margin: '10px 0 0', color: '#213064', fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ color: '#0818aa', fontSize: 22 }}>◫</span> Accede con tu PIN
                      </p>
                    </div>
                    <span style={{ color: '#0818aa', fontSize: 30, paddingTop: 4 }}>⬡</span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 20 }}>
                    <motion.button whileTap={{ scale: 0.96 }}
                      onClick={() => { setLoginCedula(''); setLoginPin(''); setLoginError(''); setView('pin-login'); }}
                      style={{
                        background: 'rgba(251,251,252,0.96)', borderRadius: 16, minHeight: 80, padding: '16px 10px',
                        textAlign: 'center', border: 'none', cursor: 'pointer', display: 'flex', flexDirection: 'column',
                        alignItems: 'center', justifyContent: 'center', gap: 8, color: '#0f2070', fontSize: 14, fontWeight: 700,
                      }}>
                      <div style={{ width: 44, height: 44, borderRadius: '50%', background: '#e0f2fe', display: 'grid', placeItems: 'center', fontSize: 20 }}>🔐</div>
                      Ingresar con PIN
                    </motion.button>
                    <motion.button whileTap={{ scale: 0.96 }}
                      onClick={() => { setCode(''); setCodeError(''); setView('code-input'); }}
                      style={{
                        background: 'rgba(251,251,252,0.96)', borderRadius: 16, minHeight: 80, padding: '16px 10px',
                        textAlign: 'center', border: 'none', cursor: 'pointer', display: 'flex', flexDirection: 'column',
                        alignItems: 'center', justifyContent: 'center', gap: 8, color: '#0f2070', fontSize: 14, fontWeight: 700,
                      }}>
                      <div style={{ width: 44, height: 44, borderRadius: '50%', background: '#fef3c7', display: 'grid', placeItems: 'center', fontSize: 20 }}>📱</div>
                      Tengo un código
                    </motion.button>
                  </div>
                </article>

                <p style={{ textAlign: 'center', fontSize: 11, marginTop: 20, color: 'rgba(8,20,93,0.45)' }}>
                  Helpyy Hand · BBVA Colombia © 2026
                </p>
              </motion.div>
            )}

            {/* ══ PIN LOGIN ══ */}
            {view === 'pin-login' && (
              <motion.div key="pin-login" variants={slide} initial="enter" animate="center" exit="exit" transition={{ duration: 0.25 }}>
                <BackBtn onBack={() => setView('welcome')} />
                <article style={glassCard}>
                  {/* Avatar */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 14, marginBottom: 24 }}>
                    <div>
                      <h2 style={{ margin: 0, fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 36, lineHeight: 0.97, letterSpacing: -1 }}>
                        {storedName ? `Hola,\n${storedName.split(' ')[0]}` : 'Bienvenido\nde vuelta'}
                      </h2>
                    </div>
                    <div style={{
                      width: 90, height: 90, borderRadius: '50%', background: '#93e1e8',
                      display: 'grid', placeItems: 'center', flexShrink: 0,
                      fontSize: 26, fontWeight: 600, color: '#1f2872',
                    }}>
                      {initials}
                    </div>
                  </div>

                  {/* Cedula field */}
                  <div style={{ marginBottom: 20 }}>
                    <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 6 }}>
                      Número de cédula{!storedHasCedula ? ' (opcional si activaste con código)' : ''}
                    </label>
                    <input
                      type="number"
                      value={loginCedula}
                      onChange={e => { setLoginCedula(e.target.value); setLoginError(''); }}
                      placeholder="Ej: 1234567890"
                      style={{ ...inputStyle }}
                    />
                  </div>

                  {/* PIN keypad */}
                  <p style={{ fontSize: 13, color: '#6b7280', textAlign: 'center', marginBottom: 12 }}>Ingresa tu PIN de 4 dígitos</p>
                  <PinKeypad value={loginPin} onChange={handleLoginPin} />

                  <AnimatePresence>
                    {loginError && (
                      <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                        style={{ color: '#ef4444', fontSize: 13, textAlign: 'center', marginTop: 12 }}>
                        {loginError}
                      </motion.p>
                    )}
                  </AnimatePresence>

                  <button
                    onClick={() => { clearStoredAccount(); setView('welcome'); }}
                    style={{ display: 'block', margin: '20px auto 0', fontSize: 13, color: '#b9bdd7', background: 'none', border: 'none', cursor: 'pointer' }}>
                    ¿No eres tú? Cambiar cuenta
                  </button>
                </article>
              </motion.div>
            )}

            {/* ══ IN-APP REGISTER ══ */}
            {view === 'in-app-register' && (
              <motion.div key="in-app-register" variants={slide} initial="enter" animate="center" exit="exit" transition={{ duration: 0.25 }}>
                <BackBtn onBack={() => { setView('welcome'); resetRegister(); }} />
                <article style={glassCard}>
                  <StepDots current={regStep - 1} total={4} />

                  {regStep === 1 && (
                    <motion.div key="s1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                      <h2 style={{ margin: '0 0 4px', fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 28 }}>
                        Información personal
                      </h2>
                      <p style={{ margin: '0 0 20px', color: '#6b7280', fontSize: 14 }}>Datos básicos para tu cuenta BBVA</p>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 20 }}>
                        <Field label="Nombre completo">
                          <input type="text" value={regName} onChange={e => setRegName(e.target.value)}
                            placeholder="Ej: Juan Pérez García" style={inputStyle} />
                        </Field>
                        <Field label="Número de cédula">
                          <input type="number" value={regCedula} onChange={e => setRegCedula(e.target.value)}
                            placeholder="Ej: 1234567890" style={inputStyle} />
                        </Field>
                        <Field label="Ingreso mensual aproximado">
                          <select value={regIncome} onChange={e => setRegIncome(e.target.value)}
                            style={{ ...inputStyle, color: regIncome ? '#0b1650' : '#9ca3af' }}>
                            <option value="" disabled>Selecciona un rango</option>
                            {INCOME_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                          </select>
                        </Field>
                      </div>
                      <PrimaryBtn onClick={() => setRegStep(2)} disabled={!regName.trim() || !regCedula.trim() || !regIncome}>
                        Continuar →
                      </PrimaryBtn>
                    </motion.div>
                  )}

                  {regStep === 2 && (
                    <motion.div key="s2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                      <h2 style={{ margin: '0 0 4px', fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 28 }}>Tu selfie</h2>
                      <PhotoStep
                        subtitle="Toma una foto de tu cara en un lugar con buena luz"
                        capture="user"
                        photo={selfiePhoto}
                        onPhoto={setSelfiePhoto}
                        onSimulate={() => setSelfiePhoto(DEMO_PHOTO)}
                      />
                      <div style={{ marginTop: 16 }}>
                        <PrimaryBtn onClick={() => setRegStep(3)} disabled={!selfiePhoto}>Continuar →</PrimaryBtn>
                      </div>
                    </motion.div>
                  )}

                  {regStep === 3 && (
                    <motion.div key="s3" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                      <h2 style={{ margin: '0 0 4px', fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 28 }}>Cédula — frontal</h2>
                      <PhotoStep
                        subtitle="Captura la parte delantera de tu cédula sobre una superficie plana"
                        capture="environment"
                        photo={idFrontPhoto}
                        onPhoto={setIdFrontPhoto}
                        onSimulate={() => setIdFrontPhoto(DEMO_PHOTO)}
                      />
                      <div style={{ marginTop: 16 }}>
                        <PrimaryBtn onClick={() => setRegStep(4)} disabled={!idFrontPhoto}>Continuar →</PrimaryBtn>
                      </div>
                    </motion.div>
                  )}

                  {regStep === 4 && (
                    <motion.div key="s4" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                      <h2 style={{ margin: '0 0 4px', fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 28 }}>Cédula — posterior</h2>
                      <PhotoStep
                        subtitle="Voltea la cédula y captura la parte trasera"
                        capture="environment"
                        photo={idBackPhoto}
                        onPhoto={setIdBackPhoto}
                        onSimulate={() => setIdBackPhoto(DEMO_PHOTO)}
                      />
                      <AnimatePresence>
                        {regError && (
                          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                            style={{ color: '#ef4444', fontSize: 13, textAlign: 'center', marginTop: 10 }}>
                            {regError}
                          </motion.p>
                        )}
                      </AnimatePresence>
                      <div style={{ marginTop: 16 }}>
                        <PrimaryBtn onClick={handleRegister} disabled={!idBackPhoto} loading={registering}>
                          {registering ? 'Creando cuenta...' : 'Crear mi cuenta'}
                        </PrimaryBtn>
                      </div>
                      <p style={{ fontSize: 11, textAlign: 'center', marginTop: 12, color: '#9ca3af' }}>
                        Al continuar aceptas nuestros Términos y Política de Privacidad
                      </p>
                    </motion.div>
                  )}
                </article>
              </motion.div>
            )}

            {/* ══ PIN SETUP ══ */}
            {view === 'pin-setup' && (
              <motion.div key="pin-setup" variants={slide} initial="enter" animate="center" exit="exit" transition={{ duration: 0.25 }}>
                <article style={{ ...glassCard, textAlign: 'center' }}>
                  <div style={{ width: 64, height: 64, borderRadius: 20, background: '#0a1fb8', margin: '0 auto 20px', display: 'grid', placeItems: 'center' }}>
                    <svg width={34} height={34} viewBox="0 0 24 24" fill="white">
                      <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z"/>
                    </svg>
                  </div>
                  <h2 style={{ margin: '0 0 8px', fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 32 }}>
                    {pinStep === 'create' ? 'Crea tu PIN' : 'Confirma tu PIN'}
                  </h2>
                  <p style={{ margin: '0 0 28px', color: '#6b7280', fontSize: 14 }}>
                    {pinStep === 'create' ? 'Elige 4 dígitos para acceder a tu cuenta' : 'Ingresa de nuevo el mismo PIN'}
                  </p>
                  <PinKeypad value={pinStep === 'create' ? pin : pinConfirm} onChange={handlePinInput} />
                  <AnimatePresence>
                    {pinError && (
                      <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                        style={{ color: '#ef4444', fontSize: 13, textAlign: 'center', marginTop: 16 }}>
                        {pinError}
                      </motion.p>
                    )}
                  </AnimatePresence>
                </article>
              </motion.div>
            )}

            {/* ══ CODE INPUT ══ */}
            {view === 'code-input' && (
              <motion.div key="code-input" variants={slide} initial="enter" animate="center" exit="exit" transition={{ duration: 0.25 }}>
                <BackBtn onBack={() => { setView('welcome'); setCode(''); setCodeError(''); }} />
                <article style={glassCard}>
                  <div style={{ width: 56, height: 56, borderRadius: 18, background: '#0a1fb8', marginBottom: 20, display: 'grid', placeItems: 'center' }}>
                    <svg width={30} height={30} viewBox="0 0 24 24" fill="white">
                      <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
                    </svg>
                  </div>
                  <h2 style={{ margin: '0 0 6px', fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 28 }}>Ingresa tu código</h2>
                  <p style={{ margin: '0 0 20px', color: '#9ca3af', fontSize: 14 }}>El código que recibiste al crear tu cuenta desde la web</p>
                  <input
                    type="text" value={code}
                    onChange={e => { setCode(e.target.value.toUpperCase()); setCodeError(''); }}
                    onKeyDown={e => e.key === 'Enter' && handleActivate()}
                    placeholder="HLP-XXXXXX" maxLength={10} autoFocus
                    style={{ ...inputStyle, textAlign: 'center', fontSize: 22, fontFamily: 'monospace', fontWeight: 700, letterSpacing: 4, border: `2px solid ${codeError ? '#ef4444' : '#e5e7eb'}`, marginBottom: 12 }}
                  />
                  <AnimatePresence>
                    {codeError && (
                      <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                        style={{ color: '#ef4444', fontSize: 13, textAlign: 'center', marginBottom: 12 }}>
                        {codeError}
                      </motion.p>
                    )}
                  </AnimatePresence>
                  <PrimaryBtn onClick={handleActivate} disabled={!code.trim()} loading={activating}>
                    {activating ? 'Verificando...' : 'Activar'}
                  </PrimaryBtn>
                </article>
              </motion.div>
            )}

          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
