import { expect, it } from 'vitest';
import { applyField, appendFinancialCandidate, appendVacation, mergeExtractions, suggestProgressionIdentification, syncApplications, onlyGlobalApprovalChanged, fieldTargets } from './documentExtraction';
import type { ExtractedDocument, ExtractionReview } from './documentExtraction';
import { emptyAbonoPlan } from './abonoReview';
import { serializeReviewData } from './reviewData';
import { emptySubstitutionPlan } from './substitutionReview';

it('keeps reader revisions separate without duplicating the same extraction or applying money', () => {
  const source: ExtractedDocument = { ...doc, versao_leitor: 'rh_paginas_v5', leitores: [{ identificador: 'siape_tae', versao: '1', paginas: [1] }] };
  const first = mergeExtractions(undefined, [source]);
  expect(mergeExtractions(first, [{ ...source, id: 'RETRY' }]).documentos).toHaveLength(1);
  const next = mergeExtractions(first, [{ ...source, id: 'NEW', leitores: [{ identificador: 'siape_tae', versao: '2', paginas: [1] }] }]);
  expect(next.documentos).toHaveLength(2);
  expect(next.aplicacoes).toHaveLength(0);
  expect(next.confirmado).toBe(false);
});

it('does not add canceled vacations and restricts the target of the exercise date', () => {
  const field = { ...doc.campos[0], campo: 'periodo_ferias', inicio: '2026-01-01', fim: '2026-01-10', cancelada: true };
  const review = mergeExtractions(undefined, [doc]);
  const data = { substituicao: emptySubstitutionPlan(), rescisao: { inicio_exercicio: '', data_termino: '' }, revisao_extracao: review };
  expect(() => appendVacation(data, doc, field, false)).toThrow(/cancelada/);
  expect(fieldTargets(data, doc, { ...field, campo: 'inicio_exercicio' })).toEqual([['rescisao', 'inicio_exercicio']]);
});

function identificationSource(): ExtractedDocument {
  return { ...doc, versao_leitor: 'rh_paginas_v4', campos: [
    { ...doc.campos[0], id: 'NAME', bloco_id: doc.blocos[0].id, campo: 'nome', valor: doc.blocos[0].nome!, observado: doc.blocos[0].nome! },
    { ...doc.campos[0], id: 'EMPLOYEE', bloco_id: doc.blocos[0].id, campo: 'matricula', valor: doc.blocos[0].matricula!, observado: doc.blocos[0].matricula! },
  ] };
}

it('suggests only proven identification, keeps its source and does not approve the progression or the association', () => {
  const source = identificationSource();
  const review = mergeExtractions(undefined, [source]);
  const plan = { modalidade: '', inicio: '', estado_inicial: { posicao: { carreira: '' } }, conferido_pelo_rh: false };
  const result = suggestProgressionIdentification({ nome: '', matricula: '', progressao: plan, revisao_extracao: review });
  expect(result).toMatchObject({ nome: 'ALFA SINTETICO', matricula: '000999', progressao: plan });
  const final = result.revisao_extracao as ExtractionReview;
  expect(final.aplicacoes.map(a => [a.campo_id, a.destino, a.valor_revisado])).toEqual([
    ['NAME', ['nome'], 'ALFA SINTETICO'], ['EMPLOYEE', ['matricula'], '000999'],
  ]);
  expect(final.confirmado).toBe(false);
  expect(final.associacoes[0]).toMatchObject({ confirmado: false, matricula: '', vinculo: '' });
  expect(review.aplicacoes).toHaveLength(0);
  expect(final.documentos[0]).toEqual(source);
});

it.each(['person', 'name', 'link', 'ambiguous', 'missing-proof'])('does not suggest identification from incompatible or uncertain sources (%s)', change => {
  const source = identificationSource();
  const other = structuredClone(source);
  other.id = 'OTHER'; other.impressao = 'b'.repeat(64);
  if (change === 'person') other.blocos[0].matricula = '888';
  if (change === 'name') other.blocos[0].nome = 'OUTRA PESSOA';
  if (change === 'link') { source.blocos[0].vinculo = 'V1'; other.blocos[0].vinculo = 'V2'; }
  if (change === 'ambiguous') source.campos.forEach(field => { field.estado = 'AMBIGUO'; });
  if (change === 'missing-proof') source.campos = [];
  const documents = ['ambiguous', 'missing-proof'].includes(change) ? [source] : [source, other];
  const data = { nome: '', matricula: '', progressao: {}, revisao_extracao: mergeExtractions(undefined, documents) };
  expect(suggestProgressionIdentification(data)).toEqual(data);
});

it('preserves values already entered and never creates missing dates, positions or financial entries', () => {
  const data = { nome: 'NOME CONFERIDO', matricula: '123', progressao: { inicio: '', rubricas: [], recebidos: [] }, revisao_extracao: mergeExtractions(undefined, [identificationSource()]) };
  expect(suggestProgressionIdentification(data)).toEqual(data);
});

it('does not fill the name of a different person when the form already has an employee number', () => {
  const data = { nome: '', matricula: '888', progressao: {}, revisao_extracao: mergeExtractions(undefined, [identificationSource()]) };
  expect(suggestProgressionIdentification(data)).toEqual(data);
});

it('resolve conflito explicitamente sem perder sugestão, valor manual ou fonte anterior', () => {
  const data = { nome: '', revisao_extracao: mergeExtractions(undefined, [doc]) };
  const first = applyField(data, doc, doc.campos[0], ['nome'], '100');
  const edited = syncApplications({ ...first, nome: '140' });
  expect(() => applyField(edited, doc, doc.campos[0], ['nome'], '200')).toThrow();
  expect(() => applyField(edited, doc, doc.campos[0], ['nome'], '200', '', true)).toThrow(/Justifique/);
  const resolved = applyField(edited, doc, doc.campos[0], ['nome'], '200', 'Valor confirmado pelo RH', true);
  expect(resolved.nome).toBe('200');
  const review = resolved.revisao_extracao as ExtractionReview;
  expect(review.aplicacoes).toHaveLength(1);
  expect(review.aplicacoes[0]).toMatchObject({ valor_anterior: '140', valor_revisado: '200' });
  expect(review.historico_aplicacoes?.[0].valor_revisado).toBe('140');
  expect(review.documentos[0].campos[0].valor).toBe('-330.00');
  expect(edited.nome).toBe('140');
});

export const doc: ExtractedDocument = { id: 'DOC', nome_arquivo: 'sintetico.pdf', impressao: 'a'.repeat(64), layout: 'FICHA_SIAPE', versao_leitor: 'rh_paginas_v1', situacao: 'CONCLUIDO', total_paginas: 2, blocos: [{ id: 'B', matricula: '000999', nome: 'ALFA SINTETICO', categoria: 'TAE', paginas: [1, 2] }], campos: [{ id: 'F', bloco_id: 'B', campo: 'rubrica', valor: '-330.00', observado: '-330,00', estado: 'EXTRAIDO', pagina: 2, localizador: 'Página 2, linha 4', competencia: '2025-01', rubrica: '98002', natureza: 'D', sequencia: '6' }], avisos: [] };

it('papel explícito do titular não é substituto e permanece sujeito à associação manual', () => {
  const source: ExtractedDocument = { ...doc, layout: 'ATO_UFPI_SUBSTITUICAO', versao_leitor: 'rh_paginas_v3', blocos: [{ ...doc.blocos[0], papel_documental: 'TITULAR' }] };
  const review = mergeExtractions(undefined, [source]);
  expect(review.associacoes[0]).toMatchObject({ pessoa: 'TITULAR', matricula: '', vinculo: '', confirmado: false });
});

it('destinos não trocam data documental, efeitos, início e fim ou função própria', () => {
  const data = { nome: '', substituicao: emptySubstitutionPlan(), revisao_extracao: mergeExtractions(undefined, [doc]), progressao: { data_documento: '', eventos: [{ efeitos_financeiros: '' }] } };
  const paths = (campo: string) => fieldTargets(data, doc, { ...doc.campos[0], campo });
  expect(paths('data_documento')).toContainEqual(['progressao', 'data_documento']);
  expect(paths('data_documento')).not.toContainEqual(['progressao', 'eventos', 0, 'efeitos_financeiros']);
  expect(paths('efeitos_financeiros')).toEqual([['progressao', 'eventos', 0, 'efeitos_financeiros']]);
  expect(paths('fim_designacao').every(path => path.at(-1) === 'ultimo_dia_considerado')).toBe(true);
  expect(paths('codigo_funcao_substituida')).toEqual([['substituicao', 'estado_inicial', 'substituida', 'codigo_funcao']]);
});

it('mantém documentos e blocos separados e não confirma associações automaticamente', () => {
  const review = mergeExtractions(undefined, [doc, { ...doc, id: 'OTHER', impressao: 'b'.repeat(64), blocos: [{ id: 'C', matricula: '888', categoria: 'SUBSTITUTO', paginas: [1] }] }]);
  expect(review.documentos).toHaveLength(2);
  expect(review.associacoes).toMatchObject([{ matricula: '', vinculo: '', confirmado: false }, { matricula: '', confirmado: false }]);
});

it('reextrair o mesmo conteúdo conserva fontes aplicadas e edições já feitas', () => {
  const review = mergeExtractions(undefined, [doc]); review.vinculo_calculo = 'V1'; review.associacoes[0].confirmado = true;
  const merged = mergeExtractions(review, [{ ...doc, id: 'NEW', campos: [{ ...doc.campos[0], id: 'NEW-F', valor: '999' }] }]);
  expect(merged.documentos[0].campos[0].valor).toBe('-330.00');
  expect(merged.documentos).toHaveLength(1);
  expect(merged.associacoes[0].confirmado).toBe(true);
  expect(merged.confirmado).toBe(false);
});

it('leva uma ocorrência para revisão sem presumir papel, operação ou concessão', () => {
  const data = { abono: emptyAbonoPlan(), revisao_extracao: mergeExtractions(undefined, [doc]) };
  const next = appendFinancialCandidate(data, doc, doc.campos[0]);
  expect(next.abono).toMatchObject({ lancamentos: [{ rubrica: '98002', competencia: '2025-01', natureza_rubrica: 'D', valor: '330.00', papel: '', categoria: '', operacao: '', conferido: false }] });
  expect(next.revisao_extracao).toMatchObject({ aplicacoes: [{ valor_revisado: '330.00', justificativa: '', registro_id: expect.any(String) }] });
});

it('não sobrescreve valor editado nem vincula duas fontes ao mesmo destino', () => {
  const base = { nome: 'MANUAL', revisao_extracao: mergeExtractions(undefined, [doc]) };
  expect(() => applyField(base, doc, doc.campos[0], ['nome'], 'NOVO')).toThrow(/não sobrescreve/);
  const blank = { nome: '', revisao_extracao: mergeExtractions(undefined, [doc]) };
  const first = applyField(blank, doc, doc.campos[0], ['nome'], 'ALFA');
  expect(() => applyField(first, doc, doc.campos[0], ['nome'], 'ALFA')).toThrow(/já associado/);
});

it('preserva identidade da origem ao remover uma linha anterior e retira vínculo de linha removida', () => {
  const review = mergeExtractions(undefined, [doc]); review.aplicacoes = [{ documento_id: 'DOC', campo_id: 'F', destino: ['abono', 'lancamentos', 1, 'valor'], valor_revisado: '330.00', justificativa: '', registro_id: 'SECOND' }];
  const shifted = syncApplications({ revisao_extracao: review, abono: { lancamentos: [{ id: 'SECOND', valor: '400.00' }] } });
  expect((shifted.revisao_extracao as ExtractionReview).aplicacoes[0]).toMatchObject({ destino: ['abono', 'lancamentos', 0, 'valor'], valor_revisado: '400.00' });
  const removed = syncApplications({ revisao_extracao: review, abono: { lancamentos: [] } });
  expect((removed.revisao_extracao as ExtractionReview).aplicacoes).toEqual([]);
});

it('não invalida confirmações independentes quando apenas a confirmação global muda', () => {
  const review = mergeExtractions(undefined, [doc]);
  expect(onlyGlobalApprovalChanged({ revisao_extracao: review }, { revisao_extracao: { ...review, confirmado: true } }, ['revisao_extracao'])).toBe(true);
  expect(onlyGlobalApprovalChanged({ abono: { vinculo_id: 'V1', conferido_pelo_rh: false } }, { abono: { vinculo_id: 'V1', conferido_pelo_rh: true } }, ['abono'])).toBe(true);
  expect(onlyGlobalApprovalChanged({ abono: { vinculo_id: 'V1', conferido_pelo_rh: false } }, { abono: { vinculo_id: 'V2', conferido_pelo_rh: true } }, ['abono'])).toBe(false);
});

it('serializa evidências sem converter matrícula ou valor observado em float', () => {
  const review = mergeExtractions(undefined, [doc]);
  expect(serializeReviewData({ revisao_extracao: review })).toEqual({ revisao_extracao: review });
});

it('fim divergente exige escolha explícita e preserva os dois candidatos', () => {
  const field = { ...doc.campos[0], campo: 'periodo_ferias', valor: '10', estado: 'AMBIGUO' as const, inicio: '2026-01-01', fim: null, fim_informado: '2026-01-20', fim_calculado: '2026-01-10' };
  const data = { substituicao: emptySubstitutionPlan(), revisao_extracao: mergeExtractions(undefined, [{ ...doc, campos: [field] }]) };
  expect(() => appendVacation(data, doc, field, false)).toThrow(/escolha explicitamente/);
  expect(() => appendVacation(data, doc, field, false, '2026-02-01')).toThrow(/candidato observado/);
  const result = appendVacation(data, doc, field, false, '2026-01-20');
  expect(result.substituicao).toMatchObject({ impedimentos_substituto: [{ inicio: '2026-01-01', ultimo_dia_considerado: '2026-01-20', motivo: '' }] });
  expect(result.revisao_extracao).toMatchObject({ documentos: [{ campos: [{ fim_informado: '2026-01-20', fim_calculado: '2026-01-10', fim: null }] }] });
});

it('a nova versão do leitor não substitui silenciosamente fontes já revisadas', () => {
  const previous = mergeExtractions(undefined, [{ ...doc, versao_leitor: 'rh_paginas_v3' }]);
  const result = mergeExtractions(previous, [{ ...doc, id: 'NEW-READER', versao_leitor: 'rh_paginas_v4' }]);
  expect(result.documentos).toHaveLength(2);
  expect(result.documentos.map(source => source.versao_leitor)).toEqual(['rh_paginas_v3', 'rh_paginas_v4']);
});
