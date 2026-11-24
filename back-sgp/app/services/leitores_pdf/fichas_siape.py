"""Perfis SIAPE comprovados; o núcleo financeiro é comum aos cinco exemplos."""

import re
from decimal import Decimal
from uuid import uuid4

from app.services.leitores_pdf.base import extrair_base
from app.services.leitores_pdf.comuns import normalizar, origem
from app.services.leitores_pdf.geometria import linhas_posicionadas


def categoria_cargo(job):
    upper = normalizar(job)
    code = re.match(r"(\d{6})\b", upper)
    if (code and code[1] == "705002") or "PROFESSOR SUBSTITUTO" in upper:
        return "SUBSTITUTO"
    if (code and code[1] == "705001") or "MAGIST" in upper or "DOCENTE" in upper:
        return "DOCENTE"
    if (code and code[1].startswith("701")) or "TECNICO-ADMINISTRATIVO" in upper:
        return "TAE"
    return "NAO_IDENTIFICADA"


def perfil(text):
    upper = normalizar(text)
    function = re.search(r"FUNCAO/EXERC\.?\s*:\s*((?:CD|FG)\s*[- ]?\s*\d+)", upper)
    if function:
        return "siape_" + function[1][:2].lower()
    job = re.search(r"CARGO/LOTACAO:\s*([^\n]+)", upper)
    category = (
        categoria_cargo(job[1].split("FUNCAO/EXERC", 1)[0])
        if job
        else "NAO_IDENTIFICADA"
    )
    if category != "NAO_IDENTIFICADA":
        return {
            "TAE": "siape_tae",
            "DOCENTE": "siape_docente",
            "SUBSTITUTO": "siape_substituto",
        }[category]
    return "siape_financeira"


def ler(pages):
    geometry, prepared = {}, []
    for page in pages:
        if page.get("ignorar"):
            geometry.clear()
            prepared.append(page)
            continue
        text = page.get("texto_original", page["texto"])
        if page.get("palavras") and not re.search(r"RUBRICA\s*\|", text, re.IGNORECASE):
            text = linhas_posicionadas(page["palavras"], geometry, page.get("largura"))
            prepared.append(
                {
                    **page,
                    "texto": text,
                    "ambiguidades": geometry.get("ambiguidades", []),
                    "avisos": geometry.get("avisos", []),
                }
            )
        else:
            geometry.clear()
            prepared.append({**page, "texto": text})
    # Herança da coluna R/D somente no perfil SIAPE identificado. Uma tabela
    # financeira genérica com células vazias não comprova agrupamento.
    prepared = [
        {
            **p,
            "natureza_agrupada": "SIAPE"
            in normalizar(p.get("texto_original", p["texto"])),
        }
        for p in prepared
    ]
    doc = extrair_base(prepared)
    active = [p for p in prepared if not p.get("ignorar")]
    profiles = {p["numero"]: perfil(p["texto"]) for p in active}
    doc["leitores"] = []
    for identifier in sorted(set(profiles.values())):
        doc["leitores"].append(
            {
                "identificador": identifier,
                "versao": "2",
                "paginas": [n for n, p in profiles.items() if p == identifier],
            }
        )
    for field in doc["campos"]:
        number = (
            field["pagina"]
            or (field.get("paginas_analisadas") or [active[0]["numero"]])[0]
        )
        field["leitor_id"], field["leitor_versao"] = (
            profiles.get(number, "siape_financeira"),
            "2",
        )
        source_page = next((p for p in active if p["numero"] == number), None)
        year = (
            re.search(r"referente a:\s*(\d{4})", source_page["texto"], re.IGNORECASE)
            if source_page
            else None
        )
        if year and field["pagina"] is not None:
            field["ano_referencia"] = int(year[1])
    for block in doc["blocos"]:
        categories = {
            categoria_cargo(f["valor"])
            for f in doc["campos"]
            if f["bloco_id"] == block["id"]
            and f["campo"] == "cargo_lotacao"
            and f["valor"]
        }
        categories.discard("NAO_IDENTIFICADA")
        block["categoria"] = (
            next(iter(categories)) if len(categories) == 1 else "NAO_IDENTIFICADA"
        )
        if len(categories) > 1:
            doc["avisos"].append(
                "Cargo observado muda de categoria entre páginas; confira o vínculo e a carreira."
            )
            doc["situacao"] = "PARCIAL"
    positions = []
    for field in doc["campos"]:
        if field["campo"] != "cargo_lotacao" or not field["valor"]:
            continue
        match = re.match(r"(\d{6})\s+([A-Z0-9]+)\s+(\d{1,3})\b", field["valor"])
        if not match:
            continue
        if match[1].startswith("701") and match[2] in ("A", "B", "C", "D", "E"):
            facts = [
                ("classificacao_tae", match[2]),
                ("posicao_tae_observada", match[3]),
            ]
        elif match[1] in ("705001", "705002"):
            facts = [
                ("classe_docente_observada", match[2]),
                ("nivel_docente_observado", match[3]),
            ]
        else:
            facts = []
        for name, value in facts:
            positions.append(
                {
                    **field,
                    "id": str(uuid4()),
                    "campo": name,
                    "valor": value,
                    "fontes_campo_ids": [field["id"]],
                }
            )
    available = max(0, 1900 - len(doc["campos"]))
    doc["campos"].extend(positions[:available])
    if len(positions) > available:
        doc["situacao"] = "PARCIAL"
        doc["avisos"] = (doc["avisos"] + ["Limite de campos derivados atingido; confira as posições no cargo observado e complete manualmente."])[:100]
    groups = {}
    for field in doc["campos"]:
        if (
            field["campo"] == "rubrica"
            and field["estado"] == "EXTRAIDO"
            and field["natureza"] == "R"
            and field["sequencia"] == "0"
        ):
            groups.setdefault(
                (field["bloco_id"], field["pagina"], field["competencia"]), []
            ).append(field)
    for fields in groups.values():
        basics = [
            f for f in fields if f["rubrica"] == "00001" and Decimal(f["valor"]) > 0
        ]
        additions = [
            f
            for f in fields
            if re.search(
                r"INSALUBRIDADE|PERICULOSIDADE",
                normalizar(f.get("descricao_rubrica") or ""),
            )
            and Decimal(f["valor"]) > 0
        ]
        if len(basics) == len(additions) == 1:
            basic, addition = basics[0], additions[0]
            ratio = Decimal(addition["valor"]) * 100 / Decimal(basic["valor"])
            if ratio <= 100 and len(doc["campos"]) < 1900:
                doc["campos"].append(
                    {
                        **addition,
                        "id": str(uuid4()),
                        "campo": "percentual_adicional_sugerido",
                        "valor": str(ratio),
                        "estado": "AMBIGUO",
                        "sugestao": True,
                        "fontes_campo_ids": [addition["id"], basic["id"]],
                        "observado": "Razão entre adicional e VB observados na mesma competência; base, integralidade e concessão exigem confirmação.",
                        "localizador": f"Página {addition['pagina']}, razão adicional/VB; sugestão para revisão",
                    }
                )
                doc["situacao"] = "PARCIAL"
    return doc


def ler_tabular_ferias(pages):
    geometry, prepared = {}, []
    for page in pages:
        if page.get("ignorar"):
            geometry.clear()
            prepared.append(page)
        elif page.get("palavras") and "|" not in page["texto"]:
            text = linhas_posicionadas(page["palavras"], geometry, page.get("largura"))
            prepared.append(
                {**page, "texto": text, "avisos": geometry.get("avisos", [])}
            )
        else:
            prepared.append(page)
    return origem(
        extrair_base(prepared),
        "cacoferias_tabular",
        [p["numero"] for p in pages if not p.get("ignorar")],
        version="2",
    )
