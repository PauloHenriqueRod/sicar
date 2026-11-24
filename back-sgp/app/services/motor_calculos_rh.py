import calendar
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from app.schemas.referencias_salariais import ConsultaSalarial
from app.utils.conversor import ConversorSaneador

P = ParamSpec("P")
R = TypeVar("R")
Numero = Decimal | float


def _calculo_decimal(funcao: Callable[P, R]) -> Callable[P, R]:
    @wraps(funcao)
    def executar(*args: P.args, **kwargs: P.kwargs) -> R:
        # A precisão comporta os produtos dos limites do contrato da API sem
        # perder centavos. O contexto é local, sem modificar outras requisições.
        with localcontext() as contexto:
            contexto.prec = 64
            return funcao(*args, **kwargs)
    return executar


def _decimal(valor: Numero) -> Decimal:
    return Decimal(str(valor))


def _arredondar(valor: Decimal, casas: int = 2) -> Decimal:
    with localcontext() as contexto:
        contexto.prec = 64
        return valor.quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)


def _resultado_json(valor: Any) -> Any:
    """Finaliza valores monetários só na saída, nunca durante a acumulação."""
    if isinstance(valor, Decimal):
        return float(_arredondar(valor))
    if isinstance(valor, dict):
        return {chave: _resultado_json(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_resultado_json(item) for item in valor]
    return valor


class MotorCalculosRH:
    @staticmethod
    def calcular_avos_ferias(
        data_exercicio: date,
        data_rescisao: date,
        ocorrencias_adicional_ferias: int = 0,
    ) -> int:
        """Conta avos desde o dia anterior ao aniversário mensal do contrato.

        A fração final com 15 dias ou mais vale um avo. Cada ocorrência da
        rubrica 750/00750 de adicional de 1/3 já paga desconta 12 avos.
        O retorno pode ser negativo, representando valor a devolver.
        """
        if data_rescisao < data_exercicio:
            raise ValueError("A data de rescisão não pode ser anterior à entrada em exercício")

        meses = (data_rescisao.year - data_exercicio.year) * 12 + data_rescisao.month - data_exercicio.month
        aniversario = data_exercicio.replace(
            year=data_exercicio.year + (data_exercicio.month - 1 + meses) // 12,
            month=(data_exercicio.month - 1 + meses) % 12 + 1,
            day=min(
                data_exercicio.day,
                calendar.monthrange(
                    data_exercicio.year + (data_exercicio.month - 1 + meses) // 12,
                    (data_exercicio.month - 1 + meses) % 12 + 1,
                )[1],
            ),
        )
        if aniversario > data_rescisao:
            meses -= 1
            mes_indice = data_exercicio.month - 1 + meses
            ano_aniversario = data_exercicio.year + mes_indice // 12
            mes_aniversario = mes_indice % 12 + 1
            aniversario = data_exercicio.replace(
                year=ano_aniversario,
                month=mes_aniversario,
                day=min(data_exercicio.day, calendar.monthrange(ano_aniversario, mes_aniversario)[1]),
            )
        dias_fracao = (data_rescisao - aniversario).days + 1
        avos = meses + (1 if dias_fracao >= 15 else 0)
        return avos - (12 * ocorrencias_adicional_ferias)
    @staticmethod
    @_calculo_decimal
    def _obter_salario_tabela(classe: str, nivel: int, titulacao: str, ano: int = 2024, *, referencia: ConsultaSalarial | None = None) -> Decimal:
        """Argumentos anuais são metadados legados; somente a referência qualificada seleciona valores."""
        from app.database import SessionLocal
        from app.services.salary_references import resolve_salary

        with SessionLocal() as db:
            return resolve_salary(db, referencia, titulacao)[0]
    @staticmethod
    @_calculo_decimal
    def calcular_substituicao(
        salario_substituta: Numero,
        salario_propria: Numero,
        dias_substituidos: int,
        dias_interrupcao: int = 0,
        mes: int = 12,
        ano: int = 2024,
    ) -> dict[str, Any]:
        """Calcula substituição de função com dias reais do mês."""
        if any(not math.isfinite(valor) or valor < 0 for valor in (salario_substituta, salario_propria)):
            raise ValueError("Os valores das funções devem ser finitos e não negativos")
        if any(isinstance(dias, bool) or not isinstance(dias, int) for dias in (dias_substituidos, dias_interrupcao)):
            raise ValueError("Informe quantidades inteiras de dias")
        dias_totais_mes = ConversorSaneador.obter_dias_do_mes(mes, ano)
        if not 0 <= dias_interrupcao <= dias_substituidos <= dias_totais_mes:
            raise ValueError("Confira os dias da substituição e da interrupção no mês de referência")
        diferenca_bruta = _decimal(salario_substituta) - _decimal(salario_propria)
        dias_efetivos = max(0, dias_substituidos - dias_interrupcao)
        valor_proporcional = diferenca_bruta * dias_efetivos / dias_totais_mes

        return _resultado_json({
            "funcao_substituta_valor": salario_substituta,
            "funcao_propria_valor": salario_propria,
            "diferenca_mensal_cheia": diferenca_bruta,
            "dias_substituidos": dias_substituidos,
            "dias_interrupcao": dias_interrupcao,
            "dias_efetivos": dias_efetivos,
            "dias_totais_mes": dias_totais_mes,
            "valor_proporcional_devido": max(Decimal(0), valor_proporcional),
        })

    @staticmethod
    @_calculo_decimal
    def calcular_retroativo_insalubridade(
        valores_mensais: Mapping[str, Numero],
        multiplicadores_especiais: Mapping[str, Numero] | None = None,
    ) -> dict[str, Any]:
        # O contrato legado soma parcelas informadas. Nomes de competência não
        # comprovam férias/13º; novos reflexos usam eventos com avos explícitos.
        multiplicadores_especiais = multiplicadores_especiais or {}

        detalhamento = []
        total_geral = Decimal(0)

        for mes, base in valores_mensais.items():
            chave_busca = mes.upper().strip()
            mult: Numero = 1.0
            for k, m in multiplicadores_especiais.items():
                if k in chave_busca:
                    mult = m
                    break

            valor_calculado = _decimal(base) * _decimal(mult)
            total_geral += valor_calculado
            detalhamento.append(
                {
                    "mes": mes,
                    "valor_base": base,
                    "multiplicador": float(mult),
                    "valor_calculado": valor_calculado,
                }
            )

        return _resultado_json({
            "total_acumulado": total_geral,
            "detalhamento_mensal": detalhamento,
        })

    @staticmethod
    @_calculo_decimal
    def calcular_abono_permanencia(valores_anuais: Mapping[int, Sequence[Numero]]) -> dict[str, Any]:
        totais_por_ano = {}
        total_geral = Decimal(0)

        for ano, valores in valores_anuais.items():
            soma_ano = sum((_decimal(valor) for valor in valores), Decimal(0))
            totais_por_ano[ano] = soma_ano
            total_geral += soma_ano

        return _resultado_json({
            "total_geral": total_geral,
            "consolidado_anual": totais_por_ano,
        })

    @staticmethod
    @_calculo_decimal
    def calcular_rescisao_substituto(
        classe: str = "",
        nivel: int = 1,
        titulacao: str = "",
        meses_ferias_indenizadas: Numero = 0.0,
        meses_completos_13o: int = 0,
        dias_trabalhados_ultimo_mes: int = 0,
        valores_ja_recebidos: Mapping[str, Numero] | None = None,
        mes_rescisao: int = 12,
        ano_rescisao: int = 2024,
        salario_mensal: Numero | None = None,
        data_exercicio: date | None = None,
        data_rescisao: date | None = None,
        ocorrencias_adicional_ferias: int = 0,
        referencia_salarial: ConsultaSalarial | None = None,
    ) -> dict[str, Any]:
        """Calcula rescisão com dias reais do mês e busca de tabela."""
        dias_mes = calendar.monthrange(ano_rescisao, mes_rescisao)[1]
        if type(dias_trabalhados_ultimo_mes) is not int or not 0 <= dias_trabalhados_ultimo_mes <= dias_mes:
            raise ValueError("Confira os dias trabalhados no mês da rescisão.")
        if type(meses_completos_13o) is not int or not 0 <= meses_completos_13o <= 12:
            raise ValueError("Confira os avos de décimo terceiro.")
        if type(ocorrencias_adicional_ferias) is not int or ocorrencias_adicional_ferias < 0:
            raise ValueError("Confira as ocorrências de férias.")
        if valores_ja_recebidos is None:
            valores_ja_recebidos = {}
        if salario_mensal is None:
            salario_mensal = MotorCalculosRH._obter_salario_tabela(classe, nivel, titulacao, ano_rescisao, referencia=referencia_salarial)
        if data_exercicio and data_rescisao:
            meses_ferias_indenizadas = MotorCalculosRH.calcular_avos_ferias(
                data_exercicio, data_rescisao, ocorrencias_adicional_ferias
            )
        meses_ferias_validos = _decimal(meses_ferias_indenizadas)
        if meses_ferias_validos > 24:
            from app.services.pendencias import PendenciaApuracao
            raise PendenciaApuracao("limite_ferias_sem_regra", "Mais de 24 avos exige regra confirmada no contrato de rescisão por períodos; nenhum corte foi aplicado.")
        dias_mes = ConversorSaneador.obter_dias_do_mes(mes_rescisao, ano_rescisao)
        salario = _decimal(salario_mensal)
        recebidos = {rubrica: _decimal(valor) for rubrica, valor in valores_ja_recebidos.items()}
        salario_proporcional = salario * dias_trabalhados_ultimo_mes / dias_mes
        saldo_ferias = salario * meses_ferias_validos / 12
        # Quando a rubrica 750 antecipou mais avos do que o contrato adquiriu,
        # devolve-se somente o adicional de um terço excedente. O principal
        # indenizável nunca é negativo por causa dessas antecipações.
        ferias_indenizadas = max(Decimal(0), saldo_ferias)
        um_terco_ferias = salario * meses_ferias_validos / 36
        decimo_terceiro = salario * meses_completos_13o / 12

        calculos = {}
        for rubrica, devido in (
            ("742_salario", salario_proporcional), ("772_ferias", ferias_indenizadas),
            ("82696_terco_ferias", um_terco_ferias), ("82407_decimo_terceiro", decimo_terceiro),
        ):
            recebido = recebidos.get(rubrica, Decimal(0))
            calculos[rubrica] = {
                "devido": devido, "recebido": recebido,
                "diferenca": devido - recebido,
            }
        # Reunir as frações antes da divisão evita perder um empate exato
        # ao somar dízimas aproximadas (dias/mês, avos/12 e avos/36).
        numerador_devido = salario * (
            dias_trabalhados_ultimo_mes * 36
            + max(Decimal(0), meses_ferias_validos) * 3 * dias_mes
            + meses_ferias_validos * dias_mes
            + meses_completos_13o * 3 * dias_mes
        )
        total_recebido = sum((item["recebido"] for item in calculos.values()), Decimal(0))
        total_diferenca = (numerador_devido - total_recebido * 36 * dias_mes) / (36 * dias_mes)

        return _resultado_json({
            "salario_base_contrato": salario_mensal,
            "avos_ferias_devidos": float(meses_ferias_validos),
            "ocorrencias_adicional_ferias": ocorrencias_adicional_ferias,
            "detalhamento_rubricas": calculos,
            "total_liquido_a_receber": total_diferenca,
            "saldo_parcelas_calculadas": total_diferenca,
        })

    @staticmethod
    @_calculo_decimal
    def calcular_progressao_docente(
        classe_atual: str = "",
        nivel_atual: int = 1,
        titulacao: str = "",
        classe_antiga: str = "",
        nivel_antigo: int = 1,
        percentual_anuenio: Numero = 0.0,
        percentual_insalubridade: Numero = 0.0,
        percentual_incentivo: Numero = 0.0,
        percentual_incentivo_antigo: Numero | None = None,
        percentual_incentivo_novo: Numero | None = None,
        meses_diferenca: Numero = 0.0,
        aplica_proporcao_dias: bool = False,
        dias_proporcionais: int = 0,
        mes_proporcao: int = 12,
        ano_proporcao: int = 2024,
        salario_novo: Numero | None = None,
        salario_antigo: Numero | None = None,
        quantidade_reflexos_ferias: Numero = 1.0,
        quantidade_reflexos_13: Numero = 1.0,
        referencia_nova: ConsultaSalarial | None = None,
        referencia_antiga: ConsultaSalarial | None = None,
    ) -> dict[str, Any]:
        """Calcula progressão com dias reais do mês consultando a tabela salarial."""
        dias_mes = calendar.monthrange(ano_proporcao, mes_proporcao)[1]
        if type(dias_proporcionais) is not int or not 0 <= dias_proporcionais <= dias_mes:
            raise ValueError("Confira os dias proporcionais da progressão.")
        if not math.isfinite(meses_diferenca) or meses_diferenca < 0:
            raise ValueError("Confira o período da progressão.")
        if salario_novo is None:
            salario_novo = MotorCalculosRH._obter_salario_tabela(classe_atual, nivel_atual, titulacao, ano_proporcao, referencia=referencia_nova)
        if salario_antigo is None:
            salario_antigo = MotorCalculosRH._obter_salario_tabela(classe_antiga, nivel_antigo, titulacao, ano_proporcao, referencia=referencia_antiga)
        
        diff_base = _decimal(salario_novo) - _decimal(salario_antigo)
        diff_anuenio = diff_base * _decimal(percentual_anuenio) / 100
        diff_insalubridade = diff_base * _decimal(percentual_insalubridade) / 100
        incentivo_antigo = (
            percentual_incentivo
            if percentual_incentivo_antigo is None
            else percentual_incentivo_antigo
        )
        incentivo_novo = (
            percentual_incentivo
            if percentual_incentivo_novo is None
            else percentual_incentivo_novo
        )
        incentivo_antigo_bruto = (
            _decimal(salario_antigo) * _decimal(incentivo_antigo) / 100
        )
        incentivo_novo_bruto = (
            _decimal(salario_novo) * _decimal(incentivo_novo) / 100
        )
        diff_incentivo = incentivo_novo_bruto - incentivo_antigo_bruto
        total_mensal = diff_base + diff_incentivo + diff_anuenio + diff_insalubridade

        meses = _decimal(meses_diferenca)
        multiplicador_tempo = meses
        dias_rateio = 0
        if aplica_proporcao_dias and dias_proporcionais > 0:
            dias_mes = ConversorSaneador.obter_dias_do_mes(mes_proporcao, ano_proporcao)
            multiplicador_tempo += _decimal(dias_proporcionais) / dias_mes
            dias_rateio = dias_proporcionais

        # Uma divisão periódica no multiplicador pode ficar abaixo do empate
        # exato. O numerador único preserva o meio centavo até a quantização.
        total_acumulado = total_mensal * (meses * dias_mes + dias_rateio) / dias_mes
        reflexo_ferias = total_mensal * _decimal(quantidade_reflexos_ferias) / 3
        reflexo_decimo_terceiro = total_mensal * _decimal(quantidade_reflexos_13)
        total_com_reflexos = total_mensal * (
            meses * dias_mes * 3 + dias_rateio * 3
            + _decimal(quantidade_reflexos_ferias) * dias_mes
            + _decimal(quantidade_reflexos_13) * dias_mes * 3
        ) / (dias_mes * 3)

        return _resultado_json({
            "diferenca_base": diff_base,
            "incentivo_antigo": incentivo_antigo_bruto,
            "incentivo_novo": incentivo_novo_bruto,
            "diferenca_incentivo_qualificacao": diff_incentivo,
            "diferenca_anuenio": diff_anuenio,
            "diferenca_insalubridade": diff_insalubridade,
            "diferenca_mensal_total": total_mensal,
            "multiplicador_tempo": float(_arredondar(multiplicador_tempo, 4)),
            "total_geral_devido": total_acumulado,
            "reflexo_ferias": reflexo_ferias,
            "reflexo_decimo_terceiro": reflexo_decimo_terceiro,
            "total_com_reflexos": total_com_reflexos,
        })

    @staticmethod
    @_calculo_decimal
    def calcular_exercicio_anterior(fluxo_mensal: list[dict[str, Any]]) -> dict[str, Any]:
        total_devido = Decimal(0)
        total_recebido = Decimal(0)
        total_a_receber = Decimal(0)
        total_abono_ferias = Decimal(0)
        total_decimo_terceiro = Decimal(0)

        detalhamento = []

        for item in fluxo_mensal:
            valores = {}
            for campo in ("v_dev", "v_rec", "ab_ferias", "13_sal"):
                entrada = item.get(campo, 0)
                # A API fornece números. O leitor legado ainda pode fornecer
                # texto monetário brasileiro; números e Decimal não passam por float.
                if entrada is None or isinstance(entrada, str):
                    entrada = ConversorSaneador.para_decimal(entrada)
                valores[campo] = _decimal(entrada)
            devido, recebido = valores["v_dev"], valores["v_rec"]
            abono, decimo_terceiro = valores["ab_ferias"], valores["13_sal"]

            diferenca_mes = devido - recebido
            total_devido += devido
            total_recebido += recebido
            total_abono_ferias += abono
            total_decimo_terceiro += decimo_terceiro

            acumulado_mes = diferenca_mes + abono + decimo_terceiro
            total_a_receber += acumulado_mes

            detalhamento.append(
                {
                    "periodo": item.get("periodo", "N/A"),
                    "devido": devido,
                    "recebido": recebido,
                    "diferenca_salarial": diferenca_mes,
                    "abono_ferias": abono,
                    "decimo_terceiro": decimo_terceiro,
                    "total_mes": acumulado_mes,
                }
            )

        return _resultado_json({
            "resumo_consolidado": {
                "total_devido_base": total_devido,
                "total_recebido_base": total_recebido,
                "total_diferenca_salarial": total_devido - total_recebido,
                "total_abono_ferias": total_abono_ferias,
                "total_decimo_terceiro": total_decimo_terceiro,
                "total_geral_a_receber": total_a_receber,
            },
            "detalhamento_por_competencia": detalhamento,
        })
