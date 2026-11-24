"""Designação e exercício são declarações conferidas pelo RH, nunca presumidas."""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.apuracao_periodos import (
    ChaveFolha,
    ContratoPeriodo,
    Identificador,
    IntervaloApuracao,
    ParcelaRecebida,
    Percentual,
    ValorManual,
    VigenciaRegra,
)
from app.schemas.fontes_oficiais import effect_date
from app.utils.salary_keys import salary_key


def confirmacao_explicita(value):
    if value is not True:
        raise ValueError(
            "Confirme a opção, os componentes, os percentuais e os dados conforme a regra conferida pelo RH."
        )
    return value


class PeriodoFonte(IntervaloApuracao):
    id: Identificador
    motivo: str = Field(min_length=1, max_length=200)
    origem: str = Field(min_length=1, max_length=300)
    localizador: str = Field(min_length=1, max_length=200)


class ComponenteFuncao(ContratoPeriodo):
    componente: str = Field(min_length=1, max_length=60)
    percentual_utilizado: Percentual
    origem: Literal["TABELA", "MANUAL"]
    valor_manual: ValorManual | None = None
    inicio_vigencia: date | None = None
    fim_vigencia: date | None = None
    _dates = field_validator("inicio_vigencia", "fim_vigencia", mode="before")(
        effect_date
    )

    @model_validator(mode="after")
    def fonte(self):
        if self.origem == "MANUAL" and (
            self.valor_manual is None or self.inicio_vigencia is None
        ):
            raise ValueError(
                "Valor manual exige fonte, localizador e início de vigência explícitos."
            )
        if self.origem == "TABELA" and (
            self.valor_manual is not None
            or self.inicio_vigencia is not None
            or self.fim_vigencia is not None
        ):
            raise ValueError(
                "Componente de tabela usa a vigência do cadastro, sem misturar valor manual."
            )
        if self.fim_vigencia is not None and (
            self.inicio_vigencia is None or self.fim_vigencia < self.inicio_vigencia
        ):
            raise ValueError("Confira a vigência do componente manual.")
        return self


class ComposicaoFuncao(ContratoPeriodo):
    tipo_funcao: Literal["CD", "FG", "FCC"]
    codigo_funcao: str = Field(min_length=1, max_length=30)
    modalidade: str = Field(min_length=1, max_length=60)
    componentes: list[ComponenteFuncao] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def componentes_distintos(self):
        keys = [salary_key(item.componente) for item in self.componentes]
        if any(not key for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("Identifique cada componente da função uma única vez.")
        if "total" in keys and len(keys) > 1:
            raise ValueError("Não some o TOTAL aos componentes que já o compõem.")
        if not salary_key(self.codigo_funcao) or not salary_key(self.modalidade):
            raise ValueError(
                "Código e modalidade da função precisam de identificação válida."
            )
        return self


class FuncaoPropria(ContratoPeriodo):
    situacao: Literal["SEM_FUNCAO_CONFIRMADA", "COM_FUNCAO"]
    funcao: ComposicaoFuncao | None = None

    @model_validator(mode="after")
    def presenca(self):
        if (self.situacao == "COM_FUNCAO") != (self.funcao is not None):
            raise ValueError(
                "Confirme a ausência de função própria ou informe sua composição completa."
            )
        return self


class OpcaoRemuneratoria(VigenciaRegra):
    # Operações aritméticas explícitas; não representam concessão automática de uma opção legal.
    calculo: Literal["DIFERENCA_FUNCOES", "BASE_SUBSTITUIDA"]
    diferenca_negativa: Literal["ZERAR", "PERMITIR"]
    confirmada: Literal[True]
    _confirm = field_validator("confirmada", mode="before")(confirmacao_explicita)


class EstadoSubstituicao(ContratoPeriodo):
    substituida: ComposicaoFuncao
    propria: FuncaoPropria
    opcao: OpcaoRemuneratoria


class EventoSubstituicao(ContratoPeriodo):
    id: Identificador
    efeitos_financeiros: date
    data_documento: date | None = None
    data_implantacao: date | None = None
    origem: str = Field(min_length=1, max_length=300)
    estado: EstadoSubstituicao
    _dates = field_validator(
        "efeitos_financeiros", "data_documento", "data_implantacao", mode="before"
    )(effect_date)


class CandidatoSubstituicao(ContratoPeriodo):
    campo: Literal["DESIGNACAO", "AFASTAMENTO_TITULAR", "IMPEDIMENTO_SUBSTITUTO"]
    inicio: date
    ultimo_dia_considerado: date
    localizador: str = Field(min_length=1, max_length=200)
    _dates = field_validator("inicio", "ultimo_dia_considerado", mode="before")(
        effect_date
    )


class PagamentoObservado(ContratoPeriodo):
    competencia: str | None = Field(
        default=None, pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$"
    )
    rubrica: Literal["83185"]
    natureza_rubrica: Literal["R", "D"] | None = None
    sequencia: str = Field(min_length=1, max_length=100)
    valor_observado: str | None = Field(
        default=None, max_length=60, pattern=r"^-?[0-9]+(?:\.[0-9]+)?$"
    )
    localizador: str = Field(min_length=1, max_length=200)


class DocumentoSubstituicao(ContratoPeriodo):
    id: Identificador
    nome_arquivo: str = Field(min_length=1, max_length=200)
    nome_identificado: str | None = Field(default=None, max_length=300)
    papel: (
        Literal[
            "DESIGNACAO",
            "AFASTAMENTO_TITULAR",
            "IMPEDIMENTO_SUBSTITUTO",
            "FICHA_FINANCEIRA",
            "OPCAO",
            "OUTRO",
        ]
        | None
    ) = None
    pessoa: Literal["TITULAR", "SUBSTITUTO", "NAO_SE_APLICA"] | None = None
    matricula_identificada: str | None = Field(
        default=None, min_length=1, max_length=100
    )
    candidatos: list[CandidatoSubstituicao] = Field(
        default_factory=list, max_length=100
    )
    pagamentos_observados: list[PagamentoObservado] = Field(
        default_factory=list, max_length=200
    )


class PlanoSubstituicao(ContratoPeriodo):
    periodo: IntervaloApuracao
    designacao: PeriodoFonte
    titular_matricula: str = Field(min_length=1, max_length=100)
    afastamentos_titular: list[PeriodoFonte] = Field(min_length=1, max_length=100)
    impedimentos_substituto: list[PeriodoFonte] = Field(max_length=100)
    estado_inicial: EstadoSubstituicao
    eventos: list[EventoSubstituicao] = Field(default_factory=list, max_length=100)
    rubrica: ChaveFolha
    recebidos: list[ParcelaRecebida] = Field(max_length=2000)
    documentos: list[DocumentoSubstituicao] = Field(default_factory=list, max_length=10)
    data_documento: date | None = None
    data_implantacao: date | None = None
    conferido_pelo_rh: Literal[True]
    _dates = field_validator("data_documento", "data_implantacao", mode="before")(
        effect_date
    )
    _confirm = field_validator("conferido_pelo_rh", mode="before")(
        confirmacao_explicita
    )

    @model_validator(mode="after")
    def consistencia(self):
        start, end = self.periodo.inicio, self.periodo.ultimo_dia_considerado
        if (end.year - start.year) * 12 + end.month - start.month >= 600:
            raise ValueError("Divida apurações com mais de 600 competências.")
        for rows in (
            self.afastamentos_titular,
            self.impedimentos_substituto,
            self.eventos,
            self.documentos,
        ):
            ids = [row.id for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError("Identificadores repetidos no mesmo grupo.")
        dates = [event.efeitos_financeiros for event in self.eventos]
        if len(dates) != len(set(dates)) or any(
            not start <= when <= end for when in dates
        ):
            raise ValueError(
                "Mudanças de função/opção devem ter datas distintas dentro da apuração."
            )
        for payment in self.recebidos:
            if (
                not f"{start.year:04}-{start.month:02}"
                <= payment.competencia
                <= f"{end.year:04}-{end.month:02}"
            ):
                raise ValueError("Recebimento fora das competências da apuração.")
            if (payment.rubrica, payment.natureza_rubrica) != (
                self.rubrica.rubrica,
                self.rubrica.natureza_rubrica,
            ):
                raise ValueError(
                    "Recebimento deve identificar a rubrica e natureza da rubrica desta substituição."
                )
        return self
