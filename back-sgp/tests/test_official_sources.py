"""Fontes inteiramente sintéticas: extração não estabelece autenticidade/direito."""

import csv
import io
import json
from datetime import date
from decimal import Decimal
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.salary_reference_migration import migrate_salary_references
from app.models.fontes_oficiais import (
    ImportacaoFonte,
    LinhaImportacaoFonte,
    ReferenciaFuncao,
    migrate_official_sources,
)
from app.models.referencias_salariais import ReferenciaSalarial
from app.schemas.fontes_oficiais import ConfiguracaoFonte
from app.services.official_source_reader import read_source
from app.services.official_sources import coverage_intervals, create_preview

ORIGIN = {
    "titulo": "Fonte sintética",
    "url": "https://www.gov.br/exemplo-sintetico",
    "obtido_em": "2026-10-26",
    "publicado_em": "2026-01-01",
}
BASE = {
    "tipo": "VB",
    "carreira": "MAGISTERIO_SUPERIOR",
    "vinculo": "EFETIVO",
    "jornada": "40H",
    "versao_carreira": "SINTETICA",
    "classe_docente": "Associado",
    "nivel_docente": 3,
    "inicio_vigencia": "2019-08-01",
    "fim_vigencia": "2026-03-31",
    "valor": "3000.125",
}


def csv_data(rows):
    output = io.StringIO()
    fields = list(dict.fromkeys(field for row in rows for field in row))
    writer = csv.DictWriter(output, fields, delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def manual(client, rows, **origin):
    response = client.post(
        "/api/tabelas/fontes/manual",
        json={
            "origem": {**ORIGIN, **origin},
            "linhas": rows,
            "localizador": "Aba sintética, página 2",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def activate(client, batch, ids=None, **extra):
    return client.post(
        f"/api/tabelas/fontes/{batch['id']}/ativar",
        json={
            "linhas": [
                {"id": row["id"], "versao": row["versao"]}
                for row in batch["linhas"]
                if ids is None or row["id"] in ids
            ],
            "conferido_pelo_rh": True,
            **extra,
        },
    )


def test_preview_repeated_headers_missing_date_and_publication_do_not_activate(
    auth_client_admin, db_session
):
    rows = [
        BASE,
        {key: key for key in BASE},
        {**BASE, "jornada": "20H", "valor": "1500"},
        {**BASE, "inicio_vigencia": ""},
    ]
    response = auth_client_admin.post(
        "/api/tabelas/fontes/previa",
        data={"metadados": json.dumps(ORIGIN)},
        files={"arquivo": ("synthetic.csv", csv_data(rows), "text/csv")},
    )
    assert response.status_code == 200, response.text
    batch = response.json()
    assert len(batch["linhas"]) == 3
    assert batch["resumo"] == {
        "PENDENTE": 2,
        "REJEITADA": 1,
        "CONFLITO": 0,
        "ATIVADA": 0,
        "DUPLICADA": 0,
    }
    assert batch["linhas"][0]["dados"]["inicio_vigencia"] == "2019-08-01"
    assert "inicio_vigencia" not in batch["linhas"][2]["dados"]
    assert "inicio_vigencia" in " ".join(batch["rejeicoes"][0]["problemas"])
    assert db_session.query(ReferenciaSalarial).count() == 0


def test_salary_rt_historical_coverage_and_reimport_preserve_confirmed(
    auth_client_admin, db_session
):
    rt = {**BASE, "tipo": "RT", "titulacao": "Mestrado", "valor": "1000.005"}
    april = {
        **BASE,
        "inicio_vigencia": "2026-04-01",
        "fim_vigencia": None,
        "valor": "3500",
    }
    batch = manual(auth_client_admin, [BASE, rt, april])
    assert db_session.query(ReferenciaSalarial).count() == 0
    response = activate(auth_client_admin, batch)
    assert response.status_code == 200, response.text
    assert response.json()["resumo"]["ATIVADA"] == 3
    refs = (
        db_session.query(ReferenciaSalarial)
        .order_by(ReferenciaSalarial.inicio_vigencia)
        .all()
    )
    assert [(r.vencimento_basico, len(r.retribuicoes)) for r in refs] == [
        (Decimal("3000.125"), 1),
        (Decimal(3500), 0),
    ]
    source_rows = db_session.query(LinhaImportacaoFonte).all()
    assert {row.revisado_por for row in source_rows} == {refs[0].conferido_por}
    assert all(row.revisado_em is not None and row.referencia_id for row in source_rows)
    again = activate(auth_client_admin, manual(auth_client_admin, [BASE, rt, april]))
    assert again.json()["resumo"]["DUPLICADA"] == 3
    conflict = activate(
        auth_client_admin, manual(auth_client_admin, [{**BASE, "valor": "9999"}])
    )
    assert conflict.json()["resumo"]["CONFLITO"] == 1
    assert db_session.query(ReferenciaSalarial).count() == 2
    db_session.refresh(refs[0])
    assert refs[0].vencimento_basico == Decimal("3000.125")
    coverage = auth_client_admin.get(
        "/api/tabelas/fontes/cobertura",
        params={"inicio": "2020-01-01", "fim": "2026-12-31"},
    ).json()
    vb = next(row for row in coverage["itens"] if row["componente"] == "VB")
    assert vb["lacunas"] == []
    rt_coverage = next(
        row for row in coverage["itens"] if row["componente"] == "RT: Mestrado"
    )
    assert rt_coverage["lacunas"] == [{"inicio": "2026-04-01", "fim": "2026-12-31"}]


def test_edit_rejected_line_is_validated_and_stale_revision_is_rejected(
    auth_client_admin,
):
    batch = manual(auth_client_admin, [{**BASE, "inicio_vigencia": ""}])
    row = batch["linhas"][0]
    payload = {
        "dados": BASE,
        "localizador": "Página 2, linha 4 conferida",
        "versao": row["versao"],
    }
    response = auth_client_admin.put(
        f"/api/tabelas/fontes/{batch['id']}/linhas/{row['id']}", json=payload
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["linhas"][0]["estado"] == "PENDENTE"
    assert updated["linhas"][0]["original"]["inicio_vigencia"] == ""
    assert (
        auth_client_admin.put(
            f"/api/tabelas/fontes/{batch['id']}/linhas/{row['id']}", json=payload
        ).status_code
        == 409
    )
    assert activate(auth_client_admin, batch).status_code == 409
    assert activate(auth_client_admin, updated).json()["resumo"]["ATIVADA"] == 1
    payload["versao"] += 2
    assert (
        auth_client_admin.put(
            f"/api/tabelas/fontes/{batch['id']}/linhas/{row['id']}", json=payload
        ).status_code
        == 409
    )


def test_rt_only_and_partial_selection_do_not_presume_salary(
    auth_client_admin, db_session
):
    rt = {**BASE, "tipo": "RT", "titulacao": "Mestrado", "valor": "1000"}
    assert (
        activate(auth_client_admin, manual(auth_client_admin, [rt])).json()["resumo"][
            "CONFLITO"
        ]
        == 1
    )
    batch = manual(auth_client_admin, [BASE, rt])
    assert (
        activate(auth_client_admin, batch, ids=[batch["linhas"][0]["id"]]).json()[
            "resumo"
        ]["CONFLITO"]
        == 1
    )
    assert db_session.query(ReferenciaSalarial).count() == 0


def test_overlapping_periods_in_same_preview_are_both_rejected(
    auth_client_admin, db_session
):
    batch = manual(
        auth_client_admin,
        [
            BASE,
            {
                **BASE,
                "inicio_vigencia": "2026-03-01",
                "fim_vigencia": None,
                "valor": "4000",
            },
        ],
    )
    response = activate(auth_client_admin, batch)
    assert response.json()["resumo"]["CONFLITO"] == 2
    assert db_session.query(ReferenciaSalarial).count() == 0


def test_cd_fg_fcc_components_options_and_duplicate_conflicts(
    auth_client_admin, db_session
):
    function = {
        "tipo": "FUNCAO",
        "tipo_funcao": "CD",
        "codigo_funcao": "1",
        "modalidade": "INTEGRAL",
        "componente": "VENCIMENTO",
        "inicio_vigencia": "2019-01-01",
        "valor": "3000",
    }
    rows = [
        function,
        {**function, "componente": "REPRESENTACAO", "valor": "2000"},
        {**function, "modalidade": "OPCAO", "valor": "1800"},
        {**function, "tipo_funcao": "FG", "valor": "500"},
        {**function, "tipo_funcao": "FCC", "valor": "1000"},
    ]
    result = activate(auth_client_admin, manual(auth_client_admin, rows))
    assert result.status_code == 200, result.text
    assert result.json()["resumo"]["ATIVADA"] == 5
    assert db_session.query(ReferenciaFuncao).count() == 5
    assert db_session.query(ReferenciaSalarial).count() == 0
    assert (
        activate(auth_client_admin, manual(auth_client_admin, rows)).json()["resumo"][
            "DUPLICADA"
        ]
        == 5
    )
    assert (
        activate(
            auth_client_admin,
            manual(auth_client_admin, [{**function, "valor": "3333"}]),
        ).json()["resumo"]["CONFLITO"]
        == 1
    )
    assert {
        str(row.valor.normalize()) for row in db_session.query(ReferenciaFuncao)
    } == {"3E+3", "2E+3", "1.8E+3", "5E+2", "1E+3"}
    response = auth_client_admin.get("/api/tabelas/fontes/funcoes")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 5


def test_parser_rejection_cannot_be_activated_without_saving_revision(
    auth_client_admin, db_session
):
    config = ConfiguracaoFonte.model_validate(ORIGIN)
    source = create_preview(
        db_session,
        config,
        "synthetic.csv",
        "0" * 64,
        [
            {
                "dados": BASE,
                "localizador": "Aba 1, linha 2",
                "erro": "Célula ambígua na fonte",
            }
        ],
        1,
    )
    db_session.commit()
    batch = auth_client_admin.get(f"/api/tabelas/fontes/{source.id}").json()
    result = activate(auth_client_admin, batch)
    assert result.json()["resumo"]["REJEITADA"] == 1
    assert db_session.query(ReferenciaSalarial).count() == 0


def test_invalid_pdf_is_rejected_and_manual_preview_remains_available(
    auth_client_admin,
):
    response = auth_client_admin.post(
        "/api/tabelas/fontes/previa",
        data={"metadados": json.dumps(ORIGIN)},
        files={"arquivo": ("synthetic.pdf", b"%PDF-synthetic")},
    )
    assert response.status_code == 422, response.text
    assert "Não foi possível ler a fonte" in response.json()["detail"]
    assert manual(auth_client_admin, [BASE])["resumo"]["PENDENTE"] == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://www.gov.br/exemplo",
        "https://www.gov.br.evil.test",
        "https://localhost",
        "https://user:pass@www.gov.br/x",
    ],
)
def test_manual_origin_requires_official_https_metadata(auth_client_admin, url):
    response = auth_client_admin.post(
        "/api/tabelas/fontes/manual",
        json={
            "origem": {**ORIGIN, "url": url},
            "linhas": [BASE],
            "localizador": "Página 1",
        },
    )
    assert response.status_code == 422


def test_non_admin_cannot_import_activate_or_read_sources(auth_client_user):
    for path in ("", "/catalogo", "/1", "/funcoes", "/cobertura?fim=2026-12-31"):
        assert auth_client_user.get("/api/tabelas/fontes" + path).status_code == 403
    assert (
        auth_client_user.post(
            "/api/tabelas/fontes/manual",
            json={"origem": ORIGIN, "linhas": [BASE], "localizador": "Página 1"},
        ).status_code
        == 403
    )
    assert (
        auth_client_user.post(
            "/api/tabelas/fontes/1/ativar",
            json={"conferido_pelo_rh": True, "linhas": [{"id": 1, "versao": 1}]},
        ).status_code
        == 403
    )


def test_ods_and_xlsx_keep_sheet_date_and_numeric_precision_separate():
    from openpyxl import Workbook

    book = Workbook()
    for index, (name, workload) in enumerate(
        (("20 horas", "20H"), ("40 horas", "40H"))
    ):
        sheet = book.active if index == 0 else book.create_sheet()
        sheet.title = name
        data = {**BASE, "jornada": workload, "valor": "3000.123456789012"}
        sheet.append(list(data))
        sheet.append(list(data.values()))
    data = io.BytesIO()
    book.save(data)
    parsed = read_source(
        data.getvalue(), "synthetic.xlsx", ConfiguracaoFonte.model_validate(ORIGIN)
    )
    assert [(row["dados"]["jornada"], row["dados"]["valor"]) for row in parsed] == [
        ("20H", "3000.123456789012"),
        ("40H", "3000.123456789012"),
    ]
    assert [row["localizador"].split(":")[0] for row in parsed] == [
        "20 horas",
        "40 horas",
    ]
    xml = """<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet><table:table table:name="RT"><table:table-row><table:table-cell><text:p>tipo</text:p></table:table-cell><table:table-cell><text:p>valor</text:p></table:table-cell></table:table-row><table:table-row><table:table-cell><text:p>RT</text:p></table:table-cell><table:table-cell office:value-type="float" office:value="1234.123456789012" /></table:table-row></table:table></office:spreadsheet></office:body></office:document-content>"""
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("content.xml", xml)
    parsed = read_source(
        output.getvalue(), "synthetic.ods", ConfiguracaoFonte.model_validate(ORIGIN)
    )
    assert parsed[0]["dados"] == {"tipo": "RT", "valor": "1234.123456789012"}


def test_wide_columns_use_explicit_contexts_without_workload_or_period_carryover():
    config = ConfiguracaoFonte.model_validate(
        {
            **ORIGIN,
            "leituras": [
                {
                    "aba": "CSV",
                    "colunas": {"valor": "VB20", "inicio_vigencia": "efeitos"},
                    "contexto": {
                        **{
                            k: str(v)
                            for k, v in BASE.items()
                            if k not in ("valor", "jornada", "inicio_vigencia")
                        },
                        "jornada": "20H",
                    },
                },
                {
                    "aba": "CSV",
                    "colunas": {"valor": "VB40", "inicio_vigencia": "efeitos"},
                    "contexto": {
                        **{
                            k: str(v)
                            for k, v in BASE.items()
                            if k not in ("valor", "jornada", "inicio_vigencia")
                        },
                        "jornada": "40H",
                    },
                },
            ],
        }
    )
    rows = read_source(
        b"efeitos;VB20;VB40\n2019-08-01;1500,50;3000,75\nefeitos;VB20;VB40\n;1600;3200\n",
        "synthetic.csv",
        config,
    )
    assert [
        (r["dados"].get("inicio_vigencia"), r["dados"]["jornada"], r["dados"]["valor"])
        for r in rows
    ] == [
        ("2019-08-01", "20H", "1500.50"),
        ("2019-08-01", "40H", "3000.75"),
        (None, "20H", "1600"),
        (None, "40H", "3200"),
    ]


def test_zip_limits_formula_and_migration_are_safe_and_additive(tmp_path):
    from openpyxl import Workbook

    book = Workbook()
    book.active.append(["tipo", "valor"])
    book.active.append(["VB", "=1+2"])
    content = io.BytesIO()
    book.save(content)
    assert read_source(
        content.getvalue(), "synthetic.xlsx", ConfiguracaoFonte.model_validate(ORIGIN)
    )[0]["erro"]
    with pytest.raises(ValueError, match="5 MB"):
        read_source(
            b"x" * (5 * 1024 * 1024 + 1),
            "synthetic.csv",
            ConfiguracaoFonte.model_validate(ORIGIN),
        )
    engine = create_engine(f"sqlite:///{tmp_path / 'synthetic.db'}")
    try:
        with engine.begin() as conn:
            conn.execute(
                text("CREATE TABLE original (id INTEGER PRIMARY KEY, valor TEXT)")
            )
            conn.execute(text("INSERT INTO original VALUES (1, '1234.56')"))
        migrate_salary_references(engine)
        migrate_official_sources(engine)
        migrate_official_sources(engine)
        assert inspect(engine).has_table(ImportacaoFonte.__tablename__)
        with engine.connect() as conn:
            assert (
                conn.execute(text("SELECT valor FROM original")).scalar_one()
                == "1234.56"
            )
    finally:
        engine.dispose()


def test_coverage_gap_boundaries_and_leapday_are_independent():
    covered, gaps = coverage_intervals(
        [(date(2019, 8, 1), date(2024, 2, 28)), (date(2024, 3, 1), None)],
        date(2020, 1, 1),
        date(2026, 12, 31),
    )
    assert gaps == [{"inicio": "2024-02-29", "fim": "2024-02-29"}]
    assert covered[0]["inicio"] == "2020-01-01"


def test_excel_dates_require_date_cell_style_and_plain_year_is_not_effect_date():
    from openpyxl import Workbook

    book = Workbook()
    book.active.append(["tipo", "valor", "inicio_vigencia"])
    book.active.append(["VB", "3000", date(2019, 8, 1)])
    book.active.append(["VB", "3000", 2026])
    output = io.BytesIO()
    book.save(output)
    rows = read_source(
        output.getvalue(), "synthetic.xlsx", ConfiguracaoFonte.model_validate(ORIGIN)
    )
    assert rows[0]["dados"]["inicio_vigencia"] == "2019-08-01"
    assert rows[0]["erro"] is None
    assert rows[1]["erro"]


def test_body_limits_keep_source_upload_separate_from_json(auth_client_admin):
    # Maior que o limite JSON (1 MB), menor que o da fonte (5 MB).
    content = b"formato-nao-suportado\n" + b" " * (1024 * 1024 + 10)
    response = auth_client_admin.post(
        "/api/tabelas/fontes/previa",
        data={"metadados": json.dumps(ORIGIN)},
        files={"arquivo": ("synthetic.bin", content)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["resumo"]["REJEITADA"] == 1
    too_large = auth_client_admin.post(
        "/api/tabelas/fontes/previa",
        data={"metadados": json.dumps(ORIGIN)},
        files={"arquivo": ("synthetic.csv", b"x" * (5 * 1024 * 1024 + 1))},
    )
    assert too_large.status_code == 413


def test_workloads_do_not_collide_and_review_confirmation_is_required(
    auth_client_admin, db_session
):
    batch = manual(
        auth_client_admin,
        [
            BASE,
            {**BASE, "jornada": "20H", "valor": "1500"},
            {**BASE, "jornada": "DE", "valor": "6000"},
        ],
    )
    assert (
        activate(auth_client_admin, batch, conferido_pelo_rh=False).status_code == 422
    )
    assert db_session.query(ReferenciaSalarial).count() == 0
    assert activate(auth_client_admin, batch).json()["resumo"]["ATIVADA"] == 3
    assert {row.vencimento_basico for row in db_session.query(ReferenciaSalarial)} == {
        Decimal("3000.125"),
        Decimal(1500),
        Decimal(6000),
    }


def test_function_period_overlap_is_rejected_by_database(auth_client_admin, db_session):
    from sqlalchemy.exc import IntegrityError

    function = {
        "tipo": "FUNCAO",
        "tipo_funcao": "FG",
        "codigo_funcao": "1",
        "modalidade": "PADRAO_CONFERIDO",
        "componente": "VALOR_FUNCAO",
        "inicio_vigencia": "2019-01-01",
        "valor": "500",
    }
    assert (
        activate(auth_client_admin, manual(auth_client_admin, [function])).json()[
            "resumo"
        ]["ATIVADA"]
        == 1
    )
    row = db_session.query(ReferenciaFuncao).one()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            ReferenciaFuncao(
                estrutura_id=row.estrutura_id,
                inicio_vigencia=date(2020, 1, 1),
                valor=Decimal(600),
                fonte="Sintética",
                conferido_por=1,
                conferido_em=row.conferido_em,
            )
        )
        db_session.flush()
