import { emptyAbonoRecord } from './abonoReview';
import { emptyExercicioEntry } from './exerciciosReview';
import { emptyRescisaoPayment } from './rescisaoReview';
import { emptySourcePeriod } from './substitutionReview';

export type Path = (string | number)[];
export type Obj = Record<string, unknown>;
export interface ExtractedField { ano_referencia?: number | null; fontes_campo_ids?: string[]; descricao_rubrica?: string | null; natureza_origem?: 'EXPLICITA' | 'GRUPO' | null; leitor_id?: string | null; leitor_versao?: string | null; parcela?: string | null; cancelada?: boolean | null; continuacao?: boolean | null; data_interrupcao?: string | null; reinicio?: string | null; dias_restantes?: string | null; sugestao?: boolean; id: string; bloco_id: string; campo: string; valor: string | null; observado?: string | null; estado: 'EXTRAIDO' | 'AUSENTE' | 'AMBIGUO' | 'ILEGIVEL'; pagina: number | null; localizador: string; paginas_analisadas?: number[]; competencia?: string | null; rubrica?: string | null; natureza?: 'R' | 'D' | null; sequencia?: string | null; inicio?: string | null; fim?: string | null; fim_informado?: string | null; fim_calculado?: string | null; dias_informados?: string | null; candidatos?: string[] }
export interface ExtractedDocument { arquivo_id?: string | null; categoria_informada?: string | null; leitores?: { identificador: string; versao: string; paginas: number[] }[]; id: string; nome_arquivo: string; impressao?: string | null; layout: 'FICHA_SIAPE' | 'CADASTRO_FUNCIONAL' | 'CACOFERIAS' | 'ATO_UFPI_SUBSTITUICAO' | 'PORTARIA_UFPI_DOCENTE' | 'PORTARIA_UFPI_TAE' | 'MISTO' | 'NAO_SUPORTADO'; versao_leitor: 'rh_paginas_v1' | 'rh_paginas_v2' | 'rh_paginas_v3' | 'rh_paginas_v4' | 'rh_paginas_v5'; situacao: 'CONCLUIDO' | 'PARCIAL' | 'SEM_TEXTO' | 'NAO_SUPORTADO'; total_paginas: number; blocos: { id: string; matricula?: string | null; nome?: string | null; vinculo?: string | null; categoria: 'TAE' | 'DOCENTE' | 'SUBSTITUTO' | 'NAO_IDENTIFICADA'; paginas: number[]; papel_documental?: 'SERVIDOR' | 'SUBSTITUTO' | 'TITULAR' | null }[]; campos: ExtractedField[]; avisos: string[] }
export interface Association { documento_id: string; bloco_id: string; pessoa: 'SERVIDOR' | 'TITULAR' | 'DESCARTADO'; matricula: string; vinculo: string; justificativa: string; confirmado: boolean }
export interface Application { documento_id: string; campo_id: string; destino: Path; valor_revisado: string; justificativa: string; registro_id?: string | null; valor_anterior?: string | null }
export interface ExtractionReview { documentos: ExtractedDocument[]; associacoes: Association[]; aplicacoes: Application[]; historico_aplicacoes?: Application[]; vinculo_calculo: string; vinculo_titular: string; confirmado: boolean }
export const object = (value: unknown): Obj => value && typeof value === 'object' && !Array.isArray(value) ? value as Obj : {};
export const getAt = (value: unknown, path: Path): unknown => path.reduce<unknown>((current, key) => Array.isArray(current) ? current[Number(key)] : object(current)[key], value);
export function setAt(value: unknown, path: Path, next: unknown): unknown {
  if (!path.length) return next;
  const [key, ...rest] = path;
  if (Array.isArray(value)) { const result = [...value]; result[Number(key)] = setAt(result[Number(key)], rest, next); return result; }
  return { ...object(value), [key]: setAt(object(value)[key], rest, next) };
}
function readerKey(doc: ExtractedDocument): string { return (doc.leitores ?? []).map(r => `${r.identificador}:${r.versao}:${r.paginas.join(',')}`).sort().join('|'); }
export function mergeExtractions(previous: ExtractionReview | undefined, documents: ExtractedDocument[]): ExtractionReview {
  const result: ExtractionReview = structuredClone(previous ?? { documentos: [], associacoes: [], aplicacoes: [], vinculo_calculo: '', vinculo_titular: '', confirmado: false });
  for (const doc of documents) {
    if (result.documentos.some(existing => existing.id === doc.id || (doc.impressao && doc.impressao === existing.impressao && doc.versao_leitor === existing.versao_leitor && readerKey(doc) === readerKey(existing)))) continue;
    if (result.documentos.length >= 10) throw new Error('Limite de 10 documentos na revisão. Divida o processo antes de adicionar novas fontes.');
    if (result.associacoes.length + doc.blocos.length > 100) throw new Error('Limite de 100 blocos de identificação. Divida o processo para conferir todas as pessoas e vínculos.');
    result.documentos.push(doc);
    result.associacoes.push(...doc.blocos.map(block => ({ documento_id: doc.id, bloco_id: block.id, pessoa: block.papel_documental === 'TITULAR' ? 'TITULAR' as const : 'SERVIDOR' as const, matricula: '', vinculo: '', justificativa: '', confirmado: false })));
  }
  result.confirmado = false;
  return result;
}

const identityKey = (value: string) => /^\d+$/.test(value.trim()) ? value.trim().replace(/^0+(?=\d)/, '') : value.trim().toLowerCase();
const nameKey = (value: string) => value.trim().replace(/\s+/g, ' ').toLowerCase();

/** Initial suggestions only: keep proof, leave associations and RH approval pending. */
export function suggestProgressionIdentification(data: Obj): Obj {
  const review = data.revisao_extracao as ExtractionReview | undefined;
  if (!data.progressao || !review) return data;
  const blocks = review.documentos.flatMap(doc => doc.blocos.map(block => ({ doc, block }))).filter(({ doc, block }) =>
    block.papel_documental !== 'TITULAR' && !review.associacoes.some(a => a.documento_id === doc.id && a.bloco_id === block.id && a.pessoa === 'DESCARTADO' && a.confirmado));
  const candidate = blocks.find(({ doc, block }) => ['FICHA_SIAPE', 'MISTO'].includes(doc.layout) && block.matricula?.trim() && block.nome?.trim());
  if (!candidate) return data;
  const { doc, block } = candidate;
  if (data.matricula != null && String(data.matricula).trim() && identityKey(String(data.matricula)) !== identityKey(block.matricula!)) return data;
  if (data.nome != null && String(data.nome).trim() && nameKey(String(data.nome)) !== nameKey(block.nome!)) return data;
  if (blocks.some(item => (item.block.matricula && identityKey(item.block.matricula) !== identityKey(block.matricula!)) || (item.block.nome && nameKey(item.block.nome) !== nameKey(block.nome!)))) return data;
  if (new Set(blocks.map(item => item.block.vinculo?.trim()).filter(Boolean)).size > 1) return data;
  let next = data;
  for (const key of ['nome', 'matricula'] as const) {
    if (next[key] != null && next[key] !== '') continue;
    if (review.aplicacoes.some(item => item.destino.length === 1 && item.destino[0] === key)) continue;
    const facts = doc.campos.filter(field => field.bloco_id === block.id && field.campo === key);
    const source = facts.find(field => field.estado === 'EXTRAIDO' && field.valor != null && field.pagina != null && field.valor === block[key]);
    if (!source || facts.some(field => field.estado !== 'EXTRAIDO' || field.valor !== source.valor)) continue;
    next = applyField(next, doc, source, [key], source.valor!);
  }
  return next;
}
const reserved = new Set(['revisao_extracao', 'regra', 'documentos', 'confirmada', 'confirmado', 'conferido', 'conferido_pelo_rh', 'alertas_extracao', 'id', 'substitui_historico_id']);
export function scalarTargets(value: unknown, path: Path = []): Path[] {
  if (Array.isArray(value)) return value.flatMap((row, index) => scalarTargets(row, [...path, index]));
  if (value && typeof value === 'object') return Object.entries(value).flatMap(([key, item]) => reserved.has(key) ? [] : scalarTargets(item, [...path, key]));
  return typeof value === 'boolean' ? [] : [path];
}
export function fieldTargets(data: Obj, doc: ExtractedDocument, field: ExtractedField): Path[] {
  const association = (data.revisao_extracao as ExtractionReview).associacoes.find(a => a.documento_id === doc.id && a.bloco_id === field.bloco_id);
  const allowed: Record<string, string[]> = { nome: ['nome'], matricula: ['matricula', 'titular_matricula'], inicio_exercicio: ['inicio_exercicio', 'data_exercicio'], percentual_iq: ['percentual_iq', 'incentivo'], percentual_adicional_sugerido: ['percentual_adicional', 'percentual', 'percentual_insalubridade'], jornada: ['jornada'], data_documento: ['data_documento'], data_publicacao: ['data_publicacao'], efeitos_financeiros: ['efeitos_financeiros'], inicio_designacao: ['inicio'], fim_designacao: ['ultimo_dia_considerado'], codigo_funcao_substituida: ['codigo_funcao'], tipo_funcao_substituida: ['tipo_funcao'] };
  return scalarTargets(data).filter(path => {
    if (!path.length || (allowed[field.campo] && !allowed[field.campo].includes(String(path.at(-1))))) return false;
    const designated = ['codigo_funcao_substituida', 'tipo_funcao_substituida'].includes(field.campo);
    const functionTarget = path[0] === 'substituicao' && path[1] === 'estado_inicial' && path[2] === 'substituida';
    if (designated) return functionTarget && association?.pessoa === 'SERVIDOR';
    const ownerTarget = path[0] === 'substituicao' && (['titular_matricula', 'afastamentos_titular'].includes(String(path[1])) || functionTarget);
    return association?.pessoa === 'TITULAR' ? ownerTarget : !ownerTarget;
  });
}
export function applyField(data: Obj, doc: ExtractedDocument, field: ExtractedField, path: Path, value: string, justification = '', resolveConflict = false): Obj {
  const review = structuredClone(data.revisao_extracao) as ExtractionReview;
  const old = getAt(data, path);
  if (!resolveConflict && old !== '' && old != null && String(old) !== value) throw new Error('O campo já tem um valor. Confira e edite-o no formulário; a extração não sobrescreve suas alterações.');
  if (!resolveConflict && review.aplicacoes.some(a => JSON.stringify(a.destino) === JSON.stringify(path))) throw new Error('Destino já associado. Revise a origem existente antes de trocar a fonte.');
  if (resolveConflict) {
    if (!justification.trim()) throw new Error('Justifique a substituição do valor ou da fonte.');
    const replaced = review.aplicacoes.filter(a => JSON.stringify(a.destino) === JSON.stringify(path));
    review.historico_aplicacoes = [...(review.historico_aplicacoes ?? []), ...replaced];
    if (review.historico_aplicacoes.length > 1000) throw new Error('Limite do histórico de aplicações atingido.');
    review.aplicacoes = review.aplicacoes.filter(a => JSON.stringify(a.destino) !== JSON.stringify(path));
  }
  const rowIndex = path.findIndex(key => typeof key === 'number');
  const registro = rowIndex >= 0 ? object(getAt(data, path.slice(0, rowIndex + 1))).id : undefined;
  review.aplicacoes.push({ documento_id: doc.id, campo_id: field.id, destino: path, valor_revisado: value, justificativa: justification, ...(resolveConflict ? { valor_anterior: String(old ?? '') } : {}), ...(registro ? { registro_id: String(registro) } : {}) });
  review.confirmado = false;
  return { ...object(setAt(data, path, value)), revisao_extracao: review };
}
export function appendFinancialCandidate(data: Obj, doc: ExtractedDocument, field: ExtractedField): Obj {
  const key = ['abono', 'exercicios', 'rescisao', 'substituicao', 'adicionais', 'progressao', 'apuracao'].find(k => data[k]);
  if (!key || field.valor == null) throw new Error('Selecione um cálculo e confira o valor observado.');
  const source = `${doc.nome_arquivo}, página ${field.pagina}`;
  let group = key === 'abono' ? 'lancamentos' : key === 'exercicios' ? 'recebimentos' : 'recebidos';
  let record: Obj = key === 'abono' ? emptyAbonoRecord() : key === 'exercicios' ? emptyExercicioEntry(true) : emptyRescisaoPayment();
  if (key === 'rescisao' && field.rubrica === '00750') { group = 'pagamentos_ferias'; record = emptyRescisaoPayment(true); }
  record = { ...record, id: crypto.randomUUID(), valor: '', operacao: '', ...(key === 'exercicios' ? { competencia_pagamento: field.competencia ?? '', rubrica_pagamento: field.rubrica ?? '', natureza_rubrica: field.natureza ?? '', sequencia: field.sequencia ?? '', fonte: source, localizador: field.localizador } : { competencia: field.competencia ?? '', rubrica: field.rubrica ?? '', natureza_rubrica: field.natureza ?? '', sequencia: field.sequencia ?? '', origem: source }) };
  const list = getAt(data, [key, group]) as unknown[] ?? [];
  const next = object(setAt(data, [key, group], [...list, record]));
  return applyField(next, doc, field, [key, group, list.length, 'valor'], field.valor.replace(/^-/, ''), '');
}
export function appendVacation(data: Obj, doc: ExtractedDocument, field: ExtractedField, titular: boolean, chosenEnd?: string): Obj {
  if (field.cancelada) throw new Error('Parcela cancelada: confira a situação e informe manualmente apenas o período aplicável, com justificativa.');
  const end = field.fim ?? chosenEnd;
  if (!data.substituicao || !field.inicio || !end) throw new Error('Confira as datas e escolha explicitamente o fim do período.');
  if (!field.fim && ![field.fim_informado, field.fim_calculado].includes(end)) throw new Error('O fim escolhido precisa corresponder a um candidato observado.');
  const group = titular ? 'afastamentos_titular' : 'impedimentos_substituto';
  const rows = getAt(data, ['substituicao', group]) as unknown[] ?? [];
  const row = { ...emptySourcePeriod(), origem: doc.nome_arquivo, localizador: field.localizador, motivo: '' };
  let next = object(setAt(data, ['substituicao', group], [...rows, row]));
  next = applyField(next, doc, field, ['substituicao', group, rows.length, 'inicio'], field.inicio, 'Início observado da programação; aplicabilidade será conferida pelo RH.');
  return applyField(next, doc, field, ['substituicao', group, rows.length, 'ultimo_dia_considerado'], end, field.fim ? 'Fim conferido a partir dos dados da programação; não comprova gozo.' : 'Fim escolhido explicitamente entre os candidatos da programação; aplicabilidade conferida pelo RH, sem presumir gozo.');
}
export function syncApplications(data: Obj): Obj {
  const review = data.revisao_extracao as ExtractionReview | undefined;
  if (!review) return data;
  const updated = structuredClone(review);
  updated.confirmado = false;
  updated.aplicacoes = updated.aplicacoes.flatMap(application => {
    const path = [...application.destino];
    const rowIndex = path.findIndex(key => typeof key === 'number');
    if (application.registro_id && rowIndex >= 0) {
      const rows = getAt(data, path.slice(0, rowIndex)) as Obj[] | undefined;
      const index = rows?.findIndex(row => row.id === application.registro_id) ?? -1;
      if (index < 0) return [];
      path[rowIndex] = index;
    }
    return [{ ...application, destino: path, valor_revisado: String(getAt(data, path) ?? '') }];
  });
  return { ...data, revisao_extracao: updated };
}

export function onlyGlobalApprovalChanged(before: Obj, after: Obj, path: Path): boolean {
  if (path.length !== 1) return false;
  const key = String(path[0]);
  const flag = key === 'revisao_extracao' ? 'confirmado' : 'conferido_pelo_rh';
  if (!(flag in object(before[key])) || !(flag in object(after[key]))) return false;
  return JSON.stringify({ ...object(before[key]), [flag]: false }) === JSON.stringify({ ...object(after[key]), [flag]: false });
}
