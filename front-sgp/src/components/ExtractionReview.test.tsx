import { fireEvent, render, screen, act } from '@testing-library/react';
import { useState } from 'react';
import { expect, it } from 'vitest';
import { ExtractionReview } from './ExtractionReview';
import { mergeExtractions, object } from '../utils/documentExtraction';
import type { ExtractedDocument, Obj } from '../utils/documentExtraction';
import { emptyAbonoPlan } from '../utils/abonoReview';
import { emptySubstitutionPlan } from '../utils/substitutionReview';

const doc: ExtractedDocument = { id: 'DOC', nome_arquivo: 'sintetico.pdf', layout: 'FICHA_SIAPE', versao_leitor: 'rh_paginas_v1', situacao: 'PARCIAL', total_paginas: 2, blocos: [{ id: 'BLOCK', matricula: '999', nome: 'ALFA', categoria: 'TAE', paginas: [1, 2] }], campos: [{ id: 'MONEY', bloco_id: 'BLOCK', campo: 'rubrica', valor: '0.00', observado: '0,00', estado: 'EXTRAIDO', pagina: 2, localizador: 'Página 2, linha 1', rubrica: '98002', competencia: '2025-01', natureza: 'D', sequencia: '0' }, { id: 'MISSING', bloco_id: 'BLOCK', campo: 'inicio_exercicio', valor: null, estado: 'AUSENTE', pagina: null, localizador: 'Não encontrado', paginas_analisadas: [1, 2] }], avisos: [] };

function Harness() {
  const [data, setData] = useState<Obj>({ nome: '', matricula: '', abono: emptyAbonoPlan(), revisao_extracao: mergeExtractions(undefined, [doc]) });
  return <><ExtractionReview data={data} disabled={false} onChange={(path, value) => setData(path.length ? { ...data, [String(path[0])]: value } : object(value))} /><output data-testid="data">{JSON.stringify(data)}</output></>;
}

it('agrupa os campos sem perder a origem nem transformar ausência em zero', async () => {
  render(<Harness />);
  fireEvent.click(screen.getByText('Dados observados e campos não encontrados'));
  const group = await screen.findByLabelText('Grupo de campos (sintetico.pdf, bloco 1)');
  fireEvent.change(group, { target: { value: 'datas' } });
  expect(screen.queryByText(/Rubrica 98002/)).not.toBeInTheDocument();
  expect(screen.getByText(/Entrada em exercício no cargo: Não encontrado/)).toBeVisible();
  fireEvent.change(group, { target: { value: 'financeiro' } });
  expect(screen.getByText(/Rubrica 98002.*0.00/)).toBeVisible();
  expect(screen.getByText(/Observado: 0,00/)).toBeVisible();
});

function IdentificationHarness() {
  const source: ExtractedDocument = { ...doc, campos: [
    { id: 'NAME', bloco_id: 'BLOCK', campo: 'nome', valor: 'ALFA', estado: 'EXTRAIDO', pagina: 1, localizador: 'Cabeçalho, página 1' },
    { id: 'EMPLOYEE', bloco_id: 'BLOCK', campo: 'matricula', valor: '999', estado: 'EXTRAIDO', pagina: 1, localizador: 'Cabeçalho, página 1' },
  ] };
  const [data, setData] = useState<Obj>({ nome: '', matricula: '', progressao: { inicio: '', conferido_pelo_rh: false }, revisao_extracao: mergeExtractions(undefined, [source]) });
  return <><ExtractionReview data={data} disabled={false} onChange={(path, value) => setData(path.length ? { ...data, [String(path[0])]: value } : object(value))} /><output data-testid="identification">{JSON.stringify(data)}</output></>;
}

it('permite aproveitar a identificação da ficha em um rascunho existente sem confirmar a revisão', () => {
  render(<IdentificationHarness />);
  fireEvent.click(screen.getByRole('button', { name: 'Preencher identificação a partir da ficha' }));
  const data = JSON.parse(screen.getByTestId('identification').textContent!);
  expect(data).toMatchObject({ nome: 'ALFA', matricula: '999', progressao: { inicio: '', conferido_pelo_rh: false } });
  expect(data.revisao_extracao.aplicacoes).toHaveLength(2);
  expect(data.revisao_extracao.confirmado).toBe(false);
  expect(data.revisao_extracao.associacoes[0].confirmado).toBe(false);
  expect(screen.queryByRole('button', { name: 'Preencher identificação a partir da ficha' })).not.toBeInTheDocument();
});

function ConflictHarness() {
  const source: ExtractedDocument = { ...doc, campos: [{ ...doc.campos[0], campo: 'nome', valor: 'ALFA', observado: 'ALFA' }] };
  const [data, setData] = useState<Obj>({ nome: 'EDITADO MANUALMENTE', revisao_extracao: mergeExtractions(undefined, [source]) });
  return <><ExtractionReview data={data} disabled={false} onChange={(path, value) => setData(path.length ? { ...data, [String(path[0])]: value } : object(value))} /><output data-testid="data">{JSON.stringify(data)}</output></>;
}

it('conflito preserva edição até a substituição explícita e justificada', async () => {
  render(<ConflictHarness />);
  fireEvent.click(screen.getByLabelText('Conferi pessoa, vínculo e papel deste bloco'));
  fireEvent.click(screen.getByText('Dados observados e campos não encontrados'));
  fireEvent.change(await screen.findByLabelText('Destino do campo 1 — sintetico.pdf'), { target: { value: JSON.stringify(['nome']) } });
  const replace = screen.getByRole('button', { name: 'Substituir valor ou fonte após conferência' });
  expect(replace).toBeDisabled();
  expect(JSON.parse(screen.getByTestId('data').textContent!).nome).toBe('EDITADO MANUALMENTE');
  fireEvent.change(screen.getByLabelText('Justificativa da substituição no campo 1 — sintetico.pdf'), { target: { value: 'Fonte conferida pelo RH' } });
  fireEvent.click(replace);
  const data = JSON.parse(screen.getByTestId('data').textContent!);
  expect(data.nome).toBe('ALFA');
  expect(data.revisao_extracao.aplicacoes[0]).toMatchObject({ valor_anterior: 'EDITADO MANUALMENTE', justificativa: 'Fonte conferida pelo RH' });
});

function VacationHarness() {
  const source: ExtractedDocument = { ...doc, campos: [{ ...doc.campos[0], campo: 'periodo_ferias', valor: '10', estado: 'AMBIGUO', inicio: '2026-01-01', fim: null, fim_informado: '2026-01-20', fim_calculado: '2026-01-10' }] };
  const [data, setData] = useState<Obj>({ substituicao: emptySubstitutionPlan(), revisao_extracao: mergeExtractions(undefined, [source]) });
  return <><ExtractionReview data={data} disabled={false} onChange={(path, value) => setData(path.length ? { ...data, [String(path[0])]: value } : object(value))} /><output data-testid="data">{JSON.stringify(data)}</output></>;
}

function ActHarness() {
  const source: ExtractedDocument = { ...doc, layout: 'PORTARIA_UFPI_DOCENTE', versao_leitor: 'rh_paginas_v3', campos: [{ ...doc.campos[0], campo: 'efeitos_financeiros', valor: null, estado: 'AMBIGUO', observado: '05.02.2026 | 06.02.2026', candidatos: ['05.02.2026', '06.02.2026'] }] };
  const [data, setData] = useState<Obj>({ progressao: { data_documento: '', eventos: [{ efeitos_financeiros: '' }] }, revisao_extracao: mergeExtractions(undefined, [source]) });
  return <><ExtractionReview data={data} disabled={false} onChange={(path, value) => setData(path.length ? { ...data, [String(path[0])]: value } : object(value))} /><output data-testid="data">{JSON.stringify(data)}</output></>;
}

it('ato ambíguo mantém campo vazio, mostra candidatos e permite resolução editável com origem', async () => {
  render(<ActHarness />);
  fireEvent.click(screen.getByLabelText('Conferi pessoa, vínculo e papel deste bloco'));
  fireEvent.click(screen.getByText('Dados observados e campos não encontrados'));
  await screen.findByText(/Candidatos para revisão: 05.02.2026/);
  const input = screen.getByLabelText('Valor a aplicar no campo 1 — sintetico.pdf');
  expect(input).toHaveValue('');
  const target = screen.getByLabelText('Destino do campo 1 — sintetico.pdf');
  expect(target.querySelectorAll('option')).toHaveLength(2);
  fireEvent.change(target, { target: { value: JSON.stringify(['progressao', 'eventos', 0, 'efeitos_financeiros']) } });
  const button = screen.getByRole('button', { name: 'Aplicar ao campo escolhido' });
  expect(button).toBeDisabled();
  fireEvent.change(input, { target: { value: '2026-02-05' } });
  fireEvent.click(button);
  const payload = JSON.parse(screen.getByTestId('data').textContent!);
  expect(payload.progressao.eventos[0].efeitos_financeiros).toBe('2026-02-05');
  expect(payload.revisao_extracao.documentos[0].campos[0].valor).toBeNull();
  fireEvent.change(screen.getByLabelText('Justificativa da correção 1'), { target: { value: 'Conferido manualmente com o ato sintético.' } });
  expect(JSON.parse(screen.getByTestId('data').textContent!).revisao_extracao.aplicacoes[0].justificativa).toContain('manualmente');
});

it('mostra página real, ausência sem página fictícia e exige associação antes de aplicar', async () => {
  render(<Harness />);
  expect(screen.getByText(/Valores observados: 1\. Ocorrências de rubricas: 1\./)).not.toBeVisible();
  fireEvent.click(screen.getByText('Detalhes da leitura'));
  expect(screen.getByText(/Valores observados: 1\. Ocorrências de rubricas: 1\./)).toBeVisible();
  await act(async () => { fireEvent.click(screen.getByText('Dados observados e campos não encontrados')); });
  await screen.findByText(/sintetico.pdf · página 2/);
  expect(screen.getByText(/Ausência nas páginas 1, 2/)).toBeInTheDocument();
  const add = screen.getByRole('button', { name: 'Adicionar rubrica à revisão financeira' });
  expect(add).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Conferi pessoa, vínculo e papel deste bloco'));
  fireEvent.click(add);
  const payload = JSON.parse(screen.getByTestId('data').textContent!);
  expect(payload.abono.lancamentos[0]).toMatchObject({ valor: '0.00', rubrica: '98002', operacao: '', papel: '', conferido: false });
  expect(add).toBeDisabled();
  expect(payload.revisao_extracao.aplicacoes[0].destino).toEqual(['abono', 'lancamentos', 0, 'valor']);
});

it('alterar associação retira a confirmação e o descarte não permite aplicar valores', async () => {
  render(<Harness />);
  await act(async () => { fireEvent.click(screen.getByText('Dados observados e campos não encontrados')); });
  await screen.findByRole('button', { name: 'Adicionar rubrica à revisão financeira' });
  const confirm = screen.getByLabelText('Conferi pessoa, vínculo e papel deste bloco');
  fireEvent.click(confirm); expect(confirm).toBeChecked();
  fireEvent.change(screen.getByLabelText('Vínculo associado (sintetico.pdf, bloco 1)'), { target: { value: 'V1' } });
  expect(confirm).not.toBeChecked();
  fireEvent.change(screen.getByLabelText('Pessoa no cálculo (sintetico.pdf, bloco 1)'), { target: { value: 'DESCARTADO' } });
  fireEvent.click(confirm);
  expect(screen.getByRole('button', { name: 'Adicionar rubrica à revisão financeira' })).toBeDisabled();
});

it('mostra fim informado e calculado sem aplicar nenhum deles automaticamente', async () => {
  render(<VacationHarness />);
  fireEvent.click(screen.getByLabelText('Conferi pessoa, vínculo e papel deste bloco'));
  fireEvent.click(screen.getByText('Dados observados e campos não encontrados'));
  await screen.findByText(/Fim informado: 2026-01-20; fim pelos dias: 2026-01-10/);
  const button = screen.getByRole('button', { name: 'Adicionar período para conferir sua aplicação' });
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Fim escolhido para o campo 1 — sintetico.pdf'), { target: { value: '2026-01-10' } });
  fireEvent.click(button);
  const result = JSON.parse(screen.getByTestId('data').textContent!);
  expect(result.substituicao.impedimentos_substituto[0].ultimo_dia_considerado).toBe('2026-01-10');
  expect(result.substituicao.conferido_pelo_rh).toBe(false);
  expect(result.revisao_extracao.aplicacoes).toHaveLength(2);
});
