#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🇸🇳🧠🔥 TURBOFUSION 3.0
COLLECTEUR PMU RENFORCÉ — M1 À M5

LA MAGIE DU SAVOIR

La mémoire conserve.
L'analyse comprend.
L'expérience enseigne.

Fonctions :
- Recherche des réunions PMU françaises du jour
- Collecte des courses et participants
- Identification des non-partants
- Récupération des informations sportives disponibles
- Étude préparatoire cheval par cheval
- Origines, jockeys, drivers, entraîneurs
- Équipement, ferrure et performances publiées
- Conservation des données sources
- Contrôle des doublons et erreurs
- Publication atomique de data/courses.json
- Diagnostic de couverture M1 à M5

IMPORTANT :
Les champs sportifs absents restent absents.
Aucun score, probabilité ou pronostic inventé.
Aucun pari réel exécuté.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

from pathlib import Path
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURATION
# ============================================================

PARIS = ZoneInfo("Europe/Paris")

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

OUTPUT_FILE = DATA_DIR / "courses.json"

DIAGNOSTIC_FILE = (
    DATA_DIR / "diagnostic_collecte.json"
)

BASE_URL = os.environ.get(
    "PMU_API_BASE",
    "https://online.turfinfo.api.pmu.fr/rest/client/61"
).rstrip("/")

TIMEOUT = 18
TENTATIVES = 3
PAUSE_REQUETES = 0.10

USER_AGENT = (
    "TURBOFUSION-3.0/"
    "collecteur-hippique"
)

# Valeurs descriptives disponibles dans
# certaines réponses PMU. Les noms des champs
# peuvent varier selon les disciplines et API.

CHAMPS_PERFORMANCES = (
    "musique",
    "performances",
    "performancesPassees",
    "historiquePerformances",
    "dernierePerformance",
    "nombreCourses",
    "nombreVictoires",
    "nombrePlaces",
    "gainsCarriere",
    "gains",
    "record",
    "reductionKilometrique",
    "handicapValeur",
    "valeurHandicap",
)

CHAMPS_ORIGINES = (
    "pere",
    "mere",
    "pereDeMere",
    "origine",
    "origines",
    "race",
    "studBook",
)

CHAMPS_ENTOURAGE = (
    "jockey",
    "driver",
    "entraineur",
    "proprietaire",
    "eleveur",
)

CHAMPS_EQUIPEMENT = (
    "ferrure",
    "deferre",
    "oeilleres",
    "equipement",
    "robe",
    "corde",
)

CHAMPS_CONDITIONS = (
    "distance",
    "discipline",
    "specialite",
    "terrain",
    "etatTerrain",
    "piste",
    "corde",
    "allocation",
    "montantPrix",
    "categorieParticularite",
    "conditions",
    "conditionsCourse",
)


# ============================================================
# OUTILS GÉNÉRAUX
# ============================================================

def maintenant():
    return dt.datetime.now(PARIS)


def texte(valeur):
    if valeur is None:
        return ""

    if isinstance(valeur, dict):
        for cle in (
            "libelleLong",
            "libelleCourt",
            "libelle",
            "nom",
            "name",
            "code",
        ):
            resultat = valeur.get(cle)
            if resultat is not None:
                return str(resultat).strip()

        return ""

    return str(valeur).strip()


def entier(valeur):
    if isinstance(valeur, bool):
        return None

    try:
        if valeur is None or valeur == "":
            return None

        return int(valeur)

    except (ValueError, TypeError):
        return None


def premier(objet, *cles):
    if not isinstance(objet, dict):
        return None

    for cle in cles:
        valeur = objet.get(cle)

        if valeur is not None and valeur != "":
            return valeur

    return None


def champs_disponibles(objet, champs):
    if not isinstance(objet, dict):
        return {}

    resultat = {}

    for champ in champs:
        if champ not in objet:
            continue

        valeur = objet[champ]

        if valeur is None or valeur == "":
            continue

        if isinstance(valeur, (list, dict)):
            if not valeur:
                continue

        resultat[champ] = valeur

    return resultat


def date_iso(valeur):
    if valeur is None:
        return None

    try:
        if isinstance(valeur, (int, float)):
            secondes = (
                valeur / 1000
                if valeur > 100000000000
                else valeur
            )

            instant = dt.datetime.fromtimestamp(
                secondes,
                tz=dt.timezone.utc,
            )

            return instant.isoformat()

        instant = dt.datetime.fromisoformat(
            str(valeur).replace(
                "Z",
                "+00:00",
            )
        )

        if instant.tzinfo is None:
            # Une date sans fuseau ne doit pas
            # être convertie silencieusement.
            return None

        return instant.astimezone(
            dt.timezone.utc
        ).isoformat()

    except (
        ValueError,
        TypeError,
        OverflowError,
        OSError,
    ):
        return None


def ecrire_json(chemin, donnees):
    chemin.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporaire = chemin.with_suffix(
        chemin.suffix + ".tmp"
    )

    temporaire.write_text(
        json.dumps(
            donnees,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )

    os.replace(
        temporaire,
        chemin,
    )


# ============================================================
# REQUÊTES HTTP
# ============================================================

def obtenir_json(url):
    derniere_erreur = None

    for tentative in range(TENTATIVES):
        try:
            requete = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
            )

            with urllib.request.urlopen(
                requete,
                timeout=TIMEOUT,
            ) as reponse:

                if reponse.status != 200:
                    raise RuntimeError(
                        f"HTTP {reponse.status}"
                    )

                return json.load(reponse)

        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            RuntimeError,
        ) as erreur:

            derniere_erreur = erreur

            if tentative < TENTATIVES - 1:
                time.sleep(
                    2 ** tentative
                )

    raise RuntimeError(
        f"Collecte impossible : "
        f"{url} — {derniere_erreur}"
    )


# ============================================================
# IDENTIFICATION DES NON-PARTANTS
# ============================================================

def est_non_partant(cheval):
    statut = texte(
        cheval.get("statut")
    ).upper()

    if cheval.get("nonPartant") is True:
        return True

    if cheval.get("estNonPartant") is True:
        return True

    return statut in (
        "NON_PARTANT",
        "NON PARTANT",
        "NP",
    )


# ============================================================
# EXTRACTION CHEVAL PAR CHEVAL
# ============================================================

def analyser_participant(brut, source):
    numero = entier(
        premier(
            brut,
            "numPmu",
            "numero",
        )
    )

    nom = texte(
        premier(
            brut,
            "nom",
            "nomCheval",
        )
    )

    if numero is None or numero <= 0:
        return None

    if not nom:
        return None

    performances = champs_disponibles(
        brut,
        CHAMPS_PERFORMANCES,
    )

    origines = champs_disponibles(
        brut,
        CHAMPS_ORIGINES,
    )

    entourage = champs_disponibles(
        brut,
        CHAMPS_ENTOURAGE,
    )

    equipement = champs_disponibles(
        brut,
        CHAMPS_EQUIPEMENT,
    )

    jockey = texte(
        premier(
            brut,
            "jockey",
            "driver",
        )
    )

    entraineur = texte(
        brut.get("entraineur")
    )

    proprietaire = texte(
        brut.get("proprietaire")
    )

    cheval = {
        "numero": numero,
        "nom": nom,

        "non_partant": est_non_partant(
            brut
        ),

        "age": entier(
            brut.get("age")
        ),

        "sexe": texte(
            brut.get("sexe")
        ),

        "jockey_nom": jockey,
        "entraineur_nom": entraineur,
        "proprietaire_nom": proprietaire,

        "performances": performances,
        "origines": origines,
        "entourage": entourage,
        "equipement": equipement,

        "source": source,

        "donnees_disponibles": {
            "performances": bool(
                performances
            ),
            "origines": bool(
                origines
            ),
            "entourage": bool(
                entourage
            ),
            "equipement": bool(
                equipement
            ),
        },
    }

    # Données descriptives directement
    # identifiables, sans calcul artificiel.

    musique = premier(
        brut,
        "musique",
    )

    if musique is not None:
        cheval["musique"] = musique

    gains = premier(
        brut,
        "gainsCarriere",
        "gains",
    )

    if gains is not None:
        cheval["gains"] = gains

    ferrure = premier(
        brut,
        "ferrure",
        "deferre",
    )

    if ferrure is not None:
        cheval["ferrure"] = ferrure

    pere = premier(
        brut,
        "pere",
    )

    mere = premier(
        brut,
        "mere",
    )

    if pere is not None:
        cheval["pere"] = texte(pere)

    if mere is not None:
        cheval["mere"] = texte(mere)

    # Les moteurs utilisent des critères
    # numériques normalisés entre 0 et 1.
    # Les données brutes ne sont PAS des scores.
    #
    # Aucun champ forme/regularite/etc.
    # n'est créé artificiellement.
    #
    # Un module d'analyse sportive validé
    # devra produire ces critères à partir
    # des données vérifiées.

    return cheval


# ============================================================
# COLLECTE DES PARTICIPANTS
# ============================================================

def collecter_participants(url):
    donnees = obtenir_json(url)

    if isinstance(donnees, list):
        participants = donnees

    elif isinstance(donnees, dict):
        participants = donnees.get(
            "participants"
        )

    else:
        participants = None

    if not isinstance(participants, list):
        raise ValueError(
            "Liste des participants indisponible"
        )

    chevaux = []
    numeros = set()

    for brut in participants:
        if not isinstance(brut, dict):
            continue

        cheval = analyser_participant(
            brut,
            url,
        )

        if cheval is None:
            continue

        numero = cheval["numero"]

        if numero in numeros:
            raise ValueError(
                f"Numéro de cheval en double : "
                f"{numero}"
            )

        numeros.add(numero)
        chevaux.append(cheval)

    chevaux.sort(
        key=lambda cheval: cheval["numero"]
    )

    return chevaux


# ============================================================
# DIAGNOSTIC DES INFORMATIONS
# ============================================================

def diagnostic_chevaux(chevaux):
    categories = (
        "performances",
        "origines",
        "entourage",
        "equipement",
    )

    bilan = {
        "chevaux": len(chevaux),
        "partants": sum(
            not cheval["non_partant"]
            for cheval in chevaux
        ),
        "non_partants": sum(
            cheval["non_partant"]
            for cheval in chevaux
        ),
    }

    for categorie in categories:
        bilan[categorie] = sum(
            bool(
                cheval[
                    "donnees_disponibles"
                ][categorie]
            )
            for cheval in chevaux
        )

    return bilan


# ============================================================
# COLLECTE DU PROGRAMME FRANÇAIS
# ============================================================

def collecter(date_cible=None):
    debut = maintenant()

    jour = (
        date_cible
        if date_cible is not None
        else debut.date()
    )

    date_pmu = jour.strftime(
        "%d%m%Y"
    )

    programme_url = (
        f"{BASE_URL}/programme/{date_pmu}"
    )

    programme = obtenir_json(
        programme_url
    )

    reunions = (
        programme.get("programme") or {}
    ).get("reunions") or []

    if not isinstance(reunions, list):
        raise RuntimeError(
            "Structure du programme invalide"
        )

    if not reunions:
        raise RuntimeError(
            "Programme PMU indisponible"
        )

    courses = []
    erreurs = []
    identifiants = set()

    for reunion in reunions:
        if not isinstance(reunion, dict):
            continue

        pays = texte(
            premier(
                reunion,
                "paysCode",
                "pays",
            )
        ).upper()

        if pays not in (
            "FR",
            "FRA",
            "FRANCE",
        ):
            continue

        reunion_numero = entier(
            reunion.get("numOfficiel")
        )

        if reunion_numero is None:
            continue

        hippodrome = texte(
            reunion.get("hippodrome")
        )

        courses_reunion = (
            reunion.get("courses") or []
        )

        for brut in courses_reunion:
            if not isinstance(brut, dict):
                continue

            course_numero = entier(
                brut.get("numOrdre")
            )

            depart = date_iso(
                premier(
                    brut,
                    "heureDepart",
                    "heureDepartPrevue",
                )
            )

            if course_numero is None:
                continue

            if depart is None:
                erreurs.append(
                    f"R{reunion_numero}"
                    f"C{course_numero}: "
                    "départ indisponible"
                )
                continue

            date_depart = (
                dt.datetime.fromisoformat(
                    depart
                ).astimezone(PARIS).date()
            )

            if date_depart != jour:
                continue

            identifiant = (
                f"{jour.isoformat()}"
                f"-R{reunion_numero}"
                f"-C{course_numero}"
            )

            if identifiant in identifiants:
                erreurs.append(
                    f"Course en double : "
                    f"{identifiant}"
                )
                continue

            identifiants.add(
                identifiant
            )

            participants_url = (
                f"{BASE_URL}/programme/"
                f"{date_pmu}/"
                f"R{reunion_numero}/"
                f"C{course_numero}/"
                f"participants"
            )

            chevaux = []
            collecte_statut = "ok"

            try:
                chevaux = collecter_participants(
                    participants_url
                )

                if not chevaux:
                    collecte_statut = (
                        "participants_vides"
                    )

            except (
                RuntimeError,
                ValueError,
            ) as erreur:

                collecte_statut = (
                    "indisponible"
                )

                erreurs.append(
                    f"{identifiant}: "
                    f"{erreur}"
                )

            conditions = champs_disponibles(
                brut,
                CHAMPS_CONDITIONS,
            )

            diagnostic = diagnostic_chevaux(
                chevaux
            )

            course = {
                "id": identifiant,

                "reunion": reunion_numero,
                "course": course_numero,

                "hippodrome": hippodrome,

                "nom": texte(
                    brut.get("libelle")
                ),

                "depart": depart,

                "distance_metres": entier(
                    brut.get("distance")
                ),

                "discipline": texte(
                    brut.get("discipline")
                ),

                "conditions": conditions,

                "source": participants_url,

                # Format attendu par main.py
                "partants": chevaux,

                "nombre_partants": diagnostic[
                    "partants"
                ],

                "nombre_non_partants": diagnostic[
                    "non_partants"
                ],

                "collecte_participants": (
                    collecte_statut
                ),

                "diagnostic": diagnostic,
            }

            courses.append(course)

            print(
                f"{identifiant} — "
                f"{hippodrome} — "
                f"{diagnostic['partants']} "
                f"partants — "
                f"{collecte_statut}"
            )

            time.sleep(
                PAUSE_REQUETES
            )

    if not courses:
        raise RuntimeError(
            "Aucune course française "
            "collectée pour cette date"
        )

    courses.sort(
        key=lambda course: (
            course["depart"],
            course["id"],
        )
    )

    # Vérification finale des identifiants
    # et des départs avant publication.

    for course in courses:
        if not course["id"]:
            raise ValueError(
                "Identifiant de course absent"
            )

        if not course["depart"]:
            raise ValueError(
                "Heure de départ absente"
            )

    total_chevaux = sum(
        len(course["partants"])
        for course in courses
    )

    total_partants = sum(
        course["nombre_partants"]
        for course in courses
    )

    total_np = sum(
        course["nombre_non_partants"]
        for course in courses
    )

    fin = maintenant()

    resultat = {
        "logiciel": "TURBOFUSION 3.0",

        "version_collecteur": "3.1",

        "date": jour.isoformat(),

        "collecte_a": fin.isoformat(),

        "source": programme_url,

        "statut_collecte": (
            "partielle"
            if erreurs
            else "ok"
        ),

        "erreurs_participants": erreurs,

        "courses": courses,
    }

    diagnostic_global = {
        "logiciel": "TURBOFUSION 3.0",

        "date": jour.isoformat(),

        "collecte_a": fin.isoformat(),

        "courses_collectees": len(
            courses
        ),

        "chevaux_recenses": total_chevaux,

        "partants": total_partants,

        "non_partants": total_np,

        "erreurs": erreurs,

        "couverture": {
            "performances": sum(
                course["diagnostic"][
                    "performances"
                ]
                for course in courses
            ),

            "origines": sum(
                course["diagnostic"][
                    "origines"
                ]
                for course in courses
            ),

            "entourage": sum(
                course["diagnostic"][
                    "entourage"
                ]
                for course in courses
            ),

            "equipement": sum(
                course["diagnostic"][
                    "equipement"
                ]
                for course in courses
            ),
        },

        "note": (
            "Les informations descriptives "
            "ne sont pas des scores sportifs. "
            "Les moteurs doivent s'abstenir "
            "si les critères calculés et "
            "validés sont absents."
        ),
    }

    ecrire_json(
        OUTPUT_FILE,
        resultat,
    )

    ecrire_json(
        DIAGNOSTIC_FILE,
        diagnostic_global,
    )

    print()
    print("=" * 60)
    print("🇸🇳🧠🔥 TURBOFUSION 3.0")
    print("COLLECTE PMU TERMINÉE")
    print("=" * 60)

    print(
        "Courses collectées :",
        len(courses),
    )

    print(
        "Chevaux recensés :",
        total_chevaux,
    )

    print(
        "Partants :",
        total_partants,
    )

    print(
        "Non-partants :",
        total_np,
    )

    print(
        "Erreurs de collecte :",
        len(erreurs),
    )

    print(
        "Publication :",
        OUTPUT_FILE,
    )

    print(
        "Diagnostic :",
        DIAGNOSTIC_FILE,
    )

    print("=" * 60)


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "TURBOFUSION 3.0 — "
            "Collecte hippique PMU renforcée"
        )
    )

    parser.add_argument(
        "--date",
        help="Date au format AAAA-MM-JJ",
    )

    arguments = parser.parse_args()

    date_cible = None

    if arguments.date:
        try:
            date_cible = dt.date.fromisoformat(
                arguments.date
            )

        except ValueError:
            parser.error(
                "Date invalide. "
                "Utiliser AAAA-MM-JJ."
            )

    collecter(date_cible)


if __name__ == "__main__":
    try:
        main()

    except (
        RuntimeError,
        ValueError,
        OSError,
        TypeError,
    ) as erreur:

        print(
            "ERREUR COLLECTE PMU :",
            erreur,
            file=sys.stderr,
        )

        sys.exit(1)
