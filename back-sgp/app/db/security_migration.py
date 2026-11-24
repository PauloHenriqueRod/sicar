"""Migração aditiva e idempotente para bancos anteriores às sessões persistentes."""
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def migrate_security_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "users" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "token_version" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 1"))
        if "auth_subject" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN auth_subject VARCHAR(36)"))
        ids = connection.execute(text("SELECT id FROM users WHERE auth_subject IS NULL OR auth_subject = ''")).scalars().all()
        for user_id in ids:
            connection.execute(text("UPDATE users SET auth_subject = :subject WHERE id = :id"), {"subject": str(uuid4()), "id": user_id})
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_auth_subject ON users (auth_subject)"))
        connection.execute(text("UPDATE users SET token_version = 1 WHERE token_version IS NULL"))
