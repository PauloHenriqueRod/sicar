"""Esperados independentes; nenhuma fonte real de RH é utilizada."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.referencias_salariais import ReferenciaSalarial
from app.models.tabelas_salariais import HistoricoCalculo
from app.schemas.progressao_eventos import PlanoProgressao
from app.schemas.referencias_salariais import ReferenciaEntrada
from app.services.apuracao_periodos import PendenciaApuracao
from app.services.progressao_eventos import calcular_progressao_eventos
from app.services.salary_references import salvar_referencia

RULE = {"identificador": "REGRA-SINTETICA", "versao": "1", "fonte": "Exemplo sintético conferido", "inicio_vigencia": "2020-01-01"}
TAE = {"carreira": "TAE", "vinculo": "EFETIVO", "jornada": "40H", "versao_carreira": "SINTETICA", "classificacao_tae": "E", "padrao_tae": 1}
DOCENTE = {"carreira": "MAGISTERIO_SUPERIOR", "vinculo": "EFETIVO", "jornada": "40H", "versao_carreira": "SINTETICA", "classe_docente": "Adjunto", "nivel_docente": 1}


def position(modality, level=1):
    return {**(TAE if modality == "TAE" else DOCENTE), "padrao_tae" if modality == "TAE" else "nivel_docente": level}


def rubric(code, formula):
    return {"rubrica": code, "natureza_folha": "NORMAL", "natureza_rubrica": "R", "formula": formula, "regra": RULE}


def event(kind, effective, **changes):
    return {"id": kind, "tipo": kind, "efeitos_financeiros": effective, "regra": RULE, "alteracoes": changes}


def plan(modality="TAE"):
    tae = modality == "TAE"
    return {
        "modalidade": modality,
        "periodo": {"inicio": "2024-02-01", "ultimo_dia_considerado": "2024-02-29"},
        "estado_inicial": {"posicao": position(modality), "titulacao": "Graduação" if tae else "Mestrado", "percentual_adicional": "0", "percentual_anuenio": "0", **({"percentual_iq": "10"} if tae else {})},
        "eventos": [event("PROGRESSAO", "2024-02-15", posicao=position(modality, 2)), event("IQ" if tae else "RT", "2024-02-20", **({"percentual_iq": "20", "titulacao": "Especialização"} if tae else {"titulacao": "Doutorado"}))],
        "rubricas": [rubric("1", "VB"), rubric("2", "IQ_SOBRE_VB" if tae else "RT")],
        "recebidos": [], "conferido_pelo_rh": True,
    }


def seed(db, modality="TAE", old="2900", new="5800", start="2020-01-01"):
    for level, amount in ((1, old), (2, new)):
        data = {**position(modality, level), "inicio_vigencia": start, "vencimento_basico": amount, "fonte": "Tabela sintética confirmada", "estado": "CONFIRMADA"}
        if modality != "TAE":
            data["retribuicoes"] = [{"titulacao": "Mestrado", "valor": "580" if level == 1 else "1160"}, {"titulacao": "Doutorado", "valor": "870" if level == 1 else "1740"}]
        salvar_referencia(db, ReferenciaEntrada.model_validate(data), 1)


def calculate(data, db):
    return calcular_progressao_eventos(PlanoProgressao.model_validate(data), db)


def test_opcoes_docentes_respeitam_vigencia_e_perfil(auth_client_user, db_session):
    seed(db_session, "DOCENTE")
    primeiro, segundo = db_session.query(ReferenciaSalarial).order_by(ReferenciaSalarial.id).all()
    primeiro.fim_vigencia = date(2024, 2, 29)
    segundo.estado = "PENDENTE"
    db_session.flush()
    seed(db_session, "TAE")
    url = "/api/tabelas/posicoes-docentes"
    response = auth_client_user.get(url, params={"data_referencia": "2024-02-29"})
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 2
    assert {r["titulacao"] for r in result["itens"]} == {"Mestrado", "Doutorado"}
    assert all(r["posicao"] == DOCENTE for r in result["itens"])
    assert all(r["fonte"] == "Tabela sintética confirmada" and r["vb"] == "2900.00" for r in result["itens"])
    assert {r["titulacao"]: r["rt"] for r in result["itens"]} == {"Mestrado": "580.00", "Doutorado": "870.00"}
    filtros = {"data_referencia": "2024-02-29", "carreira": DOCENTE["carreira"],
               "classe_docente": "Adjunto", "nivel_docente": 1, "jornada": "40H", "vencimento_basico": "2900.00"}
    assert auth_client_user.get(url, params=filtros).json()["itens"] == result["itens"]
    for chave, outro in (("nivel_docente", 2), ("jornada", "DE"), ("vencimento_basico", "2900.01")):
        assert auth_client_user.get(url, params={**filtros, chave: outro}).json()["total"] == 0
    assert auth_client_user.get(url, params={"data_referencia": "2024-03-01"}).json()["itens"] == []
    assert auth_client_user.get(url, params={"data_referencia": "2024-02-29", "pagina": 2}).json()["itens"] == []
    assert auth_client_user.get("/api/tabelas/referencias").status_code == 403


def correction(amount):
    return {"valor": amount, "fonte": "Memória sintética conferida", "localizador": "linha 1", "justificativa": "Base individual conferida pelo RH"}


@pytest.mark.parametrize("classe,nova_classe,destino_jan,total", [
    ("A", "A", 1, "250.00"),
    ("C", "B", 2, "850.00"),
])
def test_correlacao_docente_dezembro_janeiro(db_session, classe, nova_classe, destino_jan, total):
    data = plan("DOCENTE")
    data["periodo"] = {"inicio": "2024-12-01", "ultimo_dia_considerado": "2025-01-31"}
    data["eventos"] = [event("PROGRESSAO", "2024-12-01", posicao=position("DOCENTE", 2))]
    for pos in (data["estado_inicial"]["posicao"], data["eventos"][0]["alteracoes"]["posicao"]):
        pos.update(versao_carreira="MS até 2024", classe_docente=classe)
    for versao, cl, nivel, inicio, fim, vb, rt in [
        ("MS até 2024", classe, 1, "2024-01-01", "2024-12-31", "4000", "1000"),
        ("MS até 2024", classe, 2, "2024-01-01", "2024-12-31", "4200", "1050"),
        ("MS desde 2025", nova_classe, 1, "2025-01-01", None, "5000", "1200"),
        ("MS desde 2025", "B", 2, "2025-01-01", None, "5500", "1300"),
    ]:
        ref = {**position("DOCENTE", nivel), "versao_carreira": versao, "classe_docente": cl,
               "inicio_vigencia": inicio, "fim_vigencia": fim, "vencimento_basico": vb, "estado": "CONFIRMADA",
               "retribuicoes": [{"titulacao": "Mestrado", "valor": rt}], "fonte": "Tabela sintética"}
        salvar_referencia(db_session, ReferenciaEntrada.model_validate(ref), 1)
    result = calculate(data, db_session)
    dez, jan = result["segmentos"]
    assert dez["estado"]["posicao"]["nivel_docente"] == 2
    assert jan["estado"]["posicao"]["classe_docente"] == nova_classe
    assert jan["estado"]["posicao"]["nivel_docente"] == destino_jan
    assert sum(r["identificador"] == "CORRELACAO-MS-2025" for r in jan["referencias_regras"]) == 1
    assert result["total_geral_a_receber"] == total
    # A base individual de dezembro termina com o enquadramento antigo.
    data["estado_inicial"]["vb_manual"] = correction("3900")
    assert calculate(data, db_session)["total_geral_a_receber"] == format(Decimal(total) + 100, ".2f")
    # Uma base conferida especificamente para janeiro continua válida na nova estrutura.
    data["estado_inicial"].pop("vb_manual")
    data["bases_mensais_origem"] = [{"id": mes, "competencia": mes, "vb": correction(valor),
                                     "base_mensal_integral_confirmada": True}
                                    for mes, valor in (("2024-12", "4000"), ("2025-01", "4800"))]
    assert calculate(data, db_session)["total_geral_a_receber"] == format(Decimal(total) + 200, ".2f")
    data["bases_mensais_origem"][1]["rt"] = correction("900")
    assert calculate(data, db_session)["total_geral_a_receber"] == format(Decimal(total) + 500, ".2f")
    db_session.query(ReferenciaSalarial).filter_by(inicio_vigencia=date(2025, 1, 1)).update({"estado": "PENDENTE"})
    db_session.flush()
    with pytest.raises(PendenciaApuracao, match="0 referências confirmadas.*MS desde 2025"):
        calculate(data, db_session)


def test_individual_vb_rt_corrections_keep_original_table_and_use_final_values(db_session):
    seed(db_session, "DOCENTE")
    data = plan("DOCENTE")
    data["estado_inicial"].update(vb_manual=correction("3000"), rt_manual=correction("600"))
    result = calculate(data, db_session)
    # VB: 2800*15/29; RT: 560*5/29 + 1140*10/29 = 56200/29.
    assert result["total_geral_a_receber"] == "1937.93"
    sources = [s for segment in result["segmentos"] for s in segment["referencias_tabelas"]]
    assert any(s.get("valor_sugerido") == "2900" and s["valor"] == "3000" for s in sources)
    assert any(s.get("valor_sugerido") == "580" and s["valor"] == "600" for s in sources)
    # A separate calculation still obtains the unchanged confirmed references.
    assert calculate(plan("DOCENTE"), db_session)["total_geral_a_receber"] == "2000.00"


@pytest.mark.parametrize("restore,expected", [(False, "2110.34"), (True, "2075.86")])
def test_base_event_is_independent_and_can_return_to_confirmed_table(db_session, restore, expected):
    seed(db_session, "DOCENTE")
    data = plan("DOCENTE")
    data["eventos"].append(event("BASE", "2024-02-15", vb_manual=correction("6000"), rt_manual=correction("1200")))
    if restore:
        data["eventos"].append({**event("BASE", "2024-02-25", vb_manual=None, rt_manual=None), "id": "RETORNO"})
    assert calculate(data, db_session)["total_geral_a_receber"] == expected


@pytest.mark.parametrize("missing", ["posicao", "titulacao"])
def test_manual_corrections_cannot_bypass_reference_or_rt_validation(db_session, missing):
    seed(db_session, "DOCENTE")
    data = plan("DOCENTE")
    data["estado_inicial"].update(vb_manual=correction("3000"), rt_manual=correction("600"))
    if missing == "posicao":
        data["estado_inicial"]["posicao"]["nivel_docente"] = 3
    else:
        data["estado_inicial"]["titulacao"] = "TITULAÇÃO SEM REFERÊNCIA"
    with pytest.raises(PendenciaApuracao):
        calculate(data, db_session)


@pytest.mark.parametrize("modality,expected,component", [("TAE", "1850.00", "350.00"), ("DOCENTE", "2000.00", "500.00")])
def test_independent_dates_have_own_segments_without_double_counting(db_session, modality, expected, component):
    seed(db_session, modality)
    result = calculate(plan(modality), db_session)
    assert result["total_geral_a_receber"] == expected
    assert [item["dias_computados"] for item in result["segmentos"]] == [14, 5, 10]
    assert sum(item["dias_computados"] for item in result["segmentos"]) == 29
    assert [item["devido"] for item in result["por_competencia"]] == ["1500.00", component]
    assert all({source["papel"] for source in item["referencias_tabelas"]} == {"ORIGEM", "DESTINO"} for item in result["segmentos"])


def test_iq_can_start_before_progression(db_session):
    seed(db_session)
    data = plan()
    data["eventos"][1]["efeitos_financeiros"] = "2024-02-11"
    result = calculate(data, db_session)
    assert result["total_geral_a_receber"] == "1990.00"  # VB:1500; IQ:40+450.


@pytest.mark.parametrize("modality,expected", [("TAE", "1950.00"), ("DOCENTE", "2100.00")])
def test_same_day_progression_and_qualification_are_applied_once(db_session, modality, expected):
    seed(db_session, modality)
    data = plan(modality)
    data["eventos"][1]["efeitos_financeiros"] = "2024-02-15"
    first = calculate(data, db_session)
    data["eventos"].reverse()
    second = calculate(data, db_session)
    assert first["total_geral_a_receber"] == second["total_geral_a_receber"] == expected
    assert [item["dias_computados"] for item in first["segmentos"]] == [14, 15]


def test_historical_salary_changes_update_both_sides_of_the_comparison(db_session):
    for level, amount in ((1, "2900"), (2, "5800")):
        for start, end, salary in (("2024-02-01", "2024-02-14", amount), ("2024-02-15", None, str(int(amount) * 2))):
            salvar_referencia(db_session, ReferenciaEntrada.model_validate({
                **position("TAE", level), "inicio_vigencia": start, "fim_vigencia": end,
                "vencimento_basico": salary, "fonte": "Tabela histórica sintética", "estado": "CONFIRMADA",
            }), 1)
    result = calculate(plan(), db_session)
    assert result["total_geral_a_receber"] == "3700.00"  # VB 3000 + IQ (100 + 600).
    assert len({source["referencia_id"] for segment in result["segmentos"] for source in segment["referencias_tabelas"]}) == 3


def test_workload_is_an_independent_event_with_its_own_reference(db_session):
    seed(db_session, "DOCENTE")
    salvar_referencia(db_session, ReferenciaEntrada.model_validate({
        **position("DOCENTE", 2), "jornada": "DE", "inicio_vigencia": "2020-01-01",
        "vencimento_basico": "8700", "retribuicoes": [{"titulacao": "Doutorado", "valor": "2610"}],
        "fonte": "Tabela DE sintética", "estado": "CONFIRMADA",
    }), 1)
    data = plan("DOCENTE")
    data["eventos"].append(event("JORNADA", "2024-02-25", posicao={**position("DOCENTE", 2), "jornada": "DE"}))
    result = calculate(data, db_session)
    assert result["total_geral_a_receber"] == "2650.00"  # 2000 + (2900+870)*5/29.
    assert [item["dias_computados"] for item in result["segmentos"]] == [14, 5, 5, 5]


def test_progression_accumulates_before_rounding(db_session):
    seed(db_session, old="1", new="1.01")
    data = plan()
    data["periodo"] = {"inicio": "2023-02-15", "ultimo_dia_considerado": "2023-02-28"}
    data["estado_inicial"]["percentual_iq"] = "100"
    data["eventos"] = [event("PROGRESSAO", "2023-02-15", posicao=position("TAE", 2))]
    result = calculate(data, db_session)
    assert [item["devido"] for item in result["por_competencia"]] == ["0.01", "0.01"]
    assert result["total_geral_a_receber"] == "0.01"  # .01*14/28 + .01*14/28.


def test_month_labels_do_not_create_reflexes(db_session):
    seed(db_session)
    first = plan()
    second = deepcopy(first)
    first["eventos"][0]["id"] = "Dezembro"
    second["eventos"][0]["id"] = "dezembro (retificação)"
    a, b = calculate(first, db_session), calculate(second, db_session)
    assert a["totais"] == b["totais"]
    assert a["reflexos"] == b["reflexos"] == []


def test_reflexes_use_explicit_date_components_and_avos(db_session):
    seed(db_session, "DOCENTE")
    data = plan("DOCENTE")
    common = {"data_base": "2024-02-29", "competencia": "2024-02", "formulas_base": ["VB", "RT"], "regra": RULE, "natureza_folha": "NORMAL", "natureza_rubrica": "R"}
    data["reflexos"] = [
        {**common, "id": "F1", "tipo": "FERIAS_UM_TERCO", "avos": 12, "rubrica": "750"},
        {**common, "id": "D1", "tipo": "DECIMO_TERCEIRO", "avos": 6, "rubrica": "13"},
    ]
    result = calculate(data, db_session)
    assert [item["devido"] for item in result["reflexos"]] == ["1353.33", "2030.00"]
    assert result["total_geral_a_receber"] == "5383.33"  # 2000 + 4060/3 + 4060*6/12.


@pytest.mark.parametrize("reverse", [False, True])
def test_disjoint_reflex_components_allow_distinct_avos(db_session, reverse):
    seed(db_session, "DOCENTE")
    data = plan("DOCENTE")
    common = {"tipo": "DECIMO_TERCEIRO", "data_base": "2024-02-29", "competencia": "2024-02", "rubrica": "13", "natureza_folha": "NORMAL", "natureza_rubrica": "R", "regra": RULE}
    data["reflexos"] = [
        {**common, "id": "DECIMO-VB", "avos": 12, "formulas_base": ["VB"]},
        {**common, "id": "DECIMO-RT", "avos": 6, "formulas_base": ["RT"]},
    ]
    if reverse:
        data["reflexos"].reverse()
    result = calculate(data, db_session)
    assert {row["id"]: row["devido"] for row in result["reflexos"]} == {"DECIMO-VB": "2900.00", "DECIMO-RT": "580.00"}
    assert next(row["devido"] for row in result["por_competencia"] if row["rubrica"] == "00013") == "3480.00"
    assert result["total_geral_a_receber"] == "5480.00"  # Principal 2000 + 2900*12/12 + 1160*6/12.


@pytest.mark.parametrize("first,second", [(["VB"], ["VB"]), (["VB", "RT"], ["RT"]), (["VB", "RT"], ["RT", "VB"])])
def test_overlapping_reflex_components_remain_invalid(first, second):
    data = plan("DOCENTE")
    common = {"tipo": "DECIMO_TERCEIRO", "data_base": "2024-02-29", "competencia": "2024-02", "rubrica": "13", "natureza_folha": "NORMAL", "natureza_rubrica": "R", "regra": RULE}
    data["reflexos"] = [{**common, "id": "R1", "avos": 12, "formulas_base": first}, {**common, "id": "R2", "avos": 6, "formulas_base": second}]
    with pytest.raises(ValidationError, match="componentes sobrepostos"):
        PlanoProgressao.model_validate(data)


def test_duplicate_reflex_ids_are_invalid_even_with_disjoint_components():
    data = plan("DOCENTE")
    common = {"id": "REPETIDO", "tipo": "DECIMO_TERCEIRO", "data_base": "2024-02-29", "competencia": "2024-02", "rubrica": "13", "natureza_folha": "NORMAL", "natureza_rubrica": "R", "regra": RULE}
    data["reflexos"] = [{**common, "avos": 12, "formulas_base": ["VB"]}, {**common, "avos": 6, "formulas_base": ["RT"]}]
    with pytest.raises(ValidationError, match="identificadores repetidos"):
        PlanoProgressao.model_validate(data)


def test_historical_interruptions_exclude_overlapping_days_once(db_session):
    seed(db_session)
    data = plan()
    data["interrupcoes"] = [
        {"id": "I1", "inicio": "2024-02-21", "ultimo_dia_considerado": "2024-02-22", "regra": {**RULE, "inicio_vigencia": "2024-02-21", "fim_vigencia": "2024-02-22"}},
        {"id": "I2", "inicio": "2024-02-22", "ultimo_dia_considerado": "2024-02-23", "regra": RULE},
    ]
    result = calculate(data, db_session)
    assert sum(row["dias_computados"] for row in result["segmentos"]) == 26
    assert result["total_geral_a_receber"] == "1460.00"  # 1850 - (3770/29)*3.
    excluded = next(row for row in result["segmentos"] if row["inicio"] == "2024-02-21")
    assert excluded["referencias_regras"][-1]["fim_vigencia"] == "2024-02-22"


@pytest.mark.parametrize("rule", [{**RULE, "inicio_vigencia": "2024-02-22"}, {**RULE, "fim_vigencia": "2024-02-21"}])
def test_interruption_must_be_fully_covered_by_its_rule(rule):
    data = plan()
    data["interrupcoes"] = [{"id": "I1", "inicio": "2024-02-21", "ultimo_dia_considerado": "2024-02-22", "regra": rule}]
    with pytest.raises(ValidationError, match="todos os dias da interrupção"):
        PlanoProgressao.model_validate(data)


def test_http_accepts_ui_interruption_rule_and_exposes_its_contract(auth_client_user, db_session):
    seed(db_session)
    data = plan()
    data["interrupcoes"] = [{"id": "I1", "inicio": "2024-02-21", "ultimo_dia_considerado": "2024-02-22", "regra": {**RULE, "fim_vigencia": "2024-02-22"}}]
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": {"progressao": data}})
    assert response.status_code == 200, response.text
    assert response.json()["resultado_calculo"]["total_geral_a_receber"] == "1590.00"
    assert db_session.query(HistoricoCalculo).count() == 1
    schema = auth_client_user.get("/api/calculos/contratos/progressao").json()
    assert schema["$defs"]["InterrupcaoProgressao"]["properties"]["regra"]["$ref"].endswith("/RegraHistorica")


def test_reference_example_is_recalculated_without_intermediate_rounding(db_session):
    seed(db_session, old="3686.33", new="3833.79")
    data = plan()
    data["periodo"] = {"inicio": "2026-01-18", "ultimo_dia_considerado": "2026-01-31"}
    data["estado_inicial"]["percentual_iq"] = "30"
    data["eventos"] = [event("PROGRESSAO", "2026-01-18", posicao=position("TAE", 2))]
    common = {"data_base": "2026-01-31", "competencia": "2026-01", "avos": 12, "formulas_base": ["VB", "IQ_SOBRE_VB"], "regra": RULE, "natureza_folha": "NORMAL", "natureza_rubrica": "R"}
    data["reflexos"] = [{**common, "id": "F", "rubrica": "750", "tipo": "FERIAS_UM_TERCO"}, {**common, "id": "D", "rubrica": "13", "tipo": "DECIMO_TERCEIRO"}]
    result = calculate(data, db_session)
    assert [row["devido"] for row in result["reflexos"]] == ["63.90", "191.70"]
    assert [row["devido"] for row in result["por_competencia"][:2]] == ["66.59", "19.98"]
    # (147.46 + 44.238) * (14/31 + 1/3 + 1), sem somar os valores apresentados.
    assert result["total_geral_a_receber"] == "342.17"


def test_received_differences_are_deduplicated_and_complements_count_once(db_session):
    seed(db_session)
    data = plan()
    payment = {"id": "P1", "competencia": "2024-02", "rubrica": "1", "natureza_folha": "NORMAL", "natureza_rubrica": "R", "identificador_folha": "FOLHA", "sequencia": "1", "operacao": "PAGAMENTO", "valor": "100", "origem": "Ficha sintética"}
    data["recebidos"] = [payment, {**payment, "id": "P2", "origem": "Segunda via"}, {**payment, "id": "C", "sequencia": "2", "operacao": "COMPLEMENTO", "valor": "50"}]
    result = calculate(data, db_session)
    assert result["totais"]["recebido"] == "150.00"
    assert result["total_geral_a_receber"] == "1700.00"
    assert len(result["duplicidades"]) == 1


def test_progression_pdf_retains_the_period_sources_and_final_amount(db_session, tmp_path):
    import pdfplumber

    from app.services.gerador_pdf import GeradorPDF

    seed(db_session)
    data = PlanoProgressao.model_validate(plan())
    result = calcular_progressao_eventos(data, db_session)
    filename = str(tmp_path / "progressao-sintetica.pdf")
    GeradorPDF.gerar_relatorio("progressao", {"matricula": "DEMO-1", "progressao": data.model_dump(mode="json")}, result, output_path=filename)
    with pdfplumber.open(filename) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "R$ 1850.00" in text
    assert "2024-02-15" in text and "2024-02-20" in text
    assert "REGRA-SINTETICA" in text


def test_exporta_progressao_plurianual_salva_com_ficha_extensa(auth_client_user, db_session):
    from io import BytesIO

    import pdfplumber

    seed(db_session, "DOCENTE")
    data = plan("DOCENTE")
    data["periodo"]["ultimo_dia_considerado"] = "2026-01-31"
    campo = {"bloco_id": "B", "estado": "EXTRAIDO", "pagina": 1, "localizador": "Página 1"}
    campos = [{**campo, "id": "M", "campo": "matricula", "valor": "123"}]
    campos.extend({**campo, "id": f"F{i}", "campo": "observacao", "valor": "Exemplo sem uso no cálculo"}
                  for i in range(700))
    revisao = {"confirmado": True, "vinculo_calculo": "V1",
               "documentos": [{"id": "D", "nome_arquivo": "ficha-sintetica.pdf", "layout": "FICHA_SIAPE",
                               "situacao": "CONCLUIDO", "total_paginas": 1, "campos": campos,
                               "blocos": [{"id": "B", "matricula": "123", "vinculo": "V1", "categoria": "DOCENTE", "paginas": [1]}]}],
               "associacoes": [{"documento_id": "D", "bloco_id": "B", "pessoa": "SERVIDOR",
                                "matricula": "123", "vinculo": "V1", "confirmado": True}],
               "aplicacoes": [{"documento_id": "D", "campo_id": "M", "destino": ["matricula"], "valor_revisado": "123"}]}
    saved = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": {
        "matricula": "123", "progressao": data, "revisao_extracao": revisao,
    }})
    assert saved.status_code == 200, saved.text
    snapshot = saved.json()
    pdf = auth_client_user.post("/api/exportar-pdf", json={"historico_id": snapshot["historico_id"]})
    assert pdf.status_code == 200, pdf.text if pdf.status_code != 200 else ""
    with pdfplumber.open(BytesIO(pdf.content)) as arquivo:
        texto = "\n".join(p.extract_text() for p in arquivo.pages)
    for esperado in ("2024-02", "2026-01", "ficha-sintetica.pdf", "REGRA-SINTETICA",
                     snapshot["resultado_calculo"]["total_geral_a_receber"]):
        assert esperado in texto
    assert "Exemplo sem uso" not in texto


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(modalidade="DOCENTE"),
    lambda data: data["eventos"][1].update(tipo="RT"),
    lambda data: data["eventos"][0].update(regra={**RULE, "fim_vigencia": "2024-02-14"}),
    lambda data: data["eventos"][0]["alteracoes"]["posicao"].update(vinculo="OUTRO"),
    lambda data: data["rubricas"].append(rubric("99", "VB")),
    lambda data: data["estado_inicial"].update(vb_manual={"valor": "1", "fonte": "Não confirmada", "localizador": "Linha 1"}),
    lambda data: data["eventos"][0]["alteracoes"].update(percentual_iq="30"),
])
def test_ambiguous_modalities_rules_and_combined_events_are_rejected(mutation):
    data = plan()
    mutation(data)
    with pytest.raises(ValidationError):
        PlanoProgressao.model_validate(data)


@pytest.mark.parametrize("missing", ["origem", "destino", "jornada", "titulacao"])
def test_missing_reference_never_presumes_salary(db_session, missing):
    seed(db_session, "DOCENTE")
    data = plan("DOCENTE")
    if missing == "origem":
        data["estado_inicial"]["posicao"]["nivel_docente"] = 3
    elif missing == "destino":
        data["eventos"][0]["alteracoes"]["posicao"]["nivel_docente"] = 3
    elif missing == "jornada":
        data["eventos"][0]["alteracoes"]["posicao"]["jornada"] = "DE"
    else:
        data["eventos"][1]["alteracoes"]["titulacao"] = "Especialização"
    with pytest.raises(PendenciaApuracao):
        calculate(data, db_session)


def test_http_history_idempotency_and_contract(auth_client_user, db_session):
    seed(db_session)
    data = plan()
    payload = {"tipo_calculo": "progressao", "dados_extraidos": {"matricula": "DEMO-1", "progressao": data}, "idempotency_key": str(uuid4())}
    first = auth_client_user.post("/api/calcular", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["resultado_calculo"]["total_geral_a_receber"] == "1850.00"
    data["eventos"][1]["alteracoes"]["percentual_iq"] = "20.00"
    assert auth_client_user.post("/api/calcular", json=payload).json() == first.json()
    assert db_session.query(HistoricoCalculo).one().classe == "Técnico Administrativo"
    schema = auth_client_user.get("/api/calculos/contratos/progressao").json()
    assert "PlanoProgressao" in schema["$defs"]
    data["eventos"][1]["efeitos_financeiros"] = "2024-02-21"
    assert auth_client_user.post("/api/calcular", json=payload).status_code == 409


def test_pending_reference_does_not_save_history(auth_client_user, db_session):
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": {"progressao": plan()}})
    assert response.status_code == 400
    assert response.json()["detail"][0]["loc"] == ["dados_extraidos", "progressao"]
    assert db_session.query(HistoricoCalculo).count() == 0


def monthly_docente_plan():
    data = plan("DOCENTE")
    data["periodo"] = {"inicio": "2024-02-15", "ultimo_dia_considerado": "2024-03-31"}
    data["eventos"] = [event("PROGRESSAO", "2024-02-15", posicao=position("DOCENTE", 2))]
    data["bases_mensais_origem"] = [
        {"id": "base-fev", "competencia": "2024-02", "vb": correction("3000"), "base_mensal_integral_confirmada": True},
        {"id": "base-mar", "competencia": "2024-03", "vb": correction("3500"), "base_mensal_integral_confirmada": True},
    ]
    return data


def test_monthly_vb_compares_each_source_month_with_destination_and_final_rounding(db_session):
    seed(db_session, "DOCENTE")
    data = monthly_docente_plan()
    result = calculate(data, db_session)
    # VB: (5800-3000)*15/29 + (5800-3500) = 3748.275862...
    # RT remains separately referenced: (1160-580)*15/29 + 580 = 880.
    assert result["total_geral_a_receber"] == "4628.28"
    vb = [row for row in result["por_competencia"] if row["rubrica"] == "00001"]
    assert [(row["competencia"], row["devido"]) for row in vb] == [("2024-02", "1448.28"), ("2024-03", "2300.00")]
    assert result["bases_mensais_origem"][1]["vb"]["valor"] == "3500"
    assert any(source.get("papel") == "ORIGEM" and source.get("valor") == "3500" for segment in result["segmentos"] for source in segment["referencias_tabelas"])
    data["bases_mensais_origem"][1]["vb"]["valor"] = "5800"
    assert next(row for row in calculate(data, db_session)["por_competencia"] if row["rubrica"] == "00001" and row["competencia"] == "2024-03")["devido"] == "0.00"


def test_monthly_vb_missing_month_stays_pending(db_session):
    seed(db_session, "DOCENTE")
    data = monthly_docente_plan()
    data["bases_mensais_origem"].pop()
    with pytest.raises(PendenciaApuracao, match="2024-03"):
        calculate(data, db_session)


@pytest.mark.parametrize("case", ["duplicate", "unconfirmed", "before_effect", "no_justification"])
def test_monthly_vb_rejects_incomplete_or_conflicting_review(case):
    data = monthly_docente_plan()
    if case == "duplicate":
        data["bases_mensais_origem"].append(deepcopy(data["bases_mensais_origem"][0]))
    elif case == "unconfirmed":
        data["bases_mensais_origem"][0]["base_mensal_integral_confirmada"] = False
    elif case == "before_effect":
        data["periodo"]["inicio"] = "2024-02-01"
    else:
        data["bases_mensais_origem"][0]["vb"]["justificativa"] = ""
    with pytest.raises(ValidationError):
        PlanoProgressao.model_validate(data)


def test_paid_current_vb_does_not_imply_payment_of_thirteenth_difference(db_session):
    seed(db_session, "DOCENTE")
    data = monthly_docente_plan()
    data["bases_mensais_origem"][1]["vb"]["valor"] = "5800"
    data["reflexos"] = [{"id": "13", "tipo": "DECIMO_TERCEIRO", "data_base": "2024-03-31", "competencia": "2024-03", "avos": 12, "rubrica": "13", "natureza_folha": "DECIMO", "natureza_rubrica": "R", "formulas_base": ["VB"], "regra": RULE}]
    result = calculate(data, db_session)
    assert result["reflexos"][0]["devido"] == "2900.00"
    assert any(source.get("papel") == "ORIGEM_REFLEXO" for source in result["reflexos"][0]["referencias_tabelas"])


def test_http_preserves_monthly_values_and_sources_in_saved_result(auth_client_user, db_session):
    seed(db_session, "DOCENTE")
    data = monthly_docente_plan()
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": {"progressao": data}})
    assert response.status_code == 200, response.text
    assert response.json()["resultado_calculo"]["total_geral_a_receber"] == "4628.28"
    assert response.json()["resultado_calculo"]["bases_mensais_origem"][0]["vb"]["valor"] == "3000"
    assert db_session.query(HistoricoCalculo).count() == 1
    schema = auth_client_user.get("/api/calculos/contratos/progressao").json()
    assert "bases_mensais_origem" in schema["$defs"]["PlanoProgressao"]["properties"]


def test_monthly_confirmed_zero_is_not_replaced_by_table(db_session):
    seed(db_session, "DOCENTE")
    data = monthly_docente_plan()
    data["bases_mensais_origem"][0]["vb"]["valor"] = "0"
    result = calculate(data, db_session)
    assert next(row for row in result["por_competencia"] if row["rubrica"] == "00001" and row["competencia"] == "2024-02")["devido"] == "3000.00"


def test_progressao_docente_componentes_internos_preservam_valores_e_memoria(auth_client_user, db_session):
    seed(db_session, "DOCENTE")
    data = monthly_docente_plan()
    for item in data["bases_mensais_origem"]:
        item["rt"] = correction("580")
    for row in data["rubricas"]:
        row["rubrica"] = {"VB": "DIF-VB", "RT": "DIF-RT"}[row["formula"]]
    response = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": {"progressao": data}})
    assert response.status_code == 200, response.text
    result = response.json()["resultado_calculo"]
    assert result["total_geral_a_receber"] == "4628.28"
    assert {row["rubrica"] for row in result["por_competencia"]} == {"DIF-VB", "DIF-RT"}
    data["rubricas"][0]["rubrica"] = "DIF-RT"
    with pytest.raises(ValidationError, match="fórmula correspondente"):
        PlanoProgressao.model_validate(data)


def test_previa_e_memoria_comparam_folha_real_de_cada_mes(auth_client_user, db_session):
    seed(db_session, "DOCENTE")
    data = monthly_docente_plan()
    data["periodo"]["ultimo_dia_considerado"] = "2024-04-30"
    data["bases_mensais_origem"].append({"id": "abril", "competencia": "2024-04", "vb": correction("5800"),
                                         "base_mensal_integral_confirmada": True})
    for item, rt in zip(data["bases_mensais_origem"], ["580", "800", "1160"], strict=True):
        item["rt"] = correction(rt)
    for row in data["rubricas"]:
        row["rubrica"] = "DIF-" + row["formula"]
    response = auth_client_user.post("/api/calculos/progressao/previa-folha", json=data)
    assert response.status_code == 200, response.text
    linhas = response.json()["parcelas"]
    assert [(r["componente"], r["diferenca"]) for r in linhas] == [
        ("VB", "1448.28"), ("RT", "300.00"), ("VB", "2300.00"), ("RT", "360.00"), ("VB", "0.00"), ("RT", "0.00")]
    assert linhas[3]["pago"] == "800.00" and linhas[3]["destino"] == "1160.00"
    assert linhas[3]["fonte"] == "Tabela sintética confirmada"
    assert db_session.query(HistoricoCalculo).count() == 0
    assert calculate(data, db_session)["total_geral_a_receber"] == "4408.28"
    data["bases_mensais_origem"][1]["rt"] = correction("580")
    assert calculate(data, db_session)["total_geral_a_receber"] == "4628.28"
    saved = auth_client_user.post("/api/calcular", json={"tipo_calculo": "progressao", "dados_extraidos": {"progressao": data}})
    assert saved.status_code == 200, saved.text
    exported = auth_client_user.post("/api/exportar-pdf", json={"historico_id": saved.json()["historico_id"]})
    assert exported.status_code == 200
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(exported.content)) as pdf:
        text = " ".join(page.extract_text() or "" for page in pdf.pages)
    assert "4628.28" in text and "destino mensal" in text and "pago mensal" in text
    data["bases_mensais_origem"][1]["rt"] = correction("0")
    assert calculate(data, db_session)["total_geral_a_receber"] == "5208.28"
    del data["bases_mensais_origem"][1]["rt"]
    with pytest.raises(PendenciaApuracao, match="RT paga em 2024-03"):
        calculate(data, db_session)
    data["bases_mensais_origem"] = []
    with pytest.raises(PendenciaApuracao, match="cada competência"):
        calculate(data, db_session)


def test_sqlite_preserva_centavos_e_rejeita_fracao_indistinguivel(db_session):
    from decimal import Decimal

    entry = ReferenciaEntrada.model_validate({
        **DOCENTE, "inicio_vigencia": "2026-04-01", "vencimento_basico": "12245.03",
        "retribuicoes": [{"titulacao": "Exemplo", "valor": "10568.54"}],
        "fonte": "Teste de representação decimal", "estado": "CONFIRMADA",
    })
    ref = salvar_referencia(db_session, entry, 1)
    db_session.expire_all()
    assert ref.vencimento_basico == Decimal("12245.03")
    assert ref.retribuicoes[0].valor == Decimal("10568.54")
    other = entry.model_copy(update={"nivel_docente": 2, "vencimento_basico": Decimal("12245.030000000001")})
    with pytest.raises(ValueError, match="precisão do VB"):
        salvar_referencia(db_session, other, 1)
