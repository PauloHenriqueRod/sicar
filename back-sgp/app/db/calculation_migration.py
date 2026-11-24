"""Migração aditiva: preserva históricos existentes e permite repetição segura."""
from sqlalchemy import inspect, text


def migrate_calculation_schema(engine):
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "historico_calculo" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("historico_calculo")}
        if "idempotency_key" not in columns:
            connection.execute(text("ALTER TABLE historico_calculo ADD COLUMN idempotency_key VARCHAR(36)"))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_historico_requisicao "
            "ON historico_calculo (user_id, idempotency_key)"
        ))
