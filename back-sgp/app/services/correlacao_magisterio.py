"""Correlação estrutural do MS efetivo. Promoções individuais exigem evento próprio."""

from datetime import date

from app.schemas.referencias_salariais import PosicaoSalarial
from app.utils.salary_keys import salary_key

INICIO_MS_2025 = date(2025, 1, 1)
REGRA_MS_2025 = {
    "identificador": "CORRELACAO-MS-2025",
    "versao": "Lei 15.141/2025, Anexo LXXVIII, item c",
    "fonte": "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/anexo/anexo1a100-lei15141.htm",
    "inicio_vigencia": INICIO_MS_2025.isoformat(),
}


def posicao_ms_2025(posicao: PosicaoSalarial) -> PosicaoSalarial | None:
    if (
        posicao.carreira != "MAGISTERIO_SUPERIOR"
        or posicao.vinculo != "EFETIVO"
        or salary_key(posicao.versao_carreira) != salary_key("MS até 2024")
    ):
        return None
    classe, nivel = (posicao.classe_docente or "").upper(), posicao.nivel_docente
    if classe in {"A", "B"} and nivel in (1, 2):
        classe, nivel = "A", 1
    elif classe in {"C", "D"} and nivel in (1, 2, 3, 4):
        classe = {"C": "B", "D": "C"}[classe]
    elif classe == "E" and nivel == 1:
        classe = "D"
    else:
        return None
    return posicao.model_copy(update={"versao_carreira": "MS desde 2025", "classe_docente": classe, "nivel_docente": nivel})
