"""Outil de rotation pour le compte démo SEIDRA Ultimate.

Ce script génère un mot de passe robuste pour l'utilisateur par défaut,
calcule son hachage via les utilitaires internes et met à jour la base de
l'application.  Le mot de passe en clair est affiché une seule fois afin
que l'opérateur puisse le stocker en lieu sûr, tandis que le hachage est
journalisé pour vérification.
"""

from __future__ import annotations

import argparse
import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Tuple

from services.database import (
    DEFAULT_USER_TEMPLATE,
    User,
    _hash_password,
    _update_default_user_rotation_settings,
    session_scope,
)


LOGGER = logging.getLogger("seidra.rotate_default_user")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def _generate_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"

    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        has_lower = any(c.islower() for c in candidate)
        has_upper = any(c.isupper() for c in candidate)
        has_digit = any(c.isdigit() for c in candidate)
        has_symbol = any(c in "!@#$%^&*()-_=+" for c in candidate)
        if has_lower and has_upper and has_digit and has_symbol:
            return candidate


def rotate_default_user(password_length: int = 24) -> Tuple[str, str]:
    password = _generate_password(password_length)
    hashed = _hash_password(password)
    rotated_at = datetime.now(timezone.utc)

    with session_scope() as session:
        user = (
            session.query(User)
            .filter(User.id == DEFAULT_USER_TEMPLATE["id"])
            .one_or_none()
        )
        if user is None:
            raise RuntimeError(
                "Le compte démo (ID=%s) est introuvable dans la base."%
                DEFAULT_USER_TEMPLATE["id"],
            )

        user.hashed_password = hashed
        user.is_active = True
        user.settings = _update_default_user_rotation_settings(
            user.settings, rotated_at
        )
        session.add(user)

    LOGGER.info("Nouveau hachage du compte démo : %s", hashed)
    return password, hashed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fait tourner le mot de passe du compte démo SEIDRA.",
    )
    parser.add_argument(
        "--length",
        type=int,
        default=24,
        help="Longueur du mot de passe généré (min. 12 caractères).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Active les logs détaillés.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.length < 12:
        raise SystemExit("La longueur minimale est de 12 caractères.")

    _configure_logging(args.verbose)

    password, hashed = rotate_default_user(password_length=args.length)
    print("\nMot de passe généré (à conserver immédiatement) :")
    print(password)
    print("\nHachage enregistré :")
    print(hashed)


if __name__ == "__main__":
    main()
