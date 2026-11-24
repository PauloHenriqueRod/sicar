"""Casos sintéticos; expectativas independentes do serviço financeiro."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pdfplumber
import pytest
from pydantic import ValidationError

from app.models.fontes_oficiais import EstruturaFuncao, ReferenciaFuncao
from app.models.tabelas_salariais import HistoricoCalculo
from app.schemas.substituicao_periodos import PlanoSubstituicao
from app.services.pendencias import PendenciaApuracao
from app.services.substituicao_periodos import calcular_substituicao_periodos
from app.utils.clock import utcnow
from app.utils.function_keys import function_key


def interval(id, start, end, motivo="Fonte sintética"):
    return {
        "id": id,
        "inicio": start,
        "ultimo_dia_considerado": end,
        "motivo": motivo,
        "origem": "Documento sintético",
        "localizador": "linha 1",
    }


def fn(code="S1", manual=None):
    comp = {
        "componente": "GRATIFICACAO",
        "origem": "TABELA",
        "percentual_utilizado": "100",
    }
    if manual is not None:
        comp.update(
            origem="MANUAL",
            valor_manual={
                "valor": manual,
                "fonte": "Tabela sintética",
                "localizador": "linha 1",
            },
            inicio_vigencia="2019-01-01",
        )
    return {
        "tipo_funcao": "FG",
        "codigo_funcao": code,
        "modalidade": "TESTE",
        "componentes": [comp],
    }


def option():
    return {
        "identificador": "REGRA-SINTETICA",
        "versao": "1",
        "fonte": "Regra sintética conferida",
        "inicio_vigencia": "2019-01-01",
        "calculo": "DIFERENCA_FUNCOES",
        "diferenca_negativa": "ZERAR",
        "confirmada": True,
    }


def plan():
    return {
        "periodo": {"inicio": "2024-03-01", "ultimo_dia_considerado": "2024-03-31"},
        "designacao": interval("D", "2024-03-01", "2024-03-31"),
        "titular_matricula": "998",
        "afastamentos_titular": [interval("A", "2024-03-05", "2024-03-25")],
        "impedimentos_substituto": [
            interval("F", "2024-03-08", "2024-03-12", "Férias"),
            interval("L", "2024-03-10", "2024-03-14", "Licença"),
        ],
        "estado_inicial": {
            "substituida": fn(),
            "propria": {"situacao": "COM_FUNCAO", "funcao": fn("P1")},
            "opcao": option(),
        },
        "rubrica": {
            "rubrica": "83185",
            "natureza_folha": "NORMAL",
            "natureza_rubrica": "R",
        },
        "recebidos": [
            {
                "id": "P",
                "competencia": "2024-03",
                "rubrica": "83185",
                "natureza_folha": "NORMAL",
                "natureza_rubrica": "R",
                "identificador_folha": "F1",
                "sequencia": "0",
                "operacao": "PAGAMENTO",
                "valor": "500",
                "origem": "Ficha sintética, linha 1",
            }
        ],
        "conferido_pelo_rh": True,
    }


def reference(db, code, amount, start="2019-01-01", end=None):
    key = function_key("FG", code, "TESTE", "GRATIFICACAO")
    structure = db.query(EstruturaFuncao).filter_by(chave=key).first()
    if structure is None:
        structure = EstruturaFuncao(
            chave=key,
            tipo_funcao="FG",
            codigo_funcao=code,
            modalidade="TESTE",
            componente="GRATIFICACAO",
        )
        db.add(structure)
        db.flush()
    db.add(
        ReferenciaFuncao(
            estrutura_id=structure.id,
            valor=Decimal(amount),
            inicio_vigencia=date.fromisoformat(start),
            fim_vigencia=date.fromisoformat(end) if end else None,
            fonte="Tabela sintética confirmada",
            conferido_por=1,
            conferido_em=utcnow(),
        )
    )
    db.flush()


def seed(db):
    reference(db, "S1", "4100", end="2024-03-15")
    reference(db, "S1", "7200", start="2024-03-16")
    reference(db, "P1", "1000")


def calculate(data, db):
    return calcular_substituicao_periodos(PlanoSubstituicao.model_validate(data), db)


def test_crosses_three_sources_counts_overlap_once_and_follows_reference_change(
    db_session,
):
    seed(db_session)
    result = calculate(plan(), db_session)
    assert result["totais"]["devido"] == "2400.00"  # 3100*4/31 + 6200*10/31.
    assert result["totais"]["recebido"] == "500.00"
    assert result["totais"]["saldo"] == "1900.00"
    summary = result["dias_por_competencia"][0]
    assert summary["dias_considerados"] == 14
    assert summary["dias_aplicaveis"] == 21
    assert summary["dias_impedidos"] == 7
    assert summary["dias_excluidos"] == 17  # 10 fora do afastamento + 7 impedidos.
    assert {
        "motivos": ["IMPEDIMENTO:F", "IMPEDIMENTO:L"],
        "dias_excluidos": 3,
    } in summary["grupos_exclusao"]
    assert sum(s["dias_calendario"] for s in result["segmentos"]) == 31
    assert any(
        s["inicio"] == "2024-03-16" and s["referencias_funcoes"]
        for s in result["segmentos"]
    )


def test_reason_identifiers_are_opaque_even_when_they_contain_separators(db_session):
    seed(db_session)
    data = plan()
    data["impedimentos_substituto"][0]["id"] = "F | IMPEDIMENTO:L"
    result = calculate(data, db_session)
    assert {
        "motivos": ["IMPEDIMENTO:F | IMPEDIMENTO:L"],
        "dias_excluidos": 2,
    } in result["dias_por_competencia"][0]["grupos_exclusao"]
    assert result["totais"]["saldo"] == "1900.00"


def test_absence_overlap_and_impediments_outside_applicable_interval(db_session):
    seed(db_session)
    data = plan()
    data["afastamentos_titular"].append(interval("A2", "2024-03-10", "2024-03-20"))
    data["impedimentos_substituto"].extend(
        [
            interval("OUT", "2023-01-01", "2024-03-04"),
            interval("OUT2", "2024-03-26", "2025-01-01"),
        ]
    )
    assert calculate(data, db_session)["totais"]["saldo"] == "1900.00"


@pytest.mark.parametrize(
    "year,month,last,expected",
    [
        (2023, 2, 28, "50.01"),
        (2024, 2, 29, "51.73"),
        (2024, 4, 30, "53.34"),
        (2024, 5, 31, "54.84"),
    ],
)
def test_real_calendar_and_final_rounding(db_session, year, month, last, expected):
    start, end = f"{year}-{month:02}-01", f"{year}-{month:02}-{last}"
    data = plan()
    data.update(
        periodo={"inicio": start, "ultimo_dia_considerado": end},
        designacao=interval("D", start, end),
        afastamentos_titular=[interval("A", f"{year}-{month:02}-15", end)],
        impedimentos_substituto=[],
        recebidos=[],
    )
    data["estado_inicial"].update(
        substituida=fn(manual="100.01"), propria={"situacao": "SEM_FUNCAO_CONFIRMADA"}
    )
    assert calculate(data, db_session)["totais"]["devido"] == expected


def test_monthly_rounded_values_do_not_feed_total(db_session):
    data = plan()
    data.update(
        periodo={"inicio": "2023-12-01", "ultimo_dia_considerado": "2024-01-31"},
        designacao=interval("D", "2023-12-01", "2024-01-31"),
        afastamentos_titular=[interval("A", "2023-12-01", "2024-01-31")],
        impedimentos_substituto=[],
        recebidos=[],
    )
    data["estado_inicial"].update(
        substituida=fn(manual="0.015"), propria={"situacao": "SEM_FUNCAO_CONFIRMADA"}
    )
    result = calculate(data, db_session)
    assert [p["devido"] for p in result["por_competencia"]] == ["0.02", "0.02"]
    assert result["totais"]["devido"] == "0.03"


def test_function_code_and_option_changes_are_separate_segments(db_session):
    seed(db_session)
    reference(db_session, "NOVA", "10300")
    data = plan()
    changed = deepcopy(data["estado_inicial"])
    changed["substituida"] = fn("NOVA")
    data["eventos"] = [
        {
            "id": "E",
            "efeitos_financeiros": "2024-03-20",
            "origem": "Ato sintético",
            "estado": changed,
        }
    ]
    result = calculate(data, db_session)
    assert result["totais"]["devido"] == "3000.00"  # 400 + 6200*4/31 + 9300*6/31.
    assert any(
        s["inicio"] == "2024-03-20"
        and s["estado"]["substituida"]["codigo_funcao"] == "NOVA"
        for s in result["segmentos"]
    )


def test_missing_reference_is_specific_and_manual_path_remains_valid(db_session):
    data = plan()
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == "referencia_funcao_pendente"
    data["estado_inicial"].update(
        substituida=fn(manual="4100"), propria={"situacao": "SEM_FUNCAO_CONFIRMADA"}
    )
    assert calculate(data, db_session)["totais"]["devido"] == "1851.61"  # 4100*14/31.


def test_option_change_uses_new_composition_without_double_deducting_own_function(
    db_session,
):
    seed(db_session)
    data = plan()
    changed = deepcopy(data["estado_inicial"])
    changed["opcao"]["calculo"] = "BASE_SUBSTITUIDA"
    changed["propria"]["funcao"] = fn("NAO_NECESSARIA")
    data["eventos"] = [
        {
            "id": "OPCAO",
            "efeitos_financeiros": "2024-03-16",
            "origem": "Opção sintética conferida",
            "estado": changed,
        }
    ]
    result = calculate(data, db_session)
    assert result["totais"]["devido"] == "2722.58"  # 3100*4/31 + 7200*10/31.
    assert result["totais"]["saldo"] == "2222.58"


@pytest.mark.parametrize(
    "policy,due,balance",
    [("ZERAR", "0.00", "-500.00"), ("PERMITIR", "-1664.52", "-2164.52")],
)
def test_negative_monthly_difference_follows_confirmed_policy(
    db_session, policy, due, balance
):
    reference(db_session, "S1", "4100", end="2024-03-15")
    reference(db_session, "S1", "7200", start="2024-03-16")
    reference(db_session, "P1", "10000")
    data = plan()
    data["estado_inicial"]["opcao"]["diferenca_negativa"] = policy
    result = calculate(data, db_session)
    assert result["totais"]["devido"] == due
    assert result["totais"]["saldo"] == balance


def test_nonintersecting_dates_and_expired_option_are_pending(db_session):
    data = plan()
    data["afastamentos_titular"] = [interval("A", "2024-04-01", "2024-04-02")]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == "periodo_sem_intersecao"
    data = plan()
    data["estado_inicial"]["opcao"]["fim_vigencia"] = "2024-03-04"
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == "opcao_fora_vigencia"


def test_full_impediment_needs_no_salary_and_does_not_hide_overpayment(db_session):
    data = plan()
    data["impedimentos_substituto"] = [interval("I", "2024-03-01", "2024-03-31")]
    result = calculate(data, db_session)
    assert result["totais"]["devido"] == "0.00"
    assert result["totais"]["saldo"] == "-500.00"


def test_supplemental_payroll_is_reconciled_without_merging_source_sheets(
    auth_client_user, db_session
):
    seed(db_session)
    data = plan()
    supplement = {
        **data["recebidos"][0],
        "id": "SUP",
        "natureza_folha": "SUPLEMENTAR",
        "identificador_folha": "F2",
        "operacao": "COMPLEMENTO",
        "valor": "20",
    }
    data["recebidos"].extend([supplement, {**supplement, "id": "COPY"}])
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "substituicao",
            "dados_extraidos": {"matricula": "999", "substituicao": data},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["resultado_calculo"]
    assert result["totais"]["devido"] == "2400.00"
    assert result["totais"]["recebido"] == "520.00"
    assert result["totais"]["saldo"] == "1880.00"
    assert len(result["duplicidades"]) == 1
    sheets = {row["natureza_folha"]: row for row in result["por_competencia"]}
    assert sheets["NORMAL"]["recebido"] == "500.00"
    assert sheets["SUPLEMENTAR"]["recebido"] == "20.00"
    assert sheets["SUPLEMENTAR"]["devido"] == "0.00"


@pytest.mark.parametrize("field,value", [("rubrica", "98002"), ("natureza_rubrica", "D")])
def test_receipts_still_require_matching_rubric_and_kind(field, value):
    data = plan()
    data["recebidos"][0][field] = value
    with pytest.raises(ValidationError):
        PlanoSubstituicao.model_validate(data)


def test_payments_deduplicate_copies_and_keep_complements_and_reversals(db_session):
    seed(db_session)
    data = plan()
    data["recebidos"].extend(
        [
            {**data["recebidos"][0], "id": "COPY"},
            {
                **data["recebidos"][0],
                "id": "C",
                "sequencia": "1",
                "operacao": "COMPLEMENTO",
                "valor": "20",
            },
            {
                **data["recebidos"][0],
                "id": "R",
                "sequencia": "2",
                "operacao": "ESTORNO",
                "estorna_id": "COPY",
                "valor": "5",
            },
        ]
    )
    result = calculate(data, db_session)
    assert result["totais"]["recebido"] == "515.00"
    assert result["totais"]["saldo"] == "1885.00"
    assert len(result["duplicidades"]) == 1


@pytest.mark.parametrize(
    "change",
    [
        "missing_option",
        "unconfirmed",
        "same_event_day",
        "sum_total",
        "duplicate_component",
        "manual_no_source",
        "unknown_own_function",
    ],
)
def test_inconsistent_choices_are_rejected(change):
    data = plan()
    if change == "missing_option":
        del data["estado_inicial"]["opcao"]
    if change == "unconfirmed":
        data["estado_inicial"]["opcao"]["confirmada"] = 1
    if change == "same_event_day":
        data["eventos"] = [
            {
                "id": str(i),
                "efeitos_financeiros": "2024-03-20",
                "origem": "Ato sintético",
                "estado": data["estado_inicial"],
            }
            for i in (1, 2)
        ]
    if change in ("sum_total", "duplicate_component"):
        data["estado_inicial"]["substituida"]["componentes"].append(
            {
                **data["estado_inicial"]["substituida"]["componentes"][0],
                "componente": "TOTAL" if change == "sum_total" else "gratificação",
            }
        )
    if change == "manual_no_source":
        data["estado_inicial"]["substituida"]["componentes"][0]["origem"] = "MANUAL"
    if change == "unknown_own_function":
        data["estado_inicial"]["propria"] = {}
    with pytest.raises(ValidationError):
        PlanoSubstituicao.model_validate(data)


def test_api_history_idempotency_revision_and_function_read_permissions(
    auth_client_user, db_session
):
    seed(db_session)
    request = {
        "tipo_calculo": "substituicao",
        "dados_extraidos": {"matricula": "000999", "substituicao": plan()},
        "idempotency_key": str(uuid4()),
    }
    first = auth_client_user.post("/api/calcular", json=request)
    assert first.status_code == 200, first.text
    assert first.json()["resultado_calculo"]["totais"]["saldo"] == "1900.00"
    request["dados_extraidos"]["substituicao"]["estado_inicial"]["substituida"][
        "componentes"
    ][0]["percentual_utilizado"] = "100.000"
    assert auth_client_user.post("/api/calcular", json=request).json() == first.json()
    request["idempotency_key"] = str(uuid4())
    request["dados_extraidos"]["substitui_historico_id"] = first.json()["historico_id"]
    second = auth_client_user.post("/api/calcular", json=request)
    assert second.status_code == 200, second.text
    assert db_session.query(HistoricoCalculo).count() == 2
    exported = auth_client_user.post(
        "/api/exportar-pdf", json={"historico_id": first.json()["historico_id"]}
    )
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"] == "application/pdf"
    with pdfplumber.open(BytesIO(exported.content)) as pdf:
        text = " ".join(
            " ".join((page.extract_text() or "").split()) for page in pdf.pages
        )
    assert f"VERSÃO HISTÓRICA SUBSTITUÍDA PELO #{second.json()['historico_id']}" in text
    assert (
        auth_client_user.get("/api/calculos/contratos/substituicao").status_code == 200
    )
    refs = auth_client_user.get(
        "/api/calculos/referencias-funcao?inicio=2024-03-01&fim=2024-03-31"
    )
    assert refs.status_code == 200 and refs.json()["total"] == 3
    assert auth_client_user.get("/api/tabelas/fontes/funcoes").status_code == 403


def test_statement_identification_does_not_use_the_issuers_employee_number():
    from app.services.dados_pdf import extract_calculation_data

    data = extract_calculation_data(
        "Ficha Financeira referente a: 2024\nNome: 00999 - PESSOA SINTETICA Banco/Agência/C. Corrente: 000/0\nResponsável pela emissão\nMatrícula: 111\n",
        "substituicao",
    )
    assert data["matricula"] == "00999"
    assert data["nome"] == "PESSOA SINTETICA"


def test_reference_endpoint_requires_session(client):
    assert (
        client.get(
            "/api/calculos/referencias-funcao?inicio=2024-03-01&fim=2024-03-31"
        ).status_code
        == 401
    )


def test_pdf_exports_manual_function_events_without_raising_depth_limits(
    auth_client_user,
):
    data = plan()
    data["estado_inicial"].update(
        substituida=fn(manual="4100"),
        propria={"situacao": "COM_FUNCAO", "funcao": fn("P1", manual="1000")},
    )
    state = deepcopy(data["estado_inicial"])
    state["substituida"] = fn(manual="7200")
    data["eventos"] = [
        {
            "id": "E",
            "efeitos_financeiros": "2024-03-16",
            "origem": "Ato sintético",
            "estado": state,
        }
    ]
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "substituicao",
            "dados_extraidos": {"matricula": "999", "substituicao": data},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["resultado_calculo"]["totais"]["saldo"] == "1900.00"
    pdf = auth_client_user.post(
        "/api/exportar-pdf", json={"historico_id": response.json()["historico_id"]}
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF-")


@pytest.mark.parametrize("period_count,payment_count", [(100, 200), (101, 200), (100, 201), (101, 201)])
def test_extraction_warns_only_when_valid_source_items_exceed_limits(
    auth_client_user, period_count, payment_count
):
    from unittest.mock import patch

    from app.services.dados_pdf import extract_calculation_data

    text = "\n".join(
        ["Impedimento do substituto: 01/03/2024 a 02/03/2024"] * period_count
    )
    ficha = {
        "rubricas": {
            "83185": [
                {
                    "ano": 2024, "natureza": "R", "sequencia": i,
                    "meses": ["MAR", "TOTAL"], "celulas": ["1.00", "1.00"],
                }
                for i in range(payment_count)
            ]
        }
    }
    with patch("app.services.dados_pdf.extrair_dados_ficha_financeira", return_value=ficha):
        extracted = extract_calculation_data(text, "substituicao")
    with patch("app.routers.calculos_router.extract_pdf_data", return_value=extracted):
        response = auth_client_user.post(
            "/api/extrair-pdf",
            data={"tipo_calculo": "substituicao"},
            files={"arquivos": ("sintetico.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
    assert response.status_code == 200, response.text
    document = response.json()["resultados"][0]
    assert len(document["candidatos_substituicao"]) == 100
    assert len(document["pagamentos_observados"]) == 200
    warnings = document["dados_extraidos"]["alertas_extracao"]
    assert len(warnings) == (period_count > 100) + (payment_count > 200)
    assert any("100 períodos" in warning for warning in warnings) == (period_count > 100)
    assert any("200 pagamentos" in warning for warning in warnings) == (payment_count > 200)
    assert all("manualmente" in warning and "incompleta" in warning for warning in warnings)


def test_document_candidates_are_outside_financial_payload_and_never_assume_days(
    auth_client_user,
):
    from unittest.mock import patch

    from app.services.dados_pdf import extract_calculation_data

    text = "Designação: 01/03/2024 a 31/03/2024\nAfastamento do titular: 05/03/2024 até 25/03/2024\nFérias do substituto: 08/03/2024 a 12/03/2024\nFérias: 01/02/2024 a 02/02/2024"
    result = extract_calculation_data(text, "substituicao")
    assert [row["campo"] for row in result["_candidatos_substituicao"]] == [
        "DESIGNACAO",
        "AFASTAMENTO_TITULAR",
        "IMPEDIMENTO_SUBSTITUTO",
    ]
    assert result["salario_substituta"] is None and result["dias_interrupcao"] is None
    with patch("app.routers.calculos_router.extract_pdf_data", return_value=result):
        response = auth_client_user.post(
            "/api/extrair-pdf",
            data={"tipo_calculo": "substituicao"},
            files={"arquivos": ("sintetico.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
    assert response.status_code == 200, response.text
    document = response.json()["resultados"][0]
    assert len(document["candidatos_substituicao"]) == 3
    assert "_candidatos_substituicao" not in document["dados_extraidos"]


@pytest.mark.parametrize(
    "person,matricula,expected",
    [
        (None, "999", 400),
        ("SUBSTITUTO", "998", 400),
        ("TITULAR", "999", 400),
        ("TITULAR", "998", 200),
        ("SUBSTITUTO", "000999", 200),
    ],
)
def test_document_identity_is_reviewed_before_calculation(
    auth_client_user, db_session, person, matricula, expected
):
    seed(db_session)
    data = plan()
    data["documentos"] = [
        {
            "id": "DOC",
            "nome_arquivo": "sintetico.pdf",
            "matricula_identificada": matricula,
            "pessoa": person,
        }
    ]
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "substituicao",
            "dados_extraidos": {"matricula": "999", "substituicao": data},
        },
    )
    assert response.status_code == expected, response.text


def test_manual_csv_has_no_function_or_period_defaults(tmp_path):
    from app.utils.csv_leitores import ler_csv_substituicao

    path = tmp_path / "incompleto.csv"
    path.write_text(
        "Nome:,Pessoa sintética\nFunção que substitui,FG_01,CD_03\n",
        encoding="utf-8-sig",
    )
    result = ler_csv_substituicao(str(path))
    assert "calculo" not in result and "funcao_substituta" not in result
    assert result["alertas_extracao"]


def test_payments_observed_in_statement_do_not_become_confirmed_payments(
    auth_client_user, db_session
):
    from app.services.dados_pdf import extract_calculation_data

    text = "Ficha Financeira referente a: 2024 - 1º Semestre\nRubrica|Nome Rubrica|R/D|Seq.| MAR | TOTAL\n83185|SUBSTITUICAO|R|0|500,00|500,00\n83185|SUBSTITUICAO|R|2|-5,00|-5,00\n"
    extracted = extract_calculation_data(text, "substituicao")
    observed = extracted["_pagamentos_substituicao"]
    assert len(observed) == 2
    assert [item["valor_observado"] for item in observed] == ["500.0", "-5.0"]
    assert all(item["competencia"] == "2024-03" for item in observed)
    assert "operacao" not in observed[1]  # Valor negativo não presume estorno.
    seed(db_session)
    data = plan()
    data["documentos"] = [
        {
            "id": "FIN",
            "nome_arquivo": "sintetico.pdf",
            "papel": "FICHA_FINANCEIRA",
            "pessoa": "SUBSTITUTO",
            "matricula_identificada": "999",
            "pagamentos_observados": observed,
        }
    ]
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "substituicao",
            "dados_extraidos": {"matricula": "999", "substituicao": data},
        },
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["resultado_calculo"]["totais"]["recebido"] == "500.00"
    )  # Somente o lançamento confirmado do plano.
