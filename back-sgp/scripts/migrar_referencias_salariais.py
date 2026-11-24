"""Executar a partir de back-sgp: python -m scripts.migrar_referencias_salariais --help."""

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine

from app.db.salary_reference_migration import migrate_salary_references


def main():
    parser = argparse.ArgumentParser(
        description="Copia o cadastro anual como pendência; não presume vigências."
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="Banco alvo explícito; use primeiro uma cópia temporária.",
    )
    parser.add_argument(
        "--report", required=True, type=Path, help="Relatório local; não versionar."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Confirma a migração; o padrão é simular e desfazer.",
    )
    args = parser.parse_args()
    # Reserva o arquivo antes de abrir o banco; não sobrescreve relatórios existentes.
    with args.report.open("x", encoding="utf-8") as output:
        engine = create_engine(args.database_url, hide_parameters=True)
        try:
            report = migrate_salary_references(engine, dry_run=not args.apply)
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write("\n")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
