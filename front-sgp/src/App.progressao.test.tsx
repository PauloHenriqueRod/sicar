import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('isLoggedIn', 'true'); localStorage.setItem('role', 'user');
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

it.each(['TAE', 'DOCENTE'])('envia a progressão %s com referências e datas separadas, sem exigir upload', async modality => {
  const requests: [string, RequestInit | undefined][] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    requests.push([String(url), options]);
    const body = String(url).includes('/calcular') ? { historico_id: 123, resultado_calculo: { tipo_apuracao: 'periodos_v1', tipo_progressao: 'eventos_v1', total_geral_a_receber: '1850.00' } }
      : { total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] };
    return new Response(JSON.stringify(body), { status: 200 });
  }));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'progressao' } });
  expect(screen.getByText(/PDFs e portarias são opcionais/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByLabelText('Modalidade da progressão');
  const fill = (label: string, value: string, scope: HTMLElement = document.body) => fireEvent.change(within(scope).getByLabelText(label), { target: { value } });
  fill('Modalidade da progressão', modality);
  fill('Início da apuração', '2024-02-01'); fill('Último dia considerado (incluído)', '2024-02-29');
  const position = (scope: HTMLElement, level: string) => {
    fill('Carreira', modality === 'TAE' ? 'TAE' : 'MAGISTERIO_SUPERIOR', scope);
    fill('Vínculo (conforme a tabela)', 'EFETIVO', scope); fill('Jornada ou regime', '40H', scope); fill('Estrutura histórica da carreira', 'SINTETICA', scope);
    if (modality === 'TAE') { fill('Classificação TAE', 'E', scope); fill('Padrão TAE', level, scope); }
    else { fill('Classe docente', 'Adjunto', scope); fill('Nível docente', level, scope); }
  };
  const origin = screen.getByRole('group', { name: 'Posição de origem' });
  position(origin, '1');
  fill(modality === 'TAE' ? 'Escolaridade inicial' : 'Titulação inicial (RT)', modality === 'TAE' ? 'Graduação' : 'Mestrado', origin);
  if (modality === 'TAE') fill('Percentual inicial de IQ', '10', origin);
  fill('Percentual inicial de anuênio', '0', origin);
  const rule = (scope: HTMLElement) => {
    fill('Regra ou ato de referência', 'REGRA-SINTETICA', scope); fill('Versão da regra ou ato', '1', scope); fill('Fonte da regra', 'Documento sintético', scope); fill('Início da vigência da regra', '2020-01-01', scope);
  };
  ['VB', modality === 'TAE' ? 'IQ_SOBRE_VB' : 'RT'].forEach((formula, index) => {
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar rubricas devidas' }));
    const row = screen.getByRole('group', { name: `Rubricas devidas: registro ${index + 1}` });
    fill('Código da rubrica', String(index + 1), row); fill('Natureza da folha (conforme a fonte)', 'NORMAL', row); fill('Natureza da rubrica', 'R', row); fill('Base de cálculo da rubrica', formula, row); rule(row);
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
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: /Conferi períodos/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar e Calcular' }));
  await screen.findByRole('button', { name: 'Baixar PDF' });
  const request = requests.find(([url]) => url.includes('/calcular'));
  const payload = JSON.parse(String(request?.[1]?.body));
  expect(payload).toMatchObject({ tipo_calculo: 'progressao', dados_extraidos: { progressao: { modalidade: modality, conferido_pelo_rh: true, reflexos: [], eventos: [
    { tipo: 'PROGRESSAO', efeitos_financeiros: '2024-02-15' }, { tipo: modality === 'TAE' ? 'IQ' : 'RT', efeitos_financeiros: '2024-02-20' },
  ] } } });
  expect(payload.dados_extraidos).not.toHaveProperty('meses_diferenca');
  expect(payload.dados_extraidos.progressao.estado_inicial.posicao).toMatchObject({ [modality === 'TAE' ? 'padrao_tae' : 'nivel_docente']: 1 });
  expect(requests.some(([url]) => url.includes('/extrair-pdf'))).toBe(false);
}, 15000);
