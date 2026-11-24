"""Apuração de adicionais ocupacionais com concessão, base e reflexos explícitos."""

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.apuracao_periodos import (
    EventoRemuneratorio,
    PlanoApuracao,
    RubricaApuracao,
)
from app.schemas.progressao_eventos import (
    InterrupcaoProgressao,
    ReflexoProgressao,
    RegraHistorica,
    validar_reflexos_adicionais,
)


class RubricaAdicional(RubricaApuracao):
    formula: Literal["ADICIONAL_CONFIRMADO"]
    regra: RegraHistorica
    apurar_principal: bool = Field(default=True, strict=True)


class EventoAdicional(EventoRemuneratorio):
    tipo: Literal["ADICIONAL", "POSICAO", "RT"]
    regra: RegraHistorica

    @model_validator(mode="after")
    def alteracao_tipificada(self):
        required = {
            "ADICIONAL": {"adicional"},
            "POSICAO": {"posicao"},
            "RT": {"titulacao"},
        }[self.tipo]
        if self.alteracoes.model_fields_set != required:
            raise ValueError(
                "A alteração deve corresponder ao tipo do evento de adicional."
            )
        if not self.regra.cobre(self.efeitos_financeiros):
            raise ValueError(
                "Os efeitos financeiros estão fora da vigência da regra do evento."
            )
        return self


class PlanoAdicionais(PlanoApuracao):
    rubricas: list[RubricaAdicional] = Field(min_length=1, max_length=1)
    eventos: list[EventoAdicional] = Field(default_factory=list, max_length=100)
    interrupcoes: list[InterrupcaoProgressao] = Field(
        default_factory=list, max_length=100
    )
    reflexos: list[ReflexoProgressao] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def bases_e_reflexos(self):
        if (
            self.estado_inicial.vb_manual is not None
            or self.estado_inicial.rt_manual is not None
        ):
            raise ValueError(
                "Use referências confirmadas de VB/RT ou uma base VALOR_CONFIRMADO com fonte própria."
            )
        ids = [item.id for item in self.reflexos]
        for rubric in self.rubricas:
            if not rubric.regra.cobre(self.periodo.inicio) or not rubric.regra.cobre(
                self.periodo.ultimo_dia_considerado
            ):
                raise ValueError("A regra da rubrica deve cobrir o período apurado.")
        if len(ids) != len(set(ids)):
            raise ValueError("Reflexos duplicados: identificadores repetidos.")
        identities = set()
        for event in self.reflexos:
            if event.formulas_base != ["ADICIONAL_CONFIRMADO"]:
                raise ValueError(
                    "O reflexo deste fluxo deve usar somente o adicional confirmado."
                )
            identity = (
                event.tipo,
                event.data_base,
                event.competencia,
                event.rubrica,
                event.natureza_folha,
                event.natureza_rubrica,
            )
            if identity in identities:
                raise ValueError("Reflexos com componentes sobrepostos.")
            identities.add(identity)
            if (
                not self.periodo.inicio
                <= event.data_base
                <= self.periodo.ultimo_dia_considerado
            ):
                raise ValueError(
                    "A data-base do reflexo deve estar no período apurado."
                )
            if (
                not f"{self.periodo.inicio.year:04}-{self.periodo.inicio.month:02}"
                <= event.competencia
                <= f"{self.periodo.ultimo_dia_considerado.year:04}-{self.periodo.ultimo_dia_considerado.month:02}"
            ):
                raise ValueError(
                    "A competência do reflexo deve estar no período apurado."
                )
        validar_reflexos_adicionais(self)
        return self
