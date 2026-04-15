import React, { useState } from 'react';
import { motion } from 'framer-motion';

const INCOME_OPTIONS = [
  { label: 'Menos de $500K', value: 300000 },
  { label: '$500K – $1M', value: 750000 },
  { label: '$1M – $1.5M', value: 1250000 },
  { label: '$1.5M – $2M', value: 1750000 },
  { label: 'Más de $2M', value: 2500000 },
];

const FIELDS = {
  employment_type: ['Informal', 'Formal', 'Independiente'],
  city_type: ['Urbana', 'Rural'],
  occupation: ['Vendedor ambulante', 'Trabajador doméstico', 'Conductor', 'Comerciante', 'Otro'],
  loan_purpose: ['Capital de trabajo', 'Emergencia', 'Educación', 'Mejora de vivienda'],
};

const selectCls = 'w-full rounded-xl bg-gray-100 border-2 border-gray-200 px-4 py-3 text-sm outline-none focus:border-blue-400';
const labelCls = 'text-xs font-semibold text-gray-500';

export default function LoanApplicationForm({ onSubmit, onCancel }) {
  const [form, setForm] = useState({
    monthly_income: '', employment_type: '', age: '', city_type: '',
    occupation: '', dependents: '0', has_other_credits: false, loan_purpose: '',
  });

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const valid = form.monthly_income && form.employment_type && form.age >= 18 && form.city_type && form.occupation && form.loan_purpose;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      className="bg-white rounded-2xl border border-gray-100 shadow-md p-4 space-y-3"
    >
      <h3 className="text-sm font-bold text-blue-800">📋 Solicitud de Microcrédito</h3>

      <div className="space-y-2.5">
        <label className={labelCls}>Ingreso mensual</label>
        <select value={form.monthly_income} onChange={(e) => set('monthly_income', Number(e.target.value))} className={selectCls}>
          <option value="">Selecciona</option>
          {INCOME_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        <label className={labelCls}>Tipo de empleo</label>
        <select value={form.employment_type} onChange={(e) => set('employment_type', e.target.value)} className={selectCls}>
          <option value="">Selecciona</option>
          {FIELDS.employment_type.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>

        <div className="flex gap-3">
          <div className="flex-1">
            <label className={labelCls}>Edad</label>
            <input type="number" min={18} max={100} value={form.age} onChange={(e) => set('age', e.target.value)}
              placeholder="18" className={selectCls} />
          </div>
          <div className="flex-1">
            <label className={labelCls}>Personas a cargo</label>
            <input type="number" min={0} max={10} value={form.dependents} onChange={(e) => set('dependents', e.target.value)}
              placeholder="0" className={selectCls} />
          </div>
        </div>

        <label className={labelCls}>Ciudad</label>
        <select value={form.city_type} onChange={(e) => set('city_type', e.target.value)} className={selectCls}>
          <option value="">Selecciona</option>
          {FIELDS.city_type.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>

        <label className={labelCls}>Ocupación</label>
        <select value={form.occupation} onChange={(e) => set('occupation', e.target.value)} className={selectCls}>
          <option value="">Selecciona</option>
          {FIELDS.occupation.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>

        <label className={labelCls}>¿Para qué necesita el crédito?</label>
        <select value={form.loan_purpose} onChange={(e) => set('loan_purpose', e.target.value)} className={selectCls}>
          <option value="">Selecciona</option>
          {FIELDS.loan_purpose.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>

        <div className="flex items-center justify-between py-1">
          <span className={labelCls}>¿Tiene otros créditos?</span>
          <button type="button" onClick={() => set('has_other_credits', !form.has_other_credits)}
            className={`w-12 h-6 rounded-full transition-colors ${form.has_other_credits ? 'bg-blue-600' : 'bg-gray-300'}`}>
            <div className={`w-5 h-5 bg-white rounded-full shadow transition-transform ${form.has_other_credits ? 'translate-x-6' : 'translate-x-0.5'}`} />
          </button>
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <button onClick={onCancel} className="flex-1 py-2.5 rounded-xl border border-gray-300 text-sm font-medium text-gray-600">
          Cancelar
        </button>
        <button onClick={() => valid && onSubmit({ ...form, age: Number(form.age), dependents: Number(form.dependents) })}
          disabled={!valid}
          className="flex-1 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-bold disabled:bg-gray-300 disabled:cursor-not-allowed">
          Evaluar crédito
        </button>
      </div>
    </motion.div>
  );
}
