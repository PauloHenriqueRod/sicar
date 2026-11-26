import { docenteEventId, getAt, identityKey, object, type ExtractionReview, type Obj, type Path } from './documentExtraction';
import { missingPayroll, payrollMonths } from './docentePayroll';

export function isMonthlyProgression(entries: Obj): boolean {
  const plan = object(entries.progressao);
  if (!entries.progressao || plan.modalidade === 'TAE' || entries.revisao_docente_detalhada === true) return false;
  // Registros com abatimentos, interrupções ou eventos independentes precisam da revisão detalhada.
  if ([plan.recebidos, plan.interrupcoes].some(rows => Array.isArray(rows) && rows.length) ||
      object(plan.estado_inicial).adicional ||
      (Array.isArray(plan.rubricas) && plan.rubricas.some(row => !String(object(row).rubrica).startsWith('DIF-'))) ||
      (Array.isArray(plan.eventos) && plan.eventos.some(row => object(row).id !== docenteEventId))) return false;
  const documents = (entries.revisao_extracao as ExtractionReview | undefined)?.documentos ?? [];
  if (plan.modalidade === 'DOCENTE') return true;
  return documents.some(doc => doc.campos.some(field => field.leitor_id === 'portaria_docente_progressao') ||
    (doc.layout === 'FICHA_SIAPE' && doc.blocos.some(block => block.categoria === 'DOCENTE')));
}

export function singleDocenteReview(entries: Obj): ExtractionReview {
  const review = entries.revisao_extracao as ExtractionReview;
  const matricula = String(entries.matricula ?? '').trim();
  const nome = String(entries.nome ?? '').trim();
  if (!matricula || !nome) throw new Error('Confira o nome e a matrícula do docente.');
  const nameKey = (name: string) => name.trim().replace(/\s+/g, ' ').toLocaleLowerCase('pt-BR');
  const correctedName = review.aplicacoes.find(a => a.destino.length === 1 && a.destino[0] === 'nome' &&
    a.valor_revisado === nome && a.justificativa.trim());
  const nameDoc = correctedName && review.documentos.find(d => d.id === correctedName.documento_id);
  const nameField = nameDoc?.campos.find(f => f.id === correctedName?.campo_id && f.campo === 'nome');
  const documentedName = nameField?.valor && nameDoc?.blocos.some(b => b.id === nameField.bloco_id &&
    b.matricula && identityKey(b.matricula) === identityKey(matricula)) ? nameKey(nameField.valor) : nameKey(nome);
  const links = new Set<string>();
  const associationKey = 'SIAPE ' + matricula;
  if (review.vinculo_calculo && review.vinculo_calculo !== associationKey) links.add(review.vinculo_calculo);
  const confirmed = object(entries.progressao).conferido_pelo_rh === true;
  const associations = review.documentos.flatMap(doc => doc.blocos.map(block => {
    const saved = review.associacoes.find(a => a.documento_id === doc.id && a.bloco_id === block.id);
    if (saved?.pessoa === 'DESCARTADO' && saved.confirmado && saved.justificativa.trim()) return saved;
    if (block.papel_documental === 'TITULAR' || ['TAE', 'SUBSTITUTO'].includes(block.categoria) || (saved && saved.pessoa !== 'SERVIDOR') ||
        (!block.matricula && !block.nome) ||
        [block.matricula, saved?.matricula].some(n => n && identityKey(n) !== identityKey(matricula)) ||
        (block.nome && nameKey(block.nome) !== documentedName)) {
      throw new Error('A identificação de um documento diverge do docente ou está ausente. Confira os anexos ou use a revisão com eventos independentes.');
    }
    if (block.vinculo) links.add(block.vinculo);
    if (saved?.vinculo && saved.vinculo !== associationKey) links.add(saved.vinculo);
    return { documento_id: doc.id, bloco_id: block.id, pessoa: 'SERVIDOR' as const, matricula,
      vinculo: '', confirmado: confirmed, justificativa: saved?.justificativa ||
        (!block.matricula || !block.vinculo ? 'Vínculo único conferido pelo RH a partir dos documentos deste cálculo.' : '') };
  }));
  if (links.size > 1) throw new Error('Os documentos identificam vínculos diferentes. Confira os anexos deste cálculo.');
  const link = [...links][0] ?? associationKey;
  return { ...review, confirmado: confirmed, vinculo_calculo: link,
    associacoes: associations.map(a => a.pessoa === 'DESCARTADO' ? a : { ...a, vinculo: link }) };
}

export function docenteDestinationSource(entries: Obj): string | undefined {
  const review = entries.revisao_extracao as ExtractionReview | undefined;
  const application = review?.aplicacoes.find(a => a.registro_id === docenteEventId && a.destino.at(-1) === 'classe_docente');
  const doc = application && review?.documentos.find(d => d.id === application.documento_id);
  const field = doc?.campos.find(f => f.id === application?.campo_id);
  if (!doc || !field?.pagina) return;
  const names = doc.campos.filter(f => f.bloco_id === field.bloco_id && f.pagina === field.pagina && f.leitor_id === field.leitor_id && f.campo === 'denominacao_destino');
  const name = names.length === 1 && names[0].estado === 'EXTRAIDO' ? names[0].valor : '';
  return [name, doc.nome_arquivo, 'página ' + field.pagina].filter(Boolean).join(' · ');
}

/** O VB da competência inicial é uma pista de enquadramento, não uma base já confirmada. */
export function docenteInitialBase(entries: Obj): string {
  const plan = object(entries.progressao);
  const month = String(object(plan.periodo).inicio ?? '').slice(0, 7);
  if (!month) return '';
  const manual = object(object(plan.estado_inicial).vb_manual).valor;
  if (manual) return String(manual).replace(',', '.');
  const review = entries.revisao_extracao as ExtractionReview | undefined;
  if (!review) return '';
  try { singleDocenteReview(entries); } catch { return ''; }
  const candidates = review.documentos.flatMap(doc => doc.campos.filter(f => f.campo === 'rubrica' && f.competencia === month && f.rubrica === '00001' &&
    doc.blocos.some(b => b.id === f.bloco_id && b.categoria === 'DOCENTE') &&
    !review.associacoes.some(a => a.documento_id === doc.id && a.bloco_id === f.bloco_id && a.pessoa === 'DESCARTADO')));
  const field = candidates[0];
  if (candidates.length !== 1 || field.estado !== 'EXTRAIDO' || field.natureza !== 'R' || field.sequencia !== '0') return '';
  const value = field.correcao?.valor ?? field.valor ?? '';
  return /^\d+(\.\d{1,2})?$/.test(value) && Number(value) > 0 ? value : '';
}

export function invalidateDocenteOrigin(entries: Obj): Obj {
  const plan = object(entries.progressao);
  const source = object(plan.origem_automatica);
  if (!source.data || (source.data === object(plan.periodo).inicio &&
      (source.vb == null || source.vb === docenteInitialBase(entries)))) return entries;
  const state = object(plan.estado_inicial);
  const revised = { ...plan, estado_inicial: { ...state, posicao: source.posicao_observada }, conferido_pelo_rh: false };
  Reflect.deleteProperty(revised, 'origem_automatica');
  return { ...entries, progressao: revised };
}

export function missingProgressionInputs(entries: Obj): Record<string, string> {
  if (!isMonthlyProgression(entries)) return {};
  const fields: Record<string, string> = {};
  const required = (path: Path, message: string) => {
    if (!String(getAt(entries, path) ?? '').trim()) fields[JSON.stringify(path)] = message;
  };
  if (entries.revisao_extracao) {
    try { singleDocenteReview(entries); }
    catch (error) { fields[JSON.stringify(['matricula'])] = (error as Error).message; }
  }
  const state = ['progressao', 'estado_inicial'];
  const position = [...state, 'posicao'];
  if (!getAt(entries, [...position, 'vinculo']) || !getAt(entries, [...position, 'versao_carreira'])) {
    fields[JSON.stringify(position)] = 'Escolha a posição de origem na tabela vigente para a data inicial.';
  }
  required([...state, 'titulacao'], 'Informe a titulação de origem.');
  required([...state, 'percentual_anuenio'], 'Informe o percentual conferido, inclusive zero quando não houver anuênio.');
  required(['progressao', 'periodo', 'inicio'], 'Informe o primeiro dia da apuração.');
  required(['progressao', 'periodo', 'ultimo_dia_considerado'], 'Informe o último dia da apuração.');
  const evento = ['progressao', 'eventos', 0];
  required([...evento, 'efeitos_financeiros'], 'Informe a data dos efeitos da progressão.');
  required([...evento, 'alteracoes', 'posicao', 'classe_docente'], 'Confira a nova classe na ata ou portaria.');
  required([...evento, 'alteracoes', 'posicao', 'nivel_docente'], 'Confira o novo nível na ata ou portaria.');
  const start = getAt(entries, ['progressao', 'periodo', 'inicio']);
  const last = getAt(entries, ['progressao', 'periodo', 'ultimo_dia_considerado']);
  if (typeof start === 'string' && typeof last === 'string' && last && last < start) {
    fields[JSON.stringify(['progressao', 'periodo', 'ultimo_dia_considerado'])] = 'O último dia considerado deve ser igual ou posterior ao início da apuração.';
  }
  const effective = getAt(entries, [...evento, 'efeitos_financeiros']);
  if (start && effective && start !== effective) fields[JSON.stringify(['progressao', 'periodo', 'inicio'])] = 'Inicie a comparação mensal na data dos efeitos financeiros da progressão.';
  const missing = missingPayroll(reviewedPayrollMonths(entries));
  if (missing) fields[JSON.stringify(['progressao', 'bases_mensais_origem'])] = missing;
  return fields;
}

export function reviewedPayrollMonths(entries: Obj) {
  let review: ExtractionReview | undefined;
  if (entries.revisao_extracao) {
    try { review = singleDocenteReview(entries); } catch { /* A divergência é indicada junto à identificação. */ }
  }
  return payrollMonths(entries, review);
}

export function prepareDocentePlan(entries: Obj): Obj {
  const plan = object(entries.progressao);
  const origin = object(object(plan.estado_inicial).posicao);
  const event = object((plan.eventos as Obj[] | undefined)?.[0]);
  const period = object(plan.periodo);
  const target = object(object(event.alteracoes).posicao);
  const review = entries.revisao_extracao as ExtractionReview | undefined;
  const applied = review?.aplicacoes.find(a => a.registro_id === docenteEventId && a.destino.at(-1) === 'efeitos_financeiros');
  const doc = applied && review?.documentos.find(d => d.id === applied.documento_id);
  const page = doc && doc.campos.find(f => f.id === applied?.campo_id)?.pagina;
  const source = doc && page ? doc.nome_arquivo + ', página ' + page : 'Enquadramento e efeitos informados pelo RH';
  const rule = { identificador: 'DIFERENCA-POSICAO-DOCENTE', versao: '1', fonte: source, inicio_vigencia: period.inicio, fim_vigencia: period.ultimo_dia_considerado };
  const formulas = [['DIF-VB', 'VB'], ['DIF-RT', 'RT']];
  if (Number(String(object(plan.estado_inicial).percentual_anuenio).replace(',', '.')) > 0) formulas.push(['DIF-ANUENIO', 'ANUENIO_SOBRE_VB']);
  return {
    ...plan,
    modalidade: 'DOCENTE',
    eventos: [{ ...event, alteracoes: { posicao: { ...origin, ...target } }, regra: rule }],
    rubricas: formulas.map(([rubrica, formula]) => ({ rubrica, formula, natureza_folha: 'NORMAL', natureza_rubrica: 'R', regra: rule })),
  };
}
