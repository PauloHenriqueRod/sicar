import type { TipoCalculo, PageTab } from '../types';

export const pageTitles: Record<PageTab, string> = {
  dashboard: 'Visão geral', calculo: 'Cálculos', historico: 'Processos calculados',
  tabelas: 'Tabelas remuneratórias', usuarios: 'Usuários e acessos', auditoria: 'Auditoria do sistema',
};

export const calculationLabels: Record<TipoCalculo, string> = {
  substituicao: 'Substituição',
  insalubridade: 'Adicionais ocupacionais',
  abono: 'Abono de permanência',
  rescisao: 'Rescisão de professor substituto',
  progressao: 'Progressão docente ou TAE',
  exercicio_anterior: 'Exercício anterior',
  apuracao_periodos: 'Apuração por períodos e rubricas',
};

export function calculationLabel(type: string) {
  return calculationLabels[type as TipoCalculo] ?? type.replace(/_/g, ' ');
}

const roleLabels: Record<string, string> = { user: 'Usuário', admin: 'Administrador', dev: 'Desenvolvedor' };
export function roleLabel(role: string) { return roleLabels[role] ?? role; }

const currency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const date = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
const dateTime = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });

export function formatCurrency(value: number | string) {
  if (typeof value === 'string') {
    const match = /^(-?)(\d+)\.(\d{2})$/.exec(value);
    return match ? `${match[1]}R$\u00a0${match[2].replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${match[3]}` : 'Não informado';
  }
  return Number.isFinite(value) ? currency.format(value) : 'Não informado';
}

export function formatCalculationValue(key: string, value: unknown): string | number {
  if (typeof value === 'number') {
    const counter = key.startsWith('exercicio') || key.endsWith('_id') || key.includes('avos') || key.includes('dias') || key.includes('mes') || key.includes('ano') || key.includes('multiplicador') || ['id', 'referencia_id', 'nivel', 'nivel_docente', 'padrao_tae', 'avos', 'segmento_base'].includes(key);
    return counter ? value : formatCurrency(value);
  }
  if (typeof value === 'string' && ['principal', 'acrescimos', 'reducoes', 'devido', 'recebido', 'saldo', 'total_geral_a_receber', 'saldo_parcelas_calculadas', 'devolucao', 'valor_conciliado', 'contribuicao_conciliada'].includes(key) && /^-?\d+\.\d{2}$/.test(value)) return formatCurrency(value);
  return String(value);
}
export function formatDate(value: string, includeTime = false) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 'Não informado' : (includeTime ? dateTime : date).format(parsed);
}

export function unwrapCalculationResult(result: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const nested = result?.resultado_calculo;
  return nested && typeof nested === 'object' && !Array.isArray(nested) ? nested as Record<string, unknown> : result ?? {};
}

export function calculationTotal(result: Record<string, unknown>): [string, number | string] | undefined {
  const data = unwrapCalculationResult(result);
  const keys = ['saldo_parcelas_calculadas', 'total_com_reflexos', 'total_liquido_a_receber', 'total_geral_a_receber', 'total_a_receber', 'total_geral_devido', 'total_acumulado', 'total_geral', 'valor_proporcional_devido'];
  for (const key of keys) {
    const value = data[key];
    if (typeof value === 'number' && Number.isFinite(value)) return [key, value];
    if ((data.tipo_apuracao === 'periodos_v1' || data.tipo_substituicao === 'periodos_v1' || data.tipo_rescisao === 'periodos_v1' || data.tipo_abono === 'parcelas_v1' || data.tipo_exercicio === 'parcelas_v1') && typeof value === 'string' && /^-?\d+\.\d{2}$/.test(value)) return [key, value];
  }
  const summary = data.resumo_consolidado;
  if (summary && typeof summary === 'object' && !Array.isArray(summary)) return calculationTotal(summary as Record<string, unknown>);
}

export function formatHistoryTotal(json: string) {
  try {
    const result = JSON.parse(json);
    if (!result || typeof result !== 'object') return 'Não informado';
    const total = calculationTotal(result)?.[1];
    return total === undefined ? 'Não informado' : formatCurrency(total);
  } catch {
    return 'Não disponível';
  }
}
