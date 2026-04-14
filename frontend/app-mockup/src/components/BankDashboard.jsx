import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAgent } from '../contexts/AgentContext';
import HelpyyPanel from './HelpyyPanel';
import OnboardingFlow from './OnboardingFlow';
import NotificationBell from './NotificationBell';

function getInitials(name) {
  if (!name) return '?';
  const parts = name.trim().split(' ').filter(Boolean);
  return parts.length >= 2
    ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    : parts[0].slice(0, 2).toUpperCase();
}

/* ─── SVG Icons ─── */
const Icons = {
  transfer: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
    </svg>
  ),
  pay: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
    </svg>
  ),
  breb: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
    </svg>
  ),
  withdrawal: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
    </svg>
  ),
  helpyy: (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
      <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z" />
      <path d="M7 9h10v2H7zm0-3h10v2H7zm0 6h7v2H7z" />
    </svg>
  ),
  home: (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
      <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" />
    </svg>
  ),
  operate: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
    </svg>
  ),
  contract: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  ),
  bell: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
    </svg>
  ),
  help: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  eye: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
    </svg>
  ),
  eyeOff: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
    </svg>
  ),
  menu: (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
      <path d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/>
    </svg>
  ),
  qr: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z" />
    </svg>
  ),
};

/* BBVA-style avatar color pool — matches the app's circle initials */
const AVATAR_COLORS = ['#4ecdc4', '#45b7d1', '#96ceb4', '#88d8b0', '#6c5ce7', '#fdcb6e'];
function getAvatarColor(name) {
  if (!name) return AVATAR_COLORS[0];
  const idx = name.charCodeAt(0) % AVATAR_COLORS.length;
  return AVATAR_COLORS[idx];
}

const MOCK_TRANSACTIONS = [
  { name: 'Transferencia a Maria L.', amount: '-$150.000', date: 'Hoy, 2:34 PM', negative: true },
  { name: 'Deposito nomina', amount: '+$1.800.000', date: 'Abr 5, 9:00 AM', negative: false },
  { name: 'Pago Claro movil', amount: '-$45.000', date: 'Abr 4, 11:22 AM', negative: true },
  { name: 'Bre-B recibido', amount: '+$80.000', date: 'Abr 3, 3:15 PM', negative: false },
];

export default function BankDashboard() {
  const {
    helpyyActive,
    showActivationModal,
    helpyyPanelOpen,
    unreadCount,
    userProfile,
    isFreshAccount,
    activateHelpyy,
    triggerActivation,
    setHelpyyPanelOpen,
    setShowActivationModal,
    logout,
  } = useAgent();

  const [drawerOpen, setDrawerOpen] = useState(false);

  const displayName = userProfile?.name || 'Usuario';
  const firstName = displayName.split(' ')[0];
  const lastName = displayName.split(' ').slice(1).join(' ');
  const avatarInitials = getInitials(displayName);
  const avatarColor = getAvatarColor(displayName);

  // Balance and transactions depend on whether this is a brand-new account
  const balance = isFreshAccount ? 0 : 1245800;
  const transactions = isFreshAccount ? [] : MOCK_TRANSACTIONS;
  const accountLastFour = isFreshAccount
    ? (userProfile?.accountId?.slice(-4) || '0000')
    : '4521';

  const [balanceVisible, setBalanceVisible] = useState(true);

  const quickActions = [
    { icon: Icons.transfer, label: 'Transferir' },
    { icon: Icons.pay, label: 'Pagar servicios' },
    { icon: Icons.breb, label: 'Bre-B' },
    { icon: Icons.withdrawal, label: 'Retiro sin tarjeta' },
  ];

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      {/* Phone frame */}
      <div
        className="w-[390px] overflow-hidden shadow-2xl flex flex-col relative"
        style={{ borderRadius: 38, height: 844, boxShadow: '0 24px 60px rgba(8, 20, 93, 0.18)', background: '#dfe7f5' }}
      >

        {/* ─── Sky gradient header area ─── */}
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 260,
          background: 'linear-gradient(180deg, #7fb3e7 0%, #78aee4 70%, #dfe7f2 100%)',
          zIndex: 0, overflow: 'hidden',
        }}>
          {/* City left */}
          <div style={{ position: 'absolute', bottom: 0, left: -4, width: 160, height: 160,
            background: `linear-gradient(90deg, #b18d79 0 2%, transparent 2% 20%, #f0e6de 20% 72%, #b58e77 72% 74%, transparent 74% 100%)`,
            clipPath: 'polygon(0 30%, 18% 28%, 18% 12%, 31% 8%, 33% 0, 37% 0, 39% 8%, 54% 12%, 54% 28%, 100% 25%, 100% 100%, 0 100%)',
            opacity: 0.9 }} />
          {/* City right */}
          <div style={{ position: 'absolute', bottom: 0, right: -4, width: 110, height: 160,
            background: 'linear-gradient(180deg, #7a4b3c 0 12%, #925843 12% 14%, transparent 14% 100%)',
            clipPath: 'polygon(0 22%, 24% 0, 100% 16%, 100% 100%, 0 100%)',
            opacity: 0.9 }} />
        </div>

        {/* ─── Status bar ─── */}
        <div
          className="flex items-center justify-between px-6 pt-6 pb-2 flex-shrink-0"
          style={{ position: 'relative', zIndex: 2 }}
        >
          <span style={{ color: '#08145d', fontSize: 17, fontWeight: 700 }}>
            {new Date().getHours().toString().padStart(2,'0')}:{new Date().getMinutes().toString().padStart(2,'0')}
          </span>
          <div className="flex items-center gap-1.5">
            <svg className="w-4 h-3" viewBox="0 0 17 12" fill="#08145d">
              <rect x="0" y="3" width="3" height="9" rx="1" opacity="0.4"/>
              <rect x="4.5" y="2" width="3" height="10" rx="1" opacity="0.6"/>
              <rect x="9" y="0.5" width="3" height="11.5" rx="1"/>
            </svg>
          </div>
        </div>

        {/* ─── Header with BBVA logo ─── */}
        <div
          className="flex items-center justify-between px-6 pb-2 flex-shrink-0"
          style={{ position: 'relative', zIndex: 2 }}
        >
          <button
            onClick={() => setDrawerOpen(true)}
            className="w-16 h-16 rounded-full flex items-center justify-center text-white"
            style={{ background: '#081468', boxShadow: '0 10px 24px rgba(8, 20, 104, 0.18)', flexShrink: 0 }}
          >
            <div style={{ position: 'relative', width: 26, height: 18 }}>
              {[0, 9, 18].map(t => (
                <div key={t} style={{ position: 'absolute', left: 0, right: 0, top: t, height: 3, borderRadius: 3, background: '#c9dafd' }} />
              ))}
            </div>
          </button>

          {/* BBVA logo centered */}
          <h1 style={{ color: 'white', fontSize: 48, fontWeight: 500, letterSpacing: 2, margin: 0, lineHeight: 1 }}>BBVA</h1>

          {/* Notification bell */}
          <div className="relative">
            <NotificationBell />
          </div>
        </div>

        {/* ─── Welcome card (glass) ─── */}
        <div className="px-4 pt-2 pb-3 flex-shrink-0" style={{ position: 'relative', zIndex: 2 }}>
          <div style={{
            background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(8px)',
            borderRadius: 30, padding: '28px 24px 24px',
            boxShadow: '0 14px 28px rgba(10, 29, 110, 0.08)',
          }}>
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <motion.h2
                  key={displayName}
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  style={{ margin: 0, fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 38, lineHeight: 0.97, letterSpacing: -1.2 }}
                >
                  Hola {firstName}
                  {lastName && <><br />{lastName}</>}
                </motion.h2>
                <button
                  onClick={logout}
                  style={{ display: 'inline-block', marginTop: 18, color: '#0a21b4', fontSize: 16, fontWeight: 700, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  Cambiar usuario
                </button>
              </div>

              {/* Avatar */}
              <div
                className="rounded-full flex items-center justify-center text-white font-bold flex-shrink-0"
                style={{ width: 90, height: 90, background: avatarColor, fontSize: 28 }}
              >
                {avatarInitials}
              </div>
            </div>

            {/* Balance row */}
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid rgba(201,204,224,0.5)' }}>
              <div className="flex items-center justify-between">
                <div>
                  <p style={{ fontSize: 12, marginBottom: 4, color: '#9ca3af' }}>
                    Saldo disponible · Libreton ****{accountLastFour}
                  </p>
                  <AnimatePresence mode="wait">
                    {balanceVisible ? (
                      <motion.p key="v" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        style={{ fontSize: 24, fontWeight: 700, color: '#08145d', margin: 0 }}>
                        ${balance.toLocaleString('es-CO')}
                      </motion.p>
                    ) : (
                      <motion.p key="h" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        style={{ fontSize: 24, fontWeight: 700, letterSpacing: 6, color: '#08145d', margin: 0 }}>
                        ••••••
                      </motion.p>
                    )}
                  </AnimatePresence>
                </div>
                <button
                  onClick={() => setBalanceVisible(!balanceVisible)}
                  className="ml-3 flex-shrink-0"
                  style={{ color: '#9ca3af', background: 'none', border: 'none', cursor: 'pointer' }}
                >
                  {balanceVisible ? Icons.eye : Icons.eyeOff}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ─── Body (scrollable) ─── */}
        <div className="flex-1 overflow-y-auto pb-20" style={{ background: '#dfe7f5', position: 'relative', zIndex: 1 }}>

          {/* Quick actions */}
          <div style={{ background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(8px)', borderRadius: 30, margin: '0 14px 12px', padding: '20px 16px' }}>
            <h2 className="text-sm font-semibold mb-3" style={{ color: '#374151' }}>Acciones rápidas</h2>
            <div className="flex justify-between items-start gap-1">
              {quickActions.map((action, i) => (
                <button key={i} className="flex flex-col items-center gap-2 flex-1">
                  <div
                    className="w-12 h-12 rounded-full flex items-center justify-center"
                    style={{ background: '#f0f4ff', color: '#1464a0' }}
                  >
                    {action.icon}
                  </div>
                  <span className="text-[10px] text-center leading-tight" style={{ color: '#6b7280' }}>
                    {action.label}
                  </span>
                </button>
              ))}

              {/* Helpyy Hand button */}
              <AnimatePresence>
                {helpyyActive ? (
                  <motion.button
                    initial={{ scale: 0, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ type: 'spring', damping: 12, delay: 0.2 }}
                    onClick={() => setHelpyyPanelOpen(true)}
                    className="flex flex-col items-center gap-2 flex-1"
                  >
                    <div className="w-12 h-12 rounded-full flex items-center justify-center text-white shadow-md"
                      style={{ background: 'linear-gradient(135deg, #00a870, #007a52)' }}>
                      {Icons.helpyy}
                    </div>
                    <span className="text-[10px] text-center font-semibold leading-tight" style={{ color: '#00a870' }}>
                      Helpyy
                    </span>
                  </motion.button>
                ) : (
                  <button
                    onClick={triggerActivation}
                    className="flex flex-col items-center gap-2 flex-1"
                  >
                    <div className="w-12 h-12 rounded-full flex items-center justify-center"
                      style={{ background: '#f3f4f6', color: '#d1d5db' }}>
                      {Icons.helpyy}
                    </div>
                    <span className="text-[10px] text-center leading-tight" style={{ color: '#9ca3af' }}>
                      Activar
                    </span>
                  </button>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Pagos rápidos section (contact circles) */}
          <div style={{ background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(8px)', borderRadius: 30, margin: '0 14px 12px', padding: '20px 16px', minHeight: 200 }}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold" style={{ color: '#374151' }}>Pagos rápidos</h2>
              <div className="flex items-center gap-1" style={{ color: '#1464a0' }}>
                {Icons.qr}
                <span className="text-xs">Envía y recibe al instante</span>
              </div>
            </div>
            <div className="flex gap-3 overflow-x-auto pb-1">
              {[
                { initials: '+', label: 'Nuevo', color: '#e0f2fe', text: '#1464a0' },
                { initials: 'JA', label: 'Jose Alfonso', color: '#a855f7', text: 'white' },
                { initials: 'FF', label: 'Fabian F.', color: '#f59e0b', text: 'white' },
                { initials: 'MA', label: 'Magal Asoc.', color: '#4ecdc4', text: 'white' },
                { initials: 'CM', label: 'Camilo M.', color: '#f97316', text: 'white' },
              ].map((contact, i) => (
                <button key={i} className="flex flex-col items-center gap-1.5 flex-shrink-0">
                  <div
                    className="w-12 h-12 rounded-full flex items-center justify-center text-sm font-bold"
                    style={{ background: contact.color, color: contact.text }}
                  >
                    {contact.initials}
                  </div>
                  <span className="text-[10px] text-center" style={{ color: '#6b7280', maxWidth: 52 }}>
                    {contact.label}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Accounts section */}
          <div style={{ background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(8px)', borderRadius: 30, margin: '0 14px 12px', padding: '20px 16px' }}>
            <h2 className="text-sm font-semibold mb-3" style={{ color: '#374151' }}>Mis cuentas</h2>

            {/* Savings account */}
            <div
              className="rounded-2xl p-4 mb-3"
              style={{ background: 'linear-gradient(135deg, #072146, #1464a0)' }}
            >
              <div className="flex justify-between items-center">
                <div>
                  <p className="text-xs mb-0.5" style={{ color: 'rgba(255,255,255,0.6)' }}>Cuenta de Ahorro</p>
                  <p className="text-sm font-medium text-white">Libreton **** {accountLastFour}</p>
                </div>
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center"
                  style={{ background: 'rgba(255,255,255,0.15)' }}
                >
                  <svg viewBox="0 0 24 24" className="w-5 h-5" fill="white">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 16.09V20h-2.67v-1.93c-1.71-.36-3.16-1.46-3.27-3.4h1.96c.1 1.05.82 1.87 2.65 1.87 1.96 0 2.4-.98 2.4-1.59 0-.83-.44-1.61-2.67-2.14-2.48-.6-4.18-1.62-4.18-3.67 0-1.72 1.39-2.84 3.11-3.21V4h2.67v1.95c1.86.45 2.79 1.86 2.85 3.39H14.3c-.05-1.11-.64-1.87-2.22-1.87-1.5 0-2.4.68-2.4 1.64 0 .84.65 1.39 2.67 1.91s4.18 1.39 4.18 3.91c-.01 1.83-1.38 2.83-3.12 3.16z"/>
                  </svg>
                </div>
              </div>
            </div>

            {/* Microprestamo card (only if helpyy active) */}
            <AnimatePresence>
              {helpyyActive && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div
                    className="rounded-2xl p-4 mb-3"
                    style={{ border: '1.5px solid #a7f3d0', background: '#f0fdf4' }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-6 h-6 rounded-full flex items-center justify-center"
                        style={{ background: '#00a870' }}>
                        <svg className="w-3 h-3 text-white" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z" />
                        </svg>
                      </div>
                      <span className="text-sm font-semibold" style={{ color: '#065f46' }}>Microprestamo Helpyy</span>
                    </div>
                    <div className="w-full rounded-full h-1.5 mb-1" style={{ background: '#bbf7d0' }}>
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: '65%' }}
                        transition={{ duration: 1, delay: 0.5 }}
                        className="h-full rounded-full"
                        style={{ background: '#00a870' }}
                      />
                    </div>
                    <div className="flex justify-between text-xs" style={{ color: '#059669' }}>
                      <span>65% hacia tu primer préstamo</span>
                      <span>3 misiones</span>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Recent transactions */}
          <div style={{ background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(8px)', borderRadius: 30, margin: '0 14px', padding: '20px 16px' }}>
            <h2 className="text-sm font-semibold mb-3" style={{ color: '#374151' }}>Movimientos recientes</h2>
            {transactions.length === 0 ? (
              <div className="flex flex-col items-center py-8" style={{ color: '#9ca3af' }}>
                <svg className="w-10 h-10 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                <p className="text-sm font-medium" style={{ color: '#6b7280' }}>Sin movimientos aún</p>
                <p className="text-xs mt-1 text-center">Tus transacciones aparecerán aquí</p>
              </div>
            ) : (
              transactions.map((tx, i) => (
                <div key={i} className="flex items-center justify-between py-3" style={{
                  borderBottom: i < transactions.length - 1 ? '1px solid #f3f4f6' : 'none'
                }}>
                  <div className="flex items-center gap-3">
                    <div
                      className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
                      style={{ background: tx.negative ? '#fff1f2' : '#f0fdf4' }}
                    >
                      <svg className="w-4 h-4" viewBox="0 0 24 24" fill={tx.negative ? '#f87171' : '#34d399'}>
                        {tx.negative
                          ? <path d="M7 14l5-5 5 5H7z"/>
                          : <path d="M7 10l5 5 5-5H7z"/>
                        }
                      </svg>
                    </div>
                    <div>
                      <p className="text-sm font-medium" style={{ color: '#111827' }}>{tx.name}</p>
                      <p className="text-xs" style={{ color: '#9ca3af' }}>{tx.date}</p>
                    </div>
                  </div>
                  <span className="text-sm font-semibold" style={{ color: tx.negative ? '#ef4444' : '#059669' }}>
                    {tx.amount}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ─── Bottom Navigation ─── */}
        <div
          className="absolute bottom-0 left-0 right-0 px-2 pb-6 pt-2 flex-shrink-0"
          style={{ background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(12px)', borderTop: '1px solid rgba(201,204,224,0.4)', zIndex: 10 }}
        >
          <div className="flex justify-around items-center">
            {[
              { icon: Icons.home, label: 'Inicio', active: true },
              { icon: Icons.operate, label: 'Opera', active: false },
              { icon: Icons.contract, label: 'Contrata', active: false },
              { label: 'Notificaciones', active: false, isBell: true },
              { icon: Icons.help, label: 'Ayuda', active: false },
            ].map((item, i) => (
              <button
                key={i}
                className="flex flex-col items-center gap-0.5 px-3 py-1"
                style={{ color: item.active ? '#1464a0' : '#9ca3af' }}
              >
                {item.isBell ? (
                  <div className="relative">
                    {Icons.bell}
                    {unreadCount > 0 && (
                      <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-red-500 text-white text-[8px] font-bold rounded-full flex items-center justify-center">
                        {unreadCount > 9 ? '9+' : unreadCount}
                      </span>
                    )}
                  </div>
                ) : item.icon}
                <span className="text-[9px]">{item.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ─── Helpyy Panel Overlay ─── */}
        <AnimatePresence>
          {helpyyPanelOpen && (
            <motion.div
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="absolute inset-0 z-40"
            >
              <HelpyyPanel onClose={() => setHelpyyPanelOpen(false)} />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ─── Activation Modal ─── */}
        {showActivationModal && (
          <OnboardingFlow
            onActivate={activateHelpyy}
            onDismiss={() => setShowActivationModal(false)}
          />
        )}

        {/* ─── Side Drawer ─── */}
        <AnimatePresence>
          {drawerOpen && (
            <>
              {/* Backdrop */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setDrawerOpen(false)}
                style={{ position: 'absolute', inset: 0, background: 'rgba(10, 29, 129, 0.72)', zIndex: 30 }}
              />
              {/* Drawer panel */}
              <motion.aside
                initial={{ x: '100%' }}
                animate={{ x: 0 }}
                exit={{ x: '100%' }}
                transition={{ type: 'spring', damping: 28, stiffness: 300 }}
                style={{
                  position: 'absolute', top: 0, right: 0, width: 300, height: '100%',
                  background: 'rgba(255,255,255,0.985)', borderRadius: '36px 0 0 36px',
                  boxShadow: '-18px 0 32px rgba(8, 20, 93, 0.12)',
                  padding: '100px 28px 30px', zIndex: 31,
                  display: 'flex', flexDirection: 'column',
                }}
              >
                {/* Drawer header */}
                <div style={{ marginBottom: 32 }}>
                  <h2 style={{ margin: 0, fontFamily: 'Georgia, "Times New Roman", serif', color: '#08145d', fontSize: 30, lineHeight: 1.02, letterSpacing: -0.8 }}>
                    {displayName}
                  </h2>
                  <p style={{ margin: '8px 0 0', color: '#b9bdd7', fontSize: 18, fontWeight: 700 }}>Perfil</p>
                </div>

                {/* Menu items */}
                <nav style={{ display: 'flex', flexDirection: 'column', gap: 24, flex: 1 }}>
                  {[
                    { icon: '⬡', label: 'Configuración', active: false },
                    { icon: '◫', label: 'Seguridad y privacidad', active: true },
                    { icon: '◧', label: 'Pagar servicios', active: false },
                    { icon: '▦', label: 'Usar QR', active: true },
                    { icon: '◔', label: 'Operaciones favoritas', active: false },
                  ].map((item, i) => (
                    <button key={i} style={{
                      display: 'grid', gridTemplateColumns: '34px 1fr', gap: 16, alignItems: 'center',
                      background: 'none', border: 'none', cursor: 'pointer',
                      fontSize: 18, fontWeight: 700, lineHeight: 1.15, textAlign: 'left',
                      color: item.active ? '#0818aa' : '#c9cce0',
                    }}>
                      <span style={{ fontSize: 26, textAlign: 'center' }}>{item.icon}</span>
                      <span>{item.label}</span>
                    </button>
                  ))}
                </nav>

                {/* Logout button */}
                <button
                  onClick={() => { setDrawerOpen(false); logout(); }}
                  style={{
                    width: '100%', padding: '16px', borderRadius: 18,
                    background: '#0818aa', color: 'white', border: 'none', cursor: 'pointer',
                    fontSize: 17, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                  }}>
                  <svg width={20} height={20} fill="none" stroke="white" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                  </svg>
                  Cerrar sesión
                </button>
              </motion.aside>
            </>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
