import { useState } from 'react';
import { Button, SelectField } from './ui';
import { applyField, object } from '../utils/documentExtraction';
import { formatCurrency } from '../utils/presentation';
import type { ExtractionReview, Obj, Path } from '../utils/documentExtraction';

/** Observações da ficha: nunca são automaticamente recebimentos da diferença. */
export function ProgressionFinancialReview({ data, onChange, disabled }: {
  data: Obj; onChange: (path: Path, value: unknown) => void; disabled: boolean;
}) {
  const review = data.revisao_extracao as ExtractionReview | undefined;
  const [source, setSource] = useState('');
  const [month, setMonth] = useState('');
  const [error, setError] = useState('');
  const [showOther, setShowOther] = useState(false);
  const sources = review?.documentos.flatMap(doc => doc.blocos
    .filter(block => doc.campos.some(f => f.bloco_id === block.id && f.campo === 'rubrica'))
    .map(block => ({ doc, block, key: `${doc.id}/${block.id}` }))) ?? [];
  const selected = sources.find(item => item.key === source) ?? (sources.length === 1 ? sources[0] : undefined);
  const fields = selected?.doc.campos.filter(f => f.bloco_id === selected.block.id && f.campo === 'rubrica') ?? [];
  const months = [...new Set(fields.flatMap(f => f.competencia ? [f.competencia] : []))].sort().reverse();
  const monthRows = fields.filter(f => f.competencia === month);
  const usedCodes = (object(data.progressao).rubricas as Obj[] | undefined)?.map(row => row.rubrica) ?? [];
  const rows = monthRows.filter(f => showOther || f.rubrica === '00001' || usedCodes.includes(f.rubrica) || /VENCIMENTO|RETRIB|TITUL|ANU[EÊ]N|INSALUBR|PERICUL|F[EÉ]RIAS|13|NATALIN/i.test(f.descricao_rubrica ?? ''));
  const state = object(object(data.progressao).estado_inicial);
  if (object(data.progressao).modalidade === 'TAE') return null;
  return <section className="mb-6 space-y-4" aria-label="Remuneração observada na ficha financeira">
    <h3 className="subsection-title">Valores da ficha financeira</h3>
    <p className="help-text">Escolha o mês para conferir os valores. Use uma sugestão após revisar a fonte; os campos do cálculo continuam editáveis.</p>
    {!sources.length ? <p className="help-text">Sem valores financeiros extraídos. Informe VB e RT manualmente na posição de origem ou utilize uma referência salarial confirmada.</p> : <>
      {sources.length > 1 && <SelectField label="Ficha e servidor para conferência" value={source} disabled={disabled} onChange={e => { setSource(e.target.value); setMonth(''); }}><option value="">Selecione</option>{sources.map(item => <option key={item.key} value={item.key}>{item.doc.nome_arquivo} — {item.block.nome || 'Identificação pendente'}</option>)}</SelectField>}
      <SelectField label="Mês e ano da ficha financeira" value={month} disabled={disabled || !selected} onChange={e => setMonth(e.target.value)}><option value="">Selecione o mês</option>{months.map(item => <option key={item} value={item}>{item.slice(5)}/{item.slice(0, 4)}</option>)}</SelectField>
      <details className="text-sm"><summary>Preencher bases mensais com os valores desta ficha</summary><p className="help-text my-3">Prepara os meses do período informado. Cada base precisa de conferência; valores já preenchidos são preservados.</p><Button variant="secondary" disabled={disabled || !selected} onClick={() => {
        try {
          const period = object(object(data.progressao).periodo);
          if (!period.inicio || !period.ultimo_dia_considerado) throw new Error('Informe o início e o último dia da apuração antes de preparar as bases mensais.');
          let next = data;
          for (const competence of months.filter(m => m >= String(period.inicio).slice(0, 7) && m <= String(period.ultimo_dia_considerado).slice(0, 7))) {
            const candidates = fields.filter(f => f.competencia === competence && f.rubrica === '00001');
            if (candidates.length !== 1) continue;
            const field = candidates[0];
            if (field.estado !== 'EXTRAIDO' || field.natureza !== 'R' || field.sequencia !== '0' || field.valor == null || field.valor.startsWith('-')) continue;
            const plan = object(next.progressao);
            const existing = Array.isArray(plan.bases_mensais_origem) ? plan.bases_mensais_origem as Obj[] : [];
            if (existing.some(row => row.competencia === competence)) continue;
            if (existing.length >= 120) throw new Error('Divida a apuração: limite de 120 bases mensais.');
            const row = { id: crypto.randomUUID(), competencia: competence, vb: { valor: '', fonte: selected!.doc.nome_arquivo, localizador: field.localizador, justificativa: '' }, base_mensal_integral_confirmada: false };
            next = applyField({ ...next, progressao: { ...plan, bases_mensais_origem: [...existing, row], conferido_pelo_rh: false } }, selected!.doc, field, ['progressao', 'bases_mensais_origem', existing.length, 'vb', 'valor'], field.valor);
          }
          if (next === data) throw new Error('Nenhuma base nova inequívoca no período. Confira duplicidades, competências e bases já preenchidas.');
          onChange([], next); setError('');
        } catch (e) { setError((e as Error).message); }
      }}>Preparar VB por competência desta ficha</Button></details>
      {selected && month && <div className="overflow-x-auto"><label className="block text-sm mb-3"><input type="checkbox" checked={showOther} disabled={disabled} onChange={e => setShowOther(e.target.checked)} /> Ver outras rubricas do mês</label><table role="table" className="block w-full text-sm sm:table"><caption className="text-left help-text break-words mb-3">{selected.doc.nome_arquivo} · {month.slice(5)}/{month.slice(0, 4)}</caption><thead role="rowgroup" className="block sm:table-header-group"><tr role="row" className="grid grid-cols-[minmax(0,1fr)_auto] sm:table-row"><th role="columnheader" scope="col" className="text-left p-2">Rubrica</th><th role="columnheader" scope="col" className="text-right p-2">Valor</th><th role="columnheader" scope="col" className="hidden text-left p-2 sm:table-cell">Conferência</th></tr></thead><tbody role="rowgroup" className="block sm:table-row-group">{rows.map(field => {
        const component = field.rubrica === '00001' ? 'vb_manual' : /RETRIB.*TITUL|RET[. ]*TITUL|^RT\b/i.test(field.descricao_rubrica ?? '') ? 'rt_manual' : undefined;
        const unique = component && monthRows.filter(f => (component === 'vb_manual' ? f.rubrica === '00001' : /RETRIB.*TITUL|RET[. ]*TITUL|^RT\b/i.test(f.descricao_rubrica ?? ''))).length === 1;
        const eligible = unique && field.estado === 'EXTRAIDO' && field.natureza === 'R' && field.sequencia === '0' && field.valor != null && (object(state[component!]).valor == null || object(state[component!]).valor === '');
        const monthlyRows = Array.isArray(object(data.progressao).bases_mensais_origem) ? object(data.progressao).bases_mensais_origem as Obj[] : [];
        return <tr role="row" key={field.id} className="grid grid-cols-[minmax(0,1fr)_auto] border-t border-outline align-top sm:table-row"><td role="cell" className="min-w-0 p-2 break-words">{field.descricao_rubrica || 'Descrição ausente'}<span className="block help-text">{field.rubrica} · {field.natureza === 'D' ? 'Desconto' : field.natureza === 'R' ? 'Rendimento' : 'Natureza pendente'}</span></td><td role="cell" className="p-2 text-right tabular-nums whitespace-nowrap font-medium">{field.valor == null ? 'Revisar' : /^-?\d+\.\d{2}$/.test(field.valor) ? formatCurrency(field.valor) : field.valor}{field.estado !== 'EXTRAIDO' && <span className="block text-sm text-warning">Conferir valor</span>}</td><td role="cell" className="col-span-2 p-2"><details><summary className="cursor-pointer">{component ? 'Conferir e usar' : 'Ver origem'}</summary><p className="help-text my-2">Página {field.pagina ?? '?'} · sequência {field.sequencia ?? 'pendente'}</p><div className="flex flex-col items-start gap-2">{component === 'vb_manual' && <Button variant="secondary" disabled={disabled || !unique || field.estado !== 'EXTRAIDO' || field.natureza !== 'R' || field.sequencia !== '0' || field.valor == null || field.valor.startsWith('-') || monthlyRows.some(row => row.competencia === month) || monthlyRows.length >= 120} onClick={() => {
          try {
            const row = { id: crypto.randomUUID(), competencia: month, vb: { valor: '', fonte: selected.doc.nome_arquivo, localizador: field.localizador, justificativa: '' }, base_mensal_integral_confirmada: false };
            const next = { ...data, progressao: { ...object(data.progressao), bases_mensais_origem: [...monthlyRows, row], conferido_pelo_rh: false } };
            onChange([], applyField(next, selected.doc, field, ['progressao', 'bases_mensais_origem', monthlyRows.length, 'vb', 'valor'], field.valor!)); setError('');
          } catch (e) { setError((e as Error).message); }
        }}>Usar VB nesta competência</Button>}{component && <Button variant="quiet" disabled={disabled || !eligible} onClick={() => {
          try {
            const plan = object(data.progressao);
            const next = { ...data, progressao: { ...plan, conferido_pelo_rh: false, estado_inicial: { ...state, [component]: { valor: '', fonte: selected.doc.nome_arquivo, localizador: field.localizador, justificativa: 'Base sugerida pela ficha financeira; sujeita à conferência do RH.' } } } };
            const applied = applyField(next, selected.doc, field, ['progressao', 'estado_inicial', component, 'valor'], field.valor!);
            onChange([], applied); setError('');
          } catch (e) { setError((e as Error).message); }
        }}>Usar como {component === 'vb_manual' ? 'VB' : 'RT'} de origem</Button>}</div></details></td></tr>;
      })}</tbody></table>{!rows.length && <p>Nenhuma rubrica nesta competência.</p>}</div>}
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
