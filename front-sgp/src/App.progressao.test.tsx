import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('isLoggedIn', 'true'); localStorage.setItem('role', 'user');
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

async function submitProgression(modality: string, monthly: boolean) {
  const fact = { id: 'vb', bloco_id: 'B', campo: 'rubrica', valor: '3000.00', rubrica: '00001', competencia: '2024-02',
    descricao_rubrica: 'VENCIMENTO BASICO', natureza: 'R', sequencia: '0', estado: 'EXTRAIDO', pagina: 1, localizador: 'Página 1' };
  const doc = { id: 'F', nome_arquivo: 'ficha.pdf', layout: 'FICHA_SIAPE', versao_leitor: 'rh_paginas_v5', situacao: 'CONCLUIDO', total_paginas: 1,
    blocos: [{ id: 'B', nome: 'DOCENTE SINTÉTICO', matricula: '123', categoria: 'DOCENTE', vinculo: 'EFETIVO', paginas: [1] }], campos: [fact], avisos: [] };
  const requests: [string, RequestInit | undefined][] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    requests.push([String(url), options]);
    const body = String(url).includes('/calcular') ? { historico_id: 123, resultado_calculo: { tipo_apuracao: 'periodos_v1', tipo_progressao: 'eventos_v1', total_geral_a_receber: '1850.00' } }
      : String(url).includes('/previa-folha') ? { parcelas: [{ inicio: '2024-02-15', fim: '2024-02-29', componente: 'VB',
        pago: '3100.00', destino: '5800.00', diferenca: '1396.55', fonte: 'Tabela de destino sintética' }] }
      : String(url).includes('/extrair-pdf') ? { versao_contrato: 2, resultados: [{ filename: 'ficha.pdf', extracao: doc }], falhas: [] }
      : String(url).includes('/posicoes-docentes?data_referencia=2024-02-15') ? { total: 1, tamanho_pagina: 50, itens: [{ id: 11, titulacao: 'Mestrado', posicao: { carreira: 'MAGISTERIO_SUPERIOR', vinculo: 'EFETIVO', jornada: '40H', versao_carreira: 'SINTETICA', classe_docente: 'Adjunto', nivel_docente: 1 } }] }
      : { total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] };
    return new Response(JSON.stringify(body), { status: 200 });
  }));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'progressao' } });
  expect(screen.getByText(/PDFs e portarias são opcionais/)).toBeVisible();
  if (monthly) fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [new File(['PDF'], 'ficha.pdf')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText(monthly ? 'Nova classe' : 'Modalidade da progressão');
  const fill = (label: string, value: string, scope: HTMLElement = document.body) => fireEvent.change(within(scope).getByLabelText(label), { target: { value } });
  if (monthly) {
    expect(screen.queryByText('Continuar para os dados do cálculo')).not.toBeInTheDocument();
    expect(screen.queryByText(/Servidor e fontes documentais/)).toBeNull();
    fireEvent.click(screen.getByRole('checkbox', { name: /Conferi períodos/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
    expect(requests.some(([url]) => url.includes('/calcular'))).toBe(false);
    expect(screen.getByLabelText('Matrícula SIAPE')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Nova classe')).toBeVisible();
    for (const label of ['Vínculo (conforme a tabela)', 'Estrutura histórica da carreira']) expect(screen.queryByLabelText(label)).toBeNull();
    for (const summary of [/^Rubricas devidas/, /^Mudanças no período/, /^Interrupções e diferenças já pagas/]) expect(screen.queryByText(summary)).toBeNull();
    fireEvent.click(screen.getByLabelText('Editar valor de 00001 · 2024-02'));
    fill('Valor conferido em reais · 00001 · 2024-02', '3100,00');
    fill('Motivo da correção', 'Conferido na ficha de fevereiro');
    fireEvent.click(screen.getByText('Salvar valor'));
    fill('Nome do servidor', 'DOCENTE SINTÉTICO'); fill('Matrícula SIAPE', '123');
  }
  if (!monthly) fill('Modalidade da progressão', modality);
  if (!monthly && modality === 'DOCENTE') fireEvent.click(screen.getByRole('button', { name: 'Usar apuração com eventos independentes' }));
  fill('Início da apuração', monthly ? '2024-02-15' : '2024-02-01'); fill('Último dia considerado (incluído)', '2024-02-29');
  const position = (scope: HTMLElement, level: string) => {
    fill('Carreira', modality === 'TAE' ? 'TAE' : 'MAGISTERIO_SUPERIOR', scope);
    fill('Vínculo (conforme a tabela)', 'EFETIVO', scope); fill('Jornada ou regime', '40H', scope); fill('Estrutura histórica da carreira', 'SINTETICA', scope);
    if (modality === 'TAE') { fill('Classificação TAE', 'E', scope); fill('Padrão TAE', level, scope); }
    else { fill('Classe docente', 'Adjunto', scope); fill('Nível docente', level, scope); }
  };
  const origin = screen.getByRole('group', { name: 'Posição de origem' });
  if (monthly) {
    await within(origin).findByText('Classe Adjunto · nível 1 · 40H');
    fill('Titulação inicial (RT)', 'Mestrado');
  } else {
    position(origin, '1');
    fill(modality === 'TAE' ? 'Escolaridade inicial' : 'Titulação inicial (RT)', modality === 'TAE' ? 'Graduação' : 'Mestrado', origin);
  }
  if (modality === 'TAE') fill('Percentual inicial de IQ', '10', origin);
  fill('Percentual inicial de anuênio', monthly ? '3' : '0', monthly ? document.body : origin);

  const rule = (scope: HTMLElement) => {
    fill('Regra ou ato de referência', 'REGRA-SINTETICA', scope); fill('Versão da regra ou ato', '1', scope); fill('Fonte da regra', 'Documento sintético', scope); fill('Início da vigência da regra', '2020-01-01', scope);
  };
  if (monthly) {
    fill('Nova classe', 'Adjunto'); fill('Novo nível', '2'); fill('Início dos efeitos financeiros', '2024-02-15');
  } else {
    ['VB', modality === 'TAE' ? 'IQ_SOBRE_VB' : 'RT'].forEach((formula, index) => {
      fireEvent.click(screen.getByRole('button', { name: 'Adicionar rubricas devidas' }));
      const row = screen.getByRole('group', { name: `Rubricas devidas: registro ${index + 1}` });
      fill('Código da rubrica', String(index + 1), row); fill('Natureza da folha (conforme a fonte)', 'NORMAL', row);
      fill('Natureza da rubrica', 'R', row); fill('Base de cálculo da rubrica', formula, row);
      rule(row);
    });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar mudanças no período' }));
    const progress = screen.getByRole('group', { name: 'Mudanças no período: registro 1' });
    fill('Tipo de mudança', 'PROGRESSAO', progress); fill('Início dos efeitos financeiros', '2024-02-15', progress); position(progress, '2'); rule(progress);
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar mudanças no período' }));
    const qualification = screen.getByRole('group', { name: 'Mudanças no período: registro 2' });
    fill('Tipo de mudança', modality === 'TAE' ? 'IQ' : 'RT', qualification); fill('Início dos efeitos financeiros', '2024-02-20', qualification);
    if (modality === 'TAE') { fill('Novo percentual de IQ', '20', qualification); fill('Nova escolaridade', 'Especialização', qualification); }
    else fill('Nova titulação (RT)', 'Doutorado', qualification);
    rule(qualification);
  }
  if (monthly) {
    fill('Nome do servidor', 'DOCENTE SINTÉTICO'); fill('Matrícula SIAPE', '123');
    expect(screen.getByLabelText('VB pago no mês (R$)')).toHaveValue('3100.00');
    expect(screen.getByLabelText('RT paga no mês (R$)')).toHaveValue('');
    fill('RT paga no mês (R$)', '0');
    fill('Fonte da RT paga', 'Ficha complementar sintética');
    fill('Justificativa da RT paga', 'Zero conferido na folha');
    expect(screen.queryByLabelText(/^Matrícula associada/)).toBeNull();
    expect(screen.queryByLabelText(/^Vínculo associado/)).toBeNull();
  }
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: /Conferi períodos/ }));
  if (monthly) {
    fireEvent.click(screen.getByRole('button', { name: 'Conferir diferenças com a tabela' }));
    const comparison = await screen.findByRole('list', { name: 'Comparação com a tabela' });
    expect(comparison).toHaveTextContent('Tabela de destino sintética');
    expect(comparison).toHaveTextContent('1.396,55');
    expect(requests.some(([url]) => url.includes('/calcular'))).toBe(false);
  }
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
  await screen.findByRole('button', { name: 'Baixar PDF' });
  const request = requests.find(([url]) => url.includes('/calcular'));
  const payload = JSON.parse(String(request?.[1]?.body));
  expect(payload).toMatchObject({ tipo_calculo: 'progressao', dados_extraidos: { progressao: { modalidade: modality, conferido_pelo_rh: true, reflexos: [], eventos: [
    { tipo: 'PROGRESSAO', efeitos_financeiros: '2024-02-15' }, ...(monthly ? [] : [{ tipo: modality === 'TAE' ? 'IQ' : 'RT', efeitos_financeiros: '2024-02-20' }]),
  ] } } });
  expect(payload.dados_extraidos).not.toHaveProperty('meses_diferenca');
  expect(payload.dados_extraidos.progressao.estado_inicial.posicao).toMatchObject({ [modality === 'TAE' ? 'padrao_tae' : 'nivel_docente']: 1 });
  expect(requests.some(([url]) => url.includes('/extrair-pdf'))).toBe(monthly);
  if (monthly) {
    expect(payload.dados_extraidos.progressao.rubricas.map((r: { rubrica: string }) => r.rubrica)).toEqual(['DIF-VB', 'DIF-RT', 'DIF-ANUENIO']);
    expect(payload.dados_extraidos.progressao.eventos[0].alteracoes.posicao).toMatchObject({ versao_carreira: 'SINTETICA', vinculo: 'EFETIVO', classe_docente: 'Adjunto', nivel_docente: 2 });
    expect(payload.dados_extraidos.progressao.estado_inicial).toMatchObject({ percentual_anuenio: '3' });
    expect(payload.dados_extraidos.progressao.bases_mensais_origem).toMatchObject([{ competencia: '2024-02', vb: { valor: '3100.00' }, rt: { valor: '0' } }]);
    expect(payload.dados_extraidos.revisao_extracao).toMatchObject({ confirmado: true, associacoes: [{ pessoa: 'SERVIDOR', matricula: '123', vinculo: 'EFETIVO', confirmado: true }], aplicacoes: [{ campo_id: 'vb', valor_revisado: '3100.00' }] });
  }
}

it.each(['TAE', 'DOCENTE'])('envia a progressão %s com referências e datas separadas, sem exigir upload', async modality => {
  await submitProgression(modality, false);
}, 15000);

it('envia a ficha corrigida, o anuênio e as confirmações na mesma tela', async () => {
  await submitProgression('DOCENTE', true);
}, 30000);
