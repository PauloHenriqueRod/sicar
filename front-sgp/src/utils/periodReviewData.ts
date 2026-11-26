import { emptySalaryPosition, serializeSalaryPosition } from './salaryReferences';
import type { SalaryPosition } from './salaryReferences';

export const emptyRule = () => ({ identificador: '', versao: '', fonte: '' });
export const emptyManualValue = () => ({ valor: '', fonte: '', localizador: '' });
export const emptyPeriodPlan = () => ({
  periodo: { inicio: '', ultimo_dia_considerado: '' }, data_documento: '', data_implantacao: '',
  estado_inicial: { posicao: emptySalaryPosition(), titulacao: '' },
  eventos: [], interrupcoes: [], rubricas: [], recebidos: [], conferido_pelo_rh: false,
});
export const emptyProgressionPlan = () => {
  const today = new Date();
  const lastDay = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  return {
    ...emptyPeriodPlan(),
    periodo: { inicio: '', ultimo_dia_considerado: lastDay },
    modalidade: '', reflexos: [],
  };
};
export const emptyAdditional = () => ({ identificador: '', especie: '', percentual: '', percentual_confirmado: false, inicio_vigencia: '', fim_vigencia: '', base: { tipo: '', confirmada: false }, regra: { ...emptyRule(), inicio_vigencia: '', fim_vigencia: '', confirmada: false } });
export const emptyAdditionalPlan = () => ({ ...emptyPeriodPlan(), estado_inicial: { posicao: emptySalaryPosition(), titulacao: '', adicional: emptyAdditional() }, reflexos: [] });

export function serializePeriodPlan(value: unknown): unknown {
  const visit = (item: unknown, key = ''): unknown => {
    if (Array.isArray(item)) return item.map(value => visit(value));
    if (item && typeof item === 'object') {
      if (key === 'posicao') return serializeSalaryPosition(item as SalaryPosition);
      return Object.fromEntries(Object.entries(item).filter(([k, v]) => v !== '' && k !== 'origem_automatica').map(([k, v]) => [k, visit(v, k)]));
    }
    if (typeof item === 'string' && (key === 'valor' || key === 'percentual' || key.startsWith('percentual_'))) {
      const text = item.trim();
      if (!/^\d+(?:\.\d+)?$/.test(text) && !/^(?:\d+|\d{1,3}(?:\.\d{3})+),\d+$/.test(text)) {
        const labels: Record<string, string> = { percentual_anuenio: 'Anuênio', percentual_adicional: 'Adicional', percentual_iq: 'IQ', percentual_utilizado: 'Percentual utilizado do componente' };
        const label = labels[key] ?? 'Valor';
        throw new Error(`${label}: informe um número válido. Use 1234,56 ou 1234.56.`);
      }
      return text.includes(',') ? text.replaceAll('.', '').replace(',', '.') : text;
    }
    if (typeof item === 'string' && key === 'valor_observado') {
      const text = item.trim();
      if (!/^[+-]?\d+(?:\.\d+)?$/.test(text) && !/^[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+),\d+$/.test(text)) throw new Error('Valor observado: informe um número válido.');
      const normalized = text.includes(',') ? text.replaceAll('.', '').replace(',', '.') : text;
      return normalized.startsWith('+') ? normalized.slice(1) : normalized;
    }
    if (key === 'avos' && typeof item === 'string') {
      if (!/^\d+$/.test(item.trim()) || !Number.isSafeInteger(Number(item))) throw new Error('Informe uma quantidade inteira de avos.');
      return Number(item);
    }
    return item;
  };
  return visit(value);
}

export function serializeProgressionPlan(value: unknown): unknown {
  const plan = value as { modalidade?: string; estado_inicial?: Record<string, unknown>; rubricas?: { formula: string }[] };
  for (const [field, label] of [...(plan.rubricas?.some(item => item.formula === 'ADICIONAL_SOBRE_VB') ? [['percentual_adicional', 'adicional']] : []), ['percentual_anuenio', 'anuênio'], ...(plan.modalidade === 'TAE' ? [['percentual_iq', 'IQ']] : [])]) {
    const current = plan.estado_inicial?.[field];
    if (current == null || String(current).trim() === '') throw new Error(`Confira o percentual inicial de ${label}, inclusive zero quando não houver.`);
  }
  return serializePeriodPlan(value);
}
