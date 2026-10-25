#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TURBOFUSION 3.0 — Publication officielle M1 à M5.

Lit data/audit_latest.json.
Produit data/publication_latest.json.

Ne crée aucun pronostic absent.
Ne modifie aucun fichier FIGÉ historique.
Conserve les cinq moteurs indépendants.
"""

import json
import math
import os
import sys
import tempfile
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
MOTEURS = ("M1", "M2", "M3", "M4", "M5")


def _constante_invalide(valeur):
    raise ValueError(
        f"Constante JSON interdite : {valeur}"
    )


def _sans_doublons(paires):
    resultat = {}
    for cle, valeur in paires:
        if cle in resultat:
            raise ValueError(
                f"Cle JSON en double : {cle}"
            )
        resultat[cle] = valeur
    return resultat


def _verifier_json(valeur):
    if valeur is None or isinstance(
        valeur, (str, bool, int)
    ):
        return

    if isinstance(valeur, float):
        if not math.isfinite(valeur):
            raise ValueError(
                "Nombre JSON non fini"
            )
        return

    if isinstance(valeur, list):
        for element in valeur:
            _verifier_json(element)
        return

    if isinstance(valeur, dict):
        for cle, element in valeur.items():
            if not isinstance(cle, str):
                raise ValueError(
                    "Cle JSON non textuelle"
                )
            _verifier_json(element)
        return

    raise ValueError(
        f"Type JSON invalide : {type(valeur).__name__}"
    )


def _moteurs_valides(valeur):
    if valeur is None:
        return {}

    if not isinstance(valeur, dict):
        raise ValueError(
            "Les moteurs doivent etre un objet JSON"
        )

    inconnus = set(valeur) - set(MOTEURS)

    if inconnus:
        raise ValueError(
            f"Moteurs inconnus : {sorted(inconnus)}"
        )

    resultat = {}

    for nom in MOTEURS:
        if nom not in valeur:
            continue

        moteur = valeur[nom]

        if not isinstance(moteur, dict):
            raise ValueError(
                f"Moteur {nom} invalide"
            )

        if moteur.get("moteur", nom) != nom:
            raise ValueError(
                f"Identite incoherente : {nom}"
            )

        resultat[nom] = moteur

    return resultat


def publish(data_dir=DATA_DIR):
    """
    Publie les audits valides.

    Retourne le chemin du fichier cree,
    ou None si la publication echoue.
    """
    data_dir = Path(data_dir)

    source = data_dir / "audit_latest.json"
    cible = data_dir / "publication_latest.json"

    temporaire = None

    try:
        if not source.is_file():
            raise FileNotFoundError(
                f"Audit introuvable : {source}"
            )

        with source.open(
            "r",
            encoding="utf-8",
        ) as fichier:
            audit = json.load(
                fichier,
                parse_constant=_constante_invalide,
                object_pairs_hook=_sans_doublons,
            )

        if not isinstance(audit, dict):
            raise ValueError(
                "Audit JSON invalide"
            )

        _verifier_json(audit)

        courses_source = audit.get("courses")

        if not isinstance(courses_source, list):
            raise ValueError(
                "Liste des courses invalide"
            )

        courses = []
        identifiants = set()

        for index, course in enumerate(
            courses_source, start=1
        ):
            if not isinstance(course, dict):
                raise ValueError(
                    f"Course {index} invalide"
                )

            identifiant = course.get("id")

            if not isinstance(identifiant, str):
                raise ValueError(
                    f"Course {index} sans identifiant"
                )

            identifiant = identifiant.strip()

            if not identifiant:
                raise ValueError(
                    f"Course {index} sans identifiant"
                )

            if identifiant in identifiants:
                raise ValueError(
                    f"Course en double : {identifiant}"
                )

            identifiants.add(identifiant)

            statut = course.get("statut")

            if statut is not None and not isinstance(
                statut, str
            ):
                raise ValueError(
                    f"Statut invalide : {identifiant}"
                )

            moteurs = _moteurs_valides(
                course.get("moteurs")
            )

            entree = dict(course)
            entree["id"] = identifiant
            entree["moteurs"] = moteurs

            # La publication reproduit le statut
            # sans prétendre authentifier le FIGÉ.
            courses.append(entree)

        publication = {
            "logiciel": "TURBOFUSION 3.0",
            "date": audit.get("date"),
            "genere_a": audit.get("genere_a"),
            "statut_collecte": audit.get(
                "statut_collecte"
            ),
            "moteurs": list(MOTEURS),
            "courses": courses,
            "avertissements": [
                "Les analyses provisoires ne sont pas des FIGES.",
                "Les fichiers FIGES historiques restent inchanges.",
                "La publication ne certifie pas les FIGES.",
                "Aucun pronostic absent n'est invente.",
                "Aucune garantie de gain.",
            ],
        }

        contenu = json.dumps(
            publication,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n"

        data_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=data_dir,
            prefix=".publication_",
            suffix=".tmp",
            delete=False,
        ) as fichier:
            temporaire = Path(fichier.name)
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())

        os.replace(temporaire, cible)
        temporaire = None

        print(
            f"TURBOFUSION 3.0 : "
            f"{len(courses)} course(s) publiee(s)."
        )
        print(f"Publication : {cible}")

        return cible

    except (
        OSError,
        ValueError,
        TypeError,
    ) as erreur:
        print(
            f"ERREUR PUBLICATION : {erreur}",
            file=sys.stderr,
        )
        return None

    finally:
        if temporaire is not None:
            temporaire.unlink(missing_ok=True)


# Compatibilite avec les anciens appels.
publier = publish


if __name__ == "__main__":
    if publish() is None:
        raise SystemExit(1)
        
