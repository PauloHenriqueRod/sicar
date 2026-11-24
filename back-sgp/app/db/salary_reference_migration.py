"""Migração aditiva, repetível e sem ativação presumida de referências."""

import json
from decimal import Decimal, InvalidOperation, localcontext

from sqlalchemy import inspect, select, text

from app.models.referencias_salariais import (
    SALARY_REFERENCE_TABLES,
    PendenciaSalarialLegada,
)

LEGACY_TABLES = ("tabela_vencimento_basico", "tabela_retribuicao_titulacao")


def _valor_convertido(original):
    if original is None:
        return None
    try:
        value = Decimal(str(original))
        if not value.is_finite() or not 0 <= value <= Decimal("1e12"):
            return None
        with localcontext() as context:
            context.prec = 64
            candidate = value.quantize(Decimal("0.000000000001"))
        # Não arredonda nem corrige um valor legado silenciosamente.
        return candidate if candidate == value else None
    except (InvalidOperation, ValueError):
        return None


def sync_legacy_salary_rows(connection):
    """Copia apenas dados remuneratórios; nunca altera a tabela de origem."""
    pending = PendenciaSalarialLegada.__table__
    tables = set(inspect(connection).get_table_names())
    converted, unchanged = 0, 0
    for table in LEGACY_TABLES:
        if table not in tables:
            continue
        for row in connection.execute(
            text(f"SELECT * FROM {table} ORDER BY id")
        ).mappings():
            original = {
                field: row.get(field)
                for field in ("classe", "nivel", "ano", "titulacao", "valor")
            }
            original["valor"] = (
                str(original["valor"]) if original["valor"] is not None else None
            )
            original_json = json.dumps(
                original, sort_keys=True, default=str, ensure_ascii=False
            )
            existing = (
                connection.execute(
                    select(pending).where(
                        pending.c.tabela_origem == table,
                        pending.c.id_origem == row["id"],
                    )
                )
                .mappings()
                .first()
            )
            if existing and existing["dados_originais"] == original_json:
                unchanged += 1
                continue
            numeric = _valor_convertido(original["valor"])
            values = {
                "tabela_origem": table,
                "id_origem": row["id"],
                "dados_originais": original_json,
                "valor_original": str(original["valor"])
                if original["valor"] is not None
                else None,
                "valor_decimal": numeric,
                "referencia_id": None,
                "motivo": "Carreira, vínculo, jornada, posição e vigência precisam de conferência."
                + (
                    " O valor não pôde ser convertido sem alteração; confira o original."
                    if numeric is None
                    else ""
                ),
            }
            if existing:
                identifier = existing["id"]
                connection.execute(
                    pending.update().where(pending.c.id == identifier).values(**values)
                )
            else:
                identifier = connection.execute(
                    pending.insert().values(**values)
                ).inserted_primary_key[0]
            persisted = connection.execute(
                select(pending.c.valor_decimal).where(pending.c.id == identifier)
            ).scalar_one()
            if numeric is not None and persisted != numeric:
                connection.execute(
                    pending.update()
                    .where(pending.c.id == identifier)
                    .values(
                        valor_decimal=None,
                        motivo=values["motivo"]
                        + " O banco não preservou a precisão; confira o valor original em PostgreSQL.",
                    )
                )
            converted += 1
    return {"copiados_ou_atualizados": converted, "inalterados": unchanged}


def migrate_salary_references(engine, *, dry_run=False):
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            if connection.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN")
            for table in SALARY_REFERENCE_TABLES:
                table.create(connection, checkfirst=True)
            summary = sync_legacy_salary_rows(connection)
            rows = (
                connection.execute(
                    select(PendenciaSalarialLegada.__table__).order_by(
                        PendenciaSalarialLegada.id
                    )
                )
                .mappings()
                .all()
            )
            report = {
                "versao": "referencias_salariais_v1",
                "simulacao": dry_run,
                **summary,
                "registros": [
                    {
                        "id": row["id"],
                        "origem": row["tabela_origem"],
                        "id_origem": row["id_origem"],
                        "valor_original": row["valor_original"],
                        "valor_decimal": str(row["valor_decimal"])
                        if row["valor_decimal"] is not None
                        else None,
                        "conversao_sem_alteracao": row["valor_decimal"] is not None
                        and Decimal(row["valor_original"]) == row["valor_decimal"],
                        "estado": "VINCULADA" if row["referencia_id"] else "PENDENTE",
                        "motivo": row["motivo"],
                    }
                    for row in rows
                ],
            }
            transaction.rollback() if dry_run else transaction.commit()
            return report
        except Exception:
            transaction.rollback()
            raise
