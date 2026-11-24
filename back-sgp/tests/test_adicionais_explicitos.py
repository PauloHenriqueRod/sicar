"""Concessões sintéticas e esperados calculados sem usar o motor como oráculo."""

from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from test_progressao_eventos import RULE, event, position, rubric, seed
from test_progressao_eventos import plan as progression

from app.db.base import Base
from app.models.cobertura_adicionais import CoberturaAdicional, RevisaoCalculo
from app.models.tabelas_salariais import HistoricoCalculo
from app.schemas.adicionais import PlanoAdicionais
from app.schemas.progressao_eventos import PlanoProgressao
from app.schemas.referencias_salariais import ReferenciaEntrada
from app.services.adicionais import calcular_adicionais
from app.services.apuracao_periodos import PendenciaApuracao
from app.services.progressao_eventos import calcular_progressao_eventos
from app.services.salary_references import salvar_referencia


def concession(base="VB", start="2020-01-01", end=None):
    return {
        "identificador": "ATO-SINTETICO-123",
        "especie": "INSALUBRIDADE",
        "percentual": "10",
        "percentual_confirmado": True,
        "inicio_vigencia": start,
        "fim_vigencia": end,
        "base": {"tipo": base, "confirmada": True},
        "regra": {**RULE, "confirmada": True},
    }


def plan(modality="TAE"):
    return {
        "periodo": {"inicio": "2024-02-01", "ultimo_dia_considerado": "2024-02-29"},
        "estado_inicial": {
            "posicao": position(modality),
            "titulacao": "Mestrado" if modality == "DOCENTE" else "N/A",
            "adicional": concession(),
        },
        "rubricas": [rubric("53", "ADICIONAL_CONFIRMADO")],
        "recebidos": [],
        "conferido_pelo_rh": True,
    }


def reflex(kind="FERIAS_UM_TERCO", **kwargs):
    return {
        "id": "F1",
        "tipo": kind,
        "data_base": "2024-02-29",
        "competencia": "2024-02",
        "avos": 12,
        "rubrica": "750",
        "natureza_folha": "NORMAL",
        "natureza_rubrica": "R",
        "formulas_base": ["ADICIONAL_CONFIRMADO"],
        "regra": RULE,
        "origem": "ATO-SINTETICO-123",
        "periodo_referencia": {
            "inicio": "2023-03-01",
            "ultimo_dia_considerado": "2024-02-29",
        },
        "pagamentos_anteriores": [],
        **kwargs,
    }


def payment(identifier="P1", **kwargs):
    return {
        "id": identifier,
        "competencia": "2024-02",
        "rubrica": "750",
        "natureza_folha": "NORMAL",
        "natureza_rubrica": "R",
        "identificador_folha": "FOLHA-SINTETICA",
        "sequencia": "0",
        "operacao": "PAGAMENTO",
        "valor": "20",
        "origem": "Ficha sintética, linha 1",
        **kwargs,
    }


def calculate(data, db):
    return calcular_adicionais(PlanoAdicionais.model_validate(data), db)


def payload(data):
    return {
        "tipo_calculo": "insalubridade",
        "dados_extraidos": {
            "nome": "Pessoa sintética",
            "matricula": "000999",
            "adicionais": data,
        },
        "idempotency_key": str(uuid4()),
    }


@pytest.mark.parametrize("base,expected", [("VB", "290.00"), ("VB_RT", "348.00")])
def test_vb_and_rt_are_distinct_components(db_session, base, expected):
    seed(db_session, "DOCENTE")
    data = plan("DOCENTE")
    data["estado_inicial"]["adicional"]["base"]["tipo"] = base
    result = calculate(data, db_session)
    assert result["totais"]["devido"] == expected  # 2900*.1 ou (2900+580)*.1.
    sources = result["segmentos"][0]["referencias_tabelas"]
    assert any(s["componente"] == "VB" for s in sources)
    assert any(s["componente"] == "RT" for s in sources) == (base == "VB_RT")


def test_manual_base_needs_no_salary_reference(db_session):
    data = plan()
    data["estado_inicial"]["adicional"]["base"] = {
        "tipo": "VALOR_CONFIRMADO",
        "confirmada": True,
        "valor_manual": {
            "valor": "1234.55",
            "fonte": "Fonte sintética",
            "localizador": "página 1",
        },
    }
    result = calculate(data, db_session)
    assert result["totais"]["devido"] == "123.46"  # 123.455 HALF_UP somente na saída.


def test_vb_only_does_not_depend_on_an_unconfirmed_rt(db_session):
    salvar_referencia(
        db_session,
        ReferenciaEntrada.model_validate(
            {
                **position("DOCENTE"),
                "inicio_vigencia": "2020-01-01",
                "vencimento_basico": "2900",
                "fonte": "Tabela sintética sem RT",
                "estado": "CONFIRMADA",
            }
        ),
        1,
    )
    data = plan("DOCENTE")
    assert calculate(data, db_session)["totais"]["devido"] == "290.00"
    data["estado_inicial"]["adicional"]["base"]["tipo"] = "VB_RT"
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == "rt_pendente"


@pytest.mark.parametrize(
    "year,month,last,expected",
    [
        (2023, 2, 28, "145.00"),
        (2024, 2, 29, "150.00"),
        (2024, 4, 30, "154.67"),
        (2024, 5, 31, "159.03"),
    ],
)
def test_actual_calendar_partial_concession(db_session, year, month, last, expected):
    seed(db_session)
    data = plan()
    data["periodo"] = {
        "inicio": f"{year}-{month:02}-01",
        "ultimo_dia_considerado": f"{year}-{month:02}-{last}",
    }
    data["estado_inicial"]["adicional"]["inicio_vigencia"] = f"{year}-{month:02}-15"
    assert (
        calculate(data, db_session)["totais"]["devido"] == expected
    )  # 290*(last-14)/last.


def test_reflex_only_does_not_require_base_of_an_unrelated_segment(db_session):
    data = plan()
    data["estado_inicial"]["adicional"] = None
    confirmed = concession()
    confirmed["base"] = {
        "tipo": "VALOR_CONFIRMADO",
        "confirmada": True,
        "valor_manual": {
            "valor": "2900",
            "fonte": "Fonte sintética",
            "localizador": "página 1",
        },
    }
    data["eventos"] = [event("ADICIONAL", "2024-02-20", adicional=confirmed)]
    data["rubricas"][0]["apurar_principal"] = False
    data["reflexos"] = [reflex()]
    assert calculate(data, db_session)["totais"]["devido"] == "96.67"


def test_reflex_cannot_appear_again_with_another_base_date_or_rubric():
    data = plan()
    data["reflexos"] = [
        reflex(),
        reflex(id="F2", data_base="2024-02-28", rubrica="999"),
    ]
    with pytest.raises(ValidationError, match="repetir dias"):
        PlanoAdicionais.model_validate(data)


def test_reflex_alias_and_reversal_are_not_deducted_twice(db_session):
    seed(db_session)
    data = plan()
    data["recebidos"] = [
        payment(),
        payment("COPY"),
        payment("EST", sequencia="2", operacao="ESTORNO", estorna_id="COPY", valor="5"),
    ]
    data["reflexos"] = [reflex(pagamentos_anteriores=["COPY", "EST"])]
    result = calculate(data, db_session)
    assert result["totais"]["recebido"] == "15.00"
    assert result["totais"]["saldo"] == "371.67"
    assert [item["id"] for item in result["reflexos"][0]["pagamentos_anteriores"]] == [
        "P1",
        "EST",
    ]
    data["reflexos"][0]["pagamentos_anteriores"] = ["P1", "COPY", "EST"]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == "pagamento_reflexo_duplicado"


def test_changed_base_and_concession_validity_split_without_double_days(db_session):
    seed(db_session, "DOCENTE")
    data = plan("DOCENTE")
    data["estado_inicial"]["adicional"] = concession(
        start="2024-02-05", end="2024-02-25"
    )
    changed = concession("VB_RT", start="2024-02-05", end="2024-02-25")
    data["eventos"] = [event("ADICIONAL", "2024-02-15", adicional=changed)]
    result = calculate(data, db_session)
    assert result["totais"]["devido"] == "232.00"  # 290*10/29 + 348*11/29 = 232.
    assert [s["dias_calendario"] for s in result["segmentos"]] == [4, 10, 11, 4]
    assert sum(s["dias_calendario"] for s in result["segmentos"]) == 29


@pytest.mark.parametrize(
    "field,code",
    [
        ("base", "base_adicional_pendente"),
        ("regra", "regra_adicional_pendente"),
        ("percentual_confirmado", "percentual_adicional_pendente"),
    ],
)
def test_only_dependent_case_requires_confirmations(db_session, field, code):
    seed(db_session)
    data = plan()
    data["estado_inicial"]["adicional"][field] = (
        False if field == "percentual_confirmado" else None
    )
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == code
    data["rubricas"][0]["apurar_principal"] = False
    assert calculate(data, db_session)["totais"]["devido"] == "0.00"
    unaffected = progression()
    unaffected["estado_inicial"]["adicional"] = data["estado_inicial"]["adicional"]
    assert (
        calcular_progressao_eventos(
            PlanoProgressao.model_validate(unaffected), db_session
        )["totais"]["devido"]
        == "1850.00"
    )


def test_inactive_concession_does_not_require_unknown_base(db_session):
    data = plan()
    data["estado_inicial"]["adicional"] = {
        "identificador": "ATO-PENDENTE",
        "inicio_vigencia": "2024-03-01",
    }
    assert calculate(data, db_session)["totais"]["devido"] == "0.00"


@pytest.mark.parametrize(
    "missing", ["origem", "periodo_referencia", "pagamentos_anteriores", "avos"]
)
def test_month_label_cannot_supply_reflex_data(missing):
    data = plan()
    data["reflexos"] = [reflex(id="Dezembro com férias")]
    del data["reflexos"][0][missing]
    with pytest.raises(ValidationError):
        PlanoAdicionais.model_validate(data)


def test_reflex_discriminates_previous_payments_once(db_session):
    seed(db_session)
    data = plan()
    data["reflexos"] = [reflex(pagamentos_anteriores=["P1", "P2"])]
    data["recebidos"] = [
        payment(),
        payment("P2", sequencia="1", operacao="COMPLEMENTO", valor="6.666"),
    ]
    result = calculate(data, db_session)
    assert result["totais"] == {
        "devido": "386.67",
        "recebido": "26.67",
        "saldo": "360.00",
        "saldo_exato": {"numerador": "540001", "denominador": "1500"},
    }
    output = result["reflexos"][0]
    assert [p["origem"] for p in output["pagamentos_anteriores"]] == [
        "Ficha sintética, linha 1"
    ] * 2
    assert output["origem"] == "ATO-SINTETICO-123"
    assert output["periodo_referencia"]["inicio"] == "2023-03-01"


@pytest.mark.parametrize(
    "change,code",
    [
        ("unassigned", "pagamento_reflexo_nao_discriminado"),
        ("mismatch", "pagamento_reflexo_incompativel"),
        ("origin", "origem_reflexo_incompativel"),
    ],
)
def test_invalid_reflex_links_are_pending(db_session, change, code):
    seed(db_session)
    data = plan()
    data["reflexos"] = [
        reflex(pagamentos_anteriores=[] if change == "unassigned" else ["P1"])
    ]
    data["recebidos"] = [payment(rubrica="1" if change == "mismatch" else "750")]
    if change == "origin":
        data["reflexos"][0]["origem"] = "OUTRO-ATO"
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == code


def test_api_blocks_cross_flow_overlap_and_allows_reflex_only(
    auth_client_user, db_session
):
    seed(db_session)
    first = payload(plan())
    saved = auth_client_user.post("/api/calcular", json=first)
    assert saved.status_code == 200, saved.text
    assert (
        auth_client_user.post("/api/calcular", json=first).json() == saved.json()
    )  # Idempotência.
    data = progression()
    data["estado_inicial"]["adicional"] = concession()
    data["rubricas"].append(rubric("53", "ADICIONAL_CONFIRMADO"))
    second = {
        "tipo_calculo": "progressao",
        "dados_extraidos": {"matricula": "999", "progressao": data},
    }
    blocked = auth_client_user.post("/api/calcular", json=second)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"][0]["type"] == "adicional_ja_apurado"
    assert db_session.query(HistoricoCalculo).count() == 1
    data["rubricas"][-1]["apurar_principal"] = False
    data["reflexos"] = [reflex()]
    assert auth_client_user.post("/api/calcular", json=second).status_code == 200
    other = plan()
    other["rubricas"][0]["apurar_principal"] = False
    other["reflexos"] = [reflex()]
    assert (
        auth_client_user.post("/api/calcular", json=payload(other)).status_code == 409
    )


def test_revision_replaces_coverage_preserves_history_and_allows_old_export(
    auth_client_user, db_session
):
    seed(db_session)
    first = auth_client_user.post("/api/calcular", json=payload(plan())).json()
    revised = payload(plan())
    revised["dados_extraidos"]["substitui_historico_id"] = first["historico_id"]
    revised["dados_extraidos"]["adicionais"]["estado_inicial"]["adicional"][
        "percentual"
    ] = "20"
    response = auth_client_user.post("/api/calcular", json=revised)
    assert response.status_code == 200, response.text
    second = response.json()
    assert second["resultado_calculo"]["totais"]["devido"] == "580.00"
    assert db_session.query(HistoricoCalculo).count() == 2
    assert (
        db_session.get(RevisaoCalculo, first["historico_id"]).novo_id
        == second["historico_id"]
    )
    assert {r.historico_id for r in db_session.query(CoberturaAdicional)} == {
        second["historico_id"]
    }
    assert (
        auth_client_user.post(
            "/api/exportar-pdf", json={"historico_id": first["historico_id"]}
        ).status_code
        == 200
    )
    listing = auth_client_user.get("/api/historico").json()
    assert (
        next(r for r in listing if r["id"] == first["historico_id"])["substituido_por"]
        == second["historico_id"]
    )
    assert (
        auth_client_user.post(
            "/api/calcular", json={**revised, "idempotency_key": str(uuid4())}
        ).status_code
        == 409
    )


def test_conflicting_revision_rolls_back_history_and_original_coverage(
    auth_client_user, db_session
):
    seed(db_session)
    first = payload(plan())
    first["dados_extraidos"]["adicionais"]["periodo"]["ultimo_dia_considerado"] = (
        "2024-02-14"
    )
    original = auth_client_user.post("/api/calcular", json=first).json()
    second = deepcopy(first)
    second["idempotency_key"] = str(uuid4())
    second["dados_extraidos"]["adicionais"]["periodo"] = {
        "inicio": "2024-02-15",
        "ultimo_dia_considerado": "2024-02-29",
    }
    assert auth_client_user.post("/api/calcular", json=second).status_code == 200
    revised = payload(plan())
    revised["dados_extraidos"]["substitui_historico_id"] = original["historico_id"]
    assert auth_client_user.post("/api/calcular", json=revised).status_code == 409
    assert db_session.query(HistoricoCalculo).count() == 2
    assert db_session.query(CoberturaAdicional).count() == 2
    assert db_session.query(RevisaoCalculo).count() == 0
    assert {r.historico_id for r in db_session.query(CoberturaAdicional)} >= {
        original["historico_id"]
    }


def test_revision_of_another_users_history_is_unavailable(
    auth_client_user, db_session, admin_user
):
    seed(db_session)
    foreign = HistoricoCalculo(
        user_id=admin_user.id,
        tipo_calculo="insalubridade",
        matricula="999",
        resultado_json="synthetic",
    )
    db_session.add(foreign)
    db_session.flush()
    data = payload(plan())
    data["dados_extraidos"]["substitui_historico_id"] = foreign.id
    response = auth_client_user.post("/api/calcular", json=data)
    assert response.status_code == 409
    assert response.json()["detail"][0]["type"] == "revisao_indisponivel"
    assert db_session.query(CoberturaAdicional).count() == 0


def test_new_contract_idempotency_uses_decimal_value_and_exports_saved_report(
    auth_client_user, db_session
):
    seed(db_session)
    data = payload(plan())
    saved = auth_client_user.post("/api/calcular", json=data)
    assert saved.status_code == 200, saved.text
    data["dados_extraidos"]["adicionais"]["estado_inicial"]["adicional"][
        "percentual"
    ] = "10.000"
    assert auth_client_user.post("/api/calcular", json=data).json() == saved.json()
    pdf = auth_client_user.post(
        "/api/exportar-pdf", json={"historico_id": saved.json()["historico_id"]}
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF-")
    assert (
        auth_client_user.get("/api/calculos/contratos/adicionais").json()["$defs"][
            "ConcessaoAdicional"
        ]["properties"]["percentual_confirmado"]["default"]
        is False
    )


def test_cessation_reserves_the_original_concession_and_rejects_duplicate_refund(
    auth_client_user, db_session
):
    seed(db_session)
    data = progression()
    data["periodo"]["inicio"] = "2024-02-15"
    data["estado_inicial"]["adicional"] = concession()
    data["rubricas"].append(rubric("53", "ADICIONAL_CONFIRMADO"))
    data["eventos"] = [
        event("ADICIONAL", "2024-02-15", adicional=concession(end="2024-02-14"))
    ]
    request = {
        "tipo_calculo": "progressao",
        "dados_extraidos": {"matricula": "999", "progressao": data},
        "idempotency_key": str(uuid4()),
    }
    first = auth_client_user.post("/api/calcular", json=request)
    assert first.status_code == 200, first.text
    assert (
        first.json()["resultado_calculo"]["totais"]["saldo"] == "-150.00"
    )  # -290 * 15/29.
    assert auth_client_user.post("/api/calcular", json=request).json() == first.json()
    request["idempotency_key"] = str(uuid4())
    repeated = auth_client_user.post("/api/calcular", json=request)
    assert repeated.status_code == 409, repeated.text
    assert repeated.json()["detail"][0]["type"] == "adicional_ja_apurado"
    assert db_session.query(HistoricoCalculo).count() == 1
    cover = db_session.query(CoberturaAdicional).one()
    assert str(cover.inicio) == "2024-02-15" and str(cover.fim) == "2024-02-29"
    request["dados_extraidos"]["substitui_historico_id"] = first.json()["historico_id"]
    revised = auth_client_user.post("/api/calcular", json=request)
    assert revised.status_code == 200, revised.text
    assert (
        db_session.query(CoberturaAdicional).one().historico_id
        == revised.json()["historico_id"]
    )


@pytest.mark.parametrize("reflex_only", [False, True])
def test_changed_concession_reserves_both_origins_between_flows(
    auth_client_user, db_session, reflex_only
):
    seed(db_session)
    data = progression()
    data["periodo"]["inicio"] = "2024-02-15"
    data["estado_inicial"]["adicional"] = concession()
    changed = {
        **concession(),
        "identificador": "NOVO-ATO-SINTETICO",
        "percentual": "20",
    }
    data["eventos"] = [event("ADICIONAL", "2024-02-15", adicional=changed)]
    data["rubricas"].append(
        {**rubric("53", "ADICIONAL_CONFIRMADO"), "apurar_principal": not reflex_only}
    )
    if reflex_only:
        data["reflexos"] = [reflex(kind="DECIMO_TERCEIRO", origem="NOVO-ATO-SINTETICO")]
    first = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "progressao",
            "dados_extraidos": {"matricula": "999", "progressao": data},
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["resultado_calculo"]["totais"]["devido"] == (
        "290.00" if reflex_only else "150.00"
    )
    assert db_session.query(CoberturaAdicional).count() == 2
    for grant in (concession(), changed):
        other = plan()
        other["periodo"]["inicio"] = "2024-02-15"
        other["estado_inicial"]["adicional"] = grant
        other["rubricas"][0]["apurar_principal"] = not reflex_only
        if reflex_only:
            other["reflexos"] = [
                reflex(kind="DECIMO_TERCEIRO", origem=grant["identificador"])
            ]
        response = auth_client_user.post("/api/calcular", json=payload(other))
        assert response.status_code == 409, response.text
    assert db_session.query(HistoricoCalculo).count() == 1


@pytest.mark.parametrize(
    "other_code,other_sheet,other_kind",
    [("54", "NORMAL", "R"), ("53", "COMPLEMENTAR", "R"), ("53", "NORMAL", "D")],
)
def test_common_api_rejects_same_concession_under_different_payroll_keys(
    auth_client_user, db_session, other_code, other_sheet, other_kind
):
    seed(db_session)
    data = plan()
    data["rubricas"][0]["regra"] = {
        key: RULE[key] for key in ("identificador", "versao", "fonte")
    }
    single = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "apuracao_periodos",
            "dados_extraidos": {"matricula": "999", "apuracao": data},
        },
    )
    assert single.status_code == 200, single.text
    assert single.json()["resultado_calculo"]["totais"]["devido"] == "290.00"
    data["rubricas"].append(
        {
            **deepcopy(data["rubricas"][0]),
            "rubrica": other_code,
            "natureza_folha": other_sheet,
            "natureza_rubrica": other_kind,
        }
    )
    repeated = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "apuracao_periodos",
            "dados_extraidos": {"matricula": "999", "apuracao": data},
        },
    )
    assert repeated.status_code == 400, repeated.text
    assert "uma única vez" in repeated.json()["detail"][0]["msg"]
    assert db_session.query(HistoricoCalculo).count() == 1
    assert db_session.query(CoberturaAdicional).count() == 1


@pytest.mark.parametrize(
    "label",
    [
        "OUTUBRO",
        "outubro",
        "NOVEMBRO E 13º",
        "Janeiro e férias",
        "competência conferida",
    ],
)
def test_legacy_api_never_creates_reflexes_from_a_month_label(auth_client_user, label):
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "insalubridade",
            "dados_extraidos": {"valores_mensais": {label: 100}},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["resultado_calculo"]
    assert result["total_acumulado"] == 100
    assert result["detalhamento_mensal"][0]["multiplicador"] == 1


def test_additive_tables_can_be_created_twice_without_changing_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE historico_calculo (id INTEGER PRIMARY KEY, resultado_json TEXT)"
        )
        conn.exec_driver_sql(
            "INSERT INTO historico_calculo VALUES (1, 'synthetic-encrypted-placeholder')"
        )
        for _ in range(2):
            Base.metadata.create_all(
                conn,
                tables=[
                    Base.metadata.tables[name]
                    for name in (
                        "escopos_adicionais",
                        "coberturas_adicionais",
                        "revisoes_calculos",
                    )
                ],
            )
        assert (
            conn.exec_driver_sql(
                "SELECT resultado_json FROM historico_calculo"
            ).scalar_one()
            == "synthetic-encrypted-placeholder"
        )
        assert {
            "escopos_adicionais",
            "coberturas_adicionais",
            "revisoes_calculos",
        }.issubset(inspect(conn).get_table_names())
    engine.dispose()
