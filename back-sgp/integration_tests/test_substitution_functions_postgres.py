"""Referências de função e cálculo racional no PostgreSQL isolado do CI."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session


def test_function_reference_change_and_explicit_option_calculation(postgres_engine, history_table):
    from app.db.salary_reference_migration import migrate_salary_references
    from app.models.fontes_oficiais import (
        EstruturaFuncao,
        ReferenciaFuncao,
        migrate_official_sources,
    )
    from app.schemas.substituicao_periodos import PlanoSubstituicao
    from app.services.substituicao_periodos import calcular_substituicao_periodos
    from app.utils.function_keys import function_key

    migrate_salary_references(postgres_engine)
    migrate_official_sources(postgres_engine)
    with Session(postgres_engine) as db:
        structure = EstruturaFuncao(
            chave=function_key("FG", "SINTETICA", "TESTE", "GRATIFICACAO"),
            tipo_funcao="FG",
            codigo_funcao="SINTETICA",
            modalidade="TESTE",
            componente="GRATIFICACAO",
        )
        db.add(structure)
        db.flush()
        for first, last, amount in (
            (date(2024, 4, 1), date(2024, 4, 15), "100"),
            (date(2024, 4, 16), None, "200"),
        ):
            db.add(
                ReferenciaFuncao(
                    estrutura_id=structure.id,
                    inicio_vigencia=first,
                    fim_vigencia=last,
                    valor=Decimal(amount),
                    fonte="Tabela sintética",
                    conferido_por=1,
                    conferido_em=datetime(2026, 10, 28, 12),
                )
            )
        db.flush()
        interval = {
            "id": "D",
            "inicio": "2024-04-01",
            "ultimo_dia_considerado": "2024-04-30",
            "origem": "Documento sintético",
            "localizador": "linha 1",
            "motivo": "Teste",
        }
        plan = PlanoSubstituicao.model_validate(
            {
                "periodo": {
                    "inicio": "2024-04-01",
                    "ultimo_dia_considerado": "2024-04-30",
                },
                "designacao": interval,
                "titular_matricula": "998",
                "afastamentos_titular": [{**interval, "id": "A"}],
                "impedimentos_substituto": [],
                "estado_inicial": {
                    "substituida": {
                        "tipo_funcao": "FG",
                        "codigo_funcao": "SINTETICA",
                        "modalidade": "TESTE",
                        "componentes": [
                            {
                                "componente": "GRATIFICACAO",
                                "origem": "TABELA",
                                "percentual_utilizado": "60",
                            }
                        ],
                    },
                    "propria": {"situacao": "SEM_FUNCAO_CONFIRMADA"},
                    "opcao": {
                        "identificador": "R",
                        "versao": "1",
                        "fonte": "Regra sintética",
                        "inicio_vigencia": "2020-01-01",
                        "calculo": "BASE_SUBSTITUIDA",
                        "diferenca_negativa": "ZERAR",
                        "confirmada": True,
                    },
                },
                "rubrica": {
                    "rubrica": "83185",
                    "natureza_folha": "NORMAL",
                    "natureza_rubrica": "R",
                },
                "recebidos": [],
                "conferido_pelo_rh": True,
            }
        )
        result = calcular_substituicao_periodos(plan, db)
        assert result["totais"]["devido"] == "90.00"  # 100*.6*15/30 + 200*.6*15/30.
        assert (
            len(
                {
                    s["referencias_funcoes"][0]["referencia_id"]
                    for s in result["segmentos"]
                }
            )
            == 2
        )
