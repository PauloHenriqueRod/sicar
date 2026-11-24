"""Parcelas de exercícios anteriores; direito e conferência permanecem com o RH."""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.abono_parcelas import Codigo, Competencia, Identificador
from app.schemas.apuracao_periodos import (
    ContratoPeriodo,
    IntervaloApuracao,
    VigenciaRegra,
)
from app.schemas.fontes_oficiais import effect_date
from app.schemas.referencias_salariais import ValorReferencia


class RegraExercicio(VigenciaRegra):
    confirmada: bool = Field(default=False, strict=True)


class OrigemDireito(ContratoPeriodo):
    id: Identificador
    descricao: str = Field(min_length=1, max_length=500)
    periodo_efeitos: IntervaloApuracao
    data_documento: date | None = None
    fonte: str = Field(min_length=1, max_length=300)
    localizador: str = Field(min_length=1, max_length=200)
    regra: RegraExercicio
    _data = field_validator("data_documento", mode="before")(effect_date)


class ParcelaExercicio(ContratoPeriodo):
    id: Identificador
    origem_direito_id: Identificador
    competencia: Competencia
    rubrica: Codigo
    categoria: Literal[
        "PRINCIPAL", "FERIAS", "TERCO_FERIAS", "DECIMO_TERCEIRO", "OUTRA"
    ]
    periodo_referencia: IntervaloApuracao
    natureza_folha_devida: str = Field(min_length=1, max_length=40)
    estado_revisao: Literal["PENDENTE", "CONFERIDO", "ENCAMINHADO"] = "PENDENTE"
    nota_revisao: str = Field(min_length=1, max_length=500)
    pesquisa_pagamentos: Literal[
        "PENDENTE", "IDENTIFICADOS", "NAO_HOUVE_CONFIRMADO"
    ] = "PENDENTE"

    @field_validator("natureza_folha_devida", mode="before")
    @classmethod
    def natureza(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    def chave(self):
        return (
            self.origem_direito_id,
            self.competencia,
            self.rubrica,
            self.categoria,
            self.natureza_folha_devida,
        )


class LancamentoVinculado(ContratoPeriodo):
    id: Identificador
    parcela_id: Identificador
    operacao: Literal["LANCAMENTO", "COMPLEMENTO", "ESTORNO"]
    valor: ValorReferencia | None = None
    complementa_id: Identificador | None = None
    estorna_id: Identificador | None = None
    fonte: str = Field(min_length=1, max_length=300)
    localizador: str = Field(min_length=1, max_length=200)
    conferido: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def referencia_operacao(self):
        if (self.operacao == "COMPLEMENTO") != (self.complementa_id is not None) or (
            self.operacao == "ESTORNO"
        ) != (self.estorna_id is not None):
            raise ValueError(
                "Informe exclusivamente a referência original exigida pela operação."
            )
        return self


class DevidoExercicio(LancamentoVinculado):
    identificador_evento: Identificador
    memoria_calculo: str = Field(min_length=1, max_length=1000)

    def chave(self):
        return self.parcela_id, self.identificador_evento

    def contexto(self):
        return (self.parcela_id,)


class RecebimentoExercicio(LancamentoVinculado):
    tipo_origem: Literal["FOLHA", "DOCUMENTO"]
    via_pagamento: Literal["NAO_INFORMADA", "ADMINISTRATIVA", "JUDICIAL"] = (
        "NAO_INFORMADA"
    )
    processo: str | None = Field(default=None, min_length=1, max_length=200)
    data_pagamento: date | None = None
    competencia_pagamento: Competencia | None = None
    rubrica_pagamento: Codigo | None = None
    natureza_folha: str | None = Field(default=None, min_length=1, max_length=40)
    natureza_rubrica: Literal["R", "D"] | None = None
    identificador_folha: Identificador | None = None
    sequencia: Identificador | None = None
    identificador_pagamento: Identificador | None = None
    justificativa_vinculo: str = Field(min_length=1, max_length=500)
    _data = field_validator("data_pagamento", mode="before")(effect_date)

    @field_validator("natureza_folha", "natureza_rubrica", mode="before")
    @classmethod
    def natureza(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def identidade_origem(self):
        if self.tipo_origem == "FOLHA":
            if any(
                value is None
                for value in (
                    self.competencia_pagamento,
                    self.rubrica_pagamento,
                    self.natureza_folha,
                    self.natureza_rubrica,
                    self.identificador_folha,
                    self.sequencia,
                )
            ):
                raise ValueError(
                    "Recebimento em folha exige competência, rubrica, naturezas, folha e sequência."
                )
        elif not self.identificador_pagamento or any(
            value is not None
            for value in (self.identificador_folha, self.sequencia, self.natureza_folha)
        ):
            raise ValueError(
                "Documento exige identificador de pagamento, sem inventar folha ou sequência."
            )
        return self

    def chave(self):
        if self.identificador_pagamento:
            return "PAGAMENTO", self.identificador_pagamento
        return (
            "FOLHA",
            self.competencia_pagamento,
            self.rubrica_pagamento,
            self.natureza_folha,
            self.natureza_rubrica,
            self.identificador_folha,
            self.sequencia,
        )

    def contexto(self):
        return (self.parcela_id,)


class AjusteExercicio(ContratoPeriodo):
    id: Identificador
    identificador_evento: Identificador | None = None
    parcela_id: Identificador
    tipo: Literal["PRESCRICAO", "JUROS", "ATUALIZACAO", "DESCONTO"]
    efeito: Literal["ACRESCIMO", "REDUCAO"]
    valor: ValorReferencia | None = None
    regra: RegraExercicio
    memoria_calculo: str = Field(min_length=1, max_length=1000)
    fonte: str = Field(min_length=1, max_length=300)
    localizador: str = Field(min_length=1, max_length=200)
    conferido: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def reducao(self):
        if self.tipo in ("PRESCRICAO", "DESCONTO") and self.efeito != "REDUCAO":
            raise ValueError(
                "Prescrição ou desconto declarado deve identificar redução."
            )
        return self


class CandidatoExercicio(ContratoPeriodo):
    tipo: Literal["DEVIDO", "RECEBIMENTO", "AJUSTE", "NAO_IDENTIFICADO"]
    competencia: Competencia | None = None
    rubrica: Codigo | None = None
    natureza_rubrica: Literal["R", "D"] | None = None
    sequencia: Identificador | None = None
    valor_observado: str | None = Field(
        default=None, max_length=60, pattern=r"^[+-]?[0-9]+(?:\.[0-9]+)?$"
    )
    descricao: str = Field(default="", max_length=200)
    localizador: str = Field(min_length=1, max_length=200)
    decisao: Literal["PENDENTE", "UTILIZADO", "DESCARTADO"] = "PENDENTE"
    alvo_tipo: Literal["DEVIDO", "RECEBIMENTO", "AJUSTE"] | None = None
    alvo_id: Identificador | None = None
    justificativa: str = Field(default="", max_length=500)
    correcao_sinal_confirmada: bool = Field(default=False, strict=True)


class DocumentoExercicio(ContratoPeriodo):
    id: Identificador
    nome_arquivo: str = Field(min_length=1, max_length=200)
    matricula_identificada: str | None = Field(default=None, max_length=100)
    vinculo_identificado: Identificador
    vinculo_confirmado: bool = Field(default=False, strict=True)
    candidatos: list[CandidatoExercicio] = Field(default_factory=list, max_length=200)


class PlanoExercicios(ContratoPeriodo):
    vinculo_id: Identificador
    periodo: IntervaloApuracao
    origens: list[OrigemDireito] = Field(min_length=1, max_length=100)
    parcelas: list[ParcelaExercicio] = Field(min_length=1, max_length=1000)
    devidos: list[DevidoExercicio] = Field(default_factory=list, max_length=2000)
    recebimentos: list[RecebimentoExercicio] = Field(
        default_factory=list, max_length=2000
    )
    ajustes: list[AjusteExercicio] = Field(default_factory=list, max_length=200)
    documentos: list[DocumentoExercicio] = Field(default_factory=list, max_length=10)
    conferido_pelo_rh: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def identidades(self):
        first, last = self.periodo.inicio, self.periodo.ultimo_dia_considerado
        if (last.year - first.year) * 12 + last.month - first.month >= 600:
            raise ValueError("Divida o período: limite técnico de 600 competências.")
        for records in (self.origens, self.parcelas, self.documentos, self.ajustes):
            if len({row.id for row in records}) != len(records):
                raise ValueError("Identificador repetido no mesmo grupo.")
        if len({row.chave() for row in self.parcelas}) != len(self.parcelas):
            raise ValueError(
                "Parcela repetida para a mesma origem, competência, rubrica, categoria e natureza de folha."
            )
        return self
