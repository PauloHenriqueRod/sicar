"""Observações documentais, separadas das regras de concessão e cálculo."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.apuracao_periodos import ContratoPeriodo


class CorrecaoRubrica(ContratoPeriodo):
    valor: str = Field(pattern=r"^-?[0-9]{1,12}(?:\.[0-9]{1,2})?$")
    justificativa: str = Field(min_length=1, max_length=500, pattern=r"\S")


class CampoExtraido(ContratoPeriodo):
    id: str = Field(min_length=1, max_length=100)
    bloco_id: str = Field(min_length=1, max_length=100)
    campo: str = Field(min_length=1, max_length=80)
    valor: str | None = Field(default=None, max_length=300)
    observado: str | None = Field(default=None, max_length=300)
    correcao: CorrecaoRubrica | None = Field(default=None, exclude_if=lambda v: v is None)
    estado: Literal["EXTRAIDO", "AUSENTE", "AMBIGUO", "ILEGIVEL"]
    pagina: int | None = Field(default=None, ge=1, le=100)
    localizador: str = Field(max_length=200)
    paginas_analisadas: list[int] = Field(default_factory=list, max_length=100)
    competencia: str | None = Field(
        default=None, pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$"
    )
    rubrica: str | None = Field(default=None, pattern=r"^[0-9]{5,8}$")
    natureza: Literal["R", "D"] | None = None
    sequencia: str | None = Field(default=None, max_length=100)
    inicio: str | None = Field(default=None, max_length=10)
    fim: str | None = Field(default=None, max_length=10)
    fim_informado: str | None = Field(default=None, max_length=10)
    fim_calculado: str | None = Field(default=None, max_length=10)
    dias_informados: str | None = Field(default=None, max_length=40)
    descricao_rubrica: str | None = Field(default=None, exclude_if=lambda value: value is None, max_length=300)
    natureza_origem: Literal["EXPLICITA", "GRUPO"] | None = Field(default=None, exclude_if=lambda value: value is None)
    leitor_id: str | None = Field(default=None, exclude_if=lambda value: value is None, max_length=80)
    leitor_versao: str | None = Field(default=None, exclude_if=lambda value: value is None, max_length=30)
    parcela: str | None = Field(default=None, exclude_if=lambda value: value is None, max_length=30)
    cancelada: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    continuacao: bool | None = Field(default=None, exclude_if=lambda value: value is None)
    data_interrupcao: str | None = Field(default=None, exclude_if=lambda value: value is None, max_length=10)
    reinicio: str | None = Field(default=None, exclude_if=lambda value: value is None, max_length=10)
    dias_restantes: str | None = Field(default=None, exclude_if=lambda value: value is None, max_length=40)
    sugestao: bool = Field(default=False, exclude_if=lambda value: not value)
    fontes_campo_ids: list[str] = Field(default_factory=list, max_length=10, exclude_if=lambda value: not value)
    ano_referencia: int | None = Field(default=None, ge=1, le=9999, exclude_if=lambda value: value is None)
    candidatos: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("candidatos")
    @classmethod
    def limitar_candidatos(cls, values):
        if any(len(value) > 300 for value in values):
            raise ValueError("Candidato documental excessivamente longo.")
        return values

    @model_validator(mode="after")
    def evidencia(self):
        if self.correcao and (self.campo != "rubrica" or not self.competencia or not self.pagina):
            raise ValueError("A correção mensal exige uma rubrica com competência e página identificadas.")
        if self.estado == "EXTRAIDO" and (self.valor is None or self.pagina is None):
            raise ValueError("Valor extraído exige página e valor explícitos.")
        if self.estado == "AUSENTE" and (
            self.valor is not None or self.pagina is not None
        ):
            raise ValueError("Ausência não pode inventar valor ou página de origem.")
        return self


class BlocoIdentificado(ContratoPeriodo):
    id: str = Field(min_length=1, max_length=100)
    matricula: str | None = Field(default=None, max_length=100)
    nome: str | None = Field(default=None, max_length=300)
    vinculo: str | None = Field(default=None, max_length=100)
    categoria: Literal["TAE", "DOCENTE", "SUBSTITUTO", "NAO_IDENTIFICADA"] = (
        "NAO_IDENTIFICADA"
    )
    paginas: list[int] = Field(max_length=100)
    papel_documental: Literal["SERVIDOR", "SUBSTITUTO", "TITULAR"] | None = None


class LeitorExecutado(ContratoPeriodo):
    identificador: str = Field(min_length=1, max_length=80)
    versao: str = Field(min_length=1, max_length=30)
    paginas: list[int] = Field(min_length=1, max_length=100)


class ArquivoExtracao(ContratoPeriodo):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    categoria: Literal["financeira", "cadastro", "ferias", "ato", "ata", "reflexos", "outros", "afastamento", "opcao", "contrato", "pagamentos"]


class DocumentoExtraido(ContratoPeriodo):
    id: str = Field(min_length=1, max_length=100)
    nome_arquivo: str = Field(default="", max_length=200)
    impressao: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    layout: Literal[
        "FICHA_SIAPE",
        "CADASTRO_FUNCIONAL",
        "CACOFERIAS",
        "MISTO",
        "NAO_SUPORTADO",
        "ATO_UFPI_SUBSTITUICAO",
        "PORTARIA_UFPI_DOCENTE",
        "PORTARIA_UFPI_TAE",
    ]
    versao_leitor: Literal[
        "rh_paginas_v1", "rh_paginas_v2", "rh_paginas_v3", "rh_paginas_v4", "rh_paginas_v5"
    ] = "rh_paginas_v5"
    leitores: list[LeitorExecutado] = Field(default_factory=list, max_length=100, exclude_if=lambda value: not value)
    arquivo_id: str | None = Field(default=None, exclude_if=lambda value: value is None, min_length=1, max_length=100)
    categoria_informada: str | None = Field(default=None, exclude_if=lambda value: value is None, max_length=40)
    situacao: Literal["CONCLUIDO", "PARCIAL", "SEM_TEXTO", "NAO_SUPORTADO"]
    total_paginas: int = Field(ge=1, le=100)
    blocos: list[BlocoIdentificado] = Field(max_length=100)
    campos: list[CampoExtraido] = Field(max_length=2000)
    avisos: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def referencias(self):
        if any(not 1 <= page <= self.total_paginas for reader in self.leitores for page in reader.paginas):
            raise ValueError("Página do leitor fora do documento.")
        blocks = {block.id: block for block in self.blocos}
        fields_by_id = {field.id: field for field in self.campos}
        if len(blocks) != len(self.blocos) or len(
            {field.id for field in self.campos}
        ) != len(self.campos):
            raise ValueError("Identificador documental repetido.")
        for block in self.blocos:
            if not block.paginas or any(
                not 1 <= page <= self.total_paginas for page in block.paginas
            ):
                raise ValueError("Páginas do bloco fora do documento.")
        for field in self.campos:
            block = blocks.get(field.bloco_id)
            if (
                block is None
                or (field.pagina is not None and field.pagina not in block.paginas)
                or any(page not in block.paginas for page in field.paginas_analisadas)
            ):
                raise ValueError("Campo sem bloco ou página de origem válida.")
            if any(source not in fields_by_id or source == field.id or fields_by_id[source].bloco_id != field.bloco_id for source in field.fontes_campo_ids):
                raise ValueError("Sugestão sem campos de origem válidos.")
        return self


class AssociacaoDocumento(ContratoPeriodo):
    documento_id: str = Field(max_length=100)
    bloco_id: str = Field(max_length=100)
    pessoa: Literal["SERVIDOR", "TITULAR", "DESCARTADO"]
    matricula: str = Field(default="", max_length=100)
    vinculo: str = Field(default="", max_length=100)
    justificativa: str = Field(default="", max_length=500)
    confirmado: bool = Field(default=False, strict=True)


class AplicacaoCampo(ContratoPeriodo):
    documento_id: str = Field(max_length=100)
    campo_id: str = Field(max_length=100)
    destino: list[str | int] = Field(min_length=1, max_length=12)
    valor_revisado: str = Field(max_length=300)
    justificativa: str = Field(default="", max_length=500)
    registro_id: str | None = Field(default=None, max_length=100)
    valor_anterior: str | None = Field(default=None, max_length=300)

    @field_validator("destino", mode="before")
    @classmethod
    def caminho(cls, value):
        if not isinstance(value, list) or any(
            isinstance(key, bool)
            or not isinstance(key, (str, int))
            or (isinstance(key, int) and not 0 <= key <= 2000)
            or (isinstance(key, str) and not 1 <= len(key) <= 100)
            for key in value
        ):
            raise ValueError("Caminho de destino inválido.")
        return value


class RevisaoExtracao(ContratoPeriodo):
    historico_aplicacoes: list[AplicacaoCampo] = Field(
        default_factory=list, max_length=1000
    )
    documentos: list[DocumentoExtraido] = Field(max_length=10)
    associacoes: list[AssociacaoDocumento] = Field(max_length=100)
    aplicacoes: list[AplicacaoCampo] = Field(default_factory=list, max_length=1000)
    vinculo_calculo: str = Field(min_length=1, max_length=100)
    vinculo_titular: str = Field(default="", max_length=100)
    confirmado: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def identidades(self):
        for application in self.historico_aplicacoes:
            doc = next(
                (doc for doc in self.documentos if doc.id == application.documento_id),
                None,
            )
            if doc is None or not any(
                field.id == application.campo_id for field in doc.campos
            ):
                raise ValueError("Histórico de aplicação sem fonte documental válida.")
        if len({doc.id for doc in self.documentos}) != len(self.documentos):
            raise ValueError("Documento repetido na revisão.")
        keys = [(item.documento_id, item.bloco_id) for item in self.associacoes]
        if len(keys) != len(set(keys)):
            raise ValueError("Associação repetida.")
        return self
