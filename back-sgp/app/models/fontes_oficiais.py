"""Prévia de fontes públicas e componentes de função; sem documentos de servidores."""

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
    event,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EstruturaFuncao(Base):
    __tablename__ = "estrutura_funcao"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chave: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tipo_funcao: Mapped[str] = mapped_column(String(3), nullable=False)
    codigo_funcao: Mapped[str] = mapped_column(String(30), nullable=False)
    modalidade: Mapped[str] = mapped_column(String(60), nullable=False)
    componente: Mapped[str] = mapped_column(String(60), nullable=False)
    __table_args__ = (
        CheckConstraint("tipo_funcao IN ('CD','FG','FCC')", name="ck_funcao_tipo"),
    )


class ReferenciaFuncao(Base):
    __tablename__ = "referencia_funcao"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estrutura_id: Mapped[int] = mapped_column(
        ForeignKey("estrutura_funcao.id"), nullable=False, index=True
    )
    inicio_vigencia: Mapped[date] = mapped_column(Date, nullable=False)
    fim_vigencia: Mapped[date | None] = mapped_column(Date)
    valor: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    fonte: Mapped[str] = mapped_column(String(500), nullable=False)
    conferido_por: Mapped[int] = mapped_column(Integer, nullable=False)
    conferido_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "fim_vigencia IS NULL OR fim_vigencia >= inicio_vigencia",
            name="ck_funcao_periodo",
        ),
        CheckConstraint(
            "valor >= 0 AND valor <= 1000000000000", name="ck_funcao_valor"
        ),
        Index(
            "uq_funcao_intervalo",
            "estrutura_id",
            "inicio_vigencia",
            text("COALESCE(fim_vigencia, '9999-12-31')"),
            unique=True,
        ),
        ExcludeConstraint(
            (text("int8range(estrutura_id::bigint, estrutura_id::bigint, '[]')"), "&&"),
            (text("daterange(inicio_vigencia, fim_vigencia, '[]')"), "&&"),
            name="ex_funcao_vigencia",
        ).ddl_if(dialect="postgresql"),
    )


class EstruturaIQ(Base):
    __tablename__ = "estrutura_iq"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chave: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    titulacao: Mapped[str] = mapped_column(String(300), nullable=False)


class ReferenciaIQ(Base):
    __tablename__ = "referencia_iq"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estrutura_id: Mapped[int] = mapped_column(ForeignKey("estrutura_iq.id"), nullable=False, index=True)
    inicio_vigencia: Mapped[date] = mapped_column(Date, nullable=False)
    fim_vigencia: Mapped[date | None] = mapped_column(Date)
    valor: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    fonte: Mapped[str] = mapped_column(String(500), nullable=False)
    conferido_por: Mapped[int] = mapped_column(Integer, nullable=False)
    conferido_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    __table_args__ = (
        CheckConstraint("fim_vigencia IS NULL OR fim_vigencia >= inicio_vigencia", name="ck_iq_periodo"),
        CheckConstraint("valor >= 0 AND valor <= 100", name="ck_iq_percentual"),
        Index("uq_iq_intervalo", "estrutura_id", "inicio_vigencia", text("COALESCE(fim_vigencia, '9999-12-31')"), unique=True),
        ExcludeConstraint(
            (text("int8range(estrutura_id::bigint, estrutura_id::bigint, '[]')"), "&&"),
            (text("daterange(inicio_vigencia, fim_vigencia, '[]')"), "&&"),
            name="ex_iq_vigencia",
        ).ddl_if(dialect="postgresql"),
    )


for operation in ("INSERT", "UPDATE"):
    event.listen(ReferenciaIQ.__table__, "after_create", DDL(f"""
        CREATE TRIGGER IF NOT EXISTS iq_vigencia_{operation.lower()}
        BEFORE {operation} ON referencia_iq
        WHEN EXISTS (
            SELECT 1 FROM referencia_iq a WHERE a.estrutura_id = NEW.estrutura_id
              AND a.id <> COALESCE(NEW.id, -1)
              AND (NEW.fim_vigencia IS NULL OR a.inicio_vigencia <= NEW.fim_vigencia)
              AND (a.fim_vigencia IS NULL OR NEW.inicio_vigencia <= a.fim_vigencia)
        ) BEGIN SELECT RAISE(ABORT, 'iq_vigencia_sobreposta'); END
    """).execute_if(dialect="sqlite"))


class ImportacaoFonte(Base):
    __tablename__ = "importacao_fonte"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    obtido_em: Mapped[date] = mapped_column(Date, nullable=False)
    publicado_em: Mapped[date | None] = mapped_column(Date)
    arquivo: Mapped[str] = mapped_column(String(200), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    formato: Mapped[str] = mapped_column(String(20), nullable=False)
    criado_por: Mapped[int] = mapped_column(Integer, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class LinhaImportacaoFonte(Base):
    __tablename__ = "linha_importacao_fonte"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lote_id: Mapped[int] = mapped_column(
        ForeignKey("importacao_fonte.id"), nullable=False, index=True
    )
    localizador: Mapped[str] = mapped_column(String(200), nullable=False)
    original_json: Mapped[str] = mapped_column(Text, nullable=False)
    dados_json: Mapped[str] = mapped_column(Text, nullable=False)
    problemas_json: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDENTE")
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revisado_por: Mapped[int | None] = mapped_column(Integer)
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime)
    referencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("referencia_salarial.id")
    )
    funcao_id: Mapped[int | None] = mapped_column(ForeignKey("referencia_funcao.id"))


for operation in ("INSERT", "UPDATE"):
    event.listen(
        ReferenciaFuncao.__table__,
        "after_create",
        DDL(f"""
        CREATE TRIGGER IF NOT EXISTS funcao_vigencia_{operation.lower()}
        BEFORE {operation} ON referencia_funcao
        WHEN EXISTS (
            SELECT 1 FROM referencia_funcao a WHERE a.estrutura_id = NEW.estrutura_id
              AND a.id <> COALESCE(NEW.id, -1)
              AND (NEW.fim_vigencia IS NULL OR a.inicio_vigencia <= NEW.fim_vigencia)
              AND (a.fim_vigencia IS NULL OR NEW.inicio_vigencia <= a.fim_vigencia)
        ) BEGIN SELECT RAISE(ABORT, 'funcao_vigencia_sobreposta'); END
    """).execute_if(dialect="sqlite"),
    )


def migrate_official_sources(engine):
    with engine.begin() as connection:
        for table in (
            EstruturaFuncao.__table__,
            ReferenciaFuncao.__table__,
            EstruturaIQ.__table__,
            ReferenciaIQ.__table__,
            ImportacaoFonte.__table__,
            LinhaImportacaoFonte.__table__,
        ):
            table.create(connection, checkfirst=True)
