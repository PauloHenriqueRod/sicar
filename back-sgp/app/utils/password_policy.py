"""Política única para cadastro, troca de senha e criação da conta inicial."""
import re


def is_strong_password(password: str) -> bool:
    if len(password) < 8 or len(password.encode("utf-8")) > 72:
        return False
    return bool(
        re.search(r"[A-Z]", password)
        and re.search(r"\d", password)
        and re.search(r"[@$!%*?&]", password)
    )
