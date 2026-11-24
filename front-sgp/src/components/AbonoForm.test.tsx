import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { expect, it } from 'vitest';
import { AbonoForm } from './AbonoForm';
import { emptyAbonoPlan, serializeAbonoPlan } from '../utils/abonoReview';

function Harness({ initial = {} }: { initial?: Record<string, unknown> }) {
  const [value, setValue] = useState<Record<string, unknown>>({ ...emptyAbonoPlan(), ...initial });
  return <><AbonoForm value={value} disabled={false} onChange={(_, value) => setValue(value as Record<string, unknown>)} /><output data-testid="payload">{JSON.stringify(value)}</output></>;
}

it('mantém desconhecidos distintos de zero e invalida confirmação quando o valor muda', () => {
  render(<Harness initial={{ conferido_pelo_rh: true }} />);
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar parcelas de direito' }));
  expect(screen.getByLabelText('Estado da contribuição')).toHaveValue('PENDENTE');
  expect(screen.getByLabelText('Estado da pesquisa de pagamentos')).toHaveValue('PENDENTE');
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar lançamentos de folha' }));
  fireEvent.change(screen.getByLabelText('Valor do lançamento, inclusive zero confirmado'), { target: { value: '1.234,005' } });
  const payload = serializeAbonoPlan(JSON.parse(screen.getByTestId('payload').textContent!));
  expect(payload).toMatchObject({ lancamentos: [{ valor: '1234.005', conferido: false }], conferido_pelo_rh: false });
});

it('aplica observações somente após identificar vínculo e preserva edições ao reaplicar', () => {
  render(<Harness initial={{ documentos: [{ id: 'D', nome_arquivo: 'ficha.pdf', vinculo_identificado: 'V1', vinculo_confirmado: false, observacoes: [{ rubrica: '98004', competencia: '2026-12', natureza_rubrica: 'D', sequencia: '6', valor_observado: '-300.00', localizador: 'linha 1', decisao: 'PENDENTE' }] }] }} />);
  const button = screen.getByRole('button', { name: 'Levar à revisão sem presumir papel, categoria ou operação' });
  expect(button).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Conferi a pessoa e o vínculo deste documento'));
  fireEvent.click(button);
  const scope = screen.getByRole('group', { name: 'Lançamentos de folha 1' });
  expect(within(scope).getByLabelText('Papel do lançamento')).toHaveValue('');
  expect(within(scope).getByLabelText('Categoria do lançamento')).toHaveValue('');
  expect(within(scope).getByLabelText('Operação confirmada')).toHaveValue('');
  expect(within(scope).getByLabelText('Valor do lançamento, inclusive zero confirmado')).toHaveValue('300.00');
  fireEvent.change(within(scope).getByLabelText('Operação confirmada'), { target: { value: 'ESTORNO' } });
  fireEvent.click(button);
  expect(within(scope).getByLabelText('Operação confirmada')).toHaveValue('ESTORNO');
  expect(JSON.parse(screen.getByTestId('payload').textContent!).lancamentos).toHaveLength(1);
});

it('cobertura do 13º começa pendente e exclusão de observação exige campo de justificativa', () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar cobertura do 13º por exercício' }));
  expect(screen.getByLabelText('Situação do 13º')).toHaveValue('PENDENTE');
  expect(screen.getByLabelText('Justificativa da cobertura')).toHaveValue('');
});

it.each([
  ['Adicionar lançamentos de folha', 'Identificador do lançamento'],
  ['Adicionar parcelas de direito', 'Identificador da parcela'],
])('preserva foco ao editar identificador em %s', (button, label) => {
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: button }));
  const input = screen.getByLabelText(label);
  input.focus();
  for (const value of ['F', 'F1', 'F12']) {
    fireEvent.change(input, { target: { value } });
    expect(screen.getByLabelText(label)).toBe(input);
    expect(input).toHaveFocus();
    expect(input).toHaveValue(value);
  }
});

it('remove uma linha sem remontar nem perder o foco da linha remanescente', () => {
  render(<Harness />);
  const add = screen.getByRole('button', { name: 'Adicionar lançamentos de folha' });
  fireEvent.click(add); fireEvent.click(add);
  const second = screen.getAllByLabelText('Identificador do lançamento')[1];
  second.focus();
  fireEvent.change(second, { target: { value: 'SEGUNDO' } });
  fireEvent.click(screen.getByRole('button', { name: 'Remover lançamentos de folha 1' }));
  expect(screen.getByLabelText('Identificador do lançamento')).toBe(second);
  expect(second).toHaveValue('SEGUNDO');
  fireEvent.click(add);
  expect(screen.getAllByLabelText('Identificador do lançamento')[0]).toBe(second);
});

it('exige confirmação específica para correção de sinal e a retira ao editar o valor observado', () => {
  render(<Harness initial={{ documentos: [{ id: 'D', nome_arquivo: 'ficha.pdf', vinculo_identificado: 'V1', vinculo_confirmado: true, observacoes: [{ rubrica: '98002', competencia: '2026-01', natureza_rubrica: 'D', sequencia: '0', valor_observado: '-100.00', localizador: 'linha 1', decisao: 'PENDENTE' }] }] }} />);
  expect(screen.getByText(/Valor negativo observado/)).toBeVisible();
  const confirmation = screen.getByLabelText('Confirmei a correção do sinal observado conforme a justificativa');
  expect(confirmation).not.toBeChecked();
  fireEvent.change(screen.getByLabelText('Justificativa de exclusão ou correção'), { target: { value: 'Sinal revisado pelo RH na fonte sintética' } });
  fireEvent.click(confirmation);
  expect(confirmation).toBeChecked();
  fireEvent.change(screen.getByLabelText('Valor observado na ficha'), { target: { value: '-200.00' } });
  expect(screen.getByLabelText('Confirmei a correção do sinal observado conforme a justificativa')).not.toBeChecked();
  const data = JSON.parse(screen.getByTestId('payload').textContent!);
  expect(data.documentos[0].observacoes[0].correcao_sinal_confirmada).toBe(false);
  expect(data).not.toHaveProperty('rowKeys');
});
