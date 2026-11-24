import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { Historico } from './Historico';

describe('Historico Component', () => {
  it('consulta a versão salva e prepara recálculo com precisão e fontes intactas', async () => {
    const recalculate = vi.fn();
    const snapshot = { versao: 2, dados_extraidos: { matricula: 'SINTETICO', abono: { valor: '1234.565', conferido_pelo_rh: true }, revisao_extracao: { documentos: [] } }, resultado_calculo: { total_geral_a_receber: '1234.57', nota_arredondamento: 'Arredondamento somente no total final.' }, rastreabilidade: { versao_motor: 'SINTETICA-ANTIGA', entradas_decimais: { valor: '1234.565' } } };
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(String(input).includes('/historico/7') ? { id: 7, tipo_calculo: 'abono', snapshot, anterior_id: 3, substituido_por: null, pode_recalcular: true } : { itens: [{ id: 7, tipo_calculo: 'abono', resultado_json: JSON.stringify(snapshot.resultado_calculo), matricula: 'SINTETICO' }], total: 1 }))));
    render(<Historico onRecalculate={recalculate} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Ver memória #7' }));
    expect(await screen.findByText('Histórico #7 · Motor SINTETICA-ANTIGA')).toBeVisible();
    expect(screen.getByText('Arredondamento somente no total final.')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Preparar recálculo #7' }));
    expect(recalculate).toHaveBeenCalledWith('abono', snapshot.dados_extraidos, 7);
    recalculate.mockReturnValue(false);
    fireEvent.click(screen.getByRole('button', { name: 'Preparar recálculo #7' }));
    expect(await screen.findByText(/Conclua ou descarte o rascunho atual/)).toBeVisible();
    expect(snapshot.dados_extraidos.abono.valor).toBe('1234.565');
  });

  it('mantém legado e versão substituída consultáveis sem preparar recálculo indevido', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(String(input).includes('/historico/8') ? { id: 8, tipo_calculo: 'abono', snapshot: { total: 50 }, anterior_id: null, substituido_por: 9, pode_recalcular: false } : { itens: [{ id: 8, tipo_calculo: 'abono', resultado_json: '{"total":50}', matricula: 'SINTETICO' }], total: 1 }))));
    render(<Historico onRecalculate={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Ver memória #8' }));
    expect(await screen.findByText(/Registro legado sem entradas completas/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Preparar recálculo #8' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Exportar versão #8' })).toBeDisabled();
  });
  afterEach(() => vi.unstubAllGlobals());
  it('renders without crashing', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    const { container } = render(<Historico />);
    expect(container.firstChild).not.toBeNull();
  });

  it('distinguishes a loading failure from an empty history and confirms a successful retry', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response('', { status: 500 })).mockResolvedValueOnce(new Response(JSON.stringify({ itens: [], total: 0, pagina: 1, tamanho_pagina: 10 }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    render(<Historico />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível carregar o histórico.');
    expect(screen.queryByText('Nenhum cálculo registrado ainda.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar registros' }));
    expect(await screen.findByText('Histórico atualizado.')).toBeVisible();
    expect(screen.getByText('Nenhum cálculo registrado ainda.')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('uses server totals to reach records after the first fifty, and sends filters and sort order', async () => {
    const urls: URL[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      urls.push(url);
      const pagina = Number(url.searchParams.get('pagina'));
      return new Response(JSON.stringify({ total: 61, pagina, tamanho_pagina: 10, itens: [{ id: pagina, matricula: `MATRICULA-PAGINA-${pagina}`, tipo_calculo: 'substituicao', data_calculo: '2026-01-01T12:00:00', classe: 'Adjunto', nivel: 1, titulacao: 'Mestrado', resultado_json: '{}' }] }));
    }));
    render(<Historico />);
    await screen.findByText('MATRICULA-PAGINA-1');
    expect(screen.getByText(/de 61 registros/)).toBeVisible();
    const nextPage = screen.getByRole('button', { name: 'Próxima página do histórico' });
    for (let page = 2; page <= 6; page++) {
      fireEvent.click(nextPage);
      await screen.findByText(`MATRICULA-PAGINA-${page}`);
    }
    expect(urls.at(-1)?.searchParams.get('pagina')).toBe('6');
    fireEvent.change(screen.getByLabelText('Matrícula'), { target: { value: '00123' } });
    await screen.findByText('MATRICULA-PAGINA-1');
    expect(urls.at(-1)?.searchParams.get('busca')).toBe('00123');
    const button = screen.getByRole('button', { name: 'Matrícula' });
    button.focus();
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByRole('columnheader', { name: 'Matrícula' })).toHaveAttribute('aria-sort', 'ascending'));
    expect(urls.at(-1)?.searchParams.get('ordenar_por')).toBe('matricula');
    expect(urls.at(-1)?.searchParams.get('ordem')).toBe('asc');
    expect(button).toHaveFocus();
  }, 15000);

  it('aborts obsolete searches and ignores their late responses', async () => {
    let finishFirst!: (response: Response) => void;
    let oldSignal: AbortSignal | null | undefined;
    const initial = new Promise<Response>(resolve => { finishFirst = resolve; });
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, options?: RequestInit) => {
      if (new URL(String(input)).searchParams.get('busca') === 'nova') return Promise.resolve(new Response(JSON.stringify({ itens: [], total: 0 })));
      oldSignal = options?.signal;
      return initial;
    }));
    render(<Historico />);
    fireEvent.change(screen.getByLabelText('Matrícula'), { target: { value: 'nova' } });
    await screen.findByText('Nenhum cálculo encontrado para os filtros selecionados.');
    expect(oldSignal?.aborted).toBe(true);
    await act(async () => { finishFirst(new Response(JSON.stringify({ itens: [{ id: 1, matricula: 'DADO ANTIGO' }], total: 1 }))); });
    expect(screen.queryByText('DADO ANTIGO')).not.toBeInTheDocument();
  });
});
