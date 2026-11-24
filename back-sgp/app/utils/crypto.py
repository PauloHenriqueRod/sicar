import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import String, TypeDecorator
from dotenv import load_dotenv

load_dotenv()

_key = os.getenv("ENCRYPTION_KEY")
if not _key:
    raise RuntimeError("FATAL: ENCRYPTION_KEY não configurada. A aplicação não pode iniciar sem uma chave persistente.")

fernet = Fernet(_key.encode("utf-8"))

def encrypt_data(data: str) -> str:
    """Criptografa uma string usando Fernet"""
    return fernet.encrypt(data.encode("utf-8")).decode("utf-8")

def decrypt_data(encrypted_data: str) -> str:
    """Descriptografa uma string usando Fernet"""
    try:
        return fernet.decrypt(encrypted_data.encode("utf-8")).decode("utf-8")
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise DataIntegrityError("Não foi possível verificar os dados protegidos.") from exc


class DataIntegrityError(ValueError):
    """Dados ilegíveis nunca são substituídos por um resultado vazio."""


class EncryptedString(TypeDecorator):
    """Criptografia transparente após a migração dos registros legados."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_data(value) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_data(value)
