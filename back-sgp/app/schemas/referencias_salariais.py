import json
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.utils.salary_keys import salary_key


def decimal_cadastro(value: object) -> Decimal:
    # Texto decimal também é aceito neste cadastro para preservar Numeric na UI.
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise ValueError("Informe um valor decimal.")  # noqa: TRY004
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Informe um valor decimal válido.") from exc


ValorReferencia = Annotated[
    Decimal,
    BeforeValidator(decimal_cadastro),
    Field(
        ge=0,
        le=Decimal("1e12"),
        allow_inf_nan=False,
        max_digits=30,
        decimal_places=12,
    ),
]


class PosicaoSalarial(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    carreira: Literal["TAE", "MAGISTERIO_SUPERIOR", "EBTT"]
    vinculo: str = Field(min_length=1, max_length=60)
    jornada: str = Field(min_length=1, max_length=20, pattern=r"^(?:[1-9][0-9]?H|DE)$")
    versao_carreira: str = Field(min_length=1, max_length=100)
    classificacao_tae: Literal["A", "B", "C", "D", "E"] | None = None
    capacitacao_tae: str | None = Field(default=None, min_length=1, max_length=20)
    padrao_tae: int | None = Field(default=None, gt=0, le=1000, strict=True)
    classe_docente: str | None = Field(default=None, min_length=1, max_length=100)
    nivel_docente: int | None = Field(default=None, gt=0, le=1000, strict=True)

    @field_validator(
        "carreira", "vinculo", "jornada", "classificacao_tae", mode="before"
    )
    @classmethod
    def normalizar_codigos(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("versao_carreira", "vinculo", "classe_docente", "capacitacao_tae")
    @classmethod
    def validar_identificador(cls, value):
        if value is not None and (not salary_key(value) or "%" in value):
            raise ValueError("Informe um identificador válido.")
        return value

    @model_validator(mode="after")
    def validar_posicao(self):
        if self.carreira == "TAE":
            if (
                not self.classificacao_tae
                or self.padrao_tae is None
                or self.classe_docente is not None
                or self.nivel_docente is not None
            ):
                raise ValueError(
                    "Para TAE, informe classificação e padrão, sem classe/nível docente."
                )
            if self.jornada == "DE":
                raise ValueError("O regime DE não é uma jornada TAE.")
        elif (
            self.classificacao_tae is not None
            or self.capacitacao_tae is not None
            or self.padrao_tae is not None
            or not self.classe_docente
            or self.nivel_docente is None
        ):
            raise ValueError(
                "Para docentes, informe classe e nível, sem classificação/capacitação/padrão TAE."
            )
        return self

    def chave_estrutura(self) -> str:
        canonical = json.dumps(
            [
                self.carreira,
                salary_key(self.vinculo),
                self.jornada,
                salary_key(self.versao_carreira),
                self.classificacao_tae,
                salary_key(self.capacitacao_tae or ""),
                self.padrao_tae,
                salary_key(self.classe_docente or ""),
                self.nivel_docente,
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return sha256(canonical.encode("utf-8")).hexdigest()


class ConsultaSalarial(PosicaoSalarial):
    data_referencia: date


class RetribuicaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    titulacao: str = Field(min_length=1, max_length=100)
    valor: ValorReferencia

    @field_validator("titulacao")
    @classmethod
    def validar_titulacao(cls, value):
        if (
            not salary_key(value)
            or "%" in value
            or salary_key(value) == salary_key("N/A")
        ):
            raise ValueError("Informe a titulação correspondente ao valor da RT.")
        return value


class ReferenciaEntrada(PosicaoSalarial):
    inicio_vigencia: date
    fim_vigencia: date | None = None
    vencimento_basico: ValorReferencia
    retribuicoes: list[RetribuicaoEntrada] = Field(default_factory=list, max_length=20)
    fonte: str = Field(min_length=1, max_length=500)
    estado: Literal["PENDENTE", "CONFIRMADA", "INATIVA"] = "PENDENTE"

    @model_validator(mode="after")
    def validar_referencia(self):
        if self.fim_vigencia is not None and self.fim_vigencia < self.inicio_vigencia:
            raise ValueError("O fim da vigência não pode anteceder o início.")
        chaves = [salary_key(rt.titulacao) for rt in self.retribuicoes]
        if len(chaves) != len(set(chaves)):
            raise ValueError("Há titulações duplicadas nesta referência.")
        if self.carreira == "TAE" and self.retribuicoes:
            raise ValueError(
                "RT docente não se aplica à referência TAE; IQ é parâmetro do cálculo."
            )
        return self


class VincularLegado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    referencia_id: int = Field(gt=0, strict=True)
