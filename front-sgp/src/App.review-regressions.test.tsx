import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import type { TipoCalculo } from './types';

const json = (data: unknown) => new Response(JSON.stringify(data), { status: 200 });
function typeCharacters(label: string, text: string) {
  const input = screen.getByLabelText(label) as HTMLInputElement;
  fireEvent.change(input, { target: { value: '' } });
  for (const character of text) fireEvent.change(input, { target: { value: input.value + character } });
  expect(input).toHaveValue(text);
}

async function openReview(type: TipoCalculo, data: Record<string, unknown> = {}) {
  const payloads: Record<string, unknown>[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    if (String(url).includes('/extrair-pdf')) return json({ resultados: [{ filename: 'sintetico.pdf', dados_extraidos: data }] });
    if (String(url).includes('/calcular')) { payloads.push(JSON.parse(String(options?.body)).dados_extraidos); return json({ historico_id: 10, resultado_calculo: { total_a_receber: 100 } }); }
    return json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] });
  }));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: type } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [new File(['PDF sintético'], 'sintetico.pdf', { type: 'application/pdf' })] } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByRole('button', { name: 'Confirmar e Calcular' });
  if (type === 'progressao') {
    fireEvent.change(screen.getByLabelText('Modalidade da progressão'), { target: { value: 'TAE' } });
    fireEvent.change(screen.getByLabelText('Carreira'), { target: { value: 'TAE' } });
    fireEvent.change(screen.getByLabelText('Percentual inicial de anuênio'), { target: { value: '0' } });
    fireEvent.change(screen.getByLabelText('Percentual inicial de IQ'), { target: { value: '0' } });
  }
  return payloads;
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('isLoggedIn', 'true');
  localStorage.setItem('role', 'user');
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); localStorage.clear(); });

describe('Review input regressions', () => {
  it.each([null, ''])('does not infer a concession or block unrelated progression from an unknown percentage (%s)', async (insalubridade) => {
    const payloads = await openReview('progressao', { ano_proporcao: 2026, insalubridade, percentual_adicional_sugerido: 20, alertas_extracao: ['Confira o percentual de insalubridade.'] });
    expect(screen.getByRole('note')).toHaveTextContent('somente uma sugestão');
    expect(screen.getByLabelText('Informar concessão do adicional')).not.toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: /Conferi períodos/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    expect((payloads[0].progressao as { estado_inicial: object }).estado_inicial).not.toHaveProperty('adicional');
    expect((payloads[0].progressao as { estado_inicial: object }).estado_inicial).not.toHaveProperty('percentual_adicional');
  }, 15000);

  it('preserves intermediate decimal separators and leading zeros in the employee identifier', async () => {
    const payloads = await openReview('exercicio_anterior', { nome: '', matricula: '', fluxo_mensal: [{ periodo: '2026-01', v_dev: 0, v_rec: 0 }] });
    typeCharacters('Valor devido (R$)', '1.5');
    typeCharacters('Valor recebido (R$)', '1.234,56');
    typeCharacters('Matrícula SIAPE', '0012345');
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    expect(payloads[0]).toMatchObject({ matricula: '0012345', fluxo_mensal: [{ v_dev: 1.5, v_rec: 1234.56 }] });
  });

  it('rejects malformed numbers and fractional strict integers before sending a calculation', async () => {
    const payloads = await openReview('progressao', { ano_proporcao: 2026 });
    fireEvent.change(screen.getByLabelText('Padrão TAE'), { target: { value: '1.5' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /Conferi períodos/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('número inteiro válido');
    expect(payloads).toHaveLength(0);
    fireEvent.change(screen.getByLabelText('Padrão TAE'), { target: { value: '2' } });
    typeCharacters('Percentual inicial de anuênio', '1,2,3');
    fireEvent.click(screen.getByRole('checkbox', { name: /Conferi períodos/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Anuênio');
    expect(payloads).toHaveLength(0);
    typeCharacters('Percentual inicial de anuênio', '1,5');
    fireEvent.click(screen.getByRole('checkbox', { name: /Conferi períodos/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    expect(payloads[0]).toMatchObject({ progressao: { estado_inicial: { posicao: { padrao_tae: 2 }, percentual_anuenio: '1.5' } } });
  });

  it('mantém dados legados como observações e permite revisar datas e pagamentos antes da confirmação', async () => {
    const payloads = await openReview('rescisao', { ocorrencias_adicional_ferias: null, alertas_extracao: ['Confira a quantidade da rubrica 750 nos documentos.'] });
    expect(screen.getByRole('note')).toHaveTextContent('Confira a quantidade da rubrica 750');
    expect(screen.queryByLabelText('Alertas extracao')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Entrada em exercício'), { target: { value: '2025-01-16' } });
    fireEvent.change(screen.getByLabelText('Data do término'), { target: { value: '2026-08-31' } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar recebimentos das parcelas finais' }));
    typeCharacters('Rubrica', '00742');
    typeCharacters('Valor do lançamento', '6.000,00');
    expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
    expect(screen.queryByLabelText('Pagamentos anteriores do adicional de férias')).not.toBeInTheDocument();
    expect(payloads).toHaveLength(0);
    fireEvent.click(screen.getByLabelText('Conferi contrato, datas, regra, bases, avos e pagamentos das parcelas calculadas'));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    expect(payloads[0]).toMatchObject({ rescisao: { inicio_exercicio: '2025-01-16', data_termino: '2026-08-31', recebidos: [{ rubrica: '00742', valor: '6000.00' }], conferido_pelo_rh: true } });
    expect(payloads[0]).not.toHaveProperty('ocorrencias_adicional_ferias');
  });

  it('adds, removes and submits periods from an empty exercise collection without coercing the period identifier', async () => {
    const payloads = await openReview('exercicio_anterior', { fluxo_mensal: [] });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar período' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remover período 1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar período' }));
    typeCharacters('Período de referência', '01/2026');
    typeCharacters('Valor devido (R$)', '1234,56');
    typeCharacters('Valor recebido (R$)', '100.50');
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    expect(payloads[0]).toMatchObject({ fluxo_mensal: [{ periodo: '01/2026', v_dev: 1234.56, v_rec: 100.5, ab_ferias: 0, '13_sal': 0 }] });
  });

  it('normalizes legacy exercise fields without duplicating aliases or overriding canonical values', async () => {
    const payloads = await openReview('exercicio_anterior', { fluxo: [
      { periodo: '01/2026', v_dev: 100, v_rec: 50, v_abono: 10, v_13: 20 },
      { periodo: '02/2026', v_dev: 200, v_rec: 100, v_abono: 10, v_13: 20, ab_ferias: 25, '13_sal': 0 },
    ] });
    expect(screen.queryByLabelText('Abono (R$)')).not.toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('Resumo agregado legado');
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    expect(payloads[0]).toEqual({ alertas_extracao: ['Resumo agregado legado, sem rubrica ou origem do direito. Não representa a revisão do contrato por parcelas.'], fluxo_mensal: [
      { periodo: '01/2026', v_dev: 100, v_rec: 50, ab_ferias: 10, '13_sal': 20 },
      { periodo: '02/2026', v_dev: 200, v_rec: 100, ab_ferias: 25, '13_sal': 0 },
    ] });
  });

  it('não transforma ano desconhecido em competências ou parcelas confirmadas', async () => {
    const payloads = await openReview('abono', { valores_anuais: { 'Ano a conferir': [null] } });
    expect(screen.getByRole('note')).toHaveTextContent('Listas anuais legadas não identificam parcelas');
    expect(screen.queryByLabelText('Ano a adicionar')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Início dos efeitos financeiros')).toHaveValue('');
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar parcelas de direito' }));
    expect(screen.getByLabelText('Estado da contribuição')).toHaveValue('PENDENTE');
    expect(screen.getByLabelText('Estado da pesquisa de pagamentos')).toHaveValue('PENDENTE');
    expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
    expect(payloads).toHaveLength(0);
  });

  it('preserva valores e exige conferência ao remover lançamentos do abono', async () => {
    const payloads = await openReview('abono', { valores_anuais: {} });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar lançamentos de folha' }));
    typeCharacters('Valor do lançamento, inclusive zero confirmado', '750,25');
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar lançamentos de folha' }));
    const values = screen.getAllByLabelText('Valor do lançamento, inclusive zero confirmado');
    fireEvent.change(values[1], { target: { value: '800,50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Remover lançamentos de folha 1' }));
    expect(screen.getByLabelText('Valor do lançamento, inclusive zero confirmado')).toHaveValue('800,50');
    expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
    expect(payloads).toHaveLength(0);
  });

  it('opens explicit concessions instead of inferring monthly multipliers from legacy amounts', async () => {
    const payloads = await openReview('insalubridade', { valores_mensais: {} });
    expect(screen.queryByLabelText('Mês a adicionar')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Percentual confirmado do adicional')).toHaveValue('');
    expect(screen.getByLabelText('Conferi a espécie e o percentual no documento de concessão.')).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
    expect(payloads).toHaveLength(0);
  });
});

describe('Logout confirmation', () => {
  it.each([429, 503, 'network'])('clears private data but reports a %s logout failure and permits retry', async status => {
    await openReview('abono', { nome: 'Servidor privado' });
    const logout = vi.fn().mockImplementationOnce(async () => {
      if (status === 'network') throw new TypeError('Failed to fetch');
      return new Response('', { status: Number(status) });
    }).mockResolvedValue(json({}));
    vi.stubGlobal('fetch', logout);
    fireEvent.click(screen.getByRole('button', { name: 'Menu da conta' }));
    fireEvent.click(screen.getByRole('button', { name: 'Encerrar sessão' }));
    expect(screen.queryByDisplayValue('Servidor privado')).not.toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível confirmar a saída');
    expect(screen.queryByRole('button', { name: /Acessar Sistema/i })).not.toBeInTheDocument();
    expect(localStorage.getItem('sgp:logout-pending')).toBe('true');
    expect(localStorage.getItem('username')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Tentar encerrar novamente' }));
    await screen.findByRole('button', { name: /Acessar Sistema/i });
    expect(logout).toHaveBeenCalledTimes(2);
    expect(localStorage.getItem('sgp:logout-pending')).toBeNull();
  });

  it('times out, prevents duplicate logout requests and ignores a late failed response during retry', async () => {
    await openReview('abono');
    vi.useFakeTimers();
    let finishFirst!: (value: Response) => void;
    let finishRetry!: (value: Response) => void;
    const logout = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finishFirst = resolve; })).mockImplementationOnce(() => new Promise(resolve => { finishRetry = resolve; }));
    vi.stubGlobal('fetch', logout);
    fireEvent.click(screen.getByRole('button', { name: 'Menu da conta' }));
    fireEvent.click(screen.getByRole('button', { name: 'Encerrar sessão' }));
    fireEvent.click(screen.getByRole('button', { name: 'Aguarde...' }));
    expect(logout).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(screen.getByRole('alert')).toHaveTextContent('demorou para responder');
    expect(logout.mock.calls[0][1].signal.aborted).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Tentar encerrar novamente' }));
    await act(async () => { finishFirst(new Response('', { status: 503 })); });
    expect(screen.getByRole('button', { name: 'Aguarde...' })).toBeDisabled();
    await act(async () => { finishRetry(json({})); });
    expect(screen.getByRole('button', { name: /Acessar Sistema/i })).toBeVisible();
    expect(logout).toHaveBeenCalledTimes(2);
  });

  it('retains the retry screen after a reload while logout is unconfirmed', async () => {
    localStorage.removeItem('isLoggedIn');
    localStorage.setItem('sgp:logout-pending', 'true');
    vi.stubGlobal('fetch', vi.fn(async () => json({})));
    render(<App />);
    expect(screen.getByRole('alert')).toHaveTextContent('ainda não foi confirmado');
    fireEvent.click(screen.getByRole('button', { name: 'Tentar encerrar novamente' }));
    await waitFor(() => expect(localStorage.getItem('sgp:logout-pending')).toBeNull());
    expect(screen.getByRole('button', { name: /Acessar Sistema/i })).toBeVisible();
  });
});
