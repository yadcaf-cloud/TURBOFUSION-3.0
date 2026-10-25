
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🇸🇳🧠🔥 TURBOFUSION 3.0
INSTALLATEUR UNIQUE — M1 À M5

Intelligence hippique spécialisée
La magie du savoir

La mémoire conserve.
L'analyse comprend.
L'expérience enseigne.

Installation :
    python installer_turbofusion.py

Remplacement volontaire des fichiers générés :
    python installer_turbofusion.py --force

Cet installateur préserve :
    main.py
    publish_data.py
    index.html

Il installe :
    collect_courses.py
    tests/test_collect_courses.py
    .github/workflows/turbofusion.yml

L'installation ne garantit pas, à elle seule,
le fonctionnement des pronostics PMU.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import shutil
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MOTEURS = ("M1", "M2", "M3", "M4", "M5")


# ============================================================
# COLLECTEUR DES COURSES
# ============================================================

COLLECTEUR = r'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TURBOFUSION 3.0 — COLLECTEUR

Collecte les courses depuis une source HTTPS
configurée par TURBOFUSION_COURSES_URL.

Le JSON doit contenir :
{
    "courses": [
        {
            "id": "R1C1",
            "hippodrome": "Nom",
            "pays": "FR",
            "source": "https://...",
            "depart": "2026-10-25T14:00:00+01:00",
            "partants": [
                {"numero": 1, "nom": "Cheval A"}
            ]
        }
    ]
}

Les scores éventuels sont normalisés entre 0 et 1.
Le collecteur ne fabrique aucun score absent.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")

FEATURES = (
    "forme",
    "aptitude",
    "regularite",
    "jockey",
    "entraineur",
    "distance",
    "terrain",
)

MAX_BYTES = 3_000_000


def date_depart(valeur):
    if not isinstance(valeur, str):
        raise ValueError("Départ non textuel")

    try:
        depart = dt.datetime.fromisoformat(
            valeur.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            "Date de départ invalide"
        ) from exc

    if depart.tzinfo is None:
        raise ValueError(
            "Fuseau horaire absent"
        )

    if depart.utcoffset() is None:
        raise ValueError(
            "Décalage horaire absent"
        )

    return depart


def valider(course):
    if not isinstance(course, dict):
        raise ValueError("Course invalide")

    obligatoires = (
        "id",
        "depart",
        "source",
        "partants",
    )

    for champ in obligatoires:
        if champ not in course:
            raise ValueError(
                "Champ absent : " + champ
            )

    identifiant = course["id"]

    if (
        not isinstance(identifiant, str)
        or not identifiant.strip()
    ):
        raise ValueError(
            "Identifiant de course invalide"
        )

    source = course["source"]

    if (
        not isinstance(source, str)
        or not source.strip()
    ):
        raise ValueError(
            "Source non documentée"
        )

    source_parsee = urllib.parse.urlparse(source)

    if (
        source_parsee.scheme != "https"
        or not source_parsee.hostname
    ):
        raise ValueError(
            "Source de course HTTPS obligatoire"
        )

    depart = date_depart(course["depart"])

    pays = str(
        course.get("pays", "")
    ).strip().upper()

    if pays not in ("FR", "FRA", "FRANCE"):
        raise ValueError(
            "Course non confirmée en France"
        )

    chevaux = course["partants"]

    if (
        not isinstance(chevaux, list)
        or len(chevaux) < 2
    ):
        raise ValueError(
            "Nombre de partants insuffisant"
        )

    numeros = set()

    for cheval in chevaux:
        if not isinstance(cheval, dict):
            raise ValueError(
                "Cheval invalide"
            )

        numero = cheval.get("numero")

        if (
            type(numero) is not int
            or numero <= 0
        ):
            raise ValueError(
                "Numéro de cheval invalide"
            )

        if numero in numeros:
            raise ValueError(
                "Numéro de cheval dupliqué"
            )

        numeros.add(numero)

        nom = cheval.get("nom")

        if (
            not isinstance(nom, str)
            or not nom.strip()
        ):
            raise ValueError(
                "Nom du cheval manquant"
            )

        for feature in FEATURES:
            if feature not in cheval:
                continue

            valeur = cheval[feature]

            if (
                type(valeur) not in (int, float)
                or not math.isfinite(valeur)
                or not 0 <= valeur <= 1
            ):
                raise ValueError(
                    "Score invalide : " + feature
                )

    np = course.get("non_partants", [])

    if not isinstance(np, list):
        raise ValueError(
            "Liste des non-partants invalide"
        )

    np_numeros = set()

    for numero in np:
        if (
            type(numero) is not int
            or numero <= 0
        ):
            raise ValueError(
                "Numéro NP invalide"
            )

        if numero in np_numeros:
            raise ValueError(
                "Non-partant dupliqué"
            )

        np_numeros.add(numero)

    if not np_numeros.issubset(numeros):
        raise ValueError(
            "NP absent de la liste des chevaux"
        )

    return depart.astimezone(PARIS).date()


def ecriture_atomique(destination, donnees):
    destination = Path(destination)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporaire = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            suffix=".tmp",
            delete=False,
        ) as fichier:

            temporaire = Path(fichier.name)

            json.dump(
                donnees,
                fichier,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )

            fichier.write("\n")
            fichier.flush()
            os.fsync(fichier.fileno())

        os.replace(
            temporaire,
            destination
        )

    finally:
        if (
            temporaire is not None
            and temporaire.exists()
        ):
            temporaire.unlink()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/courses.json"),
    )

    parser.add_argument(
        "--date",
        default=dt.datetime.now(
            PARIS
        ).date().isoformat(),
    )

    args = parser.parse_args()

    try:
        date_cible = dt.date.fromisoformat(
            args.date
        )

        url = os.environ.get(
            "TURBOFUSION_COURSES_URL",
            ""
        ).strip()

        parsed = urllib.parse.urlparse(url)

        if (
            parsed.scheme != "https"
            or not parsed.hostname
        ):
            raise ValueError(
                "TURBOFUSION_COURSES_URL "
                "doit être une URL HTTPS"
            )

        requete = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "TURBOFUSION-3.0/1.0",
            },
        )

        with urllib.request.urlopen(
            requete,
            timeout=25,
        ) as reponse:

            if reponse.geturl().startswith(
                "https://"
            ) is False:
                raise ValueError(
                    "Redirection non HTTPS"
                )

            brut = reponse.read(
                MAX_BYTES + 1
            )

        if len(brut) > MAX_BYTES:
            raise ValueError(
                "Réponse trop volumineuse"
            )

        donnees = json.loads(brut)

        if (
            not isinstance(donnees, dict)
            or not isinstance(
                donnees.get("courses"),
                list
            )
        ):
            raise ValueError(
                "Format courses[] attendu"
            )

        courses = []
        identifiants = set()

        for course in donnees["courses"]:
            jour = valider(course)

            if jour != date_cible:
                continue

            identifiant = course["id"]

            if identifiant in identifiants:
                raise ValueError(
                    "Identifiant de course dupliqué"
                )

            identifiants.add(
                identifiant
            )

            courses.append(course)

        if not courses:
            print(
                "Aucune course valide "
                "pour la date demandée"
            )
            return 2

        publication = {
            "genere_a": dt.datetime.now(
                dt.timezone.utc
            ).isoformat(),
            "statut_collecte": "structure_validee",
            "courses": courses,
        }

        ecriture_atomique(
            args.output,
            publication
        )

        print(
            "COLLECTE TERMINÉE :",
            len(courses),
            "course(s)"
        )

        return 0

    except (
        ValueError,
        OSError,
        TypeError,
        TimeoutError,
        UnicodeError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as erreur:

        print(
            "ERREUR COLLECTE :",
            erreur
        )

        return 2


if __name__ == "__main__":
    raise SystemExit(main())
'''


# ============================================================
# TESTS AUTOMATISÉS
# ============================================================

TESTS = r'''
import unittest

from collect_courses import valider


class TestCollecteur(unittest.TestCase):

    def exemple(self):
        return {
            "id": "TEST-R1-C1",
            "source": "https://example.org/course",
            "pays": "FR",
            "depart": "2026-10-25T14:00:00+01:00",
            "partants": [
                {
                    "numero": 1,
                    "nom": "Cheval A",
                    "forme": 0.8,
                },
                {
                    "numero": 2,
                    "nom": "Cheval B",
                    "forme": 0.6,
                },
            ],
            "non_partants": [],
        }

    def test_valide(self):
        self.assertEqual(
            valider(self.exemple()).isoformat(),
            "2026-10-25",
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

        course["depart"] = (
            "2026-10-25T14:00:00"
        )

        with self.assertRaises(ValueError):
            valider(course)

    def test_pays_invalide(self):
        course = self.exemple()

        course["pays"] = "GB"

        with self.assertRaises(ValueError):
            valider(course)

    def test_np_invalide(self):
        course = self.exemple()

        course["non_partants"] = [99]

        with self.assertRaises(ValueError):
            valider(course)


if __name__ == "__main__":
    unittest.main()
'''


# ============================================================
# WORKFLOW GITHUB ACTIONS
# ============================================================

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
    name: Analyse M1-M5
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - name: Recuperer le depot
        uses: actions/checkout@v4

      - name: Installer Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Verifier les fichiers Python
        shell: bash
        run: |
          set -euo pipefail

          python -m py_compile \
            main.py \
            publish_data.py \
            collect_courses.py

          python -m unittest \
            discover -s tests -v

      - name: Verifier les cinq moteurs
        shell: bash
        run: |
          set -euo pipefail

          python - <<'PY'
          from main import WEIGHTS
          from publish_data import MOTEURS

          attendus = (
              "M1", "M2", "M3", "M4", "M5"
          )

          assert set(WEIGHTS) == set(attendus)
          assert set(MOTEURS) == set(attendus)

          for moteur in attendus:
              assert len(WEIGHTS[moteur]) == 7

          print("MOTEURS M1-M5 : OK")
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

      - name: Executer les cinq moteurs
        if: steps.collecte.outputs.disponible == 'true'
        shell: bash
        run: |
          set -euo pipefail

          python main.py \
            --figer \
            --strict-input \
            --safety-minutes 2

      - name: Verifier la publication
        if: steps.collecte.outputs.disponible == 'true'
        shell: bash
        run: |
          set -euo pipefail

          python - <<'PY'
          import json
          from pathlib import Path

          fichier = Path(
              "data/publication_latest.json"
          )

          if not fichier.is_file():
              raise SystemExit(
                  "Publication absente"
              )

          data = json.loads(
              fichier.read_text(
                  encoding="utf-8"
              )
          )

          if not isinstance(data, dict):
              raise SystemExit(
                  "Publication invalide"
              )

          courses = data.get("courses")

          if not isinstance(courses, list):
              raise SystemExit(
                  "Liste des courses invalide"
              )

          autorises = {
              "M1", "M2", "M3", "M4", "M5"
          }

          for course in courses:
              moteurs = course.get(
                  "moteurs", {}
              )

              if not isinstance(
                  moteurs, dict
              ):
                  raise SystemExit(
                      "Moteurs invalides"
                  )

              if not set(
                  moteurs
              ).issubset(autorises):
                  raise SystemExit(
                      "Moteur inconnu"
                  )

          print(
              "PUBLICATION STRUCTURELLEMENT VALIDE"
          )
          PY

      - name: Publier les donnees
        if: steps.collecte.outputs.disponible == 'true'
        shell: bash
        run: |
          set -euo pipefail

          git config user.name \
            "github-actions[bot]"

          git config user.email \
            "41898282+github-actions[bot]@users.noreply.github.com"

          git add -- data/

          if git diff --cached --quiet; then
            echo "Aucune modification"
            exit 0
          fi

          git commit -m \
            "Actualisation TURBOFUSION M1-M5"

          git push origin HEAD:main
'''


# ============================================================
# CONTRÔLES DE COMPATIBILITÉ
# ============================================================

def verifier_fichiers():
    essentiels = (
        "main.py",
        "publish_data.py",
        "index.html",
    )

    absents = [
        nom
        for nom in essentiels
        if not (ROOT / nom).is_file()
    ]

    if absents:
        raise SystemExit(
            "Installation annulée. "
            "Fichiers absents : "
            + ", ".join(absents)
        )


def verifier_python():
    for nom in (
        "main.py",
        "publish_data.py",
    ):
        chemin = ROOT / nom

        try:
            source = chemin.read_text(
                encoding="utf-8"
            )

            ast.parse(
                source,
                filename=str(chemin)
            )

        except (
            SyntaxError,
            UnicodeError,
            OSError,
        ) as erreur:
            raise SystemExit(
                "Fichier Python invalide : "
                + nom
                + " — "
                + str(erreur)
            )


def verifier_moteurs():
    """
    Vérification statique sans exécuter main.py.

    L'existence des constantes est contrôlée.
    La validation complète de leurs valeurs
    reste effectuée par GitHub Actions.
    """

    for nom, variable in (
        ("main.py", "WEIGHTS"),
        ("publish_data.py", "MOTEURS"),
    ):
        chemin = ROOT / nom

        arbre = ast.parse(
            chemin.read_text(
                encoding="utf-8"
            )
        )

        variables = set()

        for noeud in ast.walk(arbre):
            if isinstance(
                noeud,
                ast.Assign
            ):
                for cible in noeud.targets:
                    if isinstance(
                        cible,
                        ast.Name
                    ):
                        variables.add(
                            cible.id
                        )

            elif isinstance(
                noeud,
                ast.AnnAssign
            ):
                if isinstance(
                    noeud.target,
                    ast.Name
                ):
                    variables.add(
                        noeud.target.id
                    )

        if variable not in variables:
            print(
                "AVERTISSEMENT :",
                variable,
                "non trouvé dans",
                nom
            )

            print(
                "Vérifier la compatibilité "
                "avant activation."
            )


# ============================================================
# INSTALLATION PROTÉGÉE
# ============================================================

def installer(
    fichier,
    contenu,
    force=False,
):
    destination = ROOT / fichier

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    contenu = (
        textwrap.dedent(contenu).lstrip()
    )

    if destination.exists():
        if not force:
            print(
                "CONSERVÉ :",
                fichier,
                "(déjà présent)"
            )
            return False

        horodatage = (
            dt.datetime.now(
                dt.timezone.utc
            ).strftime(
                "%Y%m%dT%H%M%SZ"
            )
        )

        sauvegarde = destination.with_name(
            destination.name
            + ".bak-"
            + horodatage
        )

        shutil.copy2(
            destination,
      