import re
from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from app.schemas.referencias_salariais import (
    PosicaoSalarial,
    RetribuicaoEntrada,
    ValorReferencia,
)
from app.utils.salary_keys import salary_key


def effect_date(value):
    if (
        value is not None
        and not isinstance(value, date)
        and (
            not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        )
    ):
        raise ValueError("Informe a data completa dos efeitos no formato AAAA-MM-DD.")
    return value


class ContratoFonte(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrigemFonte(ContratoFonte):
    titulo: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=1000)
    obtido_em: date
    publicado_em: date | None = None
    _dates = field_validator("obtido_em", "publicado_em", mode="before")(effect_date)

    @field_validator("url")
    @classmethod
    def oficial(cls, value):
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not (
                host == "ufpi.br" or host.endswith((".gov.br", ".edu.br", ".ufpi.br"))
            )
        ):
            raise ValueError(
                "Informe o endereço HTTPS da fonte oficial gov.br, edu.br ou da UFPI."
            )
        return value


class LeituraColuna(ContratoFonte):
    aba: str = Field(min_length=1, max_length=100)
    linha_inicial: int = Field(default=1, ge=1, le=1048576, strict=True)
    linha_final: int | None = Field(default=None, ge=1, le=1048576, strict=True)
    colunas: dict[str, str] = Field(default_factory=dict, max_length=30)
    contexto: dict[str, str] = Field(default_factory=dict, max_length=30)

    @model_validator(mode="after")
    def conferir_campos(self):
        if self.linha_final is not None and self.linha_final < self.linha_inicial:
            raise ValueError(
                "Intervalo de linhas inválido; inclua o cabeçalho da tabela."
            )
        allowed = set(LinhaSalarial.model_fields) | set(LinhaFuncao.model_fields) | set(LinhaIQ.model_fields)
        self.colunas = {key: value for key, value in self.colunas.items() if value}
        self.contexto = {key: value for key, value in self.contexto.items() if value}
        if (
            not (set(self.colunas) | set(self.contexto)) <= allowed
            or ("valor" not in self.colunas and self.aba not in ("PDF", "anexos_tae", "comparativo_tae_2025_2026", "comparativo_magisterio"))
            or set(self.colunas) & set(self.contexto)
        ):
            raise ValueError(
                "Mapeie a coluna de valor e use apenas campos conhecidos, sem repetir coluna e valor fixo para o mesmo campo."
            )
        if any(
            len(value) > 200
            for value in (*self.colunas.values(), *self.contexto.values())
        ):
            raise ValueError("Cabeçalho ou contexto excessivamente longo.")
        return self


class ConfiguracaoFonte(OrigemFonte):
    leituras: list[LeituraColuna] = Field(default_factory=list, max_length=30)


class LinhaSalarial(PosicaoSalarial):
    tipo: Literal["VB", "RT"]
    inicio_vigencia: date
    fim_vigencia: date | None = None
    valor: ValorReferencia
    titulacao: str | None = None

    _effect_dates = field_validator("inicio_vigencia", "fim_vigencia", mode="before")(
        effect_date
    )

    @model_validator(mode="after")
    def conferir(self):
        if self.fim_vigencia is not None and self.fim_vigencia < self.inicio_vigencia:
            raise ValueError("Fim de vigência anterior ao início.")
        if self.tipo == "RT":
            if self.carreira == "TAE":
                raise ValueError("TAE não possui RT docente.")
            RetribuicaoEntrada(titulacao=self.titulacao or "", valor=self.valor)
        elif self.titulacao:
            raise ValueError("VB não deve ter titulação; informe RT em linha separada.")
        return self


class LinhaIQ(ContratoFonte):
    tipo: Literal["IQ"]
    titulacao: str = Field(min_length=1, max_length=300)
    valor: ValorReferencia
    inicio_vigencia: date
    fim_vigencia: date | None = None

    _effect_dates = field_validator("inicio_vigencia", "fim_vigencia", mode="before")(effect_date)

    @model_validator(mode="after")
    def conferir(self):
        if self.valor > 100 or not salary_key(self.titulacao):
            raise ValueError("Informe titulação e percentual de IQ entre zero e cem.")
        if self.fim_vigencia is not None and self.fim_vigencia < self.inicio_vigencia:
            raise ValueError("Fim de vigência anterior ao início.")
        return self

    def chave_estrutura(self):
        from hashlib import sha256
        return sha256(salary_key(self.titulacao).encode()).hexdigest()


class LinhaFuncao(ContratoFonte):
    tipo: Literal["FUNCAO"]
    tipo_funcao: Literal["CD", "FG", "FCC"]
    codigo_funcao: str = Field(min_length=1, max_length=30)
    modalidade: str = Field(min_length=1, max_length=60)
    componente: str = Field(min_length=1, max_length=60)
    inicio_vigencia: date
    fim_vigencia: date | None = None
    valor: ValorReferencia

    _effect_dates = field_validator("inicio_vigencia", "fim_vigencia", mode="before")(
        effect_date
    )

    @field_validator("codigo_funcao", "modalidade", "componente")
    @classmethod
    def identificador(cls, value):
        if not salary_key(value):
            raise ValueError("Informe um identificador válido.")
        return value

    @model_validator(mode="after")
    def periodo(self):
        if self.fim_vigencia is not None and self.fim_vigencia < self.inicio_vigencia:
            raise ValueError("Fim de vigência anterior ao início.")
        return self

    def chave_estrutura(self):
        from app.utils.function_keys import function_key

        return function_key(
            self.tipo_funcao, self.codigo_funcao, self.modalidade, self.componente
        )


class EditarLinha(ContratoFonte):
    versao: int = Field(gt=0, strict=True)
    dados: dict[str, str | StrictInt | None] = Field(max_length=30)
    localizador: str = Field(min_length=1, max_length=200)

    @field_validator("dados")
    @classmethod
    def tamanho_registro(cls, value):
        allowed = set(LinhaSalarial.model_fields) | set(LinhaFuncao.model_fields) | set(LinhaIQ.model_fields)
        if not set(value) <= allowed:
            raise ValueError(
                "Use somente campos remuneratórios previstos no contrato; não inclua dados de servidores."
            )
        if any(
            len(key) > 60 or (isinstance(item, str) and len(item) > 2000)
            for key, item in value.items()
        ):
            raise ValueError("Campos da prévia excedem os limites de tamanho.")
        return value


class CadastroManual(ContratoFonte):
    origem: OrigemFonte
    linhas: list[dict[str, str | StrictInt | None]] = Field(
        min_length=1, max_length=2000
    )
    localizador: str = Field(min_length=1, max_length=200)

    @field_validator("linhas")
    @classmethod
    def tamanho_registros(cls, value):
        for record in value:
            if len(record) > 30:
                raise ValueError("Máximo de 30 campos por registro.")
            EditarLinha.tamanho_registro(record)
        return value


class SelecaoLinha(ContratoFonte):
    id: int = Field(gt=0, strict=True)
    versao: int = Field(gt=0, strict=True)


class AtivarFonte(ContratoFonte):
    linhas: list[SelecaoLinha] = Field(min_length=1, max_length=2000)
    conferido_pelo_rh: Literal[True]

    @field_validator("conferido_pelo_rh", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Confirme explicitamente a conferência do RH.")
        return value


class ConsultaCobertura(ContratoFonte):
    posicao: PosicaoSalarial
    inicio: date
    fim: date
    titulacao: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def periodo(self):
        if self.fim < self.inicio:
            raise ValueError("Período de cobertura inválido.")
        if (
            self.posicao.carreira == "TAE"
            and self.titulacao
            and salary_key(self.titulacao) != "n/a"
        ):
            raise ValueError("TAE utiliza IQ separado; esta consulta de RT é docente.")
        return self
