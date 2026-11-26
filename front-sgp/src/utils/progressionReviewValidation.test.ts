import { expect, it } from 'vitest';
import { apiErrorDetails } from './apiErrors';
import { missingProgressionInputs } from './progressionReviewValidation';

it('identifica os campos pendentes na revisão mensal e aceita zero de anuênio confirmado', () => {
  const entries = {
    progressao: { modalidade: 'DOCENTE', estado_inicial: { percentual_anuenio: '0' }, rubricas: [] },
    revisao_extracao: { documentos: [{ campos: [{ campo: 'rubrica', competencia: '2024-02' }] }], vinculo_calculo: '' },
  };
  const missing = missingProgressionInputs(entries);
  const paths = Object.keys(missing).map(key => JSON.parse(key).join('.'));
  expect(paths).toEqual(expect.arrayContaining(['matricula', 'progressao.estado_inicial.posicao',
    'progressao.eventos.0.alteracoes.posicao.classe_docente', 'progressao.eventos.0.alteracoes.posicao.nivel_docente',
    'progressao.estado_inicial.titulacao']));
  expect(paths).not.toContain('progressao.estado_inicial.percentual_anuenio');
  expect(missingProgressionInputs({ ...entries, progressao: { ...entries.progressao, modalidade: 'TAE' } })).toEqual({});
});

it('sinaliza um fim anterior ao início mesmo dentro da mesma competência', () => {
  const errors = missingProgressionInputs({ progressao: { modalidade: 'DOCENTE', periodo: { inicio: '2024-02-15', ultimo_dia_considerado: '2024-02-14' } } });
  expect(errors[JSON.stringify(['progressao', 'periodo', 'ultimo_dia_considerado'])]).toMatch(/posterior ao início/);
});

it('traduz exigências de lista e texto recebidas da API e conserva seus campos', () => {
  const { fields } = apiErrorDetails({ detail: [
    { loc: ['body', 'dados_extraidos', 'progressao', 'rubricas'], msg: 'List should have at least 1 item after validation, not 0', type: 'too_short' },
    { loc: ['body', 'revisao_extracao', 'vinculo_calculo'], msg: 'String should have at least 1 character', type: 'string_too_short' },
  ] }, '');
  expect(fields).toEqual({ '["progressao","rubricas"]': 'Inclua pelo menos um registro.',
    '["revisao_extracao","vinculo_calculo"]': 'Preencha este campo.' });
});
