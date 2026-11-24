"""Leitores delimitados por página/bloco; valores observados nunca concedem direito."""

import re
from collections import defaultdict
from datetime import timedelta
from uuid import uuid4

from app.schemas.extracao_documentos import DocumentoExtraido
from app.utils.conversor import ConversorSaneador
from app.utils.employee_identity import employee_key
from app.utils.exercicios_candidates import valor_observado
from app.utils.ficha_financeira import MESES

FIELDS = (
    "matricula",
    "nome",
    "vinculo",
    "cargo_lotacao",
    "posicao",
    "quantidade_anuenios",
    "funcao_exercida",
    "inicio_exercicio",
)


def data_documental(raw):
    compact = re.fullmatch(r"(\d{2})([A-Za-zÇç]{3})(\d{4})", raw)
    if compact and compact.group(2).upper() in MESES:
        raw = f"{compact.group(1)}/{MESES[compact.group(2).upper()]:02}/{compact.group(3)}"
    return ConversorSaneador.para_data(raw)


def extrair_base(pages):
    doc_id = str(uuid4())
    blocks, fields, layouts, warnings = [], [], set(), []
    current, year, columns, section = None, None, [], None
    vacation_header, vacation_identity = None, None
    truncated = False
    natureza_grupo = None

    def add(campo, value, raw, page, line, **extra):
        nonlocal truncated
        if len(fields) >= 1900:
            truncated = True
            return
        if page not in current["paginas"]:
            current["paginas"].append(page)
        fields.append(
            {
                "id": str(uuid4()),
                "bloco_id": current["id"],
                "campo": campo,
                "valor": value,
                "observado": str(raw)[:300] if raw is not None else None,
                "estado": "EXTRAIDO" if value is not None else "ILEGIVEL",
                "pagina": page,
                "localizador": f"Página {page}, linha {line}",
                **extra,
            }
        )
        return fields[-1]

    def block(page, matricula=None, nome=None, vinculo=None):
        nonlocal current, year, columns, section, natureza_grupo
        natureza_grupo = None
        if current is not None and not any(
            field["bloco_id"] == current["id"] for field in fields
        ):
            current.update(matricula=matricula, nome=nome, vinculo=vinculo)
            if page not in current["paginas"]:
                current["paginas"].append(page)
            year, columns, section = None, [], None
            return
        current = {
            "id": str(uuid4()),
            "matricula": matricula,
            "nome": nome,
            "vinculo": vinculo,
            "paginas": [page],
            "categoria": "NAO_IDENTIFICADA",
        }
        blocks.append(current)
        year, columns, section = None, [], None

    for page in pages:
        if page.get("ignorar"):
            continue
        number, text = page["numero"], page["texto"]
        warnings.extend(
            f"Página {number}: {warning}"
            for warning in page.get("avisos", [])
            if len(warnings) < 100
        )
        ambiguous_columns = {tuple(item) for item in page.get("ambiguidades", [])}
        page_year = re.search(r"referente a:\s*(\d{4})", text, re.IGNORECASE)
        if not text.strip():
            warnings.append(
                f"Página {number} sem texto utilizável; preencha manualmente. Não há OCR."
            )
            continue
        if current is None:
            block(number)
        section = None
        natureza_grupo = None
        section_lines = 0
        issuer = False
        for line_number, line in enumerate(text.splitlines(), 1):
            if re.search(
                r"RESPONS[ÁA]VEL\s+(?:PELA\s+)?EMISS[ÃA]O|EMITIDO\s+POR",
                line,
                re.IGNORECASE,
            ):
                issuer = True
                continue
            if issuer:
                # O SIAPE também imprime o emissor antes da tabela financeira.
                # O cabeçalho encerra esse bloco sem reaproveitar sua identidade.
                if re.match(
                    r"\s*(?:Ficha Financeira|CACOFERIAS|CARGO/EMPREGO|RUBRICA\s*\|)",
                    line,
                    re.IGNORECASE,
                ):
                    issuer = False
                else:
                    continue
            person = re.search(
                r"^\s*Nome:\s*(\d+)\s*-\s*(.+?)(?:\s+Banco/Ag[êe]ncia|$)",
                line,
                re.IGNORECASE,
            )
            named = re.search(
                r"^\s*Nome(?: do servidor)?\s*:\s*(.+?)(?:\s+Matr[ií]cula\s*:|$)",
                line,
                re.IGNORECASE,
            )
            matric = re.search(
                r"^\s*Matr[ií]cula(?: SIAPE)?\s*:\s*(\d+)\b", line, re.IGNORECASE
            )
            if person or named or matric:
                mat = person.group(1) if person else matric.group(1) if matric else None
                name = (
                    person.group(2).strip()
                    if person
                    else named.group(1).strip()
                    if named
                    else None
                )
                changed = (
                    mat
                    and current["matricula"]
                    and employee_key(mat) != employee_key(current["matricula"])
                ) or (
                    name
                    and current["nome"]
                    and name.casefold() != current["nome"].casefold()
                )
                previous_facts = any(
                    field["bloco_id"] == current["id"]
                    and field["campo"] not in ("nome", "matricula", "vinculo")
                    for field in fields
                )
                late_identity = (
                    previous_facts
                    and not current["matricula"]
                    and (mat or (name and not current["nome"]))
                )
                if late_identity:
                    warnings.append(
                        f"Página {number}: identificação encontrada após dados sem pessoa comprovada; os dados anteriores permanecem em bloco separado para associação manual."
                    )
                    changed = True
                if changed:
                    natureza_grupo = None
                    block(number, mat, name)
                    vacation_header, vacation_identity = None, None
                    if page_year:
                        year = int(page_year.group(1))
                else:
                    if mat:
                        current["matricula"] = mat
                    if name:
                        current["nome"] = name
                if mat:
                    add("matricula", mat, mat, number, line_number)
                if name:
                    add("nome", name, name, number, line_number)
            link = re.search(
                r"^\s*(?:V[ií]nculo|Contrato)(?:\s+n[ºo°.]*)?\s*:\s*(\S.{0,98})$",
                line,
                re.IGNORECASE,
            )
            if link:
                value = link.group(1).strip()
                if current["vinculo"] and value != current["vinculo"]:
                    block(number, current["matricula"], current["nome"], value)
                    if page_year:
                        year = int(page_year.group(1))
                current["vinculo"] = value
                add("vinculo", value, value, number, line_number)
            annual = re.search(r"referente a:\s*(\d{4})", line, re.IGNORECASE)
            if annual:
                natureza_grupo = None
                layouts.add("FICHA_SIAPE")
                year = int(annual.group(1))
                columns = []
                vacation_header, vacation_identity = None, None
            if re.match(r"\s*RUBRICA\s*\|", line, re.IGNORECASE):
                natureza_grupo = None
                layouts.add("FICHA_SIAPE")
                columns = [c.strip().upper() for c in line.split("|")[4:]]
                continue
            if re.search(r"CARGO\s*[/ ]\s*EMPREGO", line, re.IGNORECASE):
                layouts.add("CADASTRO_FUNCIONAL")
                section = "CARGO"
                section_lines = 0
                vacation_header, vacation_identity = None, None
            elif re.match(
                r"\s*(?:DADOS BANC|DEPENDENTES|APOSENTADORIA|LOTA[CÇ])",
                line,
                re.IGNORECASE,
            ):
                section = None
            if section == "CARGO":
                section_lines += 1
                if section_lines > 12:
                    section = None
            if section == "CARGO":
                entry = re.search(
                    r"\bEXERC[IÍ]CIO\s*:?\s*(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})",
                    line,
                    re.IGNORECASE,
                )
                if entry:
                    parsed = ConversorSaneador.para_data(entry.group(1))
                    add(
                        "inicio_exercicio",
                        parsed.isoformat() if parsed else None,
                        entry.group(1),
                        number,
                        line_number,
                    )
            job = re.search(
                r"(?:Cargo/Lota[çc][ãa]o|Cargo/Emprego|Cargo)\s*:\s*(.+?)(?=\s+Fun[çc][ãa]o/Exerc|$)",
                line,
                re.IGNORECASE,
            )
            if job:
                value = job.group(1).strip()
                add("cargo_lotacao", value[:300], value, number, line_number)
                add("posicao", value[:300], value, number, line_number)
                code = re.match(r"(\d{6})\b", value)
                if code:
                    add("codigo_cargo", code[1], code[1], number, line_number)
            function = re.search(
                r"Fun[çc][ãa]o/Exerc\.?\s*:\s*(.*?)(?=Localiza[çc][ãa]o\s*:|Dep\.?\s*IR|T\.\s*serv|$)",
                line,
                re.IGNORECASE,
            )
            if function:
                value = function.group(1).strip()
                if value:
                    add("funcao_exercida", value[:300], value, number, line_number)
            time = re.search(r"T\.\s*serv\.?\s*:\s*([0-9.,]+)", line, re.IGNORECASE)
            if time:
                value = time.group(1).replace(",", ".")
                add(
                    "quantidade_anuenios",
                    value if re.fullmatch(r"\d+(?:\.\d+)?", value) else None,
                    time.group(1),
                    number,
                    line_number,
                )
            upper = line.upper()
            if "SUBSTITUTO" in upper:
                current["categoria"] = "SUBSTITUTO"
            elif current["categoria"] != "SUBSTITUTO" and (
                "MAGIST" in upper or "DOCENTE" in upper
            ):
                current["categoria"] = "DOCENTE"
            elif "TECNICO-ADMINISTRATIVO" in upper or "TÉCNICO-ADMINISTRATIVO" in upper:
                current["categoria"] = "TAE"
            rubric = re.match(
                r"\s*(\d{5})\s*\|([^|]+)\|([^|]*)\|\s*(\d+)\s*\|(.*)", line
            )
            if re.match(r"\s*(?:TOTAIS?|SOMATORIO|SOMATÓRIO)\b", line, re.IGNORECASE):
                natureza_grupo = None
            if rubric:
                code, description, nature, seq, amounts = rubric.groups()
                explicit_nature = nature.strip() in ("R", "D")
                if explicit_nature:
                    natureza_grupo = nature.strip()
                elif nature.strip():
                    natureza_grupo = None
                observed_nature = (
                    nature.strip()
                    if explicit_nature
                    else natureza_grupo
                    if not nature.strip() and page.get("natureza_agrupada")
                    else None
                )
                for index, raw in enumerate(amounts.split("|")):
                    label = columns[index] if index < len(columns) else ""
                    ambiguous_column = (line_number, index) in ambiguous_columns
                    if (
                        label in ("TOTAL", "TOTAIS") and not ambiguous_column
                    ) or raw.strip() in ("", "-", "—"):
                        continue
                    month = MESES.get(label[:3])
                    amount = valor_observado(raw)
                    competence = (
                        f"{year:04}-{month:02}"
                        if year and year > 0 and month and not ambiguous_column
                        else None
                    )
                    added = add(
                        "rubrica",
                        amount,
                        raw.strip(),
                        number,
                        line_number,
                        rubrica=code,
                        descricao_rubrica=description.strip()[:300],
                        natureza=observed_nature,
                        natureza_origem="EXPLICITA"
                        if explicit_nature
                        else "GRUPO"
                        if observed_nature
                        else None,
                        sequencia=seq,
                        competencia=competence,
                    )
                    if (
                        added
                        and amount is not None
                        and (competence is None or observed_nature is None)
                    ):
                        added["estado"] = "AMBIGUO"
                    iq = re.search(
                        r"\bIQ\s*-\s*(\d{1,3}(?:[.,]\d+)?)\s*%",
                        description,
                        re.IGNORECASE,
                    )
                    if iq and amount is not None:
                        add(
                            "percentual_iq",
                            iq[1].replace(",", "."),
                            description,
                            number,
                            line_number,
                            rubrica=code,
                            competencia=competence,
                            sequencia=seq,
                        )
            # CACOFERIAS delimitado, inclusive texto com colunas alinhadas.
            cells = [c.strip() for c in re.split(r"\s*\|\s*|\s{2,}", line.strip())]
            if len(cells) == 1:
                cells = line.split()
            labels = [c.upper().replace("Í", "I") for c in cells]
            if all(label in labels for label in ("INICIO", "DIAS", "PARCELA")):
                layouts.add("CACOFERIAS")
                vacation_header = labels.index("INICIO"), labels.index("DIAS")
                vacation_identity = {
                    label: labels.index(label)
                    for label in ("MATRICULA", "NOME", "VINCULO", "EXERCICIO", "FIM")
                    if label in labels
                }
                continue
            if vacation_header and len(cells) > max(vacation_header):
                raw_start, days = cells[vacation_header[0]], cells[vacation_header[1]]
                if (
                    vacation_identity
                    and "MATRICULA" in vacation_identity
                    and re.match(r"\d{2}(?:/|[A-Za-zÇç])", raw_start)
                ):
                    mat = cells[vacation_identity["MATRICULA"]]
                    name = (
                        cells[vacation_identity["NOME"]]
                        if "NOME" in vacation_identity
                        else None
                    )
                    link = (
                        cells[vacation_identity["VINCULO"]]
                        if "VINCULO" in vacation_identity
                        else None
                    )
                    if (
                        not mat.isdigit()
                        or not current["matricula"]
                        or employee_key(mat) != employee_key(current["matricula"])
                        or (link and current["vinculo"] and link != current["vinculo"])
                    ):
                        block(number, mat if mat.isdigit() else None, name, link)
                    if mat.isdigit():
                        add("matricula", mat, mat, number, line_number)
                    if name:
                        add("nome", name, name, number, line_number)
                    if link:
                        current["vinculo"] = link
                        add("vinculo", link, link, number, line_number)
                if (
                    vacation_identity
                    and "EXERCICIO" in vacation_identity
                    and len(cells) > vacation_identity["EXERCICIO"]
                ):
                    exercise = cells[vacation_identity["EXERCICIO"]]
                    if re.fullmatch(r"\d{4}", exercise):
                        add("exercicio_ferias", exercise, exercise, number, line_number)
                start = data_documental(raw_start)
                end_index = (vacation_identity or {}).get("FIM")
                raw_end = (
                    cells[end_index]
                    if end_index is not None and len(cells) > end_index
                    else ""
                )
                informed_end = data_documental(raw_end) if raw_end else None
                if start and days.isdigit() and 1 <= int(days) <= 366:
                    try:
                        end = start + timedelta(days=int(days) - 1)
                    except OverflowError:
                        end = None
                    conflicting = bool(raw_end) and informed_end != end
                    invalid = end is None or (bool(raw_end) and informed_end is None)
                    added = add(
                        "periodo_ferias",
                        days,
                        " ".join(cells)[:300],
                        number,
                        line_number,
                        inicio=start.isoformat(),
                        fim=end.isoformat()
                        if end and not conflicting and not invalid
                        else None,
                        fim_informado=informed_end.isoformat()
                        if informed_end
                        else None,
                        fim_calculado=end.isoformat() if end else None,
                        dias_informados=days,
                    )
                    if added and (conflicting or invalid):
                        added["estado"] = "ILEGIVEL" if invalid else "AMBIGUO"
                        warnings.append(
                            f"Página {number}, linha {line_number}: fim informado e duração das férias exigem revisão; nenhum fim foi escolhido automaticamente."
                        )
                elif re.match(r"\d{2}(?:/|[A-Za-zÇç])", raw_start):
                    add(
                        "periodo_ferias",
                        None,
                        " ".join(cells)[:300],
                        number,
                        line_number,
                    )
        if number not in current["paginas"]:
            current["paginas"].append(number)
    # Não presume unicidade quando o mesmo campo singular tem valores divergentes.
    grouped = defaultdict(list)
    for field in fields:
        if field["campo"] in FIELDS and field["campo"] not in (
            "cargo_lotacao",
            "posicao",
        ):
            grouped[field["bloco_id"], field["campo"]].append(field)
    for values in grouped.values():
        if len({v["valor"] for v in values}) > 1:
            for value in values:
                value["estado"] = "AMBIGUO"
    for item in blocks:
        present = {f["campo"] for f in fields if f["bloco_id"] == item["id"]}
        for missing in set(FIELDS) - present:
            fields.append(
                {
                    "id": str(uuid4()),
                    "bloco_id": item["id"],
                    "campo": missing,
                    "valor": None,
                    "estado": "AUSENTE",
                    "pagina": None,
                    "localizador": "Não encontrado nas páginas analisadas",
                    "paginas_analisadas": item["paginas"],
                }
            )
    if truncated:
        warnings.append(
            "Extração incompleta: limite de campos atingido. Confira o documento inteiro e complete manualmente."
        )
    if not layouts:
        warnings.append("Layout não suportado; preencha os dados manualmente.")
    if len(blocks) > 100 or len(fields) > 2000:
        raise ValueError("Divida o documento: excesso de blocos ou campos.")
    state = (
        "SEM_TEXTO"
        if not blocks
        else "NAO_SUPORTADO"
        if not layouts
        else "PARCIAL"
        if warnings or any(f["estado"] in ("AMBIGUO", "ILEGIVEL") for f in fields)
        else "CONCLUIDO"
    )
    return DocumentoExtraido.model_validate(
        {
            "id": doc_id,
            "layout": next(iter(layouts))
            if len(layouts) == 1
            else "MISTO"
            if layouts
            else "NAO_SUPORTADO",
            "situacao": state,
            "total_paginas": len(pages),
            "blocos": blocks,
            "campos": fields,
            "avisos": warnings[:100],
        }
    ).model_dump(mode="json")
