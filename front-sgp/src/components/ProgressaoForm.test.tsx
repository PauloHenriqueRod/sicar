import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PeriodApuracaoForm } from './PeriodApuracaoForm';
import { emptyProgressionPlan, serializeProgressionPlan } from '../utils/periodReviewData';

function Harness() {
  const [data, setData] = useState<Record<string, unknown>>(emptyProgressionPlan());
  return <><PeriodApuracaoForm value={data} disabled={false} progression onChange={(_, value) => setData(value as Record<string, unknown>)} /><output aria-label="Plano revisado">{JSON.stringify(data)}</output></>;
}

describe('Progressão por eventos', () => {
  it('permite correção individual com fonte e justificativa e retorno explícito à tabela', () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText('Modalidade da progressão'), { target: { value: 'DOCENTE' } });
    fireEvent.change(screen.getByLabelText('Percentual inicial de anuênio'), { target: { value: '0' } });
    fireEvent.click(screen.getByLabelText('Informar VB manualmente com fonte conferida'));
    fireEvent.change(screen.getByLabelText('Valor mensal conferido'), { target: { value: '3000,005' } });
    fireEvent.change(screen.getByLabelText('Fonte do valor mensal'), { target: { value: 'Memória sintética' } });
    fireEvent.change(screen.getByLabelText('Página, aba ou linha da tabela'), { target: { value: 'linha 1' } });
    fireEvent.change(screen.getByLabelText('Justificativa da correção individual'), { target: { value: 'Valor individual conferido' } });
    let plan = JSON.parse(screen.getByLabelText('Plano revisado').textContent!);
    expect(plan.estado_inicial.vb_manual).toMatchObject({ valor: '3000,005', justificativa: 'Valor individual conferido' });
    expect(serializeProgressionPlan(plan)).toMatchObject({ estado_inicial: { vb_manual: { valor: '3000.005', justificativa: 'Valor individual conferido' } } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar mudanças no período' }));
    const row = screen.getByRole('group', { name: 'Mudanças no período: registro 1' });
    fireEvent.change(within(row).getByLabelText('Tipo de mudança'), { target: { value: 'BASE' } });
    plan = JSON.parse(screen.getByLabelText('Plano revisado').textContent!);
    expect(plan.eventos[0].alteracoes).toEqual({});
    fireEvent.click(within(row).getByRole('button', { name: 'Retornar VB à tabela neste evento' }));
    plan = JSON.parse(screen.getByLabelText('Plano revisado').textContent!);
    expect(plan.eventos[0]).toMatchObject({ tipo: 'BASE', alteracoes: { vb_manual: null } });
    expect(plan.conferido_pelo_rh).toBe(false);
  });
  it('preserva vigência da interrupção e parcelas de reflexo com componentes e avos próprios', () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText('Modalidade da progressão'), { target: { value: 'DOCENTE' } });
    fireEvent.change(screen.getByLabelText('Percentual inicial de anuênio'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar interrupções' }));
    const interruption = screen.getByRole('group', { name: 'Interrupções: registro 1' });
    const fill = (scope: HTMLElement, label: string, value: string) => fireEvent.change(within(scope).getByLabelText(label), { target: { value } });
    fill(interruption, 'Primeiro dia da interrupção', '2024-02-21');
    fill(interruption, 'Último dia da interrupção (incluído)', '2024-02-22');
    fill(interruption, 'Início da vigência da regra', '2024-02-21');
    fill(interruption, 'Fim da vigência da regra (opcional)', '2024-02-22');
    for (const [index, component, avos] of [[1, 'Vencimento básico', '12'], [2, 'Retribuição por titulação', '6']] as const) {
      fireEvent.click(screen.getByRole('button', { name: 'Adicionar reflexos' }));
      const row = screen.getByRole('group', { name: `Reflexos: registro ${index}` });
      fill(row, 'Tipo de reflexo', 'DECIMO_TERCEIRO');
      fill(row, 'Data-base do reflexo', '2024-02-29');
      fill(row, 'Competência do reflexo', '2024-02');
      fill(row, 'Código da rubrica', '13');
      fill(row, 'Natureza da folha (conforme a fonte)', 'NORMAL');
      fill(row, 'Natureza da rubrica', 'R');
      fill(row, 'Avos do reflexo (1 a 12)', avos);
      fireEvent.click(within(row).getByLabelText(`${component} na base do reflexo`));
    }
    const payload = serializeProgressionPlan(JSON.parse(screen.getByLabelText('Plano revisado').textContent ?? '{}'));
    expect(payload).toMatchObject({
      interrupcoes: [{ inicio: '2024-02-21', ultimo_dia_considerado: '2024-02-22', regra: { inicio_vigencia: '2024-02-21', fim_vigencia: '2024-02-22' } }],
      reflexos: [{ avos: 12, formulas_base: ['VB'] }, { avos: 6, formulas_base: ['RT'] }],
    });
  });

  it.each(['TAE', 'DOCENTE'])('separa a progressão da mudança de IQ/RT em %s', modality => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText('Modalidade da progressão'), { target: { value: modality } });
    expect(screen.getByLabelText('Informar VB manualmente com fonte conferida')).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar mudanças no período' }));
    const progression = screen.getByRole('group', { name: 'Mudanças no período: registro 1' });
    fireEvent.change(within(progression).getByLabelText('Tipo de mudança'), { target: { value: 'PROGRESSAO' } });
    fireEvent.change(within(progression).getByLabelText('Início dos efeitos financeiros'), { target: { value: '2024-02-15' } });
    expect(within(progression).getByRole('group', { name: 'Posição de destino' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar mudanças no período' }));
    const qualification = screen.getByRole('group', { name: 'Mudanças no período: registro 2' });
    fireEvent.change(within(qualification).getByLabelText('Tipo de mudança'), { target: { value: modality === 'TAE' ? 'IQ' : 'RT' } });
    fireEvent.change(within(qualification).getByLabelText('Início dos efeitos financeiros'), { target: { value: '2024-02-20' } });
    if (modality === 'TAE') {
      fireEvent.change(within(qualification).getByLabelText('Novo percentual de IQ'), { target: { value: '20,5' } });
      fireEvent.change(within(qualification).getByLabelText('Nova escolaridade'), { target: { value: 'Especialização' } });
    } else {
      expect(within(qualification).queryByRole('option', { name: 'Mudança de IQ' })).not.toBeInTheDocument();
      fireEvent.change(within(qualification).getByLabelText('Nova titulação (RT)'), { target: { value: 'Doutorado' } });
    }
    const payload = JSON.parse(screen.getByLabelText('Plano revisado').textContent ?? '{}');
    expect(payload.eventos.map((event: { efeitos_financeiros: string }) => event.efeitos_financeiros)).toEqual(['2024-02-15', '2024-02-20']);
    expect(Object.keys(payload.eventos[0].alteracoes)).toEqual(['posicao']);
    expect(payload.eventos[1].alteracoes.titulacao).toBe(modality === 'TAE' ? 'Especialização' : 'Doutorado');
    const confirmation = screen.getByRole('checkbox', { name: /Conferi períodos/ });
    fireEvent.click(confirmation);
    fireEvent.change(within(qualification).getByLabelText('Início dos efeitos financeiros'), { target: { value: '2024-02-21' } });
    expect(confirmation).not.toBeChecked();
  });

  it('exige percentuais conferidos e preserva os avos inteiros dos reflexos', () => {
    const data = emptyProgressionPlan();
    expect(() => serializeProgressionPlan(data)).toThrow('percentual inicial de anuênio');
    const valid = { ...data, modalidade: 'TAE', estado_inicial: { ...data.estado_inicial, percentual_adicional: '0', percentual_anuenio: '0', percentual_iq: '10,5' }, reflexos: [{ avos: '12' }] };
    expect(serializeProgressionPlan(valid)).toMatchObject({ estado_inicial: { percentual_iq: '10.5' }, reflexos: [{ avos: 12 }] });
    expect(() => serializeProgressionPlan({ ...valid, reflexos: [{ avos: '1.5' }] })).toThrow('inteira de avos');
  });
});


it('expõe destino, data, 13º e férias sem anexos e preserva a origem', () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar novo enquadramento docente' }));
  const row = screen.getByRole('group', { name: 'Mudanças no período: registro 1' });
  fireEvent.change(within(row).getByLabelText('Início dos efeitos financeiros'), { target: { value: '2026-02-15' } });
  fireEvent.change(within(row).getByLabelText('Carreira'), { target: { value: 'MAGISTERIO_SUPERIOR' } });
  fireEvent.change(within(row).getByLabelText('Classe docente'), { target: { value: 'B' } });
  fireEvent.change(within(row).getByLabelText('Nível docente'), { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Incluir 13º salário' }));
  fireEvent.click(screen.getByRole('button', { name: 'Incluir 1/3 de férias' }));
  const plan = JSON.parse(screen.getByLabelText('Plano revisado').textContent!);
  expect(plan.modalidade).toBe('DOCENTE');
  expect(plan.eventos[0]).toMatchObject({ tipo: 'PROGRESSAO', efeitos_financeiros: '2026-02-15', alteracoes: { posicao: { classe_docente: 'B', nivel_docente: '2' } } });
  expect(plan.estado_inicial.posicao.classe_docente).toBeUndefined();
  expect(plan.reflexos.map((r: { tipo: string; avos: string }) => [r.tipo, r.avos])).toEqual([['DECIMO_TERCEIRO', ''], ['FERIAS_UM_TERCO', '']]);
});


it('edita VB por competência e invalida a confirmação ao corrigir o valor', () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar VB por competência manualmente' }));
  fireEvent.change(screen.getByLabelText('Competência da base mensal'), { target: { value: '2026-01' } });
  fireEvent.change(screen.getByLabelText('VB mensal integral conferido (R$)'), { target: { value: '3000,005' } });
  const confirmation = screen.getByLabelText('Confirmei que este valor representa a base mensal integral da competência.');
  fireEvent.click(confirmation);
  expect(confirmation).toBeChecked();
  fireEvent.change(screen.getByLabelText('VB mensal integral conferido (R$)'), { target: { value: '3100,005' } });
  expect(confirmation).not.toBeChecked();
  const plan = JSON.parse(screen.getByLabelText('Plano revisado').textContent!);
  expect(plan.bases_mensais_origem[0]).toMatchObject({ competencia: '2026-01', vb: { valor: '3100,005' }, base_mensal_integral_confirmada: false });
  expect(plan.conferido_pelo_rh).toBe(false);
});
