import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { GestaoTabelas } from './GestaoTabelas';
const reference = { id: 7, carreira: 'MAGISTERIO_SUPERIOR', vinculo: 'EFETIVO', jornada: '40H', versao_carreira: 'Estrutura sintética', classe_docente: 'Adjunto', nivel_docente: 1, inicio_vigencia: '2026-04-01', fim_vigencia: null, vencimento_basico: '4200.125', retribuicoes: [{ titulacao: 'Mestrado', valor: '1500.025' }], fonte: 'Fonte sintética', estado: 'CONFIRMADA', classificacao_tae: null, capacitacao_tae: null, padrao_tae: null, estrutura_id: 2, conferido_em: null };
describe('Gestão de referências por vigência', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: string) => new Response(JSON.stringify(input.includes('pendencias-legadas')
      ? { itens: [{ id: 4, tabela_origem: 'tabela_vencimento_basico', id_origem: 1, valor_original: '4200.125', motivo: 'Vigência não comprovada', referencia_id: null }], total: 1 }
      : { itens: [reference], total: 1 }), { status: 200 })));
  });
  afterEach(() => vi.unstubAllGlobals());
  it('mostra datas e dimensões sem presumir o ano mais recente', async () => {
    render(<GestaoTabelas />);
    expect(await screen.findByText('2026-04-01 até em aberto')).toBeVisible();
    expect(screen.getByText('EFETIVO / 40H')).toBeVisible();
    expect(screen.queryByLabelText('Filtrar por ano')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Vigente na data'), { target: { value: '2026-03-31' } });
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('data_referencia=2026-03-31'))).toBe(true));
  });
  it('envia valores decimais exatos e preserva RT da mesma referência ao editar', async () => {
    render(<GestaoTabelas />);
    fireEvent.click(await screen.findByRole('button', { name: 'Editar referência 7' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByLabelText('Vencimento básico (decimal com ponto)')).toHaveValue('4200.125');
    fireEvent.change(dialog.getByLabelText('Vencimento básico (decimal com ponto)'), { target: { value: '4300.123456789012' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Salvar referência' }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(true));
    const saved = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'PUT')!;
    expect(JSON.parse(String(saved[1]?.body))).toMatchObject({ vencimento_basico: '4300.123456789012', retribuicoes: reference.retribuicoes, inicio_vigencia: '2026-04-01', fim_vigencia: null });
    expect(JSON.parse(String(saved[1]?.body))).not.toHaveProperty('id');
  });
  it('separa os campos TAE e docente sem preencher datas ou salários presumidos', async () => {
    render(<GestaoTabelas />);
    await screen.findByText('EFETIVO / 40H');
    fireEvent.click(screen.getByRole('button', { name: 'Nova referência salarial' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByLabelText('Início da vigência')).toHaveValue('');
    expect(dialog.getByLabelText('Vencimento básico (decimal com ponto)')).toHaveValue('');
    fireEvent.change(dialog.getByLabelText('Carreira'), { target: { value: 'TAE' } });
    expect(dialog.getByLabelText('Padrão TAE')).toBeVisible();
    expect(dialog.queryByLabelText('Classe docente')).not.toBeInTheDocument();
    expect(dialog.queryByRole('button', { name: 'Adicionar RT' })).not.toBeInTheDocument();
    fireEvent.change(dialog.getByLabelText('Carreira'), { target: { value: 'MAGISTERIO_SUPERIOR' } });
    expect(dialog.getByLabelText('Classe docente')).toBeVisible();
    expect(dialog.queryByLabelText('Padrão TAE')).not.toBeInTheDocument();
  });
  it('mantém edição e informa conflito de vigência para correção', async () => {
    render(<GestaoTabelas />);
    fireEvent.click(await screen.findByRole('button', { name: 'Editar referência 7' }));
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Vigência sobreposta' }), { status: 409 })));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Salvar referência' }));
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Vigência sobreposta');
    expect(screen.getByLabelText('Início da vigência')).toHaveValue('2026-04-01');
  });
  it('mostra legado pendente e exige correspondência manual explícita', async () => {
    render(<GestaoTabelas />);
    await screen.findByText('EFETIVO / 40H');
    fireEvent.change(screen.getByLabelText('Consultar'), { target: { value: 'pendencias-legadas' } });
    fireEvent.click(await screen.findByRole('button', { name: 'Vincular pendência 4' }));
    expect(screen.getByLabelText('ID da referência confirmada')).toHaveValue(null);
    fireEvent.change(screen.getByLabelText('ID da referência confirmada'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: 'Registrar correspondência conferida' }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => String(url).endsWith('/pendencias-legadas/4/vinculo') && init?.body === '{"referencia_id":7}')).toBe(true));
  });
});
