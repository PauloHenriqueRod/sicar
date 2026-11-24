import { Button } from './ui';
import { SalaryPositionFields } from './SalaryPositionFields';
import { emptySalaryPosition } from '../utils/salaryReferences';
import type { SalaryPosition } from '../utils/salaryReferences';
export function SalaryReferenceReview({ data, onChange, disabled }: {
  data: Record<string, unknown>; onChange: (path: (string | number)[], value: unknown) => void; disabled: boolean;
}) {
  const contexts = 'mes_rescisao' in data ? [['referencia_salarial', 'Salário do contrato']] : 'salario_antigo' in data ? [['referencia_antiga', 'Salário anterior'], ['referencia_nova', 'Novo salário']] : [];
  return <div className="space-y-5">{contexts.map(([key, label]) => <section key={key} className="form-section border border-outline rounded-lg p-4 space-y-4">
    <h3 className="subsection-title">{label}: referência salarial</h3>
    <p className="help-text">Informe o salário revisado no campo de valor ou deixe-o vazio para consultar uma tabela confirmada. A consulta exige todos os identificadores e uma data explícita. Confira o direito e a documentação com o RH.</p>
    {data[key] ? <><SalaryPositionFields value={data[key] as SalaryPosition} disabled={disabled} date onChange={value => onChange([key], value)} />
      <Button variant="quiet" disabled={disabled} onClick={() => onChange([key], null)}>Remover consulta de {label.toLowerCase()}</Button></> :
      <Button variant="secondary" disabled={disabled} onClick={() => onChange([key], { ...emptySalaryPosition(), data_referencia: '' })}>Consultar tabela para {label.toLowerCase()}</Button>}
  </section>)}</div>;
}
