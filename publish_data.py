#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 3.0 — Publication contrôlée M1–M5.

Priorité à data/audit_latest.json. À défaut, validation de la publication
existante produite par main.py. Aucun pronostic ou FIGÉ n'est créé ici.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
MOTEURS = ("M1", "M2", "M3", "M4", "M5")
IDENTIFIANT = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


def _constante_invalide(valeur):
    raise ValueError(f"Constante JSON interdite : {valeur}")


def _sans_doublons(paires):
    resultat = {}
    for cle, valeur in paires:
        if cle in resultat:
            raise ValueError(f"Clé JSON dupliquée : {cle}")
        resultat[cle] = valeur
    return resultat


def _verifier_json(valeur):
    if valeur is None or isinstance(valeur, (str, bool, int)):
        return
    if isinstance(valeur, float):
        if not math.isfinite(valeur):
            raise ValueError("Nombre non fini")
        return
    if isinstance(valeur, list):
        for element in valeur:
            _verifier_json(element)
        return
    if isinstance(valeur, dict):
        for cle, element in valeur.items():
            if not isinstance(cle, str):
                raise ValueError("Clé non textuelle")
            _verifier_json(element)
        return
    raise ValueError(f"Type JSON interdit : {type(valeur).__name__}")


def _date_avec_fuseau(valeur, champ):
    if not isinstance(valeur, str):
        raise ValueError(f"{champ} absent ou invalide")
    try:
        date = dt.datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{champ} non ISO-8601") from exc
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError(f"{champ} sans fuseau horaire")
    return date


def _moteurs_valides(valeur):
    if valeur is None:
        return {}
    if not isinstance(valeur, dict):
        raise ValueError("Les moteurs doivent être un objet JSON")
    inconnus = set(valeur) - set(MOTEURS)
    if inconnus:
        raise ValueError(f"Moteurs inconnus : {sorted(inconnus)}")
    resultat = {}
    for nom in MOTEURS:
        if nom not in valeur:
            continue
        moteur = valeur[nom]
        if not isinstance(moteur, dict) or moteur.get("moteur", nom) != nom:
            raise ValueError(f"Moteur incohérent : {nom}")
        classement = moteur.get("classement", [])
        if not isinstance(classement, list):
            raise ValueError(f"Classement invalide : {nom}")
        numeros = []
        for cheval in classement:
            numero = cheval.get("numero") if isinstance(cheval, dict) else cheval
            if type(numero) is not int or numero <= 0:
                raise ValueError(f"Numéro invalide : {nom}")
            numeros.append(numero)
        if len(numeros) != len(set(numeros)):
            raise ValueError(f"Doublon de classement : {nom}")
        resultat[nom] = moteur
    return resultat


def _preuve_non_certifiee(course):
    # Une publication n'a pas le droit de s'auto-certifier.
    copie = dict(course)
    if copie.get("statut") == "fige":
        copie["statut"] = "fige_non_certifie"
    copie["preuve_fige"] = {
        "verifie": False,
        "horodatage_avant_depart": False,
        "sha256_verifie": False,
        "pv_verifie": False,
    }
    return copie


def _normaliser_course(course, index):
    if not isinstance(course, dict):
        raise ValueError(f"Course {index} invalide")
    identifiant = course.get("id")
    if not isinstance(identifiant, str) or not IDENTIFIANT.fullmatch(identifiant):
        raise ValueError(f"Identifiant invalide, course {index}")
    _date_avec_fuseau(course.get("depart"), f"Départ {identifiant}")
    if not isinstance(course.get("statut", "non_valide"), str):
        raise ValueError(f"Statut invalide : {identifiant}")
    moteurs = _moteurs_valides(course.get("moteurs"))
    copie = _preuve_non_certifiee(course)
    copie["moteurs"] = moteurs
    return copie


def _normaliser_audits(valeur):
    if valeur is None:
        return []
    if not isinstance(valeur, list):
        raise ValueError("audits doit être une liste")
    resultat = []
    for i, audit in enumerate(valeur, 1):
        if not isinstance(audit, dict):
            raise ValueError(f"Audit {i} invalide")
        copie = dict(audit)
        # Le module ne vérifie pas les empreintes archivées.
        copie["preuve_fige"] = {
            "verifie": False,
            "horodatage_avant_depart": False,
            "sha256_verifie": False,
            "pv_verifie": False,
        }
        resultat.append(copie)
    return resultat


def _charger(chemin):
    with chemin.open("r", encoding="utf-8") as fichier:
        donnees = json.load(
            fichier,
            parse_constant=_constante_invalide,
            object_pairs_hook=_sans_doublons,
        )
    _verifier_json(donnees)
    if not isinstance(donnees, dict):
        raise ValueError("Racine JSON invalide")
    return donnees


def publish(data_dir=DATA_DIR):
    data_dir = Path(data_dir)
    audit_source = data_dir / "audit_latest.json"
    cible = data_dir / "publication_latest.json"
    temporaire = None
    try:
        # Ne pas régénérer une publication depuis elle-même si l'audit manque.
        # Dans ce cas, vérifier l'existant et le conserver intact.
        if not audit_source.is_file():
            if not cible.is_file():
                raise FileNotFoundError("Ni audit_latest.json ni publication_latest.json")
            source = _charger(cible)
            courses = source.get("courses")
            if not isinstance(courses, list):
                raise ValueError("Publication existante : courses[] invalide")
            ids = set()
            for i, course in enumerate(courses, 1):
                valide = _normaliser_course(course, i)
                if valide["id"] in ids:
                    raise ValueError("Course dupliquée")
                ids.add(valide["id"])
            _normaliser_audits(source.get("audits", []))
            print(f"Publication existante vérifiée structurellement et conservée : {cible}")
            return cible

        audit = _charger(audit_source)
        courses_source = audit.get("courses")
        if not isinstance(courses_source, list):
            raise ValueError("Liste courses[] absente ou invalide")
        courses, ids = [], set()
        for index, course in enumerate(courses_source, 1):
            entree = _normaliser_course(course, index)
            if entree["id"] in ids:
                raise ValueError(f"Course dupliquée : {entree['id']}")
            ids.add(entree["id"])
            courses.append(entree)
        courses.sort(key=lambda c: _date_avec_fuseau(c["depart"], "depart"))
        audits = _normaliser_audits(audit.get("audits", []))
        publication = {
            "logiciel": "TURBOFUSION 3.0",
            "date": audit.get("date"),
            "genere_a": audit.get("genere_a"),
            "statut_collecte": audit.get("statut_collecte", "non_verifie"),
            "moteurs": list(MOTEURS),
            "courses": courses,
            "audits": audits,
            "avertissements": list(audit.get("avertissements", [])) if isinstance(audit.get("avertissements", []), list) else [],
        }
        publication["avertissements"].extend([
            "FIGÉS non certifiés par ce module de publication.",
            "Aucun pronostic absent n'est créé.",
            "Aucun pari réel exécuté. Aucune garantie de gain.",
        ])
        contenu = json.dumps(publication, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=data_dir,
            prefix=".publication_", suffix=".tmp", delete=False,
        ) as fichier:
            temporaire = Path(fichier.name)
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.replace(temporaire, cible)
        temporaire = None
        print(f"TURBOFUSION : {len(courses)} course(s) publiée(s) — FIGÉS non certifiés.")
        return cible
    except (OSError, ValueError, TypeError, OverflowError) as erreur:
        print(f"ERREUR PUBLICATION : {erreur}", file=sys.stderr)
        return None
    finally:
        if temporaire is not None:
            temporaire.unlink(missing_ok=True)


publier = publish

if __name__ == "__main__":
    if publish() is None:
        raise SystemExit(1)
