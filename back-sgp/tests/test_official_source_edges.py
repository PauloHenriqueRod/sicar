"""Limites e ambiguidades; todas as entradas são sintéticas."""

import io
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook
from test_official_sources import BASE, ORIGIN, activate, manual

from app.schemas.fontes_oficiais import ConfiguracaoFonte
from app.services.official_source_reader import read_source


def test_coverage_of_unknown_position_and_title_reports_full_gap(auth_client_admin):
    position = {
        key: BASE[key]
        for key in (
            "carreira",
            "vinculo",
            "jornada",
            "versao_carreira",
            "classe_docente",
            "nivel_docente",
        )
    }
    response = auth_client_admin.post(
        "/api/tabelas/fontes/cobertura/salarial",
        json={
            "posicao": position,
            "inicio": "2020-01-01",
            "fim": "2026-12-31",
            "titulacao": "Mestrado",
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["itens"]
    assert {row["componente"] for row in items} == {"VB", "RT: Mestrado"}
    assert all(
        row["cobertos"] == []
        and row["lacunas"] == [{"inicio": "2020-01-01", "fim": "2026-12-31"}]
        for row in items
    )


def test_coverage_merges_title_spelling_variants_in_same_position(auth_client_admin):
    old = {**BASE, "tipo": "RT", "titulacao": "Mestrado", "valor": "1000"}
    new = {
        **old,
        "inicio_vigencia": "2026-04-01",
        "fim_vigencia": None,
        "titulacao": "MESTRADO",
    }
    basic_new = {**BASE, "inicio_vigencia": "2026-04-01", "fim_vigencia": None}
    assert (
        activate(
            auth_client_admin, manual(auth_client_admin, [BASE, old, basic_new, new])
        ).json()["resumo"]["ATIVADA"]
        == 4
    )
    coverage = auth_client_admin.get(
        "/api/tabelas/fontes/cobertura", params={"fim": "2026-12-31"}
    ).json()
    rt = [item for item in coverage["itens"] if item["componente"].startswith("RT:")]
    assert len(rt) == 1
    assert rt[0]["lacunas"] == []


def test_manual_rejects_personal_fields_and_does_not_treat_zero_as_effect_date(
    auth_client_admin,
):
    response = auth_client_admin.post(
        "/api/tabelas/fontes/manual",
        json={
            "origem": ORIGIN,
            "linhas": [{**BASE, "nome": "Dado sintético fora do contrato"}],
            "localizador": "Página 2",
        },
    )
    assert response.status_code == 422
    batch = manual(auth_client_admin, [{**BASE, "inicio_vigencia": 0}])
    assert batch["resumo"]["REJEITADA"] == 1


def test_numeric_xlsx_keeps_original_decimal_lexeme_without_float_conversion():
    book = Workbook()
    book.active.append(["tipo", "valor"])
    book.active.append(["VB", 1000.125])
    original = io.BytesIO()
    book.save(original)
    modified = io.BytesIO()
    with (
        ZipFile(io.BytesIO(original.getvalue())) as source,
        ZipFile(modified, "w") as target,
    ):
        for name in source.namelist():
            content = source.read(name)
            if name == "xl/worksheets/sheet1.xml":
                content = content.replace(
                    b"<v>1000.125</v>", b"<v>1234.123456789012</v>"
                )
            target.writestr(name, content)
    rows = read_source(
        modified.getvalue(), "synthetic.xlsx", ConfiguracaoFonte.model_validate(ORIGIN)
    )
    assert rows[0]["dados"]["valor"] == "1234.123456789012"


def test_zip_expansion_is_limited():
    archive = io.BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as source:
        source.writestr("content.xml", b"x" * (21 * 1024 * 1024))
    with pytest.raises(ValueError, match="limites"):
        read_source(
            archive.getvalue(),
            "synthetic.ods",
            ConfiguracaoFonte.model_validate(ORIGIN),
        )


def test_source_original_does_not_persist_unmapped_columns():
    rows = read_source(
        b"tipo;valor;coluna_nao_mapeada\nVB;3000;texto_sintetico_externo\n",
        "synthetic.csv",
        ConfiguracaoFonte.model_validate(ORIGIN),
    )
    assert "texto_sintetico_externo" not in json.dumps(rows)


def test_csv_multiline_cells_keep_physical_source_location():
    content = b'tipo;valor;observacao\nVB;3000;"nota\ncontinuada"\nRT;1000;x\n'
    rows = read_source(
        content, "synthetic.csv", ConfiguracaoFonte.model_validate(ORIGIN)
    )
    assert [row["localizador"] for row in rows] == [
        "CSV: linha 2, leitura 1",
        "CSV: linha 4, leitura 1",
    ]


def test_separate_rt_source_only_adds_missing_title_and_preserves_confirmed_values(
    auth_client_admin, db_session
):
    from decimal import Decimal

    from app.models.referencias_salariais import ReferenciaSalarial

    basic = activate(auth_client_admin, manual(auth_client_admin, [BASE]))
    assert basic.json()["resumo"]["ATIVADA"] == 1
    reference = db_session.query(ReferenciaSalarial).one()
    original = (
        reference.vencimento_basico,
        reference.inicio_vigencia,
        reference.fim_vigencia,
        reference.fonte,
        reference.conferido_em,
    )
    rt = {**BASE, "tipo": "RT", "titulacao": "Mestrado", "valor": "1000.005"}
    result = activate(
        auth_client_admin,
        manual(auth_client_admin, [rt], titulo="Outra fonte sintética de RT"),
    )
    assert result.json()["resumo"]["ATIVADA"] == 1
    db_session.refresh(reference)
    assert (
        reference.vencimento_basico,
        reference.inicio_vigencia,
        reference.fim_vigencia,
        reference.fonte,
        reference.conferido_em,
    ) == original
    assert len(reference.retribuicoes) == 1
    assert reference.retribuicoes[0].valor == Decimal("1000.005")
    origins = auth_client_admin.get(
        "/api/tabelas/fontes/origens", params={"referencia_id": reference.id}
    ).json()
    assert origins["total"] == 2
    assert {row["dados"]["tipo"] for row in origins["itens"]} == {"VB", "RT"}
    assert {row["titulo"] for row in origins["itens"]} == {
        ORIGIN["titulo"],
        "Outra fonte sintética de RT",
    }
    assert all(
        row["localizador"] and row["obtido_em"] and row["revisado_em"]
        for row in origins["itens"]
    )
    assert (
        activate(auth_client_admin, manual(auth_client_admin, [rt])).json()["resumo"][
            "DUPLICADA"
        ]
        == 1
    )
    changed = activate(
        auth_client_admin, manual(auth_client_admin, [{**rt, "valor": "1999"}])
    )
    assert changed.json()["resumo"]["CONFLITO"] == 1
    db_session.refresh(reference)
    assert reference.retribuicoes[0].valor == Decimal("1000.005")


def test_rt_append_precision_failure_rolls_back_without_changing_vb(
    auth_client_admin, db_session
):
    from decimal import Decimal

    from app.models.referencias_salariais import ReferenciaSalarial

    assert (
        activate(auth_client_admin, manual(auth_client_admin, [BASE])).json()["resumo"][
            "ATIVADA"
        ]
        == 1
    )
    rt = {
        **BASE,
        "tipo": "RT",
        "titulacao": "Mestrado",
        "valor": "999999999999.123456789012",
    }
    result = activate(auth_client_admin, manual(auth_client_admin, [rt]))
    assert result.json()["resumo"]["CONFLITO"] == 1
    reference = db_session.query(ReferenciaSalarial).one()
    db_session.refresh(reference)
    assert reference.vencimento_basico == Decimal("3000.125")
    assert reference.retribuicoes == []


def test_distinct_row_blocks_do_not_share_workload_or_effect_dates():
    common = {
        key: str(value)
        for key, value in BASE.items()
        if key not in ("valor", "jornada", "inicio_vigencia", "fim_vigencia")
    }
    config = ConfiguracaoFonte.model_validate(
        {
            **ORIGIN,
            "leituras": [
                {
                    "aba": "CSV",
                    "linha_inicial": 1,
                    "linha_final": 2,
                    "colunas": {"valor": "Valor"},
                    "contexto": {
                        **common,
                        "jornada": "20H",
                        "inicio_vigencia": "2019-08-01",
                        "fim_vigencia": "2026-03-31",
                    },
                },
                {
                    "aba": "CSV",
                    "linha_inicial": 4,
                    "linha_final": 5,
                    "colunas": {"valor": "Valor"},
                    "contexto": {
                        **common,
                        "jornada": "40H",
                        "inicio_vigencia": "2026-04-01",
                    },
                },
            ],
        }
    )
    rows = read_source(b"Valor\n1500\n\nValor\n3000\n", "synthetic.csv", config)
    assert [
        (
            row["dados"]["jornada"],
            row["dados"]["inicio_vigencia"],
            row["dados"]["valor"],
        )
        for row in rows
    ] == [("20H", "2019-08-01", "1500"), ("40H", "2026-04-01", "3000")]


def test_repeated_ambiguous_headers_cannot_bypass_preview_row_limit():
    config = ConfiguracaoFonte.model_validate(
        {
            **ORIGIN,
            "leituras": [
                {
                    "aba": "CSV",
                    "colunas": {"valor": "Valor"},
                    "contexto": {"tipo": "VB"},
                }
                for _ in range(30)
            ],
        }
    )
    with pytest.raises(ValueError, match="2000 registros"):
        read_source(b"Valor;Valor\n" * 68, "synthetic.csv", config)


@pytest.mark.parametrize("field", ["valor", "nivel_docente"])
@pytest.mark.parametrize("value", [True, False])
def test_manual_boolean_is_not_coerced_to_money_or_level(
    auth_client_admin, field, value
):
    response = auth_client_admin.post(
        "/api/tabelas/fontes/manual",
        json={
            "origem": ORIGIN,
            "linhas": [{**BASE, field: value}],
            "localizador": "Página 2",
        },
    )
    assert response.status_code == 422


def test_edit_boolean_is_not_coerced_to_money(auth_client_admin):
    batch = manual(auth_client_admin, [BASE])
    row = batch["linhas"][0]
    response = auth_client_admin.put(
        f"/api/tabelas/fontes/{batch['id']}/linhas/{row['id']}",
        json={
            "dados": {**BASE, "valor": True},
            "versao": row["versao"],
            "localizador": row["localizador"],
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "url", ["https://ufpi.br/fonte-sintetica", "https://progep.ufpi.br/fonte-sintetica"]
)
def test_ufpi_official_domain_is_accepted_as_source_metadata(url):
    assert ConfiguracaoFonte.model_validate({**ORIGIN, "url": url}).url == url


def test_excel_time_or_zero_date_is_not_presumed_to_be_an_effect_date():
    from datetime import time

    book = Workbook()
    book.active.append(["tipo", "valor", "inicio_vigencia"])
    book.active.append(["VB", "3000", time(12, 30)])
    book.active["C2"].number_format = "h:mm"
    book.active.append(["VB", "3000", 0])
    book.active["C3"].number_format = "mm-dd-yy"
    output = io.BytesIO()
    book.save(output)
    rows = read_source(
        output.getvalue(), "synthetic.xlsx", ConfiguracaoFonte.model_validate(ORIGIN)
    )
    assert len(rows) == 2
    assert all(row["erro"] for row in rows)
    assert all(
        not str(row["dados"].get("inicio_vigencia", "")).startswith("1899-")
        for row in rows
    )


def ods_document(rows):
    xml = (
        "<office:document-content "
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        '<office:body><office:spreadsheet><table:table table:name="Tabela">'
        + rows
        + "</table:table></office:spreadsheet></office:body></office:document-content>"
    )
    content = io.BytesIO()
    with ZipFile(content, "w") as archive:
        archive.writestr("content.xml", xml)
    return content.getvalue()


@pytest.mark.parametrize("extension", ["csv", "xlsx", "ods"])
def test_missing_mapped_end_date_header_cannot_activate_open_reference(
    auth_client_admin, db_session, extension
):
    from app.models.referencias_salariais import ReferenciaSalarial

    headers, values = ["Valor", "Termino"], ["3000", "2026-03-31"]
    if extension == "csv":
        content = b"Valor;Termino\n3000;2026-03-31\n"
        sheet = "CSV"
    elif extension == "xlsx":
        book = Workbook()
        book.active.append(headers)
        book.active.append(values)
        output = io.BytesIO()
        book.save(output)
        content, sheet = output.getvalue(), book.active.title
    else:
        content = ods_document(
            "".join(
                "<table:table-row>"
                + "".join(
                    f"<table:table-cell><text:p>{value}</text:p></table:table-cell>"
                    for value in row
                )
                + "</table:table-row>"
                for row in (headers, values)
            )
        )
        sheet = "Tabela"
    config = {
        **ORIGIN,
        "leituras": [
            {
                "aba": sheet,
                "colunas": {"valor": "Valor", "fim_vigencia": "Fim"},
                "contexto": {
                    key: str(value)
                    for key, value in BASE.items()
                    if key not in ("valor", "fim_vigencia")
                },
            }
        ],
    }
    response = auth_client_admin.post(
        "/api/tabelas/fontes/previa",
        data={"metadados": json.dumps(config)},
        files={"arquivo": (f"synthetic.{extension}", content)},
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["resumo"]["PENDENTE"] == 0
    assert all(row["estado"] == "REJEITADA" for row in preview["linhas"])
    assert "fim_vigencia" in " ".join(preview["rejeicoes"][0]["problemas"])
    activated = activate(auth_client_admin, preview)
    assert activated.status_code == 200, activated.text
    assert activated.json()["resumo"]["ATIVADA"] == 0
    assert db_session.query(ReferenciaSalarial).count() == 0


def test_incomplete_repeated_header_invalidates_previous_column_mapping():
    config = ConfiguracaoFonte.model_validate(
        {
            **ORIGIN,
            "leituras": [
                {
                    "aba": "CSV",
                    "colunas": {"valor": "Valor", "fim_vigencia": "Fim"},
                    "contexto": {"tipo": "VB"},
                }
            ],
        }
    )
    rows = read_source(
        b"Valor;Fim\n3000;2020-12-31\nValor;Termino\n4000;2021-12-31\nValor;Fim\n5000;\n",
        "synthetic.csv",
        config,
    )
    assert rows[0]["dados"]["fim_vigencia"] == "2020-12-31"
    assert "fim_vigencia" in rows[1]["erro"]
    assert rows[2]["erro"]
    # Cabeçalho completo com célula vazia continua permitindo fim em aberto.
    assert rows[3]["erro"] is None
    assert rows[3]["dados"] == {"tipo": "VB", "valor": "5000"}


def test_ods_grouped_rows_keep_document_order_repetitions_and_locations():
    content = ods_document("""
        <table:table-header-rows><table:table-row><table:table-cell>
          <text:p>Valor</text:p></table:table-cell></table:table-row>
        </table:table-header-rows>
        <table:table-rows><table:table-row><table:table-cell office:value="3000"/>
        </table:table-row></table:table-rows>
        <table:table-row-group>
          <table:table-row table:number-rows-repeated="2"><table:table-cell/></table:table-row>
          <table:table-row-group><table:table-rows>
            <table:table-row table:number-rows-repeated="2">
              <table:table-cell office:value="6000"/>
            </table:table-row>
          </table:table-rows></table:table-row-group>
        </table:table-row-group>
        <table:table-row><table:table-cell office:value="9000"/></table:table-row>
    """)
    config = ConfiguracaoFonte.model_validate(
        {
            **ORIGIN,
            "leituras": [
                {
                    "aba": "Tabela",
                    "colunas": {"valor": "Valor"},
                    "contexto": {
                        key: str(value) for key, value in BASE.items() if key != "valor"
                    },
                }
            ],
        }
    )
    rows = read_source(content, "synthetic.ods", config)
    assert [row["dados"]["valor"] for row in rows] == ["3000", "6000", "6000", "9000"]
    assert all(row["erro"] is None for row in rows)
    assert [row["localizador"] for row in rows] == [
        f"Tabela: linha {number}, leitura 1" for number in (2, 5, 6, 7)
    ]


def test_ods_grouped_repetitions_respect_row_limit():
    content = ods_document("""
        <table:table-row-group><table:table-rows>
          <table:table-row table:number-rows-repeated="2001">
            <table:table-cell office:value="3000"/>
          </table:table-row>
        </table:table-rows></table:table-row-group>
    """)
    with pytest.raises(ValueError, match="2000 linhas"):
        read_source(content, "synthetic.ods", ConfiguracaoFonte.model_validate(ORIGIN))


def test_repeated_header_without_value_cannot_activate_rt_as_basic_salary(
    auth_client_admin, db_session
):
    from decimal import Decimal

    from app.models.referencias_salariais import ReferenciaSalarial

    context = {
        key: str(value)
        for key, value in BASE.items()
        if key not in ("valor", "inicio_vigencia", "fim_vigencia")
    }
    config = {
        **ORIGIN,
        "leituras": [
            {
                "aba": "CSV",
                "contexto": context,
                "colunas": {
                    "valor": "Valor",
                    "inicio_vigencia": "Inicio",
                    "fim_vigencia": "Fim",
                },
            }
        ],
    }
    response = auth_client_admin.post(
        "/api/tabelas/fontes/previa",
        data={"metadados": json.dumps(config)},
        files={
            "arquivo": (
                "synthetic.csv",
                (
                    b"Valor;RT;Inicio;Fim\n3000;1000;2020-01-01;2020-12-31\n"
                    b"RT;Novo VB;Inicio;Fim\n1200;4000;2021-01-01;2021-12-31\n"
                    b"Valor;RT;Inicio;Fim\n4000;1200;2021-01-01;2021-12-31\n"
                ),
            )
        },
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert [row["estado"] for row in preview["linhas"]] == [
        "PENDENTE",
        "REJEITADA",
        "REJEITADA",
        "PENDENTE",
    ]
    assert "valor" in " ".join(preview["linhas"][1]["problemas"])
    result = activate(
        auth_client_admin,
        preview,
        ids=[row["id"] for row in preview["linhas"] if row["estado"] == "PENDENTE"],
    )
    assert result.status_code == 200, result.text
    assert result.json()["resumo"]["ATIVADA"] == 2
    assert [
        ref.vencimento_basico
        for ref in db_session.query(ReferenciaSalarial).order_by(
            ReferenciaSalarial.inicio_vigencia
        )
    ] == [Decimal(3000), Decimal(4000)]


def test_single_recognized_label_in_partial_header_clears_old_mapping():
    config = ConfiguracaoFonte.model_validate(
        {
            **ORIGIN,
            "leituras": [
                {
                    "aba": "CSV",
                    "colunas": {"valor": "Valor", "fim_vigencia": "Fim"},
                    "contexto": {"tipo": "VB"},
                }
            ],
        }
    )
    rows = read_source(
        b"Valor;Fim\n3000;2020-12-31\nNovo VB;Fim\n4000;2021-12-31\n",
        "synthetic.csv",
        config,
    )
    assert rows[0]["erro"] is None
    assert "valor" in rows[1]["erro"]
    assert rows[2]["erro"]


def test_function_data_matching_one_header_label_is_not_a_new_header():
    config = ConfiguracaoFonte.model_validate(
        {
            **ORIGIN,
            "leituras": [
                {
                    "aba": "CSV",
                    "colunas": {
                        "tipo": "Tipo",
                        "componente": "Função",
                        "valor": "Valor",
                    },
                    "contexto": {
                        "tipo_funcao": "FG",
                        "codigo_funcao": "1",
                        "modalidade": "PADRAO",
                        "inicio_vigencia": "2020-01-01",
                    },
                }
            ],
        }
    )
    rows = read_source(
        "Tipo;Função;Valor\nFUNCAO;GRATIFICACAO;3000\n".encode(),
        "synthetic.csv",
        config,
    )
    assert len(rows) == 1
    assert rows[0]["erro"] is None
    assert rows[0]["dados"]["tipo"] == "FUNCAO"
    assert rows[0]["dados"]["valor"] == "3000"


@pytest.mark.parametrize("empty_cells", [64, 65, 16384])
def test_ods_value_after_repeated_empty_columns_is_rejected(
    auth_client_admin, db_session, empty_cells
):
    from app.models.fontes_oficiais import ImportacaoFonte
    from app.models.referencias_salariais import ReferenciaSalarial

    content = ods_document(f'''
        <table:table-row><table:table-cell><text:p>Valor</text:p></table:table-cell></table:table-row>
        <table:table-row><table:table-cell table:number-columns-repeated="{empty_cells}"/>
        <table:table-cell office:value="4000"/></table:table-row>
    ''')
    config = {
        **ORIGIN,
        "leituras": [
            {
                "aba": "Tabela",
                "colunas": {"valor": "Valor"},
                "contexto": {
                    key: str(value) for key, value in BASE.items() if key != "valor"
                },
            }
        ],
    }
    response = auth_client_admin.post(
        "/api/tabelas/fontes/previa",
        data={"metadados": json.dumps(config)},
        files={"arquivo": ("synthetic.ods", content)},
    )
    assert response.status_code == 422, response.text
    assert "64 colunas" in response.json()["detail"]
    assert db_session.query(ImportacaoFonte).count() == 0
    assert db_session.query(ReferenciaSalarial).count() == 0


def test_ods_preserves_internal_empty_columns_and_accepts_only_empty_tail():
    content = ods_document("""
        <table:table-row><table:table-cell/><table:table-cell/><table:table-cell><text:p>Valor</text:p></table:table-cell>
          <table:table-cell table:number-columns-repeated="16381"/></table:table-row>
        <table:table-row><table:table-cell table:number-columns-repeated="2"/><table:table-cell office:value="4000"/>
          <table:table-cell table:number-columns-repeated="16381"/><table:table-cell/>
        </table:table-row>
    """)
    config = ConfiguracaoFonte.model_validate(
        {
            **ORIGIN,
            "leituras": [
                {
                    "aba": "Tabela",
                    "colunas": {"valor": "Valor"},
                    "contexto": {"tipo": "VB"},
                }
            ],
        }
    )
    rows = read_source(content, "synthetic.ods", config)
    assert len(rows) == 1
    assert rows[0]["erro"] is None
    assert rows[0]["dados"] == {"tipo": "VB", "valor": "4000"}
