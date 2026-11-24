import { SelectField, TextField } from './ui';
import { emptyAdditional, emptyManualValue } from '../utils/periodReviewData';

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => v && typeof v === 'object' ? v as Obj : {};

export function AdditionalConcessionFields({ value, onChange, disabled, getError = () => undefined }: { value: unknown; onChange: (value: unknown) => void; disabled: boolean; getError?: (path: string[]) => string | undefined }) {
  const data = obj(value), base = obj(data.base), rule = obj(data.regra);
  const update = (key: string, value: unknown) => onChange({ ...data, [key]: value, ...(['percentual', 'especie', 'descricao'].includes(key) ? { percentual_confirmado: false } : {}) });
  const text = (target: Obj, key: string, label: string, set: (key: string, value: unknown) => void, prefix: string[] = [], type = 'text') => <TextField label={label} type={type} value={String(target[key] ?? '')} disabled={disabled} error={getError([...prefix, key])} onChange={e => set(key, e.target.value)} />;
  const baseSet = (key: string, value: unknown) => update('base', { ...base, [key]: value, confirmada: false });
  const ruleSet = (key: string, value: unknown) => update('regra', { ...rule, [key]: value, confirmada: false });
  return <fieldset className="space-y-4"><legend className="subsection-title">Concessão do adicional</legend>
    <label className="block"><input type="checkbox" checked={Boolean(value)} disabled={disabled} onChange={e => onChange(e.target.checked ? emptyAdditional() : null)} /> Informar concessão do adicional</label>
    {Boolean(value) && <>
      <p className="help-text">Use a mesma identificação da concessão nos fluxos de adicional e progressão. A razão adicional/VB é apenas sugestão e não comprova direito.</p>
      <div className="form-grid">{text(data, 'identificador', 'Identificação única da concessão', update)}
        <SelectField label="Espécie do adicional" disabled={disabled} value={String(data.especie ?? '')} error={getError(['especie'])} onChange={e => update('especie', e.target.value)}><option value="">Selecione</option>{Object.entries({ INSALUBRIDADE: 'Insalubridade', PERICULOSIDADE: 'Periculosidade', IRRADIACAO: 'Irradiação ionizante', RAIOS_X: 'Raios X', OUTRO: 'Outro, conforme regra conferida' }).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</SelectField>
        {data.especie === 'OUTRO' && text(data, 'descricao', 'Descrição do adicional', update)}
        {text(data, 'percentual', 'Percentual confirmado do adicional', update)}
        {text(data, 'inicio_vigencia', 'Início da vigência da concessão', update, [], 'date')}{text(data, 'fim_vigencia', 'Fim da vigência da concessão (opcional)', update, [], 'date')}
      </div>
      <label className="block"><input type="checkbox" checked={data.percentual_confirmado === true} disabled={disabled} onChange={e => update('percentual_confirmado', e.target.checked)} /> Conferi a espécie e o percentual no documento de concessão.</label>
      <SelectField label="Base do adicional" disabled={disabled} value={String(base.tipo ?? '')} error={getError(['base', 'tipo'])} onChange={e => update('base', { tipo: e.target.value, confirmada: false, ...(e.target.value === 'VALOR_CONFIRMADO' ? { valor_manual: emptyManualValue() } : {}) })}><option value="">Selecione</option><option value="VB">Somente VB</option><option value="VB_RT">VB e RT, discriminados</option><option value="VALOR_CONFIRMADO">Outra base com valor e fonte conferidos</option></SelectField>
      {base.tipo === 'VALOR_CONFIRMADO' && <div className="form-grid">{['valor', 'fonte', 'localizador'].map(key => <div key={key}>{text(obj(base.valor_manual), key, ({ valor: 'Valor da base', fonte: 'Fonte da base', localizador: 'Página, aba ou linha da base' })[key]!, (k, v) => baseSet('valor_manual', { ...obj(base.valor_manual), [k]: v }), ['base', 'valor_manual'])}</div>)}</div>}
      <label className="block"><input type="checkbox" checked={base.confirmada === true} disabled={disabled} onChange={e => update('base', { ...base, confirmada: e.target.checked })} /> Conferi a base aplicável ao adicional.</label>
      <div className="form-grid">{text(rule, 'identificador', 'Identificação da regra do adicional', ruleSet, ['regra'])}{text(rule, 'versao', 'Versão da regra do adicional', ruleSet, ['regra'])}{text(rule, 'fonte', 'Fonte da regra do adicional', ruleSet, ['regra'])}{text(rule, 'inicio_vigencia', 'Início dos efeitos da regra do adicional', ruleSet, ['regra'], 'date')}{text(rule, 'fim_vigencia', 'Fim dos efeitos da regra do adicional (opcional)', ruleSet, ['regra'], 'date')}</div>
      <label className="block"><input type="checkbox" checked={rule.confirmada === true} disabled={disabled} onChange={e => update('regra', { ...rule, confirmada: e.target.checked })} /> Conferi a regra e seus efeitos financeiros.</label>
    </>}
  </fieldset>;
}
