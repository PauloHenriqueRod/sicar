import { expect, it } from 'vitest';
import { missingPayroll, payrollMonths, payrollPayload } from './docentePayroll';
import type { ExtractedField, ExtractionReview } from './documentExtraction';

const period = { inicio: '2024-02-15', ultimo_dia_considerado: '2024-03-31' };
const entries = { progressao: { periodo: period } };
const field = (rubrica: string, valor: string): ExtractedField => ({
  campo: 'rubrica', id: rubrica, bloco_id: 'b', rubrica, competencia: '2024-02',
  pagina: 1, localizador: 'linha da folha', estado: 'EXTRAIDO', natureza: 'R', sequencia: '0', valor,
});
function review(campos: ExtractedField[]): ExtractionReview {
  return {
    documentos: [{ id: 'd', nome_arquivo: 'sintetica.pdf', layout: 'FICHA_SIAPE', versao_leitor: 'rh_paginas_v5',
      situacao: 'CONCLUIDO', total_paginas: 1, campos, avisos: [], blocos: [{ id: 'b', categoria: 'DOCENTE', paginas: [1] }] }],
    associacoes: [{ documento_id: 'd', bloco_id: 'b', matricula: '1', vinculo: 'Efetivo', pessoa: 'SERVIDOR', confirmado: true, justificativa: '' }],
    aplicacoes: [], vinculo_calculo: 'Efetivo', vinculo_titular: '', confirmado: true,
  };
}

it('separa zero pago, rubrica ausente e mês sem cobertura', () => {
  const months = payrollMonths(entries, review([field('00001', '3000.00'), field('82606', '0.00')]));
  expect(months[0].rt.value.valor).toBe('0.00');
  expect(months[1].rt.value.valor).toBe('');
  expect(missingPayroll(months)).toContain('2024-03 (VB/RT)');
  expect(missingPayroll([months[0]])).toBe('');
  const { rows, applications } = payrollPayload([months[0]], false);
  expect(rows[0].base_mensal_integral_confirmada).toBe(false);
  expect(applications.map(a => [a.campo_id, a.destino.slice(-2)])).toEqual([['00001', ['vb', 'valor']], ['82606', ['rt', 'valor']]]);
});

it('exige revisão de ocorrências concorrentes e descarta descontos, outro vínculo e 13º', () => {
  const sources = review([field('00001', '2000.00'), { ...field('00001', '300.00'), id: 'complemento', sequencia: '1' },
    { ...field('82606', '50.00'), natureza: 'D' }, { ...field('00100', '1000.00'), descricao_rubrica: 'RT - 13º' }]);
  const [february] = payrollMonths(entries, sources);
  expect([february.vb.value.valor, february.rt.value.valor]).toEqual(['', '']);
  const discarded = review([field('00001', '3000.00')]);
  discarded.associacoes[0].pessoa = 'DESCARTADO';
  expect(payrollMonths(entries, discarded)[0].vb.value.valor).toBe('');
});

it('preserva a edição mensal e a origem observada ao reabrir o cálculo', () => {
  const sources = review([field('00001', '3000.00'), field('82606', '100.00')]);
  const manual = { valor: '3250.00', fonte: 'Memória complementar', localizador: 'fevereiro', justificativa: 'Base integral conferida' };
  const draft = { ...manual, documento_id: 'd', campo_id: '00001' };
  const months = payrollMonths({ ...entries, edicoes_folha_docente: { '2024-02': { vb: draft } } }, sources);
  const saved = payrollPayload([months[0]], true);
  const reopened = payrollMonths({ progressao: { periodo: period, bases_mensais_origem: saved.rows } }, { ...sources, aplicacoes: saved.applications });
  expect(reopened[0].vb.value).toEqual(manual);
  expect(reopened[0].vb.candidate?.field.valor).toBe('3000.00');
  const manualOnly = payrollMonths({ progressao: { periodo: period, bases_mensais_origem: saved.rows } }, sources);
  expect(manualOnly[0].vb.value).toEqual(manual);
  expect(payrollPayload([manualOnly[0]], true).applications).toEqual([]);
  const newDocument = payrollMonths({ ...entries, edicoes_folha_docente: { '2024-02': { vb: manual } } }, sources);
  expect(newDocument[0].vb.candidate).toBeUndefined();
});
