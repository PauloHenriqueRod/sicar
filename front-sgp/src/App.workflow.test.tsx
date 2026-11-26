import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import saveAs from 'file-saver';

vi.mock('file-saver', () => ({ default: vi.fn() }));

function jsonResponse(data: unknown) {
  return new Response(JSON.stringify(data), { status: 200 });
}

async function uploadFiles(names = ['documento.pdf']) {
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'exercicio_anterior' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: names.map(name => new File(['demo'], name, { type: 'application/pdf' })) } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText('Nome do servidor');
}

describe('Calculation workflow', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(saveAs).mockClear();
    localStorage.setItem('isLoggedIn', 'true');
    localStorage.setItem('role', 'user');
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (url.includes('/dashboard/stats')) return jsonResponse({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] });
      if (url.includes('/extrair-pdf')) return jsonResponse({ resultados: [{ filename: ((options?.body as FormData).getAll('arquivos')[0] as File).name, dados_extraidos: { nome: 'Servidor 1', matricula: '', fluxo_mensal: [{ periodo: '2024-03', v_dev: 1200, v_rec: 0 }] } }] });
      if (url.includes('/calcular')) return jsonResponse({ historico_id: 42, resultado_calculo: { total_a_receber: 1200, dias_substituidos: 30 } });
      return jsonResponse({});
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

  it('calcula períodos sem upload e preserva as entradas decimais conferidas', async () => {
    const requests: [RequestInfo | URL, RequestInit | undefined][] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      requests.push([input, options]);
      if (String(input).includes('/dashboard/stats')) return jsonResponse({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] });
      if (String(input).includes('/calcular')) return jsonResponse({ historico_id: 43, resultado_calculo: { tipo_apuracao: 'periodos_v1', total_geral_a_receber: '3000.01' } });
      return jsonResponse({});
    }));
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
    fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'apuracao_periodos' } });
    expect(screen.getByLabelText('Selecionar PDFs — Ficha Financeira')).not.toBeRequired();
    fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
    await screen.findByLabelText('Início da apuração');
    const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fill('Início da apuração', '2024-02-01'); fill('Último dia considerado (incluído)', '2024-02-29');
    fill('Carreira', 'TAE'); fill('Vínculo (conforme a tabela)', 'EFETIVO'); fill('Jornada ou regime', '40H');
    fill('Estrutura histórica da carreira', 'SINTETICA'); fill('Classificação TAE', 'E'); fill('Padrão TAE', '1');
    fill('Titulação inicial (N/A quando não houver RT)', 'N/A');
    fireEvent.click(screen.getByLabelText('Informar VB manualmente com fonte conferida'));
    fill('Valor mensal conferido', '3000,005'); fill('Fonte do valor mensal', 'Fonte sintética'); fill('Página, aba ou linha da tabela', 'Aba 1');
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar rubricas devidas' }));
    fill('Código da rubrica', '1'); fill('Natureza da folha (conforme a fonte)', 'NORMAL'); fill('Natureza da rubrica', 'R');
    fill('Base de cálculo da rubrica', 'VB'); fill('Regra ou ato de referência', 'REGRA-1'); fill('Versão da regra ou ato', '1'); fill('Fonte da regra', 'Fonte sintética');
    expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /Conferi períodos/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    const resultPanel = screen.getByRole('heading', { name: 'Resultado do cálculo' }).closest('.surface') as HTMLElement;
    expect(within(resultPanel).getByText('R$ 3.000,01')).toBeVisible();
    const request = requests.find(([url]) => String(url).includes('/calcular'));
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({ tipo_calculo: 'apuracao_periodos', dados_extraidos: { apuracao: {
      estado_inicial: { vb_manual: { valor: '3000.005' }, posicao: { padrao_tae: 1 } }, conferido_pelo_rh: true, recebidos: [],
    } } });
    expect(requests.some(([url]) => String(url).includes('/extrair-pdf'))).toBe(false);
  }, 15000);

  it.each(['extração', 'cálculo', 'PDF'])('discards pending %s responses after logout and login by another user', async (operation) => {
    render(<App />);
    if (operation !== 'extração') {
      await uploadFiles();
      if (operation === 'PDF') {
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
        await screen.findByRole('button', { name: 'Baixar PDF' });

      }
    }
    let finish!: (response: Response) => void;
    let signal: AbortSignal | null | undefined;
    const pending = new Promise<Response>(resolve => { finish = resolve; });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (url.includes('/auth/login')) return jsonResponse({ username: 'segundo', role: 'user' });
      if (url.includes('/dashboard/stats')) return jsonResponse({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] });
      if (url.includes('/extrair-pdf') || url.includes('/calcular') || url.includes('/exportar-pdf')) { signal = options?.signal; return pending.then(response => response.clone()); }
      return jsonResponse({});
    }));
    if (operation === 'extração') {
      fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
      fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'exercicio_anterior' } });
      fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [new File(['demo'], 'privado.pdf')] } });
      fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
    } else {
      fireEvent.click(screen.getByRole('button', { name: operation === 'cálculo' ? 'Confirmar e Calcular' : 'Baixar PDF' }));
    }

    await waitFor(() => expect(signal).toBeDefined());
    const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    try {
      fireEvent.click(screen.getByRole('button', { name: 'Menu da conta' }));
      fireEvent.click(screen.getByRole('button', { name: 'Encerrar sessão' }));
      fireEvent.click(await screen.findByRole('button', { name: /Acessar Sistema/i }));
      expect(signal?.aborted).toBe(true);
      fireEvent.change(screen.getByLabelText('Usuário'), { target: { value: 'segundo' } });
      fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'senha-de-teste' } });
      fireEvent.submit(screen.getByLabelText('Senha').closest('form')!);
      await screen.findByRole('button', { name: 'Menu da conta' });
      await act(async () => {
        finish(operation === 'extração' ? jsonResponse({ resultados: [{ filename: 'privado.pdf', dados_extraidos: { nome: 'DADO PRIVADO' } }] }) : operation === 'cálculo' ? jsonResponse({ historico_id: 42, resultado_calculo: { total_a_receber: 123 } }) : new Response('%PDF-demo'));
      });
      fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
      expect(screen.getByLabelText('Tipo de cálculo')).toHaveValue('');
      expect(screen.queryByLabelText('Nome do servidor')).not.toBeInTheDocument();
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Baixar PDF' })).not.toBeInTheDocument();
      expect(saveAs).not.toHaveBeenCalled();
      expect(download).not.toHaveBeenCalled();
    } finally { download.mockRestore(); }
  }, 15000);

  it('reports a persistence failure without marking the calculation as complete', async () => {
    render(<App />);
    await uploadFiles();
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Não foi possível salvar o cálculo no histórico. Tente novamente.' }), { status: 500 })));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível salvar o cálculo no histórico');
    expect(screen.queryByRole('button', { name: 'Baixar PDF' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeEnabled();
  }, 15000);

  it('does not complete a calculation without its saved identifier', async () => {
    render(<App />);
    await uploadFiles();
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ resultado_calculo: { total_a_receber: 999 } })));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('não confirmou o registro');
    expect(screen.queryByRole('button', { name: 'Baixar PDF' })).not.toBeInTheDocument();
  });

  it('exports only the identifier returned by the server', async () => {
    render(<App />);
    await uploadFiles();
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    const fetchMock = vi.fn(async () => new Response('', { status: 500 }));
    vi.stubGlobal('fetch', fetchMock);
    fireEvent.click(screen.getByRole('button', { name: 'Baixar PDF' }));
    await screen.findByRole('alert');
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toEqual({ historico_id: 42 });
  });

  it('returns to review after edits, preserves the draft across navigation and resets only on a new calculation', async () => {
    render(<App />);
    await uploadFiles();
    expect(screen.getByText('Dados extraídos de 1 documento.')).toBeVisible();
    expect(screen.getByText('Revisão', { exact: true }).closest('li')).toHaveAttribute('aria-current', 'step');
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    expect(screen.getByText('Resultado', { exact: true }).closest('li')).toHaveAttribute('aria-current', 'step');
    const name = screen.getByLabelText('Nome do servidor');
    expect(name).not.toBeVisible();
    const resultHeading = screen.getByRole('heading', { name: 'Resultado do cálculo' });
    expect(within(resultHeading.closest('.surface') as HTMLElement).getByText('R$ 1.200,00')).toBeVisible();
    expect(resultHeading.compareDocumentPosition(screen.getByRole('heading', { name: 'Dados usados no cálculo' })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(screen.getByText('Dados usados no cálculo').closest('summary')!);
    expect(name).toBeVisible();
    name.focus();
    fireEvent.change(name, { target: { value: 'Nome revisado' } });
    expect(screen.getByText('Dados atualizados.')).toBeVisible();
    expect(screen.getByLabelText('Nome do servidor')).toHaveFocus();
    expect(screen.queryByRole('button', { name: 'Baixar PDF' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeVisible();
    expect(screen.getByText('Revisão', { exact: true }).closest('li')).toHaveAttribute('aria-current', 'step');
    fireEvent.click(screen.getByRole('button', { name: 'Visão geral' }));
    fireEvent.click(screen.getByRole('button', { name: 'Continuar cálculo' }));
    expect(screen.getByLabelText('Nome do servidor')).toHaveValue('Nome revisado');
    fireEvent.click(screen.getByRole('button', { name: 'Novo cálculo' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Descartar a revisão em andamento?');
    fireEvent.click(screen.getByRole('button', { name: 'Continuar revisão' }));
    expect(screen.getByLabelText('Nome do servidor')).toHaveValue('Nome revisado');
    fireEvent.click(screen.getByRole('button', { name: 'Novo cálculo' }));
    fireEvent.click(screen.getByRole('button', { name: 'Descartar e iniciar novo cálculo' }));
    expect(screen.getByLabelText('Tipo de cálculo')).toHaveValue('');
    expect(screen.getByText('Documentos', { exact: true }).closest('li')).toHaveAttribute('aria-current', 'step');
  }, 15000);

  it('reuses the same calculation key after a lost response and changes it after editing', async () => {
    render(<App />);
    await uploadFiles();
    const requests: Record<string, unknown>[] = [];
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, options?: RequestInit) => {
      requests.push(JSON.parse(String(options?.body)));
      if (requests.length === 1) throw new TypeError('Network response lost');
      return jsonResponse({ historico_id: 42, resultado_calculo: { total_a_receber: 1200 } });
    }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    expect(requests[0].idempotency_key).toMatch(/^[0-9a-f-]{36}$/);
    expect(requests[1]).toEqual(requests[0]);
    fireEvent.click(screen.getByText('Dados usados no cálculo').closest('summary')!);
    fireEvent.change(screen.getByLabelText('Nome do servidor'), { target: { value: 'Revisado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    expect(requests[2].idempotency_key).not.toBe(requests[0].idempotency_key);
  });

  it('protects an unfinished review on reload without storing personnel data in browser storage', async () => {
    render(<App />);
    await uploadFiles();
    const pendingUnload = new Event('beforeunload', { cancelable: true });
    expect(window.dispatchEvent(pendingUnload)).toBe(false);
    expect(JSON.stringify({ ...localStorage })).not.toContain('Servidor 1');
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    await waitFor(() => expect(window.dispatchEvent(new Event('beforeunload', { cancelable: true }))).toBe(true));
  });

  it.each([400, 422])('associates structured validation errors with the reviewed field (%s)', async (status) => {
    render(<App />);
    await uploadFiles();
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: [{ loc: ['dados_extraidos', 'matricula'], msg: 'Confira o ano informado.', type: 'value_error', input: 'CONTEUDO PRIVADO' }] }), { status })));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Confira o ano informado.');
    const year = screen.getByLabelText('Matrícula SIAPE');
    expect(year).toHaveAttribute('aria-invalid', 'true');
    expect(year).toHaveAccessibleDescription(expect.stringContaining('Confira o ano informado.'));
    expect(screen.queryByText(/CONTEUDO PRIVADO/)).not.toBeInTheDocument();
    fireEvent.change(year, { target: { value: '2026' } });
    expect(year).not.toHaveAttribute('aria-invalid', 'true');
  });

  it.each(['login', 'logout'])('clears pending review and rejects late responses after another tab performs %s', async (change) => {
    render(<App />);
    await uploadFiles();
    let finish!: (response: Response) => void;
    let signal: AbortSignal | null | undefined;
    let confirmIdentity!: (response: Response) => void;
    const pending = new Promise<Response>(resolve => { finish = resolve; });
    const identity = new Promise<Response>(resolve => { confirmIdentity = resolve; });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      if (String(input).includes('/calcular')) { signal = options?.signal; return pending; }
      if (String(input).includes('/auth/me')) return identity;
      return jsonResponse({});
    }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await waitFor(() => expect(signal).toBeDefined());
    act(() => {
      if (change === 'login') {
        localStorage.setItem('username', 'outra-conta');
        localStorage.setItem('role', 'admin');
      } else {
        localStorage.removeItem('isLoggedIn');
        localStorage.removeItem('username');
        localStorage.removeItem('role');
      }
      localStorage.setItem('sgp:session-event', 'evento-externo');
      window.dispatchEvent(new StorageEvent('storage', { key: 'sgp:session-event' }));
    });
    expect(signal?.aborted).toBe(true);
    expect(screen.queryByLabelText('Nome do servidor')).not.toBeInTheDocument();
    await act(async () => { finish(jsonResponse({ historico_id: 99, resultado_calculo: { total_a_receber: 987654 } })); });
    expect(screen.queryByRole('button', { name: 'Baixar PDF' })).not.toBeInTheDocument();
    if (change === 'login') {
      expect(screen.getByText('Atualizando a sessão...')).toBeVisible();
      expect(screen.queryByRole('button', { name: 'Usuários' })).not.toBeInTheDocument();
      await act(async () => { confirmIdentity(jsonResponse({ username: 'identidade-confirmada', role: 'user', auth_subject: 'id2' })); });
      await screen.findByRole('button', { name: 'Menu da conta' });
      expect(localStorage.getItem('username')).toBe('identidade-confirmada');
      expect(screen.queryByRole('button', { name: 'Usuários' })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
      expect(screen.getByLabelText('Tipo de cálculo')).toHaveValue('');
    } else expect(screen.getByRole('button', { name: /Acessar Sistema/i })).toBeVisible();
  });

  it('blocks private data when a logout in another tab is still unconfirmed', async () => {
    render(<App />);
    await uploadFiles();
    act(() => {
      localStorage.setItem('sgp:logout-pending', 'true');
      window.dispatchEvent(new StorageEvent('storage', { key: 'sgp:logout-pending' }));
    });
    expect(screen.getByRole('heading', { name: 'Encerramento da sessão' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Tentar encerrar novamente' })).toBeEnabled();
    expect(screen.queryByLabelText('Nome do servidor')).not.toBeInTheDocument();
    act(() => {
      localStorage.removeItem('sgp:logout-pending');
      localStorage.removeItem('isLoggedIn');
      window.dispatchEvent(new StorageEvent('storage', { key: 'sgp:logout-pending' }));
    });
    expect(screen.getByRole('button', { name: /Acessar Sistema/i })).toBeVisible();
  });

  it('uses one review and one result for the current server without batch navigation', async () => {
    render(<App />);
    await uploadFiles(['primeiro.pdf', 'segundo.pdf']);
    expect(screen.queryByRole('button', { name: 'Próximo arquivo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Baixar lote (ZIP)' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    expect(screen.getAllByRole('heading', { name: 'Resultado do cálculo' })).toHaveLength(1);
    fireEvent.click(screen.getByText('Dados usados no cálculo').closest('summary')!);
    fireEvent.change(screen.getByLabelText('Nome do servidor'), { target: { value: 'Pessoa revisada' } });
    expect(screen.queryByRole('button', { name: 'Baixar PDF' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Nome do servidor')).toHaveValue('Pessoa revisada');
  }, 15000);


  it('preserves values when result disclosures are closed and returns to a new review after edits', async () => {
    render(<App />);
    await uploadFiles();
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    fireEvent.click(screen.getByText('Dados usados no cálculo').closest('summary')!);
    expect(screen.getByLabelText('Nome do servidor')).toBeVisible();
    fireEvent.click(screen.getByText('Dados usados no cálculo').closest('summary')!);
    expect(screen.getByLabelText('Nome do servidor')).not.toBeVisible();
    fireEvent.click(screen.getByText('Dados usados no cálculo').closest('summary')!);
    expect(screen.getByLabelText('Nome do servidor')).toHaveValue('Servidor 1');
    fireEvent.change(screen.getByLabelText('Nome do servidor'), { target: { value: 'Pessoa revisada' } });
    expect(screen.getByLabelText('Nome do servidor')).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Resultado do cálculo' })).not.toBeInTheDocument();
  }, 15000);


  it('prevents changing files or input data while a calculation is pending', async () => {
    render(<App />);
    await uploadFiles(['primeiro.pdf']);
    let finishCalculation!: (response: Response) => void;
    const pendingResponse = new Promise<Response>(resolve => { finishCalculation = resolve; });
    vi.stubGlobal('fetch', vi.fn(() => pendingResponse));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    expect(screen.getByLabelText('Nome do servidor')).toBeDisabled();
    expect(screen.getByText('Calculando primeiro.pdf...')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Novo cálculo' })).toBeDisabled();
    await act(async () => { finishCalculation(jsonResponse({ historico_id: 42, resultado_calculo: { total_a_receber: 1200 } })); });
    expect(screen.getByText('Cálculo concluído para primeiro.pdf.')).toBeVisible();
    expect(screen.getByLabelText('Nome do servidor')).toBeEnabled();
  }, 15000);

  it('shows the missing-period message and keeps the document available for correction', async () => {
    render(<App />);
    await uploadFiles();
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Confira o ano de referência na revisão e informe um valor válido.' }), { status: 400 })));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Confira o ano de referência');
    expect(screen.getByLabelText('Nome do servidor')).toHaveValue('Servidor 1');
    expect(screen.queryByRole('button', { name: 'Baixar PDF' })).not.toBeInTheDocument();
  }, 15000);

  it('rejects an extraction response that would create independent reviews for several people', async () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
    fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'progressao' } });
    fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [new File(['demo'], 'origem.pdf')] } });
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ resultados: ['Pessoa A', 'Pessoa B'].map(nome => ({ filename: `${nome}.pdf`, dados_extraidos: { nome } })) })));
    fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('um servidor por vez');
    expect(screen.queryByLabelText('Nome do servidor')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continuar com preenchimento manual' })).toBeEnabled();
  }, 15000);


  it('shows PDF errors in the page and confirms a successful retry without claiming the file was saved', async () => {
    render(<App />);
    await uploadFiles();
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    await screen.findByRole('button', { name: 'Baixar PDF' });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Exportação de relatórios ocupada.' }), { status: 503 })));
    fireEvent.click(screen.getByRole('button', { name: 'Baixar PDF' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível gerar o PDF. Exportação de relatórios ocupada.');
    expect(screen.getByRole('button', { name: 'Baixar PDF' })).toBeEnabled();
    let finishExport!: (response: Response) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finishExport = resolve; })));
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:demo'), revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    try {
      fireEvent.click(screen.getByRole('button', { name: 'Baixar PDF' }));
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Gerando PDF...' })).toBeDisabled();
      expect(screen.getByRole('status')).toHaveTextContent('Gerando relatório em PDF');
      await act(async () => { finishExport(new Response('%PDF-demo')); });
      expect(screen.getByRole('status')).toHaveTextContent('PDF gerado. Download solicitado ao navegador.');
      expect(screen.getByRole('button', { name: 'Baixar PDF' })).toBeEnabled();
      expect(click).toHaveBeenCalledOnce();
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:demo');
    } finally { click.mockRestore(); }
  }, 15000);

  it('shows the extraction error returned by the API and clears it when the user replaces the documents', async () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
    fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'exercicio_anterior' } });
    const input = screen.getByLabelText('Selecionar PDFs — Ficha Financeira');
    fireEvent.change(input, { target: { files: [new File(['demo'], 'grande.pdf')] } });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'O limite é de 5MB.' }), { status: 413 })));
    fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('O limite é de 5MB.');
    expect(screen.getByRole('button', { name: 'Continuar para revisão' })).toBeEnabled();
    fireEvent.change(input, { target: { files: [new File(['demo'], 'novo.pdf')] } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('2 documentos selecionados para este cálculo.')).toBeVisible();
  }, 15000);

  it('shows onboarding under the welcome panel, remembers dismissal for each user and allows reopening', () => {
    localStorage.setItem('username', 'Equipe A');
    const first = render(<App />);
    const guide = screen.getByRole('region', { name: 'Primeiros passos no SICAR' });
    const welcome = screen.getByRole('heading', { name: 'Bem-vindo, Equipe A' }).closest('.surface')!;
    expect(welcome.nextElementSibling).toBe(guide);
    fireEvent.click(screen.getByRole('button', { name: 'Pular guia' }));
    expect(screen.queryByRole('region', { name: 'Primeiros passos no SICAR' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Abrir guia rápido' })).toHaveFocus();
    first.unmount();
    const returning = render(<App />);
    expect(screen.queryByRole('region', { name: 'Primeiros passos no SICAR' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Abrir guia rápido' }));
    expect(screen.getByRole('heading', { name: 'Prepare os documentos' })).toHaveFocus();
    returning.unmount();
    localStorage.setItem('username', 'Equipe B');
    render(<App />);
    expect(screen.getByRole('region', { name: 'Primeiros passos no SICAR' })).toBeVisible();
  });

  it('preserves reviewed data when reopening the guide and resuming a calculation', async () => {
    render(<App />);
    await uploadFiles();
    fireEvent.change(screen.getByLabelText('Nome do servidor'), { target: { value: 'Dados conferidos' } });
    fireEvent.click(screen.getByRole('button', { name: 'Abrir guia rápido' }));
    expect(screen.getByRole('heading', { name: 'Prepare os documentos' })).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: 'Próxima etapa' }));
    fireEvent.click(screen.getByRole('button', { name: 'Próxima etapa' }));
    fireEvent.click(screen.getByRole('button', { name: 'Retomar cálculo' }));
    expect(screen.getByLabelText('Nome do servidor')).toHaveValue('Dados conferidos');
    expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeVisible();
    expect(screen.getByRole('main')).toHaveFocus();
  }, 15000);
});
