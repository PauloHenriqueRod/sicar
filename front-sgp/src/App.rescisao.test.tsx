import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';

beforeEach(() => {
  localStorage.clear(); localStorage.setItem('isLoggedIn', 'true'); localStorage.setItem('role', 'user');
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });
const json = (value: unknown) => new Response(JSON.stringify(value));

it('inicia rescisão sem PDF, com datas vazias e confirmação obrigatória', async () => {
  const fetchMock = vi.fn().mockResolvedValue(json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] }));
  vi.stubGlobal('fetch', fetchMock);
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'rescisao' } });
  expect(screen.getByText(/PDFs e portarias são opcionais/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  expect(await screen.findByLabelText('Entrada em exercício')).toHaveValue('');
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/extrair-pdf'))).toBe(false);
});

it('agrupa fichas de anos diferentes e cadastro sem escolher automaticamente a pessoa ou contrato', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => String(url).includes('/extrair-pdf') ? json({ resultados: [
    { filename: 'ficha-2025.pdf', dados_extraidos: { matricula: '999' }, fontes_rescisao: { pagamentos_observados: [{ competencia: '2025-07', rubrica: '00750', sequencia: '0', valor_observado: '2000.00', localizador: 'linha 1' }] } },
    { filename: 'cadastro.pdf', dados_extraidos: { matricula: '888', alertas_extracao: ['Confira o vínculo.'] }, fontes_rescisao: { candidatos: [{ campo: 'inicio_exercicio', valor: '2025-01-16', localizador: 'CARGO/EMPREGO, linha 2' }] } },
  ] }) : json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] })));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'rescisao' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: ['ficha-2025.pdf', 'cadastro.pdf'].map(name => new File(['sintético'], name, { type: 'application/pdf' })) } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText('Entrada em exercício');
  expect(screen.getAllByLabelText('Nome do arquivo')).toHaveLength(2);
  expect(screen.getByLabelText('Entrada em exercício')).toHaveValue('');
  expect(screen.getByLabelText('Matrícula SIAPE')).toHaveValue('');
  expect(screen.queryByRole('button', { name: 'Próximo arquivo' })).not.toBeInTheDocument();
  expect(screen.getByText('cadastro.pdf: Confira o vínculo.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Usar inicio exercicio após conferir' })).toBeDisabled();
});
