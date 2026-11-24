import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { SubstituicaoForm } from './SubstituicaoForm';
import { emptySubstitutionPlan } from '../utils/substitutionReview';
import { serializeReviewData } from '../utils/reviewData';

afterEach(() => vi.unstubAllGlobals());
function Harness({ documents = [] }: { documents?: Record<string, unknown>[] }) {
  const initial = { ...emptySubstitutionPlan(), documentos: documents, conferido_pelo_rh: true };
  const [data, setData] = useState<unknown>(initial);
  return <><SubstituicaoForm value={data} disabled={false} onChange={(_, v) => setData(v)} /><output aria-label="Plano revisado">{JSON.stringify(data)}</output></>;
}

it('exige opção e ausência de função própria explícitas, sem presumir dias', () => {
  render(<Harness />);
  expect(screen.getByLabelText('Situação da função própria')).toHaveValue('');
  expect(screen.getByLabelText('Composição confirmada da opção')).toHaveValue('');
  expect(screen.queryByLabelText('Dias do período de substituição')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Início da apuração'), { target: { value: '2024-03-01' } });
  expect(screen.getByLabelText(/Conferi os envolvidos/)).not.toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar impedimentos do substituto' }));
  const row = screen.getByRole('group', { name: 'Impedimentos do substituto: registro 1' });
  fireEvent.change(within(row).getByLabelText('Primeiro dia (incluído)'), { target: { value: '2024-03-08' } });
  fireEvent.change(within(row).getByLabelText('Último dia (incluído)'), { target: { value: '2024-03-12' } });
  expect(JSON.parse(screen.getByLabelText('Plano revisado').textContent ?? '{}').impedimentos_substituto[0]).toMatchObject({ inicio: '2024-03-08', ultimo_dia_considerado: '2024-03-12' });
});

it('preserva decimais e retira a confirmação da opção ao editar componentes', () => {
  render(<Harness />);
  fireEvent.change(screen.getByLabelText('Origem do valor'), { target: { value: 'MANUAL' } });
  fireEvent.change(screen.getByLabelText('Valor manual do componente'), { target: { value: '99999999999,123456789012' } });
  fireEvent.click(screen.getByLabelText('Conferi a opção, os componentes e os percentuais conforme a regra.'));
  fireEvent.change(screen.getByLabelText('Percentual utilizado do componente (%)'), { target: { value: '50,5' } });
  expect(screen.getByLabelText('Conferi a opção, os componentes e os percentuais conforme a regra.')).not.toBeChecked();
  const serialized = serializeReviewData({ substituicao: JSON.parse(screen.getByLabelText('Plano revisado').textContent ?? '{}') });
  expect(serialized).toMatchObject({ substituicao: { estado_inicial: { substituida: { componentes: [{ percentual_utilizado: '50.5', valor_manual: { valor: '99999999999.123456789012' } }] } } } });
  fireEvent.change(screen.getByLabelText('Origem do valor'), { target: { value: 'TABELA' } });
  expect(JSON.parse(screen.getByLabelText('Plano revisado').textContent ?? '{}').estado_inicial.substituida.componentes[0]).not.toHaveProperty('valor_manual');
});

it('descarta resposta antiga da consulta quando o período é alterado', async () => {
  let finish!: (r: Response) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve; })));
  render(<Harness />);
  fireEvent.change(screen.getByLabelText('Início da apuração'), { target: { value: '2024-03-01' } });
  fireEvent.change(screen.getByLabelText('Último dia considerado'), { target: { value: '2024-03-31' } });
  fireEvent.click(screen.getByRole('button', { name: 'Consultar referências confirmadas' }));
  fireEvent.change(screen.getByLabelText('Último dia considerado'), { target: { value: '2024-04-30' } });
  const { act } = await import('@testing-library/react');
  await act(async () => finish(new Response(JSON.stringify({ total: 1, itens: [{ id: 1, codigo_funcao: 'ANTIGA' }] }))));
  expect(screen.queryByLabelText('Usar componente do cadastro confirmado')).not.toBeInTheDocument();
});

it('mantém pagamentos observados fora do cálculo até conferir folha, operação e valor', () => {
  render(<Harness documents={[{ id: 'DOC', nome_arquivo: 'ficha.pdf', pagamentos_observados: [{ competencia: '2024-03', rubrica: '83185', sequencia: '2', valor_observado: '-5,00', natureza_rubrica: 'R', localizador: 'Linha 1' }] }]} />);
  const button = screen.getByRole('button', { name: 'Levar pagamento observado para conferência' });
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Papel do documento'), { target: { value: 'FICHA_FINANCEIRA' } });
  fireEvent.change(screen.getByLabelText('Pessoa identificada no documento'), { target: { value: 'SUBSTITUTO' } });
  fireEvent.click(button);
  const data = JSON.parse(screen.getByLabelText('Plano revisado').textContent ?? '{}');
  expect(data.recebidos).toMatchObject([{ operacao: '', identificador_folha: '', valor: '-5,00' }]);
  fireEvent.change(screen.getByLabelText('Valor pago ou estornado (positivo)'), { target: { value: '5,00' } });
  fireEvent.change(screen.getByLabelText('Operação'), { target: { value: 'ESTORNO' } });
  fireEvent.change(screen.getByLabelText('Identificação do pagamento original'), { target: { value: 'P1' } });
  const serialized = serializeReviewData({ substituicao: JSON.parse(screen.getByLabelText('Plano revisado').textContent ?? '{}') });
  expect(serialized).toMatchObject({ substituicao: { documentos: [{ pagamentos_observados: [{ valor_observado: '-5.00' }] }], recebidos: [{ valor: '5.00', estorna_id: 'P1' }] } });
});
