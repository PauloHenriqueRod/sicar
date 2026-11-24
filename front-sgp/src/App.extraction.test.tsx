import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';

const doc = { id: 'DOC', nome_arquivo: 'sintetico.pdf', impressao: 'a'.repeat(64), layout: 'CADASTRO_FUNCIONAL', versao_leitor: 'rh_paginas_v1', situacao: 'CONCLUIDO', total_paginas: 1, blocos: [{ id: 'B', matricula: '999', nome: 'ALFA', vinculo: 'V1', categoria: 'SUBSTITUTO', paginas: [1] }], campos: [{ id: 'F', bloco_id: 'B', campo: 'inicio_exercicio', valor: '2025-01-16', observado: '16/01/2025', estado: 'EXTRAIDO', pagina: 1, localizador: 'Página 1, CARGO/EMPREGO' }], avisos: [] };
const json = (value: unknown) => new Response(JSON.stringify(value));
beforeEach(() => { localStorage.clear(); localStorage.setItem('isLoggedIn', 'true'); localStorage.setItem('role', 'user'); vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))); });
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

it.each(['NOME REVISADO', ''])('preenche a identificação inequívoca da ficha e preserva a edição "%s" na reextração', async revisedName => {
  const financial = { ...doc, layout: 'FICHA_SIAPE', versao_leitor: 'rh_paginas_v4', blocos: [{ ...doc.blocos[0], categoria: 'DOCENTE' }], campos: [
    { ...doc.campos[0], id: 'NAME', campo: 'nome', valor: 'ALFA' },
    { ...doc.campos[0], id: 'EMPLOYEE', campo: 'matricula', valor: '999' },
  ] };
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => String(url).includes('/extrair-pdf') ? json({ versao_contrato: 2, resultados: [{ filename: 'ficha.pdf', extracao: financial }], falhas: [] }) : json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] })));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'progressao' } });
  const file = new File(['sintético'], 'ficha.pdf');
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await waitFor(() => expect(screen.getByLabelText('Nome do servidor')).toHaveValue('ALFA'));
  expect(screen.getByLabelText('Matrícula SIAPE')).toHaveValue('999');
  expect(screen.getByLabelText('Modalidade da progressão')).toHaveValue('');
  expect(screen.getByLabelText('Início da apuração')).toHaveValue('');
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
  expect(screen.getByText('Valores aplicados e correções')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Nome do servidor'), { target: { value: revisedName } });
  fireEvent.click(screen.getByText('Adicionar ou repetir documentos'));
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: 'Extrair arquivos selecionados preservando edições' }));
  await waitFor(() => expect(screen.getByLabelText('Selecionar PDFs — Ficha Financeira')).not.toBeDisabled());
  expect(screen.getByLabelText('Nome do servidor')).toHaveValue(revisedName);
  expect(screen.getByLabelText('Matrícula SIAPE')).toHaveValue('999');
});

it('envia fontes de seções diferentes para uma única revisão sem aplicar identidades automaticamente', async () => {
  let sent: File[] = [];
  let metadata: { id: string; categoria: string }[] = [];
  const financial = { ...doc, id: 'FIN', nome_arquivo: 'ficha.pdf', impressao: 'b'.repeat(64), layout: 'FICHA_FINANCEIRA', campos: [] };
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    if (String(url).includes('/extrair-pdf')) {
      sent = (options?.body as FormData).getAll('arquivos') as File[];
      metadata = JSON.parse(String((options?.body as FormData).get('metadados_arquivos')));
      return json({ versao_contrato: 2, resultados: [{ filename: 'ficha.pdf', extracao: financial }, { filename: 'cadastro.pdf', extracao: { ...doc, nome_arquivo: 'cadastro.pdf' } }], falhas: [] });
    }
    return json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] });
  }));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'rescisao' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [new File(['ficha'], 'ficha.pdf')] } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Cadastro funcional'), { target: { files: [new File(['cadastro'], 'cadastro.pdf')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByRole('region', { name: 'Fontes e associação dos documentos' });
  expect(sent.map(file => file.name)).toEqual(['ficha.pdf', 'cadastro.pdf']);
  expect(metadata.map(item => item.categoria)).toEqual(['financeira', 'cadastro']);
  expect(new Set(metadata.map(item => item.id)).size).toBe(2);
  expect(screen.getAllByLabelText('Nome do servidor')).toHaveLength(1);
  expect(screen.getByLabelText('Matrícula SIAPE')).toHaveValue('');
  expect(screen.getByLabelText('Entrada em exercício')).toHaveValue('');
  expect(screen.queryByRole('button', { name: 'Próximo arquivo' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Baixar lote (ZIP)' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Selecionar PDFs — Cadastro funcional')).toBeEnabled();
});

it('trocar a modalidade limpa os anexos anteriores sem movê-los para outra seção', () => {
  vi.stubGlobal('fetch', vi.fn(async () => json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] })));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'rescisao' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Cadastro funcional'), { target: { files: [new File(['cadastro'], 'cadastro.pdf')] } });
  expect(screen.getByText('cadastro.pdf')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'progressao' } });
  expect(screen.queryByLabelText('Selecionar PDFs — Cadastro funcional')).not.toBeInTheDocument();
  expect(screen.queryByText('cadastro.pdf')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Selecionar PDFs — Ato ou portaria de progressão e IQ/RT')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Continuar para revisão' })).toBeEnabled();
});

it('mostra cada arquivo pendente e oferece entrada manual após erro de rede', async () => {
  let rejectUpload: (error: Error) => void = () => {};
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => String(url).includes('/extrair-pdf') ? new Promise<Response>((_, reject) => { rejectUpload = reject; }) : json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] })));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'apuracao_periodos' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [new File(['x'], 'alfa.pdf'), new File(['y'], 'beta.pdf')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  const progress = screen.getByRole('region', { name: 'Situação dos arquivos' });
  expect(progress).toHaveTextContent('alfa.pdf: Enviado; aguardando resposta');
  expect(progress).toHaveTextContent('beta.pdf: Enviado; aguardando resposta');
  await act(async () => { rejectUpload(new Error('Falha de rede sintética')); });
  const manual = await screen.findByRole('button', { name: 'Continuar com preenchimento manual' });
  fireEvent.click(manual);
  expect(await screen.findByLabelText('Início da apuração')).toHaveValue('');
  expect(screen.queryByRole('region', { name: 'Situação dos arquivos' })).not.toBeInTheDocument();
});

it('sem portarias ou qualquer anexo avança para edição sem chamar extração', async () => {
  const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
    if (String(url).includes('/extrair-pdf')) throw new Error('Extração inesperada sem anexos');
    return json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] });
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'rescisao' } });
  expect(screen.getByText(/PDFs e portarias são opcionais/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  const field = await screen.findByLabelText('Entrada em exercício');
  expect(field).toHaveValue('');
  fireEvent.change(field, { target: { value: '2025-01-16' } });
  expect(field).toHaveValue('2025-01-16');
  expect(fetchMock.mock.calls.every(call => !String(call[0]).includes('/extrair-pdf'))).toBe(true);
  expect(screen.queryByRole('region', { name: 'Fontes e associação dos documentos' })).not.toBeInTheDocument();
});

it('preserva formulário e edições ao repetir apenas um PDF depois de falha parcial', async () => {
  let calls = 0;
  const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
    if (String(url).includes('/extrair-pdf')) { calls += 1; return json({ versao_contrato: 2, resultados: [{ filename: 'sintetico.pdf', dados_extraidos: {}, extracao: { ...doc, id: calls === 1 ? 'DOC' : 'OTHER' } }], falhas: calls === 1 ? [{ filename: 'quebrado.pdf', codigo: 'pdf_400', mensagem: 'Arquivo inválido' }] : [] }); }
    return json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] });
  });
  vi.stubGlobal('fetch', fetchMock); render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'rescisao' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [new File(['sintetico'], 'sintetico.pdf', { type: 'application/pdf' })] } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByRole('region', { name: 'Fontes e associação dos documentos' });
  expect(screen.getByText('quebrado.pdf: Arquivo inválido')).toBeVisible();
  expect(screen.getByRole('region', { name: 'Situação dos arquivos' })).toHaveTextContent('sintetico.pdf: CONCLUIDO');
  expect(screen.getByRole('region', { name: 'Situação dos arquivos' })).toHaveTextContent('quebrado.pdf: Falha');
  fireEvent.change(screen.getByLabelText('Matrícula SIAPE'), { target: { value: '999' } });
  fireEvent.change(screen.getByLabelText('Entrada em exercício'), { target: { value: '2025-01-20' } });
  fireEvent.click(screen.getByText('Adicionar ou repetir documentos'));
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [new File(['sintetico'], 'sintetico.pdf', { type: 'application/pdf' })] } });
  fireEvent.click(screen.getByRole('button', { name: 'Extrair arquivos selecionados preservando edições' }));
  await waitFor(() => { expect(calls).toBe(2); expect(screen.getByLabelText('Selecionar PDFs — Ficha Financeira')).not.toBeDisabled(); expect(screen.queryByText('quebrado.pdf: Arquivo inválido')).not.toBeInTheDocument(); });
  expect(screen.getByLabelText('Entrada em exercício')).toHaveValue('2025-01-20');
  expect(screen.getAllByText('Matrícula 999 · vínculo V1')).toHaveLength(1);
  expect(calls).toBe(2);
});

it('todos os arquivos falhando ainda abre formulário manual com diagnóstico individual', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => String(url).includes('/extrair-pdf') ? json({ versao_contrato: 2, resultados: [], falhas: [{ filename: 'invalido.pdf', codigo: 'pdf_400', mensagem: 'Não foi possível ler' }] }) : json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] })));
  render(<App />); fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'abono' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [new File(['erro'], 'invalido.pdf', { type: 'application/pdf' })] } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByText('invalido.pdf: Não foi possível ler');
  expect(screen.getByLabelText('Identificação do vínculo')).toHaveValue('');
  expect(screen.getByLabelText('Matrícula SIAPE')).toHaveValue('');
});

it('aplica a data com origem e permite confirmar fontes e cálculo sem invalidar um ao outro', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => String(url).includes('/extrair-pdf') ? json({ versao_contrato: 2, resultados: [{ filename: 'sintetico.pdf', dados_extraidos: {}, extracao: doc }], falhas: [] }) : json({ total_calculos: 0, total_usuarios: 1, calculos_por_tipo: {}, ultimos_calculos: [] })));
  render(<App />); fireEvent.click(screen.getByRole('button', { name: 'Cálculos' }));
  fireEvent.change(screen.getByLabelText('Tipo de cálculo'), { target: { value: 'rescisao' } });
  fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [new File(['sintetico'], 'sintetico.pdf', { type: 'application/pdf' })] } });
  fireEvent.click(screen.getByRole('button', { name: 'Continuar para revisão' }));
  await screen.findByRole('region', { name: 'Fontes e associação dos documentos' });
  fireEvent.change(screen.getByLabelText('Matrícula SIAPE'), { target: { value: '999' } });
  fireEvent.change(screen.getByLabelText('Vínculo ou contrato deste cálculo'), { target: { value: 'V1' } });
  fireEvent.change(screen.getByLabelText('Matrícula associada (sintetico.pdf, bloco 1)'), { target: { value: '999' } });
  fireEvent.change(screen.getByLabelText('Vínculo associado (sintetico.pdf, bloco 1)'), { target: { value: 'V1' } });
  fireEvent.click(screen.getByLabelText('Conferi pessoa, vínculo e papel deste bloco'));
  fireEvent.click(screen.getByText('Dados observados e campos não encontrados'));
  const target = await screen.findByLabelText('Destino do campo 1 — sintetico.pdf');
  fireEvent.change(target, { target: { value: JSON.stringify(['rescisao', 'inicio_exercicio']) } });
  fireEvent.click(screen.getByRole('button', { name: 'Aplicar ao campo escolhido' }));
  expect(screen.getByLabelText('Entrada em exercício')).toHaveValue('2025-01-16');
  const sourceApproval = screen.getByLabelText('Conferi as associações, as fontes e os valores finais aplicados');
  const calculationApproval = screen.getByLabelText('Conferi contrato, datas, regra, bases, avos e pagamentos das parcelas calculadas');
  fireEvent.click(sourceApproval); fireEvent.click(calculationApproval);
  expect(sourceApproval).toBeChecked(); expect(calculationApproval).toBeChecked();
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeEnabled();
  fireEvent.change(screen.getByLabelText('Entrada em exercício'), { target: { value: '2025-01-20' } });
  expect(sourceApproval).not.toBeChecked(); expect(calculationApproval).not.toBeChecked();
  fireEvent.click(screen.getByText('Valores aplicados e correções'));
  expect(screen.getByText(/observado 2025-01-16 → utilizado 2025-01-20/)).toBeVisible();
});
