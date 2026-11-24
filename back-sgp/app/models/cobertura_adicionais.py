"""Índice opaco de parcelas já apuradas; detalhes permanecem no histórico cifrado."""

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EscopoAdicional(Base):
    __tablename__ = "escopos_adicionais"
    chave: Mapped[str] = mapped_column(String(64), primary_key=True)


class CoberturaAdicional(Base):
    __tablename__ = "coberturas_adicionais"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    escopo: Mapped[str] = mapped_column(
        ForeignKey("escopos_adicionais.chave"), index=True
    )
    inicio: Mapped[date] = mapped_column(Date)
    fim: Mapped[date] = mapped_column(Date)
    historico_id: Mapped[int] = mapped_column(
        ForeignKey("historico_calculo.id"), index=True
    )


class RevisaoCalculo(Base):
    __tablename__ = "revisoes_calculos"
    anterior_id: Mapped[int] = mapped_column(
        ForeignKey("historico_calculo.id"), primary_key=True
    )
    novo_id: Mapped[int] = mapped_column(
        ForeignKey("historico_calculo.id"), unique=True
    )
