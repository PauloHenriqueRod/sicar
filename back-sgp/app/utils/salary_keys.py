"""Chaves exatas de tabelas salariais, independentes de caixa e acentos."""
import unicodedata


def salary_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower().split())
