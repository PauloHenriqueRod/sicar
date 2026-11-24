from unittest.mock import patch

import pytest

from app.services.motor_calculos_rh import MotorCalculosRH
from app.utils.conversor import ConversorSaneador
from app.utils.crypto import decrypt_data, encrypt_data

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _mock_salario(valor: float):
    """Retorna um patch que faz _obter_salario_tabela devolver `valor`."""
    return patch.object(MotorCalculosRH, "_obter_salario_tabela", return_value=valor)


# ─────────────────────────────────────────────────────────────
# Motor de Cálculos — Substituição
# ─────────────────────────────────────────────────────────────

def test_calculo_substituicao():
    resultado = MotorCalculosRH.calcular_substituicao(
        salario_substituta=7374.97,
        salario_propria=4989.43,
        dias_substituidos=15,
        mes=10,  # Outubro tem 31 dias
        ano=2024,
    )
    assert resultado["diferenca_mensal_cheia"] == 2385.54
    assert resultado["dias_substituidos"] == 15
    assert resultado["dias_totais_mes"] == 31
    assert resultado["valor_proporcional_devido"] == 1154.29


def test_calculo_substituicao_zero_dias():
    resultado = MotorCalculosRH.calcular_substituicao(
        salario_substituta=5000.0,
        salario_propria=3000.0,
        dias_substituidos=0,
        mes=1,
        ano=2024,
    )
    assert resultado["valor_proporcional_devido"] == 0.0


def test_calculo_substituicao_salario_menor_retorna_zero():
    """Quando substituta ganha menos que a própria, resultado deve ser 0."""
    resultado = MotorCalculosRH.calcular_substituicao(
        salario_substituta=2000.0,
        salario_propria=5000.0,
        dias_substituidos=10,
        mes=3,
        ano=2024,
    )
    assert resultado["valor_proporcional_devido"] == 0.0


# ─────────────────────────────────────────────────────────────
# Motor de Cálculos — Insalubridade
# ─────────────────────────────────────────────────────────────

def test_calculo_retroativo_insalubridade():
    resultado = MotorCalculosRH.calcular_retroativo_insalubridade({
        "JANEIRO E FÉRIAS": 1000.0,
        "OUTUBRO": 1500.0,
        "NOVEMBRO E 13º": 1200.0,
    })
    assert resultado["total_acumulado"] == 3700.0
    assert len(resultado["detalhamento_mensal"]) == 3
    assert resultado["detalhamento_mensal"][0]["valor_calculado"] == 1000.0
    assert resultado["detalhamento_mensal"][1]["valor_calculado"] == 1500.0
    assert resultado["detalhamento_mensal"][2]["valor_calculado"] == 1200.0


def test_calculo_insalubridade_vazio():
    resultado = MotorCalculosRH.calcular_retroativo_insalubridade({})
    assert resultado["total_acumulado"] == 0.0
    assert resultado["detalhamento_mensal"] == []


def test_calculo_insalubridade_mes_sem_multiplicador():
    """Mês sem multiplicador especial deve usar mult=1.0."""
    resultado = MotorCalculosRH.calcular_retroativo_insalubridade({"MARÇO": 500.0})
    assert resultado["detalhamento_mensal"][0]["multiplicador"] == 1.0
    assert resultado["total_acumulado"] == 500.0


# ─────────────────────────────────────────────────────────────
# Motor de Cálculos — Abono Permanência
# ─────────────────────────────────────────────────────────────

def test_calculo_abono_permanencia():
    resultado = MotorCalculosRH.calcular_abono_permanencia({
        2022: [500.0, 600.0, 550.0],
        2023: [700.0, 750.0, 800.0],
    })
    assert resultado["total_geral"] == 3900.0
    assert resultado["consolidado_anual"][2022] == 1650.0
    assert resultado["consolidado_anual"][2023] == 2250.0


def test_calculo_abono_permanencia_vazio():
    resultado = MotorCalculosRH.calcular_abono_permanencia({})
    assert resultado["total_geral"] == 0.0
    assert resultado["consolidado_anual"] == {}


# ─────────────────────────────────────────────────────────────
# Motor de Cálculos — Exercício Anterior
# ─────────────────────────────────────────────────────────────

def test_calculo_exercicio_anterior():
    resultado = MotorCalculosRH.calcular_exercicio_anterior([
        {"periodo": "2023-01", "v_dev": 2000.0, "v_rec": 1500.0, "ab_ferias": 200.0, "13_sal": 0.0},
        {"periodo": "2023-02", "v_dev": 2100.0, "v_rec": 1600.0, "ab_ferias": 0.0, "13_sal": 300.0},
    ])
    consolidado = resultado["resumo_consolidado"]
    assert consolidado["total_devido_base"] == 4100.0
    assert consolidado["total_recebido_base"] == 3100.0
    assert consolidado["total_diferenca_salarial"] == 1000.0
    assert consolidado["total_abono_ferias"] == 200.0
    assert consolidado["total_decimo_terceiro"] == 300.0
    assert consolidado["total_geral_a_receber"] == 1500.0


def test_calculo_exercicio_anterior_vazio():
    resultado = MotorCalculosRH.calcular_exercicio_anterior([])
    assert resultado["resumo_consolidado"]["total_geral_a_receber"] == 0.0
    assert resultado["detalhamento_por_competencia"] == []


# ─────────────────────────────────────────────────────────────
# Motor de Cálculos — Rescisão (com mock de tabela salarial)
# ─────────────────────────────────────────────────────────────

def test_calculo_rescisao_substituto():
    with _mock_salario(5949.07):
        resultado = MotorCalculosRH.calcular_rescisao_substituto(
            classe="Auxiliar",
            nivel=1,
            titulacao="Mestrado",
            meses_ferias_indenizadas=24,
            meses_completos_13o=6,
            dias_trabalhados_ultimo_mes=18,
            valores_ja_recebidos={
                "742_salario": 0.0,
                "772_ferias": 4800.64,
                "82696_terco_ferias": 1600.21,
                "82407_decimo_terceiro": 300.04,
            },
            mes_rescisao=12,
            ano_rescisao=2024,
        )
    assert resultado["salario_base_contrato"] == 5949.07
    # Referência independente: 18/31 do salário, 24/12 de férias, 1/3
    # dessas férias e 6/12 de 13º, descontados os quatro pagamentos.
    # Política confirmada: 2.974,535 - 300,04 = 2.674,495, que deve
    # arredondar para 2.674,50 (meio centavo para cima).
    assert resultado["detalhamento_rubricas"] == {
        "742_salario": {"devido": 3454.30, "recebido": 0.0, "diferenca": 3454.30},
        "772_ferias": {"devido": 11898.14, "recebido": 4800.64, "diferenca": 7097.50},
        "82696_terco_ferias": {"devido": 3966.05, "recebido": 1600.21, "diferenca": 2365.84},
        "82407_decimo_terceiro": {"devido": 2974.54, "recebido": 300.04, "diferenca": 2674.50},
    }
    # O total usa as quatro parcelas exatas, sem somar diferenças já
    # arredondadas: 15.592,130913… -> 15.592,13.
    assert resultado["total_liquido_a_receber"] == 15592.13


# ─────────────────────────────────────────────────────────────
# Motor de Cálculos — Progressão Docente (com mock de tabela)
# ─────────────────────────────────────────────────────────────

def test_calculo_progressao_docente():
    with patch.object(
        MotorCalculosRH, "_obter_salario_tabela",
        side_effect=[8874.74, 7099.79]  # primeiro chamado: novo, segundo: antigo
    ):
        resultado = MotorCalculosRH.calcular_progressao_docente(
            classe_atual="Adjunto",
            nivel_atual=2,
            titulacao="Doutorado",
            classe_antiga="Adjunto",
            nivel_antigo=1,
            percentual_anuenio=21.0,
            percentual_insalubridade=10.0,
            meses_diferenca=11.0,
            aplica_proporcao_dias=True,
            dias_proporcionais=16,
            mes_proporcao=1,  # Janeiro tem 31 dias
            ano_proporcao=2024,
        )
    assert resultado["diferenca_base"] == 1774.95
    assert resultado["diferenca_anuenio"] == 372.74
    assert resultado["diferenca_insalubridade"] == 177.50
    assert resultado["diferenca_mensal_total"] == 2325.18
    assert resultado["multiplicador_tempo"] == 11.5161
    # Mensal exato: 1.774,95 × 1,31 = 2.325,1845. A versão exibida
    # (2.325,18) não alimenta principal ou reflexos.
    assert resultado["total_geral_devido"] == 26777.12
    assert resultado["reflexo_ferias"] == 775.06
    assert resultado["reflexo_decimo_terceiro"] == 2325.18
    assert resultado["total_com_reflexos"] == 29877.37


def test_calculo_progressao_sem_proporcao():
    with patch.object(
        MotorCalculosRH, "_obter_salario_tabela",
        side_effect=[6000.0, 5000.0]
    ):
        resultado = MotorCalculosRH.calcular_progressao_docente(
            classe_atual="Adjunto",
            nivel_atual=2,
            titulacao="Doutorado",
            classe_antiga="Adjunto",
            nivel_antigo=1,
            percentual_anuenio=0.0,
            percentual_insalubridade=0.0,
            meses_diferenca=6.0,
            aplica_proporcao_dias=False,
        )
    assert resultado["diferenca_base"] == 1000.0
    assert resultado["multiplicador_tempo"] == 6.0
    assert resultado["total_geral_devido"] == 6000.0


def test_progressao_tae_inclui_iq_anuenio_e_reflexos():
    resultado = MotorCalculosRH.calcular_progressao_docente(
        salario_antigo=3721.27,
        salario_novo=3870.12,
        percentual_anuenio=5,
        percentual_incentivo=10,
        meses_diferenca=1,
    )
    assert resultado["diferenca_base"] == 148.85
    assert resultado["diferenca_incentivo_qualificacao"] == 14.89
    assert resultado["diferenca_anuenio"] == 7.44
    assert resultado["diferenca_mensal_total"] == 171.18
    assert resultado["total_geral_devido"] == 171.18
    assert resultado["reflexo_ferias"] == 57.06
    assert resultado["reflexo_decimo_terceiro"] == 171.18
    # 148,85 × 1,15 × (1 + 1/3 + 1) = 399,414166…
    assert resultado["total_com_reflexos"] == 399.41


def test_progressao_tae_mudanca_percentual_iq():
    resultado = MotorCalculosRH.calcular_progressao_docente(
        salario_antigo=3721.27,
        salario_novo=3870.12,
        percentual_incentivo_antigo=10,
        percentual_incentivo_novo=25,
        meses_diferenca=1,
        quantidade_reflexos_ferias=0,
        quantidade_reflexos_13=0,
    )
    assert resultado["incentivo_antigo"] == 372.13
    assert resultado["incentivo_novo"] == 967.53
    assert resultado["diferenca_incentivo_qualificacao"] == 595.40
    assert resultado["total_geral_devido"] == 744.25


def test_progressao_tae_dias_usam_calendario_real():
    resultado = MotorCalculosRH.calcular_progressao_docente(
        salario_antigo=3686.33,
        salario_novo=3833.79,
        percentual_incentivo=30,
        meses_diferenca=0,
        aplica_proporcao_dias=True,
        dias_proporcionais=14,
        mes_proporcao=1,
        ano_proporcao=2026,
        quantidade_reflexos_ferias=0,
        quantidade_reflexos_13=0,
    )
    assert resultado["diferenca_mensal_total"] == 191.70
    assert resultado["multiplicador_tempo"] == 0.4516
    assert resultado["total_geral_devido"] == 86.57


@pytest.mark.parametrize("mes,ano,dias_mes,proporcional,devolucao", [
    (2, 2023, 28, 1660.71, -1439.29),
    (2, 2024, 29, 1603.45, -1496.55),
    (4, 2024, 30, 1550.00, -1550.00),
    (12, 2024, 31, 1500.00, -1600.00),
])
def test_calculos_proporcionais_preservam_centavos_e_dias_reais(mes, ano, dias_mes, proporcional, devolucao):
    # Referência: R$ 3.100 × 15/dias do mês. Na rescisão, a folha
    # já pagou R$ 3.100 e a diferença deve ser uma devolução.
    substituicao = MotorCalculosRH.calcular_substituicao(4100, 1000, 15, mes=mes, ano=ano)
    progressao = MotorCalculosRH.calcular_progressao_docente(
        salario_antigo=1000, salario_novo=4100, meses_diferenca=0,
        aplica_proporcao_dias=True, dias_proporcionais=15, mes_proporcao=mes, ano_proporcao=ano,
        quantidade_reflexos_ferias=0, quantidade_reflexos_13=0,
    )
    rescisao = MotorCalculosRH.calcular_rescisao_substituto(
        salario_mensal=3100, dias_trabalhados_ultimo_mes=15, mes_rescisao=mes, ano_rescisao=ano,
        valores_ja_recebidos={"742_salario": 3100},
    )
    assert substituicao["dias_totais_mes"] == dias_mes
    assert substituicao["valor_proporcional_devido"] == proporcional
    assert progressao["total_geral_devido"] == proporcional
    assert progressao["total_com_reflexos"] == proporcional
    assert rescisao["detalhamento_rubricas"]["742_salario"]["diferenca"] == devolucao
    assert rescisao["total_liquido_a_receber"] == devolucao


# ─────────────────────────────────────────────────────────────
# ConversorSaneador
# ─────────────────────────────────────────────────────────────

class TestConversorSaneador:

    def test_para_float_virgula_decimal(self):
        assert ConversorSaneador.para_float("1.234,56") == pytest.approx(1234.56)

    def test_para_float_ponto_decimal(self):
        assert ConversorSaneador.para_float("1234.56") == pytest.approx(1234.56)

    def test_para_float_com_rs(self):
        assert ConversorSaneador.para_float("R$ 500,00") == pytest.approx(500.0)

    def test_para_float_vazio_retorna_zero(self):
        assert ConversorSaneador.para_float("") == 0.0
        assert ConversorSaneador.para_float(None) == 0.0

    def test_para_float_zero_string(self):
        assert ConversorSaneador.para_float("0") == 0.0

    def test_para_float_invalido_retorna_zero(self):
        assert ConversorSaneador.para_float("abc") == 0.0

    def test_sanitizar_texto_escapa_html(self):
        assert ConversorSaneador.sanitizar_texto("<script>alert(1)</script>") == \
            "&lt;script&gt;alert(1)&lt;/script&gt;"

    def test_sanitizar_texto_vazio(self):
        assert ConversorSaneador.sanitizar_texto("") == ""
        assert ConversorSaneador.sanitizar_texto(None) == ""

    def test_sanitizar_texto_normal(self):
        assert ConversorSaneador.sanitizar_texto("  João Silva  ") == "João Silva"

    def test_obter_dias_do_mes_fevereiro_bissexto(self):
        assert ConversorSaneador.obter_dias_do_mes(2, 2024) == 29

    def test_obter_dias_do_mes_fevereiro_normal(self):
        assert ConversorSaneador.obter_dias_do_mes(2, 2023) == 28

    def test_obter_dias_do_mes_invalido_retorna_30(self):
        assert ConversorSaneador.obter_dias_do_mes(13, 2024) == 30

    def test_para_data_formato_br(self):
        from datetime import date
        assert ConversorSaneador.para_data("15/06/2024") == date(2024, 6, 15)

    def test_para_data_formato_iso(self):
        from datetime import date
        assert ConversorSaneador.para_data("2024-06-15") == date(2024, 6, 15)

    def test_para_data_invalida_retorna_none(self):
        assert ConversorSaneador.para_data("não é uma data") is None

    def test_para_data_vazia_retorna_none(self):
        assert ConversorSaneador.para_data("") is None


# ─────────────────────────────────────────────────────────────
# Criptografia (Fernet)
# ─────────────────────────────────────────────────────────────

class TestCrypto:

    def test_encrypt_decrypt_roundtrip(self):
        original = '{"salario": 5000.0, "classe": "Adjunto"}'
        token = encrypt_data(original)
        assert token != original
        assert decrypt_data(token) == original

    def test_encrypt_retorna_string(self):
        result = encrypt_data("teste")
        assert isinstance(result, str)

    def test_decrypt_dado_invalido_sinaliza_integridade(self):
        from app.utils.crypto import DataIntegrityError
        with pytest.raises(DataIntegrityError):
            decrypt_data("dado_invalido_corrompido")

    def test_encrypt_string_vazia(self):
        token = encrypt_data("")
        assert decrypt_data(token) == ""

    def test_encrypt_json_complexo(self):
        import json
        dados = {"lista": [1, 2, 3], "nested": {"key": "value"}}
        token = encrypt_data(json.dumps(dados))
        recovered = json.loads(decrypt_data(token))
        assert recovered == dados
