#!/usr/bin/env python3
"""TURBOFUSION 3.0 — Collecte hippique contrôlée."""

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
DESTINATION = Path("data/courses.json")
CRITERES = (
    "forme", "aptitude", "regularite",
    "jockey", "entraineur", "distance", "terrain"
)


def collecter():
    url = os.environ.get("TURBOFUSION_SOURCE_URL", "").strip()

    if not url.startswith("https://"):
        raise ValueError(
            "Configurer TURBOFUSION_SOURCE_URL "
            "avec une URL HTTPS de données JSON."
        )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "TURBOFUSION-3.0/1.0",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise ValueError("Erreur HTTP de collecte")
        contenu = response.read(5_000_001)

    if len(contenu) > 5_000_000:
        raise ValueError("Réponse trop volumineuse")

    donnees = json.loads(contenu.decode("utf-8"))

    if not isinstance(donnees, dict):
        raise ValueError("Objet JSON attendu")

    courses = donnees.get("courses")
    if not isinstance(courses, list):
        raise ValueError("Champ courses manquant ou invalide")

    aujourd_hui = datetime.now(PARIS).date()
    valides = []
    identifiants = set()

    for course in courses:
        if not isinstance(course, dict):
            continue

        try:
            identifiant = str(course["id"]).strip()
            depart = datetime.fromisoformat(course["depart"])
            source = course["source"]
            partants = course["partants"]

            if not identifiant or identifiant in identifiants:
                continue
            if depart.tzinfo is None:
                continue
            if depart.astimezone(PARIS).date() != aujourd_hui:
                continue
            if not isinstance(source, str) or not source.strip():
                continue
            if not isinstance(partants, list) or len(partants) < 2:
                continue

            numeros = set()
            for cheval in partants:
                numero = int(cheval["numero"])
                if numero <= 0 or numero in numeros:
                    raise ValueError("Numéro invalide")
                numeros.add(numero)

                if not str(cheval["nom"]).strip():
                    raise ValueError("Nom manquant")

                for critere in CRITERES:
                    if critere in cheval:
                        note = cheval[critere]
                        if (
                            isinstance(note, bool)
                            or not isinstance(note, (int, float))
                            or not 0 <= note <= 1
                        ):
                            raise ValueError("Note invalide")

            identifiants.add(identifiant)
            valides.append(course)

        except (KeyError, TypeError, ValueError):
            continue

    if not valides:
        raise ValueError(
            "Aucune course valide pour aujourd'hui. "
            "Anciennes données conservées sans validation."
        )

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporaire = DESTINATION.with_suffix(".tmp")

    temporaire.write_text(
        json.dumps(
            {"courses": valides},
            ensure_ascii=False,
            indent=2,
            allow_nan=False
        ) + "\n",
        encoding="utf-8"
    )
    temporaire.replace(DESTINATION)

    print(f"Collecte validée : {len(valides)} courses")
    print(f"Fichier : {DESTINATION}")


if __name__ == "__main__":
    try:
        collecter()
    except Exception as erreur:
        print(f"ERREUR COLLECTE : {erreur}", file=sys.stderr)
        sys.exit(1)
  
