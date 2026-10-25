#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TURBOFUSION 3.0 — INSTALLATEUR UNIQUE
Préserve main.py, publish_data.py et les moteurs M1-M5.

Utilisation :
    python installer_turbofusion.py
"""

from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parent


def installer(fichier, contenu):
    destination = ROOT / fichier
    destination.parent.mkdir(
        parents=True, exist_ok=True
    )
    destination.write_text(
        textwrap.dedent(contenu).lstrip(),
        encoding="utf-8"
    )
    print("INSTALLÉ :", fichier)


COLLECTEUR = r'''
#!/usr/bin/env python3
"""Collecte JSON contrôlée pour TURBOFUSION M1-M5."""

import argparse
import datetime as dt
import json
import math
import os
import tempfile
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")

FEATURES = (
    "forme", "aptitude", "regularite",
    "jockey", "entraineur", "distance", "terrain"
)


def valider(course):
    if not isinstance(course, dict):
        raise ValueError("Course invalide")

    for champ in ("id", "depart", "source", "partants"):
        if champ not in course:
            raise ValueError("Champ absent : " + champ)

    if not isinstance(course["id"], str) or not course["id"].strip():
        raise ValueError("Identifiant invalide")

    if not isinstance(course["source"], str) or not course["source"].strip() or course["source"] == "non_documentee":
        raise ValueError("Source non documentée")

    depart = dt.datetime.fromisoformat(course["depart"])
    if depart.tzinfo is None or depart.utcoffset() is None:
        raise ValueError("Fuseau horaire absent")

    chevaux = course["partants"]
    if not isinstance(chevaux, list) or len(chevaux) < 2:
        raise ValueError("Partants insuffisants")

    numeros = set()
    for cheval in chevaux:
        if not isinstance(cheval, dict):
            raise ValueError("Cheval invalide")

        numero = cheval.get("numero")
        if type(numero) is not int or numero <= 0:
            raise ValueError("Numéro invalide")
        if numero in numeros:
            raise ValueError("Numéro dupliqué")
        numeros.add(numero)

        if not isinstance(cheval.get("nom"), str) or not cheval["nom"].strip():
            raise ValueError("Nom manquant")

        for feature in FEATURES:
            if feature in cheval:
                valeur = cheval[feature]
                if (
                    type(valeur) not in (int, float)
                    or not math.isfinite(valeur)
                    or not 0 <= valeur <= 1
                ):
                    raise ValueError(
                        "Score invalide : " + feature
                    )

    return depart.astimezone(PARIS).date()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/courses.json")
    )
    parser.add_argument(
        "--date",
        default=dt.datetime.now(PARIS).date().isoformat()
    )
    args = parser.parse_args()

    url = os.environ.get("TURBOFUSION_COURSES_URL", "")
    if not url.startswith("https://"):
        print("AVERTISSEMENT : source HTTPS non configurée")
        return 2

    try:
        date_cible = dt.date.fromisoformat(args.date)

        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "TURBOFUSION-3.0/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=25) as response:
            brut = response.read(3000001)

        if len(brut) > 3000000:
            raise ValueError("Réponse trop volumineuse")

        donnees = json.loads(brut)
        if not isinstance(donnees, dict) or not isinstance(donnees.get("courses"), list):
            raise ValueError("Format courses[] attendu")

        courses = []
        ids = set()

        for course in donnees["courses"]:
            jour = valider(course)
            if jour != date_cible:
                continue
            if course["id"] in ids:
                raise ValueError("Identifiant dupliqué")
            ids.add(course["id"])
            courses.append(course)

        if not courses:
            print("Aucune course vérifiée")
            return 2

        args.output.parent.mkdir(
            parents=True, exist_ok=True
        )

        temporaire = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=args.output.parent,
                delete=False,
                suffix=".tmp"
            ) as f:
                temporaire = Path(f.name)
                json.dump(
                    {"courses": courses},
                    f,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False
                )
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())

            os.replace(temporaire, args.output)
        finally:
            if temporaire and temporaire.exists():
                temporaire.unlink()

        print("Courses vérifiées :", len(courses))
        return 0

    except (
        ValueError, OSError, TypeError,
        TimeoutError, json.JSONDecodeError
    ) as erreur:
        print("ERREUR COLLECTE :", erreur)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
'''


TESTS = r'''
import unittest
from collect_courses import valider


class TestCollecteur(unittest.TestCase):

    def exemple(self):
        return {
            "id": "TEST-R1-C1",
            "source": "test_uniquement",
            "depart": "2026-10-25T14:00:00+01:00",
            "partants": [
                {
                    "numero": 1,
                    "nom": "Cheval A",
                    "forme": 0.8
                },
                {
                    "numero": 2,
                    "nom": "Cheval B",
                    "forme": 0.6
                }
            ]
        }

    def test_valide(self):
        self.assertEqual(
            valider(self.exemple()).isoformat(),
            "2026-10-25"
        )

    def test_doublon(self):
        course = self.exemple()
        course["partants"][1]["numero"] = 1
        with self.assertRaises(ValueError):
            valider(course)

    def test_score_invalide(self):
        course = self.exemple()
        course["partants"][0]["forme"] = 2
        with self.assertRaises(ValueError):
            valider(course)

    def test_fuseau_absent(self):
        course = self.exemple()
        course["depart"] = "2026-10-25T14:00:00"
        with self.assertRaises(ValueError):
            valider(course)


if __name__ == "__main__":
    unittest.main()
'''


WORKFLOW = r'''
name: TURBOFUSION 3.0 - M1 a M5

on:
  workflow_dispatch:
  schedule:
    - cron: "15 * * * *"

permissions:
  contents: write

concurrency:
  group: turbofusion-production
  cancel-in-progress: false

jobs:
  analyse:
    name: Analyse et publication M1-M5
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - name: Recuperer le depot
        uses: actions/checkout@v4

      - name: Installer Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Verifier le logiciel
        shell: bash
        run: |
          set -euo pipefail
          python -m py_compile main.py publish_data.py collect_courses.py
          python -m unittest discover -s tests -v

      - name: Verifier les cinq moteurs
        shell: bash
        run: |
          python - <<'PY'
          from main import WEIGHTS
          from publish_data import MOTEURS

          attendus = ("M1", "M2", "M3", "M4", "M5")
          assert tuple(WEIGHTS) == attendus
          assert tuple(MOTEURS) == attendus
          for moteur in attendus:
              assert len(WEIGHTS[moteur]) == 7
          print("M1-M5 : OK")
          PY

      - name: Collecter les courses
        id: collecte
        shell: bash
        env:
          TURBOFUSION_COURSES_URL: ${{ secrets.TURBOFUSION_COURSES_URL }}
        run: |
          set +e
          python collect_courses.py
          code=$?
          if [ "$code" -eq 0 ]; then
            echo "disponible=true" >> "$GITHUB_OUTPUT"
          elif [ "$code" -eq 2 ]; then
            echo "disponible=false" >> "$GITHUB_OUTPUT"
            echo "::warning::Collecte indisponible"
          else
            exit "$code"
          fi

      - name: Executer M1-M5
        if: steps.collecte.outputs.disponible == 'true'
        shell: bash
        run: |
          set -euo pipefail
          python main.py --figer --strict-input --safety-minutes 2

      - name: Verifier la publication
        if: steps.collecte.outputs.disponible == 'true'
        shell: bash
        run: |
          python - <<'PY'
          import json
          from pathlib import Path

          path = Path("data/publication_latest.json")
          if not path.is_file():
              raise SystemExit("Publication absente")

          data = json.loads(path.read_text(encoding="utf-8"))
          if not isinstance(data, dict) or not isinstance(data.get("courses"), list):
              raise SystemExit("Publication invalide")

          for course in data["courses"]:
              moteurs = course.get("moteurs", {})
              if not isinstance(moteurs, dict):
                  raise SystemExit("Moteurs invalides")
              if not set(moteurs).issubset({"M1", "M2", "M3", "M4", "M5"}):
                  raise SystemExit("Moteur inconnu")

          print("Publication valide")
          PY

      - name: Enregistrer les donnees
        if: steps.collecte.outputs.disponible == 'true'
        shell: bash
        run: |
          set -euo pipefail
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -- data/

          if git diff --cached --quiet; then
            echo "Aucune modification"
            exit 0
          fi

          git commit -m "Actualisation TURBOFUSION M1-M5"

          for tentative in 1 2 3; do
            if git push origin HEAD:main; then
              exit 0
            fi
            if [ "$tentative" -eq 3 ]; then
              exit 1
            fi
            sleep 5
          done
'''


def main():
    essentiels = [
        "main.py",
        "publish_data.py",
        "index.html"
    ]

    absents = [
        nom for nom in essentiels
        if not (ROOT / nom).is_file()
    ]

    if absents:
        raise SystemExit(
            "Installation annulée. Fichiers absents : "
            + ", ".join(absents)
        )

    from main import WEIGHTS
    from publish_data import MOTEURS

    attendus = ("M1", "M2", "M3", "M4", "M5")

    if tuple(WEIGHTS) != attendus or tuple(MOTEURS) != attendus:
        raise SystemExit(
            "Installation annulée : configuration M1-M5 incompatible"
        )

    for moteur in attendus:
        if len(WEIGHTS[moteur]) != 7:
            raise SystemExit(
                "Pondérations invalides : " + moteur
            )

    print("TURBOFUSION 3.0")
    print("Installation des composants de collecte")

    installer("collect_courses.py", COLLECTEUR)
    installer("tests/test_collect_courses.py", TESTS)
    installer(
        ".github/workflows/turbofusion.yml",
        WORKFLOW
    )

    print()
    print("INSTALLATION DES FICHIERS TERMINÉE")
    print("Moteurs M1-M5 préservés.")
    print("Configurer TURBOFUSION_COURSES_URL.")
    print("Exécuter les tests avant publication.")


if __name__ == "__main__":
    main()
