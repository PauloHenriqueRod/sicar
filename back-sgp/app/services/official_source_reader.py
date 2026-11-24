"""Leitor tabular limitado. Não executa fórmulas, macros, links ou OCR."""

import csv
import io
import posixpath
import re
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from defusedxml.ElementTree import fromstring
from pydantic import BaseModel

from app.schemas.fontes_oficiais import (
    ConfiguracaoFonte,
    LeituraColuna,
    LinhaFuncao,
    LinhaIQ,
    LinhaSalarial,
)
from app.utils.salary_keys import salary_key


class SourceReadError(ValueError):
    """Mensagem controlada do leitor; pode ser apresentada ao operador."""


MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000
MAX_CELLS = 64
FIELDS = (
    "tipo",
    "carreira",
    "vinculo",
    "jornada",
    "versao_carreira",
    "classificacao_tae",
    "capacitacao_tae",
    "padrao_tae",
    "classe_docente",
    "nivel_docente",
    "inicio_vigencia",
    "fim_vigencia",
    "valor",
    "titulacao",
    "tipo_funcao",
    "codigo_funcao",
    "modalidade",
    "componente",
)


def key(value):
    return re.sub(r"[\s_/-]+", " ", salary_key(str(value))).strip()


ALIASES = {key(field): field for field in FIELDS}
ALIASES.update(
    {
        "regime": "jornada",
        "vigencia inicial": "inicio_vigencia",
        "vigencia final": "fim_vigencia",
        "valor r$": "valor",
    }
)


def value_text(value):
    if isinstance(value, (date, datetime)):
        return (
            value.date().isoformat()
            if isinstance(value, datetime)
            else value.isoformat()
        )
    return str(value).strip() if value is not None else ""


def normalize(data, *, epoch=None):
    result = {
        name: value_text(value) for name, value in data.items() if value_text(value)
    }
    for field in ("tipo", "tipo_funcao", "carreira", "jornada", "classificacao_tae"):
        if field in result:
            result[field] = result[field].upper()
    for field in ("inicio_vigencia", "fim_vigencia"):
        token = result.get(field, "")
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", token):
            result[field] = datetime.strptime(token, "%d/%m/%Y").date().isoformat()
        elif token and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
            raise SourceReadError(
                "Informe uma data de efeitos completa; ano ou número isolado não comprovam vigência."
            )
    for field in ("padrao_tae", "nivel_docente"):
        if field in result and re.fullmatch(r"\d{1,4}", result[field]):
            result[field] = int(result[field])
    token = result.get("valor", "").removeprefix("R$").strip()
    if "," in token:
        if not re.fullmatch(r"(?:\d+|\d{1,3}(?:\.\d{3})+),\d+", token):
            raise SourceReadError(
                "Valor monetário ambíguo; confira o separador decimal."
            )
        token = token.replace(".", "").replace(",", ".")
    if token:
        # A escala original é preservada; o contrato validará limites e sinal.
        result["valor"] = str(Decimal(token))
    return result


def _zip(content):
    archive = zipfile.ZipFile(io.BytesIO(content))
    entries = archive.infolist()
    if (
        len(entries) > 1000
        or sum(item.file_size for item in entries) > 20 * 1024 * 1024
        or any(item.flag_bits & 1 for item in entries)
    ):
        archive.close()
        raise SourceReadError(
            "Planilha excede os limites de leitura ou está criptografada."
        )
    return archive


def _xlsx(content):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with _zip(content) as archive:
        book = fromstring(archive.read("xl/workbook.xml"))
        epoch = (
            date(1904, 1, 1)
            if book.find("s:workbookPr", ns) is not None
            and book.find("s:workbookPr", ns).get("date1904") in ("1", "true")
            else date(1899, 12, 30)
        )
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = [
                "".join(t.text or "" for t in node.findall(".//s:t", ns))
                for node in fromstring(archive.read("xl/sharedStrings.xml")).findall(
                    "s:si", ns
                )
            ]
        relationships = {
            node.get("Id"): node.get("Target")
            for node in fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            if node.get("TargetMode") != "External"
        }
        date_styles = set()
        if "xl/styles.xml" in archive.namelist():
            styles = fromstring(archive.read("xl/styles.xml"))
            custom = {
                int(node.get("numFmtId")): node.get("formatCode", "")
                for node in styles.findall("s:numFmts/s:numFmt", ns)
            }
            for index, style in enumerate(styles.findall("s:cellXfs/s:xf", ns)):
                fmt = int(style.get("numFmtId", "0"))
                code = re.sub(r'"[^"]*"|\[[^]]*\]', "", custom.get(fmt, "")).lower()
                if fmt in {14, 15, 16, 17, 22} or re.search(r"[yd]", code):
                    date_styles.add(index)
        sheets = book.findall("s:sheets/s:sheet", ns)
        if len(sheets) > 30:
            raise SourceReadError("Máximo de 30 abas por arquivo.")
        for sheet in sheets:
            target = relationships[
                sheet.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
            ]
            path = posixpath.normpath(
                target.lstrip("/") if target.startswith("/") else "xl/" + target
            )
            if not path.startswith("xl/worksheets/"):
                raise SourceReadError("Aba não suportada.")
            rows = []
            for row in fromstring(archive.read(path)).findall("s:sheetData/s:row", ns):
                values = []
                seen_columns = set()
                for cell in row.findall("s:c", ns):
                    letters = re.match(r"[A-Z]+", cell.get("r", ""))
                    if letters is None:
                        raise SourceReadError("Posição de célula inválida.")
                    column = 0
                    for letter in letters.group():
                        column = column * 26 + ord(letter) - 64
                    if column > MAX_CELLS:
                        raise SourceReadError("Máximo de 64 colunas por aba.")
                    if column in seen_columns:
                        raise SourceReadError("Célula duplicada na mesma linha.")
                    seen_columns.add(column)
                    values.extend([None] * max(0, column - len(values)))
                    raw = cell.find("s:v", ns)
                    value = raw.text if raw is not None else ""
                    kind = cell.get("t")
                    if cell.find("s:f", ns) is not None or kind in ("e", "b"):
                        value = "=CELULA_NAO_SUPORTADA"
                    elif kind == "s":
                        shared_index = int(value)
                        if not 0 <= shared_index < len(shared):
                            raise SourceReadError("Texto compartilhado inválido.")
                        value = shared[shared_index]
                    elif kind == "inlineStr":
                        value = "".join(
                            t.text or "" for t in cell.findall(".//s:t", ns)
                        )
                    elif int(cell.get("s", "0")) in date_styles and value:
                        raw_serial = Decimal(value)
                        serial = int(raw_serial)
                        if raw_serial < 0 or (
                            epoch == date(1899, 12, 30)
                            and (raw_serial < 1 or serial == 60)
                        ):
                            value = "=DATA_EXCEL_INVALIDA"
                        else:
                            offset = (
                                1 if epoch == date(1899, 12, 30) and serial < 60 else 0
                            )
                            value = (
                                epoch + timedelta(days=serial + offset)
                            ).isoformat()
                    values[column - 1] = value
                rows.append((int(row.get("r", len(rows) + 1)), values))
                if len(rows) > MAX_ROWS:
                    raise SourceReadError("Máximo de 2000 linhas por arquivo.")
            yield sheet.get("name", "Aba"), rows, epoch


def _ods_rows(sheet, namespace):
    # Percorre apenas contêineres de linhas, sem entrar em células/tabelas
    # embutidas. A pilha evita recursão em agrupamentos profundamente aninhados.
    containers = {
        f"{{{namespace}}}{name}"
        for name in ("table-row-group", "table-header-rows", "table-rows")
    }
    stack = [iter(sheet)]
    while stack:
        node = next(stack[-1], None)
        if node is None:
            stack.pop()
        elif node.tag == f"{{{namespace}}}table-row":
            yield node
        elif node.tag in containers:
            stack.append(iter(node))


def _ods(content):
    ns = {
        "t": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
        "o": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
        "p": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    }
    attr = lambda prefix, name: "{" + ns[prefix] + "}" + name
    with _zip(content) as archive:
        root = fromstring(archive.read("content.xml"))
        sheets = root.findall("o:body/o:spreadsheet/t:table", ns)
        if len(sheets) > 30:
            raise SourceReadError("Máximo de 30 abas por arquivo.")
        for sheet in sheets:
            rows = []
            row_number = 0
            for row in _ods_rows(sheet, ns["t"]):
                repeats = int(row.get(attr("t", "number-rows-repeated"), "1"))
                if repeats < 1:
                    raise SourceReadError("Repetição de linhas ODS inválida.")
                values = []
                column = 0
                for cell in row:
                    repeat = int(cell.get(attr("t", "number-columns-repeated"), "1"))
                    if repeat < 1:
                        raise SourceReadError("Repetição de colunas ODS inválida.")
                    column += repeat
                    value = cell.get(
                        attr("o", "date-value"), cell.get(attr("o", "value"))
                    )
                    if value is None:
                        value = " ".join(
                            "".join(p.itertext()) for p in cell.findall("p:p", ns)
                        )
                    if cell.get(attr("t", "formula")):
                        value = "=CELULA_NAO_SUPORTADA"
                    if column > MAX_CELLS:
                        if value:
                            raise SourceReadError("Máximo de 64 colunas por aba.")
                        # Não expande a cauda vazia, mas conta suas posições:
                        # qualquer valor posterior continua além do limite.
                        continue
                    values.extend([value] * repeat)
                if not any(values):
                    row_number += repeats
                    continue
                if repeats > MAX_ROWS or len(rows) + repeats > MAX_ROWS:
                    raise SourceReadError("Máximo de 2000 linhas por arquivo.")
                for _ in range(repeats):
                    row_number += 1
                    rows.append((row_number, values))
            yield sheet.get(attr("t", "name"), "Aba"), rows, None


def _csv_rows(decoded, delimiter):
    reader = csv.reader(io.StringIO(decoded), delimiter=delimiter)
    while True:
        start_line = reader.line_num + 1
        try:
            row = next(reader)
        except StopIteration:
            return
        yield start_line, row


def read_source(content: bytes, filename: str, config: ConfiguracaoFonte):
    if len(content) > MAX_BYTES:
        raise SourceReadError("Arquivo excede 5 MB.")
    extension = filename.rsplit(".", 1)[-1].lower()
    if extension == "pdf":
        if any(rule.linha_inicial != 1 or rule.linha_final is not None for rule in config.leituras):
            raise SourceReadError("PDF não suporta intervalos de linhas. Use contexto comum do leitor e revise cada registro na prévia.")
        import os
        import tempfile

        from app.services.pdf_extraction import extract_pdf_data

        if not content.startswith(b"%PDF-"):
            raise SourceReadError("Arquivo PDF inválido.")
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporary:
                path = temporary.name
                temporary.write(content)
            rows = extract_pdf_data(path, "fonte:pdf")["linhas"]
            # Apenas contexto informado pelo operador. Nunca usar publicação
            # como efeitos nem sobrescrever posição/jornada/valor observado.
            for row in rows:
                for pdf_rule in config.leituras:
                    if pdf_rule.aba in ("PDF", row.get("leitor", "")):
                        for name, value in pdf_rule.contexto.items():
                            row_models: dict[str, type[BaseModel]] = {"IQ": LinhaIQ, "FUNCAO": LinhaFuncao}
                            row_model = row_models.get(row["dados"].get("tipo"), LinhaSalarial)
                            if name not in row_model.model_fields:
                                continue
                            if name not in row["dados"] or row["dados"][name] in (None, ""):
                                row["dados"][name] = value
                                row.setdefault("original", {}).setdefault("contexto_revisavel", {})[name] = value
                for name in ("padrao_tae", "nivel_docente"):
                    if isinstance(row["dados"].get(name), str) and row["dados"][name].isdigit():
                        row["dados"][name] = int(row["dados"][name])
            return rows
        finally:
            if path is not None:
                os.unlink(path)
    if extension == "csv":
        decoded = content.decode("utf-8-sig")
        delimiter = (
            ";"
            if decoded.splitlines()
            and decoded.splitlines()[0].count(";") >= decoded.splitlines()[0].count(",")
            else ","
        )
        tables = [("CSV", _csv_rows(decoded, delimiter), None)]
    elif extension == "xlsx":
        tables = _xlsx(content)
    elif extension == "ods":
        tables = _ods(content)
    else:
        return [
            {
                "localizador": "Arquivo",
                "dados": {},
                "erro": "Formato sem leitura suportada. Prefira CSV/XLSX/ODS equivalentes ou cadastre os valores manualmente, indicando página/aba.",
            }
        ]
    result: list[dict[str, Any]] = []

    def append_result(item: dict[str, Any]):
        if len(result) >= MAX_ROWS:
            raise SourceReadError(
                "Máximo de 2000 registros por prévia, incluindo rejeições."
            )
        result.append(item)

    seen = 0
    logical_size = 0
    projected_size = 0
    for sheet, rows, epoch in tables:
        rules: list[LeituraColuna | None] = [
            rule for rule in config.leituras if rule.aba == sheet
        ] or [None]
        if config.leituras and rules == [None]:
            append_result(
                {
                    "localizador": sheet,
                    "dados": {},
                    "erro": "Aba sem regra de leitura; confira e cadastre uma regra explícita.",
                }
            )
            continue
        headers: list[dict[str, int] | None] = [None for _ in rules]
        for number, cells in rows:
            seen += 1
            logical_size += sum(len(value_text(cell)) for cell in cells)
            if logical_size > MAX_BYTES:
                raise SourceReadError(
                    "Expansão lógica da planilha excede 5 MB de texto."
                )
            if seen > MAX_ROWS or len(cells) > MAX_CELLS:
                raise SourceReadError("Limite de 2000 linhas/64 colunas excedido.")
            if any(len(value_text(cell)) > 2000 for cell in cells):
                raise SourceReadError(
                    "Célula excede 2000 caracteres; use cadastro manual conferido."
                )
            if not any(value_text(cell) for cell in cells):
                continue
            for index, rule in enumerate(rules):
                if rule is not None and (
                    number < rule.linha_inicial
                    or (rule.linha_final is not None and number > rule.linha_final)
                ):
                    continue
                aliases = (
                    {key(column): field for field, column in rule.colunas.items()}
                    if rule
                    else ALIASES
                )
                header = {
                    aliases[key(cell)]: i
                    for i, cell in enumerate(cells)
                    if key(cell) in aliases
                }
                location = f"{sheet}: linha {number}, leitura {index + 1}"
                is_header = "valor" in header or len(header) >= 2
                if header and not is_header:
                    # Um rótulo isolado pode ser um dado legítimo (por exemplo,
                    # FUNCAO sob um cabeçalho que contém 'Função'). Só preserva
                    # o mapeamento se a coluna de valor ainda contiver um número.
                    value_column = (headers[index] or {}).get("valor", len(cells))
                    try:
                        token = normalize(
                            {
                                "valor": cells[value_column]
                                if value_column < len(cells)
                                else None
                            }
                        ).get("valor", "")
                        is_header = not token or not Decimal(token).is_finite()
                    except (ValueError, ArithmeticError):
                        is_header = True
                if is_header:
                    if len(header) != len(
                        [cell for cell in cells if key(cell) in aliases]
                    ):
                        append_result(
                            {
                                "localizador": location,
                                "dados": {},
                                "erro": "Colunas duplicadas/ambíguas no cabeçalho.",
                            }
                        )
                        headers[index] = None
                    elif (
                        missing := (set(rule.colunas) if rule else {"valor"})
                        - header.keys()
                    ):
                        append_result(
                            {
                                "localizador": location,
                                "dados": {},
                                "erro": "Colunas mapeadas ausentes no cabeçalho: "
                                + ", ".join(sorted(missing))
                                + ". Confira a regra de leitura.",
                            }
                        )
                        headers[index] = None
                    else:
                        headers[index] = header
                    continue  # Inclui cabeçalhos repetidos; nunca são dados.
                mapping = headers[index]
                data: dict[str, object] = dict(rule.contexto) if rule else {}
                if mapping:
                    data.update(
                        {
                            field: cells[column] if column < len(cells) else None
                            for field, column in mapping.items()
                        }
                    )
                projected_size += sum(len(value_text(value)) for value in data.values())
                if projected_size > MAX_BYTES:
                    raise SourceReadError("Prévia projetada excede 5 MB de texto.")
                try:
                    if not mapping:
                        raise SourceReadError(
                            "Cabeçalho não identificado. Configure as colunas ou use cadastro manual."
                        )
                    if any(
                        value_text(cell).startswith(("=", "+", "@")) for cell in cells
                    ):
                        raise SourceReadError(
                            "Fórmula/célula não suportada; informe o valor conferido manualmente."
                        )
                    normalized = normalize(data, epoch=epoch)
                    append_result(
                        {
                            "localizador": location,
                            "dados": normalized,
                            "original": {
                                "campos_lidos": {
                                    field: value_text(cells[column])
                                    if column < len(cells)
                                    else ""
                                    for field, column in mapping.items()
                                },
                                "contexto": dict(rule.contexto) if rule else {},
                            },
                            "erro": None,
                        }
                    )
                except (ValueError, ArithmeticError):
                    append_result(
                        {
                            "localizador": location,
                            "dados": {k: value_text(v) for k, v in data.items()},
                            "original": {
                                "campos_lidos": {
                                    field: value_text(cells[column])
                                    if column < len(cells)
                                    else ""
                                    for field, column in mapping.items()
                                }
                                if mapping
                                else {},
                                "contexto": dict(rule.contexto) if rule else {},
                            },
                            "erro": "Linha não interpretada com segurança; confira cabeçalho, datas e valor ou preencha manualmente.",
                        }
                    )
                if len(result) > MAX_ROWS:
                    raise SourceReadError("Máximo de 2000 registros por prévia.")
    return result or [
        {
            "localizador": "Arquivo",
            "dados": {},
            "erro": "Nenhuma linha encontrada; cadastre manualmente.",
        }
    ]
