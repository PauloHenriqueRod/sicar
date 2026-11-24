"""Normalização para conferência; a matrícula original permanece no histórico."""


def employee_key(value):
    text = str(value).strip().casefold()
    return str(int(text)) if text.isascii() and text.isdigit() else text
