"""Expectativas independentes, documentos sintéticos e banco temporário."""

from copy import deepcopy
from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.schemas.rescisao_periodos import PlanoRescisao
from app.services.pendencias import PendenciaApuracao
from app.services.rescisao_periodos import calcular_rescisao_periodos, previa_rescisao


def manual(value="6000"):
    return {"valor": value, "fonte": "Fonte sintética", "localizador": "linha 1"}


def base(value="6000"):
    return {"titulacao": "N/A", "valor_manual": manual(value)}


def plan():
    return {
        "modalidade": "PROFESSOR_SUBSTITUTO",
        "motivo_termino": "TERMINO_CONTRATO",
        "contrato_id": "SINTETICO-1",
        "natureza_folha_devida": "NORMAL",
        "inicio_exercicio": "2025-01-16",
        "data_termino": "2026-08-31",
        "sentido_termino": "A_PARTIR_DE",
        "ultimo_dia_trabalhado": "2026-08-30",
        "ultimo_dia_considerado": "2026-08-30",
        "regra": {
            "identificador": "REGRA-SINTETICA",
            "versao": "1",
            "fonte": "Fonte sintética confirmada",
            "inicio_vigencia": "2020-01-01",
            "confirmada": True,
            "motivos_suportados": ["TERMINO_CONTRATO"],
            "ferias_sem_teto_confirmada": True,
        },
        "salarios": [
            {
                "inicio": "2026-08-01",
                "ultimo_dia_considerado": "2026-08-30",
                "base": base(),
            }
        ],
        "base_ferias": base(),
        "base_13": base(),
        "pagamentos_ferias": [],
        "recebidos": [],
        "conferido_pelo_rh": True,
    }


def payment(
    id="F1", start="2025-01-16", end="2026-01-15", competencia="2025-07", value="2000"
):
    return {
        "id": id,
        "competencia": competencia,
        "rubrica": "00750",
        "natureza_folha": "NORMAL",
        "natureza_rubrica": "R",
        "identificador_folha": id,
        "sequencia": "0",
        "operacao": "PAGAMENTO",
        "valor": value,
        "origem": "Ficha sintética, linha 1",
        "avos": 12,
        "periodo_aquisitivo": {"inicio": start, "ultimo_dia_considerado": end},
        "base_terco": manual(),
    }


def calculate(data, db):
    return calcular_rescisao_periodos(PlanoRescisao.model_validate(data), db)


@pytest.mark.parametrize("reversed_amount", ["40", "100"])
def test_reversal_of_complement_keeps_original_avos_and_accepts_aliases(
    auth_client_user, reversed_amount
):
    data = plan()
    original = payment()
    complement = {
        **original,
        "id": "COMP",
        "identificador_folha": "F2",
        "operacao": "COMPLEMENTO",
        "pagamento_original_id": "COPY_ORIGINAL",
        "avos": 0,
        "valor": "100",
    }
    reversal = {
        **original,
        "id": "REV",
        "identificador_folha": "F3",
        "operacao": "ESTORNO",
        "estorna_id": "COPY_COMP",
        "avos": 0,
        "valor": reversed_amount,
    }
    # Documento pode listar o estorno antes das segundas vias dos pagamentos.
    data["pagamentos_ferias"] = [
        reversal,
        original,
        complement,
        {**original, "id": "COPY_ORIGINAL"},
        {**complement, "id": "COPY_COMP"},
    ]
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "rescisao",
            "dados_extraidos": {"matricula": "999", "rescisao": data},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["resultado_calculo"]
    assert result["avos_ferias_quitados"] == 12
    assert result["avos_ferias_devidos"] == 8
    assert len(result["duplicidades"]) == 2
    assert result["detalhamento_rubricas"]["00772"]["devido"] == "4000.00"


@pytest.mark.parametrize(
    "reversed_amount,avos,code",
    [("101", 0, "estorno_excedente"), ("100", 1, "estorno_complemento_com_avos")],
)
def test_reversal_of_complement_cannot_exceed_value_or_reverse_avos(
    db_session, reversed_amount, avos, code
):
    data = plan()
    original = payment()
    complement = {
        **original,
        "id": "COMP",
        "identificador_folha": "F2",
        "operacao": "COMPLEMENTO",
        "pagamento_original_id": "F1",
        "avos": 0,
        "valor": "100",
    }
    reversal = {
        **original,
        "id": "REV",
        "identificador_folha": "F3",
        "operacao": "ESTORNO",
        "estorna_id": "COMP",
        "avos": avos,
        "valor": reversed_amount,
    }
    data["pagamentos_ferias"] = [original, complement, reversal]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == code


def test_reversed_complement_reduces_amount_available_for_third_refund(db_session):
    data = plan()
    last = payment("F2", "2026-01-16", "2027-01-15", "2026-07", "600")
    complement = {
        **last,
        "id": "COMP",
        "identificador_folha": "F3",
        "operacao": "COMPLEMENTO",
        "pagamento_original_id": "F2",
        "avos": 0,
        "valor": "100",
    }
    reversal = {
        **last,
        "id": "REV",
        "identificador_folha": "F4",
        "operacao": "ESTORNO",
        "estorna_id": "COMP",
        "avos": 0,
        "valor": "100",
    }
    data["pagamentos_ferias"] = [payment(), last, complement]
    assert (
        calculate(data, db_session)["detalhamento_rubricas"]["82696"]["devido"]
        == "-666.67"
    )
    data["pagamentos_ferias"].append(reversal)
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == "devolucao_superior_ao_pago"


def test_unchanged_salary_day_confirmation_keeps_each_segment_days(db_session):
    data = plan()
    data["salarios"] = [
        {
            "inicio": "2026-08-01",
            "ultimo_dia_considerado": "2026-08-15",
            "base": base("3100"),
        },
        {
            "inicio": "2026-08-16",
            "ultimo_dia_considerado": "2026-08-30",
            "base": base("6200"),
        },
    ]
    data["correcoes"] = {
        "dias_salariais": {
            "valor": 30,
            "justificativa": "Quantidade conferida sem alteração",
        }
    }
    result = calculate(data, db_session)
    assert result["detalhamento_rubricas"]["00742"]["devido"] == "4500.00"
    assert [
        segment["dias_computados"] for segment in result["segmentos_salariais"]
    ] == [15, 15]
    assert result["previa"]["correcoes"]["dias_salariais"]["valor"] == 30
    data["correcoes"]["dias_salariais"]["valor"] = 29
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == "dias_com_multiplas_bases"


@pytest.mark.parametrize("nature", ["normal", " NORMAL ", "Normal"])
def test_due_and_paid_payroll_natures_share_canonical_key(db_session, nature):
    data = plan()
    data["natureza_folha_devida"] = nature
    received = {
        key: value
        for key, value in payment(value="100", competencia="2026-08").items()
        if key not in ("avos", "periodo_aquisitivo", "base_terco")
    }
    received["rubrica"] = "00742"
    data["recebidos"] = [received]
    result = calculate(data, db_session)
    rows = [row for row in result["por_competencia"] if row["rubrica"] == "00742"]
    assert len(rows) == 1
    assert rows[0]["natureza_folha"] == "NORMAL"
    assert rows[0]["devido"] == "5806.45"
    assert rows[0]["recebido"] == "100.00"
    assert rows[0]["saldo"] == "5706.45"


@pytest.mark.parametrize(
    "count,avos,principal,third",
    [
        (0, 20, "10000.00", "3333.33"),
        (1, 8, "4000.00", "1333.33"),
        (2, -4, "0.00", "-666.67"),
    ],
)
def test_rh_anniversary_examples(db_session, count, avos, principal, third):
    data = plan()
    if count:
        data["pagamentos_ferias"].append(payment())
    if count == 2:
        data["pagamentos_ferias"].append(
            payment("F2", "2026-01-16", "2027-01-15", "2026-07")
        )
    result = calculate(data, db_session)
    assert result["avos_ferias_devidos"] == avos
    assert result["detalhamento_rubricas"]["00772"]["devido"] == principal
    assert result["detalhamento_rubricas"]["82696"]["devido"] == third
    assert result["previa"]["dias_fracao_final"] == 15


def test_refund_uses_last_historical_base_and_requires_it(db_session):
    data = plan()
    last = payment("F2", "2026-01-16", "2027-01-15", "2026-07", "1800")
    last["base_terco"] = manual("5400")
    data["pagamentos_ferias"] = [payment(), last]
    result = calculate(data, db_session)
    assert result["detalhamento_rubricas"]["82696"]["devido"] == "-600.00"
    assert result["devolucoes_terco"][0]["pagamento_id"] == "F2"
    del data["pagamentos_ferias"][1]["base_terco"]
    with pytest.raises(PendenciaApuracao, match="base pertinente"):
        calculate(data, db_session)


@pytest.mark.parametrize(
    "day,last,expected",
    [
        (29, "2024-03-13", 1),
        (29, "2024-03-14", 2),
        (30, "2024-03-13", 1),
        (30, "2024-03-14", 2),
        (31, "2024-03-13", 1),
        (31, "2024-03-14", 2),
        (31, "2023-03-13", 1),
        (31, "2023-03-14", 2),
    ],
)
def test_anniversary_short_months_independent_boundaries(day, last, expected):
    data = plan()
    year = date.fromisoformat(last).year
    data.update(
        inicio_exercicio=f"{year}-01-{day}",
        data_termino=last,
        sentido_termino="INCLUSIVO",
        ultimo_dia_trabalhado=last,
        ultimo_dia_considerado=last,
    )
    data["regra"]["aniversario_meses_curtos"] = "LIMITAR_DIA_AO_MES"
    # Feb 29 + Mar 1..13 = 14; Feb 29 + Mar 1..14 = 15 (leap).
    # Non-leap Jan31 -> Feb28; Feb28..Mar13 =14, ..Mar14=15.
    result = previa_rescisao(PlanoRescisao.model_validate(data))
    assert result["sugestoes"]["avos_ferias"] == expected
    assert result["dias_fracao_final"] in (14, 15)


def test_end_exclusive_and_first_of_month_do_not_shift_salary_competence():
    data = plan()
    data.update(
        data_termino="2026-09-01",
        ultimo_dia_considerado="2026-08-31",
        ultimo_dia_trabalhado="2026-08-31",
    )
    preview = previa_rescisao(PlanoRescisao.model_validate(data))
    assert preview["competencia_salarial"] == "2026-08"
    assert preview["sugestoes"]["dias_salariais"] == 31


def test_full_salary_is_compared_to_proportional_due(db_session):
    data = plan()
    data.update(
        inicio_exercicio="2026-08-01",
        data_termino="2026-08-16",
        ultimo_dia_trabalhado="2026-08-15",
        ultimo_dia_considerado="2026-08-15",
    )
    data["salarios"] = [
        {
            "inicio": "2026-08-01",
            "ultimo_dia_considerado": "2026-08-15",
            "base": base("3100"),
        }
    ]
    paid = payment(value="3100", competencia="2026-08")
    data["recebidos"] = [
        {
            key: value
            for key, value in paid.items()
            if key not in ("avos", "periodo_aquisitivo", "base_terco")
        }
    ]
    data["recebidos"][0]["rubrica"] = "00742"
    result = calculate(data, db_session)
    assert result["detalhamento_rubricas"]["00742"]["devido"] == "1500.00"
    assert result["detalhamento_rubricas"]["00742"]["saldo"] == "-1600.00"


def test_complement_copy_and_explicit_reversal_do_not_count_new_twelve_avos(db_session):
    data = plan()
    original = payment()
    data["pagamentos_ferias"] = [
        original,
        {**original, "id": "COPY"},
        {
            **original,
            "id": "COMP",
            "identificador_folha": "F2",
            "sequencia": "6",
            "operacao": "COMPLEMENTO",
            "pagamento_original_id": "COPY",
            "valor": "100",
            "avos": 0,
        },
        {
            **original,
            "id": "REV",
            "sequencia": "7",
            "operacao": "ESTORNO",
            "estorna_id": "COPY",
            "valor": "500",
            "avos": 3,
        },
    ]
    result = calculate(data, db_session)
    assert result["avos_ferias_quitados"] == 9
    assert result["avos_ferias_devidos"] == 11
    assert len(result["duplicidades"]) == 1


def test_more_than_24_avos_is_not_truncated(db_session):
    data = plan()
    data["inicio_exercicio"] = "2023-01-16"
    result = calculate(data, db_session)
    assert result["avos_ferias_adquiridos"] == 44
    data["regra"]["ferias_sem_teto_confirmada"] = False
    with pytest.raises(PendenciaApuracao, match="ausência de teto"):
        calculate(data, db_session)
    data["regra"]["limite_avos_ferias"] = 24
    with pytest.raises(PendenciaApuracao, match="sem truncamento"):
        calculate(data, db_session)


@pytest.mark.parametrize(
    "change,code",
    [
        ("unconfirmed", "rescisao_sem_conferencia"),
        ("other", "motivo_termino_nao_suportado"),
        ("missing_last", "ultimos_dias_pendentes"),
        ("no_base", "base_rescisao_pendente"),
        ("salary_gap", "salario_final_sem_cobertura"),
        ("document_contract", "documento_contrato_pendente"),
    ],
)
def test_specific_pending_cases(db_session, change, code):
    data = plan()
    if change == "unconfirmed":
        data["regra"]["confirmada"] = False
    if change == "other":
        data["motivo_termino"] = "OUTRO"
    if change == "missing_last":
        del data["ultimo_dia_trabalhado"]
    if change == "no_base":
        del data["base_ferias"]
    if change == "salary_gap":
        data["salarios"] = []
    if change == "document_contract":
        data["documentos"] = [
            {
                "id": "DOC",
                "nome_arquivo": "sintetico.pdf",
                "papel": "CADASTRO",
                "contrato_identificado": "OUTRO",
            }
        ]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == code


def test_api_preview_history_idempotency_and_pdf(auth_client_user):
    payload = {"matricula": "999", "rescisao": plan()}
    preview = auth_client_user.post("/api/calculos/rescisao/previa", json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["sugestoes"]["avos_ferias"] == 20
    request = {
        "tipo_calculo": "rescisao",
        "dados_extraidos": payload,
        "idempotency_key": str(uuid4()),
    }
    response = auth_client_user.post("/api/calcular", json=request)
    assert response.status_code == 200, response.text
    result = response.json()["resultado_calculo"]
    assert result["saldo_parcelas_calculadas"] == result["total_liquido_a_receber"]
    request["dados_extraidos"]["rescisao"]["base_ferias"]["valor_manual"]["valor"] = (
        "6000.000"
    )
    assert (
        auth_client_user.post("/api/calcular", json=request).json() == response.json()
    )
    pdf = auth_client_user.post(
        "/api/exportar-pdf", json={"historico_id": response.json()["historico_id"]}
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF-")


def test_sources_are_observations_not_automatic_contract_payments(auth_client_user):
    from app.services.dados_pdf import extract_calculation_data

    text = "EXERCICIO: 01/01/2000\nCARGO/EMPREGO\nProfessor substituto\nEXERCICIO: 16/01/2025\nData de Rescisão: 31/08/2026\nContrato: SINTETICO-1\nINICIO|DIAS|PARCELA\n01JUL2026|10|1"
    extracted = extract_calculation_data(text, "rescisao", incluir_fontes_rescisao=True)
    candidates = extracted["_fontes_rescisao"]["candidatos"]
    assert [
        row["valor"] for row in candidates if row["campo"] == "inicio_exercicio"
    ] == ["2025-01-16"]
    assert any(
        row["campo"] == "inicio_ferias" and row["valor"] == "2026-07-01"
        for row in candidates
    )
    with patch(
        "app.routers.calculos_router.extract_pdf_data", return_value=deepcopy(extracted)
    ):
        response = auth_client_user.post(
            "/api/extrair-pdf",
            data={"tipo_calculo": "rescisao"},
            files={"arquivos": ("sintetico.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
    assert response.status_code == 200, response.text
    document = response.json()["resultados"][0]
    assert document["fontes_rescisao"]["candidatos"] == candidates
    assert "_fontes_rescisao" not in document["dados_extraidos"]


def test_end_changes_require_reason_and_preserve_suggestion():
    data = plan()
    data["ultimo_dia_considerado"] = "2026-08-29"
    data["ultimo_dia_trabalhado"] = "2026-08-29"
    with pytest.raises(PendenciaApuracao, match="Justifique"):
        previa_rescisao(PlanoRescisao.model_validate(data))
    data["justificativa_ultimo_dia"] = "Ajuste sintético conferido"
    data["correcoes"] = {
        "avos_ferias": {
            "valor": 19,
            "justificativa": "Período não computável conferido",
        }
    }
    preview = previa_rescisao(PlanoRescisao.model_validate(data))
    assert preview["ultimo_dia_sugerido"] == "2026-08-30"
    assert preview["adotados"]["avos_ferias"] == 19


def test_confirmed_catalog_vb_rt_and_midmonth_change(
    db_session, salary_reference, auth_client_user
):
    first, query = salary_reference(
        vinculo="TEMPORARIO",
        inicio_vigencia="2026-08-01",
        fim_vigencia="2026-08-15",
        vencimento_basico="2100",
        retribuicoes=[{"titulacao": "Mestrado", "valor": "1000"}],
    )
    second, _ = salary_reference(
        vinculo="TEMPORARIO",
        inicio_vigencia="2026-08-16",
        vencimento_basico="5200",
        retribuicoes=[{"titulacao": "Mestrado", "valor": "1000"}],
    )
    data = plan()
    data["salarios"][0]["base"] = {
        "referencia_salarial": query.model_dump(mode="json"),
        "titulacao": "Mestrado",
    }
    result = calculate(data, db_session)
    # 3100*15/31 + 6200*15/31 = 4500, independently of displayed rounding.
    assert result["detalhamento_rubricas"]["00742"]["devido"] == "4500.00"
    segments = result["segmentos_salariais"]
    assert [row["base"]["vencimento"]["id"] for row in segments] == [
        first.id,
        second.id,
    ]
    assert segments[0]["base"]["vencimento"]["valor_decimal"] == "2100.000000000000"
    assert segments[0]["base"]["retribuicao"]["valor_decimal"] == "1000.000000000000"
    assert sum(row["dias_computados"] for row in segments) == 30
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "rescisao",
            "dados_extraidos": {"matricula": "999", "rescisao": data},
        },
    )
    assert response.status_code == 200, response.text
    pdf = auth_client_user.post(
        "/api/exportar-pdf", json={"historico_id": response.json()["historico_id"]}
    )
    assert pdf.status_code == 200, pdf.text


def test_prior_thirteenth_advance_and_supplemental_sheet_are_preserved(db_session):
    data = plan()
    paid = payment(value="1000", competencia="2026-06")
    paid = {
        key: val
        for key, val in paid.items()
        if key not in ("periodo_aquisitivo", "base_terco", "avos")
    }
    paid.update(rubrica="82407", natureza_folha="SUPLEMENTAR")
    data["recebidos"] = [paid]
    result = calculate(data, db_session)
    assert result["detalhamento_rubricas"]["82407"]["saldo"] == "3000.00"
    assert any(
        row["competencia"] == "2026-06"
        and row["natureza_folha"] == "SUPLEMENTAR"
        and row["recebido"] == "1000.00"
        for row in result["por_competencia"]
    )


def test_same_identifier_cannot_hide_different_covered_avos(db_session):
    data = plan()
    data["pagamentos_ferias"] = [payment(), {**payment(), "avos": 6}]
    with pytest.raises(PendenciaApuracao, match="Mesmo identificador"):
        calculate(data, db_session)


def test_extraction_limits_are_explicit_and_invalid_values_remain_unknown():
    from app.utils.rescisao_candidates import extrair_fontes_rescisao

    ficha = {
        "rubricas": {
            "00750": [
                {
                    "ano": 2026,
                    "sequencia": index,
                    "natureza": "D",
                    "meses": ["MAR", "TOTAL"],
                    "celulas": [None, 100],
                    "celulas_invalidas": [0],
                }
                for index in range(201)
            ]
        }
    }
    result, warnings = extrair_fontes_rescisao("", ficha)
    assert len(result["pagamentos_observados"]) == 200
    assert result["pagamentos_observados"][0]["valor_observado"] is None
    assert result["pagamentos_observados"][0]["natureza_rubrica"] == "D"
    assert len(warnings) == 1 and "incompleta" in warnings[0]


def test_full_reversal_then_reissued_payment_for_same_period(db_session):
    data = plan()
    first = payment()
    data["pagamentos_ferias"] = [
        first,
        {
            **first,
            "id": "REV",
            "sequencia": "1",
            "operacao": "ESTORNO",
            "estorna_id": "F1",
        },
        {**first, "id": "NEW", "identificador_folha": "F2"},
    ]
    result = calculate(data, db_session)
    assert result["avos_ferias_quitados"] == 12
    assert result["avos_ferias_devidos"] == 8


def test_copies_with_different_document_locators_keep_one_financial_payment(db_session):
    data = plan()
    first = payment()
    copy = {
        **first,
        "id": "COPY",
        "origem": "Segunda via",
        "base_terco": {**first["base_terco"], "localizador": "linha 5 da segunda via"},
    }
    data["pagamentos_ferias"] = [first, copy]
    result = calculate(data, db_session)
    assert result["avos_ferias_quitados"] == 12
    assert len(result["duplicidades"]) == 1


def test_rounding_only_after_accumulating_exact_parcels(db_session):
    data = plan()
    data["inicio_exercicio"] = "2026-08-16"
    data["salarios"][0]["base"] = base("0")
    data["base_ferias"] = base("0.18")
    data["correcoes"] = {
        "avos_13": {"valor": 0, "justificativa": "Isolar férias em caso sintético"}
    }
    result = calculate(data, db_session)
    assert result["detalhamento_rubricas"]["00772"]["devido"] == "0.02"
    assert result["detalhamento_rubricas"]["82696"]["devido"] == "0.01"
    assert result["saldo_parcelas_calculadas"] == "0.02"


def test_actual_pdf_worker_preserves_structured_source_candidates(tmp_path):
    from fpdf import FPDF

    from app.services.pdf_extraction import extract_pdf_data

    path = tmp_path / "cadastro-sintetico.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in (
        "CARGO/EMPREGO",
        "Professor substituto",
        "EXERCICIO: 16/01/2025",
        "Contrato: SINTETICO-1",
    ):
        pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))
    result = extract_pdf_data(str(path), "rescisao")
    assert any(
        row["campo"] == "inicio_exercicio" and row["valor"] == "2025-01-16"
        for row in result["_fontes_rescisao"]["candidatos"]
    )


def test_last_third_is_selected_by_payment_order_not_acquisition_period(db_session):
    data = plan()
    last_paid = payment(competencia="2026-08", value="1800")
    last_paid["base_terco"] = manual("5400")
    data["pagamentos_ferias"] = [
        last_paid,
        payment("F2", "2026-01-16", "2027-01-15", "2026-07"),
    ]
    result = calculate(data, db_session)
    assert result["devolucoes_terco"][0]["pagamento_id"] == "F1"
    assert result["detalhamento_rubricas"]["82696"]["devido"] == "-600.00"


def test_same_competence_needs_confirmed_payment_order_for_refund(db_session):
    data = plan()
    data["pagamentos_ferias"] = [
        payment(competencia="2026-07"),
        payment("F2", "2026-01-16", "2027-01-15", "2026-07"),
    ]
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data, db_session)
    assert error.value.codigo == "ordem_tercos_pendente"
    for index, row in enumerate(data["pagamentos_ferias"], 1):
        row["ordem_devolucao"] = index
    result = calculate(data, db_session)
    assert result["devolucoes_terco"][0]["pagamento_id"] == "F2"
