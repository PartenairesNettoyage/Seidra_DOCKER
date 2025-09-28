#!/usr/bin/env python3
"""Migration utilitaire pour aligner la base Classic sur Ultimate."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterable

BACKEND_PATH = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from core.config import secret_manager, settings
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger("seidra.migrate")

MIGRATION_STATEMENTS = [
    "ALTER TABLE personas ADD COLUMN IF NOT EXISTS style_preset TEXT",
    "ALTER TABLE personas ADD COLUMN IF NOT EXISTS voice_id TEXT",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS nsfw_allowed BOOLEAN DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS retry_of INTEGER",
    "ALTER TABLE media ADD COLUMN IF NOT EXISTS favorite BOOLEAN DEFAULT 0",
]


def run_statements(engine_url: str, statements: Iterable[str], dry_run: bool) -> None:
    engine = create_engine(engine_url, future=True)
    with engine.begin() as connection:
        for statement in statements:
            LOGGER.info("Execution: %s", statement)
            if dry_run:
                continue
            connection.execute(text(statement))
    if dry_run:
        LOGGER.info("Mode simulation : aucune modification n'a été appliquée.")
    else:
        LOGGER.info("Migration terminée.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migre la base de données Classic vers Ultimate")
    parser.add_argument(
        "--database",
        help=(
            "URL SQLAlchemy de la base (ex: postgresql://user:pass@host/db). "
            "Par défaut, utilise le secret SEIDRA_DATABASE_URL."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="N'applique pas les requêtes, affiche uniquement")
    args = parser.parse_args()

    engine_url = (
        args.database
        or secret_manager.get("SEIDRA_DATABASE_URL")
        or settings.database_url
    )

    if not engine_url:
        raise SystemExit(
            "Impossible de déterminer l'URL de la base. Renseignez --database ou "
            "configurez SEIDRA_DATABASE_URL."
        )

    LOGGER.info("Connexion à %s", engine_url)
    run_statements(engine_url, MIGRATION_STATEMENTS, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
