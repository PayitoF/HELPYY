import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAgent } from '../contexts/AgentContext';
import AgentBadge from './AgentBadge';
import LoanApplicationForm from './LoanApplicationForm';
import LoanOfferCard from './LoanOfferCard';
import LoanContract from './LoanContract';

const API_ROOT = import.meta.env.VITE_API_URL || '';

function getGreeting(name) {
  const displayName = name ? name.split(' ')[0] : null;
  const saludo = displayName ? `¡Hola ${displayName}!` : '¡Hola!';
  return `${saludo} Soy Helpyy Hand, tu asistente personal. ` +
    'Puedo ayudarte con microprestamos, mejorar tu puntaje financiero y mucho mas. ¿En que te puedo ayudar?';
}

const BANKED_SUGGESTIONS = [
  'Quiero un microprestamo',
  'Mejorar mi puntaje',
  'Consultar productos',
];

const UNBANKED_SUGGESTIONS = [
  'Quiero abrir una cuenta',
  'Que es Helpyy Hand?',
  'Que beneficios tengo?',
];

export default function HelpyyPanel({ onClose }) {
  const {
    messages,
    setMessages,
    isStreaming,
    currentAgent,
    sendMessage,
    connect,
    isConnected,
    connectionState,
    userProfile,
    isBanked,
    sessionId,
  } = useAgent();

  const greeting = getGreeting(userProfile?.name);
  const suggestions = isBanked ? BANKED_SUGGESTIONS : UNBANKED_SUGGESTIONS;

  const [input, setInput] = useState('');
  const [activeTab, setActiveTab] = useState('chat');
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Loan flow state
  const [loanFlow, setLoanFlow] = useState(null);
  const [loanData, setLoanData] = useState(null);
  const [missions, setMissions] = useState([]);
  const [tabSparkle, setTabSparkle] = useState(false);

  useEffect(() => {
    connect();
  }, [connect]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  // Detect show_loan_form metadata — don't auto-open, let the button handle it
  const showLoanButton = messages[messages.length - 1]?.metadata?.show_loan_form && loanFlow === null;

  async function handleLoanSubmit(formData) {
    try {
      setLoanFlow(null);

      // Step 1: Show analyzing animation
      const steps = [
        '🔍 Analizando tu perfil financiero...',
        '📊 Consultando el modelo de riesgo...',
        '🧮 Calculando tu elegibilidad...',
      ];
      let si = 0;
      setMessages((prev) => [...prev, {
        role: 'assistant', agent: 'credit_evaluator', content: steps[0], _analyzing: true,
      }]);
      const iv = setInterval(() => {
        si++;
        if (si < steps.length) {
          setMessages((prev) => {
            const l = prev[prev.length - 1];
            return l?._analyzing ? [...prev.slice(0, -1), { ...l, content: steps[si] }] : prev;
          });
        }
      }, 1200);

      // Step 2: Call API
      const resp = await fetch(`${API_ROOT}/api/v1/scoring/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, ...formData }),
      });
      const data = await resp.json();
      clearInterval(iv);

      // Step 3: Show final step
      setMessages((prev) => {
        const l = prev[prev.length - 1];
        return l?._analyzing ? [...prev.slice(0, -1), {
          ...l, content: data.eligible ? '✅ ¡Resultado listo!' : '📋 Generando tu plan personalizado...',
        }] : prev;
      });
      await new Promise((r) => setTimeout(r, 1500));

      // Step 4: Remove animation, show result
      setMessages((prev) => prev.filter((m) => !m._analyzing));

      if (data.eligible) {
        setLoanData(data);
        setLoanFlow('offer');
      } else {
        setMissions(data.missions || []);
        setTabSparkle(true);
        const reasons = (data.rejection_reasons || []).join(', ') || 'tu perfil aún no cumple los requisitos';
        const amt = formData.requested_amount ? `$${(formData.requested_amount).toLocaleString('es-CO')}` : 'el monto solicitado';
        setMessages((prev) => [...prev, {
          role: 'assistant',
          agent: 'credit_evaluator',
          content: `Revisamos tu solicitud de ${amt} y por ahora aún no calificas para el microcrédito 😔\n\n📋 Razones: ${reasons}.\n\nPero no te preocupes — te creamos un plan con ${(data.missions || []).length} misiones concretas para mejorar tu perfil 🎯\n\n¿Quieres que nuestro asesor financiero te guíe paso a paso?`,
          suggestedActions: [],
          metadata: {
            show_advisor_prompt: true,
            user_data: { ...formData, p_default: data.p_default, score_band: data.score_band, rejection_reasons: data.rejection_reasons, improvement_factors: data.improvement_factors },
          },
        }]);
        // Don't auto-switch — let user click the tab
      }
    } catch {
      setLoanFlow(null);
    }
  }

  function handleSelectOption(option) {
    setLoanData((prev) => ({ ...prev, selectedOption: option }));
    setLoanFlow('contract');
  }

  async function handleAcceptLoan(option) {
    try {
      await fetch(`${API_ROOT}/api/v1/scoring/accept-loan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, loan_option: option }),
      });
    } catch { /* PoC — ignore */ }
    setLoanFlow('success');
    setTimeout(() => setLoanFlow(null), 5000);
  }

  function handleSend(text) {
    const msg = (text || input).trim();
    if (!msg || isStreaming) return;
    sendMessage(msg);
    setInput('');
    inputRef.current?.focus();
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const displayAgent = currentAgent || 'helpyy_general';

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* ─── Header ─── */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-700 px-4 pt-12 pb-3 flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
              <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.94-.49-7-3.85-7-7.93 0-.62.08-1.22.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" />
              </svg>
            </div>
            <div>
              <h2 className="text-white font-bold text-lg">Helpyy Hand</h2>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-blue-300 animate-pulse" />
                <span className="text-white/80 text-xs">
                  {connectionState === 'connected' ? 'En linea'
                    : connectionState === 'error' ? 'Error de conexion'
                    : connectionState === 'disconnected' ? 'Reconectando...'
                    : 'Conectando...'}
                </span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-white/15 flex items-center justify-center text-white hover:bg-white/25 transition-colors"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" />
            </svg>
          </button>
        </div>

        {/* Active agent badge */}
        <AgentBadge agentType={displayAgent} size="sm" />

        {/* Tabs */}
        <div className="flex gap-1 mt-3 bg-white/10 rounded-lg p-0.5">
          {['chat', ...(missions.length > 0 ? ['progreso'] : [])].map((tab) => (
            <button
              key={tab}
              onClick={() => { setActiveTab(tab); if (tab === 'progreso') setTabSparkle(false); }}
              className={`flex-1 py-1.5 rounded-md text-sm font-medium transition-all relative ${
                activeTab === tab
                  ? 'bg-white text-blue-800 shadow-sm'
                  : 'text-white/70 hover:text-white'
              }`}
            >
              {tab === 'chat' ? 'Chat' : '✨ Mi Progreso'}
              {tab === 'progreso' && tabSparkle && (
                <span className="absolute -top-1 -right-1 flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-300 opacity-75" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-yellow-400" />
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* ─── Chat Tab ─── */}
      {activeTab === 'chat' && (
        <>
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {/* Greeting — shows until the agent sends its first response */}
            {!messages.some((m) => m.role === 'assistant') && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <MessageBubble role="assistant" content={greeting} agent="helpyy_general" />
                <SuggestionChips actions={suggestions} onSelect={handleSend} />
              </motion.div>
            )}

            {/* Messages */}
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25 }}
              >
                {msg.role === 'system' ? (
                  <div className="text-center py-2">
                    <span className="text-xs text-gray-400 bg-gray-100 px-3 py-1 rounded-full">
                      {msg.content}
                    </span>
                  </div>
                ) : (
                  <>
                    <MessageBubble
                      role={msg.role}
                      content={msg.content}
                      agent={msg.agent}
                      streaming={msg._streaming}
                    />
                    {msg.suggestedActions?.length > 0 && (
                      <SuggestionChips actions={msg.suggestedActions} onSelect={handleSend} />
                    )}
                    {msg.metadata?.show_loan_form && loanFlow === null && (
                      <button
                        onClick={() => setLoanFlow('form')}
                        className="mt-2 w-full py-3 rounded-xl bg-blue-600 text-white font-semibold text-sm hover:bg-blue-700 active:scale-[0.98] transition-all"
                      >
                        📋 Completar solicitud de crédito
                      </button>
                    )}
                    {msg.metadata?.show_advisor_prompt && (
                      <div className="mt-3 flex gap-2">
                        <button
                          onClick={() => {
                            setActiveTab('chat');
                            const ud = msg.metadata.user_data || {};
                            const ctx = `Quiero hablar con el asesor financiero. Mis datos: ingreso $${(ud.declared_income||0).toLocaleString('es-CO')}, ${ud.employment_type||'informal'}, ${ud.age||''} años, ${ud.city_type||'urbano'}, ocupación: ${ud.occupation||''}. Pedí $${(ud.requested_amount||0).toLocaleString('es-CO')} de crédito pero no califiqué. Razones: ${(ud.rejection_reasons||[]).join(', ')}. Ayúdame a mejorar.`;
                            sendMessage(ctx);
                          }}
                          className="flex-1 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 transition-all"
                        >
                          Sí, quiero un asesor 💬
                        </button>
                        <button
                          onClick={() => setActiveTab('progreso')}
                          className="flex-1 py-2.5 rounded-xl border border-gray-300 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-all"
                        >
                          Ver mis misiones 📋
                        </button>
                      </div>
                    )}
                  </>
                )}
              </motion.div>
            ))}

            {/* Typing indicator */}
            <AnimatePresence>
              {isStreaming && !messages.some((m) => m._streaming) && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex items-center gap-1 py-2 px-3"
                >
                  <TypingDots />
                </motion.div>
              )}
            </AnimatePresence>

            <div ref={messagesEndRef} />
          </div>

          {/* ─── Loan Flow Overlay ─── */}
          <AnimatePresence>
            {loanFlow === 'form' && (
              <div className="overflow-y-auto max-h-[70vh] px-4 py-2">
                <LoanApplicationForm onSubmit={handleLoanSubmit} onCancel={() => setLoanFlow(null)} />
              </div>
            )}
            {loanFlow === 'offer' && loanData && (
              <div className="flex-shrink-0 px-4 py-2">
                <LoanOfferCard
                  maxAmount={loanData.max_amount}
                  options={loanData.options || []}
                  onSelectOption={handleSelectOption}
                  onCancel={() => setLoanFlow(null)}
                />
              </div>
            )}
            {loanFlow === 'contract' && loanData?.selectedOption && (
              <div className="flex-shrink-0 px-4 py-2">
                <LoanContract
                  loanOption={loanData.selectedOption}
                  conditions={loanData.contract_template?.conditions || loanData.conditions || []}
                  onAccept={handleAcceptLoan}
                  onCancel={() => setLoanFlow('offer')}
                />
              </div>
            )}
            {loanFlow === 'success' && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="flex-shrink-0 px-4 py-2">
                <div className="bg-white rounded-2xl border border-gray-100 shadow-md p-6 text-center">
                  <p className="text-3xl">✅</p>
                  <p className="text-sm font-bold text-blue-800 mt-2">¡Crédito aprobado exitosamente!</p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ─── Input Bar ─── */}
          <div className="flex-shrink-0 bg-white border-t border-gray-100 px-4 py-3 flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Escribe tu mensaje..."
              rows={1}
              className="flex-1 resize-none border border-gray-200 rounded-2xl px-4 py-2.5 text-sm outline-none focus:border-blue-400 transition-colors max-h-24 overflow-y-auto"
              style={{ height: 'auto', minHeight: '40px' }}
              onInput={(e) => {
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 96) + 'px';
              }}
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isStreaming}
              className="w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center text-white flex-shrink-0 disabled:bg-gray-300 disabled:cursor-not-allowed hover:bg-blue-700 active:scale-95 transition-all"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            </button>
          </div>
        </>
      )}

      {/* ─── Progress Tab ─── */}
      {activeTab === 'progreso' && <ProgressTab missions={missions} onCompleteMission={(idx) => {
        setMissions((prev) => prev.map((m, i) => i === idx ? { ...m, status: 'completed' } : m));
      }} />}
    </div>
  );
}

/* ═══ Sub-components ═══ */

function MessageBubble({ role, content, agent, streaming }) {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] px-3.5 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'bg-blue-600 text-white rounded-2xl rounded-br-md'
            : 'bg-white text-gray-800 rounded-2xl rounded-bl-md border border-gray-100 shadow-sm'
        }`}
      >
        {!isUser && agent && (
          <div className="mb-1">
            <AgentBadge agentType={agent} size="sm" />
          </div>
        )}
        <p className="whitespace-pre-wrap">{content}</p>
        {streaming && (
          <span className="inline-block w-1.5 h-4 bg-blue-400 rounded-sm animate-pulse ml-0.5 align-text-bottom" />
        )}
        <p className={`text-[10px] mt-1 ${isUser ? 'text-white/60 text-right' : 'text-gray-400'}`}>
          {new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  );
}

function SuggestionChips({ actions, onSelect }) {
  return (
    <div className="flex flex-wrap gap-1.5 mt-2 pl-1">
      {actions.map((text, i) => (
        <button
          key={i}
          onClick={() => onSelect(text)}
          className="px-3 py-1.5 text-xs font-medium border border-blue-400 text-blue-700 rounded-full bg-white hover:bg-blue-50 active:bg-blue-100 transition-colors"
        >
          {text}
        </button>
      ))}
    </div>
  );
}

function TypingDots() {
  return (
    <div className="bg-white border border-gray-100 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm inline-flex gap-1.5">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-2 h-2 rounded-full bg-gray-400"
          animate={{ y: [0, -6, 0] }}
          transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15, ease: 'easeInOut' }}
        />
      ))}
    </div>
  );
}

function ProgressTab({ missions = [], onCompleteMission }) {
  if (missions.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center px-6">
        <p className="text-sm text-gray-400 text-center">No tienes misiones activas. Solicita un préstamo para activar tu plan de mejora.</p>
      </div>
    );
  }

  const earned = missions.filter((m) => m.status === 'completed').reduce((s, m) => s + (m.points || 0), 0);
  const total = missions.reduce((s, m) => s + (m.points || 0), 0);
  const level = earned >= 300 ? 'Experto' : earned >= 150 ? 'Disciplinado' : earned >= 50 ? 'Aprendiz' : 'Principiante';

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {/* Level card */}
      <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-2xl p-5 text-white">
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-white/70 text-xs">Tu nivel</p>
            <h3 className="text-xl font-bold">{level}</h3>
          </div>
          <div className="w-14 h-14 rounded-full bg-white/20 flex items-center justify-center">
            <span className="text-2xl font-bold">{earned}</span>
          </div>
        </div>
        <div className="w-full bg-white/20 rounded-full h-2">
          <div
            className="h-full rounded-full bg-white transition-all duration-500"
            style={{ width: `${Math.min((earned / total) * 100, 100)}%` }}
          />
        </div>
        <p className="text-white/60 text-xs mt-2">{earned}/{total} puntos</p>
      </div>

      {/* Missions list */}
      <h3 className="text-sm font-semibold text-gray-600">Misiones activas</h3>
      <div className="space-y-2">
        {missions.map((m, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.08 }}
            className={`bg-white rounded-xl p-4 border ${m.status === 'completed' ? 'border-blue-200' : 'border-gray-100'} shadow-sm`}
          >
            <div className="flex items-start gap-3">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
                m.status === 'completed' ? 'bg-blue-600' : 'bg-gray-200'
              }`}>
                {m.status === 'completed' ? (
                  <svg className="w-3.5 h-3.5 text-white" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
                  </svg>
                ) : (
                  <span className="w-2 h-2 rounded-full bg-gray-400" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${m.status === 'completed' ? 'text-blue-800 line-through' : 'text-gray-800'}`}>
                  {m.title}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-gray-400">{m.factor}</span>
                  <span className="text-xs font-semibold text-blue-600">+{m.points} pts</span>
                  {m.status !== 'completed' && onCompleteMission && (
                    <button onClick={() => onCompleteMission(i)}
                      className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-semibold hover:bg-blue-200 transition-colors">
                      ✓ Completar
                    </button>
                  )}
                </div>
                {m.ml_suggestion && m.status !== 'completed' && (
                  <p className="text-[11px] text-gray-400 mt-1">{m.ml_suggestion}</p>
                )}
                {m.ml_current !== undefined && m.status !== 'completed' && (
                  <div className="mt-1.5 w-full bg-gray-100 rounded-full h-1.5">
                    <div className="h-full rounded-full bg-blue-400 transition-all"
                      style={{ width: `${Math.min((m.ml_current / m.ml_target) * 100, 100)}%` }} />
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
