"""Concessões são declarações confirmadas; razões observadas não concedem direito."""

from fractions import Fraction

from app.services.pendencias import PendenciaApuracao


def concessao_ativa(state, first, last):
    item = state.adicional
    if item is None:
        raise PendenciaApuracao(
            "adicional_pendente",
            "Informe a concessão do adicional dependente deste caso.",
        )
    if item.inicio_vigencia is None:
        raise PendenciaApuracao(
            "vigencia_adicional_pendente",
            "Confirme a data inicial da concessão do adicional.",
        )
    if last < item.inicio_vigencia or (
        item.fim_vigencia is not None and first > item.fim_vigencia
    ):
        return None
    if item.especie is None or (
        item.especie == "OUTRO" and not (item.descricao or "").strip()
    ):
        raise PendenciaApuracao(
            "especie_adicional_pendente",
            "Confirme a espécie do adicional e sua identificação.",
        )
    if item.percentual is None or not item.percentual_confirmado:
        raise PendenciaApuracao(
            "percentual_adicional_pendente",
            "O percentual do adicional precisa de confirmação; uma razão observada é somente sugestão.",
        )
    if item.base is None or not item.base.confirmada or item.base.tipo is None:
        raise PendenciaApuracao(
            "base_adicional_pendente", "Confirme a base do adicional neste caso."
        )
    if (
        item.regra is None
        or not item.regra.confirmada
        or not item.regra.cobre(first)
        or not item.regra.cobre(last)
    ):
        raise PendenciaApuracao(
            "regra_adicional_pendente",
            "Confirme uma regra do adicional vigente em todos os dias do segmento.",
        )
    if item.base.tipo == "VALOR_CONFIRMADO" and item.base.valor_manual is None:
        raise PendenciaApuracao(
            "base_adicional_pendente",
            "A base manual exige valor, fonte e localizador conferidos.",
        )
    if item.base.tipo != "VALOR_CONFIRMADO" and item.base.valor_manual is not None:
        raise PendenciaApuracao(
            "base_adicional_ambigua",
            "Escolha a base por componentes ou o valor manual, sem misturá-los.",
        )
    if item.base.tipo == "VB_RT" and state.posicao.carreira == "TAE":
        raise PendenciaApuracao(
            "base_adicional_incompativel",
            "RT é componente docente; não acrescente RT a uma posição TAE.",
        )
    return item


def componentes_adicional(state, first, last):
    item = concessao_ativa(state, first, last)
    if item is None or item.base.tipo == "VALOR_CONFIRMADO":
        return set()
    return {"VB", "RT"} if item.base.tipo == "VB_RT" else {"VB"}


def mensal_adicional(state, bases, first, last):
    item = concessao_ativa(state, first, last)
    if item is None:
        return Fraction(0)
    base = (
        Fraction(item.base.valor_manual.valor)
        if item.base.tipo == "VALOR_CONFIRMADO"
        else sum(
            (bases[key] for key in componentes_adicional(state, first, last)),
            Fraction(0),
        )
    )
    return base * Fraction(item.percentual) / 100


def limites_concessao(item):
    if item is None:
        return set()
    limits = {
        value.toordinal()
        for value in (
            item.inicio_vigencia,
            item.regra.inicio_vigencia if item.regra else None,
        )
        if value is not None
    }
    limits.update(
        value.toordinal() + 1
        for value in (
            item.fim_vigencia,
            item.regra.fim_vigencia if item.regra else None,
        )
        if value is not None
    )
    return limits
