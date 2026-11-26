import { object, type Application, type ExtractedDocument, type ExtractedField, type ExtractionReview, type Obj } from './documentExtraction';

export const components = ['vb', 'rt'] as const;
export type Component = typeof components[number];
interface Value { valor: string; fonte: string; localizador: string; justificativa: string }
interface Candidate { doc: ExtractedDocument; field: ExtractedField }
interface Cell { value: Value; candidate?: Candidate }
interface Month { competencia: string; id: string; vb: Cell; rt: Cell }

function componentOf(field: ExtractedField): Component | undefined {
  if (field.campo !== 'rubrica') return;
  if (field.rubrica === '00001') return 'vb';
  if (field.rubrica === '82606') return 'rt';
}

export function payrollMonths(entries: Obj, review?: ExtractionReview): Month[] {
  const plan = object(entries.progressao);
  const period = object(plan.periodo);
  const first = String(period.inicio ?? '').slice(0, 7);
  const last = String(period.ultimo_dia_considerado ?? '').slice(0, 7);
  const monthIndex = (s: string) => Number(s.slice(0, 4)) * 12 + Number(s.slice(5)) - 1;
  if (![first, last].every(s => /^\d{4}-(0[1-9]|1[0-2])$/.test(s))) return [];
  const count = monthIndex(last) - monthIndex(first) + 1;
  if (count < 1 || count > 120) return [];
  const candidates = new Map<string, Candidate[]>();
  for (const doc of review?.documentos ?? []) {
    const blocks = new Set(doc.blocos.filter(b => b.categoria === 'DOCENTE' &&
      review?.associacoes.some(a => a.documento_id === doc.id && a.bloco_id === b.id && a.pessoa === 'SERVIDOR')).map(b => b.id));
    for (const field of doc.campos) {
      const component = componentOf(field);
      if (!component || !blocks.has(field.bloco_id)) continue;
      const key = field.competencia + component;
      if (!candidates.has(key)) candidates.set(key, []);
      candidates.get(key)!.push({ doc, field });
    }
  }
  const existing: Obj[] = Array.isArray(plan.bases_mensais_origem) ? plan.bases_mensais_origem : [];
  return Array.from({ length: count }, (_, offset) => {
    const index = monthIndex(first) + offset;
    const competencia = Math.floor(index / 12) + '-' + String(index % 12 + 1).padStart(2, '0');
    const saved = existing.find(row => row.competencia === competencia);
    const id = String(saved?.id ?? 'folha-' + competencia);
    const cell = (component: Component): Cell => {
      const options = candidates.get(competencia + component) ?? [];
      const candidate = options.length === 1 ? options[0] : undefined;
      const f = candidate?.field;
      const amount = f?.correcao?.valor ?? f?.valor;
      const observed = candidate && f && f.pagina && f.natureza === 'R' && f.sequencia === '0' &&
        (f.estado === 'EXTRAIDO' || f.correcao) && amount != null && /^\d+(?:\.\d{1,2})?$/.test(amount)
        ? { value: { valor: amount, fonte: candidate.doc.nome_arquivo, localizador: f.localizador || 'Página ' + f.pagina,
          justificativa: f.correcao?.justificativa ?? 'Base mensal integral conferida na ficha financeira.' }, candidate } : undefined;
      const edited = object(object(object(entries.edicoes_folha_docente)[competencia])[component]);
      const previous = object(saved?.[component]);
      if (!Object.keys(edited).length && observed && (!saved || !Object.keys(previous).length)) return observed;
      const base = Object.keys(edited).length ? edited : (options.length > 1 ? {} : previous);
      const linked = Object.keys(edited).length
        ? candidate && edited.documento_id === candidate.doc.id && edited.campo_id === candidate.field.id
        : review?.aplicacoes.some(a =>
        a.registro_id === id && a.documento_id === candidate?.doc.id && a.campo_id === candidate?.field.id &&
        a.destino[0] === 'progressao' && a.destino[1] === 'bases_mensais_origem' && a.destino[3] === component);
      return { value: { valor: String(base.valor ?? ''), fonte: String(base.fonte ?? ''),
        localizador: String(base.localizador ?? competencia), justificativa: String(base.justificativa ?? '') }, candidate: linked ? observed?.candidate : undefined };
    };
    return { competencia, id, vb: cell('vb'), rt: cell('rt') };
  });
}

export function payrollFieldErrors(value: Value) {
  return {
    valor: /^(?:\d+(?:[.,]\d{1,2})?|\d{1,3}(?:\.\d{3})+,\d{1,2})$/.test(value.valor.trim()) ? undefined : 'Informe o valor mensal em reais, inclusive zero quando confirmado.',
    fonte: value.fonte.trim() ? undefined : 'Informe a fonte deste valor.',
    justificativa: value.justificativa.trim() ? undefined : 'Informe o motivo do preenchimento manual ou da correção.',
  };
}

export function missingPayroll(months: Month[]): string {
  if (!months.length) return 'Confira as datas da apuração e o limite de 120 competências.';
  const pending = months.flatMap(m => {
    const missing = components.filter(c => Object.values(payrollFieldErrors(m[c].value)).some(Boolean));
    return missing.length ? [m.competencia + ' (' + missing.join('/').toUpperCase() + ')'] : [];
  });
  return pending.length ? 'Confira os valores integrais da folha, a fonte e a justificativa em ' + pending.slice(0, 3).join(', ') +
    (pending.length > 3 ? ' e mais ' + (pending.length - 3) + ' competências.' : '.') : '';
}

export function payrollPayload(months: Month[], confirmed: boolean) {
  const applications: Application[] = [];
  const rows = months.map((m, index) => {
    for (const c of components) {
      const { candidate, value } = m[c];
      if (candidate) applications.push({ documento_id: candidate.doc.id, campo_id: candidate.field.id, registro_id: m.id,
        destino: ['progressao', 'bases_mensais_origem', index, c, 'valor'], valor_revisado: value.valor, justificativa: value.justificativa });
    }
    return { id: m.id, competencia: m.competencia, vb: m.vb.value, rt: m.rt.value, base_mensal_integral_confirmada: confirmed };
  });
  return { rows, applications };
}
