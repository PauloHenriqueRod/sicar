import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OfficialSources } from './OfficialSources';

const origin = { titulo: 'Tabela sintética MGI', url: 'https://www.gov.br/sintetico', obtido_em: '2026-10-26', publicado_em: '2026-01-01' };
const line = { id: 9, versao: 1, localizador: 'CSV: linha 2', dados: { tipo: 'VB', carreira: 'MAGISTERIO_SUPERIOR', vinculo: 'EFETIVO', jornada: '40H', versao_carreira: 'SINTETICA', classe_docente: 'Associado', nivel_docente: 3, inicio_vigencia: '2019-08-01', valor: '3000.125' }, original: {}, estado: 'PENDENTE', problemas: [], referencia_id: null, funcao_id: null };
const preview = { ...origin, id: 3, arquivo: 'sintetico.csv', sha256: '0'.repeat(64), linhas: [line], resumo: { PENDENTE: 1 }, rejeicoes: [] };

afterEach(() => vi.unstubAllGlobals());

function metadata() {
  fireEvent.change(screen.getByLabelText('Identificação da fonte e edição'), { target: { value: origin.titulo } });
  fireEvent.change(screen.getByLabelText('Endereço oficial da fonte'), { target: { value: origin.url } });
  fireEvent.change(screen.getByLabelText('Data de obtenção'), { target: { value: origin.obtido_em } });
  fireEvent.change(screen.getByLabelText('Data de publicação (opcional)'), { target: { value: origin.publicado_em } });
}

it('apresenta prévia editável e exige conferência explícita antes da ativação', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const result = url.endsWith('/catalogo') ? { fontes: [] }
      : init?.method === 'PUT' ? { ...preview, linhas: [{ ...line, versao: 2, dados: { ...line.dados, valor: '3123.123456789012' } }] }
      : url.endsWith('/ativar') ? { ...preview, linhas: [{ ...line, versao: 3, estado: 'ATIVADA', referencia_id: 4 }], resumo: { ATIVADA: 1 } } : preview;
    return new Response(JSON.stringify(result), { status: 200 });
  }));
  render(<OfficialSources />);
  metadata();
  fireEvent.change(screen.getByLabelText('Arquivo da fonte (até 5 MB)'), { target: { files: [new File(['tipo;valor\nVB;3000.125'], 'sintetico.csv')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Gerar prévia para conferência' }));
  expect(await screen.findByRole('heading', { name: 'Prévia #3: Tabela sintética MGI' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Ativar registros conferidos' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Revisar registro 9' }));
  const editor = screen.getByLabelText('Valor conferido (decimal com ponto)');
  fireEvent.change(editor, { target: { value: '3123.123456789012' } });
  fireEvent.click(screen.getByRole('button', { name: 'Salvar revisão do registro' }));
  await waitFor(() => expect(screen.queryByLabelText('Valor conferido (decimal com ponto)')).not.toBeInTheDocument());
  const edit = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'PUT');
  expect(JSON.parse(String(edit?.[1]?.body))).toMatchObject({ versao: 1, dados: { valor: '3123.123456789012', inicio_vigencia: '2019-08-01', nivel_docente: 3 } });
  fireEvent.click(screen.getByLabelText('Conferi origem, posição, jornada, efeitos financeiros e valores dos registros selecionados.'));
  fireEvent.click(screen.getByRole('button', { name: 'Ativar registros conferidos' }));
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/ativar'))).toBe(true));
  const activated = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/ativar'));
  expect(JSON.parse(String(activated?.[1]?.body))).toEqual({ conferido_pelo_rh: true, linhas: [{ id: 9, versao: 2 }] });
});

it('permite entrada manual sem arquivo e mantém efeitos vazios apesar da publicação', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/catalogo') ? { fontes: [] } : { ...preview, linhas: [{ ...line, estado: 'REJEITADA', problemas: ['Vigência ausente'] }], rejeicoes: [{ ...line, problemas: ['Vigência ausente'] }] }), { status: 200 })));
  render(<OfficialSources />);
  metadata();
  fireEvent.change(screen.getByLabelText('Entrada dos valores'), { target: { value: 'manual' } });
  expect(screen.queryByLabelText('Arquivo da fonte (até 5 MB)')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Página ou aba e linha da fonte'), { target: { value: 'Página 4, tabela FG' } });
  fireEvent.change(screen.getByLabelText('Tipo de valor'), { target: { value: 'FUNCAO' } });
  expect(screen.queryByLabelText('Classe docente')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Início dos efeitos financeiros')).toHaveValue('');
  fireEvent.click(screen.getByRole('button', { name: 'Gerar prévia para conferência' }));
  await screen.findByRole('heading', { name: 'Prévia #3: Tabela sintética MGI' });
  const sent = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/manual'));
  const body = JSON.parse(String(sent?.[1]?.body));
  expect(body).toMatchObject({ origem: origin, localizador: 'Página 4, tabela FG' });
  expect(body.linhas[0]).not.toHaveProperty('inicio_vigencia');
  expect(screen.getByRole('button', { name: 'Baixar relatório de rejeições' })).toBeEnabled();
});

it('exibe cobertura e lacunas, incluindo a declaração de estruturas conhecidas', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/catalogo') ? { fontes: [] } : {
    total_estruturas: 1, escopo: 'Somente estruturas e titulações cadastradas.', itens: [{ estrutura_id: 1, posicao: { carreira: 'TAE', jornada: '40H' }, componente: 'VB', cobertos: [{ inicio: '2020-01-01', fim: '2024-02-28' }], lacunas: [{ inicio: '2024-02-29', fim: '2024-02-29' }] }],
  }), { status: 200 })));
  render(<OfficialSources />);
  fireEvent.change(screen.getByLabelText('Área de fontes oficiais'), { target: { value: 'cobertura' } });
  fireEvent.change(screen.getByLabelText('Fim da cobertura'), { target: { value: '2026-12-31' } });
  fireEvent.click(screen.getByRole('button', { name: 'Verificar cobertura histórica' }));
  expect(await screen.findByText('Lacunas: 2024-02-29 até 2024-02-29')).toBeVisible();
  expect(screen.getByText('Somente estruturas e titulações cadastradas.')).toBeVisible();
});

it('envia VB e RT manuais juntos, preservando a posição e sem valor presumido', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/catalogo') ? { fontes: [] } : preview), { status: 200 })));
  render(<OfficialSources />);
  metadata();
  fireEvent.change(screen.getByLabelText('Entrada dos valores'), { target: { value: 'manual' } });
  fireEvent.change(screen.getByLabelText('Página ou aba e linha da fonte'), { target: { value: 'Página 2, VB e RT' } });
  fireEvent.change(screen.getByLabelText('Tipo de valor'), { target: { value: 'VB' } });
  fireEvent.change(screen.getByLabelText('Carreira'), { target: { value: 'MAGISTERIO_SUPERIOR' } });
  fireEvent.change(screen.getByLabelText('Vínculo (conforme a tabela)'), { target: { value: 'EFETIVO' } });
  fireEvent.change(screen.getByLabelText('Jornada ou regime'), { target: { value: '40H' } });
  fireEvent.change(screen.getByLabelText('Estrutura histórica da carreira'), { target: { value: 'SINTETICA' } });
  fireEvent.change(screen.getByLabelText('Classe docente'), { target: { value: 'Associado' } });
  fireEvent.change(screen.getByLabelText('Nível docente'), { target: { value: '3' } });
  fireEvent.change(screen.getByLabelText('Início dos efeitos financeiros'), { target: { value: '2019-08-01' } });
  fireEvent.change(screen.getByLabelText('Valor conferido (decimal com ponto)'), { target: { value: '3000.125' } });
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar outro registro manual' }));
  fireEvent.change(screen.getByLabelText('Tipo de valor'), { target: { value: 'RT' } });
  expect(screen.getByLabelText('Classe docente')).toHaveValue('Associado');
  expect(screen.getByLabelText('Valor conferido (decimal com ponto)')).toHaveValue('');
  fireEvent.change(screen.getByLabelText('Titulação da RT'), { target: { value: 'Mestrado' } });
  fireEvent.change(screen.getByLabelText('Valor conferido (decimal com ponto)'), { target: { value: '1000.005' } });
  fireEvent.click(screen.getByRole('button', { name: 'Gerar prévia para conferência' }));
  await screen.findByRole('heading', { name: 'Prévia #3: Tabela sintética MGI' });
  const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/manual'));
  const data = JSON.parse(String(call?.[1]?.body));
  expect(data.linhas).toHaveLength(2);
  expect(data.linhas[0]).toMatchObject({ tipo: 'VB', valor: '3000.125', inicio_vigencia: '2019-08-01', nivel_docente: 3 });
  expect(data.linhas[1]).toMatchObject({ tipo: 'RT', valor: '1000.005', titulacao: 'Mestrado', inicio_vigencia: '2019-08-01', nivel_docente: 3 });
});

describe('Persistência de prévias', () => {
  it('mantém a edição quando a revisão está desatualizada', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => new Response(JSON.stringify(init?.method === 'PUT' ? { detail: 'A prévia foi alterada. Atualize e confira novamente.' } : url.endsWith('/catalogo') ? { fontes: [] } : preview), { status: init?.method === 'PUT' ? 409 : 200 })));
    render(<OfficialSources />);
    fireEvent.change(screen.getByLabelText('Área de fontes oficiais'), { target: { value: 'historico' } });
    vi.mocked(fetch).mockImplementationOnce(async () => new Response(JSON.stringify({ total: 1, itens: [{ id: 3, titulo: origin.titulo, obtido_em: origin.obtido_em }] }), { status: 200 }));
    fireEvent.click(screen.getByRole('button', { name: 'Consultar prévias salvas' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Abrir prévia 3' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Revisar registro 9' }));
    fireEvent.click(screen.getByRole('button', { name: 'Salvar revisão do registro' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('A prévia foi alterada');
    expect(within(screen.getByRole('region', { name: 'Prévia da fonte' })).getByLabelText('Valor conferido (decimal com ponto)')).toHaveValue('3000.125');
  });
});

it('consulta a origem por componente, incluindo fonte separada de RT', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/catalogo') ? { fontes: [] } : { total: 1, nota: 'Histórico de origens por componente.', itens: [{ linha_id: 8, lote_id: 2, titulo: 'Fonte sintética da RT', url: origin.url, obtido_em: origin.obtido_em, publicado_em: origin.publicado_em, localizador: 'Página 4', estado: 'ATIVADA', revisado_em: '2026-10-26T12:00:00', dados: { tipo: 'RT', titulacao: 'Mestrado', valor: '1000.005' } }] }), { status: 200 })));
  render(<OfficialSources />);
  fireEvent.change(screen.getByLabelText('Área de fontes oficiais'), { target: { value: 'origens' } });
  fireEvent.change(screen.getByLabelText('ID da referência para consultar origem'), { target: { value: '7' } });
  fireEvent.click(screen.getByRole('button', { name: 'Consultar origens da referência' }));
  expect(await screen.findByRole('link', { name: 'Fonte sintética da RT' })).toHaveAttribute('href', origin.url);
  expect(screen.getByText('RT Mestrado · Valor conferido: 1000.005 · ATIVADA')).toBeVisible();
});

const oldCoverage = {
  total_estruturas: 21, escopo: 'Consulta sintética antiga.',
  itens: [{ estrutura_id: 1, posicao: { carreira: 'TAE' }, componente: 'VB',
    cobertos: [{ inicio: '2020-01-01', fim: '2020-12-31' }], lacunas: [] }],
};

it.each([
  ['Início da cobertura', '2021-01-01'],
  ['Fim da cobertura', '2026-12-31'],
  ['Cobertura de', 'FUNCAO'],
  ['Titulação para conferir RT (opcional)', 'Doutorado'],
  ['Área de fontes oficiais', 'funcoes'],
])('descarta a resposta pendente ao alterar %s', async (label, value) => {
  let resolve!: (response: Response) => void;
  const pending = new Promise<Response>(done => { resolve = done; });
  vi.stubGlobal('fetch', vi.fn((url: string) => url.endsWith('/catalogo')
    ? Promise.resolve(new Response(JSON.stringify({ fontes: [] }))) : pending));
  render(<OfficialSources />);
  fireEvent.change(screen.getByLabelText('Área de fontes oficiais'), { target: { value: 'cobertura' } });
  fireEvent.change(screen.getByLabelText('Fim da cobertura'), { target: { value: '2020-12-31' } });
  const specific = label.startsWith('Titulação');
  fireEvent.click(screen.getByRole('button', { name: specific ? 'Conferir cobertura da posição informada' : 'Verificar cobertura histórica' }));
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
  if (label === 'Área de fontes oficiais') fireEvent.change(screen.getByLabelText(label), { target: { value: 'cobertura' } });
  await act(async () => { resolve(new Response(JSON.stringify(oldCoverage))); });
  expect(screen.queryByText('Consulta sintética antiga.')).not.toBeInTheDocument();
  expect(screen.queryByText('Lacunas: nenhuma neste intervalo e cadastro')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Verificar cobertura histórica' })).toBeEnabled();
});

it('descarta a página pendente e reinicia a consulta após mudar o período', async () => {
  let resolve!: (response: Response) => void;
  const pending = new Promise<Response>(done => { resolve = done; });
  let calls = 0;
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.endsWith('/catalogo')) return Promise.resolve(new Response(JSON.stringify({ fontes: [] })));
    calls += 1;
    return calls === 2 ? pending : Promise.resolve(new Response(JSON.stringify(oldCoverage)));
  }));
  render(<OfficialSources />);
  fireEvent.change(screen.getByLabelText('Área de fontes oficiais'), { target: { value: 'cobertura' } });
  fireEvent.change(screen.getByLabelText('Fim da cobertura'), { target: { value: '2020-12-31' } });
  fireEvent.click(screen.getByRole('button', { name: 'Verificar cobertura histórica' }));
  await screen.findByText('Consulta sintética antiga.');
  fireEvent.click(screen.getByRole('button', { name: 'Próxima página de cobertura' }));
  fireEvent.change(screen.getByLabelText('Fim da cobertura'), { target: { value: '2026-12-31' } });
  await act(async () => { resolve(new Response(JSON.stringify(oldCoverage))); });
  expect(screen.queryByText('Consulta sintética antiga.')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Verificar cobertura histórica' }));
  await screen.findByText('Consulta sintética antiga.');
  expect(String(vi.mocked(fetch).mock.calls.at(-1)?.[0])).toContain('fim=2026-12-31&tipo=SALARIO&pagina=1');
});

const oldOrigins = { total: 21, nota: 'Origens da referência salarial 7.', itens: [{
  linha_id: 1, lote_id: 2, titulo: 'Fonte da referência salarial 7', url: origin.url,
  obtido_em: origin.obtido_em, publicado_em: null, localizador: 'Página 2',
  estado: 'ATIVADA', revisado_em: null, dados: { tipo: 'VB', valor: '3000' },
}] };

it.each([
  ['ID da referência para consultar origem', '8'],
  ['Origem de', 'FUNCAO'],
  ['Área de fontes oficiais', 'cobertura'],
])('descarta a origem pendente ao mudar %s', async (label, value) => {
  let resolve!: (response: Response) => void;
  const pending = new Promise<Response>(done => { resolve = done; });
  vi.stubGlobal('fetch', vi.fn((url: string) => url.endsWith('/catalogo')
    ? Promise.resolve(new Response(JSON.stringify({ fontes: [] }))) : pending));
  render(<OfficialSources />);
  fireEvent.change(screen.getByLabelText('Área de fontes oficiais'), { target: { value: 'origens' } });
  fireEvent.change(screen.getByLabelText('ID da referência para consultar origem'), { target: { value: '7' } });
  fireEvent.click(screen.getByRole('button', { name: 'Consultar origens da referência' }));
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
  if (label === 'Área de fontes oficiais') fireEvent.change(screen.getByLabelText(label), { target: { value: 'origens' } });
  await act(async () => { resolve(new Response(JSON.stringify(oldOrigins))); });
  expect(screen.queryByRole('link', { name: 'Fonte da referência salarial 7' })).not.toBeInTheDocument();
  expect(screen.queryByText('Origens da referência salarial 7.')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Consultar origens da referência' })).toBeEnabled();
});

it('reinicia as origens na primeira página e ignora erro da consulta anterior', async () => {
  let resolve!: (response: Response) => void;
  const pending = new Promise<Response>(done => { resolve = done; });
  let calls = 0;
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.endsWith('/catalogo')) return Promise.resolve(new Response(JSON.stringify({ fontes: [] })));
    calls += 1;
    return calls === 2 ? pending : Promise.resolve(new Response(JSON.stringify(oldOrigins)));
  }));
  render(<OfficialSources />);
  fireEvent.change(screen.getByLabelText('Área de fontes oficiais'), { target: { value: 'origens' } });
  fireEvent.change(screen.getByLabelText('ID da referência para consultar origem'), { target: { value: '7' } });
  fireEvent.click(screen.getByRole('button', { name: 'Consultar origens da referência' }));
  await screen.findByText('Origens da referência salarial 7.');
  fireEvent.click(screen.getByRole('button', { name: 'Próximas origens' }));
  fireEvent.change(screen.getByLabelText('Origem de'), { target: { value: 'FUNCAO' } });
  await act(async () => { resolve(new Response(JSON.stringify({ detail: 'Erro da consulta antiga' }), { status: 500 })); });
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(screen.queryByText('Origens da referência salarial 7.')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Consultar origens da referência' }));
  await screen.findByText('Origens da referência salarial 7.');
  expect(String(vi.mocked(fetch).mock.calls.at(-1)?.[0])).toContain('referencia_id=7&tipo=FUNCAO&pagina=1');
});


it('não oferece intervalos de linhas para contexto PDF', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ fontes: [] }), { status: 200 })));
  render(<OfficialSources />);
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar leitura de coluna' }));
  expect(screen.getByLabelText(/Primeira linha da leitura 1/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Arquivo da fonte (até 5 MB)'), { target: { files: [new File(['%PDF-synthetic'], 'sintetico.pdf')] } });
  expect(screen.queryByLabelText(/Primeira linha da leitura 1/)).not.toBeInTheDocument();
  expect(screen.getByText(/PDF: o contexto vale para todos os registros/)).toBeInTheDocument();
});
