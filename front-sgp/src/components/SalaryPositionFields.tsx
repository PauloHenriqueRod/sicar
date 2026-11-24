import { SelectField, TextField } from './ui';

import type { SalaryPosition } from '../utils/salaryReferences';
export function SalaryPositionFields({ value, onChange, disabled = false, date = false, getError = () => undefined, allowedCareers }: {
  value: SalaryPosition; onChange: (value: SalaryPosition) => void; disabled?: boolean; date?: boolean;
  getError?: (key: string) => string | undefined;
  allowedCareers?: string[];
}) {
  const field = (key: string, label: string, type = 'text') => <TextField key={key} label={label} type={type} disabled={disabled} error={getError(key)}
    value={value[key] ?? ''} onChange={e => onChange({ ...value, [key]: e.target.value })} />;
  return <div className="form-grid">
    <SelectField label="Carreira" disabled={disabled} error={getError('carreira')} value={value.carreira ?? ''} onChange={e => {
      const next: SalaryPosition = { ...value, carreira: e.target.value };
      for (const key of ['classificacao_tae', 'capacitacao_tae', 'padrao_tae', 'classe_docente', 'nivel_docente']) delete next[key];
      onChange(next);
    }}><option value="">Selecione</option>{[['TAE', 'TAE'], ['MAGISTERIO_SUPERIOR', 'Magistério superior'], ['EBTT', 'EBTT']].filter(([key]) => !allowedCareers || allowedCareers.includes(key)).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</SelectField>
    {field('vinculo', 'Vínculo (conforme a tabela)')}
    <SelectField label="Jornada ou regime" disabled={disabled} error={getError('jornada')} value={value.jornada ?? ''} onChange={e => onChange({ ...value, jornada: e.target.value })}>
      <option value="">Selecione</option>{['20H', '24H', '25H', '30H', '40H', ...(value.carreira === 'TAE' ? [] : ['DE'])].map(v => <option key={v}>{v}</option>)}
    </SelectField>
    {field('versao_carreira', 'Estrutura histórica da carreira', 'text')}
    {value.carreira === 'TAE' ? <>
      <SelectField label="Classificação TAE" disabled={disabled} error={getError('classificacao_tae')} value={value.classificacao_tae ?? ''} onChange={e => onChange({ ...value, classificacao_tae: e.target.value })}><option value="">Selecione</option>{['A', 'B', 'C', 'D', 'E'].map(v => <option key={v}>{v}</option>)}</SelectField>
      {field('capacitacao_tae', 'Capacitação TAE (quando aplicável)')}{field('padrao_tae', 'Padrão TAE', 'number')}
    </> : value.carreira ? <>{field('classe_docente', 'Classe docente')}{field('nivel_docente', 'Nível docente', 'number')}</> : null}
    {date && field('data_referencia', 'Data salarial consultada', 'date')}
  </div>;
}
