#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 3.0 — validation locale des courses PMU.

Entrée : data/courses_source.json ; sortie : data/courses.json.
Aucun accès réseau, pronostic ou FIGÉ. La provenance n'est pas certifiée.
Codes retour : 0 succès, 1 erreur, 2 source absente, 3 aucune course du jour.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
SOURCE = DATA / 'courses_source.json'
DEST = DATA / 'courses.json'
PARIS = ZoneInfo('Europe/Paris')
CHAMPS = ('id', 'hippodrome', 'depart', 'source', 'pays', 'partants')


def sans_doublons(paires):
    resultat = {}
    for cle, valeur in paires:
        if cle in resultat:
            raise ValueError(f'Clé JSON dupliquée : {cle}')
        resultat[cle] = valeur
    return resultat


def constante_interdite(valeur):
    raise ValueError(f'Constante JSON interdite : {valeur}')


def lire_json(chemin):
    return json.loads(chemin.read_text(encoding='utf-8-sig'),
                      object_pairs_hook=sans_doublons,
                      parse_constant=constante_interdite)


def texte_valide(valeur):
    return isinstance(valeur, str) and bool(valeur.strip())


def verifier_url(adresse):
    if not texte_valide(adresse) or adresse != adresse.strip():
        raise ValueError('URL source absente ou mal formée')
    if any(c.isspace() or ord(c) < 32 for c in adresse):
        raise ValueError('URL source contenant des espaces ou caractères de contrôle')
    try:
        url = urlsplit(adresse)
        port = url.port
    except ValueError as erreur:
        raise ValueError('URL source invalide') from erreur
    if (url.scheme != 'https' or not url.hostname or
            url.username is not None or url.password is not None or
            url.fragment or not url.netloc or
            url.hostname in ('localhost',) or
            (port is not None and port <= 0)):
        raise ValueError('URL source HTTPS invalide')
    # La validation syntaxique ne prouve ni la fiabilité ni l'accessibilité de l'URL.


def verifier_date(valeur):
    if not texte_valide(valeur):
        raise ValueError('Date absente')
    if not re.search(r'(Z|[+-]\d{2}:\d{2})$', valeur):
        raise ValueError('Fuseau horaire ISO explicite obligatoire')
    try:
        depart = datetime.fromisoformat(valeur.replace('Z', '+00:00'))
    except ValueError as erreur:
        raise ValueError(f'Date ISO invalide : {valeur}') from erreur
    if depart.tzinfo is None or depart.utcoffset() is None:
        raise ValueError('Fuseau horaire obligatoire')
    return depart.astimezone(PARIS)


def verifier_chevaux(course):
    chevaux = course['partants']
    if not isinstance(chevaux, list) or len(chevaux) < 2:
        raise ValueError('Liste de partants insuffisante')
    numeros = set()
    np_individuels = set()
    for cheval in chevaux:
        if not isinstance(cheval, dict):
            raise ValueError('Cheval non représenté par un objet')
        numero, nom = cheval.get('numero'), cheval.get('nom')
        if type(numero) is not int or numero <= 0:
            raise ValueError('Numéro de cheval invalide')
        if not texte_valide(nom):
            raise ValueError(f'Nom absent pour le numéro {numero}')
        if numero in numeros:
            raise ValueError(f'Numéro dupliqué : {numero}')
        numeros.add(numero)
        statut = cheval.get('non_partant', False)
        if type(statut) is not bool:
            raise ValueError(f'Statut NP invalide : {numero}')
        if statut:
            np_individuels.add(numero)
    non_partants = course.get('non_partants', [])
    if not isinstance(non_partants, list):
        raise ValueError('Liste des non-partants invalide')
    np_declares = set()
    for numero in non_partants:
        if (type(numero) is not int or numero <= 0 or
                numero not in numeros or numero in np_declares):
            raise ValueError(f'Non-partant incohérent : {numero}')
        np_declares.add(numero)
    tous_np = np_declares | np_individuels
    if len(numeros - tous_np) < 2:
        raise ValueError('Moins de deux chevaux encore partants')
    course['non_partants'] = sorted(tous_np)
    for cheval in chevaux:
        cheval['non_partant'] = cheval['numero'] in tous_np


def verifier_course(course):
    if not isinstance(course, dict):
        raise ValueError('Course non représentée par un objet')
    for champ in CHAMPS:
        if champ not in course:
            raise ValueError(f'Champ obligatoire absent : {champ}')
    identifiant = course['id']
    if not texte_valide(identifiant) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identifiant):
        raise ValueError('Identifiant de course invalide')
    if not texte_valide(course['hippodrome']):
        raise ValueError('Hippodrome invalide')
    if not texte_valide(course['pays']) or course['pays'].strip().upper() not in ('FR', 'FRANCE'):
        raise ValueError('Course hors de France ou pays non confirmé')
    verifier_url(course['source'])
    depart = verifier_date(course['depart'])
    verifier_chevaux(course)
    return depart


def ecriture_atomique(chemin, donnees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=chemin.parent, prefix='.courses_',
                                         suffix='.tmp', delete=False) as fichier:
            temporaire = Path(fichier.name)
            json.dump(donnees, fichier, ensure_ascii=False, indent=2, allow_nan=False)
            fichier.write('\n')
            fichier.flush()
            os.fsync(fichier.fileno())
        os.replace(temporaire, chemin)
    finally:
        if temporaire is not None:
            temporaire.unlink(missing_ok=True)


def invalider_sortie():
    # Une sortie antérieure ne doit pas survivre à un contrôle échoué.
    DEST.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic', action='store_true',
                        help='Vérifier les données sans publier courses.json')
    args = parser.parse_args(argv)
    maintenant = datetime.now(PARIS)
    aujourd_hui = maintenant.date()
    print('TURBOFUSION 3.0 — VALIDATION DES DONNÉES PMU')
    print('Heure Paris :', maintenant.isoformat(timespec='seconds'))
    if not args.diagnostic:
        invalider_sortie()
    if not SOURCE.is_file():
        print('SOURCE ABSENTE : data/courses_source.json. Aucun FIGÉ autorisé.', file=sys.stderr)
        return 2
    donnees = lire_json(SOURCE)
    if not isinstance(donnees, dict) or not isinstance(donnees.get('courses'), list):
        raise ValueError('Format attendu : {"courses": [...]}')
    identifiants = set()
    courses_du_jour = []
    ignorees = 0
    for course in donnees['courses']:
        depart = verifier_course(course)
        identifiant = course['id']
        if identifiant in identifiants:
            raise ValueError(f'Identifiant de course dupliqué : {identifiant}')
        identifiants.add(identifiant)
        if depart.date() != aujourd_hui:
            ignorees += 1
            continue
        courses_du_jour.append((depart, course))
    courses_du_jour.sort(key=lambda element: (element[0], element[1]['id']))
    if not courses_du_jour:
        print('Aucune course française du jour validée. Aucun FIGÉ autorisé.', file=sys.stderr)
        return 3
    if not args.diagnostic:
        ecriture_atomique(DEST, {'courses': [course for _, course in courses_du_jour]})
    print(f'Courses validées : {len(courses_du_jour)}')
    print(f'Courses hors date : {ignorees}')
    print(f'Date Paris : {aujourd_hui}')
    print('Mode : diagnostic sans publication' if args.diagnostic else 'Publié : data/courses.json')
    print('ATTENTION : provenance et fraîcheur de la source non vérifiées indépendamment.')
    return 0


if __name__ == '__main__':
    diagnostic = '--diagnostic' in sys.argv[1:]
    try:
        sys.exit(main())
    except (ValueError, TypeError, KeyError, OSError) as erreur:
        if not diagnostic:
            try:
                invalider_sortie()
            except OSError as suppression:
                print(f'ALERTE : ancienne sortie non supprimée : {suppression}', file=sys.stderr)
        print('ERREUR COLLECTE :', erreur, file=sys.stderr)
        sys.exit(1)
           
