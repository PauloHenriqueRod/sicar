import { afterEach, describe, it, expect, vi } from 'vitest';
import { prepareReviewData, serializeReviewData } from './reviewData';

describe('Referências salariais na revisão', () => {
  afterEach(() => vi.useRealTimers());
  it.each(['rescisao'] as const)('não presume titulação ou nível em %s', tipo => {
    const prepared = prepareReviewData(tipo, {});
    expect(prepared.rescisao).toMatchObject({ salarios: [], pagamentos_ferias: [], inicio_exercicio: '', conferido_pelo_rh: false });
    expect(prepared).not.toHaveProperty('nivel');
    expect(serializeReviewData(prepared)).not.toHaveProperty('titulacao');
    const observed = prepareReviewData(tipo, { titulacao: 'Mestrado', nivel: 2 });
    expect(observed.rescisao).not.toHaveProperty('base_ferias');
    expect(observed.alertas_extracao).toContainEqual(expect.stringContaining('Mestrado'));
  });
  it('usa o dia atual como fim sem presumir modalidade, posições ou efeitos pelos fatores legados', () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 10, 16, 23, 30));
    const prepared = prepareReviewData('progressao', { meses_diferenca: 12, classe_atual: 'Adjunto', nivel_atual: 2, quantidade_reflexos_13: 1 });
    expect(prepared.progressao).toMatchObject({ modalidade: '', periodo: { inicio: '', ultimo_dia_considerado: '2026-11-16' }, data_documento: '', data_implantacao: '', estado_inicial: { titulacao: '', posicao: { carreira: '' } }, eventos: [], reflexos: [], conferido_pelo_rh: false });
    expect(prepared).not.toHaveProperty('meses_diferenca');
    expect(prepared).not.toHaveProperty('nivel_atual');
    const candidate = prepareReviewData('progressao', { titulacao: 'Doutorado' });
    expect(candidate.progressao).toMatchObject({ estado_inicial: { titulacao: '' } });
    expect(candidate.alertas_extracao).toEqual([expect.stringContaining('Doutorado')]);
    vi.setSystemTime(new Date(2026, 10, 17, 0, 30));
    expect(prepareReviewData('progressao', {}).progressao).toMatchObject({ periodo: { ultimo_dia_considerado: '2026-11-17' } });
  });
  it.each(['2024-02-29', ''])('preserva o fim revisado da progressão, inclusive quando apagado: "%s"', lastDay => {
    const progression = { periodo: { inicio: '2024-02-15', ultimo_dia_considerado: lastDay }, conferido_pelo_rh: false };
    expect(prepareReviewData('progressao', { progressao: progression }).progressao).toEqual(progression);
  });
  it('preserva data e códigos e converte apenas a posição numérica', () => {
    expect(serializeReviewData({ salario_mensal: '', referencia_salarial: { carreira: 'TAE', vinculo: 'EFETIVO', jornada: '40H', versao_carreira: '2025', classificacao_tae: 'D', capacitacao_tae: '', padrao_tae: '2', data_referencia: '2026-04-01' } })).toEqual({ referencia_salarial: { carreira: 'TAE', vinculo: 'EFETIVO', jornada: '40H', versao_carreira: '2025', classificacao_tae: 'D', padrao_tae: 2, data_referencia: '2026-04-01' } });
  });
  it('omite consultas removidas sem inventar salário zero', () => {
    expect(serializeReviewData({ referencia_salarial: null, salario_mensal: '' })).toEqual({});
    expect(serializeReviewData({ salario_mensal: '0' })).toEqual({ salario_mensal: 0 });
  });
});
