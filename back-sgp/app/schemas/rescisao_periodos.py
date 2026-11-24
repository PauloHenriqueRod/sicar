"""Contrato explícito de rescisão; a confirmação do direito pertence ao RH."""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.apuracao_periodos import (
    ContratoPeriodo,
    IntervaloApuracao,
    ParcelaRecebida,
    ValorManual,
    VigenciaRegra,
)
from app.schemas.fontes_oficiais import effect_date
from app.schemas.referencias_salariais import ConsultaSalarial


class BaseRescisao(ContratoPeriodo):
    valor_manual: ValorManual | None = None
    referencia_salarial: ConsultaSalarial | None = None
    titulacao: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def origem_unica(self):
        if (self.valor_manual is None) == (self.referencia_salarial is None):
            raise ValueError(
                "Informe uma base manual com fonte ou uma referência salarial, exclusivamente."
            )
        if self.referencia_salarial and (
            self.referencia_salarial.carreira == "TAE"
            or self.referencia_salarial.vinculo
            not in ("TEMPORARIO", "SUBSTITUTO", "PROFESSOR_SUBSTITUTO")
        ):
            raise ValueError(
                "A referência deve corresponder ao vínculo docente temporário."
            )
        return self


class FaixaSalario(IntervaloApuracao):
    base: BaseRescisao


class CorrecaoQuantidade(ContratoPeriodo):
    valor: int = Field(strict=True, ge=0, le=1200)
    justificativa: str = Field(min_length=1, max_length=500)


class RegraRescisao(VigenciaRegra):
    confirmada: bool = Field(default=False, strict=True)
    aniversario_meses_curtos: Literal["LIMITAR_DIA_AO_MES"] | None = None
    motivos_suportados: list[Literal["TERMINO_CONTRATO", "RESCISAO_ANTECIPADA"]] = (
        Field(min_length=1, max_length=2)
    )
    ferias_sem_teto_confirmada: bool = Field(default=False, strict=True)
    limite_avos_ferias: int | None = Field(default=None, strict=True, ge=1, le=1200)

    @model_validator(mode="after")
    def teto_explicito(self):
        if self.ferias_sem_teto_confirmada and self.limite_avos_ferias is not None:
            raise ValueError(
                "Informe limite ou ausência de teto confirmada, exclusivamente."
            )
        return self


class PagamentoFerias(ParcelaRecebida):
    ordem_devolucao: int | None = Field(default=None, strict=True, ge=1, le=1000)
    data_pagamento: date | None = None
    _data_pagamento = field_validator("data_pagamento", mode="before")(effect_date)
    rubrica: Literal["00750"] = "00750"
    periodo_aquisitivo: IntervaloApuracao
    avos: int = Field(strict=True, ge=0, le=12)
    pagamento_original_id: str | None = Field(
        default=None, min_length=1, max_length=100
    )
    base_terco: ValorManual | None = None


class CampoRescisaoExtraido(ContratoPeriodo):
    campo: Literal[
        "inicio_exercicio",
        "data_termino",
        "contrato_id",
        "inicio_ferias",
        "dias_ferias",
    ]
    valor: str = Field(min_length=1, max_length=200)
    localizador: str = Field(min_length=1, max_length=200)


class PagamentoRescisaoObservado(ContratoPeriodo):
    competencia: str | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}$")
    rubrica: Literal["00742", "00750", "00772", "82696", "82407"]
    natureza_rubrica: Literal["R", "D"] | None = None
    sequencia: str = Field(max_length=100)
    valor_observado: str | None = Field(
        default=None, max_length=60, pattern=r"^-?[0-9]+(?:\.[0-9]+)?$"
    )
    localizador: str = Field(min_length=1, max_length=200)


class DocumentoRescisao(ContratoPeriodo):
    id: str = Field(min_length=1, max_length=100)
    nome_arquivo: str = Field(min_length=1, max_length=200)
    papel: Literal[
        "FICHA_FINANCEIRA", "CADASTRO", "TERMINO", "CONTRATO_ADITIVO", "FERIAS", "OUTRO"
    ]
    matricula_identificada: str | None = Field(default=None, max_length=100)
    vinculo_confirmado: bool = Field(default=False, strict=True)
    contrato_identificado: str = Field(min_length=1, max_length=100)
    observacoes: str = Field(default="", max_length=1000)
    candidatos: list[CampoRescisaoExtraido] = Field(
        default_factory=list, max_length=100
    )
    pagamentos_observados: list[PagamentoRescisaoObservado] = Field(
        default_factory=list, max_length=200
    )


class PlanoRescisao(ContratoPeriodo):
    modalidade: Literal["PROFESSOR_SUBSTITUTO", "OUTRO"]
    motivo_termino: Literal["TERMINO_CONTRATO", "RESCISAO_ANTECIPADA", "OUTRO"]
    contrato_id: str = Field(min_length=1, max_length=100)
    natureza_folha_devida: str = Field(min_length=1, max_length=40)
    inicio_exercicio: date
    data_termino: date
    sentido_termino: Literal["A_PARTIR_DE", "INCLUSIVO"]
    ultimo_dia_trabalhado: date | None = None
    ultimo_dia_considerado: date | None = None
    justificativa_ultimo_dia: str = Field(default="", max_length=500)
    regra: RegraRescisao
    correcoes: dict[
        Literal["dias_salariais", "avos_ferias", "avos_13"], CorrecaoQuantidade
    ] = Field(default_factory=dict, max_length=3)
    salarios: list[FaixaSalario] = Field(default_factory=list, max_length=100)
    base_ferias: BaseRescisao | None = None
    base_13: BaseRescisao | None = None
    pagamentos_ferias: list[PagamentoFerias] = Field(
        default_factory=list, max_length=1000
    )
    recebidos: list[ParcelaRecebida] = Field(default_factory=list, max_length=2000)
    documentos: list[DocumentoRescisao] = Field(default_factory=list, max_length=10)
    conferido_pelo_rh: bool = Field(default=False, strict=True)

    @field_validator("natureza_folha_devida", mode="before")
    @classmethod
    def normalizar_natureza_folha(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    _datas = field_validator(
        "inicio_exercicio",
        "data_termino",
        "ultimo_dia_trabalhado",
        "ultimo_dia_considerado",
        mode="before",
    )(effect_date)

    @model_validator(mode="after")
    def datas_e_fontes(self):
        if self.data_termino < self.inicio_exercicio:
            raise ValueError("Término não pode anteceder o exercício.")
        if (self.data_termino.year - self.inicio_exercicio.year) * 12 > 1200:
            raise ValueError(
                "Divida ou confira o contrato: limite técnico de 1200 meses."
            )
        for day in (self.ultimo_dia_trabalhado, self.ultimo_dia_considerado):
            if (
                day is not None
                and not self.inicio_exercicio <= day <= self.data_termino
            ):
                raise ValueError("Último dia deve estar entre exercício e término.")
        if len({doc.id for doc in self.documentos}) != len(self.documentos):
            raise ValueError("Documento repetido.")
        return self
