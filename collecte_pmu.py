#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""TURBOFUSION 3.0 — Validation des données PMU.

Entrée : data/courses_source.json
Sortie : data/courses.json

Le fichier source doit provenir d'un fournisseur
de données hippiques vérifié.
Aucune course ni aucun cheval n'est inventé.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "courses_source.json"
DEST = ROOT / "data" / "courses.json"


def verifier(course):
    champs = (
        "id",
        "hippodrome",
        "depart",
        "source",
        "partants",
    )

    for champ in champs:
        if champ not in course:
            raise ValueError(
                f"Champ manquant : {champ}"
            )

    if not isinstance(course["id"], str) or not course["id"]:
        raise ValueError("Identifiant invalide")

    depart = datetime.fromisoformat(
        course["depart"].replace("Z", "+00:00")
    )

    if depart.tzinfo is None or depart.utcoffset() is None:
        raise ValueError("Départ sans fuseau horaire")

    url = urlparse(course["source"])

    if url.scheme != "https" or not url.hostname:
        raise ValueError("Source HTTPS exigée")

    if course.get("pays", "").upper() not in (
        "FR",
        "FRANCE",
    ):
        raise ValueError(
            "Pays français non confirmé"
        )

    chevaux = course["partants"]

    if not isinstance(chevaux, list) or len(chevaux) < 2:
        raise ValueError("Partants absents")

    numeros = [
        cheval.get("numero")
        for cheval in chevaux
        if isinstance(cheval, dict)
    ]

    if (
        len(numeros) != len(chevaux)
        or any(
            type(numero) is not int or numero <= 0
            for numero in numeros
        )
        or len(set(numeros)) != len(numeros)
    ):
        raise ValueError(
            "Numéros invalides ou dupliqués"
        )

    for cheval in chevaux:
        if (
            not isinstance(cheval.get("nom"), str)
            or not cheval["nom"].strip()
        ):
            raise ValueError("Nom de cheval absent")

    np = course.get("non_partants", [])

    if (
        not isinstance(np, list)
        or any(type(numero) is not int for numero in np)
        or len(set(np)) != len(np)
        or not set(np).issubset(numeros)
    ):
        raise ValueError(
            "Non-partants incohérents"
        )

    return depart


def main():
    if not SOURCE.exists():
        print(
            "COLLECTE NON CONNECTÉE : "
            "data/courses_source.json absent.",
            file=sys.stderr,
        )
        return 2

    donnees = json.loads(
        SOURCE.read_text(encoding="utf-8")
    )

    if (
        not isinstance(donnees, dict)
        or not isinstance(donnees.get("courses"), list)
    ):
        raise ValueError(
            'Format attendu : {"courses": [...]}'
        )

    identifiants = set()

    for course in donnees["courses"]:
        verifier(course)

        if course["id"] in identifiants:
            raise ValueError(
                "Identifiant de course dupliqué"
            )

        identifiants.add(course["id"])

    donnees["courses"].sort(
        key=lambda course: datetime.fromisoformat(
            course["depart"].replace("Z", "+00:00")
        )
    )

    DEST.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporaire = DEST.with_suffix(".json.tmp")

    temporaire.write_text(
        json.dumps(
            {"courses": donnees["courses"]},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    temporaire.replace(DEST)

    print(
        f"Collecte validée : {len(identifiants)} "
        "courses ; provenance non vérifiée "
        "indépendamment."
    )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
    ) as erreur:
        print(
            "ERREUR COLLECTE :",
            erreur,
            file=sys.stderr,
        )
        sys.exit(1)
