"""Migração transacional: não escolhe nem remove valores salariais conflitantes."""
from sqlalchemy import inspect, text

from app.utils.crypto import decrypt_data, encrypt_data
from app.utils.salary_keys import salary_key


def migrate_salary_security(engine):
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        salary_tables = (
            ("tabela_vencimento_basico", "uq_vencimento_vigencia", False),
            ("tabela_retribuicao_titulacao", "uq_titulacao_vigencia", True),
        )
        prepared = []
        # Verifica conflitos antes de qualquer alteração de esquema ou conteúdo.
        for table, index_name, has_title in salary_tables:
            if table not in tables:
                continue
            rows = connection.execute(text(f"SELECT * FROM {table}")).mappings().all()
            seen = set()
            for row in rows:
                key = (salary_key(row["classe"] or ""), row["nivel"], row["ano"])
                if has_title:
                    key += (salary_key(row["titulacao"] or ""),)
                if not key[0] or row["nivel"] is None or row["ano"] is None or (has_title and not key[-1]):
                    raise RuntimeError("Revise registros salariais incompletos antes de atualizar a instalação.")
                if key in seen:
                    raise RuntimeError("Revise vigências salariais duplicadas antes de atualizar a instalação.")
                seen.add(key)
            prepared.append((table, index_name, has_title, rows))
        for table, index_name, has_title, rows in prepared:
            columns = {column["name"] for column in inspector.get_columns(table)}
            for column in ("classe_chave", "titulacao_chave") if has_title else ("classe_chave",):
                if column not in columns:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR NOT NULL DEFAULT ''"))
            for row in rows:
                params = {"id": row["id"], "classe": salary_key(row["classe"])}
                assignment = "classe_chave = :classe"
                if has_title:
                    assignment += ", titulacao_chave = :titulo"
                    params["titulo"] = salary_key(row["titulacao"])
                connection.execute(text(f"UPDATE {table} SET {assignment} WHERE id = :id"), params)
            keys = "classe_chave, nivel, titulacao_chave, ano" if has_title else "classe_chave, nivel, ano"
            connection.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} ({keys})"))
        if "historico_calculo" in tables:
            # Keyset pagination evita carregar todos os dados pessoais em memória.
            last_id = 0
            while True:
                rows = connection.execute(text(
                    "SELECT id, matricula, classe, titulacao, resultado_json FROM historico_calculo "
                    "WHERE id > :id ORDER BY id LIMIT 200"
                ), {"id": last_id}).mappings().all()
                if not rows:
                    break
                for row in rows:
                    assignments, params = [], {"id": row["id"]}
                    for field in ("matricula", "classe", "titulacao", "resultado_json"):
                        value = row[field]
                        if value is None:
                            continue
                        if value.startswith("gAAAAA"):
                            decrypt_data(value)  # Chave incorreta/corrupção bloqueia a migração.
                        else:
                            assignments.append(f"{field} = :{field}")
                            params[field] = encrypt_data(value)
                    if assignments:
                        connection.execute(text(f"UPDATE historico_calculo SET {', '.join(assignments)} WHERE id = :id"), params)
                last_id = rows[-1]["id"]
