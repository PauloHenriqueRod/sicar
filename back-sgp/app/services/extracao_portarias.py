"""Leitores de atos UFPI examinados; nenhum ato confirma direito ou regra.

Fontes e limites: docs/extracao-atos-portarias.md. Só texto nativo, sem OCR.
"""

import re
import unicodedata
from datetime import date
from uuid import uuid4

from app.schemas.extracao_documentos import DocumentoExtraido

TITLE = re.compile(
    r"^\s*(?:PORTARIA\s+N[.º°O\s]*\d+\s*/\s*\d{4}\s*-\s*SRH\b"
    r"|ATO\s+DA\s+REITORIA\s+N[.º°O\s]*\d+\s*/\s*\d{2,4}\b)",
    re.IGNORECASE | re.MULTILINE,
)
DATE = r"\d{2}[./]\d{2}[./]\d{4}"
MONTHS = [
    "janeiro",
    "fevereiro",
    "marco",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]
DATE_LONG = r"\d{1,2}\s+de\s+\w+\s+de\s+\d{4}"
COMMON = ("matricula", "nome", "vinculo", "data_documento", "data_publicacao")
ANNEX_TITLE = re.compile(
    r"^[ \t]*ANEXO\b[^\r\n]*\bPORTARIA\b[^\r\n]*",
    re.IGNORECASE | re.MULTILINE,
)


def referencia_portaria(text):
    matches = re.findall(
        r"\bPORTARIA\s+N[.º°O\s]*(\d+)\s*/\s*(\d{4})(?!\d)(?:[ \t]*-[ \t]*([A-Z][A-Z0-9]*))?",
        text,
        re.IGNORECASE,
    )
    if len(matches) == 1:
        number, year, issuer = matches[0]
        return int(number), int(year), issuer.upper() if issuer else None
    return None


def normalized(text):
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def documentary_date(value):
    try:
        if re.fullmatch(DATE, value):
            day, month, year = re.split(r"[./]", value)
        else:
            day, name, year = re.split(r"\s+de\s+", normalized(value).lower())
            month = MONTHS.index(name) + 1
        return date(int(year), int(month), int(day)).isoformat()
    except (ValueError, TypeError):
        return None


def linhas_anexo_tae(words):
    """Reconstitui nomes multilinha apenas entre colunas comprovadas do anexo TAE."""
    rows = []
    for word in sorted(words, key=lambda w: (round(w["top"] / 3), w["x0"])):
        if not rows or abs(rows[-1][0]["top"] - word["top"]) > 3:
            rows.append([])
        rows[-1].append(word)
    anchors = []
    for row in rows:
        codes = [
            i for i, w in enumerate(row) if re.fullmatch(r"[A-E]-\d{3}", w["text"])
        ]
        if len(codes) != 2 or codes[0] < 2 or codes[1] + 1 >= len(row):
            continue
        first, second = codes
        if not (
            re.fullmatch(r"\d{5,10}", row[0]["text"])
            and re.fullmatch(r"\d{3}", row[first - 1]["text"])
            and re.fullmatch(DATE, row[second + 1]["text"])
        ):
            continue
        anchors.append((row, first, second))
    identity_rows = [row for row in rows if re.fullmatch(r"\d{5,10}", row[0]["text"])]
    identity_indexes = {id(row): index for index, row in enumerate(identity_rows)}
    result = []
    for row, first, second in anchors:
        index = identity_indexes[id(row)]
        y = row[0]["top"]
        # Incomplete identity rows delimit their own region too.
        lower = (identity_rows[index - 1][0]["top"] + y) / 2 if index else y - 18
        upper = (
            (identity_rows[index + 1][0]["top"] + y) / 2
            if index + 1 < len(identity_rows)
            else y + 18
        )
        left, right = row[0]["x1"] + 2, row[first - 1]["x0"] - 2
        uncertain_boundary = any(
            left <= w["x0"]
            and w["x1"] <= right
            and (abs(w["top"] - lower) <= 0.5 or abs(w["top"] - upper) <= 0.5)
            for r in rows
            for w in r
        )
        names = [
            w
            for r in rows
            for w in r
            if lower < w["top"] < upper and left <= w["x0"] and w["x1"] <= right
        ]
        name = (
            ""
            if uncertain_boundary
            else " ".join(
                w["text"]
                for w in sorted(names, key=lambda w: (round(w["top"] / 3), w["x0"]))
            )
        )
        result.append(
            " ".join(
                [
                    row[0]["text"],
                    name,
                    row[first - 1]["text"],
                    row[first]["text"],
                    row[second]["text"],
                    row[second + 1]["text"],
                ]
            )
        )
    resolved_rows = {id(row) for row, _, _ in anchors}
    for row in rows:
        if id(row) not in resolved_rows and re.fullmatch(r"\d{5,10}", row[0]["text"]):
            # Keep unresolved entries visible to the parser's rejection diagnostic.
            result.append(" ".join(word["text"] for word in row))
    return result


def extrair_atos(pages):
    """Retorna documento e páginas consumidas; demais páginas seguem ao leitor comum."""
    from app.services.leitores_pdf.portarias import LEITORES, reconhecer_dispositivo

    fields, blocks, layouts, warnings, consumed = [], [], set(), [], set()
    reader_pages = {}
    metadata = None

    def block(page, role="SERVIDOR", category="NAO_IDENTIFICADA"):
        item = {
            "id": str(uuid4()),
            "paginas": [page],
            "categoria": category,
            "papel_documental": role,
            "matricula": None,
            "nome": None,
            "vinculo": None,
        }
        blocks.append(item)
        return item

    def add(item, key, values, page, locator, date_value=False):
        # Candidates stay visible, while ambiguous/invalid values remain empty.
        candidates = list(
            dict.fromkeys(str(v).strip() for v in values if str(v).strip())
        )
        if len(candidates) > 10:
            warnings.append(
                f"Página {page}: excesso de candidatos; confira o campo {key} manualmente."
            )
        raw = candidates[:10]
        converted = [documentary_date(v) if date_value else v for v in raw]
        state = (
            "AUSENTE"
            if not raw
            else "AMBIGUO"
            if len(set(converted)) > 1 or len(candidates) > 10
            else "ILEGIVEL"
            if None in converted
            else "EXTRAIDO"
        )
        value = converted[0] if state == "EXTRAIDO" else None
        fields.append(
            {
                "id": str(uuid4()),
                "leitor_id": LEITORES.get((metadata or {}).get("tipo"), "portaria_nao_suportada"),
                "leitor_versao": "2",
                "bloco_id": item["id"],
                "campo": key,
                "valor": value,
                "observado": " | ".join(raw)[:300] or None,
                "estado": state,
                "pagina": page if raw else None,
                "localizador": locator,
                "paginas_analisadas": [page],
                "candidatos": raw if state != "EXTRAIDO" else [],
            }
        )
        if key in ("nome", "matricula"):
            item[key] = value

    def common(item, meta):
        if meta["pagina"] not in item["paginas"]:
            item["paginas"].append(meta["pagina"])
        for key, raw in meta["campos"].items():
            add(
                item,
                key,
                raw,
                meta["pagina"],
                "Cabeçalho/data do próprio ato",
                key.startswith("data_"),
            )

    def finish(item, required):
        present = {f["campo"] for f in fields if f["bloco_id"] == item["id"]}
        for key in (*COMMON, *required):
            if key not in present:
                add(
                    item,
                    key,
                    [],
                    item["paginas"][0],
                    "Não encontrado nas páginas analisadas",
                )

    def reject_annex(page, headers):
        consumed.add(page)
        item = block(page, role=None)
        add(
            item,
            "identificador_ato",
            headers,
            page,
            "Cabeçalho do anexo sem dispositivo correspondente",
        )
        finish(item, ("posicao_destino", "efeitos_financeiros"))
        warnings.append(
            f"Página {page}: identificação do anexo divergente ou sem dispositivo correspondente; não foram herdadas datas nem efeitos. Complete manualmente."
        )

    for page in pages:
        number = page["numero"]
        text = page.get("texto_original", page["texto"])
        plain = normalized(text)
        titles = list(TITLE.finditer(text))
        annex_headers = ANNEX_TITLE.findall(plain)
        if titles:
            metadata = None
        official = "UNIVERSIDADE FEDERAL DO PIAUI" in " ".join(plain.upper().split())
        unknown_title = not titles and re.search(
            r"^\s*(?:PORTARIA\b|ATO DA REITORIA\b)", plain, re.IGNORECASE | re.MULTILINE
        )
        if unknown_title:
            consumed.add(number)
            metadata = None
            warnings.append(
                f"Página {number}: cabeçalho de ato fora dos formatos analisados; preencha manualmente."
            )
            continue
        if not titles and not metadata:
            if annex_headers:
                reject_annex(number, annex_headers)
            continue
        if not titles and re.search(
            r"Ficha Financeira|CARGO/EMPREGO|CACOFERIAS", plain, re.IGNORECASE
        ):
            metadata = None
            continue
        consumed.add(number)
        # Multiple acts on one page and retifications need a dedicated reader.
        if (
            len(titles) > 1
            or (titles and not official)
            or re.search(
                r"\b(?:RETIFICAR|RETIFICA|TORNAR SEM EFEITO|ONDE SE LE)\b",
                plain,
                re.IGNORECASE,
            )
        ):
            warnings.append(
                f"Página {number}: ato/retificação fora dos layouts suportados; preencha manualmente."
            )
            metadata = None
            continue
        if titles:
            title = titles[0]
            start = re.search(r"\bRESOLVE\s*:", text[title.end() :], re.IGNORECASE)
            if not start:
                warnings.append(
                    f"Página {number}: ato sem dispositivo delimitado; revisão manual."
                )
                continue
            offset = title.end() + start.end()
            original_body = text[offset:]
            body = normalized(original_body)
            # Signatures and legal preambles never identify the beneficiary.
            stop = re.search(
                r"\(Assinado digitalmente|Para verificar a autenticidade",
                original_body,
                re.IGNORECASE,
            )
            if stop:
                original_body = original_body[: stop.start()]
                body = normalized(original_body)
            city_dates = re.findall(
                rf"^\s*Teresina(?:-PI)?\s*,\s*({DATE_LONG})\.?\s*$",
                plain,
                re.IGNORECASE | re.MULTILINE,
            )
            metadata = {
                "pagina": number,
                "referencia": referencia_portaria(text[title.start() : title.end()]),
                "campos": {
                    "identificador_ato": [text[title.start() : title.end()]],
                    "data_documento": city_dates,
                    "data_publicacao": [],
                },
            }
            selected = reconhecer_dispositivo(text[title.start():title.end()], body)
            if selected:
                metadata["tipo"] = selected
                if selected == "TAE":
                    metadata["efeitos_tabela"] = bool(re.search(
                        r"efeitos financeiros\s+retroagem as respectivas datas",
                        " ".join(body.split()), re.IGNORECASE,
                    ))
            else:
                warnings.append(
                    f"Página {number}: portaria/ato sem leitor para este dispositivo; preenchimento manual disponível."
                )
                metadata = None
                continue
        else:
            # Only the analysed TAE annex can continue without a new act header.
            if metadata["tipo"] != "TAE":
                warnings.append(
                    f"Página {number}: continuação não suportada; confira manualmente."
                )
                metadata = None
                continue
            body, original_body = plain, text
        kind = metadata["tipo"]
        reader_pages.setdefault(LEITORES[kind], set()).add(number)
        if annex_headers and (
            kind != "TAE"
            or metadata["referencia"] is None
            or any(
                referencia_portaria(header) is None
                or referencia_portaria(header)[:2] != metadata["referencia"][:2]
                or referencia_portaria(header)[2]
                not in (None, metadata["referencia"][2])
                for header in annex_headers
            )
        ):
            reject_annex(number, annex_headers)
            metadata = None
            continue
        if kind == "TAE":
            layouts.add("PORTARIA_UFPI_TAE")
            # Exact row: matrícula, nome, cargo(3), origem, destino and respective date.
            rows = page.get("linhas_tae") or text.splitlines()
            found = 0
            for line in rows:
                match = re.fullmatch(
                    rf"\s*(\d{{5,10}})\s+(.+?)\s+(\d{{3}})\s+([A-E]-\d{{3}})\s+([A-E]-\d{{3}})\s+({DATE})\s*",
                    line,
                )
                if not match:
                    if re.match(r"\s*\d{5,10}\s", line):
                        warnings.append(
                            f"Página {number}: linha do anexo não resolvida; complete manualmente."
                        )
                    continue
                found += 1
                item = block(number, category="TAE")
                common(item, metadata)
                mat, name, cargo, source, target, effect = match.groups()
                for key, raw in (
                    ("matricula", mat),
                    ("nome", name),
                    ("codigo_cargo", cargo),
                    ("posicao_origem", source),
                    ("posicao_destino", target),
                ):
                    add(
                        item,
                        key,
                        [raw],
                        number,
                        "Anexo TAE: linha identificada pela matrícula",
                    )
                add(
                    item,
                    "efeitos_financeiros",
                    [effect] if metadata["efeitos_tabela"] else [],
                    number,
                    "Anexo TAE: data vinculada aos efeitos pelo dispositivo",
                    True,
                )
                finish(item, ("posicao_destino", "efeitos_financeiros"))
            if not found:
                warnings.append(
                    f"Página {number}: anexo TAE sem linhas resolvidas; preencha manualmente."
                )
            continue
        if (
            kind == "SUBSTITUICAO"
            and len(re.findall(r"\bDesignar\b", body, re.IGNORECASE)) != 1
        ):
            warnings.append(
                f"Página {number}: múltiplas designações no mesmo ato; preencha manualmente."
            )
            metadata = None
            continue
        layouts.add(
            "ATO_UFPI_SUBSTITUICAO"
            if kind == "SUBSTITUICAO"
            else "PORTARIA_UFPI_DOCENTE"
        )
        item = block(
            number,
            "SUBSTITUTO" if kind == "SUBSTITUICAO" else "SERVIDOR",
            "NAO_IDENTIFICADA" if kind == "SUBSTITUICAO" else "DOCENTE",
        )
        common(item, metadata)
        flat, raw_flat = " ".join(body.split()), " ".join(original_body.split())
        if kind == "SUBSTITUICAO":
            # Name and SIAPE belong to Designar, not to the authority or titular.
            identity = re.search(
                r"Designar\s+(.+?),\s*matricula\s+SIAPE\s+n[.º°o\s]*\s*(\d+)\s*,\s*para",
                flat,
                re.IGNORECASE,
            )
            if identity:
                # Normalization removes combining accents, not base characters.
                raw_identity = re.search(
                    r"Designar\s+(.+?),\s*matr[ií]cula", raw_flat, re.IGNORECASE
                )
                add(
                    item,
                    "nome",
                    [raw_identity.group(1) if raw_identity else identity[1]],
                    number,
                    "Dispositivo: pessoa designada",
                )
                add(
                    item,
                    "matricula",
                    [identity[2]],
                    number,
                    "Dispositivo: SIAPE da pessoa designada",
                )
            functions = re.findall(r"\bFG\s*[-–—]\s*(\d{1,2})\b", flat)
            description = re.findall(
                r"Fun[cç][aã]o\s*Gratificada,\s*FG\s*[-–—]\s*\d{1,2}\s*,\s*de\s+(.+?),\s*no\s+per[ií]odo",
                raw_flat,
                re.IGNORECASE,
            )
            add(
                item,
                "funcao_substituida",
                description,
                number,
                "Dispositivo: denominação da função designada",
            )
            add(
                item,
                "codigo_funcao_substituida",
                [f"FG-{int(n)}" for n in functions],
                number,
                "Dispositivo: código explícito da função",
            )
            add(
                item,
                "tipo_funcao_substituida",
                ["FG"] if functions else [],
                number,
                "Dispositivo: função gratificada",
            )
            periods = re.findall(
                rf"no periodo de\s+({DATE})\s+a\s+({DATE})", flat, re.IGNORECASE
            )
            for key, position in (("inicio_designacao", 0), ("fim_designacao", 1)):
                add(
                    item,
                    key,
                    [period[position] for period in periods],
                    number,
                    "Dispositivo: período de designação",
                    True,
                )
            if any(
                documentary_date(a)
                and documentary_date(b)
                and documentary_date(a) > documentary_date(b)
                for a, b in periods
            ):
                for field in fields:
                    if field["bloco_id"] == item["id"] and field["campo"] in (
                        "inicio_designacao",
                        "fim_designacao",
                    ):
                        field["valor"], field["estado"] = None, "AMBIGUO"
                        field["candidatos"] = [field["observado"]]
            # The examined act only names the titular, without SIAPE or proof of leave.
            titular = re.search(
                r"por motivo de f[eé]rias d[ao] titular,\s*(.+?)\.(?:\s+Teresina|$)",
                raw_flat,
                re.IGNORECASE,
            )
            if titular:
                owner = block(number, "TITULAR")
                add(
                    owner,
                    "nome",
                    [titular[1]],
                    number,
                    "Dispositivo: titular explicitamente nomeado",
                )
                finish(owner, ())
            finish(
                item,
                ("inicio_designacao", "fim_designacao", "codigo_funcao_substituida"),
            )
        else:
            # Restrict the reading to the concession before any numbered legal note.
            flat = re.split(
                r"\s+2\.\s+De acordo", flat, maxsplit=1, flags=re.IGNORECASE
            )[0]
            original_flat = re.split(
                r"\s+2\.\s+De acordo", raw_flat, maxsplit=1, flags=re.IGNORECASE
            )[0]
            name_pattern = r"-\s*(?:DE|20H?|40H?)\s*-\s*(.+?)\s+lotado\s*\(a\)"
            names = [
                name.rstrip(",")
                for name in re.findall(name_pattern, original_flat, re.IGNORECASE)
            ]
            add(item, "nome", names, number, "Dispositivo: docente beneficiário")
            add(
                item,
                "jornada",
                re.findall(r"-\s*(DE|20H?|40H?)\s*-", flat),
                number,
                "Dispositivo: regime explicitamente informado",
            )
            effect = re.findall(rf"a partir de\s+({DATE})", flat, re.IGNORECASE)
            add(
                item,
                "efeitos_financeiros",
                effect,
                number,
                "Dispositivo: a partir de",
                True,
            )
            if kind == "PROGRESSAO":
                origin = re.findall(
                    r"Professor\s*\(a\)\s+MS\s*-\s*([A-E])\s*-\s*Denominacao\s+([A-Za-z]+)\s*-\s*(\d{1,2})\s*-",
                    flat, re.IGNORECASE,
                )
                for key, values in (("classe_origem", [t[0] for t in origin]),
                                    ("denominacao_origem", [t[1] for t in origin]),
                                    ("nivel_origem", [str(int(t[2])) for t in origin])):
                    add(item, key, values, number, "Dispositivo: posição antes da identificação do docente")
                target = re.findall(
                    r"para\s+MS\s*-\s*([A-E])\s*-\s*Denominacao\s+([A-Za-z]+)\s*-\s*(\d{1,2})\s*,",
                    flat,
                    re.IGNORECASE,
                )
                for key, values in (
                    ("classe_destino", [t[0] for t in target]),
                    ("denominacao_destino", [t[1] for t in target]),
                    ("nivel_destino", [str(int(t[2])) for t in target]),
                ):
                    add(item, key, values, number, "Dispositivo: destino após para MS")
                finish(item, ("classe_destino", "nivel_destino", "efeitos_financeiros"))
            else:
                titles_found = re.findall(
                    r"correspondente ao nivel de\s+(Doutorado|Mestrado|Especializacao)\s+ao",
                    flat,
                    re.IGNORECASE,
                )
                add(
                    item,
                    "titulacao_destino",
                    titles_found,
                    number,
                    "Dispositivo: titulação concedida",
                )
                finish(item, ("titulacao_destino", "efeitos_financeiros"))
        # Non-tabular acts are single-page layouts; no inheritance to another page.
        metadata = None
    if not consumed:
        return None, set()
    if len(blocks) > 100 or len(fields) > 2000:
        raise ValueError("Divida o documento: excesso de blocos ou campos.")
    if not blocks:
        item = block(min(consumed))
        finish(item, ())
    partial = warnings or any(f["estado"] != "EXTRAIDO" for f in fields)
    return DocumentoExtraido.model_validate(
        {
            "id": str(uuid4()),
            "layout": next(iter(layouts))
            if len(layouts) == 1
            else "MISTO"
            if layouts
            else "NAO_SUPORTADO",
            "situacao": "NAO_SUPORTADO"
            if not layouts
            else "PARCIAL"
            if partial
            else "CONCLUIDO",
            "total_paginas": len(pages),
            "blocos": blocks,
            "campos": fields,
            "avisos": warnings[:100],
            "leitores": [{"identificador": name, "versao": "2", "paginas": sorted(numbers)} for name, numbers in reader_pages.items()],
        }
    ).model_dump(mode="json"), consumed
