"""Casos independentes e exclusivamente sintéticos de abono por parcelas."""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.schemas.abono_parcelas import PlanoAbono
from app.services.abono_parcelas import calcular_abono_parcelas
from app.services.pendencias import PendenciaApuracao


def mapping(code, role, category="REGULAR"):
    return {
        "rubrica": code,
        "papel": role,
        "categoria": category,
        "fonte": "Mapeamento sintético confirmado",
        "confirmado": True,
    }


def parcel(id="P", month="2026-01", last="2026-01-31"):
    return {
        "id": id,
        "categoria": "REGULAR",
        "competencia_direito": month,
        "periodo_referencia": {"inicio": f"{month}-01", "ultimo_dia_considerado": last},
        "rubrica_abono": "12345",
        "natureza_folha_devida": "NORMAL",
        "contribuicao": "IDENTIFICADA",
        "recebimento": "NAO_HOUVE_CONFIRMADO",
        "fonte_conferencia": "Conferência sintética por parcela",
    }


def posting(
    id="C",
    value="1000",
    role="CONTRIBUICAO",
    target="P",
    category="REGULAR",
    code=None,
    month="2026-01",
):
    return {
        "id": id,
        "papel": role,
        "categoria": category,
        "parcela_id": target,
        "competencia": month,
        "rubrica": code or ("98002" if role == "CONTRIBUICAO" else "12345"),
        "natureza_folha": "NORMAL",
        "natureza_rubrica": "D" if role == "CONTRIBUICAO" else "R",
        "identificador_folha": id,
        "sequencia": "0",
        "operacao": "LANCAMENTO",
        "valor": value,
        "origem": "Ficha sintética, linha 1",
        "conferido": True,
    }


def plan():
    return {
        "vinculo_id": "VINCULO-SINTETICO",
        "periodo_direito": {
            "inicio": "2026-01-01",
            "ultimo_dia_considerado": "2026-01-31",
        },
        "regra": {
            "identificador": "REGRA-SINTETICA",
            "versao": "1",
            "fonte": "Regra conferida pelo RH para teste",
            "inicio_vigencia": "2020-01-01",
            "formula": "CONTRIBUICAO_ELEGIVEL_CONFIRMADA",
            "confirmada": True,
        },
        "mapeamentos": [mapping("98002", "CONTRIBUICAO"), mapping("12345", "ABONO")],
        "parcelas": [parcel()],
        "cobertura_13": [
            {
                "exercicio": 2026,
                "situacao": "NAO_APLICAVEL_CONFIRMADO",
                "justificativa": "Escopo sintético conferido",
            }
        ],
        "lancamentos": [posting()],
        "conferido_pelo_rh": True,
    }


def calculate(data):
    return calcular_abono_parcelas(PlanoAbono.model_validate(data))


def test_prior_payment_reduces_target_even_in_later_supplemental_sheet():
    data = plan()
    data["parcelas"][0]["recebimento"] = "IDENTIFICADO"
    paid = posting("R", "250", "ABONO", month="2026-03")
    paid["natureza_folha"] = "SUPLEMENTAR"
    data["lancamentos"].append(paid)
    result = calculate(data)
    assert result["totais"]["devido"] == "1000.00"
    assert result["totais"]["recebido"] == "250.00"
    assert result["totais"]["saldo"] == "750.00"
    assert result["parcelas"][0]["competencia_direito"] == "2026-01"
    assert result["lancamentos_considerados"][1]["competencia"] == "2026-03"
    assert result["lancamentos_considerados"][1]["natureza_folha"] == "SUPLEMENTAR"


@pytest.mark.parametrize("same_abono_code", [False, True])
def test_regular_and_thirteenth_remain_distinct_in_same_month(same_abono_code):
    data = plan()
    data["periodo_direito"] = {
        "inicio": "2026-12-01",
        "ultimo_dia_considerado": "2026-12-31",
    }
    data["parcelas"] = [
        parcel(month="2026-12", last="2026-12-31"),
        {
            "id": "T",
            "categoria": "DECIMO_TERCEIRO",
            "exercicio_13": 2026,
            "periodo_referencia": {
                "inicio": "2026-01-01",
                "ultimo_dia_considerado": "2026-12-31",
            },
            "rubrica_abono": "12346",
            "natureza_folha_devida": "NORMAL",
            "contribuicao": "IDENTIFICADA",
            "recebimento": "NAO_HOUVE_CONFIRMADO",
            "fonte_conferencia": "13º conferido",
            "valor_elegivel": {
                "valor": "300",
                "fonte": "Base sintética",
                "localizador": "linha 3",
            },
            "justificativa_elegivel": "Elegibilidade do 13º confirmada manualmente",
        },
    ]
    data["cobertura_13"][0]["situacao"] = "INCLUIDO"
    data["mapeamentos"].extend(
        [
            mapping("98004", "CONTRIBUICAO", "DECIMO_TERCEIRO"),
            mapping("12346", "ABONO", "DECIMO_TERCEIRO"),
        ]
    )
    data["lancamentos"] = [
        posting(month="2026-12"),
        posting(
            "T1",
            "300",
            target="T",
            category="DECIMO_TERCEIRO",
            code="98004",
            month="2026-12",
        ),
        posting("R", "250", "ABONO", month="2026-12"),
    ]
    data["parcelas"][0]["recebimento"] = "IDENTIFICADO"
    if same_abono_code:
        data["parcelas"][1]["rubrica_abono"] = "12345"
        data["mapeamentos"][-1]["rubrica"] = "12345"
    result = calculate(data)
    assert [(row["categoria"], row["saldo"]) for row in result["parcelas"]] == [
        ("REGULAR", "750.00"),
        ("DECIMO_TERCEIRO", "300.00"),
    ]
    assert result["total_geral"] == "1050.00"


def test_copies_do_not_increase_due_but_distinct_equal_postings_do():
    data = plan()
    first = data["lancamentos"][0]
    data["lancamentos"].append(
        {**first, "id": "COPY", "origem": "Segunda via sintética"}
    )
    result = calculate(data)
    assert result["totais"]["devido"] == "1000.00"
    assert len(result["duplicidades"]) == 1
    data["lancamentos"].append(
        {**first, "id": "ANOTHER", "identificador_folha": "OUTRA-FOLHA"}
    )
    assert calculate(data)["totais"]["devido"] == "2000.00"


def test_cross_month_reversal_of_complement_and_aliases():
    data = plan()
    first = data["lancamentos"][0]
    supplement = {
        **first,
        "id": "S",
        "identificador_folha": "F2",
        "competencia": "2026-02",
        "operacao": "COMPLEMENTO",
        "complementa_id": "COPY",
        "valor": "100",
    }
    reversal = {
        **first,
        "id": "E",
        "identificador_folha": "F3",
        "competencia": "2026-03",
        "operacao": "ESTORNO",
        "estorna_id": "S",
        "natureza_rubrica": "R",
        "valor": "40",
    }
    data["lancamentos"] = [reversal, supplement, first, {**first, "id": "COPY"}]
    result = calculate(data)
    assert result["totais"]["devido"] == "1060.00"
    assert len(result["duplicidades"]) == 1
    data["lancamentos"][0]["valor"] = "101"
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data)
    assert error.value.codigo == "estorno_abono_excedente"


@pytest.mark.parametrize(
    "change,expected",
    [
        ("right", "direito_abono_pendente"),
        ("value", "lancamento_abono_pendente"),
        ("contribution", "dados_parcela_abono_pendentes"),
        ("payments", "dados_parcela_abono_pendentes"),
        ("missing_month", "cobertura_abono_pendente"),
        ("mapping", "rubrica_abono_pendente"),
        ("coverage13", "cobertura_13_abono_pendente"),
    ],
)
def test_unknown_data_remains_pending(change, expected):
    data = plan()
    if change == "right":
        data["regra"]["confirmada"] = False
    if change == "value":
        data["lancamentos"][0]["valor"] = None
    if change == "contribution":
        data["parcelas"][0]["contribuicao"] = "PENDENTE"
    if change == "payments":
        data["parcelas"][0]["recebimento"] = "PENDENTE"
    if change == "missing_month":
        data["periodo_direito"]["ultimo_dia_considerado"] = "2026-02-28"
    if change == "mapping":
        data["mapeamentos"][0]["confirmado"] = False
    if change == "coverage13":
        data["cobertura_13"][0]["situacao"] = "PENDENTE"
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data)
    assert error.value.codigo == expected


def test_zero_is_explicit_and_overpayment_remains_negative():
    data = plan()
    data["lancamentos"] = []
    data["parcelas"][0]["contribuicao"] = "ZERO_CONFIRMADO"
    assert calculate(data)["totais"]["saldo"] == "0.00"
    data["lancamentos"] = [posting("R", "100", "ABONO")]
    data["parcelas"][0]["recebimento"] = "IDENTIFICADO"
    assert calculate(data)["totais"]["saldo"] == "-100.00"


def test_partial_right_requires_confirmed_eligible_amount_without_day_rate():
    data = plan()
    data["periodo_direito"]["inicio"] = "2026-01-16"
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data)
    assert error.value.codigo == "base_parcial_abono_pendente"
    data["parcelas"][0].update(
        valor_elegivel={
            "valor": "400",
            "fonte": "Base elegível conferida",
            "localizador": "linha 4",
        },
        justificativa_elegivel="Desconto elegível revisado pelo RH",
    )
    assert calculate(data)["totais"]["devido"] == "400.00"


def test_one_financial_event_cannot_be_assigned_to_two_parcels():
    data = plan()
    data["lancamentos"].append(
        {**data["lancamentos"][0], "id": "COPY", "parcela_id": "OUTRA"}
    )
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data)
    assert error.value.codigo == "lancamento_abono_conflitante"


def test_final_rounding_accumulates_parcels_before_display():
    data = plan()
    data["periodo_direito"]["ultimo_dia_considerado"] = "2026-02-28"
    data["parcelas"].append(parcel("P2", "2026-02", "2026-02-28"))
    data["lancamentos"] = [
        posting(value="0.005"),
        posting("C2", "0.005", target="P2", month="2026-02"),
    ]
    result = calculate(data)
    assert [row["devido"] for row in result["parcelas"]] == ["0.01", "0.01"]
    assert result["totais"]["saldo"] == "0.01"
    assert result["totais"]["saldo_exato"] == {"numerador": "1", "denominador": "100"}


def test_api_history_exact_idempotency_contract_and_pdf(auth_client_user):
    data = {
        "tipo_calculo": "abono",
        "dados_extraidos": {"matricula": "000999", "abono": plan()},
        "idempotency_key": str(uuid4()),
    }
    first = auth_client_user.post("/api/calcular", json=data)
    assert first.status_code == 200, first.text
    data["dados_extraidos"]["abono"]["lancamentos"][0]["valor"] = "1000.000"
    assert auth_client_user.post("/api/calcular", json=data).json() == first.json()
    assert auth_client_user.get("/api/calculos/contratos/abono").status_code == 200
    pdf = auth_client_user.post(
        "/api/exportar-pdf", json={"historico_id": first.json()["historico_id"]}
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF-")


def test_observations_require_decision_and_matching_record():
    data = plan()
    observation = {
        "rubrica": "98002",
        "competencia": "2026-01",
        "natureza_rubrica": "D",
        "sequencia": "0",
        "valor_observado": "1000.00",
        "localizador": "linha 1",
    }
    data["documentos"] = [
        {
            "id": "D",
            "nome_arquivo": "sintetico.pdf",
            "vinculo_identificado": data["vinculo_id"],
            "vinculo_confirmado": True,
            "observacoes": [observation],
        }
    ]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data)
    assert error.value.codigo == "observacao_abono_pendente"
    observation.update(decisao="UTILIZADO", lancamento_id="C")
    assert calculate(data)["totais"]["devido"] == "1000.00"
    observation["valor_observado"] = "999"
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data)
    assert error.value.codigo == "observacao_abono_divergente"
    observation.update(
        decisao="DESCARTADO", justificativa="Documento de outro período conferido"
    )
    assert calculate(data)["totais"]["devido"] == "1000.00"


def test_extraction_keeps_98004_supplements_exact_cells_and_unknowns():
    from app.services.dados_pdf import extract_calculation_data

    text = "Ficha Financeira referente a: 2026\nRubrica|Nome|R/D|Seq.|DEZ|TOTAL\n98002|PSS|D|0|100,00|100,00\n98002|PSS|D|6|25,00|25,00\n98004|CONTR.PSS - GRATIF. NATALINA|D|0|30,00|30,00\n12345|ABONO PERMANENCIA|R|0|ilegível|0,00"
    result = extract_calculation_data(text, "abono", incluir_fontes_abono=True)
    rows = result["_observacoes_abono"]
    assert [
        (row["rubrica"], row["sequencia"], row["valor_observado"]) for row in rows
    ] == [
        ("98002", "0", "100.00"),
        ("98002", "6", "25.00"),
        ("98004", "0", "30.00"),
        ("12345", "0", None),
    ]
    assert all(row["decisao"] == "PENDENTE" for row in rows)
    assert result["alertas_extracao"]


def test_structured_upload_is_separate_from_legacy_payload(auth_client_user):
    from unittest.mock import patch

    from app.services.dados_pdf import extract_calculation_data

    result = extract_calculation_data(
        "Ficha Financeira referente a: 2026\nRubrica|Nome|R/D|Seq.|JAN\n98002|PSS|D|0|100,00",
        "abono",
        incluir_fontes_abono=True,
    )
    with patch(
        "app.routers.calculos_router.extract_pdf_data", return_value=deepcopy(result)
    ):
        response = auth_client_user.post(
            "/api/extrair-pdf",
            data={"tipo_calculo": "abono"},
            files={"arquivos": ("sintetico.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
    assert response.status_code == 200
    document = response.json()["resultados"][0]
    assert document["observacoes_abono"][0]["valor_observado"] == "100.00"
    assert "_observacoes_abono" not in document["dados_extraidos"]


def test_legacy_api_keeps_sum_but_marks_scope(auth_client_user):
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "abono",
            "dados_extraidos": {"valores_anuais": {"2026": [100, 200]}},
        },
    )
    assert response.status_code == 200
    assert response.json()["resultado_calculo"]["total_geral"] == 300
    assert response.json()["resultado_calculo"]["tipo_abono"] == "resumo_legado_v1"


def signed_observation(record, value):
    return {
        "id": "D",
        "nome_arquivo": "ficha-sintetica.pdf",
        "vinculo_identificado": "VINCULO-SINTETICO",
        "vinculo_confirmado": True,
        "observacoes": [
            {
                "rubrica": record["rubrica"],
                "competencia": record["competencia"],
                "natureza_rubrica": record["natureza_rubrica"],
                "sequencia": record["sequencia"],
                "valor_observado": value,
                "localizador": "linha 1",
                "decisao": "UTILIZADO",
                "lancamento_id": record["id"],
            }
        ],
    }


@pytest.mark.parametrize(
    "role,operation",
    [
        ("CONTRIBUICAO", "LANCAMENTO"),
        ("CONTRIBUICAO", "COMPLEMENTO"),
        ("ABONO", "LANCAMENTO"),
    ],
)
def test_negative_observation_cannot_increase_debit_or_credit_without_sign_review(
    role, operation
):
    data = plan()
    record = posting("N", "100", role)
    record["operacao"] = operation
    if operation == "COMPLEMENTO":
        record["complementa_id"] = "C"
    data["lancamentos"].append(record)
    if role == "ABONO":
        data["parcelas"][0]["recebimento"] = "IDENTIFICADO"
    data["documentos"] = [signed_observation(record, "-100.00")]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data)
    assert error.value.codigo == "sinal_observado_abono_pendente"


@pytest.mark.parametrize(
    "confirmed,reason,valid",
    [
        (False, "", False),
        (False, "Nota sem confirmação específica", False),
        (True, "", False),
        (True, "Sinal corrigido pelo RH após conferência da fonte sintética", True),
    ],
)
def test_negative_original_requires_both_sign_confirmation_and_reason(
    auth_client_user, confirmed, reason, valid
):
    data = plan()
    data["lancamentos"][0]["valor"] = "100"
    document = signed_observation(data["lancamentos"][0], "-100.00")
    document["observacoes"][0].update(
        correcao_sinal_confirmada=confirmed, justificativa=reason
    )
    data["documentos"] = [document]
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "abono",
            "dados_extraidos": {"matricula": "999", "abono": data},
        },
    )
    if valid:
        assert response.status_code == 200, response.text
        assert response.json()["resultado_calculo"]["totais"]["devido"] == "100.00"
    else:
        assert response.status_code == 400, response.text
        assert response.json()["detail"][0]["type"] == "sinal_observado_abono_pendente"


@pytest.mark.parametrize("observed,nature", [("-100.00", "D"), ("100.00", "R")])
def test_explicit_reversal_accepts_source_sign_conventions_without_extra_override(
    observed, nature
):
    data = plan()
    reversal = posting("E", "100")
    reversal.update(operacao="ESTORNO", estorna_id="C", natureza_rubrica=nature)
    data["lancamentos"].append(reversal)
    data["documentos"] = [signed_observation(reversal, observed)]
    assert calculate(data)["totais"]["devido"] == "900.00"


@pytest.mark.parametrize("count,warning", [(200, False), (201, True)])
def test_extraction_limit_is_not_silent_or_triggered_by_totals(count, warning):
    from app.utils.abono_candidates import extrair_observacoes_abono
    from app.utils.ficha_financeira import extrair_dados_ficha_financeira

    text = (
        "Ficha Financeira referente a: 2026\nRubrica|Nome|R/D|Seq.|JAN|TOTAL\n"
        + "\n".join(f"98002|PSS|D|{n}|1,00|1,00" for n in range(count))
    )
    rows, warnings = extrair_observacoes_abono(extrair_dados_ficha_financeira(text))
    assert len(rows) == 200
    assert bool(warnings) is warning
    if warning:
        assert "incompleta" in warnings[0]


def test_actual_worker_returns_structured_regular_and_thirteenth_observations(tmp_path):
    from fpdf import FPDF

    from app.services.pdf_extraction import extract_pdf_data

    path = tmp_path / "ficha-sintetica.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in (
        "Ficha Financeira referente a: 2026",
        "Rubrica|Nome|R/D|Seq.|DEZ|TOTAL",
        "98002|PSS|D|0|100,00|100,00",
        "98004|PSS GRAT NATALINA|D|0|30,00|30,00",
    ):
        pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))
    result = extract_pdf_data(str(path), "abono")
    assert [
        (row["rubrica"], row["valor_observado"]) for row in result["_observacoes_abono"]
    ] == [("98002", "100.00"), ("98004", "30.00")]
