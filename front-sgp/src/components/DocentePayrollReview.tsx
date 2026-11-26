import { useState } from 'react';
import { apiBaseUrl } from '../utils/api';
import { apiErrorDetails } from '../utils/apiErrors';
import { components, missingPayroll, payrollFieldErrors, type Component } from '../utils/docentePayroll';
import { object, type Obj, type Path } from '../utils/documentExtraction';
import { reviewedPayrollMonths } from '../utils/progressionReviewValidation';
import { serializeReviewData } from '../utils/reviewData';
import { formatCurrency } from '../utils/presentation';
import { Button, SelectField, TextField } from './ui';
import { ProgressionFinancialReview } from './ProgressionFinancialReview';

interface Line { inicio: string; fim: string; componente: string; pago: string; destino: string; diferenca: string; fonte: string }

export function DocentePayrollReview({ data, disabled, onChange, showErrors }: {
  data: Obj; disabled: boolean; onChange: (path: Path, value: unknown) => void; showErrors: boolean;
}) {
  const [selected, select] = useState('');
  const [preview, setPreview] = useState<{ input: Obj; lines?: Line[]; error?: string }>();
  const months = reviewedPayrollMonths(data);
  const active = months.find(m => m.competencia === selected) ?? months[0];
  const missing = missingPayroll(months);
  const firstPending = months.find(m => missingPayroll([m]));
  const gap = months.findIndex(month => components.some(c => !month[c].candidate || !month[c].value.valor));
  const covered = gap > 0 ? months[gap - 1].competencia : '';
  const [year, month] = covered.split('-').map(Number);
  const lastCovered = covered ? covered + '-' + new Date(Date.UTC(year, month, 0)).getUTCDate() : '';
  const confirmed = object(data.progressao).conferido_pelo_rh === true;
  const current = preview?.input === data ? preview : undefined;
  const observed = <ProgressionFinancialReview data={data} onChange={onChange} disabled={disabled} observationsOnly />;
  const edit = (c: Component, key: string, value: string) => {
    if (!active) return;
    const old = object(object(object(data.edicoes_folha_docente)[active.competencia])[c]);
    const initial = { ...active[c].value };
    if (!Object.keys(old).length && key === 'valor') initial.justificativa = '';
    const candidate = active[c].candidate;
    onChange(['edicoes_folha_docente', active.competencia, c], {
      ...initial, [key]: value, documento_id: candidate?.doc.id, campo_id: candidate?.field.id,
    });
  };
  const load = async () => {
    setPreview({ input: data });
    try {
      const plan = serializeReviewData(data).progressao;
      const response = await fetch(apiBaseUrl + '/api/calculos/progressao/previa-folha', {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(plan),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(apiErrorDetails(body, 'Não foi possível consultar a tabela.').message);
      if (!Array.isArray(body?.parcelas)) throw new Error('A consulta não retornou o comparativo da folha.');
      setPreview({ input: data, lines: body.parcelas });
    } catch (error) { setPreview({ input: data, error: (error as Error).message }); }
  };
  return <section className="space-y-3" aria-label="Comparação da folha docente">
    <h3 className="subsection-title">Remuneração paga por competência</h3>
    <p className="help-text">Confira o VB e a RT mensais integrais. Se a folha traz valor proporcional, misto ou estorno, informe a base integral e registre a fonte. O cálculo aplica a fração do mês uma única vez.</p>
    {active && <>
      <SelectField label="Competência da apuração" value={active.competencia} onChange={e => select(e.target.value)}>
        {months.map(m => <option key={m.competencia} value={m.competencia}>{m.competencia}{missingPayroll([m]) ? ' · pendente' : ''}</option>)}
      </SelectField>
      <div className="form-grid">{components.map(c => {
        const label = c === 'vb' ? 'VB pago' : 'RT paga';
        const article = c === 'vb' ? 'do ' : 'da ';
        const cell = active[c];
        const errors = payrollFieldErrors(cell.value);
        const isEdited = !!object(object(data.edicoes_folha_docente)[active.competencia])[c];
        return <fieldset key={c} className="space-y-2">
          <TextField label={label + ' no mês (R$)'} disabled={disabled} inputMode="decimal" value={cell.value.valor}
            error={showErrors ? errors.valor : undefined}
            hint={cell.candidate ? cell.candidate.doc.nome_arquivo + ' · pág. ' + cell.candidate.field.pagina + ' · observado R$ ' + cell.candidate.field.valor : undefined}
            onChange={e => edit(c, 'valor', e.target.value)} />
          {(!cell.candidate || isEdited || errors.fonte || errors.justificativa) && <>
            <TextField label={'Fonte ' + article + label} disabled={disabled} error={showErrors ? errors.fonte : undefined} maxLength={300} value={cell.value.fonte} onChange={e => edit(c, 'fonte', e.target.value)} />
            <TextField label={'Justificativa ' + article + label} disabled={disabled} error={showErrors ? errors.justificativa : undefined} maxLength={500} value={cell.value.justificativa} onChange={e => edit(c, 'justificativa', e.target.value)} />
          </>}
        </fieldset>;
      })}</div>
    </>}
    {missing && <p className="help-text" role="status">{missing}</p>}
    {firstPending && firstPending !== active && <Button variant="secondary" disabled={disabled} onClick={() => select(firstPending.competencia)}>
      Revisar primeira competência pendente ({firstPending.competencia})
    </Button>}
    {missing && lastCovered && <Button variant="quiet" disabled={disabled} onClick={() => {
      const plan = object(data.progressao);
      onChange(['progressao'], { ...plan, periodo: { ...object(plan.periodo), ultimo_dia_considerado: lastCovered }, conferido_pelo_rh: false });
    }}>Limitar ao último mês consecutivo com VB e RT na ficha ({lastCovered.split('-').reverse().join('/')})</Button>}
    {active ? <details><summary>Rubricas observadas na ficha financeira</summary>{observed}</details> : observed}
    <Button variant="secondary" disabled={disabled || !!missing || !confirmed || (!!current && !current.lines && !current.error)} onClick={load}>Conferir diferenças com a tabela</Button>
    {!missing && !confirmed && <p className="help-text">Confirme os dados do cálculo para consultar a prévia.</p>}
    {current?.error && <p role="alert">{current.error}</p>}
    {current?.lines && active && <ul className="space-y-2 text-sm" aria-label="Comparação com a tabela">{current.lines.filter(r => r.inicio.slice(0, 7) === active.competencia).map(r =>
      <li key={r.inicio + r.componente}><strong>{r.componente} · {r.inicio} a {r.fim}</strong><br />
        Pago mensal {formatCurrency(r.pago)} · Destino mensal {formatCurrency(r.destino)} · Diferença do período {formatCurrency(r.diferenca)}<br />{r.fonte}</li>)}</ul>}
  </section>;
}
