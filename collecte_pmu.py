#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 3.0 — validation locale des données PMU.

Entrée : data/courses_source.json (alimentée par un collecteur indépendant)
Sortie : data/courses.json (uniquement les courses du jour, heure de Paris)
Aucune connexion réseau ni vérification indépendante de la source.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "courses_source.json"
DEST = ROOT / "data" / "courses.json"
PARIS = ZoneInfo("Europe/Paris")


def sans_doublons(paires):
    resultat = {}
    for cle, valeur in paires:
        if cle in resultat:
            raise ValueError(f"Clé JSON dupliquée : {cle}")
        resultat[cle] = valeur
    return resultat


def verifier(course):
    if not isinstance(course, dict):
        raise ValueError("Course non représentée par un objet JSON")
    for champ in ("id", "hippodrome", "depart", "source", "partants"):
        if champ not in course:
            raise ValueError(f"Champ manquant : {champ}")
    for champ in ("id", "hippodrome", "depart", "source"):
        if not isinstance(course[champ], str) or not course[champ].strip():
            raise ValueError(f"Champ invalide : {champ}")
    try:
        depart = datetime.fromisoformat(course["depart"].replace("Z", "+00:00"))
    except ValueError as erreur:
        raise ValueError(f"Date de départ invalide : {course['id']}") from erreur
    if depart.tzinfo is None or depart.utcoffset() is None:
        raise ValueError("Départ sans fuseau horaire")
    url = urlparse(course["source"])
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("URL source HTTPS invalide")
    if not isinstance(course.get("pays"), str) or course["pays"].strip().upper() not in ("FR", "FRANCE"):
        raise ValueError("Pays français non confirmé")
    chevaux = course["partants"]
    if not isinstance(chevaux, list) or len(chevaux) < 2:
        raise ValueError("Liste des partants absente ou insuffisante")
    numeros = []
    for cheval in chevaux:
        if not isinstance(cheval, dict):
            raise ValueError("Cheval invalide")
        numero = cheval.get("numero")
        if type(numero) is not int or numero <= 0:
            raise ValueError("Numéro de cheval invalide")
        if not isinstance(cheval.get("nom"), str) or not cheval["nom"].strip():
            raise ValueError("Nom de cheval absent")
        numeros.append(numero)
    if len(set(numeros)) != len(numeros):
        raise ValueError("Numéros de chevaux dupliqués")
    np = course.get("non_partants", [])
    if (not isinstance(np, list) or any(type(n) is not int or n <= 0 for n in np)
            or len(set(np)) != len(np) or not set(np).issubset(numeros)):
        raise ValueError("Non-partants incohérents")
    return depart


def main():
    if not SOURCE.is_file():
        print("COLLECTE NON CONNECTÉE : data/courses_source.json absent.", file=sys.stderr)
        return 2
    donnees = json.loads(SOURCE.read_text(encoding="utf-8-sig"), object_pairs_hook=sans_doublons)
    if not isinstance(donnees, dict) or not isinstance(donnees.get("courses"), list):
        raise ValueError('Format attendu : {"courses": [...]}')
    aujourd_hui = datetime.now(PARIS).date()
    identifiants = set()
    courses_du_jour = []
    ignorees = 0
    for course in donnees["courses"]:
        depart = verifier(course)
        cid = course["id"]
        if cid in identifiants:
            raise ValueError(f"Identifiant de course dupliqué : {cid}")
        identifiants.add(cid)
        if depart.astimezone(PARIS).date() == aujourd_hui:
            courses_du_jour.append((depart, course))
        else:
            ignorees += 1
    courses_du_jour.sort(key=lambda element: element[0])
    DEST.parent.mkdir(parents=True, exist_ok=True)
    temporaire = DEST.with_suffix(".json.tmp")
    try:
        temporaire.write_text(
            json.dumps({"courses": [course for _, course in courses_du_jour]},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporaire.replace(DEST)
    finally:
        temporaire.unlink(missing_ok=True)
    print(f"Collecte validée : {len(courses_du_jour)} courses du {aujourd_hui} ; "
          f"{ignorees} hors date ignorées. Provenance non vérifiée indépendamment.")
    if not courses_du_jour:
        print("ATTENTION : aucune course française du jour vérifiée ; aucun FIGÉ autorisé.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as erreur:
        print("ERREUR COLLECTE :", erreur, file=sys.stderr)
        sys.exit(1)
    
