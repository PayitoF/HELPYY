import React, { useState } from 'react';
import { motion } from 'framer-motion';

const INCOME_STEPS = [0, 200000, 400000, 600000, 800000, 1000000, 1500000, 2000000, 3000000, 5000000, 7000000, 10000000];
const formatCOP = (v) => v >= 10000000 ? '$10M+' : v >= 1000000 ? `$${(v / 1000000).toFixed(1)}M` : `$${(v / 1000).toFixed(0)}K`;

const OCCUPATIONS = ['Vendedor ambulante', 'Trabajador doméstico', 'Conductor', 'Comerciante', 'Peluquero/a', 'Cocinero/a', 'Otro'];
const PURPOSES = ['Capital de trabajo', 'Emergencia', 'Educación', 'Mejora de vivienda', 'Compra de inventario'];

const selectCls = 'w-full rounded-xl bg-gray-100 border-2 border-gray-200 px-4 py-3 text-sm outline-none focus:border-blue-400';
const labelCls = 'text-xs font-semibold text-gray-500';

export default function LoanApplicationForm({ onSubmit, onCancel }) {
  const [incomeIdx, setIncomeIdx] = useState(5);
  const [form, setForm] = useState({
    employment_type: '', age: '', city_type: '',
    occupation: '', other_occupation: '', dependents: '0',
    has_other_credits: false, purpose: '',
  });

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));
  const income = INCOME_STEPS[incomeIdx];

  const valid = income > 0 && form.employment_type && form.age >= 18 && form.city_type
    && (form.occupation && (form.occupation !== 'Otro' || form.other_occupation)) && form.purpose;

  function handleSubmit() {
    if (!valid) return;
    const occ = form.occupation === 'Otro' ? form.other_occupation : form.occupation;
    onSubmit({
      declared_income: income >= 10000000 ? 10000000 : income,
      employment_type: form.employment_type === 'Independiente' ? 'independent' : form.employment_type.toLowerCase(),
      age: Number(form.age),
      city_type: form.city_type === 'Urbana' ? 'urban' : 'rural',
      occupation: occ,
      dependents: Number(form.dependents),
      has_other_credits: form.has_other_credits,
      purpose: form.purpose,
    });
  }

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      className="bg-white rounded-2xl border border-gray-100 shadow-md p-4 space-y-3">
      <h3 className="text-sm font-bold text-blue-800">📋 Solicitud de Microcrédito</h3>

      <div className="space-y-2.5">
        {/* Income slider */}
        <label className={labelCls}>Ingreso mensual: <span className="text-blue-700 font-bold">{formatCOP(income)}</span></label>
        <input type="range" min={0} max={INCOME_STEPS.length - 1} value={incomeIdx}
          onChange={(e) => setIncomeIdx(Number(e.target.value))}
          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600" />
        <div className="flex justify-between text-[10px] text-gray-400">
          <span>$0</span><span>$2M</span><span>$5M</span><span>$10M+</span>
        </div>

        <label className={labelCls}>Tipo de empleo</label>
        <select value={form.employment_type} onChange={(e) => set('employment_type', e.target.value)} className={selectCls}>
          <option value="">Selecciona</option>
          <option value="Informal">Informal</option>
          <option value="Formal">Formal</option>
          <option value="Independiente">Independiente</option>
        </select>

        <div className="flex gap-3">
          <div className="flex-1">
            <label className={labelCls}>Edad</label>
            <input type="number" min={18} max={100} value={form.age}
              onChange={(e) => set('age', e.target.value)} placeholder="18" className={selectCls} />
          </div>
          <div className="flex-1">
            <label className={labelCls}>Personas a cargo</label>
            <input type="number" min={0} max={10} value={form.dependents}
              onChange={(e) => set('dependents', e.target.value)} placeholder="0" className={selectCls} />
          </div>
        </div>

        <label className={labelCls}>Ciudad</label>
        <select value={form.city_type} onChange={(e) => set('city_type', e.target.value)} className={selectCls}>
          <option value="">Selecciona</option>
          <option value="Urbana">Urbana</option>
          <option value="Rural">Rural</option>
        </select>

        <label className={labelCls}>Ocupación</label>
        <select value={form.occupation} onChange={(e) => set('occupation', e.target.value)} className={selectCls}>
          <option value="">Selecciona</option>
          {OCCUPATIONS.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
        {form.occupation === 'Otro' && (
          <input type="text" value={form.other_occupation} onChange={(e) => set('other_occupation', e.target.value)}
            placeholder="Especifica tu ocupación" className={selectCls} />
        )}

        <label className={labelCls}>¿Para qué necesita el crédito?</label>
        <select value={form.purpose} onChange={(e) => set('purpose', e.target.value)} className={selectCls}>
          <option value="">Selecciona</option>
          {PURPOSES.map((v) => <option key={v} value={v}>{v}</option>)}
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
        <button onClick={handleSubmit} disabled={!valid}
          className="flex-1 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-bold disabled:bg-gray-300 disabled:cursor-not-allowed">
          Evaluar crédito
        </button>
      </div>
    </motion.div>
  );
}
