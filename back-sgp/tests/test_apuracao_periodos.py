"""Resultados independentes e dados exclusivamente sintéticos."""

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.tabelas_salariais import HistoricoCalculo
from app.schemas.apuracao_periodos import PlanoApuracao
from app.schemas.referencias_salariais import ReferenciaEntrada
from app.services.apuracao_periodos import PendenciaApuracao, apurar_periodos
from app.services.salary_references import salvar_referencia

POSITION = {
    "carreira": "TAE",
    "vinculo": "EFETIVO",
    "jornada": "40H",
    "versao_carreira": "SINTETICA",
    "classificacao_tae": "E",
    "padrao_tae": 1,
}
RULE = {
    "identificador": "REGRA-SINTETICA",
    "versao": "1",
    "fonte": "Parâmetros sintéticos conferidos",
}


def manual_value(value):
    return {
        "valor": value,
        "fonte": "Tabela sintética conferida",
        "localizador": "Aba 1, linha 2",
    }


def rubric(code="1", formula="VB"):
    return {
        "rubrica": code,
        "natureza_folha": "NORMAL",
        "natureza_rubrica": "R",
        "formula": formula,
        "regra": RULE,
    }


def plan(start="2024-02-01", end="2024-02-29", amount="2900"):
    return {
        "periodo": {"inicio": start, "ultimo_dia_considerado": end},
        "estado_inicial": {
            "posicao": POSITION,
            "titulacao": "N/A",
            "vb_manual": manual_value(amount),
        },
        "rubricas": [rubric()],
        "recebidos": [],
        "conferido_pelo_rh": True,
    }


def calculate(data, db):
    return apurar_periodos(PlanoApuracao.model_validate(data), db)


def event(identifier, effective, **changes):
    return {
        "id": identifier,
        "data_documento": "2024-03-15",
        "efeitos_financeiros": effective,
        "data_implantacao": "2024-04-01",
        "regra": RULE,
        "alteracoes": changes,
    }


def payment(identifier="P1", value="100", **extra):
    return {
        "id": identifier,
        "competencia": "2024-02",
        "rubrica": "00001",
        "natureza_folha": "NORMAL",
        "natureza_rubrica": "R",
        "identificador_folha": "FOLHA-1",
        "sequencia": "1",
        "operacao": "PAGAMENTO",
        "valor": value,
        "origem": "Ficha sintética, página 1",
        **extra,
    }


@pytest.mark.parametrize(
    "start,end,days",
    [
        ("2023-02-01", "2023-02-28", 28),
        ("2024-02-01", "2024-02-29", 29),
        ("2024-04-01", "2024-04-30", 30),
        ("2024-01-01", "2024-01-31", 31),
        ("9999-12-01", "9999-12-31", 31),
    ],
)
def test_whole_month_uses_real_calendar(db_session, start, end, days):
    result = calculate(plan(start, end, "3100.005"), db_session)
    assert result["total_geral_a_receber"] == "3100.01"
    assert result["segmentos"][0]["dias_reais_mes"] == days
    assert result["segmentos"][0]["dias_computados"] == days


def test_year_boundary_and_overlap_of_interruptions_never_repeat_days(db_session):
    data = plan("2023-12-30", "2024-01-02", "3100")
    data["interrupcoes"] = [
        {
            "id": "I1",
            "inicio": "2023-12-31",
            "ultimo_dia_considerado": "2024-01-01",
            "regra": RULE,
        },
        {
            "id": "I2",
            "inicio": "2024-01-01",
            "ultimo_dia_considerado": "2024-01-02",
            "regra": RULE,
        },
    ]
    result = calculate(data, db_session)
    assert result["total_geral_a_receber"] == "100.00"
    covered = []
    for segment in result["segmentos"]:
        first, last = (
            date.fromisoformat(segment["inicio"]),
            date.fromisoformat(segment["ultimo_dia_considerado"]),
        )
        covered.extend(
            first + timedelta(days=i) for i in range((last - first).days + 1)
        )
    assert covered == [
        date(2023, 12, 30),
        date(2023, 12, 31),
        date(2024, 1, 1),
        date(2024, 1, 2),
    ]
    assert len(covered) == len(set(covered))
    assert sum(item["dias_computados"] for item in result["segmentos"]) == 1


def test_salary_iq_and_additional_changes_inside_leap_month(db_session):
    for start, end, value in (
        ("2024-02-01", "2024-02-14", "2900"),
        ("2024-02-15", "2024-02-29", "5800"),
    ):
        salvar_referencia(
            db_session,
            ReferenciaEntrada.model_validate(
                {
                    **POSITION,
                    "inicio_vigencia": start,
                    "fim_vigencia": end,
                    "vencimento_basico": value,
                    "fonte": "Tabela sintética",
                    "estado": "CONFIRMADA",
                }
            ),
            1,
        )
    data = plan()
    data["estado_inicial"].pop("vb_manual")
    data["estado_inicial"].update(percentual_iq="10", percentual_adicional="10")
    data["rubricas"] = [
        rubric(),
        rubric("2", "IQ_SOBRE_VB"),
        rubric("3", "ADICIONAL_SOBRE_VB"),
    ]
    data["eventos"] = [
        event("IQ", "2024-02-11", percentual_iq="20"),
        event("INS", "2024-02-20", percentual_adicional="30"),
    ]
    result = calculate(data, db_session)
    assert [item["dias_computados"] for item in result["segmentos"]] == [10, 4, 5, 10]
    assert [item["devido"] for item in result["por_competencia"]] == [
        "4400.00",
        "780.00",
        "840.00",
    ]
    assert result["total_geral_a_receber"] == "6020.00"
    refs = [
        segment["referencias_tabelas"][0]["referencia_id"]
        for segment in result["segmentos"]
    ]
    assert refs[0] == refs[1] and refs[2] == refs[3] and refs[0] != refs[2]
    assert all(segment["referencias_regras"] for segment in result["segmentos"])


def test_same_day_position_and_manual_value_are_order_independent(db_session):
    data = plan("2024-01-01", "2024-01-31", "3100")
    data["eventos"] = [
        event("A-VALOR", "2024-01-17", vb_manual=manual_value("6200")),
        event(
            "Z-POSICAO",
            "2024-01-17",
            posicao={**POSITION, "jornada": "20H", "padrao_tae": 2},
        ),
    ]
    result = calculate(data, db_session)
    assert result["total_geral_a_receber"] == "4600.00"  # 16*100 + 15*200.
    assert result["segmentos"][1]["estado"]["posicao"]["jornada"] == "20H"
    assert result["eventos"][0]["data_documento"] == "2024-03-15"
    assert result["segmentos"][1]["inicio"] == "2024-01-17"
    data["eventos"].reverse()
    assert calculate(data, db_session) == result


def test_totals_do_not_sum_rounded_segments_and_negative_tie_is_preserved(db_session):
    data = plan("2023-02-15", "2023-04-15", "0.01")
    data["interrupcoes"] = [
        {
            "id": "MARCO",
            "inicio": "2023-03-01",
            "ultimo_dia_considerado": "2023-03-31",
            "regra": RULE,
        }
    ]
    result = calculate(data, db_session)
    assert [segment["parcelas"][0]["devido"] for segment in result["segmentos"]] == [
        "0.01",
        "0.00",
        "0.01",
    ]
    assert result["total_geral_a_receber"] == "0.01"  # 0.005 + 0 + 0.005.
    negative = plan("2023-02-15", "2023-02-28", "0.01")
    negative["recebidos"] = [payment(value="0.01", competencia="2023-02")]
    assert calculate(negative, db_session)["total_geral_a_receber"] == "-0.01"


def test_repeated_document_is_deduplicated_but_identified_complement_is_counted(
    db_session,
):
    data = plan(amount="300")
    data["recebidos"] = [
        payment(),
        payment("P1-COPIA", origem="Outro PDF sintético"),
        payment("C1", "50", sequencia="2", operacao="COMPLEMENTO"),
        payment("E1", "20", sequencia="3", operacao="ESTORNO", estorna_id="P1-COPIA"),
    ]
    result = calculate(data, db_session)
    row = result["por_competencia"][0]
    assert (row["devido"], row["recebido"], row["saldo"]) == (
        "300.00",
        "130.00",
        "170.00",
    )
    assert result["duplicidades"][0]["original_id"] == "P1"
    assert row["lancamentos_recebidos"] == ["P1", "C1", "E1"]


@pytest.mark.parametrize(
    "change,code",
    [
        ({"valor": "101"}, "lancamento_conflitante"),
        ({"operacao": "COMPLEMENTO"}, "lancamento_conflitante"),
    ],
)
def test_ambiguous_posting_does_not_silently_deduplicate(db_session, change, code):
    data = plan()
    data["recebidos"] = [payment(), payment("P2", **change)]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == code


@pytest.mark.parametrize("order", [(0, 1, 2, 3), (2, 3, 0, 1), (3, 1, 2, 0)])
def test_duplicate_reversal_uses_canonical_payment_target(db_session, order):
    data = plan(amount="300")
    rows = [
        payment("P1", "100"),
        payment("P2", "100", origem="Segunda via sintética"),
        payment("E1", "20", sequencia="2", operacao="ESTORNO", estorna_id="P1"),
        payment("E2", "20", sequencia="2", operacao="ESTORNO", estorna_id="P2"),
    ]
    data["recebidos"] = [rows[index] for index in order]
    result = calculate(data, db_session)
    assert result["totais"]["recebido"] == "80.00"  # 100 - 20, uma vez.
    assert result["total_geral_a_receber"] == "220.00"
    assert len(result["recebimentos_considerados"]) == 2
    assert len(result["duplicidades"]) == 2
    accepted = {item["id"] for item in result["recebimentos_considerados"]}
    assert result["por_competencia"][0]["lancamentos_recebidos"] == [
        rows[index]["id"] for index in order if rows[index]["id"] in accepted
    ]


def test_reversal_of_distinct_payments_remains_a_conflict(db_session):
    data = plan()
    data["recebidos"] = [
        payment("P1"), payment("P2", sequencia="2"),
        payment("E1", "20", sequencia="3", operacao="ESTORNO", estorna_id="P1"),
        payment("E2", "20", sequencia="3", operacao="ESTORNO", estorna_id="P2"),
    ]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == "lancamento_conflitante"


@pytest.mark.parametrize("career", ["TAE", "MAGISTERIO_SUPERIOR"])
def test_history_indexes_the_declared_initial_state(auth_client_user, db_session, career):
    data = plan(amount="300")
    if career == "TAE":
        position, title, expected_class, expected_level = POSITION, "N/A", "Técnico Administrativo", 1
    else:
        position = {
            "carreira": career, "vinculo": "EFETIVO", "jornada": "40H",
            "versao_carreira": "SINTETICA", "classe_docente": "Adjunto", "nivel_docente": 2,
        }
        title, expected_class, expected_level = "Doutorado", "Adjunto", 2
    data["estado_inicial"].update(posicao=position, titulacao=title)
    data["eventos"] = [event("TITULACAO", "2024-02-15", titulacao="Mestrado")]
    response = auth_client_user.post("/api/calcular", json={
        "tipo_calculo": "apuracao_periodos", "dados_extraidos": {
            "matricula": "DEMO-HISTORICO", "classe": "Titular", "nivel": 99,
            "titulacao": "Especialização", "apuracao": data,
        },
    })
    assert response.status_code == 200, response.text
    record = db_session.query(HistoricoCalculo).one()
    assert (record.classe, record.nivel, record.titulacao) == (expected_class, expected_level, title)
    page = auth_client_user.get("/api/historico", params={
        "pagina": 1, "classe": expected_class, "titulacao": title,
    }).json()
    assert page["total"] == 1
    assert page["itens"][0]["nivel"] == expected_level


def test_salary_gap_and_position_change_do_not_reuse_manual_salary(db_session):
    data = plan()
    data["eventos"] = [event("P", "2024-02-15", posicao={**POSITION, "jornada": "20H"})]
    with pytest.raises(PendenciaApuracao, match="2024-02-15") as error:
        calculate(data, db_session)
    assert error.value.codigo == "referencia_salarial_pendente"


def test_payroll_natures_and_rubric_sign_are_separate(db_session):
    data = plan(amount="300")
    data["rubricas"].append(
        {
            **rubric("2", "VALOR_MENSAL"),
            "natureza_rubrica": "D",
            "valor_mensal": manual_value("30"),
        }
    )
    data["recebidos"] = [
        payment(value="200"),
        payment("C1", "50", natureza_folha="SUPLEMENTAR"),
    ]
    result = calculate(data, db_session)
    assert len(result["por_competencia"]) == 3
    assert result["totais"] == {
        "devido": "270.00",
        "recebido": "250.00",
        "saldo": "20.00",
        "saldo_exato": {"numerador": "20", "denominador": "1"},
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update(conferido_pelo_rh=1),
        lambda data: data["estado_inicial"].update(percentual_iq=True),
        lambda data: data["periodo"].update(inicio=0),
        lambda data: data["rubricas"].append(deepcopy(data["rubricas"][0])),
        lambda data: data.update(
            eventos=[
                event("A", "2024-02-10", percentual_iq="10"),
                event("B", "2024-02-10", percentual_iq="20"),
            ]
        ),
        lambda data: data.update(
            eventos=[event("A", "2024-03-01", percentual_iq="10")]
        ),
    ],
)
def test_ambiguous_contract_is_rejected(mutate):
    data = plan()
    mutate(data)
    with pytest.raises(ValidationError):
        PlanoApuracao.model_validate(data)


@pytest.mark.parametrize("field", ["percentual_iq", "percentual_adicional", "percentual_anuenio"])
@pytest.mark.parametrize("value", ["20", 20, Decimal("20.00"), "0"])
def test_percentages_preserve_values_in_initial_state_and_events(field, value):
    data = plan()
    data["estado_inicial"][field] = value
    data["eventos"] = [event("PERCENTUAL", "2024-02-15", **{field: value})]
    validated = PlanoApuracao.model_validate(data)
    expected = Decimal(str(value))
    for state in (validated.estado_inicial, validated.eventos[0].alteracoes):
        actual = getattr(state, field)
        assert isinstance(actual, Decimal)
        assert actual == expected


@pytest.mark.parametrize("field", ["percentual_iq", "percentual_adicional", "percentual_anuenio"])
@pytest.mark.parametrize("in_event", [False, True])
@pytest.mark.parametrize("value", [True, False])
def test_percentages_reject_booleans_in_initial_state_and_events(field, in_event, value):
    data = plan()
    if in_event:
        data["eventos"] = [event("PERCENTUAL", "2024-02-15", **{field: value})]
        expected_location = ("eventos", 0, "alteracoes", field)
    else:
        data["estado_inicial"][field] = value
        expected_location = ("estado_inicial", field)
    with pytest.raises(ValidationError) as error:
        PlanoApuracao.model_validate(data)
    assert error.value.errors()[0]["loc"] == expected_location
    assert "Percentual não pode ser booleano" in error.value.errors()[0]["msg"]


def test_api_history_and_idempotency_keep_reviewed_decimal_input(
    auth_client_user, db_session
):
    payload = {
        "tipo_calculo": "apuracao_periodos",
        "dados_extraidos": {"apuracao": plan(amount="0.005")},
        "idempotency_key": str(uuid4()),
    }
    response = auth_client_user.post("/api/calcular", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["resultado_calculo"]["total_geral_a_receber"] == "0.01"
    assert auth_client_user.post("/api/calcular", json=payload).json() == result
    assert db_session.query(HistoricoCalculo).count() == 1
    payload["dados_extraidos"]["apuracao"]["estado_inicial"]["vb_manual"]["valor"] = (
        "0.0049"
    )
    assert auth_client_user.post("/api/calcular", json=payload).status_code == 409


@pytest.mark.parametrize(
    "original,retry", [("300", "300.00"), (300, "300.00"), ("300.00", 300.0)]
)
def test_idempotent_retry_accepts_equivalent_decimal_forms(
    auth_client_user, db_session, original, retry
):
    data = plan(amount=original)
    payload = {
        "tipo_calculo": "apuracao_periodos", "dados_extraidos": {"apuracao": data},
        "idempotency_key": str(uuid4()),
    }
    first = auth_client_user.post("/api/calcular", json=payload)
    assert first.status_code == 200, first.text
    data["estado_inicial"]["vb_manual"]["valor"] = retry
    repeated = auth_client_user.post("/api/calcular", json=payload)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == first.json()
    assert db_session.query(HistoricoCalculo).count() == 1


def test_idempotent_retry_compares_nested_money_and_percentages_by_value(
    auth_client_user, db_session
):
    data = plan(amount="300")
    data["estado_inicial"]["percentual_iq"] = "10"
    data["eventos"] = [event("VB", "2024-02-15", vb_manual=manual_value("600"), percentual_iq="20")]
    data["rubricas"].append({**rubric("2", "VALOR_MENSAL"), "valor_mensal": manual_value("30")})
    data["recebidos"] = [payment(value="100")]
    payload = {
        "tipo_calculo": "apuracao_periodos", "dados_extraidos": {"apuracao": data},
        "idempotency_key": str(uuid4()),
    }
    first = auth_client_user.post("/api/calcular", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["resultado_calculo"]["total_geral_a_receber"] == "385.17"
    data["estado_inicial"]["percentual_iq"] = "10.00"
    data["eventos"][0]["alteracoes"]["vb_manual"]["valor"] = "600.00"
    data["eventos"][0]["alteracoes"]["percentual_iq"] = 20.0
    data["rubricas"][1]["valor_mensal"]["valor"] = "30.000"
    data["recebidos"][0]["valor"] = 100
    repeated = auth_client_user.post("/api/calcular", json=payload)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == first.json()
    assert db_session.query(HistoricoCalculo).count() == 1


@pytest.mark.parametrize("field", ["matricula", "versao", "sequencia", "origem", "valor"])
def test_idempotent_retry_rejects_real_changes_without_normalizing_identifiers(
    auth_client_user, db_session, field
):
    data = plan(amount="300.000000000001")
    data["rubricas"][0]["regra"] = {**RULE, "versao": "01"}
    data["recebidos"] = [payment(value="0", sequencia="01", origem="300")]
    payload = {
        "tipo_calculo": "apuracao_periodos",
        "dados_extraidos": {"matricula": "001", "apuracao": data},
        "idempotency_key": str(uuid4()),
    }
    first = auth_client_user.post("/api/calcular", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["resultado_calculo"]["total_geral_a_receber"] == "300.00"
    if field == "matricula":
        payload["dados_extraidos"]["matricula"] = "1"
    elif field == "versao":
        data["rubricas"][0]["regra"]["versao"] = "1"
    elif field in {"sequencia", "origem"}:
        data["recebidos"][0][field] = "1" if field == "sequencia" else "300.00"
    else:
        # Ambos seriam apresentados como 300.00; a diferença interna é real.
        data["estado_inicial"]["vb_manual"]["valor"] = "300.000000000002"
    assert auth_client_user.post("/api/calcular", json=payload).status_code == 409
    assert db_session.query(HistoricoCalculo).count() == 1


def test_missing_reference_returns_specific_pending_without_history(
    auth_client_user, db_session
):
    data = plan()
    data["estado_inicial"].pop("vb_manual")
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "apuracao_periodos",
            "dados_extraidos": {"apuracao": data},
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"][0]["type"] == "referencia_salarial_pendente"
    assert db_session.query(HistoricoCalculo).count() == 0


def test_qualified_vb_and_rt_follow_salary_and_workload_changes(db_session):
    position = {
        "carreira": "MAGISTERIO_SUPERIOR",
        "vinculo": "EFETIVO",
        "jornada": "40H",
        "versao_carreira": "SINTETICA",
        "classe_docente": "Associado",
        "nivel_docente": 1,
    }
    for workload, start, end, vb, rt in (
        ("40H", "2024-02-01", "2024-02-14", "2900", "580"),
        ("40H", "2024-02-15", "2024-02-29", "5800", "1160"),
        ("20H", "2024-02-01", "2024-02-29", "1450", "290"),
        ("DE", "2024-02-01", "2024-02-29", "8700", "1740"),
    ):
        salvar_referencia(
            db_session,
            ReferenciaEntrada.model_validate(
                {
                    **position,
                    "jornada": workload,
                    "inicio_vigencia": start,
                    "fim_vigencia": end,
                    "vencimento_basico": vb,
                    "retribuicoes": [{"titulacao": "Mestrado", "valor": rt}],
                    "fonte": "Tabela docente sintética",
                    "estado": "CONFIRMADA",
                }
            ),
            1,
        )
    data = plan()
    data["estado_inicial"] = {"posicao": position, "titulacao": "Mestrado"}
    data["rubricas"] = [rubric(formula="VB_RT")]
    data["eventos"] = [
        event("20H", "2024-02-20", posicao={**position, "jornada": "20H"})
    ]
    result = calculate(data, db_session)
    assert result["total_geral_a_receber"] == "3480.00"
    assert [item["dias_computados"] for item in result["segmentos"]] == [14, 5, 10]
    assert all(
        sources[0]["referencia_id"] == sources[1]["referencia_id"]
        for sources in (item["referencias_tabelas"] for item in result["segmentos"])
    )


def test_explicit_null_and_absent_change_have_different_idempotency(auth_client_user):
    data = plan()
    data["eventos"] = [event("IQ", "2024-02-15", percentual_iq="10")]
    payload = {
        "tipo_calculo": "apuracao_periodos",
        "dados_extraidos": {"apuracao": data},
        "idempotency_key": str(uuid4()),
    }
    first = auth_client_user.post("/api/calcular", json=payload)
    assert first.status_code == 200, first.text
    data["eventos"][0]["alteracoes"]["vb_manual"] = None
    assert auth_client_user.post("/api/calcular", json=payload).status_code == 409


@pytest.mark.parametrize(
    "operation,target,value,code",
    [
        ("ESTORNO", "AUSENTE", "20", "estorno_sem_origem"),
        ("ESTORNO", "P1", "101", "estorno_excedente"),
    ],
)
def test_invalid_reversal_is_pending(db_session, operation, target, value, code):
    data = plan()
    data["recebidos"] = [
        payment(),
        payment("E1", value, sequencia="2", operacao=operation, estorna_id=target),
    ]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == code


def test_missing_percentage_is_not_presumed_zero(db_session):
    data = plan()
    data["rubricas"] = [rubric(formula="IQ_SOBRE_VB")]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == "percentual_pendente"


def test_result_budget_fails_before_persisting_large_trace(
    auth_client_user, db_session, monkeypatch
):
    monkeypatch.setattr("app.services.apuracao_periodos.MAX_RESULT_BYTES", 100)
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "apuracao_periodos",
            "dados_extraidos": {"apuracao": plan()},
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"][0]["type"] == "limite_resultado"
    assert db_session.query(HistoricoCalculo).count() == 0


def test_pdf_retains_exact_decimal_text_and_segment_metadata(db_session, tmp_path):
    import pdfplumber

    from app.services.gerador_pdf import GeradorPDF

    data = plan(amount="999999999999.123456789012")
    result = calculate(data, db_session)
    path = str(tmp_path / "synthetic-periods.pdf")
    GeradorPDF.gerar_relatorio(
        "apuracao_periodos", {"matricula": "DEMO-1"}, result, output_path=path
    )
    with pdfplumber.open(path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "R$ 999999999999.12" in text
    assert "Dias reais mes" in text
    assert "REGRA-SINTETICA" in text


def test_contract_is_authenticated_and_exposes_the_actual_period_fields(
    client, auth_client_user
):
    response = auth_client_user.get("/api/calculos/contratos/apuracao-periodos")
    assert response.status_code == 200
    schema = response.json()
    assert "apuracao" in schema["properties"]
    assert (
        "ultimo_dia_considerado" in schema["$defs"]["IntervaloApuracao"]["properties"]
    )
    auth_client_user.cookies.clear()
    assert client.get("/api/calculos/contratos/apuracao-periodos").status_code == 401
