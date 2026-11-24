import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';

beforeEach(() => {
  localStorage.clear(); localStorage.setItem('isLoggedIn', 'true'); localStorage.setItem('role', 'user');
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });
const json = (value: unknown) => new Response(JSON.stringify(value));

it('envia plano manual com zero confirmado sem PDF e retira confirmação após edição', async () => {
  const requests: Record<string, unknown>[] = [];
  const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    if (String(url).includes('/calcular')) { requests.push(JSON.parse(String(options?.body))); return json({ historico_id: 77, resultado_calculo: { tipo_abono: 'parcelas_v1', saldo_parcelas_calculadas: '0.00' } }); }
    return json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] });
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'abono' } });
  expect(screen.getByText(/PDFs e portarias são opcionais/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText('Identificação do vínculo');
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
  const fill = (label: string, value: string, scope = document.body) => fireEvent.change(within(scope).getByLabelText(label), { target: { value } });
  fill('Matrícula SIAPE', '000999'); fill('Identificação do vínculo', 'V1'); fill('Início dos efeitos financeiros', '2026-01-01'); fill('Último dia do direito considerado', '2026-01-31');
  fill('Identificação da regra', 'REGRA-SINTETICA'); fill('Versão da regra', '1'); fill('Fonte da regra', 'Regra sintética conferida'); fill('Início da vigência da regra', '2020-01-01');
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar mapeamentos de rubricas' }));
  fill('Código da rubrica mapeada', '12345'); fill('Papel da rubrica', 'ABONO'); fill('Categoria da rubrica', 'REGULAR'); fill('Fonte do mapeamento', 'Mapeamento sintético');
  fireEvent.click(screen.getByLabelText('Conferi o papel e a categoria desta rubrica'));
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar parcelas de direito' }));
  fill('Identificador da parcela', 'P1'); fill('Categoria da parcela', 'REGULAR'); fill('Competência de direito', '2026-01'); fill('Início do período de referência', '2026-01-01'); fill('Fim do período de referência', '2026-01-31'); fill('Rubrica do abono devido', '12345'); fill('Natureza da folha devida', 'NORMAL'); fill('Estado da contribuição', 'ZERO_CONFIRMADO'); fill('Estado da pesquisa de pagamentos', 'NAO_HOUVE_CONFIRMADO'); fill('Fonte da conferência da parcela', 'Conferência sintética');
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar cobertura do 13º por exercício' }));
  fill('Exercício conferido', '2026'); fill('Situação do 13º', 'NAO_APLICAVEL_CONFIRMADO'); fill('Justificativa da cobertura', 'Escopo sintético confirmado');
  fireEvent.click(screen.getByLabelText('Conferi o direito, a regra e sua vigência'));
  fireEvent.click(screen.getByLabelText('Conferi direito, vínculo, rubricas, cobertura, descontos e abonos recebidos de todas as parcelas'));
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
  await screen.findByRole('button', { name: 'Baixar PDF' });
  expect(requests[0]).toMatchObject({ tipo_calculo: 'abono', dados_extraidos: { matricula: '000999', abono: { vinculo_id: 'V1', parcelas: [{ categoria: 'REGULAR', contribuicao: 'ZERO_CONFIRMADO', recebimento: 'NAO_HOUVE_CONFIRMADO' }], cobertura_13: [{ exercicio: 2026 }], conferido_pelo_rh: true } } });
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/extrair-pdf'))).toBe(false);
  fireEvent.click(screen.getByText('Dados usados no cálculo').closest('summary')!);
  fill('Identificação do vínculo', 'V2');
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
}, 30000);

it('agrupa fichas sem escolher pessoa ou vínculo e mantém avisos de extração', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => String(url).includes('/extrair-pdf') ? json({ resultados: [
    { filename: 'regular.pdf', dados_extraidos: { matricula: '999' }, observacoes_abono: [{ rubrica: '98002', valor_observado: '1000.00', localizador: 'linha 1', decisao: 'PENDENTE' }] },
    { filename: 'natalina.pdf', dados_extraidos: { matricula: '888', alertas_extracao: ['Extração incompleta, confira o documento completo.'] }, observacoes_abono: [{ rubrica: '98004', valor_observado: '300.00', localizador: 'linha 2', decisao: 'PENDENTE' }] },
  ] }) : json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] })));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'abono' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: ['regular.pdf', 'natalina.pdf'].map(name => new File(['sintético'], name, { type: 'application/pdf' })) } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText('Identificação do vínculo');
  expect(screen.getByLabelText('Matrícula SIAPE')).toHaveValue('');
  expect(screen.getAllByLabelText('Nome do documento')).toHaveLength(2);
  expect(screen.queryByRole('button', { name: 'Próximo arquivo' })).not.toBeInTheDocument();
  expect(screen.getByText('natalina.pdf: Extração incompleta, confira o documento completo.')).toBeVisible();
});
