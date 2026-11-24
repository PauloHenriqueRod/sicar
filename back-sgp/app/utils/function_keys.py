"""Identidade de componente de função compartilhada por cadastro e cálculo."""

from hashlib import sha256

from app.utils.salary_keys import salary_key


def function_key(tipo, codigo, modalidade, componente):
    return sha256(
        "\x1f".join(
            salary_key(str(value)) for value in (tipo, codigo, modalidade, componente)
        ).encode()
    ).hexdigest()
