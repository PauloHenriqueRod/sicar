"""Seletores dos dispositivos oficiais analisados, sem interpretação genérica."""

import re

LEITORES = {
    "TAE": "portaria_tae_anexo",
    "PROGRESSAO": "portaria_docente_progressao",
    "TITULACAO": "portaria_docente_titulacao",
    "SUBSTITUICAO": "ato_substituicao",
}


def reconhecer_dispositivo(title, body):
    patterns = {
        "TAE": r"Conceder progressao funcional por\s+MERITO PROFISSIONAL",
        "PROGRESSAO": r"Autorizar a progressao funcional(?:\s+RETROATIVA)?\s*,\s*por desempenho academico",
        "TITULACAO": r"Conceder incentivo funcional correspondente ao nivel de",
    }
    matches = [
        kind
        for kind, pattern in patterns.items()
        if re.search(pattern, body, re.IGNORECASE)
    ]
    if title.strip().upper().startswith("ATO") and re.search(
        r"Designar\s+.+?para\s+responder\s*pela\s*Funcao\s*Gratificada",
        " ".join(body.split()),
        re.IGNORECASE,
    ):
        matches.append("SUBSTITUICAO")
    return matches[0] if len(matches) == 1 else None
