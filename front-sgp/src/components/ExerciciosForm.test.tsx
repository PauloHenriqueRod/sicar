import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { expect, it } from 'vitest';
import { ExerciciosForm } from './ExerciciosForm';
import { emptyExerciciosPlan, emptyExercicioEntry, serializeExerciciosPlan } from '../utils/exerciciosReview';
import { prepareReviewData } from '../utils/reviewData';

function Harness({ initial = {} }: { initial?: Record<string, unknown> }) {
  const [value, setValue] = useState<Record<string, unknown>>({ ...emptyExerciciosPlan(), ...initial });
  return <><ExerciciosForm value={value} disabled={false} onChange={(_, value) => setValue(value as Record<string, unknown>)} /><output data-testid="payload">{JSON.stringify(value)}</output></>;
}
const payload = () => JSON.parse(screen.getByTestId('payload').textContent!);

it('inicia valores, pesquisa e revisão pendentes, sem juros ou reflexos presumidos', () => {
  render(<Harness initial={{ conferido_pelo_rh: true }} />);
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar parcelas identificadas' }));
  expect(screen.getByLabelText('Pesquisa de pagamentos anteriores')).toHaveValue('PENDENTE');
  expect(screen.getByLabelText('Estado de revisão')).toHaveValue('PENDENTE');
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar lançamentos devidos' }));
  expect(screen.getByLabelText('Valor confirmado do lançamento')).toHaveValue('');
  expect(screen.getByLabelText('Operação')).toHaveValue('');
  fireEvent.change(screen.getByLabelText('Valor confirmado do lançamento'), { target: { value: '1.234,005' } });
  expect(serializeExerciciosPlan(payload())).toMatchObject({ devidos: [{ valor: '1234.005', conferido: false }], conferido_pelo_rh: false, ajustes: [] });
});

it.each(['Identificador do lançamento', 'Valor confirmado do lançamento'])('preserva foco e identidade de linha ao editar %s e remover outra linha', label => {
  render(<Harness />);
  const add = screen.getByRole('button', { name: 'Adicionar lançamentos devidos' });
  fireEvent.click(add); fireEvent.click(add);
  const input = screen.getAllByLabelText(label)[1]; input.focus();
  fireEvent.change(input, { target: { value: '123' } });
  expect(screen.getAllByLabelText(label)[1]).toBe(input);
  expect(input).toHaveFocus();
  fireEvent.click(screen.getByRole('button', { name: 'Remover lançamentos devidos 1' }));
  expect(screen.getByLabelText(label)).toBe(input);
  expect(input).toHaveValue('123');
});

it('trocar operação retira conferência e elimina referências incompatíveis', () => {
  render(<Harness initial={{ devidos: [{ ...emptyExercicioEntry(), operacao: 'COMPLEMENTO', complementa_id: 'D', conferido: true }], conferido_pelo_rh: true }} />);
  fireEvent.change(screen.getByLabelText('Operação'), { target: { value: 'LANCAMENTO' } });
  expect(payload().devidos[0]).toMatchObject({ operacao: 'LANCAMENTO', conferido: false });
  expect(payload().devidos[0]).not.toHaveProperty('complementa_id');
  expect(payload().conferido_pelo_rh).toBe(false);
});

it('mantém via desconhecida e campos de documento distintos de folha', () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar pagamentos identificados' }));
  expect(screen.getByLabelText('Via do pagamento quando informada')).toHaveValue('NAO_INFORMADA');
  fireEvent.change(screen.getByLabelText('Origem do recebimento'), { target: { value: 'FOLHA' } });
  fireEvent.change(screen.getByLabelText('Identificador da folha'), { target: { value: 'F1' } });
  fireEvent.change(screen.getByLabelText('Origem do recebimento'), { target: { value: 'DOCUMENTO' } });
  expect(screen.queryByLabelText('Identificador da folha')).not.toBeInTheDocument();
  expect(payload().recebimentos[0]).not.toHaveProperty('identificador_folha');
  fireEvent.change(screen.getByLabelText('Via do pagamento quando informada'), { target: { value: 'JUDICIAL' } });
  fireEvent.change(screen.getByLabelText('Processo administrativo ou judicial (se informado)'), { target: { value: 'SINTETICO' } });
  expect(payload().recebimentos[0]).toMatchObject({ via_pagamento: 'JUDICIAL', processo: 'SINTETICO' });
});

it('aplica candidato somente com vínculo e alvo escolhidos, sem inferir direito ou operação', () => {
  render(<Harness initial={{ documentos: [{ id: 'DOC', nome_arquivo: 'sintetico.pdf', vinculo_identificado: 'V1', vinculo_confirmado: false, candidatos: [{ tipo: 'RECEBIMENTO', valor_observado: '-250.00', localizador: 'linha 1', competencia: '2026-01', rubrica: '12345', decisao: 'PENDENTE' }] }] }} />);
  const button = screen.getByRole('button', { name: 'Levar ao tipo de alvo escolhido, sem presumir direito ou operação' });
  expect(button).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Conferi a pessoa e o vínculo deste documento'));
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Tipo do alvo revisado'), { target: { value: 'RECEBIMENTO' } });
  fireEvent.click(button);
  const entry = within(screen.getByRole('group', { name: 'Pagamentos identificados 1' }));
  expect(entry.getByLabelText('Operação')).toHaveValue('');
  expect(entry.getByLabelText('Parcela vinculada')).toHaveValue('');
  expect(entry.getByLabelText('Valor confirmado do lançamento')).toHaveValue('250.00');
  expect(screen.getByLabelText('Confirmei correção justificada do sinal observado')).not.toBeChecked();
  fireEvent.change(entry.getByLabelText('Operação'), { target: { value: 'ESTORNO' } });
  fireEvent.click(button);
  expect(payload().recebimentos).toHaveLength(1);
  expect(entry.getByLabelText('Operação')).toHaveValue('ESTORNO');
  fireEvent.change(screen.getByLabelText('Vínculo identificado no documento'), { target: { value: 'V2' } });
  expect(button).toBeDisabled();
});

it('exige fundamento específico para ajustes e retira confirmação da regra após edição', () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar ajustes com regra específica' }));
  const confirm = screen.getByLabelText('Conferi a regra específica e sua vigência');
  fireEvent.click(confirm); expect(confirm).toBeChecked();
  fireEvent.change(screen.getByLabelText('Fonte da regra'), { target: { value: 'Nova fonte' } });
  expect(confirm).not.toBeChecked();
  expect(screen.getByLabelText('Valor conferido do ajuste')).toHaveValue('');
});

it('mantém identificação estável do ajuste e retira conferência ao alterar o evento', () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar ajustes com regra específica' }));
  const input = screen.getByLabelText('Identificação estável do evento de ajuste (se conhecida)');
  fireEvent.change(input, { target: { value: 'EVENTO-SINTETICO-1' } });
  expect(serializeExerciciosPlan(payload())).toMatchObject({ ajustes: [{ identificador_evento: 'EVENTO-SINTETICO-1' }] });
  const confirmed = screen.getByLabelText('Conferi este ajuste e seu fundamento específico');
  fireEvent.click(confirmed); expect(confirmed).toBeChecked();
  fireEvent.change(input, { target: { value: 'EVENTO-SINTETICO-2' } });
  expect(confirmed).not.toBeChecked();
  expect(payload().conferido_pelo_rh).toBe(false);
});

it('usa perfil novo manual e identifica compatibilidade agregada sem inventar fontes', () => {
  expect(prepareReviewData('exercicio_anterior', {})).toHaveProperty('exercicios');
  const legacy = prepareReviewData('exercicio_anterior', { fluxo_mensal: [{ periodo: '01/2020', v_dev: 100, v_rec: 0 }] });
  expect(legacy).not.toHaveProperty('exercicios');
  expect(String(legacy.alertas_extracao)).toMatch(/legado/i);
});
