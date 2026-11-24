"""Horário UTC compatível com as colunas existentes sem fuso no banco."""
from datetime import UTC, datetime


def utcnow() -> datetime:
    # As colunas DateTime existentes armazenam UTC sem tzinfo. Remover apenas
    # o marcador preserva esse contrato, sem converter para o fuso da máquina.
    return datetime.now(UTC).replace(tzinfo=None)
