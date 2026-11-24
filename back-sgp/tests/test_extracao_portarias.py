"""Regressões com nomes, matrículas, datas e concessões inteiramente sintéticos."""

from types import SimpleNamespace

import pytest
from fpdf import FPDF

from app.schemas.extracao_documentos import RevisaoExtracao
from app.services.extracao_documentos import extrair_documento
from app.services.extracao_portarias import linhas_anexo_tae
from app.services.pendencias import PendenciaApuracao
from app.services.revisao_extracao import validar_revisao_extracao

HEADER = """MINISTÉRIO DA EDUCAÇÃO
UNIVERSIDADE FEDERAL DO PIAUÍ
PORTARIA Nº 900 / 2026 - SRH (11.04)
Teresina-PI, 20 de Fevereiro de 2026
A autoridade foi nomeada em 01/01/2020, publicado no DOU de 02/01/2020.
RESOLVE:
"""
PROGRESSION = """1. Autorizar a progressão funcional, por desempenho acadêmico, ao (à) Professor (a) MS -
C - Denominação Adjunto - 01 - DE - ALFA DOCENTE SINTÉTICO
lotado (a) no (a) para MS - C - Denominação Adjunto - 02, a partir de 05.02.2026.
2. De acordo com norma geral, em 01/01/2000.
(Assinado digitalmente em 21/02/2026 08:00)
EMISSOR SINTÉTICO
Matrícula: 7777777
"""
TITLING = """Conceder incentivo funcional correspondente ao nível de Doutorado ao (à) Professor (a) MS- C - 03 -
DE - BETA DOCENTE SINTÉTICO, lotado (a) no (a) Departamento Sintético,
a partir de 06.02.2026.
(Assinado digitalmente em 21/02/2026)
Matrícula: 7777777
"""
SUBSTITUTION = """UNIVERSIDADE FEDERAL DO PIAUÍ
ATO DA REITORIA N.º 900/26
RESOLVE:
Designar ALFA SUBSTITUTO, matrícula
SIAPE nº 1234567, para responder pela Função Gratificada, FG-2, de Chefe Sintético,
no período de 05/02/2026 a 10/02/2026, por motivo de férias da titular, BETA TITULAR.
Teresina, 01 de fevereiro de 2026.
AUTORIDADE SINTÉTICA
"""
TAE = """Conceder progressão funcional por MÉRITO PROFISSIONAL, aos servidores técnico
administrativos desta IFES, constantes do Anexo desta Portaria, cujos efeitos financeiros
retroagem às respectivas datas.
(Assinado digitalmente em 21/02/2026)
Matrícula: 7777777
ANEXO DE PORTARIA Nº 900 / 2026 - SRH
"""


def document(*texts):
    return extrair_documento(
        [{"numero": n + 1, "texto": t} for n, t in enumerate(texts)]
    )


def observed(doc, key, block=None):
    return [
        f
        for f in doc["campos"]
        if f["campo"] == key and (not block or f["bloco_id"] == block)
    ]


def test_docente_dates_destination_and_issuer_are_separate():
    doc = document(HEADER + PROGRESSION)
    assert doc["layout"] == "PORTARIA_UFPI_DOCENTE"
    assert doc["versao_leitor"] == "rh_paginas_v5"
    assert observed(doc, "nome")[0]["valor"] == "ALFA DOCENTE SINTÉTICO"
    assert observed(doc, "matricula")[0]["valor"] is None
    assert observed(doc, "data_documento")[0]["valor"] == "2026-02-20"
    assert observed(doc, "data_publicacao")[0]["estado"] == "AUSENTE"
    assert observed(doc, "efeitos_financeiros")[0]["valor"] == "2026-02-05"
    assert observed(doc, "classe_destino")[0]["valor"] == "C"
    assert observed(doc, "nivel_destino")[0]["valor"] == "2"
    assert not any(f["valor"] == "7777777" for f in doc["campos"])


def test_titling_does_not_infer_progression_or_payments():
    doc = document(HEADER + TITLING)
    assert observed(doc, "nome")[0]["valor"] == "BETA DOCENTE SINTÉTICO"
    assert observed(doc, "titulacao_destino")[0]["valor"] == "Doutorado"
    assert observed(doc, "efeitos_financeiros")[0]["valor"] == "2026-02-06"
    assert not observed(doc, "nivel_destino")
    assert not observed(doc, "rubrica")


def test_substitute_and_owner_are_distinct_and_leave_is_not_inferred():
    doc = document(SUBSTITUTION)
    assert doc["layout"] == "ATO_UFPI_SUBSTITUICAO"
    assert [b["papel_documental"] for b in doc["blocos"]] == ["SUBSTITUTO", "TITULAR"]
    assert [b["nome"] for b in doc["blocos"]] == ["ALFA SUBSTITUTO", "BETA TITULAR"]
    assert [b["matricula"] for b in doc["blocos"]] == ["1234567", None]
    assert observed(doc, "inicio_designacao")[0]["valor"] == "2026-02-05"
    assert observed(doc, "fim_designacao")[0]["valor"] == "2026-02-10"
    assert observed(doc, "codigo_funcao_substituida")[0]["valor"] == "FG-2"
    assert not observed(doc, "afastamentos_titular")
    assert not observed(doc, "efeitos_financeiros")


@pytest.mark.parametrize("prefix", ["  ", "\t", "\n\n  "])
def test_substitution_header_accepts_whitespace_without_changing_identity_or_dates(
    prefix,
):
    doc = document(SUBSTITUTION.replace("ATO DA REITORIA", prefix + "ATO DA REITORIA"))
    assert doc["layout"] == "ATO_UFPI_SUBSTITUICAO"
    assert [b["nome"] for b in doc["blocos"]] == ["ALFA SUBSTITUTO", "BETA TITULAR"]
    assert observed(doc, "inicio_designacao")[0]["valor"] == "2026-02-05"
    assert observed(doc, "fim_designacao")[0]["valor"] == "2026-02-10"


@pytest.mark.parametrize("replacement", ["31/02/2026", "11/02/2026"])
def test_invalid_or_reversed_period_is_left_empty(replacement):
    doc = document(SUBSTITUTION.replace("05/02/2026", replacement))
    assert observed(doc, "inicio_designacao")[0]["valor"] is None


def test_conflicting_effects_remain_empty_with_candidates_and_real_page():
    doc = document(
        HEADER
        + PROGRESSION.replace("05.02.2026.", "05.02.2026 e a partir de 06.02.2026.")
    )
    field = observed(doc, "efeitos_financeiros")[0]
    assert field["valor"] is None and field["estado"] == "AMBIGUO"
    assert field["candidatos"] == ["05.02.2026", "06.02.2026"]
    assert field["pagina"] == 1


def test_tae_annex_uses_respective_dates_and_distinct_people_across_pages():
    doc = document(
        HEADER + TAE + "1234567 ALFA TAE 200 D-001 D-002 05/02/2026",
        "2345678 BETA TAE 200 E-010 E-011 06/02/2026",
    )
    assert doc["layout"] == "PORTARIA_UFPI_TAE"
    assert [b["matricula"] for b in doc["blocos"]] == ["1234567", "2345678"]
    assert [f["valor"] for f in observed(doc, "posicao_destino")] == ["D-002", "E-011"]
    assert [
        (f["valor"], f["pagina"]) for f in observed(doc, "efeitos_financeiros")
    ] == [("2026-02-05", 1), ("2026-02-06", 2)]
    assert observed(doc, "data_documento", doc["blocos"][1]["id"])[0]["pagina"] == 1


@pytest.mark.parametrize(
    "reference",
    [
        "901 / 2026 - SRH",
        "900 / 2025 - SRH",
        "900 / 2026 - OUTRO",
        "ILEGÍVEL",
        "900 / 20260 - SRH",
        "900 / 2026 - SRH2",
        "900 / 2026 - SRH e PORTARIA Nº 901 / 2026 - SRH",
    ],
)
def test_divergent_annex_does_not_inherit_previous_act_dates_or_rights(reference):
    doc = document(
        HEADER + TAE + "1234567 ALFA 200 D-001 D-002 05/02/2026",
        f"ANEXO DE PORTARIA Nº {reference}\n2345678 BETA 200 E-001 E-002 06/02/2026",
        "3456789 GAMA 200 E-002 E-003 07/02/2026",
    )
    assert doc["situacao"] == "PARCIAL"
    assert (
        observed(doc, "efeitos_financeiros", doc["blocos"][0]["id"])[0]["valor"]
        == "2026-02-05"
    )
    assert not any(f["valor"] in ("2026-02-06", "2026-02-07") for f in doc["campos"])
    rejected = next(b for b in doc["blocos"] if b["paginas"] == [2])
    assert observed(doc, "data_documento", rejected["id"])[0]["valor"] is None
    assert observed(doc, "efeitos_financeiros", rejected["id"])[0]["valor"] is None
    assert observed(doc, "identificador_ato", rejected["id"])[0]["pagina"] == 2
    assert any(
        "identificação do anexo divergente" in warning for warning in doc["avisos"]
    )


@pytest.mark.parametrize("reference", ["900 / 2026 - SRH", "0900/2026", "900 / 2026"])
def test_matching_annex_reference_keeps_confirmed_context(reference):
    doc = document(
        HEADER + TAE + "1234567 ALFA 200 D-001 D-002 05/02/2026",
        f"ANEXO DA PORTARIA Nº {reference}\n2345678 BETA 200 E-001 E-002 06/02/2026",
    )
    assert [b["matricula"] for b in doc["blocos"]] == ["1234567", "2345678"]
    assert observed(doc, "efeitos_financeiros")[1]["valor"] == "2026-02-06"
    assert not doc["avisos"]


def test_orphan_annex_stays_manual_without_borrowing_a_right():
    doc = document(
        "ANEXO DE PORTARIA Nº 901 / 2026 - SRH\n2345678 BETA 200 E-001 E-002 06/02/2026"
    )
    assert doc["situacao"] == "NAO_SUPORTADO"
    assert observed(doc, "efeitos_financeiros")[0]["valor"] is None
    assert all(b["matricula"] is None for b in doc["blocos"])


def test_numbered_annex_with_conflicting_reference_does_not_reuse_context():
    doc = document(
        HEADER + TAE + "1234567 ALFA 200 D-001 D-002 05/02/2026",
        "ANEXO I DA PORTARIA Nº 901 / 2026 - SRH\n2345678 BETA 200 E-001 E-002 06/02/2026",
    )
    assert doc["situacao"] == "PARCIAL"
    assert [f["valor"] for f in observed(doc, "efeitos_financeiros") if f["valor"]] == [
        "2026-02-05"
    ]
    assert doc["avisos"]


def test_geometry_joins_wrapped_names_only_between_proven_columns():
    def word(text, x, y, width=25):
        return {"text": text, "x0": x, "x1": x + width, "top": y}

    words = [
        word("1234567", 10, 100),
        word("ALFA", 100, 94),
        word("SINTETICO", 100, 106),
        word("200", 250, 100),
        word("D-001", 300, 100),
        word("D-002", 350, 100),
        word("05/02/2026", 400, 100, 70),
        word("2345678", 10, 130),
        word("BETA", 100, 130),
        word("200", 250, 130),
        word("D-002", 300, 130),
        word("D-003", 350, 130),
        word("06/02/2026", 400, 130, 70),
    ]
    assert linhas_anexo_tae(words) == [
        "1234567 ALFA SINTETICO 200 D-001 D-002 05/02/2026",
        "2345678 BETA 200 D-002 D-003 06/02/2026",
    ]


def test_unresolved_native_annex_row_is_reported_without_losing_valid_rows():
    def word(text, x, y):
        return {"text": text, "x0": x, "x1": x + 25, "top": y}

    words = [
        word("1234567", 10, 100),
        word("ALFA", 100, 100),
        word("200", 250, 100),
        word("D-001", 300, 100),
        word("D-002", 350, 100),
        word("05/02/2026", 400, 100),
        word("2345678", 10, 150),
        word("BETA", 100, 150),
        word("SEM_DESTINO", 300, 150),
    ]
    rows = linhas_anexo_tae(words)
    doc = extrair_documento([{"numero": 1, "texto": HEADER + TAE, "linhas_tae": rows}])
    assert len(doc["blocos"]) == 1
    assert doc["blocos"][0]["matricula"] == "1234567"
    assert any("linha do anexo não resolvida" in warning for warning in doc["avisos"])


@pytest.mark.parametrize("bad_y", [80, 120, 180])
def test_incomplete_identity_rows_are_barriers_for_neighbor_names(bad_y):
    def word(text, x, y, width=25):
        return {"text": text, "x0": x, "x1": x + width, "top": y}

    words = []
    for mat, name, y in [("1234567", "ALFA", 100), ("3456789", "GAMA", 160)]:
        words.extend(
            [
                word(mat, 10, y),
                word(name, 100, y),
                word("200", 250, y),
                word("D-001", 300, y),
                word("D-002", 350, y),
                word("05/02/2026", 400, y, 70),
            ]
        )
    words.extend(
        [
            word("2345678", 10, bad_y),
            word("BETA", 100, bad_y),
            word("200", 250, bad_y),
            word("D-001", 300, bad_y),
            word("ILEGIVEL", 350, bad_y),
        ]
    )
    doc = extrair_documento(
        [{"numero": 1, "texto": HEADER + TAE, "linhas_tae": linhas_anexo_tae(words)}]
    )
    assert [b["nome"] for b in doc["blocos"]] == ["ALFA", "GAMA"]
    assert [b["matricula"] for b in doc["blocos"]] == ["1234567", "3456789"]
    assert any("linha do anexo não resolvida" in warning for warning in doc["avisos"])


def test_name_on_shared_boundary_is_not_assigned_to_either_person():
    def word(text, x, y, width=25):
        return {"text": text, "x0": x, "x1": x + width, "top": y}

    words = [word("INCERTO", 100, 110)]
    for mat, name, y in [("1234567", "ALFA", 100), ("2345678", "BETA", 120)]:
        words.extend(
            [
                word(mat, 10, y),
                word(name, 100, y),
                word("200", 250, y),
                word("D-001", 300, y),
                word("D-002", 350, y),
                word("05/02/2026", 400, y, 70),
            ]
        )
    doc = extrair_documento(
        [{"numero": 1, "texto": HEADER + TAE, "linhas_tae": linhas_anexo_tae(words)}]
    )
    assert not any(
        f["campo"] == "nome" and f["estado"] == "EXTRAIDO" for f in doc["campos"]
    )
    assert doc["situacao"] == "PARCIAL" and doc["avisos"]


def test_multiple_designations_are_not_attributed_to_first_person():
    doc = document(
        SUBSTITUTION.replace(
            "Teresina,",
            "Designar OUTRA PESSOA, matrícula SIAPE nº 2345678, para responder pela Função Gratificada, FG-3.\nTeresina,",
        )
    )
    assert doc["situacao"] == "NAO_SUPORTADO"
    assert all(block["matricula"] is None for block in doc["blocos"])


@pytest.mark.parametrize(
    "text",
    [
        HEADER + "Designar comissão examinadora.",
        HEADER + "RETIFICAR o ato anterior.",
        "PORTARIA Nº 900, DE 20 DE FEVEREIRO DE 2026\nRESOLVE: Designar comissão.",
    ],
)
def test_unsupported_acts_do_not_fall_back_to_generic_identity_matching(text):
    doc = document(text + "\nNome: ASSINANTE\nMatrícula: 7777777")
    assert doc["situacao"] == "NAO_SUPORTADO"
    assert not any(b["matricula"] for b in doc["blocos"])
    assert doc["avisos"]


def test_mixed_pdf_keeps_independent_financial_sources():
    financial = "Ficha Financeira referente a: 2026\nNome: 1234567 - ALFA Banco/Agencia: 1\nRubrica|Nome|R/D|Seq.|JAN\n98002|PSS|D|0|100,00"
    doc = document(SUBSTITUTION, financial)
    assert doc["layout"] == "MISTO"
    assert observed(doc, "rubrica")[0]["pagina"] == 2
    assert observed(doc, "rubrica")[0]["valor"] == "100.00"


class FinalData(SimpleNamespace):
    def model_dump(self):
        return {
            "nome": self.nome,
            "matricula": self.matricula,
            "efeitos_financeiros": "2026-02-05",
        }


def reviewed(doc, key, value, destination):
    block = doc["blocos"][0]
    field = observed(doc, key)[0]
    review = RevisaoExtracao.model_validate(
        {
            "documentos": [doc],
            "associacoes": [
                {
                    "documento_id": doc["id"],
                    "bloco_id": block["id"],
                    "pessoa": "SERVIDOR",
                    "matricula": "1234567",
                    "vinculo": "V1",
                    "confirmado": True,
                    "justificativa": "Identidade conferida manualmente com fonte sintética.",
                }
            ],
            "vinculo_calculo": "V1",
            "confirmado": True,
            "aplicacoes": [
                {
                    "documento_id": doc["id"],
                    "campo_id": field["id"],
                    "destino": [destination],
                    "valor_revisado": value,
                    "justificativa": "Ambiguidade resolvida pelo operador.",
                }
            ],
        }
    )
    return FinalData(nome="ALFA", matricula="1234567", revisao_extracao=review)


def test_manual_ambiguity_resolution_requires_justification_and_matching_final_value():
    doc = document(
        HEADER
        + PROGRESSION.replace("05.02.2026.", "05.02.2026 e a partir de 06.02.2026.")
    )
    data = reviewed(doc, "efeitos_financeiros", "2026-02-05", "efeitos_financeiros")
    validar_revisao_extracao(data)
    data.revisao_extracao.aplicacoes[0].justificativa = ""
    with pytest.raises(PendenciaApuracao):
        validar_revisao_extracao(data)


def test_act_date_cannot_fill_financial_effects():
    doc = document(HEADER + PROGRESSION)
    data = reviewed(doc, "data_documento", "2026-02-05", "efeitos_financeiros")
    with pytest.raises(PendenciaApuracao, match="Destino incompatível"):
        validar_revisao_extracao(data)


def test_explicit_person_role_cannot_be_changed_by_association():
    doc = document(HEADER + PROGRESSION)
    data = reviewed(doc, "nome", "ALFA", "nome")
    data.revisao_extracao.associacoes[0].pessoa = "TITULAR"
    data.substituicao = SimpleNamespace(titular_matricula="1234567")
    data.revisao_extracao.vinculo_titular = "V1"
    with pytest.raises(PendenciaApuracao, match="Papel associado diverge"):
        validar_revisao_extracao(data)


def test_worker_and_upload_contract_use_the_new_reader(auth_client_user, tmp_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in (HEADER + PROGRESSION).splitlines():
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    target = tmp_path / "portaria-sintetica.pdf"
    pdf.output(target)
    response = auth_client_user.post(
        "/api/extrair-pdf",
        data={"tipo_calculo": "progressao", "versao_extracao": "2"},
        files={"arquivos": (target.name, target.read_bytes(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    result = response.json()["resultados"][0]["extracao"]
    assert result["layout"] == "PORTARIA_UFPI_DOCENTE"
    assert observed(result, "nivel_destino")[0]["valor"] == "2"
    assert observed(result, "efeitos_financeiros")[0]["valor"] == "2026-02-05"


def test_valid_manual_inputs_need_no_portaria(auth_client_user):
    from test_exercicios_parcelas import plan

    validar_revisao_extracao(SimpleNamespace(revisao_extracao=None))
    response = auth_client_user.post(
        "/api/calcular",
        json={
            "tipo_calculo": "exercicio_anterior",
            "dados_extraidos": {"matricula": "1234567", "exercicios": plan()},
        },
    )
    assert response.status_code == 200, response.text
