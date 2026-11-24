"""Desconto, direito e pagamento são fatos distintos, conferidos pelo RH."""

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, field_validator, model_validator

from app.schemas.apuracao_periodos import (
    ContratoPeriodo,
    IntervaloApuracao,
    ValorManual,
    VigenciaRegra,
)
from app.schemas.fontes_oficiais import effect_date
from app.schemas.referencias_salariais import ValorReferencia


def codigo(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,8}", value.strip()):
        raise ValueError("Informe o código da rubrica com até oito dígitos.")
    return value.strip().zfill(5)


Codigo = Annotated[str, BeforeValidator(codigo)]
Identificador = Annotated[str, Field(min_length=1, max_length=100)]
Categoria = Literal["REGULAR", "DECIMO_TERCEIRO"]
Papel = Literal["CONTRIBUICAO", "ABONO"]


def competencia(value):
    if not isinstance(value, str):
        raise ValueError("Informe competência AAAA-MM.")  # noqa: TRY004
    from datetime import datetime

    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise ValueError("Informe competência AAAA-MM válida.") from exc
    if value != f"{parsed.year:04}-{parsed.month:02}":
        raise ValueError("Informe competência AAAA-MM.")
    return value


Competencia = Annotated[str, BeforeValidator(competencia)]


class RegraAbono(VigenciaRegra):
    confirmada: bool = Field(default=False, strict=True)
    formula: Literal["CONTRIBUICAO_ELEGIVEL_CONFIRMADA"]


class MapeamentoAbono(ContratoPeriodo):
    rubrica: Codigo
    papel: Papel
    categoria: Categoria
    fonte: str = Field(min_length=1, max_length=300)
    confirmado: bool = Field(default=False, strict=True)


class ParcelaAbono(ContratoPeriodo):
    id: Identificador
    categoria: Categoria
    competencia_direito: Competencia | None = None
    exercicio_13: int | None = Field(default=None, strict=True, ge=1, le=9999)
    periodo_referencia: IntervaloApuracao
    rubrica_abono: Codigo
    natureza_folha_devida: str = Field(min_length=1, max_length=40)
    contribuicao: Literal["PENDENTE", "IDENTIFICADA", "ZERO_CONFIRMADO"] = "PENDENTE"
    recebimento: Literal["PENDENTE", "IDENTIFICADO", "NAO_HOUVE_CONFIRMADO"] = (
        "PENDENTE"
    )
    fonte_conferencia: str = Field(min_length=1, max_length=300)
    valor_elegivel: ValorManual | None = None
    justificativa_elegivel: str = Field(default="", max_length=500)

    @field_validator("natureza_folha_devida", mode="before")
    @classmethod
    def natureza(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def identificacao(self):
        first, last = (
            self.periodo_referencia.inicio,
            self.periodo_referencia.ultimo_dia_considerado,
        )
        if self.categoria == "REGULAR":
            if (
                not self.competencia_direito
                or self.exercicio_13 is not None
                or any(
                    f"{d.year:04}-{d.month:02}" != self.competencia_direito
                    for d in (first, last)
                )
            ):
                raise ValueError(
                    "Parcela regular exige competência e período dentro do mesmo mês, sem exercício de 13º."
                )
        elif (
            self.exercicio_13 is None
            or self.competencia_direito is not None
            or any(d.year != self.exercicio_13 for d in (first, last))
        ):
            raise ValueError(
                "Parcela de 13º exige exercício e período nesse ano, sem competência regular presumida."
            )
        if self.valor_elegivel is not None and not self.justificativa_elegivel:
            raise ValueError("Justifique o valor elegível conferido manualmente.")
        return self

    def chave(self):
        return (self.categoria, self.competencia_direito or str(self.exercicio_13))


class Cobertura13(ContratoPeriodo):
    exercicio: int = Field(strict=True, ge=1, le=9999)
    situacao: Literal["PENDENTE", "INCLUIDO", "NAO_APLICAVEL_CONFIRMADO"]
    justificativa: str = Field(min_length=1, max_length=500)


class LancamentoAbono(ContratoPeriodo):
    id: Identificador
    papel: Papel
    categoria: Categoria
    parcela_id: Identificador
    competencia: Competencia
    rubrica: Codigo
    natureza_folha: str = Field(min_length=1, max_length=40)
    natureza_rubrica: Literal["R", "D"]
    identificador_folha: Identificador
    sequencia: Identificador
    operacao: Literal["LANCAMENTO", "COMPLEMENTO", "ESTORNO"]
    valor: ValorReferencia | None = None
    origem: str = Field(min_length=1, max_length=300)
    complementa_id: Identificador | None = None
    estorna_id: Identificador | None = None
    conferido: bool = Field(default=False, strict=True)

    @field_validator("natureza_folha", "natureza_rubrica", mode="before")
    @classmethod
    def natureza(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def operacoes(self):
        if (self.operacao == "ESTORNO") != (self.estorna_id is not None) or (
            self.operacao == "COMPLEMENTO"
        ) != (self.complementa_id is not None):
            raise ValueError(
                "Informe exclusivamente a referência original exigida pela operação."
            )
        return self


class ObservacaoAbono(ContratoPeriodo):
    rubrica: Codigo
    descricao: str = Field(default="", max_length=200)
    competencia: Competencia | None = None
    natureza_rubrica: Literal["R", "D"] | None = None
    sequencia: str = Field(default="", max_length=100)
    valor_observado: str | None = Field(
        default=None, max_length=60, pattern=r"^[+-]?[0-9]+(?:\.[0-9]+)?$"
    )
    localizador: str = Field(min_length=1, max_length=200)
    decisao: Literal["PENDENTE", "UTILIZADO", "DESCARTADO"] = "PENDENTE"
    lancamento_id: Identificador | None = None
    justificativa: str = Field(default="", max_length=500)
    correcao_sinal_confirmada: bool = Field(default=False, strict=True)


class DocumentoAbono(ContratoPeriodo):
    id: Identificador
    nome_arquivo: str = Field(min_length=1, max_length=200)
    matricula_identificada: str | None = Field(default=None, max_length=100)
    vinculo_identificado: Identificador
    vinculo_confirmado: bool = Field(default=False, strict=True)
    observacoes: list[ObservacaoAbono] = Field(default_factory=list, max_length=200)


class PlanoAbono(ContratoPeriodo):
    vinculo_id: Identificador
    periodo_direito: IntervaloApuracao
    data_documento: date | None = None
    data_requerimento: date | None = None
    regra: RegraAbono
    mapeamentos: list[MapeamentoAbono] = Field(min_length=1, max_length=40)
    parcelas: list[ParcelaAbono] = Field(min_length=1, max_length=650)
    cobertura_13: list[Cobertura13] = Field(min_length=1, max_length=51)
    lancamentos: list[LancamentoAbono] = Field(default_factory=list, max_length=2000)
    documentos: list[DocumentoAbono] = Field(default_factory=list, max_length=10)
    conferido_pelo_rh: bool = Field(default=False, strict=True)

    _datas = field_validator("data_documento", "data_requerimento", mode="before")(
        effect_date
    )

    @model_validator(mode="after")
    def limites(self):
        start, end = (
            self.periodo_direito.inicio,
            self.periodo_direito.ultimo_dia_considerado,
        )
        if (end.year - start.year) * 12 + end.month - start.month >= 600:
            raise ValueError(
                "Divida o período de direito: limite técnico de 600 competências."
            )
        for records in (self.parcelas, self.documentos):
            if len({row.id for row in records}) != len(records):
                raise ValueError("Identificadores repetidos no mesmo grupo.")
        if len({row.chave() for row in self.parcelas}) != len(self.parcelas):
            raise ValueError(
                "Parcela de direito repetida: competência regular ou exercício de 13º."
            )
        if len({row.exercicio for row in self.cobertura_13}) != len(self.cobertura_13):
            raise ValueError("Cobertura de 13º repetida para o exercício.")
        if len({(row.rubrica, row.categoria) for row in self.mapeamentos}) != len(
            self.mapeamentos
        ):
            raise ValueError(
                "Rubrica mapeada mais de uma vez; confira papel e categoria."
            )
        for row in self.mapeamentos:
            if row.rubrica in ("98002", "98004") and (
                row.papel != "CONTRIBUICAO"
                or row.categoria
                != ("REGULAR" if row.rubrica == "98002" else "DECIMO_TERCEIRO")
            ):
                raise ValueError(
                    "98002 e 98004 são candidatas de contribuição regular/13º, não pagamentos de abono."
                )
        return self
