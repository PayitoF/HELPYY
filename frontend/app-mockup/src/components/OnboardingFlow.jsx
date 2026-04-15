import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function OnboardingFlow({ onActivate, onDismiss }) {
  const [step, setStep] = useState('modal'); // modal → activating → done
  const [confetti, setConfetti] = useState([]);

  function handleActivate() {
    setStep('activating');
    // Spawn confetti
    const dots = Array.from({ length: 30 }, (_, i) => ({
      id: i,
      x: (Math.random() - 0.5) * 200,
      y: (Math.random() - 0.5) * 200 - 60,
      color: ['#0727b5', '#1a3fd1', '#fbbf24', '#ef4444', '#3b82f6', '#8b5cf6'][i % 6],
      delay: Math.random() * 0.3,
    }));
    setConfetti(dots);

    setTimeout(() => {
      setStep('done');
      onActivate();
    }, 2000);
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      >
        {step === 'modal' && (
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', damping: 20 }}
            className="bg-white rounded-2xl p-8 mx-6 max-w-sm w-full text-center shadow-2xl"
          >
            {/* Helpyy icon */}
            <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-gradient-to-br from-blue-400 to-indigo-700 flex items-center justify-center shadow-lg shadow-blue-600/30">
              <svg className="w-10 h-10 text-white" viewBox="0 0 24 24" fill="currentColor">
                <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z" />
                <path d="M7 9h10v2H7zm0-3h10v2H7zm0 6h7v2H7z" />
              </svg>
            </div>

            <h2 className="text-xl font-bold text-gray-800 mb-2">
              Tu cuenta ha sido creada
            </h2>
            <p className="text-gray-500 text-sm mb-6 leading-relaxed">
              Activa <span className="font-semibold text-blue-700">Helpyy Hand</span>,
              tu asistente personal que te acompaña en tu camino financiero.
              Te ayuda con microprestamos, tips y mucho mas.
            </p>

            <button
              onClick={handleActivate}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-blue-400 to-indigo-700 text-white font-semibold text-base shadow-lg shadow-blue-600/25 hover:shadow-blue-600/40 transition-shadow active:scale-[0.98]"
            >
              Activar Helpyy Hand
            </button>
            <button
              onClick={onDismiss}
              className="mt-3 text-sm text-gray-400 hover:text-gray-600 transition-colors"
            >
              Ahora no
            </button>
          </motion.div>
        )}

        {step === 'activating' && (
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="relative flex items-center justify-center"
          >
            {/* Confetti burst */}
            {confetti.map((dot) => (
              <motion.div
                key={dot.id}
                initial={{ x: 0, y: 0, scale: 1, opacity: 1 }}
                animate={{ x: dot.x, y: dot.y, scale: 0, opacity: 0 }}
                transition={{ duration: 0.8, delay: dot.delay, ease: 'easeOut' }}
                className="absolute w-2 h-2 rounded-full"
                style={{ backgroundColor: dot.color }}
              />
            ))}

            {/* Central check */}
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: [0, 1.2, 1] }}
              transition={{ duration: 0.5, times: [0, 0.6, 1] }}
              className="w-24 h-24 rounded-full bg-gradient-to-br from-blue-400 to-indigo-700 flex items-center justify-center shadow-2xl"
            >
              <svg className="w-12 h-12 text-white" viewBox="0 0 24 24" fill="currentColor">
                <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
              </svg>
            </motion.div>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6 }}
              className="absolute top-full mt-6 text-white font-semibold text-lg"
            >
              Helpyy Hand activado
            </motion.p>
          </motion.div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
