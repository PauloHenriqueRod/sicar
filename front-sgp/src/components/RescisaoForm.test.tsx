import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { RescisaoForm } from './RescisaoForm';
import { emptyRescisaoPlan, serializeRescisaoPlan } from '../utils/rescisaoReview';

afterEach(() => vi.unstubAllGlobals());
function Harness({ initial = {} }: { initial?: Record<string, unknown> }) {
  const [value, setValue] = useState<Record<string, unknown>>({ ...emptyRescisaoPlan(), ...initial });
  return <><RescisaoForm value={value} matricula="999" disabled={false} onChange={(_, next) => setValue(next as Record<string, unknown>)} /><output data-testid="payload">{JSON.stringify(value)}</output></>;
}

it('preserva quantidades desconhecidas e exige justificativa na correção sem perder precisão', () => {
  render(<Harness initial={{ conferido_pelo_rh: true }} />);
  expect(screen.getByLabelText('Entrada em exercício')).toHaveValue('');
  fireEvent.click(screen.getByRole('button', { name: 'Corrigir avos de férias adquiridos' }));
  fireEvent.change(screen.getByLabelText('Avos de férias adquiridos'), { target: { value: '20' } });
  fireEvent.change(screen.getByLabelText('Justificativa: Avos de férias adquiridos'), { target: { value: 'Período conferido no contrato' } });
  fireEvent.click(screen.getByRole('button', { name: 'Informar base das férias' }));
  fireEvent.change(screen.getByLabelText('Valor da base'), { target: { value: '5400,005' } });
  expect(screen.getByLabelText('Conferi contrato, datas, regra, bases, avos e pagamentos das parcelas calculadas')).not.toBeChecked();
  const payload = serializeRescisaoPlan(JSON.parse(screen.getByTestId('payload').textContent!)) as Record<string, unknown>;
  expect(payload).toMatchObject({ correcoes: { avos_ferias: { valor: 20, justificativa: 'Período conferido no contrato' } }, base_ferias: { valor_manual: { valor: '5400.005' } } });
});

it('descarta a prévia que termina depois de uma alteração de data', async () => {
  let finish!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish = resolve; })));
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Sugerir dias e avos pelas datas' }));
  fireEvent.change(screen.getByLabelText('Data do término'), { target: { value: '2026-08-31' } });
  await act(async () => finish(new Response(JSON.stringify({ ultimo_dia_sugerido: '2020-01-01', sugestoes: { avos_ferias: 99 } }))));
  expect(screen.queryByText(/2020-01-01/)).not.toBeInTheDocument();
});

it('aplica pagamento observado apenas após associação e mantém operação e período vazios', () => {
  render(<Harness initial={{ documentos: [{ id: 'D', nome_arquivo: 'ficha.pdf', papel: 'FICHA_FINANCEIRA', contrato_identificado: 'C1', vinculo_confirmado: false, pagamentos_observados: [{ competencia: '2026-07', rubrica: '00750', natureza_rubrica: 'R', sequencia: '6', valor_observado: '1800.00', localizador: 'linha 4' }] }] }} />);
  const action = screen.getByRole('button', { name: 'Levar pagamento à revisão, sem presumir operação ou período' });
  expect(action).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Conferi que o documento pertence à pessoa e ao contrato'));
  fireEvent.click(action);
  fireEvent.click(action);
  const payload = JSON.parse(screen.getByTestId('payload').textContent!);
  expect(payload.pagamentos_ferias).toHaveLength(1);
  expect(payload.pagamentos_ferias[0]).toMatchObject({ valor: '1800.00', operacao: '', avos: '', periodo_aquisitivo: { inicio: '', ultimo_dia_considerado: '' } });
  const scope = screen.getByRole('group', { name: 'Pagamentos da rubrica 750 1' });
  fireEvent.change(within(scope).getByLabelText('Operação'), { target: { value: 'COMPLEMENTO' } });
  expect(within(scope).getByLabelText('Identificador do pagamento complementado')).toBeVisible();
  fireEvent.click(action);
  expect(within(scope).getByLabelText('Operação')).toHaveValue('COMPLEMENTO');
  expect(screen.getByText('Pagamento já está em revisão. As edições foram preservadas.')).toHaveAttribute('role', 'status');
});
