"""Expectativas independentes; datas e valores não correspondem a servidores reais."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.salary_reference_migration import migrate_salary_references
from app.models.referencias_salariais import ReferenciaSalarial
from app.models.tabelas_salariais import HistoricoCalculo, TabelaVencimentoBasico
from app.schemas.referencias_salariais import ReferenciaEntrada
from app.services.salary_references import ReferenciaSalarialPendente, resolve_salary


def test_change_midyear_and_leapday(db_session, salary_reference):
    _, old = salary_reference(
        inicio_vigencia="2024-02-29",
        fim_vigencia="2026-03-31",
        vencimento_basico="3100",
        retribuicoes=[{"titulacao": "Mestrado", "valor": "1000"}],
    )
    _, new = salary_reference(
        inicio_vigencia="2026-04-01",
        vencimento_basico="3500",
        retribuicoes=[{"titulacao": "Mestrado", "valor": "1200"}],
    )
    assert resolve_salary(
        db_session,
        old.model_copy(update={"data_referencia": date(2026, 3, 31)}),
        "Mestrado",
    )[0] == Decimal(4100)
    assert resolve_salary(db_session, new, "Mestrado")[0] == Decimal(4700)
    assert resolve_salary(db_session, old)[0] == Decimal(3100)
    with pytest.raises(ReferenciaSalarialPendente):
        resolve_salary(
            db_session, old.model_copy(update={"data_referencia": date(2024, 2, 28)})
        )


def test_workloads_contracts_positions_and_career_versions_do_not_collide(
    db_session, salary_reference
):
    cases = [
        ({"jornada": "20H"}, "2100"),
        ({"jornada": "40H"}, "4200"),
        ({"jornada": "DE"}, "6300"),
        ({"jornada": "40H", "vinculo": "SUBSTITUTO"}, "4500"),
        ({"jornada": "40H", "versao_carreira": "NOVA ESTRUTURA"}, "4800"),
        ({"jornada": "40H", "nivel_docente": 2}, "4900"),
    ]
    for dimensions, expected in cases:
        _, query = salary_reference(**dimensions, vencimento_basico=expected)
        assert resolve_salary(db_session, query)[0] == Decimal(expected)
    _, tae = salary_reference(
        carreira="TAE",
        classe_docente=None,
        nivel_docente=None,
        classificacao_tae="D",
        capacitacao_tae="IV",
        padrao_tae=1,
        vencimento_basico="2800",
    )
    assert resolve_salary(db_session, tae)[0] == Decimal(2800)
    with pytest.raises(ReferenciaSalarialPendente):
        resolve_salary(db_session, tae.model_copy(update={"capacitacao_tae": "III"}))


def test_rt_never_borrows_from_different_period_or_workload(
    db_session, salary_reference
):
    salary_reference(
        fim_vigencia="2026-03-31",
        retribuicoes=[{"titulacao": "Mestrado", "valor": "900"}],
    )
    salary_reference(
        jornada="DE", retribuicoes=[{"titulacao": "Mestrado", "valor": "2000"}]
    )
    _, query = salary_reference(inicio_vigencia="2026-04-01")
    with pytest.raises(ReferenciaSalarialPendente, match="RT compatível"):
        resolve_salary(db_session, query, "Mestrado")


@pytest.mark.parametrize("state", ["PENDENTE", "INATIVA"])
def test_unconfirmed_is_not_used(db_session, salary_reference, state):
    _, query = salary_reference(estado=state)
    with pytest.raises(ReferenciaSalarialPendente):
        resolve_salary(db_session, query)


def test_legacy_year_is_never_proof_or_fallback(db_session, salary_reference):
    db_session.add(
        TabelaVencimentoBasico(classe="Adjunto", nivel=1, ano=2020, valor=9999)
    )
    db_session.flush()
    with pytest.raises(ReferenciaSalarialPendente):
        resolve_salary(db_session, None)
    _, query = salary_reference(estado="PENDENTE")
    with pytest.raises(ReferenciaSalarialPendente):
        resolve_salary(db_session, query)


@pytest.mark.parametrize(
    "start,end",
    [("2026-01-15", None), ("2026-02-28", "2026-04-01"), ("2025-01-01", "2026-01-15")],
)
def test_overlaps_and_inclusive_boundary_rejected(
    db_session, salary_reference, start, end
):
    salary_reference(fim_vigencia="2026-02-28")
    with pytest.raises(ValueError, match="sobreposta"):
        salary_reference(inicio_vigencia=start, fim_vigencia=end)


def test_database_trigger_rejects_direct_sql_overlap(db_session, salary_reference):
    item, _ = salary_reference()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(
            ReferenciaSalarial.__table__.insert().values(
                estrutura_id=item.estrutura_id,
                inicio_vigencia=date(2026, 2, 1),
                vencimento_basico=1,
                estado="CONFIRMADA",
                fonte="sintética",
            )
        )
    other, _ = salary_reference(estado="PENDENTE", inicio_vigencia="2026-02-01")
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(
            text("UPDATE referencia_salarial SET estado='CONFIRMADA' WHERE id=:id"),
            {"id": other.id},
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"fim_vigencia": "2025-01-01"},
        {"vencimento_basico": "abc"},
        {"vencimento_basico": "NaN"},
        {"vencimento_basico": "1.0000000000001"},
        {"padrao_tae": 1},
        {"nivel_docente": None},
        {
            "retribuicoes": [
                {"titulacao": "Mestrado", "valor": "1"},
                {"titulacao": " mestrado ", "valor": "2"},
            ]
        },
    ],
)
def test_invalid_reference_contract_rejected(changes):
    values = {
        "carreira": "MAGISTERIO_SUPERIOR",
        "vinculo": "EFETIVO",
        "jornada": "40H",
        "versao_carreira": "SINTÉTICA",
        "classe_docente": "Adjunto",
        "nivel_docente": 1,
        "inicio_vigencia": "2026-04-01",
        "vencimento_basico": "3000",
        "fonte": "sintética",
    }
    with pytest.raises(ValidationError):
        ReferenciaEntrada.model_validate({**values, **changes})


def test_additive_migration_report_dryrun_repeat_and_recovery(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'salarios_test.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE tabela_vencimento_basico (id INTEGER PRIMARY KEY, classe TEXT, nivel INTEGER, ano INTEGER, valor FLOAT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO tabela_vencimento_basico VALUES (1, 'D', 2, 2020, 3000.25), (2, 'E', 1, 2025, 0.1234567890123)"
            )
        )
    before = None
    with engine.connect() as conn:
        before = conn.execute(
            text("SELECT * FROM tabela_vencimento_basico ORDER BY id")
        ).all()
    report = migrate_salary_references(engine, dry_run=True)
    assert report["copiados_ou_atualizados"] == 2
    assert not inspect(engine).has_table("referencia_salarial")
    assert report["registros"][0]["conversao_sem_alteracao"] is True
    assert report["registros"][1]["valor_decimal"] is None
    assert all(r["estado"] == "PENDENTE" for r in report["registros"])
    assert migrate_salary_references(engine)["copiados_ou_atualizados"] == 2
    assert migrate_salary_references(engine)["inalterados"] == 2
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT * FROM tabela_vencimento_basico ORDER BY id")
            ).all()
            == before
        )
        assert (
            conn.execute(text("SELECT COUNT(*) FROM referencia_salarial")).scalar_one()
            == 0
        )
    # Recuperação conservadora: código anterior encontra exatamente o legado original.
    # Uma nova execução é segura, sem recriar qualquer salário confirmado.
    engine.dispose()


def test_api_pending_is_specific_and_does_not_save_history(
    auth_client_user, db_session
):
    result = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "rescisao",
            "dados_extraidos": {"mes_rescisao": 4, "ano_rescisao": 2026},
        },
    )
    assert result.status_code == 400
    assert result.json()["detail"][0]["type"] == "referencia_salarial_pendente"
    assert db_session.query(HistoricoCalculo).count() == 0


def test_api_conflicts_and_exact_decimal_contract(auth_client_admin):
    payload = {
        "carreira": "TAE",
        "vinculo": "EFETIVO",
        "jornada": "40H",
        "versao_carreira": "SINTÉTICA",
        "classificacao_tae": "D",
        "padrao_tae": 1,
        "inicio_vigencia": "2026-04-01",
        "vencimento_basico": "3000.125",
        "fonte": "Tabela sintética",
        "estado": "CONFIRMADA",
    }
    created = auth_client_admin.post("/api/tabelas/referencias", json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["vencimento_basico"] == "3000.125"
    assert (
        auth_client_admin.post("/api/tabelas/referencias", json=payload).status_code
        == 409
    )
    assert (
        auth_client_admin.get(
            "/api/tabelas/referencias?data_referencia=2026-03-31"
        ).json()["total"]
        == 0
    )
    assert (
        auth_client_admin.get(
            "/api/tabelas/referencias?data_referencia=2026-04-01"
        ).json()["total"]
        == 1
    )


def test_reference_management_requires_admin(auth_client_user):
    assert auth_client_user.get("/api/tabelas/referencias").status_code == 403
    assert auth_client_user.get("/api/tabelas/pendencias-legadas").status_code == 403


def test_duplicate_drafts_rejected_by_database(db_session, salary_reference):
    salary_reference(estado="PENDENTE")
    with pytest.raises(IntegrityError), db_session.begin_nested():
        salary_reference(estado="INATIVA")


def test_canonical_identity_and_precision_loss_are_not_silently_accepted(
    db_session, salary_reference
):
    salary_reference()
    with pytest.raises(ValueError, match="sobreposta"):
        salary_reference(classe_docente="  ADJUNTO  ", vinculo=" efetivo ")
    with pytest.raises(ValueError, match="precisão"), db_session.begin_nested():
        salary_reference(jornada="20H", vencimento_basico="9876543210.123456789012")


def test_progression_selects_each_date_and_integrates_final_rounding(
    auth_client_user, db_session, salary_reference
):
    _, old = salary_reference(fim_vigencia="2026-03-31", vencimento_basico="1000.005")
    _, new = salary_reference(
        inicio_vigencia="2026-04-01", vencimento_basico="1001.010"
    )
    db_session.commit()
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "progressao",
            "dados_extraidos": {
                "referencia_antiga": old.model_dump(mode="json"),
                "referencia_nova": new.model_dump(mode="json"),
                "titulacao": "N/A",
                "insalubridade": 0,
                "dias_proporcionais": 15,
                "mes_proporcao": 4,
                "ano_proporcao": 2026,
                "quantidade_reflexos_ferias": 0,
                "quantidade_reflexos_13": 0,
            },
        },
    )
    assert response.status_code == 200, response.text
    # (1001.010 - 1000.005) × 15 / 30 = .5025 => .50, sem arredondar a base.
    assert response.json()["resultado_calculo"]["total_geral_devido"] == 0.50


def test_manual_salary_has_explicit_precedence_even_without_reference(auth_client_user):
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "rescisao",
            "dados_extraidos": {
                "salario_mensal": 3000.015,
                "dias_trabalhados": 15,
                "mes_rescisao": 4,
                "ano_rescisao": 2026,
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["resultado_calculo"]["total_liquido_a_receber"] == 1500.01


def test_linking_is_manual_and_reference_edit_requires_new_check(
    auth_client_admin, db_session, salary_reference
):
    from app.db.salary_reference_migration import sync_legacy_salary_rows
    from app.models.referencias_salariais import PendenciaSalarialLegada
    from app.services.salary_references import referencia_json

    db_session.add(TabelaVencimentoBasico(classe="D", nivel=1, ano=2020, valor=3000))
    db_session.flush()
    sync_legacy_salary_rows(db_session.connection())
    item, _ = salary_reference()
    pending = db_session.query(PendenciaSalarialLegada).one()
    db_session.commit()
    assert pending.referencia_id is None
    response = auth_client_admin.put(
        f"/api/tabelas/pendencias-legadas/{pending.id}/vinculo",
        json={"referencia_id": item.id},
    )
    assert response.status_code == 200, response.text
    assert response.json()["estado"] == "VINCULADA"
    payload = referencia_json(item)
    for key in ("id", "estrutura_id", "conferido_em"):
        payload.pop(key)
    payload["fonte"] = "Conferência sintética revisada"
    updated = auth_client_admin.put(f"/api/tabelas/referencias/{item.id}", json=payload)
    assert updated.status_code == 200, updated.text
    db_session.refresh(pending)
    assert pending.referencia_id is None


def test_postgres_ddl_contains_native_ranges_without_extension():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    compiled = str(
        CreateTable(ReferenciaSalarial.__table__).compile(dialect=postgresql.dialect())
    )
    assert "EXCLUDE USING gist" in compiled
    assert "int8range(estrutura_id::bigint" in compiled
    assert "daterange(inicio_vigencia, fim_vigencia" in compiled
    assert "btree_gist" not in compiled


def test_cli_writes_local_report_and_recovery_copy_preserves_original(
    tmp_path, monkeypatch
):
    import json
    import sqlite3
    import sys

    from scripts.migrar_referencias_salariais import main

    database = tmp_path / "salarios_test.db"
    backup = tmp_path / "backup_test.db"
    with sqlite3.connect(database) as source:
        source.execute(
            "CREATE TABLE tabela_vencimento_basico (id INTEGER PRIMARY KEY, classe TEXT, nivel INTEGER, ano INTEGER, valor FLOAT)"
        )
        source.execute(
            "INSERT INTO tabela_vencimento_basico VALUES (1, 'D', 1, 2020, 3000.25)"
        )
        source.commit()
        with sqlite3.connect(backup) as destination:
            source.backup(destination)
    report = tmp_path / "simulacao.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "migracao",
            "--database-url",
            f"sqlite:///{database}",
            "--report",
            str(report),
        ],
    )
    main()
    assert json.loads(report.read_text(encoding="utf-8"))["simulacao"] is True
    with sqlite3.connect(database) as source:
        assert source.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='referencia_salarial'"
        ).fetchone() == (0,)
    applied = tmp_path / "aplicada.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "migracao",
            "--database-url",
            f"sqlite:///{database}",
            "--report",
            str(applied),
            "--apply",
        ],
    )
    main()
    assert (
        json.loads(applied.read_text(encoding="utf-8"))["copiados_ou_atualizados"] == 1
    )
    # Ensaiar restauração em outro banco mantém o estado posterior disponível.
    restored = tmp_path / "restaurado_test.db"
    with sqlite3.connect(backup) as source, sqlite3.connect(restored) as destination:
        source.backup(destination)
        assert destination.execute(
            "SELECT * FROM tabela_vencimento_basico"
        ).fetchall() == [(1, "D", 1, 2020, 3000.25)]
        assert destination.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='referencia_salarial'"
        ).fetchone() == (0,)
    with pytest.raises(FileExistsError):
        main()  # Relatórios anteriores nunca são sobrescritos.


def test_missing_faculty_title_is_pending_without_presumed_rt(auth_client_user, db_session, salary_reference):
    _, query = salary_reference(retribuicoes=[{"titulacao": "Mestrado", "valor": "900"}])
    db_session.commit()
    payload = {"tipo_calculo": "rescisao", "dados_extraidos": {"mes_rescisao": 4, "ano_rescisao": 2026,
               "referencia_salarial": query.model_dump(mode="json"), "dias_trabalhados": 30}}
    response = auth_client_user.post('/api/calcular', json=payload)
    assert response.status_code == 400
    assert response.json()["detail"][0]["type"] == "referencia_salarial_pendente"
    assert "titulação" in response.json()["detail"][0]["msg"]
    payload["dados_extraidos"]["titulacao"] = "N/A"
    response = auth_client_user.post('/api/calcular', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["resultado_calculo"]["total_liquido_a_receber"] == 3000
