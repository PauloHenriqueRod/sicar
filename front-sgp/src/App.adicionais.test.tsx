import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';
import { prepareReviewData, serializeReviewData } from './utils/reviewData';

beforeEach(() => {
  localStorage.clear(); localStorage.setItem('isLoggedIn', 'true'); localStorage.setItem('role', 'user');
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

it('mantém a razão observada como sugestão e não cria concessão confirmada', () => {
  const data = prepareReviewData('insalubridade', { percentual_adicional_sugerido: 20, valores_mensais: { Dezembro: 600 } });
  expect(data.alertas_extracao).toEqual([expect.stringContaining('somente uma sugestão')]);
  const value = serializeReviewData(data);
  expect(value).not.toHaveProperty('valores_mensais');
  expect(value).toMatchObject({ adicionais: { estado_inicial: { adicional: { percentual_confirmado: false, base: { confirmada: false }, regra: { confirmada: false } } }, reflexos: [] } });
  expect(((value.adicionais as { estado_inicial: { adicional: object } }).estado_inicial.adicional)).not.toHaveProperty('percentual');
});

it('envia concessão e reflexo revisados sem PDF e vincula nova edição ao histórico anterior', async () => {
  const requests: Record<string, unknown>[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    if (String(url).includes('/calcular')) {
      requests.push(JSON.parse(String(options?.body)));
      return new Response(JSON.stringify({ historico_id: 123 + requests.length, resultado_calculo: { tipo_apuracao: 'periodos_v1', tipo_adicionais: 'concessoes_v1', total_geral_a_receber: '386.67' } }), { status: 200 });
    }
    return new Response(JSON.stringify({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] }), { status: 200 });
  }));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'insalubridade' } });
  expect(screen.getByText(/PDFs e portarias são opcionais/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText('Percentual confirmado do adicional');
  const fill = (label: string, value: string, scope: HTMLElement = document.body) => fireEvent.change(within(scope).getByLabelText(label), { target: { value } });
  fill('Matrícula SIAPE', '000999');
  fill('Início da apuração', '2024-02-01'); fill('Último dia considerado (incluído)', '2024-02-29');
  fill('Carreira', 'TAE'); fill('Vínculo (conforme a tabela)', 'EFETIVO'); fill('Jornada ou regime', '40H'); fill('Estrutura histórica da carreira', 'SINTETICA'); fill('Classificação TAE', 'E'); fill('Padrão TAE', '1'); fill('Titulação inicial (N/A quando não houver RT)', 'N/A');
  fill('Identificação única da concessão', 'ATO-SINTETICO-123'); fill('Espécie do adicional', 'INSALUBRIDADE'); fill('Percentual confirmado do adicional', '10'); fill('Início da vigência da concessão', '2020-01-01'); fill('Base do adicional', 'VB');
  fill('Identificação da regra do adicional', 'REGRA-1'); fill('Versão da regra do adicional', '1'); fill('Fonte da regra do adicional', 'Fonte sintética'); fill('Início dos efeitos da regra do adicional', '2020-01-01');
  const percent = screen.getByLabelText('Conferi a espécie e o percentual no documento de concessão.');
  fireEvent.click(percent);
  fill('Percentual confirmado do adicional', '20'); expect(percent).not.toBeChecked(); fill('Percentual confirmado do adicional', '10');
  fireEvent.click(percent); fireEvent.click(screen.getByLabelText('Conferi a base aplicável ao adicional.')); fireEvent.click(screen.getByLabelText('Conferi a regra e seus efeitos financeiros.'));
  const rule = (scope: HTMLElement) => { fill('Regra ou ato de referência', 'REGRA-1', scope); fill('Versão da regra ou ato', '1', scope); fill('Fonte da regra', 'Fonte sintética', scope); fill('Início da vigência da regra', '2020-01-01', scope); };
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar rubricas devidas' }));
  const row = screen.getByRole('group', { name: 'Rubricas devidas: registro 1' });
  fill('Código da rubrica', '53', row); fill('Natureza da folha (conforme a fonte)', 'NORMAL', row); fill('Natureza da rubrica', 'R', row); fill('Base de cálculo da rubrica', 'ADICIONAL_CONFIRMADO', row); rule(row);
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar reflexos' }));
  const refl = screen.getByRole('group', { name: 'Reflexos: registro 1' });
  fill('Tipo de reflexo', 'FERIAS_UM_TERCO', refl); fill('Data-base do reflexo', '2024-02-29', refl); fill('Competência do reflexo', '2024-02', refl); fill('Avos do reflexo (1 a 12)', '12', refl); fill('Código da rubrica', '750', refl); fill('Natureza da folha (conforme a fonte)', 'NORMAL', refl); fill('Natureza da rubrica', 'R', refl); rule(refl);
  fireEvent.click(within(refl).getByLabelText('Adicional com concessão confirmada na base do reflexo'));
  fill('Concessão de origem do reflexo', 'ATO-SINTETICO-123', refl); fill('Início do período de referência do reflexo', '2023-03-01', refl); fill('Último dia do período de referência do reflexo', '2024-02-29', refl);
  fireEvent.click(screen.getByLabelText(/Conferi períodos/)); fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
  await screen.findByRole('button', { name: 'Baixar PDF' });
  expect(requests[0]).toMatchObject({ tipo_calculo: 'insalubridade', dados_extraidos: { matricula: '000999', adicionais: { estado_inicial: { adicional: { percentual: '10', percentual_confirmado: true, base: { tipo: 'VB', confirmada: true } } }, reflexos: [{ avos: 12, origem: 'ATO-SINTETICO-123', pagamentos_anteriores: [], periodo_referencia: { inicio: '2023-03-01', ultimo_dia_considerado: '2024-02-29' } }] } } });
  // A edição do resultado gera revisão explícita, não um segundo direito.
  fill('Percentual confirmado do adicional', '20');
  expect(screen.getByLabelText('Histórico a substituir (opcional, somente revisão)')).toHaveValue(124);
  expect(screen.queryByRole('button', { name: 'Baixar PDF' })).not.toBeInTheDocument();
  fireEvent.click(percent); fireEvent.click(screen.getByLabelText(/Conferi períodos/)); fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
  await screen.findByRole('button', { name: 'Baixar PDF' });
  expect(requests[1]).toMatchObject({ dados_extraidos: { substitui_historico_id: 124 } });
}, 20000);
