from app.services.dados_pdf import extract_calculation_data
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.parametrize('tipo, campo', [('substituicao', 'ano'), ('progressao', 'ano_proporcao')])
@pytest.mark.parametrize('texto, esperado', [
    ('Ficha Financeira referente a: 2026 - 1º Semestre', 2026),
    ('Ficha Financeira referente a: 2023 - 1º Semestre\nFicha Financeira referente a: 2025 - 2º Semestre', None),
    ('Nome: Demonstração', None),
])
def test_periodo_so_e_preenchido_com_ano_inequivoco(auth_client_user, tipo, campo, texto, esperado):
    with patch('app.routers.calculos_router.extract_pdf_data') as abrir:
        pagina = MagicMock()
        pagina.extract_text.return_value = texto
        abrir.side_effect = lambda path, tipo: extract_calculation_data(pagina.extract_text.return_value, tipo)
        response = auth_client_user.post('/api/extrair-pdf', data={'tipo_calculo': tipo}, files={'arquivos': ('demo.pdf', b'%PDF-1.4\n', 'application/pdf')})
    assert response.status_code == 200
    dados = response.json()['resultados'][0]['dados_extraidos']
    assert dados[campo] == esperado
    assert dados['mes' if tipo == 'substituicao' else 'mes_proporcao'] is None


@pytest.mark.parametrize('tipo, campo, periodo', [
    ('substituicao', 'ano', 'Mês: 2\nAno: 2020'),
    ('progressao', 'ano_proporcao', 'Mês Proporcional: 2\nAno Proporcional: 2020'),
])
def test_periodo_explicito_prevalece_sobre_cabecalho(auth_client_user, tipo, campo, periodo):
    with patch('app.routers.calculos_router.extract_pdf_data') as abrir:
        pagina = MagicMock()
        pagina.extract_text.return_value = 'Ficha Financeira referente a: 2026\n' + periodo
        abrir.side_effect = lambda path, tipo: extract_calculation_data(pagina.extract_text.return_value, tipo)
        response = auth_client_user.post('/api/extrair-pdf', data={'tipo_calculo': tipo}, files={'arquivos': ('demo.pdf', b'%PDF-1.4\n', 'application/pdf')})
    dados = response.json()['resultados'][0]['dados_extraidos']
    assert dados[campo] == 2020
    assert dados['mes' if tipo == 'substituicao' else 'mes_proporcao'] == 2


def test_data_rescisao_fornece_periodo_sem_usar_ano_da_ficha(auth_client_user):
    with patch('app.routers.calculos_router.extract_pdf_data') as abrir:
        pagina = MagicMock()
        pagina.extract_text.return_value = 'Ficha Financeira referente a: 2024\nData de Rescisão: 31/08/2026'
        abrir.side_effect = lambda path, tipo: extract_calculation_data(pagina.extract_text.return_value, tipo)
        response = auth_client_user.post('/api/extrair-pdf', data={'tipo_calculo': 'rescisao'}, files={'arquivos': ('demo.pdf', b'%PDF-1.4\n', 'application/pdf')})
    dados = response.json()['resultados'][0]['dados_extraidos']
    assert dados['data_rescisao'] == '2026-08-31'
    assert dados['mes_rescisao'] == 8
    assert dados['ano_rescisao'] == 2026


@pytest.mark.parametrize('tipo, dados, campo, mensagem', [
    ('substituicao', {'mes': 2}, 'ano', None),
    ('substituicao', {'mes': 13, 'ano': 2026}, 'mes', None),
    ('substituicao', {'mes': 2, 'ano': ''}, 'ano', None),
    ('progressao', {}, 'ano_proporcao', None),
    ('progressao', {'dias_proporcionais': 10, 'ano_proporcao': 2026}, None, 'mês da proporção'),
    ('rescisao', {}, None, 'mês da rescisão'),
])
def test_calculo_exige_periodo_valido_em_vez_de_assumir_2024(auth_client_user, tipo, dados, campo, mensagem):
    response = auth_client_user.post('/api/calcular', json={'tipo_calculo': tipo, 'dados_extraidos': dados})
    assert response.status_code == 400
    erros = response.json()['detail']
    if campo:
        assert any(erro['loc'] == ['dados_extraidos', campo] for erro in erros)
    else:
        assert any(erro['loc'] == ['dados_extraidos'] and mensagem in erro['msg'] for erro in erros)
