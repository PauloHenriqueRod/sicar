"""Esperados independentes, dados sintéticos e bancos das fixtures de teste."""

from copy import deepcopy
from itertools import permutations
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.exercicios_parcelas import PlanoExercicios
from app.services.exercicios_parcelas import apurar_exercicios
from app.services.pendencias import PendenciaApuracao


def interval():
    return {"inicio": "2020-01-01", "ultimo_dia_considerado": "2020-01-31"}


def rule():
    return {
        "identificador": "REGRA-SINTETICA",
        "versao": "1",
        "fonte": "Fonte sintética conferida",
        "inicio_vigencia": "2020-01-01",
        "confirmada": True,
    }


def due(id="D", amount="1000", **kwargs):
    return {
        "id": id,
        "parcela_id": "P",
        "operacao": "LANCAMENTO",
        "valor": amount,
        "fonte": "Memória sintética",
        "localizador": "linha 1",
        "conferido": True,
        "identificador_evento": id,
        "memoria_calculo": "Base confirmada de 1000 para o mês integral",
        **kwargs,
    }


def payment(id="R", amount="250", **kwargs):
    return {
        "id": id,
        "parcela_id": "P",
        "operacao": "LANCAMENTO",
        "valor": amount,
        "fonte": "Comprovante sintético",
        "localizador": "página 1",
        "conferido": True,
        "tipo_origem": "DOCUMENTO",
        "identificador_pagamento": id,
        "justificativa_vinculo": "Processo identifica a parcela P",
        **kwargs,
    }


def plan():
    return {
        "vinculo_id": "VINCULO-SINTETICO",
        "periodo": interval(),
        "origens": [
            {
                "id": "O",
                "descricao": "Direito sintético",
                "periodo_efeitos": interval(),
                "data_documento": "2026-01-15",
                "fonte": "Ato sintético",
                "localizador": "item 1",
                "regra": rule(),
            }
        ],
        "parcelas": [
            {
                "id": "P",
                "origem_direito_id": "O",
                "competencia": "2020-01",
                "rubrica": "12345",
                "categoria": "PRINCIPAL",
                "periodo_referencia": interval(),
                "natureza_folha_devida": "NORMAL",
                "estado_revisao": "CONFERIDO",
                "nota_revisao": "Conferência sintética do direito e de pagamentos",
                "pesquisa_pagamentos": "NAO_HOUVE_CONFIRMADO",
            }
        ],
        "devidos": [due()],
        "recebimentos": [],
        "conferido_pelo_rh": True,
    }


def calculate(data):
    return apurar_exercicios(PlanoExercicios.model_validate(data))


def add_payment(data, *records):
    data["recebimentos"].extend(records)
    data["parcelas"][0]["pesquisa_pagamentos"] = "IDENTIFICADOS"


def assert_pending(data, code):
    with pytest.raises(PendenciaApuracao) as error:
        calculate(data)
    assert error.value.codigo == code


def test_payment_reduces_its_parcel_and_preserves_judicial_source_and_document_date():
    data = plan()
    add_payment(
        data,
        payment(
            via_pagamento="JUDICIAL",
            processo="PROCESSO-SINTETICO",
            data_pagamento="2026-02-10",
        ),
    )
    result = calculate(data)
    assert result["totais"] == {
        "devido": "1000.00",
        "recebido": "250.00",
        "saldo": "750.00",
        "saldo_exato": {"numerador": "750", "denominador": "1"},
    }
    assert result["parcelas"][0]["origem_direito"]["data_documento"] == "2026-01-15"
    receipt = result["recebimentos_considerados"][0]
    assert receipt["via_pagamento"] == "JUDICIAL"
    assert receipt["processo"] == "PROCESSO-SINTETICO"
    assert receipt["identificador_folha"] is None
    assert receipt["data_pagamento"] == "2026-02-10"


def test_distinct_origin_and_rubric_balances_do_not_mix():
    data = plan()
    origin = deepcopy(data["origens"][0])
    origin["id"] = "O2"
    parcel = deepcopy(data["parcelas"][0])
    parcel.update(id="P2", origem_direito_id="O2", rubrica="54321")
    data["origens"].append(origin)
    data["parcelas"].append(parcel)
    data["devidos"].append(due("D2", "300", parcela_id="P2"))
    add_payment(data, payment())
    result = calculate(data)
    assert [row["saldo"] for row in result["parcelas"]] == ["750.00", "300.00"]
    assert result["totais"]["saldo"] == "1050.00"


def test_complements_reversals_forward_references_and_aliases_are_not_duplicates():
    data = plan()
    data["devidos"] = [
        due("DC", "100", operacao="COMPLEMENTO", complementa_id="COPY"),
        due("DE", "40", operacao="ESTORNO", estorna_id="DC"),
        due(),
        due("COPY", identificador_evento="D"),
    ]
    add_payment(
        data,
        payment("RC", "50", operacao="COMPLEMENTO", complementa_id="R"),
        payment("RE", "10", operacao="ESTORNO", estorna_id="RC"),
        payment("R", "200"),
    )
    result = calculate(data)
    assert result["totais"]["devido"] == "1060.00"  # 1000 + 100 - 40
    assert result["totais"]["recebido"] == "240.00"  # 200 + 50 - 10
    assert result["totais"]["saldo"] == "820.00"
    assert len(result["devidos_considerados"]) == 3
    assert result["duplicidades_devidos"][0]["id"] == "COPY"


@pytest.mark.parametrize(
    "variant", ["identical", "physical_with_shared", "shared_document"]
)
def test_duplicate_payments_once_with_all_source_metadata_retained(variant):
    data = plan()
    original = payment(
        tipo_origem="FOLHA",
        identificador_pagamento=None,
        competencia_pagamento="2026-02",
        rubrica_pagamento="12345",
        natureza_folha="SUPLEMENTAR",
        natureza_rubrica="R",
        identificador_folha="F",
        sequencia="6",
    )
    duplicate = deepcopy(original)
    duplicate.update(id="COPY", fonte="Segunda fonte")
    if variant == "physical_with_shared":
        duplicate["identificador_pagamento"] = "PAGAMENTO-1"
    elif variant == "shared_document":
        original["identificador_pagamento"] = "PAGAMENTO-1"
        duplicate = payment(
            "COPY",
            identificador_pagamento="PAGAMENTO-1",
            via_pagamento="JUDICIAL",
            processo="PROCESSO-SINTETICO",
        )
    add_payment(data, original, duplicate)
    result = calculate(data)
    assert result["totais"]["recebido"] == "250.00"
    assert len(result["duplicidades_recebimentos"]) == 1
    if variant == "shared_document":
        assert (
            result["duplicidades_recebimentos"][0]["dados_informados"]["via_pagamento"]
            == "JUDICIAL"
        )


def test_conflicting_duplicate_and_distinct_original_dues_need_review():
    data = plan()
    data["devidos"].append(due("COPY", "999", identificador_evento="D"))
    assert_pending(data, "lancamento_exercicio_conflitante")
    data["devidos"][-1] = due("OTHER", "999")
    assert_pending(data, "devido_exercicio_duplicado")


@pytest.mark.parametrize(
    "change,code",
    [
        (lambda d: d["devidos"][0].update(valor=None), "lancamento_exercicio_pendente"),
        (
            lambda d: d["parcelas"][0].update(pesquisa_pagamentos="PENDENTE"),
            "revisao_exercicio_pendente",
        ),
        (
            lambda d: d["origens"][0]["regra"].update(confirmada=False),
            "origem_direito_exercicio_pendente",
        ),
        (lambda d: d.update(conferido_pelo_rh=False), "exercicio_sem_conferencia"),
        (lambda d: d.update(devidos=[]), "devido_exercicio_ausente"),
        (
            lambda d: d["parcelas"][0].update(competencia="2021-01"),
            "competencia_exercicio_fora_escopo",
        ),
    ],
)
def test_unknown_or_inconsistent_data_blocks_only_this_case(change, code):
    data = plan()
    change(data)
    assert_pending(data, code)


def test_confirmed_zero_is_distinct_from_unknown_payment_and_negative_balance_is_preserved():
    data = plan()
    data["devidos"][0]["valor"] = "0"
    assert calculate(data)["totais"]["saldo"] == "0.00"
    add_payment(data, payment(amount=None))
    assert_pending(data, "lancamento_exercicio_pendente")
    data["recebimentos"][0]["valor"] = "10"
    assert calculate(data)["totais"]["saldo"] == "-10.00"


@pytest.mark.parametrize("type", ["PRESCRICAO", "JUROS", "ATUALIZACAO", "DESCONTO"])
def test_adjustments_require_explicit_specific_rule_never_automatic(type):
    data = plan()
    assert (
        calculate(data)["totais"]["saldo"] == "1000.00"
    )  # old year alone has no effect
    adjustment = {
        "id": "A",
        "parcela_id": "P",
        "tipo": type,
        "efeito": "REDUCAO",
        "valor": "12.345",
        "regra": rule(),
        "memoria_calculo": "Valor manual calculado e conferido pelo RH",
        "fonte": "Regra sintética",
        "localizador": "item 2",
        "conferido": True,
    }
    data["ajustes"] = [adjustment]
    adjustment["regra"]["confirmada"] = False
    assert_pending(data, "ajuste_exercicio_sem_regra")
    adjustment["regra"]["confirmada"] = True
    assert calculate(data)["totais"]["saldo"] == "987.66"  # 987.655, HALF_UP final
    adjustment["valor"] = "1001"
    assert_pending(data, "ajuste_exercicio_excedente")


def test_final_rounding_does_not_sum_displayed_rounded_parcels():
    data = plan()
    data["devidos"][0]["valor"] = "0.005"
    parcel = deepcopy(data["parcelas"][0])
    parcel.update(id="P2", rubrica="54321")
    data["parcelas"].append(parcel)
    data["devidos"].append(due("D2", "0.005", parcela_id="P2"))
    assert calculate(data)["totais"]["saldo"] == "0.01"


@pytest.mark.parametrize(
    "operation,reference,amount,code",
    [
        ("ESTORNO", "MISSING", "1", "acerto_exercicio_incompativel"),
        ("ESTORNO", "D", "1001", "estorno_exercicio_excedente"),
        ("COMPLEMENTO", "MISSING", "1", "acerto_exercicio_incompativel"),
    ],
)
def test_inconsistent_corrections_block(operation, reference, amount, code):
    data = plan()
    field = "estorna_id" if operation == "ESTORNO" else "complementa_id"
    data["devidos"].append(due("E", amount, operacao=operation, **{field: reference}))
    assert_pending(data, code)


def document(candidate):
    return {
        "id": "DOC",
        "nome_arquivo": "sintetico.pdf",
        "vinculo_identificado": "VINCULO-SINTETICO",
        "vinculo_confirmado": True,
        "candidatos": [candidate],
    }


def test_document_candidates_require_decision_source_match_and_sign_confirmation():
    data = plan()
    candidate = {
        "tipo": "DEVIDO",
        "competencia": "2020-01",
        "rubrica": "12345",
        "valor_observado": "-1000",
        "localizador": "linha 1",
        "decisao": "UTILIZADO",
        "alvo_tipo": "DEVIDO",
        "alvo_id": "D",
    }
    data["documentos"] = [document(candidate)]
    assert_pending(data, "sinal_exercicio_pendente")
    candidate.update(
        correcao_sinal_confirmada=True,
        justificativa="Sinal conferido na fonte sintética",
    )
    assert calculate(data)["totais"]["saldo"] == "1000.00"
    candidate["valor_observado"] = "999"
    assert_pending(data, "candidato_exercicio_divergente")
    candidate.update(decisao="DESCARTADO", justificativa="Documento fora do escopo")
    assert calculate(data)["totais"]["saldo"] == "1000.00"
    data["documentos"][0]["vinculo_confirmado"] = False
    assert_pending(data, "documento_exercicio_pendente")


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1", True])
def test_invalid_monetary_values_rejected(amount):
    data = plan()
    data["devidos"][0]["valor"] = amount
    with pytest.raises(ValidationError):
        PlanoExercicios.model_validate(data)


def test_api_contract_history_idempotency_and_pdf(auth_client_user):
    data = {
        "tipo_calculo": "exercicio_anterior",
        "dados_extraidos": {"matricula": "000999", "exercicios": plan()},
        "idempotency_key": str(uuid4()),
    }
    first = auth_client_user.post("/api/calcular", json=data)
    assert first.status_code == 200, first.text
    assert first.json()["resultado_calculo"]["saldo_parcelas_calculadas"] == "1000.00"
    assert auth_client_user.post("/api/calcular", json=data).json() == first.json()
    assert (
        auth_client_user.get(
            "/api/calculos/contratos/exercicios-anteriores"
        ).status_code
        == 200
    )
    pdf = auth_client_user.post(
        "/api/exportar-pdf", json={"historico_id": first.json()["historico_id"]}
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF-")


def test_api_document_identity_and_pending_type(auth_client_user):
    data = plan()
    data["devidos"][0]["valor"] = None
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "exercicio_anterior",
            "dados_extraidos": {"matricula": "999", "exercicios": data},
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"][0]["type"] == "lancamento_exercicio_pendente"
    data["documentos"] = [
        {
            **document({"tipo": "DEVIDO", "localizador": "linha 1"}),
            "matricula_identificada": "888",
        }
    ]
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "exercicio_anterior",
            "dados_extraidos": {"matricula": "999", "exercicios": data},
        },
    )
    assert response.status_code == 400


def test_legacy_api_keeps_old_sum_and_labels_scope(auth_client_user):
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "exercicio_anterior",
            "dados_extraidos": {
                "fluxo_mensal": [{"periodo": "01/2020", "v_dev": 1000, "v_rec": 250}]
            },
        },
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["resultado_calculo"]["resumo_consolidado"][
            "total_geral_a_receber"
        ]
        == 750
    )
    assert response.json()["resultado_calculo"]["tipo_exercicio"] == "resumo_legado_v1"


def test_extraction_does_not_invent_missing_paid_zero_or_origin():
    from app.services.dados_pdf import extract_calculation_data

    data = extract_calculation_data(
        "Periodo: 01/2020 | Rubrica: 12345 | Devido: R$ 1.000,00 | Recebido: ilegivel",
        "exercicio_anterior",
        incluir_fontes_exercicios=True,
    )
    rows = data["_candidatos_exercicios"]
    assert [(row["tipo"], row["valor_observado"]) for row in rows] == [
        ("DEVIDO", "1000.00"),
        ("RECEBIMENTO", None),
    ]
    assert all(row["decisao"] == "PENDENTE" for row in rows)
    assert data["alertas_extracao"]


@pytest.mark.parametrize("count,warn", [(200, False), (201, True)])
def test_candidate_limit_explicit_and_totals_not_payments(count, warn):
    from app.utils.exercicios_candidates import extrair_candidatos_exercicios
    from app.utils.ficha_financeira import extrair_dados_ficha_financeira

    text = (
        "Ficha Financeira referente a: 2020\nRubrica|Nome|R/D|Seq.|JAN|TOTAL\n"
        + "\n".join(f"12345|REMUNERACAO|R|{n}|1,00|1,00" for n in range(count))
    )
    rows, warnings = extrair_candidatos_exercicios(
        text, extrair_dados_ficha_financeira(text)
    )
    assert len(rows) == 200
    assert bool(warnings) is warn


def test_actual_pdf_worker_returns_review_candidates(tmp_path):
    from fpdf import FPDF

    from app.services.pdf_extraction import extract_pdf_data

    path = tmp_path / "exercicio-sintetico.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 8, "Periodo: 01/2020 | Devido: R$ 1.000,00 | Recebido: R$ 250,00")
    pdf.output(str(path))
    result = extract_pdf_data(str(path), "exercicio_anterior")
    assert [row["valor_observado"] for row in result["_candidatos_exercicios"]] == [
        "1000.00",
        "250.00",
    ]


def test_extracted_supplement_sequences_cannot_both_be_linked_to_one_receipt():
    from app.services.dados_pdf import extract_calculation_data

    extracted = extract_calculation_data(
        "Ficha Financeira referente a: 2020\nRubrica|Nome|R/D|Seq.|JAN\n12345|SALARIO|R|0|250,00\n12345|SALARIO|R|6|250,00",
        "exercicio_anterior",
        incluir_fontes_exercicios=True,
    )
    rows = extracted["_candidatos_exercicios"]
    assert [row["sequencia"] for row in rows] == ["0", "6"]
    data = plan()
    add_payment(
        data,
        payment(
            tipo_origem="FOLHA",
            competencia_pagamento="2020-01",
            rubrica_pagamento="12345",
            natureza_folha="NORMAL",
            natureza_rubrica="R",
            identificador_folha="F",
            sequencia="0",
        ),
    )
    for row in rows:
        row.update(decisao="UTILIZADO", alvo_tipo="RECEBIMENTO", alvo_id="R")
    data["documentos"] = [{**document(rows[0]), "candidatos": rows}]
    assert_pending(data, "candidato_exercicio_divergente")


def test_pdf_and_idempotency_preserve_duplicate_document_sources(auth_client_user):
    data = plan()
    add_payment(
        data,
        payment("R"),
        payment(
            "COPY",
            identificador_pagamento="R",
            via_pagamento="JUDICIAL",
            processo="PROCESSO-TESTE",
        ),
    )
    request = {
        "tipo_calculo": "exercicio_anterior",
        "dados_extraidos": {"matricula": "999", "exercicios": data},
        "idempotency_key": str(uuid4()),
    }
    response = auth_client_user.post("/api/calcular", json=request)
    assert response.status_code == 200, response.text
    assert (
        response.json()["resultado_calculo"]["duplicidades_recebimentos"][0][
            "dados_informados"
        ]["processo"]
        == "PROCESSO-TESTE"
    )
    data["devidos"][0]["valor"] = "1000.0000"
    assert (
        auth_client_user.post("/api/calcular", json=request).json() == response.json()
    )
    pdf = auth_client_user.post(
        "/api/exportar-pdf", json={"historico_id": response.json()["historico_id"]}
    )
    assert pdf.status_code == 200, pdf.text


def test_api_extraction_exposes_candidates_outside_legacy_data(auth_client_user):
    from unittest.mock import patch

    from app.services.dados_pdf import extract_calculation_data

    data = extract_calculation_data(
        "Periodo: 01/2020 | Devido: R$ 1.000,00",
        "exercicio_anterior",
        incluir_fontes_exercicios=True,
    )
    with patch("app.routers.calculos_router.extract_pdf_data", return_value=data):
        response = auth_client_user.post(
            "/api/extrair-pdf",
            data={"tipo_calculo": "exercicio_anterior"},
            files={"arquivos": ("sintetico.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
    assert response.status_code == 200, response.text
    result = response.json()["resultados"][0]
    assert result["candidatos_exercicios"][0]["valor_observado"] == "1000.00"
    assert "_candidatos_exercicios" not in result["dados_extraidos"]


@pytest.mark.parametrize(
    "changes",
    [
        {"via_pagamento": "ADMINISTRATIVA"},
        {"data_pagamento": "2026-02-02"},
        {"processo": "OUTRO-PROCESSO"},
    ],
)
def test_conflicting_known_metadata_is_not_silently_discarded_as_a_duplicate(changes):
    data = plan()
    first = payment(
        via_pagamento="JUDICIAL", data_pagamento="2026-02-01", processo="PROCESSO-1"
    )
    second = {**first, "id": "COPY", **changes}
    add_payment(data, first, second)
    assert_pending(data, "fonte_pagamento_exercicio_conflitante")


@pytest.mark.parametrize("order", list(permutations(range(3))))
@pytest.mark.parametrize(
    "field,left,right",
    [
        ("via_pagamento", "JUDICIAL", "ADMINISTRATIVA"),
        ("processo", "PROCESSO-A", "PROCESSO-B"),
        ("data_pagamento", "2026-02-01", "2026-02-02"),
        ("folha", "FOLHA-A", "FOLHA-B"),
    ],
)
def test_all_duplicate_sources_are_compared_even_when_first_source_is_unknown(
    order, field, left, right
):
    data = plan()
    rows = [
        payment("UNKNOWN", identificador_pagamento="EVENTO"),
        payment("A", identificador_pagamento="EVENTO"),
        payment("B", identificador_pagamento="EVENTO"),
    ]
    if field == "folha":
        for row, folha in zip(rows[1:], (left, right)):
            row.update(
                tipo_origem="FOLHA",
                competencia_pagamento="2020-01",
                rubrica_pagamento="12345",
                natureza_folha="NORMAL",
                natureza_rubrica="R",
                identificador_folha=folha,
                sequencia="0",
            )
    else:
        rows[1][field], rows[2][field] = left, right
    add_payment(data, *(rows[index] for index in order))
    assert_pending(data, "fonte_pagamento_exercicio_conflitante")


@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_complementary_source_metadata_is_preserved_without_increasing_payment(order):
    data = plan()
    rows = [
        payment("UNKNOWN", identificador_pagamento="EVENTO"),
        payment("J", identificador_pagamento="EVENTO", via_pagamento="JUDICIAL"),
        payment("P", identificador_pagamento="EVENTO", processo="PROCESSO-SINTETICO"),
    ]
    add_payment(data, *(rows[index] for index in order))
    result = calculate(data)
    assert result["totais"]["saldo"] == "750.00"
    sources = result["recebimentos_considerados"] + [
        row["dados_informados"] for row in result["duplicidades_recebimentos"]
    ]
    assert any(row["via_pagamento"] == "JUDICIAL" for row in sources)
    assert any(row["processo"] == "PROCESSO-SINTETICO" for row in sources)


@pytest.mark.parametrize("operation", ["LANCAMENTO", "COMPLEMENTO"])
def test_documentary_discount_is_not_a_positive_receipt(auth_client_user, operation):
    data = plan()
    original = payment("R", amount="200", natureza_rubrica="R")
    discount = payment("D", amount="50", natureza_rubrica="D", operacao=operation)
    if operation == "COMPLEMENTO":
        discount["complementa_id"] = "R"
    add_payment(data, original, discount)
    assert_pending(data, "natureza_recebimento_exercicio_pendente")
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "exercicio_anterior",
            "dados_extraidos": {"matricula": "999", "exercicios": data},
        },
    )
    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"][0]["type"]
        == "natureza_recebimento_exercicio_pendente"
    )


@pytest.mark.parametrize("nature", [None, "R"])
def test_documentary_receipt_with_unknown_or_credit_nature_remains_supported(nature):
    data = plan()
    add_payment(data, payment(natureza_rubrica=nature))
    assert calculate(data)["totais"]["saldo"] == "750.00"


def test_documentary_discount_requires_explicit_reversal_and_target():
    data = plan()
    add_payment(
        data,
        payment("R", amount="200"),
        payment(
            "E", amount="50", natureza_rubrica="D", operacao="ESTORNO", estorna_id="R"
        ),
    )
    result = calculate(data)
    assert result["totais"]["recebido"] == "150.00"
    assert result["totais"]["saldo"] == "850.00"


def adjustment(id="A", **kwargs):
    return {
        "id": id,
        "parcela_id": "P",
        "tipo": "DESCONTO",
        "efeito": "REDUCAO",
        "valor": "100",
        "regra": rule(),
        "memoria_calculo": "Desconto único sintético da parcela P",
        "fonte": "Fonte sintética",
        "localizador": "item 1",
        "conferido": True,
        **kwargs,
    }


@pytest.mark.parametrize("identity", [None, "EVENTO-1"])
def test_same_adjustment_with_different_row_id_counts_once_and_retains_sources(
    identity,
):
    data = plan()
    data["ajustes"] = [
        adjustment(identificador_evento=identity),
        adjustment("COPY", identificador_evento=identity),
    ]
    result = calculate(data)
    assert result["totais"]["saldo"] == "900.00"
    assert len(result["ajustes_considerados"]) == 1
    assert len(result["ajustes_declarados"]) == 2
    assert result["duplicidades_ajustes"][0]["id"] == "COPY"
    assert result["parcelas"][0]["ajustes_ids"] == ["A"]


@pytest.mark.parametrize("reverse", [False, True])
def test_adjustment_with_and_without_optional_event_id_is_not_counted_twice(reverse):
    data = plan()
    rows = [adjustment(), adjustment("COPY", identificador_evento="EVENTO-1")]
    data["ajustes"] = list(reversed(rows)) if reverse else rows
    assert calculate(data)["totais"]["saldo"] == "900.00"


@pytest.mark.parametrize("identity", [None, "EVENTO-1"])
def test_conflicting_adjustment_value_generates_pending(identity):
    data = plan()
    data["ajustes"] = [
        adjustment(identificador_evento=identity),
        adjustment("COPY", identificador_evento=identity, valor="200"),
    ]
    assert_pending(data, "ajuste_exercicio_conflitante")


def test_distinct_documented_adjustment_events_remain_separate():
    data = plan()
    data["ajustes"] = [
        adjustment(identificador_evento="EVENTO-1"),
        adjustment("OTHER", identificador_evento="EVENTO-2"),
    ]
    result = calculate(data)
    assert result["totais"]["saldo"] == "800.00"
    assert len(result["ajustes_considerados"]) == 2


def test_legacy_adjustments_from_distinct_source_items_remain_separate():
    data = plan()
    data["ajustes"] = [adjustment(), adjustment("OTHER", localizador="item 2")]
    assert calculate(data)["totais"]["saldo"] == "800.00"


def test_one_adjustment_event_in_distinct_documents_keeps_both_proofs():
    data = plan()
    data["ajustes"] = [
        adjustment(identificador_evento="EVENTO"),
        adjustment(
            "COPY",
            identificador_evento="EVENTO",
            fonte="Segunda fonte",
            localizador="página 2",
        ),
    ]
    result = calculate(data)
    assert result["totais"]["saldo"] == "900.00"
    assert (
        result["duplicidades_ajustes"][0]["dados_informados"]["fonte"]
        == "Segunda fonte"
    )


def test_unknown_or_unconfirmed_adjustment_copy_is_not_silently_dropped():
    data = plan()
    data["ajustes"] = [adjustment(), adjustment("COPY", valor=None)]
    assert_pending(data, "ajuste_exercicio_sem_regra")


@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_adjustment_with_ambiguous_source_stays_pending_in_every_order(order):
    data = plan()
    rows = [
        adjustment(),
        adjustment("FIRST", identificador_evento="EVENTO-1"),
        adjustment("SECOND", identificador_evento="EVENTO-2"),
    ]
    data["ajustes"] = [rows[index] for index in order]
    assert_pending(data, "ajuste_exercicio_ambiguo")


def test_api_duplicate_adjustment_keeps_one_balance_and_both_sources_in_pdf(
    auth_client_user,
):
    data = plan()
    data["ajustes"] = [
        adjustment(identificador_evento="EVENTO-1"),
        adjustment("COPY", identificador_evento="EVENTO-1", fonte="Outra fonte"),
    ]
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "exercicio_anterior",
            "dados_extraidos": {"matricula": "999", "exercicios": data},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["resultado_calculo"]
    assert result["totais"]["saldo"] == "900.00"
    assert len(result["ajustes_considerados"]) == 1
    assert (
        result["duplicidades_ajustes"][0]["dados_informados"]["fonte"] == "Outra fonte"
    )
    pdf = auth_client_user.post(
        "/api/exportar-pdf", json={"historico_id": response.json()["historico_id"]}
    )
    assert pdf.status_code == 200, pdf.text


def test_api_conflicting_third_payment_source_is_pending(auth_client_user):
    data = plan()
    add_payment(
        data,
        payment("UNKNOWN", identificador_pagamento="EVENTO"),
        payment("A", identificador_pagamento="EVENTO", via_pagamento="ADMINISTRATIVA"),
        payment("J", identificador_pagamento="EVENTO", via_pagamento="JUDICIAL"),
    )
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "exercicio_anterior",
            "dados_extraidos": {"matricula": "999", "exercicios": data},
        },
    )
    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"][0]["type"] == "fonte_pagamento_exercicio_conflitante"
    )
