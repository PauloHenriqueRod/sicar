import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { it, expect } from 'vitest';
import { SalaryReferenceReview } from './SalaryReferenceReview';
function Harness() {
  const [data, setData] = useState<Record<string, unknown>>({ mes_rescisao: 4 });
  return <SalaryReferenceReview data={data} disabled={false} onChange={([key], value) => setData({ ...data, [key]: value })} />;
}
it('permite adicionar e remover uma consulta explícita e editar sua posição', () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Consultar tabela para salário do contrato' }));
  expect(screen.getByLabelText('Data salarial consultada')).toHaveValue('');
  fireEvent.change(screen.getByLabelText('Carreira'), { target: { value: 'TAE' } });
  fireEvent.change(screen.getByLabelText('Padrão TAE'), { target: { value: '3' } });
  expect(screen.getByLabelText('Padrão TAE')).toHaveValue(3);
  expect(within(screen.getByLabelText('Jornada ou regime')).queryByRole('option', { name: 'DE' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Remover consulta de salário do contrato' }));
  expect(screen.queryByLabelText('Data salarial consultada')).not.toBeInTheDocument();
});
