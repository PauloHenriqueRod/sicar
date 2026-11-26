import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ProgressionFinancialReview } from './ProgressionFinancialReview';
import { emptyProgressionPlan, serializeProgressionPlan } from '../utils/periodReviewData';
import { RevisaoDadosForm } from './RevisaoDadosForm';
import type { ExtractionReview, Obj } from '../utils/documentExtraction';

function data(): Obj {
  return { progressao: { ...emptyProgressionPlan(), modalidade: 'DOCENTE' }, revisao_extracao: {
    documentos: [{ id: 'doc', nome_arquivo: 'sintetico.pdf', blocos: [{ id: 'b', nome: 'ALFA' }], campos: [
      ...[['vb', '00001', 'VENCIMENTO BASICO', '3000.00'], ['rt', '00826', 'RT - RETRIB POR TITULACAO', '1200.00'], ['13', '00100', '13 SALARIO', '4200.00']].map(([id, rubrica, descricao_rubrica, valor]) => ({ id, bloco_id: 'b', campo: 'rubrica', rubrica, descricao_rubrica, valor, competencia: '2026-01', natureza: 'R', sequencia: '0', estado: 'EXTRAIDO', pagina: 1, localizador: 'Página 1' })),
    ] }], associacoes: [], aplicacoes: [], confirmado: false,
  } };
}

describe('Conferência financeira da progressão', () => {
  it('mostra VB, RT e 13º por competência e usa a base apenas por ação explícita', () => {
    const change = vi.fn();
    render(<ProgressionFinancialReview data={data()} onChange={change} disabled={false} />);
    expect(screen.queryByText('3000.00')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Mês e ano da ficha financeira'), { target: { value: '2026-01' } });
    expect(screen.getByText(/R\$\s*3\.000,00/)).toBeVisible();
    expect(screen.getByText(/R\$\s*1\.200,00/)).toBeVisible();
    expect(screen.getByText(/13 SALARIO/)).toBeVisible();
    expect(change).not.toHaveBeenCalled();
    expect(screen.getByText('Usar como VB de origem')).not.toBeVisible();
    fireEvent.click(screen.getAllByText('Conferir e usar')[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Usar como VB de origem' }));
    const final = change.mock.calls[0][1];
    expect(final.progressao.estado_inicial.vb_manual).toMatchObject({ valor: '3000.00', fonte: 'sintetico.pdf' });
    expect(final.progressao.recebidos).toEqual([]);
    expect(final.revisao_extracao.aplicacoes[0]).toMatchObject({ documento_id: 'doc', campo_id: 'vb', destino: ['progressao', 'estado_inicial', 'vb_manual', 'valor'] });
    expect(final.revisao_extracao.confirmado).toBe(false);
  });

  it('preserva a base já editada, inclusive zero confirmado', () => {
    const edited = data();
    (edited.progressao as Obj).estado_inicial = { vb_manual: { valor: '0' } };
    render(<ProgressionFinancialReview data={edited} onChange={vi.fn()} disabled={false} />);
    fireEvent.change(screen.getByLabelText('Mês e ano da ficha financeira'), { target: { value: '2026-01' } });
    fireEvent.click(screen.getAllByText('Conferir e usar')[0]);
    expect(screen.getByRole('button', { name: 'Usar como VB de origem' })).toBeDisabled();
  });

  it('mantém preenchimento manual disponível sem anexos', () => {
    render(<ProgressionFinancialReview data={{ progressao: emptyProgressionPlan() }} onChange={vi.fn()} disabled={false} />);
    expect(screen.getByText(/Sem valores financeiros extraídos/)).toBeVisible();
  });
});

// A serialização continua exigindo confirmação explícita de anuênio.
it('não presume anuênio zero ao exibir a remuneração', () => {
  expect(() => serializeProgressionPlan(emptyProgressionPlan())).toThrow(/anuênio/);
});


it('preserva fonte e competência ao sugerir VB mensal sem confirmar integralidade', () => {
  const change = vi.fn();
  render(<ProgressionFinancialReview data={data()} onChange={change} disabled={false} />);
  fireEvent.change(screen.getByLabelText('Mês e ano da ficha financeira'), { target: { value: '2026-01' } });
  fireEvent.click(screen.getAllByText('Conferir e usar')[0]);
  fireEvent.click(screen.getByRole('button', { name: 'Usar VB nesta competência' }));
  const revised = change.mock.calls[0][1];
  expect(revised.progressao.bases_mensais_origem[0]).toMatchObject({ competencia: '2026-01', vb: { valor: '3000.00', fonte: 'sintetico.pdf' }, base_mensal_integral_confirmada: false });
  expect(revised.revisao_extracao.aplicacoes[0].destino).toEqual(['progressao', 'bases_mensais_origem', 0, 'vb', 'valor']);
  expect(revised.progressao.recebidos).toEqual([]);
});


it('prepara somente as competências do período sem presumir conferência', () => {
  const revised = data();
  (revised.progressao as Obj).periodo = { inicio: '2026-01-15', ultimo_dia_considerado: '2026-01-31' };
  const change = vi.fn();
  render(<ProgressionFinancialReview data={revised} onChange={change} disabled={false} />);
  fireEvent.click(screen.getByText('Preencher bases mensais com os valores desta ficha'));
  fireEvent.click(screen.getByRole('button', { name: 'Preparar VB por competência desta ficha' }));
  expect(change.mock.calls[0][1].progressao.bases_mensais_origem).toHaveLength(1);
  expect(change.mock.calls[0][1].progressao.bases_mensais_origem[0]).toMatchObject({ competencia: '2026-01', vb: { valor: '3000.00' }, base_mensal_integral_confirmada: false });
});

it('corrige uma ocorrência, preserva a fonte e atualiza o VB vinculado apenas no mês escolhido', () => {
  const start = data();
  const review = start.revisao_extracao as ExtractionReview;
  const doc = review.documentos[0];
  doc.campos.push({ ...doc.campos[0], id: 'vb-fev', competencia: '2026-02' });
  const change = vi.fn();
  const view = (d: Obj) => <ProgressionFinancialReview data={d} onChange={change} disabled={false} />;
  const { rerender } = render(view(start));
  fireEvent.change(screen.getByLabelText('Mês e ano da ficha financeira'), { target: { value: '2026-01' } });
  fireEvent.click(screen.getAllByText('Conferir e usar')[0]);
  fireEvent.click(screen.getByRole('button', { name: 'Usar VB nesta competência' }));
  rerender(view(change.mock.lastCall![1]));
  fireEvent.click(screen.getByLabelText('Editar valor de 00001 · 2026-01'));
  fireEvent.change(screen.getByLabelText(/Valor conferido em reais/), { target: { value: '0' } });
  fireEvent.click(screen.getByText('Salvar valor'));
  expect(screen.getByRole('alert')).toHaveTextContent('motivo');
  fireEvent.change(screen.getByLabelText('Motivo da correção'), { target: { value: 'Revisão da folha' } });
  fireEvent.click(screen.getByText('Salvar valor'));
  const saved = change.mock.lastCall![1];
  expect(saved.progressao.bases_mensais_origem[0]).toMatchObject({ competencia: '2026-01', vb: { valor: '0.00' }, base_mensal_integral_confirmada: false });
  expect(saved.revisao_extracao.documentos[0].campos[0]).toMatchObject({ valor: '3000.00', correcao: { valor: '0.00', justificativa: 'Revisão da folha' } });
  expect(saved.revisao_extracao.aplicacoes[0].valor_revisado).toBe('0.00');
  expect(saved.revisao_extracao.documentos[0].campos.at(-1).correcao).toBeUndefined();
  rerender(view(saved));
  fireEvent.change(screen.getByLabelText('Mês e ano da ficha financeira'), { target: { value: '2026-02' } });
  expect(screen.getByText(/3\.000,00/)).toBeVisible();
});

it('concentra a conferência nas rubricas mensais, no período e no 13º', () => {
  const entries = data();
  (entries.revisao_extracao as ExtractionReview).documentos[0].avisos = [];
  render(<RevisaoDadosForm data={{ dados_extraidos: entries, resultado_calculo: null }} isCalculated={false}
    isUploading={false} handleChangeData={vi.fn()} onCalculate={vi.fn()} />);
  expect(screen.getByLabelText('Mês e ano da ficha financeira')).toHaveValue('2026-01');
  expect(screen.getByLabelText('Início da apuração')).toBeVisible();
  expect(screen.getByLabelText('Último dia considerado (incluído)')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Incluir 13º salário' })).toBeVisible();
  expect(screen.queryByText('Pendências deste documento')).not.toBeInTheDocument();
  expect(screen.getByText('Posição de origem')).toBeVisible();
  expect(screen.queryByText('Incluir 1/3 de férias')).not.toBeInTheDocument();
  expect(screen.queryByText('Continuar para os dados do cálculo')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Percentual inicial de anuênio')).toBeVisible();
  expect(screen.getByLabelText('Percentual inicial de anuênio')).toHaveValue('');
  expect(screen.getByRole('button', { name: 'Confirmar e Calcular' })).toBeDisabled();
  expect(screen.queryByText('Posição, jornada e titulação')).toBeNull();
  expect(screen.queryByText(/Servidor e fontes documentais/)).toBeNull();
  expect(screen.getAllByLabelText('Percentual inicial de anuênio')).toHaveLength(1);
  expect(screen.getByLabelText('Mês e ano da ficha financeira')).toBeVisible();
});
