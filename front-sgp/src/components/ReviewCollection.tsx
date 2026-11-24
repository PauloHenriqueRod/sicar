import { useState } from 'react';
import type { ReactNode } from 'react';
import { Button, SelectField, TextField } from './ui';

type CollectionKind = 'valores_anuais' | 'valores_mensais' | 'valores_recebidos';
const payments = {
  '742_salario': 'Salário — rubrica 742',
  '772_ferias': 'Férias — rubrica 772',
  '82696_terco_ferias': 'Adicional de férias — rubrica 82696',
  '82407_decimo_terceiro': '13º salário — rubrica 82407',
};

export function ReviewCollection({ kind, value, disabled, onChange, renderEntry }: {
  kind: CollectionKind;
  value: Record<string, unknown>;
  disabled: boolean;
  onChange: (value: Record<string, unknown>) => void;
  renderEntry: (key: string, value: unknown) => ReactNode;
}) {
  const [key, setKey] = useState('');
  const [error, setError] = useState('');
  const noun = kind === 'valores_anuais' ? 'ano' : kind === 'valores_mensais' ? 'mês' : 'pagamento';
  const add = () => {
    const trimmed = key.trim();
    if (!trimmed || (kind === 'valores_anuais' && !/^[1-9]\d{3}$/.test(trimmed))) {
      setError(kind === 'valores_anuais' ? 'Informe um ano com quatro dígitos.' : `Selecione ou informe o ${noun}.`);
      return;
    }
    if (Object.hasOwn(value, trimmed)) { setError(`Este ${noun} já foi adicionado.`); return; }
    onChange({ ...value, [trimmed]: kind === 'valores_anuais' ? [] : '' });
    setKey('');
    setError('');
  };
  return <div className="space-y-5">
    {Object.entries(value).map(([entryKey, entryValue]) => <div key={entryKey} className="space-y-3 border-b border-outline pb-4">
      {kind === 'valores_anuais' && !/^[1-9]\d{3}$/.test(entryKey) && <p className="help-text">Confirme o ano no documento. Adicione o ano correto e suas contribuições abaixo; depois remova este grupo pendente.</p>}
      {renderEntry(entryKey, entryValue)}
      <Button variant="quiet" disabled={disabled} onClick={() => {
        const next = { ...value }; delete next[entryKey]; onChange(next);
      }}>Remover {noun} {payments[entryKey as keyof typeof payments] || entryKey}</Button>
    </div>)}
    {Object.keys(value).length === 0 && <p className="help-text">Nenhum {noun} informado. Adicione os dados encontrados nos documentos.</p>}
    <div className="flex flex-wrap items-end gap-3">
      {kind === 'valores_recebidos' ? <SelectField label="Pagamento recebido" value={key} disabled={disabled} error={error} onChange={event => { setKey(event.target.value); setError(''); }}>
        <option value="">Selecione a rubrica</option>
        {Object.entries(payments).filter(([code]) => !Object.hasOwn(value, code)).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
      </SelectField> : <TextField label={kind === 'valores_anuais' ? 'Ano a adicionar' : 'Mês a adicionar'} placeholder={kind === 'valores_anuais' ? '2026' : 'Ex.: 2026-01'} inputMode={kind === 'valores_anuais' ? 'numeric' : undefined} value={key} disabled={disabled} error={error} onChange={event => { setKey(event.target.value); setError(''); }} />}
      <Button variant="secondary" disabled={disabled} onClick={add}>Adicionar {noun}</Button>
    </div>
  </div>;
}
