import React, { useState } from 'react';
import { motion } from 'framer-motion';

const fmt = (n) => new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n);

export default function LoanOfferCard({ maxAmount, options = [], onSelectOption, onCancel }) {
  const [selected, setSelected] = useState(null);

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      className="bg-white rounded-2xl border border-gray-100 shadow-md p-4 space-y-4">

      <div className="text-center">
        <p className="text-2xl">🎉</p>
        <h3 className="text-sm font-bold text-blue-800">¡Felicidades! Estás pre-aprobado</h3>
        <p className="text-2xl font-bold text-blue-700 mt-1">{fmt(maxAmount)}</p>
        <p className="text-xs text-gray-500">Monto máximo aprobado</p>
      </div>

      <div className="space-y-2">
        {options.map((opt, i) => (
          <motion.button key={i}
            initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.1 }}
            onClick={() => setSelected(i)}
            className={`w-full text-left p-3 rounded-xl border-2 transition-all ${
              selected === i ? 'border-blue-600 bg-blue-50' : 'border-gray-100 bg-gray-50'
            }`}>
            <div className="flex justify-between items-center">
              <span className="text-sm font-bold text-gray-800">{opt.term_months} meses</span>
              <span className="text-sm font-bold text-blue-700">{fmt(opt.monthly_payment)}/mes</span>
            </div>
            <div className="flex gap-3 mt-1 text-xs text-gray-500">
              <span>Interés total: {fmt(opt.total_interest || 0)}</span>
              <span>TEA: {opt.tea || 0}%</span>
            </div>
          </motion.button>
        ))}
      </div>

      <div className="flex gap-2">
        <button onClick={onCancel} className="flex-1 py-2.5 rounded-xl border border-gray-300 text-sm font-medium text-gray-600">
          Cancelar
        </button>
        <button onClick={() => selected !== null && onSelectOption(options[selected])}
          disabled={selected === null}
          className="flex-1 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-bold disabled:bg-gray-300">
          Solicitar mi crédito
        </button>
      </div>
    </motion.div>
  );
}
