import { serializePeriodPlan } from './periodReviewData';
import { serializeSalaryPosition } from './salaryReferences';
import type { SalaryPosition } from './salaryReferences';

export const emptyRescisaoBase = () => ({ titulacao: '', valor_manual: { valor: '', fonte: '', localizador: '' } });
export const emptyRescisaoPayment = (holiday = false) => ({ id: crypto.randomUUID(), competencia: '', rubrica: holiday ? '00750' : '', natureza_folha: '', natureza_rubrica: '', identificador_folha: '', sequencia: '', operacao: '', valor: '', origem: '', ...(holiday ? { periodo_aquisitivo: { inicio: '', ultimo_dia_considerado: '' }, avos: '' } : {}) });
export const emptyRescisaoPlan = () => ({ modalidade: '', motivo_termino: '', contrato_id: '', natureza_folha_devida: '', inicio_exercicio: '', data_termino: '', sentido_termino: '', ultimo_dia_trabalhado: '', ultimo_dia_considerado: '', justificativa_ultimo_dia: '', regra: { identificador: '', versao: '', fonte: '', inicio_vigencia: '', fim_vigencia: '', confirmada: false, aniversario_meses_curtos: '', motivos_suportados: [], ferias_sem_teto_confirmada: false, limite_avos_ferias: '' }, correcoes: {}, salarios: [], pagamentos_ferias: [], recebidos: [], documentos: [], conferido_pelo_rh: false });

export function serializeRescisaoPlan(value: unknown): unknown {
  const integer = (value: unknown) => {
    if (!/^\d+$/.test(String(value)) || !Number.isSafeInteger(Number(value))) throw new Error('Informe uma quantidade inteira válida.');
    return Number(value);
  };
  const visit = (item: unknown, key = ''): unknown => {
    if (Array.isArray(item)) return item.map(value => visit(value));
    if (item && typeof item === 'object') {
      if (key === 'referencia_salarial') return serializeSalaryPosition(item as SalaryPosition);
      if (['dias_salariais', 'avos_ferias', 'avos_13'].includes(key)) {
        const correction = item as Record<string, unknown>;
        return { ...correction, valor: integer(correction.valor) };
      }
      return Object.fromEntries(Object.entries(item).filter(([, val]) => val !== '' && val != null).map(([key, val]) => [key, visit(val, key)]));
    }
    if (['avos', 'limite_avos_ferias', 'ordem_devolucao'].includes(key)) return integer(item);
    if (key === 'valor') return (serializePeriodPlan({ valor: item }) as Record<string, unknown>).valor;
    return item;
  };
  return visit(value);
}
