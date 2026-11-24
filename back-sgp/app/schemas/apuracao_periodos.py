"""Contrato comum de apuração; datas e direitos são conferidos pelo RH."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.fontes_oficiais import effect_date
from app.schemas.referencias_salariais import PosicaoSalarial, ValorReferencia

Identificador = Annotated[str, Field(min_length=1, max_length=100)]


def percentual_explicito(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("Percentual não pode ser booleano.")  # noqa: TRY004
    return value


Percentual = Annotated[
    Decimal,
    BeforeValidator(percentual_explicito),
    Field(ge=0, le=100, allow_inf_nan=False, max_digits=18, decimal_places=12),
]


class ContratoPeriodo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IntervaloApuracao(ContratoPeriodo):
    inicio: date
    ultimo_dia_considerado: date

    _datas = field_validator("inicio", "ultimo_dia_considerado", mode="before")(
        effect_date
    )

    @model_validator(mode="after")
    def ordem(self):
        if self.ultimo_dia_considerado < self.inicio:
            raise ValueError("O último dia considerado não pode anteceder o início.")
        return self


class ReferenciaRegra(ContratoPeriodo):
    identificador: Identificador
    versao: Identificador
    fonte: str = Field(min_length=1, max_length=300)


class ValorManual(ContratoPeriodo):
    justificativa: str | None = Field(default=None, max_length=500)
    valor: ValorReferencia
    fonte: str = Field(min_length=1, max_length=300)
    localizador: str = Field(min_length=1, max_length=200)


class VigenciaRegra(ReferenciaRegra):
    inicio_vigencia: date
    fim_vigencia: date | None = None

    _datas = field_validator("inicio_vigencia", "fim_vigencia", mode="before")(
        effect_date
    )

    @model_validator(mode="after")
    def ordem_vigencia(self):
        if self.fim_vigencia is not None and self.fim_vigencia < self.inicio_vigencia:
            raise ValueError("Confira a vigência da regra.")
        return self

    def cobre(self, day: date) -> bool:
        return self.inicio_vigencia <= day and (
            self.fim_vigencia is None or day <= self.fim_vigencia
        )


class RegraAdicional(VigenciaRegra):
    confirmada: bool = Field(default=False, strict=True)


class BaseAdicional(ContratoPeriodo):
    tipo: Literal["VB", "VB_RT", "VALOR_CONFIRMADO"] | None = None
    confirmada: bool = Field(default=False, strict=True)
    valor_manual: ValorManual | None = None


class ConcessaoAdicional(ContratoPeriodo):
    identificador: Identificador
    especie: (
        Literal["INSALUBRIDADE", "PERICULOSIDADE", "IRRADIACAO", "RAIOS_X", "OUTRO"]
        | None
    ) = None
    descricao: str | None = Field(default=None, max_length=200)
    percentual: Percentual | None = None
    percentual_confirmado: bool = Field(default=False, strict=True)
    inicio_vigencia: date | None = None
    fim_vigencia: date | None = None
    base: BaseAdicional | None = None
    regra: RegraAdicional | None = None

    _datas = field_validator("inicio_vigencia", "fim_vigencia", mode="before")(
        effect_date
    )

    @model_validator(mode="after")
    def ordem_concessao(self):
        if (
            self.inicio_vigencia
            and self.fim_vigencia
            and self.fim_vigencia < self.inicio_vigencia
        ):
            raise ValueError("O fim da concessão não pode anteceder seu início.")
        return self


class EstadoRemuneratorio(ContratoPeriodo):
    posicao: PosicaoSalarial
    titulacao: str = Field(min_length=1, max_length=100)
    vb_manual: ValorManual | None = None
    rt_manual: ValorManual | None = None
    percentual_iq: Percentual | None = None
    percentual_adicional: Percentual | None = None
    percentual_anuenio: Percentual | None = None
    adicional: ConcessaoAdicional | None = None


class AlteracaoRemuneratoria(ContratoPeriodo):
    posicao: PosicaoSalarial | None = None
    titulacao: str | None = Field(default=None, min_length=1, max_length=100)
    vb_manual: ValorManual | None = None
    rt_manual: ValorManual | None = None
    percentual_iq: Percentual | None = None
    percentual_adicional: Percentual | None = None
    percentual_anuenio: Percentual | None = None
    adicional: ConcessaoAdicional | None = None

    @model_validator(mode="after")
    def alteracoes_explicitas(self):
        if not self.model_fields_set:
            raise ValueError("Informe ao menos uma alteração no evento.")
        for field in self.model_fields_set - {"vb_manual", "rt_manual", "adicional"}:
            if getattr(self, field) is None:
                raise ValueError(
                    f"Informe um valor explícito para {field}; zero é diferente de ausência."
                )
        return self


class EventoRemuneratorio(ContratoPeriodo):
    id: Identificador
    data_documento: date | None = None
    efeitos_financeiros: date
    data_implantacao: date | None = None
    regra: ReferenciaRegra
    alteracoes: AlteracaoRemuneratoria

    _datas = field_validator(
        "data_documento", "efeitos_financeiros", "data_implantacao", mode="before"
    )(effect_date)


class InterrupcaoApuracao(IntervaloApuracao):
    id: Identificador
    regra: ReferenciaRegra


class ChaveFolha(ContratoPeriodo):
    rubrica: str = Field(pattern=r"^[0-9]{1,8}$")
    natureza_folha: str = Field(min_length=1, max_length=40)
    natureza_rubrica: Literal["R", "D"]

    @field_validator("rubrica")
    @classmethod
    def codigo(cls, value):
        return str(int(value)).zfill(5)

    @field_validator("natureza_folha", "natureza_rubrica", mode="before")
    @classmethod
    def natureza(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class RubricaApuracao(ChaveFolha):
    formula: Literal[
        "VB",
        "RT",
        "VB_RT",
        "IQ_SOBRE_VB",
        "ADICIONAL_SOBRE_VB",
        "ADICIONAL_CONFIRMADO",
        "ANUENIO_SOBRE_VB",
        "VALOR_MENSAL",
    ]
    regra: ReferenciaRegra
    valor_mensal: ValorManual | None = None

    @model_validator(mode="after")
    def fonte_fixa(self):
        if (self.formula == "VALOR_MENSAL") != (self.valor_mensal is not None):
            raise ValueError(
                "VALOR_MENSAL exige valor e fonte próprios; outras fórmulas utilizam o estado remuneratório."
            )
        return self


class ParcelaRecebida(ChaveFolha):
    id: Identificador
    competencia: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    identificador_folha: Identificador
    sequencia: Identificador
    operacao: Literal["PAGAMENTO", "COMPLEMENTO", "ESTORNO"]
    valor: ValorReferencia
    origem: str = Field(min_length=1, max_length=300)
    estorna_id: Identificador | None = None

    @field_validator("competencia")
    @classmethod
    def mes_valido(cls, value):
        year, month = map(int, value.split("-"))
        if year < 1 or not 1 <= month <= 12:
            raise ValueError("Competência inválida; use AAAA-MM.")
        return value

    @model_validator(mode="after")
    def estorno_explicito(self):
        if (self.operacao == "ESTORNO") != (self.estorna_id is not None):
            raise ValueError("Um estorno exige o identificador do pagamento original.")
        return self


class PlanoApuracao(ContratoPeriodo):
    periodo: IntervaloApuracao
    data_documento: date | None = None
    data_implantacao: date | None = None
    estado_inicial: EstadoRemuneratorio
    eventos: Sequence[EventoRemuneratorio] = Field(default_factory=list, max_length=100)
    interrupcoes: Sequence[InterrupcaoApuracao] = Field(
        default_factory=list, max_length=100
    )
    rubricas: Sequence[RubricaApuracao] = Field(min_length=1, max_length=20)
    recebidos: list[ParcelaRecebida] = Field(max_length=2000)
    conferido_pelo_rh: Literal[True]

    _datas = field_validator("data_documento", "data_implantacao", mode="before")(
        effect_date
    )

    @field_validator("conferido_pelo_rh", mode="before")
    @classmethod
    def conferencia(cls, value):
        if value is not True:
            raise ValueError(
                "Confirme explicitamente os dados, as fontes e o período pelo RH."
            )
        return value

    @model_validator(mode="after")
    def consistencia(self):
        start, end = self.periodo.inicio, self.periodo.ultimo_dia_considerado
        if (end.year - start.year) * 12 + end.month - start.month >= 600:
            raise ValueError("Divida apurações com mais de 600 competências.")
        ids = [event.id for event in self.eventos]
        if len(ids) != len(set(ids)):
            raise ValueError("Identificadores de eventos duplicados.")
        fields: set[tuple[date, str]] = set()
        for event in self.eventos:
            if not start <= event.efeitos_financeiros <= end:
                raise ValueError(
                    "Eventos precisam ter efeitos dentro do período; o estado inicial já representa a situação no início."
                )
            for field in event.alteracoes.model_fields_set:
                key = (event.efeitos_financeiros, field)
                if key in fields:
                    raise ValueError(
                        "Há alterações concorrentes do mesmo campo na mesma data."
                    )
                fields.add(key)
        interruption_ids = [item.id for item in self.interrupcoes]
        if len(interruption_ids) != len(set(interruption_ids)):
            raise ValueError("Identificadores de interrupção duplicados.")
        for item in self.interrupcoes:
            if item.inicio < start or item.ultimo_dia_considerado > end:
                raise ValueError("Recorte as interrupções ao período da apuração.")
        keys = [
            (item.rubrica, item.natureza_folha, item.natureza_rubrica)
            for item in self.rubricas
        ]
        if sum(r.formula == "ADICIONAL_CONFIRMADO" for r in self.rubricas) > 1:
            raise ValueError(
                "A concessão do adicional deve ser apurada uma única vez por segmento, mesmo sob rubricas ou naturezas diferentes."
            )
        if {"ADICIONAL_CONFIRMADO", "ADICIONAL_SOBRE_VB"}.issubset(
            {r.formula for r in self.rubricas}
        ):
            raise ValueError(
                "Não duplique o adicional nas fórmulas confirmada e legada."
            )
        if len(keys) != len(set(keys)):
            raise ValueError(
                "Cadastre uma fórmula por rubrica e naturezas; o mesmo dia não pode ser calculado duas vezes."
            )
        for item in self.recebidos:
            if (
                not f"{start.year:04}-{start.month:02}"
                <= item.competencia
                <= f"{end.year:04}-{end.month:02}"
            ):
                raise ValueError(
                    "Selecione somente recebimentos das competências da apuração."
                )
        return self
