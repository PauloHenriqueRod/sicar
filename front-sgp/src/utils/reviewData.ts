import { serializeSalaryPosition } from './salaryReferences';
import type { SalaryPosition } from './salaryReferences';
import type { TipoCalculo } from '../types';
import { reviewField } from './reviewFields';
import { getAt } from './documentExtraction';
import type { ExtractionReview } from './documentExtraction';
import { emptyPeriodPlan, emptyProgressionPlan, emptyAdditionalPlan, serializePeriodPlan, serializeProgressionPlan } from './periodReviewData';
import { emptySubstitutionPlan } from './substitutionReview';
import { emptyAbonoPlan, serializeAbonoPlan } from './abonoReview';
import { emptyRescisaoPlan, serializeRescisaoPlan } from './rescisaoReview';
import { emptyExerciciosPlan, serializeExerciciosPlan } from './exerciciosReview';
import { isMonthlyProgression, prepareDocentePlan, reviewedPayrollMonths, singleDocenteReview } from './progressionReviewValidation';
import { missingPayroll, payrollPayload } from './docentePayroll';

const fieldsByCalculation: Record<TipoCalculo, Record<string, unknown>> = {
  apuracao_periodos: { nome: '', matricula: '', apuracao: emptyPeriodPlan() },
  substituicao: { nome: '', matricula: '', substituicao: emptySubstitutionPlan() },
  insalubridade: { nome: '', matricula: '', adicionais: emptyAdditionalPlan() },
  abono: { valores_anuais: {} },
  rescisao: { nome: '', matricula: '', salario_mensal: '', classe: '', nivel: '', titulacao: '', data_exercicio: '', data_rescisao: '', mes_rescisao: '', ano_rescisao: '', meses_ferias: 0, meses_13: 0, dias_trabalhados: 0, ocorrencias_adicional_ferias: 0, valores_recebidos: {} },
  progressao: { nome: '', matricula: '', progressao: emptyProgressionPlan() },
  exercicio_anterior: { fluxo_mensal: [] },
};

export const emptyPeriod = () => ({ periodo: '', v_dev: '', v_rec: '', ab_ferias: 0, '13_sal': 0 });

export function prepareReviewData(type: TipoCalculo, data: Record<string, unknown>): Record<string, unknown> {
  if (type === 'exercicio_anterior' && (data.exercicios || !Array.isArray(data.fluxo_mensal ?? data.fluxo))) return { nome: data.nome === 'N/A' ? '' : data.nome ?? '', matricula: data.matricula === 'N/A' ? '' : data.matricula ?? '', exercicios: data.exercicios ?? emptyExerciciosPlan(), alertas_extracao: [...(Array.isArray(data.alertas_extracao) ? data.alertas_extracao : []), 'Informe origem do direito, rubrica, devido e pesquisa de pagamentos. Nenhum reflexo ou ajuste é presumido.'] };
  if (type === 'abono') return { nome: data.nome === 'N/A' ? '' : data.nome ?? '', matricula: data.matricula === 'N/A' ? '' : data.matricula ?? '', abono: data.abono ?? emptyAbonoPlan(), alertas_extracao: [...(Array.isArray(data.alertas_extracao) ? data.alertas_extracao : []), 'Listas anuais legadas não identificam parcelas ou direito e não são convertidas em meses. Confira os descontos e pagamentos por competência.'] };
  if (type === 'rescisao') return { nome: data.nome === 'N/A' ? '' : data.nome ?? '', matricula: data.matricula === 'N/A' ? '' : data.matricula ?? '', rescisao: data.rescisao ?? emptyRescisaoPlan(), alertas_extracao: [...(Array.isArray(data.alertas_extracao) ? data.alertas_extracao : []), 'Confira o contrato e aplique os dados extraídos. Quantidades agregadas legadas não são convertidas automaticamente em pagamentos ou períodos.', ...['salario_mensal', 'classe', 'nivel', 'titulacao', 'data_exercicio', 'data_rescisao'].flatMap(key => data[key] == null || data[key] === '' || data[key] === 'N/A' ? [] : [`Dado observado (${key}): ${String(data[key])}. Confira o campo e a fonte antes de usar.`])] };
  if (type === 'substituicao') return { nome: data.nome === 'N/A' ? '' : data.nome ?? '', matricula: data.matricula === 'N/A' ? '' : data.matricula ?? '', substituicao: data.substituicao ?? emptySubstitutionPlan(), ...(data.substitui_historico_id ? { substitui_historico_id: data.substitui_historico_id } : {}), alertas_extracao: [...(Array.isArray(data.alertas_extracao) ? data.alertas_extracao : []), ...(['salario_substituta', 'salario_propria', 'dias_substituidos', 'dias_interrupcao'].flatMap(key => data[key] == null ? [] : [`Dado agregado observado (${key}): ${data[key]}. Confira períodos, função e vigência antes de usar no plano.`]))] };
  const suggestions = data.percentual_adicional_sugerido == null ? [] : [`Razão adicional/VB observada: ${data.percentual_adicional_sugerido}%. É somente uma sugestão: confirme espécie, percentual, base e vigência na concessão.`];
  const observed = [['vencimento_basico', 'VB'], ['valor_insalubridade', 'Adicional']].flatMap(([key, label]) => data[key] == null ? [] : [`${label} observado na ficha: ${data[key]}. Confira a competência e a fonte antes de usá-lo como base ou pagamento.`]);
  if (type === 'insalubridade') return { nome: data.nome ?? '', matricula: data.matricula ?? '', adicionais: data.adicionais ?? emptyAdditionalPlan(), ...(data.substitui_historico_id ? { substitui_historico_id: data.substitui_historico_id } : {}), alertas_extracao: [...(Array.isArray(data.alertas_extracao) ? data.alertas_extracao : []), ...suggestions, ...observed] };
  if (type === 'progressao') {
    // A extração legada não prova modalidade, posições completas nem datas de efeitos.
    const progression = emptyProgressionPlan();
    const qualification = typeof data.titulacao === 'string' ? data.titulacao.trim() : '';
    return { nome: data.nome ?? '', matricula: data.matricula ?? '',
      progressao: data.progressao ?? progression,
      ...(data.substitui_historico_id ? { substitui_historico_id: data.substitui_historico_id } : {}),
      alertas_extracao: [...(Array.isArray(data.alertas_extracao) ? data.alertas_extracao : []),
        ...suggestions,
        ...observed,
        ...(qualification && !data.progressao ? [`Titulação ou escolaridade registrada no documento: ${qualification}. Confira separadamente a origem e cada mudança de IQ/RT.`] : [])],
    };
  }
  const prepared = { ...structuredClone(fieldsByCalculation[type]), ...data };
  if (type === 'exercicio_anterior') {
    prepared.alertas_extracao = [...(Array.isArray(data.alertas_extracao) ? data.alertas_extracao : []), 'Resumo agregado legado, sem rubrica ou origem do direito. Não representa a revisão do contrato por parcelas.'];
    const flow = data.fluxo_mensal ?? data.fluxo ?? [];
    prepared.fluxo_mensal = Array.isArray(flow) ? flow.map(item => {
      const { v_abono, v_13, ...canonical } = item;
      return { ...emptyPeriod(), ...canonical, ab_ferias: canonical.ab_ferias ?? v_abono ?? 0, '13_sal': canonical['13_sal'] ?? v_13 ?? 0 };
    }) : [];
    delete prepared.fluxo;
  }
  return prepared;
}

/** Dots are decimal separators unless a comma supplies the pt-BR decimal part. */
export function parseReviewNumber(value: unknown, integer = false): number {
  const text = String(value).trim();
  const valid = /^[+-]?\d+(?:\.\d+)?$/.test(text) || /^[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+),\d+$/.test(text);
  if (!valid) throw new Error('Informe um número válido. Use 1234,56 ou 1234.56.');
  const number = Number(text.includes(',') ? text.replaceAll('.', '').replace(',', '.') : text);
  if (!Number.isFinite(number) || (integer && !Number.isSafeInteger(number))) {
    throw new Error(integer ? 'Informe um número inteiro válido.' : 'Informe um número finito.');
  }
  return number;
}

export function serializeReviewData(data: Record<string, unknown>): Record<string, unknown> {
  if (isMonthlyProgression(data)) {
    const review = data.revisao_extracao ? singleDocenteReview(data) : undefined;
    const months = reviewedPayrollMonths(data);
    const missing = missingPayroll(months);
    if (missing) throw new Error(missing);
    const plan = prepareDocentePlan(data);
    const { rows, applications } = payrollPayload(months, plan.conferido_pelo_rh === true);
    data = { ...data, progressao: { ...plan, bases_mensais_origem: rows } };
    if (review) data.revisao_extracao = { ...review, aplicacoes: [
      ...review.aplicacoes.filter(a => !(a.destino[0] === 'progressao' && a.destino[1] === 'bases_mensais_origem')), ...applications,
    ] };
  }
  if (Object.hasOwn(data, 'insalubridade') && (data.insalubridade == null || String(data.insalubridade).trim() === '')) {
    throw new Error('Confira o percentual de insalubridade e informe um valor, inclusive zero quando não houver adicional.');
  }
  if (Object.hasOwn(data, 'ocorrencias_adicional_ferias') && (data.ocorrencias_adicional_ferias == null || data.ocorrencias_adicional_ferias === '')) {
    throw new Error('Confira os pagamentos anteriores do adicional de férias e informe a quantidade, inclusive zero quando não houver pagamento.');
  }
  const visit = (value: unknown, path: (string | number)[]): unknown => {
    if (Array.isArray(value)) return value.map((item, index) => visit(item, [...path, index]));
    if (value && typeof value === 'object') {
      return Object.fromEntries(Object.entries(value).flatMap(([key, item]) => {
        const nextPath = [...path, key];
        if (nextPath.length === 1 && ['revisao_docente_detalhada', 'edicoes_folha_docente'].includes(key)) return [];
        if (nextPath.length === 1 && key === 'revisao_extracao') return [[key, structuredClone(item)]];
        if (nextPath.length === 1 && key === 'apuracao') return [[key, serializePeriodPlan(item)]];
        if (nextPath.length === 1 && key === 'substituicao') return [[key, serializePeriodPlan(item)]];
        if (nextPath.length === 1 && key === 'rescisao') return [[key, serializeRescisaoPlan(item)]];
        if (nextPath.length === 1 && key === 'abono') return [[key, serializeAbonoPlan(item)]];
        if (nextPath.length === 1 && key === 'exercicios') return [[key, serializeExerciciosPlan(item)]];
        if (nextPath.length === 1 && key === 'adicionais') return [[key, serializePeriodPlan(item)]];
        if (nextPath.length === 1 && key === 'substitui_historico_id') return item === '' || item == null ? [] : [[key, parseReviewNumber(item, true)]];
        if (nextPath.length === 1 && key === 'progressao') return [[key, serializeProgressionPlan(item)]];
        if (nextPath.length === 1 && ['referencia_salarial', 'referencia_antiga', 'referencia_nova'].includes(key)) {
          return item ? [[key, serializeSalaryPosition(item as SalaryPosition)]] : [];
        }
        // Optional empty numbers use the server defaults; required periods are validated there.
        if ((item === '' || item === null) && reviewField(key, nextPath).inputMode && nextPath.length === 1) return [];
        return [[key, visit(item, nextPath)]];
      }));
    }
    const key = path[path.length - 1];
    const field = reviewField(key, path);
    if (!field.inputMode || key === 'matricula' || key === 'periodo') return value;
    try { return parseReviewNumber(value, field.inputMode === 'numeric'); }
    catch (error) { throw new Error(`${field.label}: ${(error as Error).message}`, { cause: error }); }
  };
  const result = visit(data, []) as Record<string, unknown>;
  const review = result.revisao_extracao as ExtractionReview | undefined;
  if (review) review.aplicacoes = review.aplicacoes.map(application => ({ ...application, valor_revisado: String(getAt(result, application.destino) ?? '') }));
  return result;
}
