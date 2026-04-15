import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const fmt = (n) => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n);

export default function LoanContract({ loanOption, conditions = [], onAccept, onCancel }) {
  const [accepted, setAccepted] = useState(false);
  const [success, setSuccess] = useState(false);

  if (success) {
    return (
      <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        className="bg-white rounded-2xl border border-gray-100 shadow-md p-6 text-center space-y-3">
        <div className="text-5xl">🎊</div>
        <h3 className="text-lg font-bold text-blue-800">¡Desembolso aprobado!</h3>
        <p className="text-sm text-gray-600">El dinero estará en tu cuenta en 24 horas</p>
        {/* Confetti dots */}
        <div className="relative h-8 overflow-hidden">
          {Array.from({ length: 12 }).map((_, i) => (
            <motion.span key={i}
              className="absolute w-2 h-2 rounded-full"
              style={{ left: `${8 + i * 8}%`, background: ['#0727b5', '#1a3fd1', '#fbbf24', '#34d399'][i % 4] }}
              initial={{ y: 0, opacity: 1 }} animate={{ y: [0, -20, 30], opacity: [1, 1, 0] }}
              transition={{ duration: 1.2, delay: i * 0.08 }}
            />
          ))}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      className="bg-white rounded-2xl border border-gray-100 shadow-md p-4 space-y-3">

      <h3 className="text-sm font-bold text-blue-800 text-center">📄 Contrato de Microcrédito BBVA</h3>

      <div className="max-h-64 overflow-y-auto bg-gray-50 rounded-xl p-3 text-xs text-gray-700 space-y-2 border border-gray-200">
        <p><strong>Monto:</strong> {fmt(loanOption.amount || loanOption.monthly_payment * loanOption.term_months)}</p>
        <p><strong>Plazo:</strong> {loanOption.term_months} meses</p>
        <p><strong>Cuota mensual:</strong> {fmt(loanOption.monthly_payment)}</p>
        <p><strong>TEA:</strong> {loanOption.tea}%</p>

        {conditions.length > 0 && (
          <>
            <p className="font-bold mt-2">Condiciones:</p>
            <ul className="list-disc pl-4 space-y-1">
              {conditions.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </>
        )}

        <p className="mt-2 text-gray-400 leading-relaxed">
          El presente contrato se rige por las disposiciones de la Superintendencia Financiera de Colombia.
          El cliente acepta las condiciones de tasa, plazo y cuota aquí establecidas. En caso de mora,
          se aplicarán los intereses moratorios vigentes conforme a la regulación colombiana.
          BBVA Colombia se reserva el derecho de verificar la información suministrada.
        </p>
      </div>

      <label className="flex items-start gap-2 cursor-pointer">
        <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)}
          className="mt-0.5 accent-blue-600" />
        <span className="text-xs text-gray-600">He leído y acepto los términos y condiciones del crédito</span>
      </label>

      <div className="flex gap-2">
        <button onClick={onCancel} className="flex-1 py-2.5 rounded-xl border border-gray-300 text-sm font-medium text-gray-600">
          Cancelar
        </button>
        <button onClick={() => { setSuccess(true); setTimeout(() => onAccept(loanOption), 3000); }}
          disabled={!accepted}
          className="flex-1 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-bold disabled:bg-gray-300">
          Firmar y aceptar
        </button>
      </div>
    </motion.div>
  );
}
