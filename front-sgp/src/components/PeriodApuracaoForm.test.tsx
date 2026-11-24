import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PeriodApuracaoForm } from './PeriodApuracaoForm';
import { emptyPeriodPlan, serializePeriodPlan } from '../utils/periodReviewData';

function Harness() {
  const [data, setData] = useState<Record<string, unknown>>({ ...emptyPeriodPlan(), conferido_pelo_rh: true });
  return <><PeriodApuracaoForm value={data} disabled={false} onChange={(_, value) => setData(value as Record<string, unknown>)} /><output aria-label="Contrato da apuração">{JSON.stringify(serializePeriodPlan(data))}</output></>;
}

describe('Apuração por períodos', () => {
  it('preserva a edição e retira a confirmação anterior na mesma atualização', () => {
    render(<Harness />);
    const confirmation = screen.getByRole('checkbox', { name: /Conferi períodos/ });
    expect(confirmation).toBeChecked();
    fireEvent.change(screen.getByLabelText('Início da apuração'), { target: { value: '2024-02-01' } });
    expect(screen.getByLabelText('Início da apuração')).toHaveValue('2024-02-01');
    expect(confirmation).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar rubricas devidas' }));
    expect(screen.getByLabelText('Código da rubrica')).toHaveValue('');
    fireEvent.change(screen.getByLabelText('Código da rubrica'), { target: { value: '1' } });
    expect(screen.getByLabelText('Código da rubrica')).toHaveValue('1');
  });

  it('mantém valores decimais exatos e alterações nulas explícitas', () => {
    render(<Harness />);
    fireEvent.click(screen.getByLabelText('Informar VB manualmente com fonte conferida'));
    fireEvent.change(screen.getByLabelText('Valor mensal conferido'), { target: { value: '999999999999,123456789012' } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar mudanças no período' }));
    fireEvent.change(screen.getByLabelText('Informação alterada'), { target: { value: 'vb_manual' } });
    const payload = JSON.parse(screen.getByLabelText('Contrato da apuração').textContent ?? '{}');
    expect(payload.estado_inicial.vb_manual.valor).toBe('999999999999.123456789012');
    expect(payload.eventos[0].alteracoes).toEqual({ vb_manual: null });
    expect(payload.conferido_pelo_rh).toBe(false);
  });

  it('permite identificar complementos e o pagamento alvo de um estorno', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar recebimentos' }));
    const fieldset = screen.getByRole('group', { name: 'Recebimentos: registro 1' });
    fireEvent.change(within(fieldset).getByLabelText('Tipo do lançamento'), { target: { value: 'ESTORNO' } });
    fireEvent.change(within(fieldset).getByLabelText('Identificador do pagamento estornado'), { target: { value: 'PAGAMENTO-1' } });
    expect(JSON.parse(screen.getByLabelText('Contrato da apuração').textContent ?? '{}').recebidos[0]).toMatchObject({ operacao: 'ESTORNO', estorna_id: 'PAGAMENTO-1' });
    fireEvent.change(within(fieldset).getByLabelText('Tipo do lançamento'), { target: { value: 'COMPLEMENTO' } });
    const receipt = JSON.parse(screen.getByLabelText('Contrato da apuração').textContent ?? '{}').recebidos[0];
    expect(receipt.operacao).toBe('COMPLEMENTO');
    expect(receipt).not.toHaveProperty('estorna_id');
    expect(within(fieldset).queryByLabelText('Identificador do pagamento estornado')).not.toBeInTheDocument();
  });

  it('remove a base mensal manual ao selecionar uma fórmula salarial', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar rubricas devidas' }));
    fireEvent.change(screen.getByLabelText('Base de cálculo da rubrica'), { target: { value: 'VALOR_MENSAL' } });
    fireEvent.click(screen.getByLabelText('Informar o valor mensal e sua fonte'));
    fireEvent.change(screen.getByLabelText('Valor mensal conferido'), { target: { value: '2000.01' } });
    fireEvent.change(screen.getByLabelText('Base de cálculo da rubrica'), { target: { value: 'VB' } });
    const rubric = JSON.parse(screen.getByLabelText('Contrato da apuração').textContent ?? '{}').rubricas[0];
    expect(rubric.formula).toBe('VB');
    expect(rubric).not.toHaveProperty('valor_mensal');
    expect(screen.queryByLabelText('Valor mensal conferido')).not.toBeInTheDocument();
  });
});
