import { describe, expect, it } from 'vitest';
import { formatCalculationValue, formatHistoryTotal } from './presentation';

describe('Apresentação de totais históricos', () => {
  it('apresenta avos e referências de segmento como contadores', () => {
    expect(formatCalculationValue('avos', 12)).toBe(12);
    expect(formatCalculationValue('segmento_base', 3)).toBe(3);
    expect(formatCalculationValue('devido', '63.90')).toMatch(/R\$\s63,90/);
  });
  it('preserva zero como total válido e apresenta devoluções com sinal negativo', () => {
    expect(formatHistoryTotal(JSON.stringify({ total_liquido_a_receber: 0, total_geral: 1000 }))).toMatch(/R\$\s0,00/);
    expect(formatHistoryTotal(JSON.stringify({ total_geral_devido: -1234.56 }))).toMatch(/-R\$\s1\.234,56/);
  });

  it('inclui reflexos e aceita a estrutura aninhada retornada pela API', () => {
    expect(formatHistoryTotal(JSON.stringify({ total_geral_devido: 100, total_com_reflexos: 233.33 }))).toMatch(/R\$\s233,33/);
    expect(formatHistoryTotal(JSON.stringify({ resultado_calculo: { total_geral_devido: 100, total_com_reflexos: 0 } }))).toMatch(/R\$\s0,00/);
  });

  it('distingue um resultado sem total de um resultado ilegível e não exibe números inválidos', () => {
    expect(formatHistoryTotal('{}')).toBe('Não informado');
    expect(formatHistoryTotal('null')).toBe('Não informado');
    expect(formatHistoryTotal('{')).toBe('Não disponível');
    expect(formatHistoryTotal('{"total_geral":"1234.56"}')).toBe('Não informado');
    expect(formatHistoryTotal('{"total_geral":1e999}')).toBe('Não informado');
    expect(formatHistoryTotal('{"resumo_consolidado":{"total_geral_a_receber":1234.56}}')).toMatch(/R\$\s1\.234,56/);
  });

  it('preserva centavos dos novos totais decimais sem conversão para ponto flutuante', () => {
    expect(formatHistoryTotal(JSON.stringify({ tipo_apuracao: 'periodos_v1', total_geral_a_receber: '999999999999999.99' }))).toMatch(/R\$\s999\.999\.999\.999\.999,99/);
    expect(formatHistoryTotal(JSON.stringify({ tipo_apuracao: 'periodos_v1', total_geral_a_receber: '-0.01' }))).toMatch(/-R\$\s0,01/);
  });
});
