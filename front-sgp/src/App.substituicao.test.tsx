import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';

beforeEach(() => {
  localStorage.clear(); localStorage.setItem('isLoggedIn', 'true'); localStorage.setItem('role', 'user');
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });
const json = (value: unknown) => new Response(JSON.stringify(value));

it('permite iniciar substituição sem documentos e sem preencher valores presumidos', async () => {
  const fetchMock = vi.fn<(url: RequestInfo | URL) => Promise<Response>>().mockResolvedValue(json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] }));
  vi.stubGlobal('fetch', fetchMock);
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'substituicao' } });
  expect(screen.getByText(/PDFs e portarias são opcionais/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText('Matrícula do titular');
  expect(screen.getByLabelText('Início da apuração')).toHaveValue('');
  expect(screen.getByLabelText('Situação da função própria')).toHaveValue('');
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
  expect(fetchMock.mock.calls.some(args => String(args[0]).includes('/extrair-pdf'))).toBe(false);
});

it('agrupa documentos, aplica períodos após revisão e envia um único plano estruturado', async () => {
  const calculations: Record<string, unknown>[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    if (String(url).includes('/extrair-pdf')) return json({ resultados: [
      { filename: 'designacao.pdf', dados_extraidos: {}, candidatos_substituicao: [{ campo: 'DESIGNACAO', inicio: '2024-03-01', ultimo_dia_considerado: '2024-03-31', localizador: 'Linha 1' }] },
      { filename: 'afastamento.pdf', dados_extraidos: { matricula: '998', alertas_extracao: ['Extração incompleta: mais de 100 períodos. Confira o documento completo e preencha os restantes manualmente.'] }, candidatos_substituicao: [{ campo: 'AFASTAMENTO_TITULAR', inicio: '2024-03-05', ultimo_dia_considerado: '2024-03-25', localizador: 'Linha 2' }] },
    ] });
    if (String(url).includes('/calcular')) { calculations.push(JSON.parse(String(options?.body))); return json({ historico_id: 77, resultado_calculo: { tipo_substituicao: 'periodos_v1', total_geral_a_receber: '2777.42' } }); }
    return json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] });
  }));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'substituicao' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: ['designacao.pdf', 'afastamento.pdf'].map(name => new File(['sintético'], name, { type: 'application/pdf' })) } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText('Matrícula do titular');
  expect(screen.queryByRole('button', { name: 'Próximo arquivo' })).not.toBeInTheDocument();
  expect(screen.getByText('afastamento.pdf: Extração incompleta: mais de 100 períodos. Confira o documento completo e preencha os restantes manualmente.')).toBeVisible();
  const fill = (label: string, value: string, scope: HTMLElement = document.body) => fireEvent.change(within(scope).getByLabelText(label), { target: { value } });
  fill('Matrícula SIAPE', '000999'); fill('Matrícula do titular', '998'); fill('Início da apuração', '2024-03-01'); fill('Último dia considerado', '2024-03-31');
  for (const [name, papel] of [['designacao.pdf', 'DESIGNACAO'], ['afastamento.pdf', 'AFASTAMENTO_TITULAR']]) {
    const doc = screen.getByRole('group', { name });
    fill('Papel do documento', papel, doc);
    if (papel === 'AFASTAMENTO_TITULAR') fill('Pessoa identificada no documento', 'TITULAR', doc);
    fireEvent.click(within(doc).getByRole('button', { name: 'Usar período extraído após conferir o papel do documento' }));
  }
  const initial = screen.getByRole('group', { name: 'Situação no início da apuração' });
  fill('Tipo de função', 'FG', initial); fill('Código da função', 'S1', initial); fill('Modalidade conforme a fonte', 'TESTE', initial); fill('Componente da função', 'GRATIFICACAO', initial); fill('Percentual utilizado do componente (%)', '100', initial); fill('Origem do valor', 'MANUAL', initial);
  fill('Valor manual do componente', '4100,00', initial); fill('Fonte do valor manual', 'Fonte sintética', initial); fill('Localizador do valor manual', 'Linha 1', initial); fill('Início da vigência do valor', '2019-01-01', initial); fill('Situação da função própria', 'SEM_FUNCAO_CONFIRMADA', initial);
  fill('Identificação da regra', 'REGRA-1', initial); fill('Versão da regra', '1', initial); fill('Fonte da regra', 'Regra sintética', initial); fill('Início dos efeitos da regra', '2019-01-01', initial); fill('Composição confirmada da opção', 'DIFERENCA_FUNCOES', initial); fill('Tratamento de diferença mensal negativa conforme regra', 'ZERAR', initial);
  const payroll = screen.getByRole('group', { name: 'Rubrica devida' }); fill('Natureza da folha', 'NORMAL', payroll); fill('Natureza da rubrica', 'R', payroll);
  fireEvent.click(within(initial).getByLabelText('Conferi a opção, os componentes e os percentuais conforme a regra.'));
  fireEvent.click(screen.getByLabelText(/Conferi os envolvidos/)); fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
  await screen.findByRole('button', { name: 'Baixar PDF' });
  expect(calculations).toHaveLength(1);
  expect(calculations[0]).toMatchObject({ tipo_calculo: 'substituicao', dados_extraidos: { matricula: '000999', substituicao: { titular_matricula: '998', designacao: { inicio: '2024-03-01' }, afastamentos_titular: [{ inicio: '2024-03-05' }], documentos: [{ nome_arquivo: 'designacao.pdf' }, { nome_arquivo: 'afastamento.pdf', pessoa: 'TITULAR' }], estado_inicial: { substituida: { componentes: [{ percentual_utilizado: '100', valor_manual: { valor: '4100.00' } }] } }, conferido_pelo_rh: true } } });
  fireEvent.click(screen.getByText('Dados usados no cálculo').closest('summary')!);
  fill('Nome do servidor', 'Pessoa revisada');
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
  expect(screen.getByLabelText('Histórico a substituir (opcional, somente revisão)')).toHaveValue(77);
}, 30000);
