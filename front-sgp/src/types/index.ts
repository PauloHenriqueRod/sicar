export type TipoCalculo = 'substituicao' | 'insalubridade' | 'abono' | 'rescisao' | 'progressao' | 'exercicio_anterior' | 'apuracao_periodos';
export type PageTab = 'dashboard' | 'calculo' | 'historico' | 'usuarios' | 'auditoria' | 'tabelas';

export interface DataState {
  historico_id?: number | null;
  dados_extraidos: Record<string, unknown> | null;
  resultado_calculo: Record<string, unknown> | null;
}

export interface CalculationItem extends DataState {
  filename: string;
  idempotency_key?: string;
  falhas_extracao?: { filename: string; codigo: string; mensagem: string }[];
}
