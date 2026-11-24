import { serializePeriodPlan } from './periodReviewData';

export const emptyAbonoMapping = () => ({ rubrica: '', papel: '', categoria: '', fonte: '', confirmado: false });
export const emptyAbonoParcel = () => ({ id: crypto.randomUUID(), categoria: '', competencia_direito: '', exercicio_13: '', periodo_referencia: { inicio: '', ultimo_dia_considerado: '' }, rubrica_abono: '', natureza_folha_devida: '', contribuicao: 'PENDENTE', recebimento: 'PENDENTE', fonte_conferencia: '' });
export const emptyAbonoRecord = () => ({ id: crypto.randomUUID(), papel: '', categoria: '', parcela_id: '', competencia: '', rubrica: '', natureza_folha: '', natureza_rubrica: '', identificador_folha: '', sequencia: '', operacao: '', valor: '', origem: '', conferido: false });
export const emptyAbonoPlan = () => ({ vinculo_id: '', periodo_direito: { inicio: '', ultimo_dia_considerado: '' }, data_documento: '', data_requerimento: '', regra: { identificador: '', versao: '', fonte: '', inicio_vigencia: '', fim_vigencia: '', formula: 'CONTRIBUICAO_ELEGIVEL_CONFIRMADA', confirmada: false }, mapeamentos: [], parcelas: [], cobertura_13: [], lancamentos: [], documentos: [], conferido_pelo_rh: false });

export function serializeAbonoPlan(value: unknown): unknown {
  const visit = (item: unknown, key = ''): unknown => {
    if (Array.isArray(item)) return item.map(value => visit(value));
    if (item && typeof item === 'object') return Object.fromEntries(Object.entries(item).filter(([, val]) => val !== '' && val != null).map(([key, val]) => [key, visit(val, key)]));
    if (typeof item === 'string' && ['exercicio', 'exercicio_13'].includes(key)) {
      if (!/^\d{4}$/.test(item) || Number(item) < 1) throw new Error('Informe exercício com quatro dígitos.');
      return Number(item);
    }
    if (key === 'valor') return (serializePeriodPlan({ valor: item }) as Record<string, unknown>).valor;
    if (key === 'valor_observado') return (serializePeriodPlan({ valor_observado: item }) as Record<string, unknown>).valor_observado;
    return item;
  };
  return visit(value);
}
