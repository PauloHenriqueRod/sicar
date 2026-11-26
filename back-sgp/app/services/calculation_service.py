"""Executa somente contratos validados e registra os parâmetros efetivamente usados."""

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.calculos import (
    AbonoDados,
    AbonoParcelasDados,
    AdicionaisDados,
    ApuracaoPeriodosDados,
    DadosIdentificados,
    ExercicioAnteriorDados,
    ExerciciosParcelasDados,
    InsalubridadeDados,
    ProgressaoDados,
    ProgressaoEventosDados,
    RescisaoDados,
    RescisaoPeriodosDados,
    SubstituicaoDados,
    SubstituicaoPeriodosDados,
    entradas_calculo,
)
from app.services.abono_parcelas import calcular_abono_parcelas
from app.services.adicionais import calcular_adicionais
from app.services.apuracao_periodos import apurar_periodos
from app.services.exercicios_parcelas import apurar_exercicios
from app.services.motor_calculos_rh import MotorCalculosRH
from app.services.progressao_eventos import calcular_progressao_eventos
from app.services.rescisao_periodos import calcular_rescisao_periodos
from app.services.salary_references import resolve_salary
from app.services.substituicao_periodos import calcular_substituicao_periodos
from app.utils.conversor import ConversorSaneador

ENGINE_VERSION = "2026-11-26.2"
ROUNDING_POLICY = "decimal_half_up_final_v3"
ROUNDING_NOTE = (
    "Valores monetários são apresentados com duas casas decimais e meio centavo para cima. "
    "O total utiliza a precisão interna das parcelas, antes do arredondamento; "
    "a soma dos valores exibidos pode diferir do total."
)


def execute_calculation(
    data: DadosIdentificados, db: Session
) -> tuple[dict[str, Any], dict[str, Any]]:
    from app.services.revisao_extracao import validar_revisao_extracao
    validar_revisao_extracao(data)
    trace: dict[str, Any] = {
        "versao_motor": ENGINE_VERSION,
        "calendario": "dias_reais_do_mes",
        "arredondamento": ROUNDING_POLICY,
        "precisao_decimal": 64,
        "entradas_decimais": entradas_calculo(data, mode="json"),
        "referencias_salariais": {},
    }
    if isinstance(
        data, (ApuracaoPeriodosDados, ProgressaoEventosDados, AdicionaisDados)
    ):
        result = (
            calcular_adicionais(data.adicionais, db)
            if isinstance(data, AdicionaisDados)
            else apurar_periodos(data.apuracao, db)
            if isinstance(data, ApuracaoPeriodosDados)
            else calcular_progressao_eventos(data.progressao, db)
        )
        trace.pop("precisao_decimal")
        trace["aritmetica_periodos"] = "racional_exata"
        trace["versao_apuracao"] = result["tipo_apuracao"]
        if isinstance(data, ProgressaoEventosDados):
            trace["versao_progressao"] = "eventos_v1"
    elif isinstance(data, SubstituicaoPeriodosDados):
        result = calcular_substituicao_periodos(data.substituicao, db)
        trace.pop("precisao_decimal")
        trace["aritmetica_periodos"] = "racional_exata"
        trace["versao_substituicao"] = "periodos_v1"
    elif isinstance(data, SubstituicaoDados):
        result = MotorCalculosRH.calcular_substituicao(
            data.salario_substituta,
            data.salario_propria,
            data.dias_substituidos,
            data.dias_interrupcao,
            data.mes,
            data.ano,
        )
    elif isinstance(data, InsalubridadeDados):
        result = MotorCalculosRH.calcular_retroativo_insalubridade(data.valores_mensais)
    elif isinstance(data, AbonoParcelasDados):
        result = calcular_abono_parcelas(data.abono)
        trace.pop("precisao_decimal")
        trace["aritmetica_periodos"] = "racional_exata"
        trace["versao_abono"] = "parcelas_v1"
    elif isinstance(data, AbonoDados):
        result = MotorCalculosRH.calcular_abono_permanencia(
            {int(k): v for k, v in data.valores_anuais.items()}
        )
        result["tipo_abono"] = "resumo_legado_v1"
        result["nota_escopo"] = "Soma de valores anuais informados, sem identificação de parcelas, direito ou pagamentos anteriores. Não representa o encontro de contas do novo contrato."
    elif isinstance(data, RescisaoPeriodosDados):
        result = calcular_rescisao_periodos(data.rescisao, db)
        trace.pop("precisao_decimal")
        trace["aritmetica_periodos"] = "racional_exata"
        trace["versao_rescisao"] = "periodos_v1"
    elif isinstance(data, RescisaoDados):
        assert data.ano_rescisao is not None and data.mes_rescisao is not None
        if data.salario_mensal is None:
            salario, source = resolve_salary(
                db, data.referencia_salarial, data.titulacao
            )
        else:
            salario = data.salario_mensal
            source = {
                "origem": "revisao",
                "valor_utilizado": float(salario),
                "valor_decimal": str(salario),
            }
        trace["referencias_salariais"]["salario_contrato"] = source
        result = MotorCalculosRH.calcular_rescisao_substituto(
            titulacao=data.titulacao,
            meses_ferias_indenizadas=data.meses_ferias,
            meses_completos_13o=data.meses_13,
            dias_trabalhados_ultimo_mes=data.dias_trabalhados,
            valores_ja_recebidos=data.valores_recebidos,
            mes_rescisao=data.mes_rescisao,
            ano_rescisao=data.ano_rescisao,
            salario_mensal=salario,
            data_exercicio=ConversorSaneador.para_data(data.data_exercicio),
            data_rescisao=ConversorSaneador.para_data(data.data_rescisao),
            ocorrencias_adicional_ferias=data.ocorrencias_adicional_ferias,
        )
    elif isinstance(data, ProgressaoDados):
        salarios: dict[str, Decimal] = {}
        for name, informado, consulta in (
            ("salario_antigo", data.salario_antigo, data.referencia_antiga),
            ("salario_novo", data.salario_novo, data.referencia_nova),
        ):
            if informado is None:
                valor, source = resolve_salary(db, consulta, data.titulacao)
            else:
                valor = Decimal(str(informado))
                source = {
                    "origem": "revisao",
                    "valor_utilizado": float(valor),
                    "valor_decimal": str(valor),
                }
            salarios[name] = valor
            trace["referencias_salariais"][name] = source
        result = MotorCalculosRH.calcular_progressao_docente(
            titulacao=data.titulacao,
            percentual_anuenio=data.anuenio,
            percentual_insalubridade=data.insalubridade,
            percentual_incentivo=data.incentivo,
            percentual_incentivo_antigo=data.incentivo_antigo,
            percentual_incentivo_novo=data.incentivo_novo,
            meses_diferenca=data.meses_diferenca,
            aplica_proporcao_dias=data.dias_proporcionais > 0,
            dias_proporcionais=data.dias_proporcionais,
            mes_proporcao=data.mes_proporcao or 1,
            ano_proporcao=data.ano_proporcao,
            quantidade_reflexos_ferias=data.quantidade_reflexos_ferias,
            quantidade_reflexos_13=data.quantidade_reflexos_13,
            salario_antigo=salarios["salario_antigo"],
            salario_novo=salarios["salario_novo"],
        )
    elif isinstance(data, ExerciciosParcelasDados):
        result = apurar_exercicios(data.exercicios)
        trace.pop("precisao_decimal")
        trace["aritmetica_periodos"] = "racional_exata"
        trace["versao_exercicios"] = "parcelas_v1"
    elif isinstance(data, ExercicioAnteriorDados):
        result = MotorCalculosRH.calcular_exercicio_anterior(
            [item.model_dump(by_alias=True) for item in data.fluxo_mensal]
        )
        result["tipo_exercicio"] = "resumo_legado_v1"
        result["nota_escopo"] = "Resumo agregado legado, sem rubricas ou origem do direito. Não comprova pesquisa de pagamentos nem revisão do novo contrato."
    else:
        raise TypeError("Tipo de cálculo desconhecido")
    result["politica_arredondamento"] = ROUNDING_POLICY
    result["nota_arredondamento"] = ROUNDING_NOTE
    return result, trace
