#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🇸🇳🧠🔥 TURBOFUSION 3.0
INTELLIGENCE HIPPIQUE SPÉCIALISÉE — M1 À M5

LA MAGIE DU SAVOIR

La mémoire conserve.
L'analyse comprend.
L'expérience enseigne.
L'intelligence progresse.

M1 : Forme et régularité
M2 : Aptitudes et conditions
M3 : Origines et entourage
M4 : Classe et stratégie
M5 : Risques et fiabilité

Fonctionnement :
- Lecture des courses PMU collectées
- Contrôle des partants et non-partants
- Analyse indépendante M1 à M5
- Classement par ordre d'arrivée espéré
- Qualification des moteurs
- FIGÉS horodatés avant départ
- Empreintes SHA-256
- Conservation des historiques
- Publication du tableau officiel
- Diagnostic et contrôle des erreurs

Aucun score sportif inventé.
Aucun pari réel exécuté.
Aucune garantie de gain.
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys

from pathlib import Path
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURATION
# ============================================================

PARIS = ZoneInfo("Europe/Paris")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

COURSES_FILE = DATA_DIR / "courses.json"
PUBLICATION_FILE = DATA_DIR / "publication_latest.json"
FIGES_DIR = DATA_DIR / "figes"

MOTEURS = {
    "M1": {
        "specialite": "Forme et régularité",
        "criteres": (
            "forme",
            "regularite",
        ),
    },
    "M2": {
        "specialite": "Aptitudes et conditions",
        "criteres": (
            "aptitude",
            "conditions",
        ),
    },
    "M3": {
        "specialite": "Origines et entourage",
        "criteres": (
            "origines",
            "entourage",
        ),
    },
    "M4": {
        "specialite": "Classe et stratégie",
        "criteres": (
            "classe",
            "strategie",
        ),
    },
    "M5": {
        "specialite": "Risques et fiabilité",
        "criteres": (
            "fiabilite",
            "regularite",
        ),
    },
}


# ============================================================
# OUTILS
# ============================================================

def maintenant_paris():
    return dt.datetime.now(PARIS)


def lire_json(chemin):
    with chemin.open(
        "r",
        encoding="utf-8",
    ) as fichier:
        return json.load(fichier)


def ecrire_json(chemin, donnees):
    chemin.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporaire = chemin.with_suffix(
        chemin.suffix + ".tmp"
    )

    contenu = json.dumps(
        donnees,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ) + "\n"

    temporaire.write_text(
        contenu,
        encoding="utf-8",
    )

    os.replace(temporaire, chemin)


def analyser_date(valeur):
    date = dt.datetime.fromisoformat(
        str(valeur).replace("Z", "+00:00")
    )

    if date.tzinfo is None:
        raise ValueError(
            "Date sans fuseau horaire"
        )

    return date


def valeur_sportive(cheval, critere):
    valeur = cheval.get(critere)

    if type(valeur) not in (int, float):
        return None

    valeur = float(valeur)

    if not math.isfinite(valeur):
        return None

    if not 0 <= valeur <= 1:
        return None

    return valeur


# ============================================================
# ANALYSE INDÉPENDANTE DES MOTEURS
# ============================================================

def analyser_moteur(
    nom_moteur,
    chevaux,
    heure_analyse,
    heure_depart,
):

    configuration = MOTEURS[nom_moteur]

    criteres = configuration["criteres"]

    classement = []

    for cheval in chevaux:

        if cheval.get("non_partant"):
            continue

        numero = cheval.get("numero")
        nom = cheval.get("nom")

        if numero is None or not nom:
            continue

        valeurs = []

        for critere in criteres:

            valeur = valeur_sportive(
                cheval,
                critere,
            )

            if valeur is not None:
                valeurs.append(valeur)

        couverture = (
            len(valeurs) / len(criteres)
        )

        score = None

        if valeurs:
            score = sum(valeurs) / len(valeurs)

        classement.append({
            "numero": int(numero),
            "nom": str(nom),
            "score": (
                round(score, 4)
                if score is not None
                else None
            ),
            "couverture": round(
                couverture,
                3,
            ),
        })

    donnees_completes = (
        len(classement) >= 2
        and all(
            cheval["score"] is not None
            and cheval["couverture"] == 1
            for cheval in classement
        )
    )

    if donnees_completes:

        classement.sort(
            key=lambda cheval: (
                -cheval["score"],
                cheval["numero"],
            )
        )

    else:

        classement.sort(
            key=lambda cheval: cheval["numero"]
        )

    eligible = False

    if (
        donnees_completes
        and heure_analyse < heure_depart
    ):

        premier = classement[0]
        deuxieme = classement[1]

        eligible = (
            premier["score"]
            > deuxieme["score"]
        )

    ordre = []

    if eligible:

        ordre = [
            cheval["numero"]
            for cheval in classement[:5]
        ]

    if eligible:
        motif = "Critères sportifs vérifiés"

    elif heure_analyse >= heure_depart:
        motif = "Départ atteint ou dépassé"

    else:
        motif = (
            "Données sportives insuffisantes "
            "ou non discriminantes"
        )

    return {
        "moteur": nom_moteur,

        "specialite": configuration[
            "specialite"
        ],

        "classement": classement[:5],

        "ordre_arrivee_espere": ordre,

        "gagnant_espere": (
            ordre[0] if eligible else None
        ),

        "place_espere": (
            ordre[1] if eligible else None
        ),

        "qualification": (
            "candidate"
            if eligible
            else "abstention"
        ),

        "motif": motif,

        "pari": "Aucun pari proposé",

        "couverture": min(
            (
                cheval["couverture"]
                for cheval in classement
            ),
            default=0,
        ),
    }


# ============================================================
# FIGÉS IMMUTABLES
# ============================================================

def enregistrer_fige(
    course,
    moteurs,
    heure_analyse,
):

    FIGES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    identifiant = course["id"]

    chemin = FIGES_DIR / (
        identifiant + ".json"
    )

    instantane = {
        "logiciel": "TURBOFUSION 3.0",
        "course_id": identifiant,
        "depart": course["depart"],
        "fige_a": heure_analyse.isoformat(),
        "moteurs": moteurs,
        "source": course.get("source"),
    }

    contenu = (
        json.dumps(
            instantane,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"
    ).encode("utf-8")

    # Le mode xb interdit l'écrasement
    # d'un FIGÉ déjà enregistré.

    try:

        with chemin.open("xb") as fichier:
            fichier.write(contenu)

    except FileExistsError:
        pass

    empreinte = hashlib.sha256(
        chemin.read_bytes()
    ).hexdigest()

    return {
        "fichier_fige": chemin.relative_to(
            BASE_DIR
        ).as_posix(),
        "sha256": empreinte,
    }


# ============================================================
# TRAITEMENT DES COURSES
# ============================================================

def traiter_courses(arguments):

    heure_analyse = maintenant_paris()

    if not COURSES_FILE.is_file():

        raise RuntimeError(
            "Fichier data/courses.json absent. "
            "Exécuter collecte_pmu.py."
        )

    donnees = lire_json(COURSES_FILE)

    courses = donnees.get("courses")

    if not isinstance(courses, list):
        raise ValueError(
            "Format des courses invalide"
        )

    publications = []

    for course in courses:

        heure_depart = analyser_date(
            course["depart"]
        )

        chevaux = course.get(
            "partants",
            [],
        )

        if not isinstance(chevaux, list):
            chevaux = []

        if arguments.strict_input and not chevaux:
            continue

        analyses = {}

        for nom_moteur in MOTEURS:

            analyses[nom_moteur] = analyser_moteur(
                nom_moteur,
                chevaux,
                heure_analyse,
                heure_depart,
            )

        qualifies = [
            nom
            for nom, analyse in analyses.items()
            if analyse["qualification"]
            == "candidate"
        ]

        partants = sum(
            not cheval.get("non_partant", False)
            for cheval in chevaux
        )

        non_partants = sum(
            bool(cheval.get("non_partant", False))
            for cheval in chevaux
        )

        publication = {
            "id": course["id"],

            "hippodrome": course.get(
                "hippodrome",
                "",
            ),

            "depart": course["depart"],

            "partants": partants,

            "non_partants": non_partants,

            "source": course.get("source"),

            "analyse_a": (
                heure_analyse.isoformat()
            ),

            "moteurs": analyses,

            "moteurs_qualifies": qualifies,

            "statut": "analyse_provisoire",
        }

        limite_fige = (
            heure_depart
            - dt.timedelta(
                minutes=arguments.safety_minutes
            )
        )

        chemin_fige = FIGES_DIR / (
            course["id"] + ".json"
        )

        if chemin_fige.exists():

            publication["statut"] = (
                "fige_existant"
            )

            publication["fichier_fige"] = (
                chemin_fige.relative_to(
                    BASE_DIR
                ).as_posix()
            )

            publication["sha256"] = (
                hashlib.sha256(
                    chemin_fige.read_bytes()
                ).hexdigest()
            )

        elif (
            arguments.figer
            and qualifies
            and heure_analyse < limite_fige
        ):

            preuve = enregistrer_fige(
                course,
                analyses,
                heure_analyse,
            )

            publication.update(preuve)

            publication["statut"] = "fige"

        publications.append(publication)

    resultat = {
        "logiciel": "TURBOFUSION 3.0",

        "date": (
            heure_analyse.date().isoformat()
        ),

        "genere_a": (
            heure_analyse.isoformat()
        ),

        "statut_collecte": "ok",

        "moteurs": list(MOTEURS),

        "courses": publications,

        "avertissements": [
            "Aucun score sportif inventé.",
            "Les analyses provisoires ne sont pas des FIGÉS.",
            "Aucun pari réel exécuté.",
            "Aucune garantie de gain.",
        ],
    }

    ecrire_json(
        PUBLICATION_FILE,
        resultat,
    )

    print(
        "TURBOFUSION 3.0 : "
        f"{len(publications)} courses publiées."
    )

    print(
        "Courses avec moteur qualifié :",
        sum(
            bool(course["moteurs_qualifies"])
            for course in publications
        ),
    )


# ============================================================
# DIAGNOSTIC
# ============================================================

def diagnostic():

    print("=" * 55)
    print("🇸🇳🧠🔥 TURBOFUSION 3.0")
    print("DIAGNOSTIC DES MOTEURS")
    print("=" * 55)

    print(
        "Heure Paris :",
        maintenant_paris().isoformat(),
    )

    for nom, configuration in MOTEURS.items():

        print(
            nom,
            "—",
            configuration["specialite"],
        )

    print(
        "Collecte présente :",
        COURSES_FILE.is_file(),
    )

    print(
        "Publication présente :",
        PUBLICATION_FILE.is_file(),
    )

    print(
        "Répertoire FIGÉS présent :",
        FIGES_DIR.is_dir(),
    )

    print(
        "Diagnostic structurel terminé."
    )


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "TURBOFUSION 3.0 "
            "Intelligence hippique M1 à M5"
        )
    )

    parser.add_argument(
        "--diagnostic",
        action="store_true",
    )

    parser.add_argument(
        "--figer",
        action="store_true",
    )

    parser.add_argument(
        "--strict-input",
        action="store_true",
    )

    parser.add_argument(
        "--safety-minutes",
        type=int,
        default=2,
    )

    arguments = parser.parse_args()

    if arguments.safety_minutes < 0:
        parser.error(
            "Délai de sécurité invalide"
        )

    if arguments.diagnostic:
        diagnostic()
        return

    traiter_courses(arguments)


if __name__ == "__main__":

    try:
        main()

    except (
        RuntimeError,
        ValueError,
        OSError,
        KeyError,
        TypeError,
    ) as erreur:

        print(
            "ERREUR TURBOFUSION :",
            erreur,
            file=sys.stderr,
        )

        sys.exit(1)
        
