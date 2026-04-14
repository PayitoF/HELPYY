import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const AGENT_CONFIG = {
  helpyy_general: {
    label: 'Helpyy Hand',
    color: 'bg-emerald-500',
    textColor: 'text-white',
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.94-.49-7-3.85-7-7.93 0-.62.08-1.22.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" />
      </svg>
    ),
  },
  credit_evaluator: {
    label: 'Microprestamos',
    color: 'bg-amber-500',
    textColor: 'text-white',
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z" />
      </svg>
    ),
  },
  financial_advisor: {
    label: 'Asesor Financiero',
    color: 'bg-emerald-600',
    textColor: 'text-white',
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z" />
      </svg>
    ),
  },
  onboarding: {
    label: 'Bienvenida',
    color: 'bg-blue-500',
    textColor: 'text-white',
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
      </svg>
    ),
  },
};

export default function AgentBadge({ agentType, size = 'sm' }) {
  const config = AGENT_CONFIG[agentType] || AGENT_CONFIG.helpyy_general;
  const sizeClasses = size === 'lg'
    ? 'px-3 py-1.5 text-sm gap-1.5'
    : 'px-2 py-0.5 text-xs gap-1';

  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={agentType}
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.8 }}
        transition={{ duration: 0.3 }}
        className={`inline-flex items-center rounded-full font-medium ${sizeClasses} ${config.color} ${config.textColor}`}
      >
        {config.icon}
        {config.label}
      </motion.span>
    </AnimatePresence>
  );
}
