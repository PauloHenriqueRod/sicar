import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';

beforeEach(() => {
  localStorage.clear(); localStorage.setItem('isLoggedIn', 'true'); localStorage.setItem('role', 'user');
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });
const json = (value: unknown) => new Response(JSON.stringify(value));

it('envia processo manual sem PDF, com zero explícito e confirmações, e invalida após edição', async () => {
  const requests: Record<string, unknown>[] = [];
  const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    if (String(url).includes('/calcular')) { requests.push(JSON.parse(String(options?.body))); return json({ historico_id: 77, resultado_calculo: { tipo_exercicio: 'parcelas_v1', saldo_parcelas_calculadas: '0.00' } }); }
    return json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] });
  });
  vi.stubGlobal('fetch', fetchMock); render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'exercicio_anterior' } });
  expect(screen.getByText(/PDFs e portarias são opcionais/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText('Identificação do vínculo');
  const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fill('Matrícula SIAPE', '000999'); fill('Identificação do vínculo', 'V1'); fill('Início do escopo', '2020-01-01'); fill('Último dia do escopo', '2020-01-31');
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar origens do direito' }));
  fill('Identificador da origem do direito', 'O'); fill('Descrição do direito', 'Direito sintético'); fill('Início dos efeitos financeiros', '2020-01-01'); fill('Último dia dos efeitos financeiros', '2020-01-31'); fill('Fonte do direito', 'Ato sintético'); fill('Localização do direito', 'item 1'); fill('Identificação da regra', 'REGRA'); fill('Versão da regra', '1'); fill('Fonte da regra', 'Fonte sintética'); fill('Início da vigência da regra', '2020-01-01');
  fireEvent.click(screen.getByLabelText('Conferi a regra específica e sua vigência'));
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar parcelas identificadas' }));
  fill('Identificador da parcela', 'P'); fill('Origem do direito vinculada', 'O'); fill('Competência do direito', '2020-01'); fill('Rubrica devida', '12345'); fill('Categoria da parcela', 'PRINCIPAL'); fill('Início do período considerado', '2020-01-01'); fill('Último dia considerado', '2020-01-31'); fill('Natureza da folha devida', 'NORMAL'); fill('Estado de revisão', 'CONFERIDO'); fill('Registro da revisão ou encaminhamento', 'Conferido sinteticamente'); fill('Pesquisa de pagamentos anteriores', 'NAO_HOUVE_CONFIRMADO');
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar lançamentos devidos' }));
  fill('Identificador do lançamento', 'D'); fill('Parcela vinculada', 'P'); fill('Operação', 'LANCAMENTO'); fill('Valor confirmado do lançamento', '0'); fill('Fonte do lançamento', 'Fonte sintética'); fill('Localização do lançamento', 'item 1'); fill('Identificação do evento de cálculo', 'EVENTO'); fill('Memória do valor devido', 'Zero confirmado');
  fireEvent.click(screen.getByLabelText('Conferi valor, identidade, fonte e vinculação do lançamento'));
  fireEvent.click(screen.getByLabelText('Conferi todas as origens, parcelas, pagamentos anteriores e ajustes deste processo'));
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
  await screen.findByRole('button', { name: 'Baixar PDF' });
  expect(requests[0]).toMatchObject({ tipo_calculo: 'exercicio_anterior', dados_extraidos: { matricula: '000999', exercicios: { parcelas: [{ pesquisa_pagamentos: 'NAO_HOUVE_CONFIRMADO', rubrica: '12345' }], devidos: [{ valor: '0', conferido: true }], conferido_pelo_rh: true } } });
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/extrair-pdf'))).toBe(false);
  fireEvent.click(screen.getByText('Dados usados no cálculo').closest('summary')!);
  fill('Valor confirmado do lançamento', '10');
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
}, 30000);

it('agrupa fontes extraídas sem escolher pessoa, origem do direito ou pagamento automaticamente', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => String(url).includes('/extrair-pdf') ? json({ resultados: [
    { filename: 'ficha.pdf', dados_extraidos: { matricula: '999' }, candidatos_exercicios: [{ tipo: 'RECEBIMENTO', competencia: '2020-01', rubrica: '12345', valor_observado: '250.00', localizador: 'linha 1' }] },
    { filename: 'ato.pdf', dados_extraidos: { matricula: '888', alertas_extracao: ['Layout sem leitura; complete manualmente.'] }, candidatos_exercicios: [] },
  ] }) : json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] })));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'exercicio_anterior' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: ['ficha.pdf', 'ato.pdf'].map(name => new File(['sintético'], name, { type: 'application/pdf' })) } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText('Identificação do vínculo');
  expect(screen.getByLabelText('Matrícula SIAPE')).toHaveValue('');
  expect(screen.getAllByLabelText('Nome do documento')).toHaveLength(2);
  expect(screen.queryByRole('button', { name: 'Próximo arquivo' })).not.toBeInTheDocument();
  expect(screen.getByText('ato.pdf: Layout sem leitura; complete manualmente.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
});
