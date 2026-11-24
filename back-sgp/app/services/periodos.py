"""Operações de calendário sem enumerar dias nem sobrepor limites inclusivos."""

import calendar
from datetime import date
from itertools import pairwise


def limites_mensais(inicio: date, fim: date) -> set[int]:
    """Ordinais usam intervalo interno [início, fim+1), inclusive em date.max."""
    limits = {inicio.toordinal(), fim.toordinal() + 1}
    year, month = inicio.year, inicio.month
    while (year, month) <= (fim.year, fim.month):
        ordinal = date(year, month, 1).toordinal()
        if inicio.toordinal() < ordinal <= fim.toordinal():
            limits.add(ordinal)
        if (year, month) == (9999, 12):
            break
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return limits


def dividir_intervalo(inicio: date, fim: date, limites: set[int]):
    points = sorted(
        limites_mensais(inicio, fim)
        | {value for value in limites if inicio.toordinal() < value <= fim.toordinal()}
    )
    for left, right in pairwise(points):
        first, last = date.fromordinal(left), date.fromordinal(right - 1)
        yield first, last, right - left, calendar.monthrange(first.year, first.month)[1]
