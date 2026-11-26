"""Progressão TAE/docente com eventos explícitos e referências confirmadas."""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.apuracao_periodos import (
    ChaveFolha,
    ContratoPeriodo,
    EstadoRemuneratorio,
    EventoRemuneratorio,
    Identificador,
    InterrupcaoApuracao,
    IntervaloApuracao,
    Percentual,
    PlanoApuracao,
    RubricaApuracao,
    ValorManual,
    VigenciaRegra,
)
from app.schemas.fontes_oficiais import effect_date
from app.utils.salary_keys import salary_key

FormulaProgressao = Literal[
    "VB",
    "RT",
    "IQ_SOBRE_VB",
    "ADICIONAL_SOBRE_VB",
    "ADICIONAL_CONFIRMADO",
    "ANUENIO_SOBRE_VB",
]


class RegraHistorica(VigenciaRegra):
    pass


class RubricaProgressao(RubricaApuracao):
    # Componentes internos da diferença docente não são códigos de lançamento SIAPE.
    rubrica: str = Field(pattern=r"^(?:[0-9]{1,8}|DIF-VB|DIF-RT|DIF-ANUENIO)$")
    formula: FormulaProgressao
    regra: RegraHistorica
    apurar_principal: bool = Field(default=True, strict=True)

    @field_validator("rubrica")
    @classmethod
    def codigo(cls, value):
        return value if value.startswith("DIF-") else super().codigo(value)

    @model_validator(mode="after")
    def validar_componente_interno(self):
        formulas = {"DIF-VB": "VB", "DIF-RT": "RT", "DIF-ANUENIO": "ANUENIO_SOBRE_VB"}
        if self.rubrica in formulas and (
            self.formula != formulas[self.rubrica] or self.natureza_rubrica != "R" or self.natureza_folha != "NORMAL"
        ):
            raise ValueError("O componente da diferença docente exige a fórmula correspondente na folha regular.")
        return self


class InterrupcaoProgressao(InterrupcaoApuracao):
    regra: RegraHistorica

    @model_validator(mode="after")
    def vigencia_da_interrupcao(self):
        if not self.regra.cobre(self.inicio) or not self.regra.cobre(
            self.ultimo_dia_considerado
        ):
            raise ValueError(
                "A vigência da regra deve cobrir todos os dias da interrupção."
            )
        return self


class EventoProgressao(EventoRemuneratorio):
    tipo: Literal["PROGRESSAO", "IQ", "RT", "JORNADA", "ADICIONAL", "ANUENIO", "BASE"]
    regra: RegraHistorica

    @model_validator(mode="after")
    def evento_independente(self):
        if self.tipo == "BASE":
            if (
                not self.alteracoes.model_fields_set
                or not self.alteracoes.model_fields_set <= {"vb_manual", "rt_manual"}
            ):
                raise ValueError(
                    "O evento BASE deve alterar somente VB/RT manuais ou retornar à tabela."
                )
            if not self.regra.cobre(self.efeitos_financeiros):
                raise ValueError(
                    "Os efeitos financeiros estão fora da vigência da regra do evento."
                )
            return self
        required = {
            "PROGRESSAO": {"posicao"},
            "JORNADA": {"posicao"},
            "IQ": {"percentual_iq", "titulacao"},
            "RT": {"titulacao"},
            "ADICIONAL": {"percentual_adicional"},
            "ANUENIO": {"percentual_anuenio"},
        }[self.tipo]
        if self.tipo == "ADICIONAL" and "adicional" in self.alteracoes.model_fields_set:
            required = {"adicional"}
        if self.alteracoes.model_fields_set != required:
            raise ValueError(
                f"O evento {self.tipo} deve alterar somente {', '.join(sorted(required))}."
            )
        if not self.regra.cobre(self.efeitos_financeiros):
            raise ValueError(
                "Os efeitos financeiros estão fora da vigência da regra do evento."
            )
        return self


class ReflexoProgressao(ChaveFolha):
    id: Identificador
    tipo: Literal["FERIAS_UM_TERCO", "DECIMO_TERCEIRO"]
    data_base: date
    competencia: str = Field(pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
    avos: int = Field(gt=0, le=12, strict=True)
    formulas_base: list[FormulaProgressao] = Field(min_length=1, max_length=5)
    regra: RegraHistorica
    origem: Identificador | None = None
    periodo_referencia: IntervaloApuracao | None = None
    pagamentos_anteriores: list[Identificador] = Field(
        default_factory=list, max_length=2000
    )

    _data = field_validator("data_base", mode="before")(effect_date)

    @model_validator(mode="after")
    def base_explicita(self):
        if len(self.formulas_base) != len(set(self.formulas_base)):
            raise ValueError("Não repita componentes na base do reflexo.")
        if not self.regra.cobre(self.data_base):
            raise ValueError("A data-base está fora da vigência da regra do reflexo.")
        if "ADICIONAL_CONFIRMADO" in self.formulas_base and (
            self.origem is None
            or self.periodo_referencia is None
            or "pagamentos_anteriores" not in self.model_fields_set
        ):
            raise ValueError(
                "Reflexo de adicional exige origem, período de referência e pagamentos anteriores discriminados, inclusive lista vazia confirmada."
            )
        return self


class EstadoProgressao(EstadoRemuneratorio):
    percentual_adicional: Percentual | None = None
    percentual_anuenio: Percentual


def validar_reflexos_adicionais(plan):
    """Um mesmo direito de reflexo não pode reaparecer com outra data-base/rubrica."""
    seen = []
    for item in plan.reflexos:
        if "ADICIONAL_CONFIRMADO" not in item.formulas_base:
            continue
        for other in seen:
            if (
                item.origem.casefold() == other.origem.casefold()
                and item.tipo == other.tipo
                and item.periodo_referencia.inicio
                <= other.periodo_referencia.ultimo_dia_considerado
                and item.periodo_referencia.ultimo_dia_considerado
                >= other.periodo_referencia.inicio
            ):
                raise ValueError(
                    "Reflexos de adicional com a mesma origem e tipo não podem repetir dias do período de referência."
                )
        if any(
            (r.rubrica, r.natureza_folha, r.natureza_rubrica)
            == (item.rubrica, item.natureza_folha, item.natureza_rubrica)
            for r in plan.rubricas
        ):
            raise ValueError(
                "Discrimine rubricas/naturezas do principal e dos reflexos do adicional."
            )
        seen.append(item)


class BaseMensalProgressao(ContratoPeriodo):
    id: Identificador
    competencia: str = Field(pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
    vb: ValorManual
    rt: ValorManual | None = Field(default=None, exclude_if=lambda value: value is None)
    base_mensal_integral_confirmada: bool = Field(default=False, strict=True)


class PlanoProgressao(PlanoApuracao):
    bases_mensais_origem: list[BaseMensalProgressao] = Field(default_factory=list, max_length=120, exclude_if=lambda value: not value)
    modalidade: Literal["TAE", "DOCENTE"]
    estado_inicial: EstadoProgressao
    eventos: list[EventoProgressao] = Field(default_factory=list, max_length=100)
    interrupcoes: list[InterrupcaoProgressao] = Field(
        default_factory=list, max_length=100
    )
    rubricas: list[RubricaProgressao] = Field(min_length=1, max_length=5)
    reflexos: list[ReflexoProgressao] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def modalidade_e_referencias(self):
        origin = self.estado_inicial
        if self.bases_mensais_origem:
            if self.modalidade != "DOCENTE":
                raise ValueError("Bases mensais da ficha são suportadas neste fluxo apenas para docente.")
            entries = self.bases_mensais_origem
            if len({item.competencia for item in entries}) != len(entries) or len({item.id for item in entries}) != len(entries):
                raise ValueError("Não repita competências ou identificadores das bases mensais.")
            if any(not item.base_mensal_integral_confirmada or not (item.vb.justificativa or "").strip() for item in entries):
                raise ValueError("Confira a base mensal integral de cada competência e justifique sua utilização.")
            if any(item.rt is not None and not item.rt.justificativa for item in entries):
                raise ValueError("Registre a conferência da RT mensal utilizada.")
            progressions = [event.efeitos_financeiros for event in self.eventos if event.tipo == "PROGRESSAO"]
            if not progressions or min(progressions) != self.periodo.inicio:
                raise ValueError("Com bases mensais, inicie a apuração na data dos efeitos da primeira progressão.")
            if any(not f"{self.periodo.inicio:%Y-%m}" <= item.competencia <= f"{self.periodo.ultimo_dia_considerado:%Y-%m}" for item in entries):
                raise ValueError("Base mensal fora do período apurado.")
        for state in (origin, *(event.alteracoes for event in self.eventos)):
            for manual in (state.vb_manual, state.rt_manual):
                if manual is not None and not (manual.justificativa or "").strip():
                    raise ValueError(
                        "Justifique a correção individual de VB/RT em relação à referência."
                    )
        tae = origin.posicao.carreira == "TAE"
        if tae != (self.modalidade == "TAE"):
            raise ValueError("A modalidade deve corresponder à carreira de origem.")
        if tae and origin.rt_manual is not None:
            raise ValueError(
                "RT é exclusiva de docente; não informe RT manual para TAE."
            )
        if tae and origin.percentual_iq is None:
            raise ValueError("Informe o IQ inicial explicitamente, inclusive zero.")
        if not tae and (
            salary_key(origin.titulacao) == "n/a" or origin.percentual_iq is not None
        ):
            raise ValueError("Docente exige titulação da RT; IQ é exclusivo de TAE.")
        formulas = [item.formula for item in self.rubricas]
        if any(item.rubrica.startswith("DIF-") for item in self.rubricas) and (tae or self.recebidos or self.interrupcoes):
            raise ValueError("Para TAE, interrupções ou abatimento de pagamentos, utilize as rubricas de folha identificadas.")
        if "ADICIONAL_SOBRE_VB" in formulas and origin.percentual_adicional is None:
            raise ValueError(
                "Confirme o percentual inicial da fórmula legada do adicional."
            )
        if {"ADICIONAL_CONFIRMADO", "ADICIONAL_SOBRE_VB"}.issubset(formulas):
            raise ValueError(
                "Não duplique o adicional nas fórmulas confirmada e legada."
            )
        if len(formulas) != len(set(formulas)):
            raise ValueError(
                "Use uma única rubrica para cada componente, sem duplicar diferenças."
            )
        required = {"VB", "IQ_SOBRE_VB"} if tae else {"VB", "RT"}
        if not required.issubset(formulas) or (
            "RT" in formulas if tae else "IQ_SOBRE_VB" in formulas
        ):
            raise ValueError(
                "TAE exige VB e IQ; docente exige VB e RT, em parcelas distintas."
            )
        for field, formula in (
            ("percentual_adicional", "ADICIONAL_SOBRE_VB"),
            ("percentual_anuenio", "ANUENIO_SOBRE_VB"),
        ):
            if (
                (
                    getattr(origin, field)
                    or any(getattr(item.alteracoes, field) for item in self.eventos)
                )
                and formula not in formulas
                and not (
                    field == "percentual_adicional"
                    and "ADICIONAL_CONFIRMADO" in formulas
                )
            ):
                raise ValueError(
                    f"Inclua a rubrica {formula} para o percentual informado."
                )
        for rubric in self.rubricas:
            if not rubric.regra.cobre(self.periodo.inicio) or not rubric.regra.cobre(
                self.periodo.ultimo_dia_considerado
            ):
                raise ValueError(
                    "A regra de base da rubrica precisa cobrir o período da apuração."
                )
        current_position = origin.posicao
        for event in sorted(
            self.eventos, key=lambda item: (item.efeitos_financeiros, item.id)
        ):
            if tae and event.alteracoes.rt_manual is not None:
                raise ValueError(
                    "RT é exclusiva de docente; não informe RT manual para TAE."
                )
            if (tae and event.tipo == "RT") or (not tae and event.tipo == "IQ"):
                raise ValueError("IQ é exclusivo de TAE e RT é exclusiva de docente.")
            position = event.alteracoes.posicao
            if position and (
                position.carreira != origin.posicao.carreira
                or position.vinculo != origin.posicao.vinculo
            ):
                raise ValueError(
                    "A progressão não pode trocar a carreira ou o vínculo de origem."
                )
            if position:
                same_position = (
                    current_position.model_copy(
                        update={"jornada": position.jornada}
                    ).chave_estrutura()
                    == position.chave_estrutura()
                )
                if event.tipo == "JORNADA" and (
                    not same_position or current_position.jornada == position.jornada
                ):
                    raise ValueError(
                        "O evento JORNADA deve alterar somente a jornada da posição corrente."
                    )
                if event.tipo == "PROGRESSAO" and same_position:
                    raise ValueError(
                        "Informe uma mudança de posição para o evento PROGRESSAO."
                    )
                current_position = position
            if (
                not tae
                and event.alteracoes.titulacao is not None
                and salary_key(event.alteracoes.titulacao) == "n/a"
            ):
                raise ValueError("Informe a titulação correspondente à RT confirmada.")
        ids = [item.id for item in self.reflexos]
        if len(ids) != len(set(ids)):
            raise ValueError("Reflexos duplicados: identificadores repetidos.")
        components: dict[tuple[str, date, str, str, str, str], set[str]] = {}
        for index, item in enumerate(self.reflexos):
            identity = (
                item.tipo,
                item.data_base,
                item.competencia,
                item.rubrica,
                item.natureza_folha,
                item.natureza_rubrica,
            )
            included = components.setdefault(identity, set())
            if included.intersection(item.formulas_base):
                raise ValueError(
                    f"Reflexo {index + 1}: componentes sobrepostos para a mesma data-base, competência, rubrica e naturezas."
                )
            included.update(item.formulas_base)
            if (
                not self.periodo.inicio
                <= item.data_base
                <= self.periodo.ultimo_dia_considerado
            ):
                raise ValueError(
                    "A data-base do reflexo precisa estar no período apurado."
                )
            if (
                not f"{self.periodo.inicio.year:04}-{self.periodo.inicio.month:02}"
                <= item.competencia
                <= f"{self.periodo.ultimo_dia_considerado.year:04}-{self.periodo.ultimo_dia_considerado.month:02}"
            ):
                raise ValueError(
                    "A competência do reflexo precisa estar no período apurado."
                )
            if not set(item.formulas_base).issubset(formulas):
                raise ValueError(
                    "A base do reflexo deve identificar componentes da apuração."
                )
        validar_reflexos_adicionais(self)
        return self
