import calendar
import re
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.abono_parcelas import PlanoAbono
from app.schemas.adicionais import PlanoAdicionais
from app.schemas.apuracao_periodos import PlanoApuracao
from app.schemas.exercicios_parcelas import PlanoExercicios
from app.schemas.extracao_documentos import RevisaoExtracao
from app.schemas.progressao_eventos import PlanoProgressao
from app.schemas.referencias_salariais import ConsultaSalarial
from app.schemas.rescisao_periodos import PlanoRescisao
from app.schemas.substituicao_periodos import PlanoSubstituicao
from app.utils.conversor import ConversorSaneador


def numero_decimal(value: object) -> Decimal:
    # Preserva o contrato: números JSON, nunca booleanos ou textos monetários.
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        # Pydantic converte ValueError em erro de validação; TypeError escaparia
        # do contrato e poderia transformar uma entrada inválida em HTTP 500.
        raise ValueError("Informe um número finito.")  # noqa: TRY004
    return Decimal(str(value))


ValorNaoNegativo = Annotated[
    Decimal,
    BeforeValidator(numero_decimal),
    Field(ge=0, le=Decimal("1e12"), allow_inf_nan=False),
]
SaldoAvos = Annotated[
    Decimal,
    BeforeValidator(numero_decimal),
    Field(ge=-100000, le=100000, allow_inf_nan=False),
]
InteiroNaoNegativo = Annotated[int, Field(ge=0, le=100000, strict=True)]
Mes = Annotated[int, Field(ge=1, le=12, strict=True)]
Ano = Annotated[int, Field(ge=1, le=9999, strict=True)]
Texto = Annotated[str, Field(max_length=300)]


class DadosIdentificados(BaseModel):
    """Metadados conhecidos da extração; campos desconhecidos não são persistidos."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nome: Texto | None = None
    matricula: Texto | None = None
    cargo_lotacao: Texto | None = None
    funcao_exercida: Texto | None = None
    classe: Texto | None = None
    nivel: int | None = Field(default=None, gt=0, le=1000, strict=True)
    titulacao: Texto | None = None
    quantidade_anuenios: ValorNaoNegativo | None = None
    percentual_anuenio: ValorNaoNegativo | None = None
    percentual_insalubridade: ValorNaoNegativo | None = None
    percentual_adicional_sugerido: ValorNaoNegativo | None = None
    percentual_incentivo: ValorNaoNegativo | None = None
    vencimento_basico: ValorNaoNegativo | None = None
    valor_insalubridade: ValorNaoNegativo | None = None
    alertas_extracao: list[Texto] = Field(default_factory=list, max_length=100)
    revisao_extracao: RevisaoExtracao | None = None
    substitui_historico_id: int | None = Field(default=None, gt=0, strict=True)


class RescisaoDados(DadosIdentificados):
    referencia_salarial: ConsultaSalarial | None = None
    salario_mensal: ValorNaoNegativo | None = None
    classe: Texto = ""
    titulacao: Texto = ""
    nivel: int | None = Field(default=None, gt=0, le=1000, strict=True)
    # Saldos de férias negativos podem representar devoluções legítimas.
    meses_ferias: SaldoAvos = Decimal(0)
    meses_13: int = Field(default=0, ge=0, le=12, strict=True)
    dias_trabalhados: InteiroNaoNegativo = 0
    ocorrencias_adicional_ferias: InteiroNaoNegativo = 0
    valores_recebidos: dict[str, ValorNaoNegativo] = Field(
        default_factory=dict, max_length=4
    )
    mes_rescisao: Mes | None = None
    ano_rescisao: Ano | None = None
    data_exercicio: Texto | None = None
    data_rescisao: Texto | None = None

    @field_validator("data_exercicio", "data_rescisao")
    @classmethod
    def validar_data(cls, value):
        if not value:
            return None
        parsed = ConversorSaneador.para_data(value)
        if parsed is None:
            raise ValueError("Informe uma data válida, em DD/MM/AAAA ou AAAA-MM-DD.")
        return parsed.isoformat()

    @field_validator("valores_recebidos")
    @classmethod
    def validar_rubricas(cls, value):
        if set(value) - {
            "742_salario",
            "772_ferias",
            "82696_terco_ferias",
            "82407_decimo_terceiro",
        }:
            raise ValueError("Rubrica não reconhecida para rescisão.")
        return value

    @model_validator(mode="after")
    def validar_periodo(self):
        inicio = ConversorSaneador.para_data(self.data_exercicio)
        fim = ConversorSaneador.para_data(self.data_rescisao)
        if fim:
            if self.mes_rescisao not in (None, fim.month) or self.ano_rescisao not in (
                None,
                fim.year,
            ):
                raise ValueError(
                    "O mês e ano da rescisão devem corresponder à data da rescisão."
                )
            self.mes_rescisao, self.ano_rescisao = fim.month, fim.year
        if inicio and not fim:
            raise ValueError("Informe também a data da rescisão para calcular os avos.")
        if inicio and fim and inicio > fim:
            raise ValueError("A data da rescisão não pode anteceder o exercício.")
        if self.mes_rescisao is None or self.ano_rescisao is None:
            raise ValueError("Confira o mês da rescisão e o ano da rescisão.")
        if (
            self.dias_trabalhados
            > calendar.monthrange(self.ano_rescisao, self.mes_rescisao)[1]
        ):
            raise ValueError("Os dias trabalhados excedem os dias reais do mês.")
        return self


class ProgressaoDados(DadosIdentificados):
    referencia_antiga: ConsultaSalarial | None = None
    referencia_nova: ConsultaSalarial | None = None
    classe_atual: Texto = ""
    classe_antiga: Texto = ""
    titulacao: Texto = ""
    nivel_atual: int | None = Field(default=None, gt=0, strict=True)
    nivel_antigo: int | None = Field(default=None, gt=0, strict=True)
    dias_proporcionais: InteiroNaoNegativo = 0
    meses_diferenca: ValorNaoNegativo = Decimal(0)
    anuenio: ValorNaoNegativo = Decimal(0)
    insalubridade: ValorNaoNegativo = Decimal(0)
    incentivo: ValorNaoNegativo = Decimal(0)
    incentivo_antigo: ValorNaoNegativo | None = None
    incentivo_novo: ValorNaoNegativo | None = None
    salario_antigo: ValorNaoNegativo | None = None
    salario_novo: ValorNaoNegativo | None = None
    quantidade_reflexos_ferias: ValorNaoNegativo = Decimal(1)
    quantidade_reflexos_13: ValorNaoNegativo = Decimal(1)
    mes_proporcao: Mes | None = None
    ano_proporcao: Ano

    @model_validator(mode="after")
    def validar_periodo(self):
        if self.dias_proporcionais > 0:
            if self.mes_proporcao is None:
                raise ValueError("Informe o mês da proporção.")
            if (
                self.dias_proporcionais
                > calendar.monthrange(self.ano_proporcao, self.mes_proporcao)[1]
            ):
                raise ValueError("Os dias proporcionais excedem os dias reais do mês.")
        return self


class SubstituicaoDados(DadosIdentificados):
    salario_substituta: ValorNaoNegativo
    salario_propria: ValorNaoNegativo = Decimal(0)
    dias_substituidos: InteiroNaoNegativo
    dias_interrupcao: InteiroNaoNegativo = 0
    mes: Mes
    ano: Ano

    @model_validator(mode="after")
    def validar_interrupcao(self):
        if self.dias_interrupcao > self.dias_substituidos:
            raise ValueError("A interrupção não pode exceder os dias da substituição")
        if self.dias_substituidos > calendar.monthrange(self.ano, self.mes)[1]:
            raise ValueError("Os dias da substituição excedem os dias reais do mês.")
        return self


class CompetenciaExercicioAnterior(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    periodo: str = Field(min_length=1, max_length=7)
    v_dev: ValorNaoNegativo
    v_rec: ValorNaoNegativo
    ab_ferias: ValorNaoNegativo = Field(
        default=Decimal(0), validation_alias=AliasChoices("ab_ferias", "v_abono")
    )
    decimo_terceiro: ValorNaoNegativo = Field(
        default=Decimal(0),
        validation_alias=AliasChoices("13_sal", "v_13"),
        serialization_alias="13_sal",
    )

    @field_validator("periodo")
    @classmethod
    def validar_competencia(cls, value):
        match = re.fullmatch(r"([0-9]{4})-([0-9]{2})", value)
        if match:
            ano, mes = map(int, match.groups())
        else:
            match = re.fullmatch(r"([0-9]{2})/([0-9]{4})", value)
            if not match:
                raise ValueError("Informe a competência em MM/AAAA ou AAAA-MM.")
            mes, ano = map(int, match.groups())
        if not 1 <= mes <= 12 or ano < 1:
            raise ValueError("Informe uma competência válida.")
        return value


class ExercicioAnteriorDados(DadosIdentificados):
    fluxo_mensal: list[CompetenciaExercicioAnterior] = Field(
        min_length=1,
        max_length=600,
        validation_alias=AliasChoices("fluxo_mensal", "fluxo"),
    )


class AbonoDados(DadosIdentificados):
    valores_anuais: dict[
        Annotated[str, Field(pattern=r"^[0-9]{4}$")], list[ValorNaoNegativo]
    ] = Field(min_length=1, max_length=100)

    @field_validator("valores_anuais")
    @classmethod
    def validar_anos(cls, value):
        if any(
            int(ano) < 1 or not 1 <= len(valores) <= 120
            for ano, valores in value.items()
        ):
            raise ValueError("Confira o ano e informe de 1 a 120 parcelas por ano.")
        return value


class InsalubridadeDados(DadosIdentificados):
    valores_mensais: dict[
        Annotated[str, Field(min_length=1, max_length=80)], ValorNaoNegativo
    ] = Field(min_length=1, max_length=600)


class ApuracaoPeriodosDados(DadosIdentificados):
    apuracao: PlanoApuracao
    substitui_historico_id: int | None = Field(default=None, gt=0, strict=True)


class ProgressaoEventosDados(DadosIdentificados):
    progressao: PlanoProgressao
    substitui_historico_id: int | None = Field(default=None, gt=0, strict=True)


class AdicionaisDados(DadosIdentificados):
    adicionais: PlanoAdicionais
    substitui_historico_id: int | None = Field(default=None, gt=0, strict=True)


class ExerciciosParcelasDados(DadosIdentificados):
    matricula: Annotated[str, Field(min_length=1, max_length=100)]
    exercicios: PlanoExercicios

    @model_validator(mode="after")
    def pessoas_documentos(self):
        from app.utils.employee_identity import employee_key
        for doc in self.exercicios.documentos:
            if doc.matricula_identificada and employee_key(doc.matricula_identificada) != employee_key(self.matricula):
                raise ValueError("Documento de matrícula incompatível com o servidor; corrija ou remova a fonte.")
        return self


class AbonoParcelasDados(DadosIdentificados):
    matricula: Annotated[str, Field(min_length=1, max_length=100)]
    abono: PlanoAbono

    @model_validator(mode="after")
    def pessoas_documentos(self):
        from app.utils.employee_identity import employee_key
        for doc in self.abono.documentos:
            if doc.matricula_identificada and employee_key(doc.matricula_identificada) != employee_key(self.matricula):
                raise ValueError("Documento de matrícula incompatível com o servidor; corrija ou remova a fonte.")
        return self


class RescisaoPeriodosDados(DadosIdentificados):
    matricula: Texto
    rescisao: PlanoRescisao

    @model_validator(mode="after")
    def identidade_documental(self):
        from app.utils.employee_identity import employee_key
        for doc in self.rescisao.documentos:
            if doc.matricula_identificada and employee_key(doc.matricula_identificada) != employee_key(self.matricula):
                raise ValueError("Documento de outra matrícula; corrija ou remova antes de calcular.")
        return self


class SubstituicaoPeriodosDados(DadosIdentificados):
    matricula: Texto
    substituicao: PlanoSubstituicao
    substitui_historico_id: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def pessoas_documentos(self):
        from app.utils.employee_identity import employee_key as identidade

        titular = self.substituicao.titular_matricula
        if identidade(titular) == identidade(self.matricula):
            raise ValueError("Titular e substituto devem ter matrículas distintas.")
        for doc in self.substituicao.documentos:
            if doc.matricula_identificada and doc.pessoa is None:
                raise ValueError("Indique a pessoa identificada em cada documento com matrícula extraída.")
            if doc.matricula_identificada and doc.pessoa in ("TITULAR", "SUBSTITUTO"):
                expected = titular if doc.pessoa == "TITULAR" else self.matricula
                if identidade(doc.matricula_identificada) != identidade(expected):
                    raise ValueError(
                        "Documento com matrícula incompatível com a pessoa selecionada. Confira ou corrija a identificação extraída."
                    )
        return self


def entradas_calculo(
    data: DadosIdentificados, *, mode: Literal["python", "json"] = "python"
):
    values = data.model_dump(mode=mode, by_alias=True, exclude_none=True)
    if isinstance(
        data, (ApuracaoPeriodosDados, ProgressaoEventosDados, AdicionaisDados)
    ):
        key = (
            "apuracao"
            if isinstance(data, ApuracaoPeriodosDados)
            else "adicionais"
            if isinstance(data, AdicionaisDados)
            else "progressao"
        )
        plan = getattr(data, key)
        for event, serialized in zip(plan.eventos, values[key]["eventos"], strict=True):
            # Null explícito remove base manual; ausência mantém a base anterior.
            serialized["alteracoes"] = event.alteracoes.model_dump(
                mode=mode, exclude_unset=True
            )
    return values


MODELOS_CALCULO: dict[str, type[DadosIdentificados]] = {
    "apuracao_periodos": ApuracaoPeriodosDados,
    "substituicao": SubstituicaoDados,
    "rescisao": RescisaoDados,
    "progressao": ProgressaoDados,
    "abono": AbonoDados,
    "insalubridade": InsalubridadeDados,
    "exercicio_anterior": ExercicioAnteriorDados,
}
