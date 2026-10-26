#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""TURBOFUSION 3.0 — Validation sécurisée des courses PMU.

Entrée : data/courses_source.json
Sortie : data/courses.json

Courses françaises du jour uniquement.
Aucune connexion réseau, aucun pronostic inventé.
Aucun FIGÉ créé par ce programme.
"""

import json
import os
import re
import sys
import tempfile

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SOURCE = DATA / "courses_source.json"
DEST = DATA / "courses.json"
PARIS = ZoneInfo("Europe/Paris")

CHAMPS_OBLIGATOIRES = (
    "id",
    "hippodrome",
    "depart",
    "source",
    "pays",
    "partants",
)


def sans_doublons(paires):
    resultat = {}
    for cle, valeur in paires:
        if cle in resultat:
            raise ValueError(
                f"Clé JSON dupliquée : {cle}"
            )
        resultat[cle] = valeur
    return resultat


def refuser_constante(valeur):
    raise ValueError(
        f"Constante JSON interdite : {valeur}"
    )


def lire_json(chemin):
    return json.loads(
        chemin.read_text(encoding="utf-8-sig"),
        object_pairs_hook=sans_doublons,
        parse_constant=refuser_constante,
    )


def texte_valide(valeur):
    return (
        isinstance(valeur, str)
        and bool(valeur.strip())
    )


def verifier_url(adresse):
    if not texte_valide(adresse):
        raise ValueError("URL source absente")

    if adresse != adresse.strip():
        raise ValueError("URL source mal formée")

    url = urlparse(adresse)

    try:
        _ = url.port
    except ValueError as erreur:
        raise ValueError(
            "Port de l'URL invalide"
        ) from erreur

    if (
        url.scheme.lower() != "https"
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.fragment
        or any(c.isspace() for c in adresse)
    ):
        raise ValueError(
            "URL source HTTPS invalide"
        )


def verifier_date(valeur):
    if not texte_valide(valeur):
        raise ValueError("Date absente")

    try:
        depart = datetime.fromisoformat(
            valeur.replace("Z", "+00:00")
        )
    except ValueError as erreur:
        raise ValueError(
            f"Date ISO invalide : {valeur}"
        ) from erreur

    if (
        depart.tzinfo is None
        or depart.utcoffset() is None
    ):
        raise ValueError(
            "Fuseau horaire obligatoire"
        )

    return depart.astimezone(PARIS)


def verifier_chevaux(course):
    chevaux = course["partants"]

    if (
        not isinstance(chevaux, list)
        or len(chevaux) < 2
    ):
        raise ValueError(
            "Liste de partants insuffisante"
        )

    numeros = set()
    np_individuels = set()

    for cheval in chevaux:
        if not isinstance(cheval, dict):
            raise ValueError(
                "Cheval non représenté par un objet"
            )

        numero = cheval.get("numero")
        nom = cheval.get("nom")

        if (
            type(numero) is not int
            or numero <= 0
        ):
            raise ValueError(
                "Numéro de cheval invalide"
            )

        if not texte_valide(nom):
            raise ValueError(
                f"Nom absent pour le numéro {numero}"
            )

        if numero in numeros:
            raise ValueError(
                f"Numéro dupliqué : {numero}"
            )

        numeros.add(numero)

        statut_np = cheval.get(
            "non_partant", False
        )

        if type(statut_np) is not bool:
            raise ValueError(
                f"Statut NP invalide : {numero}"
            )

        if statut_np:
            np_individuels.add(numero)

    non_partants = course.get(
        "non_partants", []
    )

    if not isinstance(non_partants, list):
        raise ValueError(
            "Liste des non-partants invalide"
        )

    np_declares = set()

    for numero in non_partants:
        if (
            type(numero) is not int
            or numero <= 0
            or numero not in numeros
            or numero in np_declares
        ):
            raise ValueError(
                f"Non-partant incohérent : {numero}"
            )

        np_declares.add(numero)

    tous_np = np_declares | np_individuels

    if len(numeros - tous_np) < 2:
        raise ValueError(
            "Moins de deux chevaux encore partants"
        )

    # Harmoniser les deux formes de déclaration NP.
    course["non_partants"] = sorted(tous_np)

    return True


def verifier_course(course):
    if not isinstance(course, dict):
        raise ValueError(
            "Course non représentée par un objet"
        )

    for champ in CHAMPS_OBLIGATOIRES:
        if champ not in course:
            raise ValueError(
                f"Champ obligatoire absent : {champ}"
            )

    identifiant = course["id"]

    if (
        not texte_valide(identifiant)
        or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,80}",
            identifiant,
        )
    ):
        raise ValueError(
            "Identifiant de course invalide"
        )

    if not texte_valide(course["hippodrome"]):
        raise ValueError(
            "Hippodrome invalide"
        )

    pays = course["pays"]

    if (
        not texte_valide(pays)
        or pays.strip().upper()
        not in ("FR", "FRANCE")
    ):
        raise ValueError(
            "Course hors de France ou pays non confirmé"
        )

    verifier_url(course["source"])
    depart = verifier_date(course["depart"])
    verifier_chevaux(course)

    return depart


def ecriture_atomique(chemin, donnees):
    chemin.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporaire = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=chemin.parent,
            prefix=".courses_",
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

        temporaire.replace(chemin)

    finally:
        if temporaire is not None:
            temporaire.unlink(
                missing_ok=True
            )


def main():
    print("=" * 55)
    print("TURBOFUSION 3.0")
    print("VALIDATION DES DONNÉES PMU")
    print("=" * 55)

    maintenant = datetime.now(PARIS)
    aujourd_hui = maintenant.date()

    print(
        "Heure Paris :",
        maintenant.isoformat(
            timespec="seconds"
        ),
    )

    if not SOURCE.is_file():
        print(
            "COLLECTE NON CONNECTÉE : "
            "data/courses_source.json absent.",
            file=sys.stderr,
        )
        print(
            "Aucune donnée publiée. "
            "Aucun nouveau FIGÉ autorisé.",
            file=sys.stderr,
        )
        return 2

    donnees = lire_json(SOURCE)

    if (
        not isinstance(donnees, dict)
        or not isinstance(
            donnees.get("courses"), list
        )
    ):
        raise ValueError(
            'Format attendu : {"courses": [...]}'
        )

    identifiants = set()
    courses_du_jour = []
    ignorees = 0

    for course in donnees["courses"]:
        depart = verifier_course(course)
        identifiant = course["id"]

        if identifiant in identifiants:
            raise ValueError(
                "Identifiant de course dupliqué : "
                + identifiant
            )

        identifiants.add(identifiant)

        if depart.date() != aujourd_hui:
            ignorees += 1
            continue

        courses_du_jour.append(
            (depart, course)
        )

    courses_du_jour.sort(
        key=lambda element: (
            element[0],
            element[1]["id"],
        )
    )

    if not courses_du_jour:
        print(
            "ATTENTION : aucune course française "
            "du jour dans le fichier source.",
            file=sys.stderr,
        )
        print(
            "Publication suspendue. "
            "Aucun nouveau FIGÉ autorisé.",
            file=sys.stderr,
        )
        return 3

    sortie = {
        "courses": [
            course
            for _, course in courses_du_jour
        ]
    }

    ecriture_atomique(DEST, sortie)

    print(
        f"Courses validées : "
        f"{len(courses_du_jour)}"
    )

    print(
        f"Courses hors date : {ignorees}"
    )

    print(
        f"Date Paris : {aujourd_hui}"
    )

    print(
        "Fichier publié : "
        "data/courses.json"
    )

    print(
        "ATTENTION : la provenance des données "
        "n'a pas été vérifiée indépendamment."
    )

    print(
        "VALIDATION LOCALE TERMINÉE"
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
        json.JSONDecodeError,
    ) as erreur:
        print(
            "ERREUR COLLECTE :",
            erreur,
            file=sys.stderr,
        )
        sys.exit(1)
        
