"""Regressões sintéticas de consistência, extração e identificação histórica."""
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text, update
from sqlalchemy.orm import Session

from app.db.salary_reference_migration import migrate_salary_references
from app.models.referencias_salariais import ReferenciaSalarial, RetribuicaoReferencia
from app.models.tabelas_salariais import HistoricoCalculo
from app.routers.referencias_salariais_router import listar_referencias
from app.schemas.referencias_salariais import (
    ConsultaSalarial,
    PosicaoSalarial,
    ReferenciaEntrada,
)
from app.services.dados_pdf import extract_calculation_data
from app.services.salary_references import resolve_salary, salvar_referencia
from app.utils.crypto import decrypt_data


@pytest.mark.parametrize("preload", [False, True])
@pytest.mark.parametrize("reader_kind", ["lookup", "listing"])
def test_read_never_mixes_versions_during_concurrent_edit(tmp_path, preload, reader_kind):
    engine = create_engine(f"sqlite:///{tmp_path / 'synthetic.db'}")
    try:
        with engine.begin() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
        migrate_salary_references(engine)
        entrada = ReferenciaEntrada.model_validate({
            "carreira": "MAGISTERIO_SUPERIOR", "vinculo": "EFETIVO", "jornada": "40H",
            "versao_carreira": "SINTETICA", "classe_docente": "Associado", "nivel_docente": 3,
            "inicio_vigencia": "2026-04-01", "estado": "CONFIRMADA", "fonte": "Teste sintético",
            "vencimento_basico": "3000", "retribuicoes": [{"titulacao": "Mestrado", "valor": "1000"}],
        })
        query = ConsultaSalarial.model_validate({**entrada.model_dump(include=set(PosicaoSalarial.model_fields)), "data_referencia": "2026-04-01"})
        with Session(engine) as writer:
            salvar_referencia(writer, entrada, user_id=1)
            writer.commit()
        changed = False

        def concurrent_edit(conn, cursor, statement, parameters, context, executemany):
            nonlocal changed
            sql = statement.lstrip().upper()
            if changed or not sql.startswith("SELECT") or sql.startswith("SELECT COUNT(") or "FROM referencia_salarial" not in statement:
                return
            changed = True
            with engine.begin() as writer:
                writer.execute(update(ReferenciaSalarial).values(vencimento_basico=Decimal(5000)))
                writer.execute(update(RetribuicaoReferencia).values(valor=Decimal(2000)))

        with Session(engine) as reader:
            def read_salary():
                if reader_kind == "listing":
                    result = listar_referencias(db=reader, user=None, pagina=1, tamanho_pagina=1)
                    assert result["total"] == 1
                    assert len(result["itens"]) == 1
                    reference = result["itens"][0]
                    return (Decimal(reference["vencimento_basico"]), Decimal(reference["retribuicoes"][0]["valor"]))
                value, source = resolve_salary(reader, query, "Mestrado")
                pair = (Decimal(source["vencimento"]["valor_decimal"]), Decimal(source["retribuicao"]["valor_decimal"]))
                assert value == sum(pair)
                return pair

            cached = reader.query(ReferenciaSalarial).one() if preload else None
            if cached is not None:
                assert cached.vencimento_basico == Decimal(3000)
                assert cached.retribuicoes[0].valor == Decimal(1000)
            event.listen(engine, "after_cursor_execute", concurrent_edit)
            try:
                # A edição ocorre entre o SELECT principal e qualquer carregamento tardio.
                first = read_salary()
                assert changed
                assert first == (Decimal(3000), Decimal(1000))
                # Mesmo com objetos já carregados, a próxima consulta deve ser atualizada.
                assert read_salary() == (Decimal(5000), Decimal(2000))
                if cached is not None:
                    assert cached.vencimento_basico == Decimal(5000)
                    assert cached.retribuicoes[0].valor == Decimal(2000)
            finally:
                event.remove(engine, "after_cursor_execute", concurrent_edit)
    finally:
        engine.dispose()


def test_listing_paginates_references_without_truncating_rt(auth_client_admin, db_session, salary_reference):
    first, _ = salary_reference(retribuicoes=[
        {"titulacao": "Mestrado", "valor": "1000"},
        {"titulacao": "Doutorado", "valor": "2000"},
    ])
    second, _ = salary_reference(nivel_docente=2, retribuicoes=[
        {"titulacao": "Mestrado", "valor": "1200"},
        {"titulacao": "Doutorado", "valor": "2400"},
    ])
    db_session.commit()
    for page, item, expected in (
        (1, second, {("Mestrado", "1200"), ("Doutorado", "2400")}),
        (2, first, {("Mestrado", "1000"), ("Doutorado", "2000")}),
    ):
        response = auth_client_admin.get("/api/tabelas/referencias", params={"pagina": page, "tamanho_pagina": 1})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["total"] == 2
        assert len(result["itens"]) == 1
        row = result["itens"][0]
        assert row["id"] == item.id
        assert {(rt["titulacao"], rt["valor"]) for rt in row["retribuicoes"]} == expected


@pytest.mark.parametrize("tipo", ["rescisao", "progressao"])
@pytest.mark.parametrize("line, expected", [
    ("", ""), ("Titulação:   \nClasse: Associado", ""),
    ("Titulação: N/A", "N/A"), ("Titulação: Mestrado", "Mestrado"),
])
def test_title_is_unknown_until_extracted_explicitly(tipo, line, expected):
    extracted = extract_calculation_data(line, tipo)
    assert extracted["titulacao"] == expected
    assert extracted["nivel" if tipo == "rescisao" else "nivel_atual"] is None


@pytest.mark.parametrize("tipo", ["rescisao", "progressao"])
def test_missing_extracted_title_blocks_table_salary(auth_client_user, db_session, salary_reference, tipo):
    _, query = salary_reference(retribuicoes=[{"titulacao": "Mestrado", "valor": "900"}])
    db_session.commit()
    data = extract_calculation_data("Documento sintético sem titulação", tipo)
    if tipo == "rescisao":
        data.update(mes_rescisao=4, ano_rescisao=2026, dias_trabalhados=30,
                    referencia_salarial=query.model_dump(mode="json"))
    else:
        data.update(ano_proporcao=2026, salario_antigo=1000, meses_diferenca=1,
                    referencia_nova=query.model_dump(mode="json"))
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": tipo, "dados_extraidos": data})
    assert response.status_code == 400, response.text
    assert response.json()["detail"][0]["type"] == "referencia_salarial_pendente"
    data["titulacao"] = "Mestrado"
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": tipo, "dados_extraidos": data})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("tae", [False, True])
def test_history_pdf_and_retry_use_actual_position(auth_client_user, db_session, salary_reference, monkeypatch, tmp_path, tae):
    position = {"classe_docente": "Associado", "nivel_docente": 3}
    if tae:
        position = {"carreira": "TAE", "classe_docente": None, "nivel_docente": None,
                    "classificacao_tae": "E", "capacitacao_tae": "IV", "padrao_tae": 7}
    item, query = salary_reference(**position)
    db_session.commit()
    payload = {"tipo_calculo": "rescisao", "idempotency_key": str(uuid4()), "dados_extraidos": {
        "referencia_salarial": query.model_dump(mode="json"), "titulacao": "N/A",
        "mes_rescisao": 4, "ano_rescisao": 2026, "dias_trabalhados": 30,
        "classe": "Auxiliar", "nivel": 1,
    }}
    response = auth_client_user.post("/api/calcular", json=payload)
    assert response.status_code == 200, response.text
    row = db_session.get(HistoricoCalculo, response.json()["historico_id"])
    expected_class, expected_level = ("E", 7) if tae else ("ASSOCIADO", 3)
    assert row.classe.upper() == expected_class
    assert row.nivel == expected_level
    snapshot = json.loads(decrypt_data(row.resultado_json))
    assert snapshot["dados_extraidos"]["classe"] == "Auxiliar"
    assert snapshot["dados_utilizados"]["classe"] == row.classe
    assert snapshot["dados_utilizados"]["nivel"] == expected_level
    filtered = auth_client_user.get("/api/historico", params={"pagina": 1, "classe": row.classe})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["itens"][0]["id"] == row.id
    captured = {}

    def fake_pdf(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "synthetic.pdf"
        path.write_bytes(b"%PDF-1.4 synthetic")
        return str(path)

    monkeypatch.setattr("app.routers.calculos_router.generate_pdf_report", fake_pdf)
    exported = auth_client_user.post("/api/exportar-pdf", json={"historico_id": row.id})
    assert exported.status_code == 200, exported.text
    assert captured["dados_extraidos"]["classe"] == row.classe
    assert captured["dados_extraidos"]["nivel"] == expected_level
    item.vencimento_basico = Decimal(9000)
    db_session.commit()
    retry = auth_client_user.post("/api/calcular", json=payload)
    assert retry.status_code == 200, retry.text
    assert retry.json() == response.json()


@pytest.mark.parametrize("manual", [False, True])
def test_progression_records_each_actual_position(auth_client_user, db_session, salary_reference, manual):
    _, old = salary_reference(classe_docente="Adjunto", nivel_docente=2)
    _, new = salary_reference(classe_docente="Associado", nivel_docente=3, vencimento_basico="4000")
    db_session.commit()
    data = {"referencia_antiga": old.model_dump(mode="json"), "referencia_nova": new.model_dump(mode="json"),
            "titulacao": "N/A", "ano_proporcao": 2026, "meses_diferenca": 1}
    if manual:
        data.update(salario_novo=4500, classe_atual="Informada pelo RH", nivel_atual=4)
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": data})
    assert response.status_code == 200, response.text
    row = db_session.get(HistoricoCalculo, response.json()["historico_id"])
    used = json.loads(decrypt_data(row.resultado_json))["dados_utilizados"]
    assert used["classe_antiga"].upper() == "ADJUNTO"
    assert used["nivel_antigo"] == 2
    assert row.classe.upper() == ("INFORMADA PELO RH" if manual else "ASSOCIADO")
    assert row.nivel == (4 if manual else 3)


def test_manual_salary_without_position_does_not_invent_one(auth_client_user, db_session):
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "rescisao", "dados_extraidos": {
        "salario_mensal": 3000, "mes_rescisao": 4, "ano_rescisao": 2026,
    }})
    assert response.status_code == 200, response.text
    row = db_session.get(HistoricoCalculo, response.json()["historico_id"])
    assert row.classe == ""
    assert row.nivel is None
