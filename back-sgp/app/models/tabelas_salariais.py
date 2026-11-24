from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Index, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.clock import utcnow
from app.utils.crypto import EncryptedString
from app.utils.salary_keys import salary_key

if TYPE_CHECKING:
    from app.models.user import User


class TabelaVencimentoBasico(Base):
    __tablename__ = "tabela_vencimento_basico"
    __table_args__ = (Index("uq_vencimento_vigencia", "classe_chave", "nivel", "ano", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    classe: Mapped[str] = mapped_column(String, index=True, nullable=True)
    classe_chave: Mapped[str] = mapped_column(String, nullable=False)
    nivel: Mapped[int] = mapped_column(Integer, index=True, nullable=True)
    ano: Mapped[int] = mapped_column(Integer, index=True, default=2024, nullable=True)
    valor: Mapped[float] = mapped_column(Float, nullable=True)

class TabelaRetribuicaoTitulacao(Base):
    __tablename__ = "tabela_retribuicao_titulacao"
    __table_args__ = (Index("uq_titulacao_vigencia", "classe_chave", "nivel", "titulacao_chave", "ano", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    classe: Mapped[str] = mapped_column(String, index=True, nullable=True)
    classe_chave: Mapped[str] = mapped_column(String, nullable=False)
    nivel: Mapped[int] = mapped_column(Integer, index=True, nullable=True)
    titulacao: Mapped[str] = mapped_column(String, index=True, nullable=True)
    titulacao_chave: Mapped[str] = mapped_column(String, nullable=False)
    ano: Mapped[int] = mapped_column(Integer, index=True, default=2024, nullable=True)
    valor: Mapped[float] = mapped_column(Float, nullable=True)

class HistoricoCalculo(Base):
    __tablename__ = "historico_calculo"
    __table_args__ = (Index("uq_historico_requisicao", "user_id", "idempotency_key", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    data_calculo: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=True)
    tipo_calculo: Mapped[str] = mapped_column(String, nullable=True)
    matricula: Mapped[str] = mapped_column(EncryptedString(), nullable=True)
    classe: Mapped[str] = mapped_column(EncryptedString(), nullable=True)
    nivel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    titulacao: Mapped[str] = mapped_column(EncryptedString(), nullable=True)
    resultado_json: Mapped[str] = mapped_column(String, nullable=True) # Guarda o espelho do cálculo

    user: Mapped["User | None"] = relationship("User")


@event.listens_for(TabelaVencimentoBasico, "before_insert")
@event.listens_for(TabelaVencimentoBasico, "before_update")
@event.listens_for(TabelaRetribuicaoTitulacao, "before_insert")
@event.listens_for(TabelaRetribuicaoTitulacao, "before_update")
def set_salary_keys(mapper, connection, target):
    target.classe_chave = salary_key(target.classe or "")
    if isinstance(target, TabelaRetribuicaoTitulacao):
        target.titulacao_chave = salary_key(target.titulacao or "")
