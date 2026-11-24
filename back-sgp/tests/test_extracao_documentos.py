"""Documentos inteiramente sintéticos, incluindo tabelas posicionadas sem pipes."""

import pytest
from fpdf import FPDF

from app.schemas.calculos import ExerciciosParcelasDados
from app.services.extracao_documentos import extrair_documento
from app.services.pendencias import PendenciaApuracao
from app.services.revisao_extracao import validar_revisao_extracao


@pytest.mark.parametrize(
    "saved_has_empty,current_has_history",
    [(False, False), (True, False), (False, True)],
)
def test_replay_normalizes_only_empty_extraction_history(
    monkeypatch, saved_has_empty, current_has_history
):
    from copy import deepcopy
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.routers import calculos_router
    from app.schemas.calculos import entradas_calculo

    data = review_data()
    model = ExerciciosParcelasDados.model_validate(data)
    saved = entradas_calculo(model, mode="json")
    if not saved_has_empty:
        saved["revisao_extracao"].pop("historico_aplicacoes")
    if current_has_history:
        data["revisao_extracao"]["historico_aplicacoes"] = deepcopy(
            data["revisao_extracao"]["aplicacoes"]
        )
        model = ExerciciosParcelasDados.model_validate(data)
    snapshot = {
        "dados_extraidos": saved,
        "rastreabilidade": {"entradas_decimais": deepcopy(saved)},
        "resultado_calculo": {"saldo": "1000.00"},
    }
    monkeypatch.setattr(calculos_router, "_snapshot", lambda _: snapshot)
    record = SimpleNamespace(id=123, tipo_calculo="exercicio_anterior")
    if current_has_history:
        with pytest.raises(HTTPException) as error:
            calculos_router._replay(
                record,
                record.tipo_calculo,
                entradas_calculo(model, mode="json"),
                entradas_calculo(model),
            )
        assert error.value.status_code == 409
    else:
        assert (
            calculos_router._replay(
                record,
                record.tipo_calculo,
                entradas_calculo(model, mode="json"),
                entradas_calculo(model),
            )["historico_id"]
            == 123
        )


def pages(*texts):
    return [{"numero": index + 1, "texto": text} for index, text in enumerate(texts)]


def ficha(name="ALFA SINTETICO", mat="000999", year="2025", value="330,00"):
    return f"Ficha Financeira referente a: {year}\nNome: {mat} - {name} Banco/Agencia: 1\nVinculo: V1\nCargo/Lotação: TECNICO-ADMINISTRATIVO D 303 Função/Exerc.: FG 2 Localização: TESTE T. serv.: 12\nRubrica|Nome|R/D|Seq.|JAN|FEV|TOTAL\n98002|PSS|D|0|{value}|0,00|330,00\n00750|FERIAS ADICIONAL|R|6|100,00||100,00\n00750|ESTORNO|D|7|-25,00||25,00"


@pytest.mark.parametrize(
    "category,label",
    [
        ("TAE", "TECNICO-ADMINISTRATIVO"),
        ("DOCENTE", "PROF MAGIST SUPERIOR"),
        ("SUBSTITUTO", "PROFESSOR SUBSTITUTO"),
    ],
)
def test_categories_keep_occurrences_nature_zero_and_page_without_granting_right(
    category, label
):
    doc = extrair_documento(pages(ficha().replace("TECNICO-ADMINISTRATIVO", label)))
    assert doc["blocos"][0]["categoria"] == category
    entries = [f for f in doc["campos"] if f["campo"] == "rubrica"]
    assert [
        (f["rubrica"], f["natureza"], f["sequencia"], f["valor"]) for f in entries
    ] == [
        ("98002", "D", "0", "330.00"),
        ("98002", "D", "0", "0.00"),
        ("00750", "R", "6", "100.00"),
        ("00750", "D", "7", "-25.00"),
    ]
    assert all(f["pagina"] == 1 for f in entries)
    assert entries[1]["competencia"] == "2025-02"
    assert not any("concedido" in f or "quitado" in f for f in entries)
    assert (
        next(f for f in doc["campos"] if f["campo"] == "quantidade_anuenios")["valor"]
        == "12"
    )


def test_different_people_and_links_are_distinct_even_in_same_pdf():
    doc = extrair_documento(
        pages(ficha(), ficha(name="BETA SINTETICO", mat="888", year="2026"))
    )
    assert len(doc["blocos"]) == 2
    assert [b["matricula"] for b in doc["blocos"]] == ["000999", "888"]
    assert [b["paginas"] for b in doc["blocos"]] == [[1], [2]]
    entries = [f for f in doc["campos"] if f["campo"] == "rubrica" and f["pagina"] == 2]
    assert entries[0]["competencia"] == "2026-01"
    assert entries[0]["bloco_id"] == doc["blocos"][1]["id"]
    linked = extrair_documento(
        pages(
            "Nome: 999 - ALFA Banco/Agencia: 1\nVinculo: V1\nCARGO/EMPREGO\nEXERCICIO: 16/01/2025\nVinculo: V2\nCARGO/EMPREGO\nEXERCICIO: 17/01/2025"
        )
    )
    assert [b["vinculo"] for b in linked["blocos"]] == ["V1", "V2"]


def test_repeated_headers_and_conflicting_singular_values_preserve_both_pages():
    doc = extrair_documento(
        pages(ficha(), ficha().replace("T. serv.: 12", "T. serv.: 13"))
    )
    assert len(doc["blocos"]) == 1
    observed = [f for f in doc["campos"] if f["campo"] == "quantidade_anuenios"]
    assert [(f["pagina"], f["valor"], f["estado"]) for f in observed] == [
        (1, "12", "AMBIGUO"),
        (2, "13", "AMBIGUO"),
    ]


def test_entry_date_is_read_only_in_cargo_section_and_absence_has_no_fake_page():
    doc = extrair_documento(
        pages(
            "Nome: 999 - ALFA Banco/Agencia: 1\nEXERCICIO: 01/01/2000\nCARGO/EMPREGO\nCargo: Professor substituto\nEXERCICIO: 16/01/2025\nDADOS BANCARIOS\nEXERCICIO: 02/02/2002"
        )
    )
    entries = [f for f in doc["campos"] if f["campo"] == "inicio_exercicio"]
    assert [f["valor"] for f in entries] == ["2025-01-16"]
    missing = next(f for f in doc["campos"] if f["campo"] == "quantidade_anuenios")
    assert missing["estado"] == "AUSENTE"
    assert missing["valor"] is None and missing["pagina"] is None
    assert missing["paginas_analisadas"] == [1]


def test_vacation_periods_preserve_parcels_and_real_calendar():
    doc = extrair_documento(
        pages(
            "Nome: 999 - ALFA Banco/Agencia: 1\nINICIO|DIAS|PARCELA\n28/02/2024|3|1\n01JUL2026|10|2\n05/07/2026|5|3"
        )
    )
    rows = [f for f in doc["campos"] if f["campo"] == "periodo_ferias"]
    assert [(f["inicio"], f["fim"], f["valor"]) for f in rows] == [
        ("2024-02-28", "2024-03-01", "3"),
        ("2026-07-01", "2026-07-10", "10"),
        ("2026-07-05", "2026-07-09", "5"),
    ]


def test_blank_unknown_and_partly_unreadable_pages_are_explicit():
    assert extrair_documento(pages(""))["situacao"] == "SEM_TEXTO"
    assert (
        extrair_documento(pages("Documento sem layout reconhecido"))["situacao"]
        == "NAO_SUPORTADO"
    )
    partial = extrair_documento(pages(ficha(value="ilegivel"), ""))
    assert partial["situacao"] == "PARCIAL"
    assert (
        next(f for f in partial["campos"] if f["campo"] == "rubrica")["valor"] is None
    )
    assert any("Página 2" in warning for warning in partial["avisos"])


def native_pdf(path):
    pdf = FPDF(orientation="L")
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.text(10, 15, "Ficha Financeira referente a: 2025")
    pdf.text(10, 22, "Nome: 000999 - ALFA SINTETICO Banco/Agencia: 1")
    for x, text in [
        (10, "Rubrica"),
        (40, "Nome"),
        (140, "R/D"),
        (160, "Seq."),
        (185, "JAN"),
        (220, "FEV"),
        (255, "TOTAL"),
    ]:
        pdf.text(x, 35, text)
    for x, text in [
        (10, "98002"),
        (40, "PSS"),
        (140, "D"),
        (160, "0"),
        (185, "330,00"),
        (255, "330,00"),
    ]:
        pdf.text(x, 45, text)
    pdf.output(str(path))
    return path


def test_real_worker_recognizes_positioned_columns_without_pipes(tmp_path):
    from app.services.pdf_extraction import extract_pdf_data

    path = native_pdf(tmp_path / "sintetico.pdf")
    doc = extract_pdf_data(str(path), "v2:abono")["_extracao_v2"]
    rows = [f for f in doc["campos"] if f["campo"] == "rubrica"]
    assert len(rows) == 1
    assert (rows[0]["valor"], rows[0]["competencia"], rows[0]["natureza"]) == (
        "330.00",
        "2025-01",
        "D",
    )


def test_api_keeps_valid_files_before_and_after_failure_and_cleans_temps(
    auth_client_user, tmp_path
):
    path = native_pdf(tmp_path / "sintetico.pdf")
    response = auth_client_user.post(
        "/api/extrair-pdf",
        data={"tipo_calculo": "apuracao_periodos", "versao_extracao": "2"},
        files=[
            ("arquivos", ("antes.pdf", path.read_bytes(), "application/pdf")),
            ("arquivos", ("defeito.pdf", b"erro", "application/pdf")),
            ("arquivos", ("depois.pdf", path.read_bytes(), "application/pdf")),
        ],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["versao_contrato"] == 2
    assert [r["filename"] for r in data["resultados"]] == ["antes.pdf", "depois.pdf"]
    assert [r["filename"] for r in data["falhas"]] == ["defeito.pdf"]
    assert (
        data["resultados"][0]["extracao"]["impressao"]
        == data["resultados"][1]["extracao"]["impressao"]
    )
    assert auth_client_user.get("/api/calculos/contratos/extracao").status_code == 200


def test_all_failed_files_still_allow_manual_entry(auth_client_user):
    response = auth_client_user.post(
        "/api/extrair-pdf",
        data={"tipo_calculo": "rescisao", "versao_extracao": "2"},
        files={"arquivos": ("ilegivel.pdf", b"erro", "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["resultados"] == []
    assert len(response.json()["falhas"]) == 1


def review_data():
    from test_exercicios_parcelas import plan

    doc = extrair_documento(pages(ficha()))
    field = next(f for f in doc["campos"] if f["campo"] == "matricula")
    review = {
        "documentos": [doc],
        "associacoes": [
            {
                "documento_id": doc["id"],
                "bloco_id": doc["blocos"][0]["id"],
                "pessoa": "SERVIDOR",
                "matricula": "000999",
                "vinculo": "V1",
                "confirmado": True,
            }
        ],
        "vinculo_calculo": "V1",
        "confirmado": True,
        "aplicacoes": [
            {
                "documento_id": doc["id"],
                "campo_id": field["id"],
                "destino": ["matricula"],
                "valor_revisado": "000999",
            }
        ],
    }
    business = plan()
    business["vinculo_id"] = "V1"
    return {"matricula": "000999", "exercicios": business, "revisao_extracao": review}


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["revisao_extracao"].update(confirmado=False),
        lambda d: d["revisao_extracao"]["associacoes"][0].update(matricula="888"),
        lambda d: d["revisao_extracao"]["associacoes"][0].update(vinculo="OUTRO"),
        lambda d: d["revisao_extracao"]["aplicacoes"][0].update(valor_revisado="999"),
        lambda d: d["revisao_extracao"]["aplicacoes"][0].update(
            destino=["exercicios", "conferido_pelo_rh"]
        ),
    ],
)
def test_incompatible_associations_and_stale_applications_block_calculation(change):
    data = review_data()
    change(data)
    with pytest.raises(PendenciaApuracao):
        validar_revisao_extracao(ExerciciosParcelasDados.model_validate(data))


def test_review_sources_survive_calculation_history_and_pdf(auth_client_user):
    data = review_data()
    response = auth_client_user.post(
        "/api/calcular",
        json={"tipo_calculo": "exercicio_anterior", "dados_extraidos": data},
    )
    assert response.status_code == 200, response.text
    pdf = auth_client_user.post(
        "/api/exportar-pdf", json={"historico_id": response.json()["historico_id"]}
    )
    assert pdf.status_code == 200, pdf.text


def test_revised_value_reaches_engine_without_changing_document_or_global_table(
    auth_client_user,
):
    data = review_data()
    review = data["revisao_extracao"]
    review["historico_aplicacoes"] = review["aplicacoes"][:]
    doc = review["documentos"][0]
    field = next(field for field in doc["campos"] if field["campo"] == "rubrica")
    data["exercicios"]["devidos"][0]["valor"] = "1234.565"
    review["aplicacoes"] = [
        {
            "documento_id": doc["id"],
            "campo_id": field["id"],
            "destino": ["exercicios", "devidos", 0, "valor"],
            "valor_revisado": "1234.565",
            "valor_anterior": "1000",
            "justificativa": "Valor final confirmado na memória sintética pelo RH.",
        }
    ]
    response = auth_client_user.post(
        "/api/calcular",
        json={"tipo_calculo": "exercicio_anterior", "dados_extraidos": data},
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["resultado_calculo"]["saldo_parcelas_calculadas"] == "1234.57"
    )
    assert field["valor"] == "330.00"
    review["aplicacoes"][0]["justificativa"] = ""
    with pytest.raises(PendenciaApuracao):
        validar_revisao_extracao(ExerciciosParcelasDados.model_validate(data))


def test_applied_edit_requires_reason_but_can_be_used_after_manual_review():
    data = review_data()
    field = next(
        f
        for f in data["revisao_extracao"]["documentos"][0]["campos"]
        if f["campo"] == "nome"
    )
    data["nome"] = "NOME CONFERIDO"
    data["revisao_extracao"]["aplicacoes"] = [
        {
            "documento_id": data["revisao_extracao"]["documentos"][0]["id"],
            "campo_id": field["id"],
            "destino": ["nome"],
            "valor_revisado": "NOME CONFERIDO",
        }
    ]
    with pytest.raises(PendenciaApuracao):
        validar_revisao_extracao(ExerciciosParcelasDados.model_validate(data))
    data["revisao_extracao"]["aplicacoes"][0]["justificativa"] = (
        "Nome conferido manualmente com a fonte sintética"
    )
    validar_revisao_extracao(ExerciciosParcelasDados.model_validate(data))


def test_emitter_identity_is_not_extracted_as_employee():
    doc = extrair_documento(
        pages(
            ficha()
            + "\nResponsavel pela emissao\nNome: 123 - EMISSOR SINTETICO Banco/Agencia: 1\nMatricula: 123"
        )
    )
    assert [block["matricula"] for block in doc["blocos"]] == ["000999"]
    assert not any(field["valor"] == "123" for field in doc["campos"])


def docente_com_emissor_antes_da_tabela():
    return (
        "Ficha Financeira referente a: 2025\n"
        "Nome: 000999 - ALFA SINTETICO Banco/Agencia: 1\n"
        "Cargo/Lotacao: PROF MAGIST SUPERIOR\n"
        "Responsavel pela emissao\n"
        "Nome: 123 - EMISSOR SINTETICO Banco/Agencia: 1\n"
        "Matricula: 123\n"
        "Rubrica|Nome Rubrica|R/D|Seq.|JAN|FEV|TOTAL\n"
        "00001|VENCIMENTO BASICO|R|0|3.000,00|0,00|3.000,00\n"
        "98002|CONT. PLANO SEGURIDADE SOCIAL||0|330,00||330,00\n"
        "00750|FERIAS ADICIONAL|R|6|100,00||100,00"
    )


def test_financial_header_resumes_after_emitter_without_assuming_unknown_nature():
    doc = extrair_documento(pages(docente_com_emissor_antes_da_tabela()))
    assert [block["matricula"] for block in doc["blocos"]] == ["000999"]
    assert not any(field["valor"] == "123" for field in doc["campos"])
    entries = [field for field in doc["campos"] if field["campo"] == "rubrica"]
    assert [
        (f["rubrica"], f["competencia"], f["valor"], f["natureza"], f["sequencia"])
        for f in entries
    ] == [
        ("00001", "2025-01", "3000.00", "R", "0"),
        ("00001", "2025-02", "0.00", "R", "0"),
        ("98002", "2025-01", "330.00", None, "0"),
        ("00750", "2025-01", "100.00", "R", "6"),
    ]
    assert entries[2]["estado"] == "AMBIGUO"
    assert all(f["pagina"] == 1 and f["localizador"] for f in entries)


def test_progression_upload_reads_pdf_table_below_emitter(auth_client_user, tmp_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=8)
    for index, line in enumerate(docente_com_emissor_antes_da_tabela().splitlines()):
        pdf.text(10, 15 + index * 6, line)
    path = tmp_path / "ficha-docente-sintetica.pdf"
    pdf.output(str(path))
    response = auth_client_user.post(
        "/api/extrair-pdf",
        data={"tipo_calculo": "progressao", "versao_extracao": "2"},
        files=[("arquivos", (path.name, path.read_bytes(), "application/pdf"))],
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["falhas"] == []
    doc = result["resultados"][0]["extracao"]
    assert doc["versao_leitor"] == "rh_paginas_v5"
    assert doc["blocos"][0]["categoria"] == "DOCENTE"
    assert [block["matricula"] for block in doc["blocos"]] == ["000999"]
    entries = [field for field in doc["campos"] if field["campo"] == "rubrica"]
    assert [field["valor"] for field in entries] == ["3000.00", "0.00", "330.00", "100.00"]


def test_multi_employee_vacation_rows_do_not_inherit_first_person():
    doc = extrair_documento(
        pages(
            "MATRICULA|NOME|VINCULO|EXERCICIO|INICIO|DIAS|PARCELA\n999|ALFA SINTETICO|V1|2025|01/01/2026|10|1\n888|BETA SINTETICO|V2|2025|15/01/2026|5|1"
        )
    )
    assert [block["matricula"] for block in doc["blocos"]] == ["999", "888"]
    entries = [field for field in doc["campos"] if field["campo"] == "periodo_ferias"]
    assert [field["bloco_id"] for field in entries] == [
        block["id"] for block in doc["blocos"]
    ]
    assert [field["fim"] for field in entries] == ["2026-01-10", "2026-01-19"]


def test_native_vacation_table_preserves_person_and_period(tmp_path):
    from app.services.pdf_extraction import extract_pdf_data

    pdf = FPDF(orientation="L")
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for x, value in [
        (10, "MATRICULA"),
        (55, "NOME"),
        (140, "INICIO"),
        (195, "DIAS"),
        (225, "PARCELA"),
    ]:
        pdf.text(x, 15, value)
    for x, value in [
        (10, "999"),
        (55, "ALFA SINTETICO"),
        (140, "01/01/2026"),
        (195, "10"),
        (225, "1"),
    ]:
        pdf.text(x, 25, value)
    path = tmp_path / "ferias-sinteticas.pdf"
    pdf.output(str(path))
    doc = extract_pdf_data(str(path), "v2:substituicao")["_extracao_v2"]
    assert doc["blocos"][0]["matricula"] == "999"
    assert (
        next(field for field in doc["campos"] if field["campo"] == "periodo_ferias")[
            "fim"
        ]
        == "2026-01-10"
    )


def test_invalid_vacation_date_is_not_silently_lost():
    doc = extrair_documento(pages("INICIO|DIAS|PARCELA\n31/02/2026|10|1"))
    field = next(field for field in doc["campos"] if field["campo"] == "periodo_ferias")
    assert field["estado"] == "ILEGIVEL" and field["valor"] is None


def test_changed_row_id_cannot_reuse_another_rows_evidence():
    data = review_data()
    source = next(
        field
        for field in data["revisao_extracao"]["documentos"][0]["campos"]
        if field["campo"] == "rubrica"
    )
    data["revisao_extracao"]["aplicacoes"] = [
        {
            "documento_id": data["revisao_extracao"]["documentos"][0]["id"],
            "campo_id": source["id"],
            "destino": ["exercicios", "devidos", 0, "valor"],
            "registro_id": "ANOTHER",
            "valor_revisado": "1000",
            "justificativa": "Valor conferido",
        }
    ]
    with pytest.raises(PendenciaApuracao):
        validar_revisao_extracao(ExerciciosParcelasDados.model_validate(data))


def test_financial_formatting_is_not_a_change_of_amount():
    data = review_data()
    source = next(
        field
        for field in data["revisao_extracao"]["documentos"][0]["campos"]
        if field["campo"] == "rubrica"
    )
    data["exercicios"]["devidos"][0]["valor"] = "330.000"
    data["revisao_extracao"]["aplicacoes"] = [
        {
            "documento_id": data["revisao_extracao"]["documentos"][0]["id"],
            "campo_id": source["id"],
            "destino": ["exercicios", "devidos", 0, "valor"],
            "registro_id": "D",
            "valor_revisado": "330.000",
        }
    ]
    validar_revisao_extracao(ExerciciosParcelasDados.model_validate(data))


def test_file_failure_cleans_temporary_and_never_discards_next_file(
    auth_client_user, monkeypatch, tmp_path
):
    import tempfile

    from app.routers import calculos_router

    real_tempfile = tempfile.NamedTemporaryFile
    paths = []

    def temporary(*args, **kwargs):
        handle = real_tempfile(*args, dir=tmp_path, **kwargs)
        paths.append(handle.name)
        return handle

    monkeypatch.setattr(calculos_router.tempfile, "NamedTemporaryFile", temporary)
    count = 0

    def read(path, mode):
        nonlocal count
        count += 1
        if count == 1:
            raise ValueError("Sensitive parser exception must not escape")
        return {"_extracao_v2": extrair_documento(pages(ficha()))}

    monkeypatch.setattr(calculos_router, "extract_pdf_data", read)
    response = auth_client_user.post(
        "/api/extrair-pdf",
        data={"tipo_calculo": "abono", "versao_extracao": "2"},
        files=[
            ("arquivos", ("falha.pdf", b"%PDF-1.4", "application/pdf")),
            ("arquivos", ("valido.pdf", b"%PDF-1.4", "application/pdf")),
        ],
    )
    assert response.status_code == 200
    assert len(response.json()["resultados"]) == 1
    assert "Sensitive" not in response.text
    from pathlib import Path

    assert all(not Path(path).exists() for path in paths)


def geometric_financial_pdf(
    path, align="L", continuation=None, next_width=None, emitter=False
):
    pdf = FPDF(orientation="L")
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.text(10, 15, "Ficha Financeira referente a: 2025")
    pdf.text(10, 22, "Nome: 999 - ALFA SINTETICO Banco/Agencia: 1")

    def row(y, values, money_align="L"):
        for x, width, value in values:
            pdf.set_xy(x, y)
            pdf.cell(width, 5, value, align=money_align if x >= 185 else "L")

    row(
        30,
        [
            (10, 30, "Rubrica"),
            (40, 100, "Nome"),
            (140, 20, "R/D"),
            (160, 25, "Seq."),
            (185, 35, "JAN"),
            (220, 35, "FEV"),
            (255, 35, "TOTAL"),
        ],
    )
    row(
        40,
        [
            (10, 30, "98002"),
            (40, 100, "PSS"),
            (140, 20, "D"),
            (160, 25, "0"),
            (185, 35, "330,00"),
        ],
        align,
    )
    if emitter:
        pdf.text(10, 60, "Responsavel pela emissao")
        pdf.text(10, 67, "Nome: 123 - EMISSOR SINTETICO Banco/Agencia: 1")
        pdf.text(10, 74, "Matricula: 123")
    if continuation:
        pdf.add_page(orientation="P") if next_width else pdf.add_page()
        if continuation == "OTHER_PERSON":
            pdf.text(10, 15, "Nome: 888 - BETA SINTETICO Banco/Agencia: 1")
        if continuation == "OTHER_NAME":
            pdf.text(10, 15, "Nome: BETA SINTETICO")
        if continuation == "OTHER_YEAR":
            pdf.text(10, 15, "Ficha Financeira referente a: 2026")
        row(
            30,
            [
                (10, 30, "00750"),
                (40, 100, "FERIAS"),
                (140, 20, "R"),
                (160, 25, "6"),
                (185, 35, "100,00"),
            ],
        )
    pdf.output(str(path))
    return path


def test_right_aligned_amount_is_never_silently_assigned_to_next_competence(tmp_path):
    from app.services.pdf_extraction import extract_pdf_data

    path = geometric_financial_pdf(tmp_path / "direita.pdf", align="R")
    doc = extract_pdf_data(str(path), "v2:abono")["_extracao_v2"]
    entry = next(field for field in doc["campos"] if field["campo"] == "rubrica")
    assert entry["valor"] == "330.00"
    assert entry["competencia"] is None
    assert entry["estado"] == "AMBIGUO"
    assert doc["situacao"] == "PARCIAL" and doc["avisos"]


def test_native_continuation_keeps_occurrence_without_repeated_header(tmp_path):
    from app.services.pdf_extraction import extract_pdf_data

    path = geometric_financial_pdf(
        tmp_path / "continuacao.pdf", continuation="SAME_PERSON"
    )
    doc = extract_pdf_data(str(path), "v2:abono")["_extracao_v2"]
    entries = [field for field in doc["campos"] if field["campo"] == "rubrica"]
    assert [
        (field["rubrica"], field["competencia"], field["valor"], field["pagina"])
        for field in entries
    ] == [("98002", "2025-01", "330.00", 1), ("00750", "2025-01", "100.00", 2)]
    assert doc["situacao"] == "CONCLUIDO"
    assert doc["versao_leitor"] == "rh_paginas_v5"


def test_emitter_footer_does_not_invalidate_employee_table_continuation(tmp_path):
    from app.services.pdf_extraction import extract_pdf_data

    path = geometric_financial_pdf(
        tmp_path / "rodape-emissor.pdf", continuation="SAME_PERSON", emitter=True
    )
    doc = extract_pdf_data(str(path), "v2:rescisao")["_extracao_v2"]
    assert [block["matricula"] for block in doc["blocos"]] == ["999"]
    field = next(
        field
        for field in doc["campos"]
        if field["campo"] == "rubrica" and field["pagina"] == 2
    )
    assert field["valor"] == "100.00" and field["competencia"] == "2025-01"
    assert doc["situacao"] == "CONCLUIDO"


@pytest.mark.parametrize("continuation", ["OTHER_PERSON", "OTHER_YEAR", "OTHER_NAME"])
def test_incompatible_continuation_keeps_value_without_reusing_months(
    tmp_path, continuation
):
    from app.services.pdf_extraction import extract_pdf_data

    path = geometric_financial_pdf(
        tmp_path / "outro-contexto.pdf", continuation=continuation
    )
    doc = extract_pdf_data(str(path), "v2:rescisao")["_extracao_v2"]
    entry = next(
        field
        for field in doc["campos"]
        if field["campo"] == "rubrica" and field["pagina"] == 2
    )
    assert entry["valor"] == "100.00" and entry["competencia"] is None
    assert entry["estado"] == "AMBIGUO" and doc["situacao"] == "PARCIAL"


def test_page_width_change_prevents_geometry_reuse_without_losing_value(tmp_path):
    from app.services.pdf_extraction import extract_pdf_data

    path = geometric_financial_pdf(
        tmp_path / "largura-diferente.pdf", continuation="SAME_PERSON", next_width=True
    )
    doc = extract_pdf_data(str(path), "v2:abono")["_extracao_v2"]
    field = next(
        field
        for field in doc["campos"]
        if field["campo"] == "rubrica" and field["pagina"] == 2
    )
    assert field["valor"] == "100.00" and field["competencia"] is None
    assert doc["situacao"] == "PARCIAL"


def test_late_identity_does_not_claim_previous_unidentified_occurrences():
    doc = extrair_documento(
        pages(
            "Ficha Financeira referente a: 2025\nVinculo: V1\nRubrica|Nome|R/D|Seq.|JAN\n98002|PSS SEM IDENTIFICACAO|D|0|100,00\nNome: 888 - BETA SINTETICO Banco/Agencia: 1\nRubrica|Nome|R/D|Seq.|JAN\n98002|PSS DE BETA|D|0|200,00"
        )
    )
    assert len(doc["blocos"]) == 2
    assert doc["blocos"][0]["matricula"] is None and doc["blocos"][0]["nome"] is None
    assert doc["blocos"][1]["matricula"] == "888"
    assert doc["blocos"][1]["vinculo"] is None
    entries = [field for field in doc["campos"] if field["campo"] == "rubrica"]
    assert [(field["valor"], field["bloco_id"]) for field in entries] == [
        ("100.00", doc["blocos"][0]["id"]),
        ("200.00", doc["blocos"][1]["id"]),
    ]
    assert doc["situacao"] == "PARCIAL"


def test_header_identity_before_facts_can_still_be_completed():
    doc = extrair_documento(
        pages(
            "Ficha Financeira referente a: 2025\nNome: ALFA\nMatricula: 999\nVinculo: V1\nRubrica|Nome|R/D|Seq.|JAN\n98002|PSS|D|0|100,00"
        )
    )
    assert len(doc["blocos"]) == 1
    assert doc["blocos"][0]["matricula"] == "999"
    assert doc["blocos"][0]["nome"] == "ALFA"


@pytest.mark.parametrize(
    "end,expected",
    [("20/01/2026", "AMBIGUO"), ("31/02/2026", "ILEGIVEL"), ("10/01/2026", "EXTRAIDO")],
)
def test_informed_vacation_end_is_checked_against_duration(end, expected):
    doc = extrair_documento(pages(f"INICIO|FIM|DIAS|PARCELA\n01/01/2026|{end}|10|1"))
    field = next(field for field in doc["campos"] if field["campo"] == "periodo_ferias")
    assert field["estado"] == expected
    assert field["fim_calculado"] == "2026-01-10"
    assert field["dias_informados"] == "10"
    assert field["fim"] == ("2026-01-10" if expected == "EXTRAIDO" else None)
    if expected == "AMBIGUO":
        assert field["fim_informado"] == "2026-01-20"


def test_native_explicit_vacation_end_is_not_dropped_from_header(tmp_path):
    from app.services.pdf_extraction import extract_pdf_data

    pdf = FPDF(orientation="L")
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for x, value in [(10, "INICIO"), (65, "FIM"), (120, "DIAS"), (155, "PARCELA")]:
        pdf.text(x, 15, value)
    for x, value in [(10, "01/01/2026"), (65, "20/01/2026"), (120, "10"), (155, "1")]:
        pdf.text(x, 25, value)
    path = tmp_path / "fim-informado.pdf"
    pdf.output(str(path))
    doc = extract_pdf_data(str(path), "v2:substituicao")["_extracao_v2"]
    field = next(field for field in doc["campos"] if field["campo"] == "periodo_ferias")
    assert (
        field["fim_informado"] == "2026-01-20"
        and field["fim_calculado"] == "2026-01-10"
    )
    assert field["fim"] is None and field["estado"] == "AMBIGUO"


def test_native_vacation_continuation_keeps_second_parcel(tmp_path):
    from app.services.pdf_extraction import extract_pdf_data

    pdf = FPDF(orientation="L")
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.text(10, 10, "Nome: 999 - ALFA SINTETICO Banco/Agencia: 1")
    for x, value in [(10, "INICIO"), (65, "DIAS"), (100, "PARCELA")]:
        pdf.text(x, 20, value)
    for x, value in [(10, "01/01/2026"), (65, "10"), (100, "1")]:
        pdf.text(x, 30, value)
    pdf.add_page()
    for x, value in [(10, "01/07/2026"), (65, "5"), (100, "2")]:
        pdf.text(x, 20, value)
    path = tmp_path / "ferias-continuadas.pdf"
    pdf.output(str(path))
    doc = extract_pdf_data(str(path), "v2:substituicao")["_extracao_v2"]
    fields = [field for field in doc["campos"] if field["campo"] == "periodo_ferias"]
    assert [(field["inicio"], field["fim"], field["pagina"]) for field in fields] == [
        ("2026-01-01", "2026-01-10", 1),
        ("2026-07-01", "2026-07-05", 2),
    ]
