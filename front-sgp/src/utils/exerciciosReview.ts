import { serializePeriodPlan } from './periodReviewData';

export const emptyExercicioRule = () => ({ identificador: '', versao: '', fonte: '', inicio_vigencia: '', fim_vigencia: '', confirmada: false });
export const emptyExercicioOrigin = () => ({ id: crypto.randomUUID(), descricao: '', periodo_efeitos: { inicio: '', ultimo_dia_considerado: '' }, data_documento: '', fonte: '', localizador: '', regra: emptyExercicioRule() });
export const emptyExercicioParcel = () => ({ id: crypto.randomUUID(), origem_direito_id: '', competencia: '', rubrica: '', categoria: '', periodo_referencia: { inicio: '', ultimo_dia_considerado: '' }, natureza_folha_devida: '', estado_revisao: 'PENDENTE', nota_revisao: '', pesquisa_pagamentos: 'PENDENTE' });
export const emptyExercicioEntry = (payment = false) => ({ id: crypto.randomUUID(), parcela_id: '', operacao: '', valor: '', fonte: '', localizador: '', conferido: false, ...(payment ? { tipo_origem: '', via_pagamento: 'NAO_INFORMADA', justificativa_vinculo: '' } : { identificador_evento: '', memoria_calculo: '' }) });
export const emptyExercicioAdjustment = () => ({ id: crypto.randomUUID(), parcela_id: '', identificador_evento: '', tipo: '', efeito: '', valor: '', regra: emptyExercicioRule(), memoria_calculo: '', fonte: '', localizador: '', conferido: false });
export const emptyExerciciosPlan = () => ({ vinculo_id: '', periodo: { inicio: '', ultimo_dia_considerado: '' }, origens: [], parcelas: [], devidos: [], recebimentos: [], ajustes: [], documentos: [], conferido_pelo_rh: false });
export const serializeExerciciosPlan = (value: unknown) => serializePeriodPlan(value);
