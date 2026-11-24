"""Cadastro qualificado; as tabelas anuais legadas permanecem intactas."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DDL,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EstruturaRemuneratoria(Base):
    __tablename__ = "estrutura_remuneratoria"
    __table_args__ = (
        CheckConstraint(
            "carreira IN ('TAE', 'MAGISTERIO_SUPERIOR', 'EBTT')",
            name="ck_estrutura_carreira",
        ),
        CheckConstraint(
            "(carreira = 'TAE' AND classificacao_tae IS NOT NULL AND padrao_tae IS NOT NULL AND padrao_tae > 0 "
            "AND classe_docente IS NULL AND nivel_docente IS NULL) OR "
            "(carreira <> 'TAE' AND classificacao_tae IS NULL AND capacitacao_tae IS NULL "
            "AND padrao_tae IS NULL AND classe_docente IS NOT NULL AND nivel_docente IS NOT NULL AND nivel_docente > 0)",
            name="ck_estrutura_posicao",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chave: Mapped[str] = mapped_column(String(700), nullable=False, unique=True)
    carreira: Mapped[str] = mapped_column(String(40), nullable=False)
    vinculo: Mapped[str] = mapped_column(String(60), nullable=False)
    jornada: Mapped[str] = mapped_column(String(20), nullable=False)
    versao_carreira: Mapped[str] = mapped_column(String(100), nullable=False)
    classificacao_tae: Mapped[str | None] = mapped_column(String(1))
    capacitacao_tae: Mapped[str | None] = mapped_column(String(20))
    padrao_tae: Mapped[int | None] = mapped_column(Integer)
    classe_docente: Mapped[str | None] = mapped_column(String(100))
    nivel_docente: Mapped[int | None] = mapped_column(Integer)


class ReferenciaSalarial(Base):
    __tablename__ = "referencia_salarial"
    __table_args__ = (
        Index(
            "uq_referencia_intervalo",
            "estrutura_id",
            "inicio_vigencia",
            text("COALESCE(fim_vigencia, '9999-12-31')"),
            unique=True,
        ),
        CheckConstraint(
            "fim_vigencia IS NULL OR fim_vigencia >= inicio_vigencia",
            name="ck_referencia_periodo",
        ),
        CheckConstraint(
            "vencimento_basico >= 0 AND vencimento_basico <= 1000000000000",
            name="ck_referencia_valor",
        ),
        CheckConstraint(
            "estado IN ('PENDENTE', 'CONFIRMADA', 'INATIVA')",
            name="ck_referencia_estado",
        ),
        # Dois ranges nativos evitam depender de CREATE EXTENSION btree_gist.
        # Um ponto por estrutura equivale à igualdade de seu identificador.
        ExcludeConstraint(
            (text("int8range(estrutura_id::bigint, estrutura_id::bigint, '[]')"), "&&"),
            (text("daterange(inicio_vigencia, fim_vigencia, '[]')"), "&&"),
            where=text("estado = 'CONFIRMADA'"),
            name="ex_referencia_vigencia",
        ).ddl_if(dialect="postgresql"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estrutura_id: Mapped[int] = mapped_column(
        ForeignKey("estrutura_remuneratoria.id"), nullable=False, index=True
    )
    inicio_vigencia: Mapped[date] = mapped_column(Date, nullable=False)
    fim_vigencia: Mapped[date | None] = mapped_column(Date)
    vencimento_basico: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDENTE")
    fonte: Mapped[str] = mapped_column(String(500), nullable=False)
    conferido_por: Mapped[int | None] = mapped_column(Integer)
    conferido_em: Mapped[datetime | None] = mapped_column(DateTime)
    estrutura: Mapped[EstruturaRemuneratoria] = relationship()
    retribuicoes: Mapped[list["RetribuicaoReferencia"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class RetribuicaoReferencia(Base):
    __tablename__ = "retribuicao_referencia"
    __table_args__ = (
        UniqueConstraint(
            "referencia_id", "titulacao_chave", name="uq_retribuicao_referencia"
        ),
        CheckConstraint(
            "valor >= 0 AND valor <= 1000000000000", name="ck_retribuicao_valor"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referencia_id: Mapped[int] = mapped_column(
        ForeignKey("referencia_salarial.id"), nullable=False
    )
    titulacao: Mapped[str] = mapped_column(String(100), nullable=False)
    titulacao_chave: Mapped[str] = mapped_column(String(100), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)


class PendenciaSalarialLegada(Base):
    __tablename__ = "pendencia_salarial_legada"
    __table_args__ = (
        UniqueConstraint(
            "tabela_origem", "id_origem", name="uq_pendencia_salarial_origem"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tabela_origem: Mapped[str] = mapped_column(String(60), nullable=False)
    id_origem: Mapped[int] = mapped_column(Integer, nullable=False)
    dados_originais: Mapped[str] = mapped_column(Text, nullable=False)
    valor_original: Mapped[str | None] = mapped_column(Text)
    valor_decimal: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    motivo: Mapped[str] = mapped_column(String(500), nullable=False)
    referencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("referencia_salarial.id")
    )


# SQLite serializa as escritas; a validação no banco também cobre SQL direto.
# PostgreSQL usa a exclusão GiST acima, que também protege escritas concorrentes.
for operation in ("INSERT", "UPDATE"):
    event.listen(
        ReferenciaSalarial.__table__,
        "after_create",
        DDL(f"""
        CREATE TRIGGER IF NOT EXISTS referencia_vigencia_{operation.lower()}
        BEFORE {operation} ON referencia_salarial
        WHEN NEW.estado = 'CONFIRMADA' AND EXISTS (
            SELECT 1 FROM referencia_salarial AS anterior
            WHERE anterior.estrutura_id = NEW.estrutura_id AND anterior.estado = 'CONFIRMADA'
              AND anterior.id <> COALESCE(NEW.id, -1)
              AND (NEW.fim_vigencia IS NULL OR anterior.inicio_vigencia <= NEW.fim_vigencia)
              AND (anterior.fim_vigencia IS NULL OR NEW.inicio_vigencia <= anterior.fim_vigencia)
        ) BEGIN SELECT RAISE(ABORT, 'referencia_vigencia_sobreposta'); END
    """).execute_if(dialect="sqlite"),
    )


SALARY_REFERENCE_TABLES = (
    EstruturaRemuneratoria.__table__,
    ReferenciaSalarial.__table__,
    RetribuicaoReferencia.__table__,
    PendenciaSalarialLegada.__table__,
)
