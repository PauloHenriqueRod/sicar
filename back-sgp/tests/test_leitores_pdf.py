"""Layouts sintéticos: expectativas independentes, sem documentos pessoais."""

import json
from datetime import date
from decimal import Decimal

import pytest
from fpdf import FPDF
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError

from app.db.salary_reference_migration import migrate_salary_references
from app.models.fontes_oficiais import (
    EstruturaIQ,
    ReferenciaIQ,
    migrate_official_sources,
)
from app.schemas.extracao_documentos import DocumentoExtraido
from app.services.extracao_documentos import extrair_documento
from app.services.leitores_pdf.tabelas import ler_tabelas


def pages(*texts):
    return [{"numero": i + 1, "texto": text} for i, text in enumerate(texts)]


def values(doc, key):
    return [f for f in doc["campos"] if f["campo"] == key and f["valor"] is not None]


DOCENTE_HEADER = "20h até mar/2026 20h abr/2026 40h até mar/2026 40h abr/2026 DE até mar/2026 DE abr/2026"


@pytest.mark.parametrize("amount", ["1.000,009", "1.000,00x", "1.00,00", "-1.000,00"])
def test_docente_rejects_incomplete_money_tokens(amount):
    rows = ler_tabelas(pages("Magistério Superior - Vencimento Básico\n" + DOCENTE_HEADER +
                            f"\nA - Assistente 1 {amount} 110,00 200,00 220,00 300,00 330,00"))
    assert rows and all(row.get("erro") and not row["dados"] for row in rows)


def test_docente_rejects_reordered_columns_and_accepts_analyzed_wrapped_header():
    row = "\nA - Assistente 1 100,00 110,00 200,00 220,00 300,00 330,00"
    title = "Magistério Superior - Vencimento Básico\n"
    bad = ler_tabelas(pages(title + "DE abr/2026 DE até mar/2026 40h abr/2026 40h até mar/2026 20h abr/2026 20h até mar/2026" + row))
    assert all(item.get("erro") and not item["dados"] for item in bad)
    good = ler_tabelas(pages(title + "20h até 40h até DE até\nClasse Nível mar/2026 20h abr/2026 mar/2026 40h abr/2026 mar/2026 DE abr/2026" + row))
    assert [(item["dados"]["jornada"], item["dados"]["valor"]) for item in good] == [
        ("20H", "100.00"), ("20H", "110.00"), ("40H", "200.00"), ("40H", "220.00"), ("DE", "300.00"), ("DE", "330.00")]


def test_pdf_context_rejects_line_ranges_before_reading(monkeypatch):
    from app.schemas.fontes_oficiais import ConfiguracaoFonte
    from app.services.official_source_reader import SourceReadError, read_source

    def must_not_read(*args):
        pytest.fail("Intervalos não suportados devem ser rejeitados antes da leitura.")

    monkeypatch.setattr("app.services.pdf_extraction.extract_pdf_data", must_not_read)
    config = ConfiguracaoFonte.model_validate({"titulo": "Fonte sintética", "url": "https://www.gov.br/exemplo", "obtido_em": "2026-11-03", "leituras": [
        {"aba": "PDF", "linha_inicial": 1, "linha_final": 10, "contexto": {"versao_carreira": "historica"}},
        {"aba": "PDF", "linha_inicial": 11, "contexto": {"versao_carreira": "moderna"}},
    ]})
    with pytest.raises(SourceReadError, match="intervalos"):
        read_source(b"%PDF-synthetic", "synthetic.pdf", config)


def test_vacation_continuation_with_identity_before_dates():
    doc = extrair_documento(pages(
        "CACOFERIAS\nMATRICULA|NOME|VINCULO|EXERCICIO|INICIO|DIAS|PARCELA\n123|ALFA SINTETICO|V1|2026|01JAN2026|10|1",
        "123|ALFA SINTETICO|V1|2026|01JUL2026|10|2",
    ))
    assert [(f["pagina"], f["inicio"]) for f in values(doc, "periodo_ferias")] == [(1, "2026-01-01"), (2, "2026-07-01")]


def test_derived_positions_preserve_partial_result_at_field_limit():
    text = "SIAPE\nFicha Financeira referente a: 2026\nNome: 123 - ALFA SINTETICO Banco/Agencia: 1\nCargo/Lotacao: 701200 D 303\nRubrica|Nome|R/D|Seq.|JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO\n"
    text += "00001|VB|R|0|" + "|".join(["1000,00"] * 8) + "\n98002|CONTRIBUICAO|D|0|" + "|".join(["100,00"] * 8)
    doc = extrair_documento(pages(*([text] * 100)))
    assert doc["situacao"] == "PARCIAL" and len(doc["campos"]) <= 2000
    assert values(doc, "rubrica") and values(doc, "cargo_lotacao")
    assert any("derivados" in warning for warning in doc["avisos"])


@pytest.mark.parametrize(
    "job,function,reader,category",
    [
        ("701200 D 303", "", "siape_tae", "TAE"),
        ("705001 6 601", "", "siape_docente", "DOCENTE"),
        ("705002 A 1", "", "siape_substituto", "SUBSTITUTO"),
        ("707001 T 1", "CD 3", "siape_cd", "NAO_IDENTIFICADA"),
        ("701010 E 019", "FG 2", "siape_fg", "TAE"),
    ],
)
def test_financial_profiles_keep_description_and_group_boundaries(
    job, function, reader, category
):
    text = (
        "SIAPE\nFicha Financeira referente a: 2026\nNome: 999 - ALFA SINTETICO Banco/Agencia: 1\n"
        f"Cargo/Lotação: {job} Função/Exerc.: {function} Localização: Dep.IR/SF: 00 T.serv.:\n"
        "Rubrica|Nome|R/D|Seq.|JAN|FEV|TOTAL\n"
        "00001|VENCIMENTO BASICO|R|0|1000,00|0,00|1000,00\n"
        "82922|IQ - 30% - LEI SINTETICA||0|300,00||300,00\n"
        "98002|CONTRIBUICAO|D|0|110,00||110,00\n"
        "98004|CONTRIBUICAO 13||0|10,00||10,00"
    )
    doc = extrair_documento(pages(text))
    assert doc["leitores"][0]["identificador"] == reader
    assert doc["blocos"][0]["categoria"] == category
    financial = values(doc, "rubrica")
    assert [
        (f["rubrica"], f["valor"], f["natureza"], f["natureza_origem"])
        for f in financial
    ] == [
        ("00001", "1000.00", "R", "EXPLICITA"),
        ("00001", "0.00", "R", "EXPLICITA"),
        ("82922", "300.00", "R", "GRUPO"),
        ("98002", "110.00", "D", "EXPLICITA"),
        ("98004", "10.00", "D", "GRUPO"),
    ]
    assert financial[2]["descricao_rubrica"] == "IQ - 30% - LEI SINTETICA"
    assert [(f["valor"], f["competencia"]) for f in values(doc, "percentual_iq")] == [
        ("30", "2026-01")
    ]
    assert not values(doc, "quantidade_anuenios")
    assert [f["valor"] for f in values(doc, "funcao_exercida")] == (
        [function] if function else []
    )
    second = extrair_documento(
        pages(
            text,
            "Ficha Financeira referente a: 2027\nNome: 999 - ALFA SINTETICO Banco/Agencia: 1\nRubrica|Nome|R/D|Seq.|JAN\n98002|CONTRIBUICAO||0|110,00",
        )
    )
    assert (
        next(f for f in values(second, "rubrica") if f["pagina"] == 2)["natureza"]
        is None
    )


def test_unknown_or_ambiguous_layout_does_not_run_generic_capture():
    doc = extrair_documento(
        pages("GRUPO/CARGO: não é um cadastro analisado\nNome: OUTRA PESSOA")
    )
    assert doc["situacao"] == "NAO_SUPORTADO"
    assert not values(doc, "nome") and not values(doc, "cargo_lotacao")
    ambiguous = extrair_documento(
        pages("Ficha Financeira referente a: 2026\nCARGO/EMPREGO\nNome: OUTRA PESSOA")
    )
    assert ambiguous["situacao"] == "NAO_SUPORTADO"
    assert any("Mais de um layout" in w for w in ambiguous["avisos"])


def test_additional_ratio_is_only_a_suggestion_with_two_sources():
    text = "SIAPE\nFicha Financeira referente a: 2024\nNome: 999 - ALFA Banco/Agencia: 1\nRubrica|Nome|R/D|Seq.|JAN\n00001|VENCIMENTO BASICO|R|0|1000,00\n00053|INSALUBRIDADE||0|100,00"
    doc = extrair_documento(pages(text))
    suggestion = values(doc, "percentual_adicional_sugerido")[0]
    assert suggestion["valor"] == "10" and suggestion["sugestao"]
    assert suggestion["estado"] == "AMBIGUO"
    assert set(suggestion["fontes_campo_ids"]) == {
        f["id"] for f in values(doc, "rubrica")
    }
    assert not any(f["campo"] == "concessao_confirmada" for f in doc["campos"])
    repeated = extrair_documento(pages(text + "\n00001|VB COMPLEMENTAR|R|0|100,00"))
    assert not values(repeated, "percentual_adicional_sugerido")


def test_category_comes_from_job_not_employee_name_or_number():
    doc = extrair_documento(
        pages(
            "Ficha Financeira referente a: 2026\nNome: 705002 - PROFESSOR SUBSTITUTO Banco/Agencia: 1\nCargo/Lotação: 701200 D 303\nRubrica|Nome|R/D|Seq.|JAN\n00001|VB|R|0|1000,00"
        )
    )
    assert doc["blocos"][0]["categoria"] == "TAE"
    assert doc["leitores"][0]["identificador"] == "siape_tae"
    assert [f["valor"] for f in values(doc, "classificacao_tae")] == ["D"]
    assert [f["valor"] for f in values(doc, "posicao_tae_observada")] == ["303"]
    assert all(f["ano_referencia"] == 2026 for f in values(doc, "cargo_lotacao"))


def test_column_registration_uses_beneficiary_and_compact_exercise():
    rows = [
        (10, [(10, "DADOS INDIVIDUAIS FUNCIONAIS DO SERVIDOR")]),
        (20, [(10, "Órgão:"), (150, "Matrícula:"), (300, "Ident. única:")]),
        (30, [(10, "123"), (150, "000999"), (300, "888888")]),
        (40, [(10, "Nome:"), (150, "Regime Jurídico:"), (300, "Situação serv.:")]),
        (50, [(10, "ALFA SINTETICO"), (150, "EST TEMPORARIO"), (300, "ATIVO")]),
        (70, [(10, "CARGO EMPREGO")]),
        (80, [(10, "GRUPO/CARGO : 705 / 002 - PROFESSOR SUBSTITUTO")]),
        (90, [(10, "CLASSE : A NIVEL : 001 EXERCICIO: 29FEV2024")]),
        (100, [(10, "JORNADA DE TRABALHO")]),
        (110, [(10, "CODIGO - 40 DESCRICAO - 40 HORAS SEMANAIS")]),
        (130, [(10, "EXERCICIO: 01JAN2000")]),
    ]
    words = [
        {"top": y, "x0": x, "x1": x + min(100, len(text) * 4), "text": text}
        for y, cells in rows
        for x, text in cells
    ]
    text = "\n".join(" ".join(t for _, t in cells) for _, cells in rows)
    doc = extrair_documento(
        [
            {**pages(text)[0], "palavras": words, "texto_original": text},
            {
                "numero": 2,
                "texto": "DATA OPCAO VINC. RPC:\nRPPS DATA ACAO JUDICIAL:\nAUTORIZA ACESSO IRPF:\nGRUPO/CARGO: seção de porte de arma, sem relação com o cargo funcional\nEXERCICIO: 01JAN2000",
            },
        ]
    )
    assert [f["valor"] for f in values(doc, "matricula")] == ["000999"]
    assert [f["valor"] for f in values(doc, "nome")] == ["ALFA SINTETICO"]
    assert [f["valor"] for f in values(doc, "inicio_exercicio")] == ["2024-02-29"]
    assert [f["valor"] for f in values(doc, "jornada")] == ["40H"]
    assert "PROFESSOR SUBSTITUTO" in values(doc, "cargo_lotacao")[0]["valor"]
    assert not any(f["valor"] == "888888" for f in doc["campos"])
    assert len(doc["blocos"]) == 1 and doc["blocos"][0]["paginas"] == [1, 2]
    assert len(values(doc, "cargo_lotacao")) == 1


def vacation_form():
    return (
        "SIAPECAD\nHISTORICODEFERIASDOSERVIDOR\nNOME:ALFA SINTETICO\nMATRICULA:999\nEXERCICIO:2024\n"
        "PARCELA:01 28FEV2024A01MAR2024\nQTDEDEDIAS:003\nPARCELACANCELADA:NAO\n"
        "PARCELA:02 01JUL2024A10JUL2024\nQTDEDEDIAS:010\nPARCELACANCELADA:SIM\n"
        "PARCELA:03 01AGO2024A10AGO2024\nQTDEDEDIAS:010\nPARCELACANCELADA:NAO\n"
        "DTDEINTERRUPCAO:05AGO2024\nDTINICIODASFERIASINTERROMPIDA:\n01OUT2024DIASRESTANTES:06\n"
        "PARCELA:04 01OUT2024A06OUT2024\nQTDEDEDIAS:006\nPARCELACANCELADA:NAO\n"
        "PARCELADECONTINUACAOPOR\nINTERRUPCAO"
    )


def test_form_vacations_keep_four_parcels_states_and_ambiguous_end():
    doc = extrair_documento(pages(vacation_form()))
    entries = values(doc, "periodo_ferias")
    assert len(entries) == 4
    assert [
        (f["parcela"], f["inicio"], f["fim"], f["cancelada"]) for f in entries[:2]
    ] == [
        ("01", "2024-02-28", "2024-03-01", False),
        ("02", "2024-07-01", "2024-07-10", True),
    ]
    assert entries[2]["data_interrupcao"] == "2024-08-05"
    assert (
        entries[2]["reinicio"] == "2024-10-01" and entries[2]["dias_restantes"] == "06"
    )
    assert entries[2]["estado"] == "AMBIGUO" and entries[2]["fim"] is None
    assert entries[3]["continuacao"] and entries[3]["fim"] is None
    assert all(
        f["pagina"] == 1 and f["leitor_id"] == "cacoferias_formulario" for f in entries
    )


def test_retroactive_docente_order_is_separate_from_issuer_and_publication():
    text = (
        "MINISTÉRIO DA EDUCAÇÃO\nUNIVERSIDADE FEDERAL DO PIAUÍ\nPORTARIA Nº 900 / 2026 - SRH (11.04)\n"
        "Teresina-PI, 20 de Fevereiro de 2026\nRESOLVE:\n"
        "Autorizar a progressão funcional RETROATIVA, por desempenho acadêmico, ao (à) Professor(a) "
        "MS-A-Denominação Assistente-1-DE-ALFA SINTETICO, lotado(a) no curso sintético, "
        "para MS-A-Denominação Assistente-2, a partir de 05.02.2026.\n"
        "(Assinado digitalmente em 21/02/2026)\nMatrícula: 7777777"
    )
    doc = extrair_documento(pages(text))
    assert doc["layout"] == "PORTARIA_UFPI_DOCENTE"
    assert [f["valor"] for f in values(doc, "nome")] == ["ALFA SINTETICO"]
    assert [f["valor"] for f in values(doc, "classe_origem")] == ["A"]
    assert [f["valor"] for f in values(doc, "nivel_destino")] == ["2"]
    assert not values(doc, "matricula") and not values(doc, "data_publicacao")


def test_salary_comparisons_keep_explicit_effects_and_unknown_beginning():
    tae = ler_tabelas(
        pages(
            "Nível de classificação A\nEfeitos financeiros a partir de 1º de janeiro de 2025 e 1º de abril de 2026\n1 1.000,00 1.100,00\nPadrão\n2 1.010,00 1.111,00"
        )
    )
    assert [
        (r["dados"]["padrao_tae"], r["dados"]["inicio_vigencia"], r["dados"]["valor"])
        for r in tae
    ] == [
        (1, "2025-01-01", "1000.00"),
        (1, "2026-04-01", "1100.00"),
        (2, "2025-01-01", "1010.00"),
        (2, "2026-04-01", "1111.00"),
    ]
    docente = ler_tabelas(
        pages(
            "Magistério Superior – Vencimento Básico\n20h até mar/2026 20h abr/2026 40h até mar/2026 40h abr/2026 DE até mar/2026 DE abr/2026\nA – Assistente 1 R$ 100,00 R$ 110,00 R$ 200,00 R$ 220,00 R$ 300,00 R$ 330,00"
        )
    )
    assert [r["dados"]["valor"] for r in docente] == [
        "100.00",
        "110.00",
        "200.00",
        "220.00",
        "300.00",
        "330.00",
    ]
    assert [r["dados"]["jornada"] for r in docente] == [
        "20H",
        "20H",
        "40H",
        "40H",
        "DE",
        "DE",
    ]
    assert "inicio_vigencia" not in docente[0]["dados"]
    assert docente[0]["dados"]["fim_vigencia"] == "2026-03-31"
    assert docente[1]["dados"]["inicio_vigencia"] == "2026-04-01"
    assert not any(r["dados"]["tipo"] == "RT" for r in docente)


def test_iq_multiline_schooling_keeps_text_after_centered_percentage():
    rows = ler_tabelas(
        pages(
            "Nível de classificação A\nEfeitos financeiros a partir de 1º de janeiro de 2025\n1 1.000,00 1.100,00",
            "Tabela de Percentuais de Incentivo à Qualificação\nEnsino médio profissionalizante ou ensino médio com curso\n20%\ntécnico completo\nEspecialização, com carga horária igual ou superior a\n30%\n360 horas\nMestrado 52%",
        )
    )
    iq = [r["dados"] for r in rows if r["dados"].get("tipo") == "IQ"]
    assert [(r["titulacao"], r["valor"]) for r in iq] == [
        (
            "Ensino médio profissionalizante ou ensino médio com curso técnico completo",
            "20",
        ),
        ("Especialização, com carga horária igual ou superior a 360 horas", "30"),
        ("Mestrado", "52"),
    ]
    assert all("inicio_vigencia" not in r for r in iq)


def test_anexo_cut_year_is_not_completed_from_filename_or_other_table():
    rows = ler_tabelas(
        pages(
            "ANEXO CCXXIV\nLei 11.091\nCargos do Nível D:\nEFEITOS FINANCEIROS A PARTIR DE 1º DE JANEIRO DE 2025\nEFEITOS FINANCEIROS A PARTIR DE 1º DE ABRIL DE 2\nP17 900,00 1 1 1.000,00 1.100,00"
        )
    )
    assert len(rows) == 2
    assert rows[0]["dados"]["inicio_vigencia"] == "2025-01-01"
    assert "inicio_vigencia" not in rows[1]["dados"]
    assert rows[0]["original"]["situacao_anterior"]["valor"] == "900.00"


def test_anexo_old_capacity_columns_are_not_new_patterns():
    text = "ANEXO CCXXIV\nLei 11.091\nCargos do Nível D:\nEFEITOS FINANCEIROS A PARTIR DE 1º DE JANEIRO DE 2025\n1º DE MAIO I II III IV DE 2023\nP17 900,00 1 1 1.000,00 1.100,00"
    words = [
        {"text": label, "top": 10, "x0": x, "x1": x + 2}
        for label, x in zip(("I", "II", "III", "IV"), (110, 122, 134, 146), strict=True)
    ]
    words.extend(
        {"text": label, "top": 10, "x0": x, "x1": x + 2}
        for label, x in (("1º", 20), ("DE", 30), ("MAIO", 50))
    )
    words.extend(
        {"text": label, "top": 20, "x0": x, "x1": x + 2}
        for label, x in (
            ("P17", 30),
            ("900,00", 60),
            ("1", 110),
            ("1", 170),
            ("1.000,00", 270),
            ("1.100,00", 470),
        )
    )
    rows = ler_tabelas([{**pages(text)[0], "palavras": words}])
    assert len(rows) == 3
    assert rows[-1]["dados"] == {
        "tipo": "VB",
        "carreira": "TAE",
        "classificacao_tae": "D",
        "capacitacao_tae": "I",
        "padrao_tae": 1,
        "valor": "900.00",
        "inicio_vigencia": "2023-05-01",
    }


def test_pdf_source_worker_preview_does_not_activate_or_assume_context(
    auth_client_admin, tmp_path, db_session
):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=9)
    for i, line in enumerate(
        [
            "Nivel de classificacao A",
            "Efeitos financeiros a partir de 1 de janeiro de 2025 e 1 de abril de 2026",
            "1 1.000,00 1.100,00",
        ]
    ):
        pdf.text(10, 15 + i * 6, line)
    path = tmp_path / "tabela-sintetica.pdf"
    pdf.output(str(path))
    origin = {
        "titulo": "Exemplo sintético",
        "url": "https://www.gov.br/exemplo",
        "obtido_em": "2026-11-03",
        "publicado_em": "2026-02-01",
    }
    response = auth_client_admin.post(
        "/api/tabelas/fontes/previa",
        data={"metadados": json.dumps(origin)},
        files={"arquivo": (path.name, path.read_bytes(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    rows = response.json()["linhas"]
    assert len(rows) == 2 and all(r["estado"] == "REJEITADA" for r in rows)
    assert rows[0]["dados"]["inicio_vigencia"] == "2025-01-01"
    assert rows[0]["original"]["pagina"] == 1
    assert "jornada" not in rows[0]["dados"] and "vinculo" not in rows[0]["dados"]


def test_iq_review_activation_duplicate_and_conflict(auth_client_admin, db_session):
    origin = {
        "titulo": "Fonte IQ sintética",
        "url": "https://www.gov.br/exemplo",
        "obtido_em": "2026-11-03",
    }

    def preview(value):
        response = auth_client_admin.post(
            "/api/tabelas/fontes/manual",
            json={
                "origem": origin,
                "localizador": "Página 1",
                "linhas": [
                    {
                        "tipo": "IQ",
                        "titulacao": "Doutorado sintético",
                        "valor": value,
                        "inicio_vigencia": "2025-01-01",
                    }
                ],
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def activate(batch):
        response = auth_client_admin.post(
            f"/api/tabelas/fontes/{batch['id']}/ativar",
            json={
                "linhas": [
                    {"id": r["id"], "versao": r["versao"]} for r in batch["linhas"]
                ],
                "conferido_pelo_rh": True,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["linhas"][0]["estado"]

    first = preview("75")
    assert db_session.query(ReferenciaIQ).count() == 0
    assert activate(first) == "ATIVADA"
    assert activate(preview("75")) == "DUPLICADA"
    assert activate(preview("80")) == "CONFLITO"
    reference = db_session.query(ReferenciaIQ).one()
    assert reference.valor == Decimal(75) and reference.inicio_vigencia == date(
        2025, 1, 1
    )
    coverage = auth_client_admin.get(
        "/api/tabelas/fontes/cobertura?tipo=IQ&inicio=2020-01-01&fim=2026-12-31"
    ).json()
    assert coverage["itens"][0]["lacunas"] == [
        {"inicio": "2020-01-01", "fim": "2024-12-31"}
    ]


def test_iq_additive_migration_is_repeatable_and_rejects_overlap_in_temporary_db():
    engine = create_engine("sqlite://")
    try:
        migrate_salary_references(engine)
        migrate_official_sources(engine)
        migrate_official_sources(engine)
        assert {"estrutura_iq", "referencia_iq"} <= set(
            inspect(engine).get_table_names()
        )
        with engine.begin() as connection:
            structure = connection.execute(
                EstruturaIQ.__table__.insert().values(
                    chave="sintetico", titulacao="Escolaridade sintética"
                )
            ).inserted_primary_key[0]
            values = {
                "estrutura_id": structure,
                "inicio_vigencia": date(2020, 1, 1),
                "fim_vigencia": date(2025, 12, 31),
                "valor": Decimal("30.5"),
                "fonte": "sintética",
                "conferido_por": 1,
                "conferido_em": date(2026, 11, 3),
            }
            connection.execute(ReferenciaIQ.__table__.insert().values(**values))
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                ReferenciaIQ.__table__.insert().values(
                    **{**values, "inicio_vigencia": date(2021, 1, 1)}
                )
            )
        migrate_official_sources(engine)
        with engine.connect() as connection:
            assert connection.execute(
                select(ReferenciaIQ.valor)
            ).scalar_one() == Decimal("30.5")
    finally:
        engine.dispose()


def test_file_metadata_correlates_same_named_files_and_keeps_valid_ones(
    auth_client_user, tmp_path
):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=9)
    for index, text in enumerate(vacation_form().splitlines()):
        pdf.text(10, 15 + index * 5, text)
    path = tmp_path / "sintetico.pdf"
    pdf.output(str(path))
    response = auth_client_user.post(
        "/api/extrair-pdf",
        data={
            "tipo_calculo": "substituicao",
            "versao_extracao": "2",
            "metadados_arquivos": json.dumps(
                [
                    {"id": "fonte_a", "categoria": "financeira"},
                    {"id": "fonte_b", "categoria": "ferias"},
                ]
            ),
        },
        files=[
            ("arquivos", ("igual.pdf", path.read_bytes(), "application/pdf")),
            ("arquivos", ("igual.pdf", b"%PDF-invalido", "application/pdf")),
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (
        body["resultados"][0]["arquivo_id"] == "fonte_a"
        and body["falhas"][0]["arquivo_id"] == "fonte_b"
    )
    doc = body["resultados"][0]["extracao"]
    assert doc["categoria_informada"] == "financeira" and doc["layout"] == "CACOFERIAS"
    assert any("difere" in warning for warning in doc["avisos"])


def test_previous_reader_snapshots_still_validate_without_new_metadata():
    doc = extrair_documento(pages("Documento desconhecido"))
    for version in ("rh_paginas_v1", "rh_paginas_v2", "rh_paginas_v3", "rh_paginas_v4"):
        legacy = {
            k: v
            for k, v in doc.items()
            if k not in ("leitores", "arquivo_id", "categoria_informada")
        }
        legacy["versao_leitor"] = version
        for field in legacy["campos"]:
            field.pop("leitor_id", None)
            field.pop("leitor_versao", None)
        parsed = DocumentoExtraido.model_validate(legacy)
        assert parsed.versao_leitor == version
        assert parsed.model_dump(mode="json") == legacy
