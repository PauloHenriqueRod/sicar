"""Adaptadores dos três layouts remuneratórios analisados; somente prévias."""

import re

from app.services.leitores_pdf.comuns import linhas, normalizar

MONEY = r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}"


def decimal(raw):
    return raw.replace(".", "").replace(",", ".")


def linha(data, page, number, reader, raw, error=None):
    return {
        "dados": data,
        "localizador": f"Página {page}, linha {number}, {reader}",
        "leitor": reader,
        "original": {
            "texto": raw[:1000],
            "pagina": page,
            "leitor": reader,
            "versao": "2",
        },
        "erro": error,
    }


def ler_iq(text, page, reader, effect=None):
    result, pending, first_line = [], [], 0

    def emit():
        if not pending:
            return
        raw = " ".join(pending)
        percentages = re.findall(r"\b(\d{1,3})\s*%", raw)
        title = re.sub(r"\s*\d+\s*%", "", raw).strip()
        if len(percentages) == 1 and len(title) <= 300:
            result.append(
                linha(
                    {
                        "tipo": "IQ",
                        "titulacao": title,
                        "valor": percentages[0],
                        **({"inicio_vigencia": effect} if effect else {}),
                    },
                    page,
                    first_line,
                    reader,
                    raw,
                )
            )
        else:
            result.append(
                linha(
                    {},
                    page,
                    first_line,
                    reader,
                    raw,
                    "Escolaridade sem percentual único; confira as colunas.",
                )
            )

    for number, raw in enumerate(text.splitlines(), 1):
        normalized = normalizar(raw).strip()
        if re.match(
            r"^(?:ENSINO|CURSO DE GRADUACAO|ESPECIALIZACAO|MESTRADO|DOUTORADO)",
            normalized,
        ):
            emit()
            pending, first_line = [raw.strip()], number
        elif pending and raw.strip() and not re.search(r"\(NR\)", normalized):
            if normalized.startswith(("ANEXO", "TABELA", "NIVEL DE", "PERCENTUAL")):
                emit()
                pending = []
            else:
                pending.append(raw.strip())
    emit()
    return result


def ler_comparativo_tae(pages):
    result = []
    for page in pages:
        text = page.get("texto_original", page["texto"])
        compact = re.sub(r"\s+", "", normalizar(text))
        category = re.search(
            r"NIVELDECLASSIFICACAO([A-E])\b|NIVELDECLASSIFICACAO([A-E])", compact
        )
        if category:
            klass = category[1] or category[2]
            dates = []
            # A ordem vem das colunas comprovadas deste layout, não de nomes de arquivo.
            for marker, iso in (
                (r"JANEIRODE2025", "2025-01-01"),
                (r"ABRILDE2026", "2026-04-01"),
            ):
                dates.append(
                    iso
                    if re.search(marker, compact)
                    and "EFEITOSFINANCEIROSAPARTIRDE1" in compact
                    else None
                )
            for number, raw in enumerate(text.splitlines(), 1):
                match = re.fullmatch(rf"\s*(\d{{1,3}})\s+({MONEY})\s+({MONEY})\s*", raw)
                if not match:
                    continue
                for position, effect in enumerate(dates):
                    result.append(
                        linha(
                            {
                                "tipo": "VB",
                                "carreira": "TAE",
                                "classificacao_tae": klass,
                                "padrao_tae": int(match[1]),
                                "valor": decimal(match[position + 2]),
                                **({"inicio_vigencia": effect} if effect else {}),
                            },
                            page["numero"],
                            number,
                            "comparativo_tae_2025_2026",
                            raw,
                        )
                    )
        elif "PERCENTUAISDEINCENTIVO" in compact:
            result.extend(ler_iq(text, page["numero"], "comparativo_tae_2025_2026"))
    return result


def ler_anexos_tae(pages):
    result, classification = [], None
    old_columns = None
    full_text = normalizar(" ".join(p.get("texto_original", p["texto"]) for p in pages))
    january = (
        "2025-01-01"
        if re.search(
            r"EFEITOS FINANCEIROS A PARTIR DE 1[º°o]? DE JANEIRO DE 2025", full_text
        )
        else None
    )
    may = (
        "2023-05-01"
        if re.search(r"1[º°o]? DE MAIO\s+(?:I II III IV\s+)?DE 2023", full_text)
        else None
    )
    for page in pages:
        text = page.get("texto_original", page["texto"])
        positioned = linhas(page.get("palavras", []))
        if "ANEXO CCXXIII" in normalizar(text):
            explicit = re.search(
                r"a partir de 1[º°o]? de janeiro de 2025", text, re.IGNORECASE
            )
            iq_section = re.split(r"ANEXO CCXXIV", text, flags=re.IGNORECASE)[0]
            result.extend(
                ler_iq(
                    iq_section,
                    page["numero"],
                    "anexos_tae",
                    "2025-01-01" if explicit else None,
                )
            )
        for number, raw in enumerate(text.splitlines(), 1):
            normalized = normalizar(raw)
            category = re.search(r"CARGOS DO NIVEL ([A-E])\s*:", normalized)
            if category:
                classification = category[1]
            if re.match(r"ANEXO CCXX[VX]", normalized) and "CCXXIV" not in normalized:
                classification = None
            match = re.fullmatch(
                rf"\s*P(\d{{2}})\s+({MONEY})\s+([\d\s]+)\s+({MONEY})\s+({MONEY})\s*",
                raw,
            )
            if not match or not classification:
                continue
            mapping = match[3].split()
            if not mapping:
                continue
            # O padrão de destino é a última coluna inteira antes dos dois VBs.
            pattern = int(mapping[-1])
            for amount, effect in ((match[4], january), (match[5], None)):
                result.append(
                    linha(
                        {
                            "tipo": "VB",
                            "carreira": "TAE",
                            "classificacao_tae": classification,
                            "padrao_tae": pattern,
                            "valor": decimal(amount),
                            **({"inicio_vigencia": effect} if effect else {}),
                        },
                        page["numero"],
                        number,
                        "anexos_tae",
                        raw,
                    )
                )
            # A situação anterior e a correspondência de capacitação são evidência
            # independente. O PDF possui cabeçalho de abril cortado: não completar ano.
            result[-2]["original"]["situacao_anterior"] = {
                "piso": match[1],
                "valor": decimal(match[2]),
                "classes_capacitacao_e_padrao": mapping,
            }
            result[-1]["original"]["efeitos_observados"] = (
                "1º de abril — ano incompleto no layout analisado; confirmar manualmente"
            )
            physical = [
                row
                for row in positioned
                if row[0]["text"] == "P" + match[1]
                and [w["text"] for w in row if re.fullmatch(MONEY, w["text"])]
                == [match[2], match[4], match[5]]
            ]
            if len(physical) == 1:
                row = physical[0]
                preceding = [
                    r
                    for r in positioned
                    if r[0]["top"] < row[0]["top"]
                    and [w["text"] for w in r if w["text"] in ("I", "II", "III", "IV")]
                    == ["I", "II", "III", "IV"]
                ]
                if preceding:
                    old_columns = {
                        w["text"]: (w["x0"] + w["x1"]) / 2
                        for w in preceding[-1]
                        if w["text"] in ("I", "II", "III", "IV")
                    }
                if old_columns:
                    for capacity, anchor in old_columns.items():
                        values = [
                            w["text"]
                            for w in row
                            if abs((w["x0"] + w["x1"]) / 2 - anchor) <= 3
                            and re.fullmatch(r"\d{1,2}", w["text"])
                        ]
                        if len(values) == 1:
                            result.append(
                                linha(
                                    {
                                        "tipo": "VB",
                                        "carreira": "TAE",
                                        "classificacao_tae": classification,
                                        "capacitacao_tae": capacity,
                                        "padrao_tae": int(values[0]),
                                        "valor": decimal(match[2]),
                                        **({"inicio_vigencia": may} if may else {}),
                                    },
                                    page["numero"],
                                    number,
                                    "anexos_tae",
                                    raw,
                                )
                            )
    return result


def ler_magisterio(pages):
    result = []
    for page in pages:
        text = page.get("texto_original", page["texto"])
        compact = re.sub(r"\s+", "", normalizar(text))
        if not all(
            marker in compact for marker in ("20H", "40H", "DE", "MAR/2026", "ABR/2026")
        ):
            continue
        header = re.split(r"(?m)^\s*[A-D]\s*[–—-]", text, maxsplit=1)[0]
        # Apenas as duas disposições analisadas, inclusive o cabeçalho quebrado.
        markers = re.findall(r"\b(?:20H|40H|DE|MAR/2026|ABR/2026)\b", normalizar(header))
        inline = ["20H", "MAR/2026", "20H", "ABR/2026", "40H", "MAR/2026", "40H", "ABR/2026", "DE", "MAR/2026", "DE", "ABR/2026"]
        wrapped = ["20H", "40H", "DE", "MAR/2026", "20H", "ABR/2026", "MAR/2026", "40H", "ABR/2026", "MAR/2026", "DE", "ABR/2026"]
        if markers not in (inline, wrapped):
            result.append(linha({}, page["numero"], 1, "comparativo_magisterio", header,
                                "Ordem dos cabeçalhos não suportada; confira manualmente."))
            continue
        for number, raw in enumerate(text.splitlines(), 1):
            match = re.match(
                r"\s*([A-D])\s*[–—-]\s*(Assistente|Adjunto|Associado|Titular)\s+(\d{1,2})\s+(.+)$",
                raw,
                re.IGNORECASE,
            )
            if not match:
                continue
            tokens = re.sub(r"R\$\s*", "", match[4]).split()
            amounts = tokens if all(re.fullmatch(MONEY, token) for token in tokens) else []
            if len(amounts) != 6:
                result.append(
                    linha(
                        {},
                        page["numero"],
                        number,
                        "comparativo_magisterio",
                        raw,
                        "Linha docente sem as seis colunas comprovadas; confira manualmente.",
                    )
                )
                continue
            for column, amount in enumerate(amounts):
                result.append(
                    linha(
                        {
                            "tipo": "VB",
                            "carreira": "MAGISTERIO_SUPERIOR",
                            "classe_docente": match[1].upper(),
                            "nivel_docente": int(match[3]),
                            "jornada": ("20H", "40H", "DE")[column // 2],
                            "valor": decimal(amount),
                            **(
                                {"inicio_vigencia": "2026-04-01"}
                                if column % 2
                                else {"fim_vigencia": "2026-03-31"}
                            ),
                        },
                        page["numero"],
                        number,
                        "comparativo_magisterio",
                        raw,
                    )
                )
                result[-1]["original"]["denominacao_classe"] = match[2]
    return result


def ler_tabelas(pages):
    all_text = normalizar("\n".join(p.get("texto_original", p["texto"]) for p in pages))
    compact = re.sub(r"\s+", "", all_text)
    if "ANEXOCCXXIV" in compact and "LEI" in compact and "11.091" in compact:
        result = ler_anexos_tae(pages)
    elif (
        "NIVELDECLASSIFICACAO" in compact
        and "EFEITOSFINANCEIROS" in compact
        and "JANEIRODE2025" in compact
    ):
        result = ler_comparativo_tae(pages)
    elif "MAGISTERIOSUPERIOR" in compact and "VENCIMENTOBASICO" in compact:
        result = ler_magisterio(pages)
    else:
        result = []
    if len(result) > 2000:
        raise ValueError("Divida a fonte: excesso de registros.")
    return result or [
        {
            "dados": {},
            "localizador": "Arquivo PDF",
            "erro": "Layout salarial não suportado ou sem texto utilizável; use cadastro manual ou fonte estruturada equivalente.",
        }
    ]
