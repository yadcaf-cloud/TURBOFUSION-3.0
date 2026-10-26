#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""TURBOFUSION 3.0 — Tests automatisés M1 à M5.

Tests exclusivement réalisés sur des courses fictives.
Aucun résultat PMU réel ni pari n'est créé.
"""

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

MAIN = Path(__file__).resolve().with_name("main.py")
PARIS = ZoneInfo("Europe/Paris")

CRITERES = (
    "forme",
    "regularite",
    "aptitude",
    "distance",
    "terrain",
    "origines",
    "jockey",
    "entraineur",
    "classe",
    "strategie",
    "fiabilite",
)


class TestTurbofusion(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir(parents=True, exist_ok=True)

        if not MAIN.is_file():
            self.fail("main.py est introuvable")

        (self.root / "main.py").write_bytes(MAIN.read_bytes())

        self.depart = (
            dt.datetime.now(PARIS) + dt.timedelta(hours=2)
        ).isoformat()

    def cheval(self, numero, valeur=None):
        cheval = {
            "numero": numero,
            "nom": f"Cheval fictif {numero}",
        }

        if valeur is not None:
            for critere in CRITERES:
                cheval[critere] = valeur

        return cheval

    def write_course(
        self,
        horses,
        pays="FR",
        non_partants=None,
        depart=None,
    ):
        course = {
            "id": "TEST-SYNTHETIQUE",
            "hippodrome": "Hippodrome fictif de test",
            "pays": pays,
            "depart": depart or self.depart,
            "source": "https://example.org/test-only",
            "non_partants": (
                non_partants if non_partants is not None else []
            ),
            "partants": horses,
        }

        fichier = self.data / "courses.json"
        fichier.write_text(
            json.dumps(
                {"courses": [course]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def run_main(self, *arguments):
        return subprocess.run(
            [sys.executable, "main.py", *arguments],
            cwd=self.root,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def publication(self):
        fichier = self.data / "publication_latest.json"
        self.assertTrue(
            fichier.is_file(),
            "Publication JSON absente",
        )
        return json.loads(fichier.read_text(encoding="utf-8"))

    def test_diagnostic(self):
        resultat = self.run_main("--diagnostic")

        self.assertEqual(
            resultat.returncode,
            0,
            resultat.stderr,
        )

        for moteur in ("M1", "M2", "M3", "M4", "M5"):
            self.assertIn(moteur, resultat.stdout)

    def test_no_data_no_fige(self):
        self.write_course([
            self.cheval(1),
            self.cheval(2),
        ])

        resultat = self.run_main("--figer", "--strict-input")

        self.assertEqual(
            resultat.returncode,
            0,
            resultat.stderr,
        )

        courses = self.publication()["courses"]
        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["statut"], "non_valide")

        archives = list(self.data.rglob("*.pv.json"))
        self.assertEqual(archives, [])

    def test_pv_fige_immutable(self):
        self.write_course([
            self.cheval(1, 0.90),
            self.cheval(2, 0.40),
        ])

        resultat = self.run_main("--figer", "--strict-input")

        self.assertEqual(
            resultat.returncode,
            0,
            resultat.stderr,
        )

        archives = self.data / "figes"
        self.assertTrue(archives.is_dir())

        figes = list(archives.glob("*.json"))
        self.assertTrue(figes, "Aucune archive créée")

        contenu_initial = {
            fichier.name: fichier.read_bytes()
            for fichier in figes
        }

        resultat = self.run_main("--figer", "--strict-input")

        self.assertEqual(
            resultat.returncode,
            0,
            resultat.stderr,
        )

        for nom, contenu in contenu_initial.items():
            fichier = archives / nom
            self.assertTrue(fichier.exists())
            self.assertEqual(fichier.read_bytes(), contenu)

        course = self.publication()["courses"][0]
        self.assertEqual(course["statut"], "fige")

        preuve = course.get("preuve_fige", {})
        self.assertTrue(preuve.get("pv_verifie"))

    def test_reject_wrong_country(self):
        self.write_course(
            [
                self.cheval(1),
                self.cheval(2),
            ],
            pays="GB",
        )

        resultat = self.run_main("--strict-input")
        self.assertNotEqual(resultat.returncode, 0)

    def test_reject_duplicate_numbers(self):
        self.write_course([
            self.cheval(1),
            self.cheval(1),
        ])

        resultat = self.run_main("--strict-input")
        self.assertNotEqual(resultat.returncode, 0)

    def test_non_partant_excluded(self):
        self.write_course(
            [
                self.cheval(1, 0.90),
                self.cheval(2, 0.70),
                self.cheval(3, 0.40),
            ],
            non_partants=[2],
        )

        resultat = self.run_main("--figer", "--strict-input")

        self.assertEqual(
            resultat.returncode,
            0,
            resultat.stderr,
        )

        course = self.publication()["courses"][0]
        self.assertEqual(course["partants"], 2)
        self.assertIn(2, course["non_partants"])

        for analyse in course["moteurs"].values():
            self.assertNotIn(
                2,
                analyse.get("ordre_arrivee_espere", []),
            )

    def test_no_retroactive_fige(self):
        depart_passe = (
            dt.datetime.now(PARIS) - dt.timedelta(minutes=30)
        ).isoformat()

        self.write_course(
            [
                self.cheval(1, 0.90),
                self.cheval(2, 0.40),
            ],
            depart=depart_passe,
        )

        resultat = self.run_main("--figer", "--strict-input")

        self.assertEqual(
            resultat.returncode,
            0,
            resultat.stderr,
        )

        archives = self.data / "figes"

        if archives.exists():
            self.assertEqual(
                list(archives.rglob("*.json")),
                [],
                "Un FIGÉ rétroactif a été créé",
            )

        course = self.publication()["courses"][0]
        self.assertNotEqual(course["statut"], "fige")


if __name__ == "__main__":
    unittest.main(verbosity=2)
