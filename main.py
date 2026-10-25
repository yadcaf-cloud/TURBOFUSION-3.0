
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 3.0 — M1 à M5. Analyses expérimentales, aucun pari exécuté."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo('Europe/Paris')
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
COURSES_FILE = DATA_DIR / 'courses.json'
PUBLICATION_FILE = DATA_DIR / 'publication_latest.json'
FIGES_DIR = DATA_DIR / 'figes'
# Chaque moteur utilise ses critères propres; aucun score absent n'est estimé.
MOTEURS = {
    'M1': {'specialite': 'Forme et régularité', 'criteres': ('forme', 'regularite')},
    'M2': {'specialite': 'Aptitudes et conditions', 'criteres': ('aptitude', 'distance', 'terrain')},
    'M3': {'specialite': 'Origines et entourage', 'criteres': ('origines', 'jockey', 'entraineur')},
    'M4': {'specialite': 'Classe et stratégie', 'criteres': ('classe', 'strategie')},
    'M5': {'specialite': 'Risques et fiabilité', 'criteres': ('fiabilite', 'regularite')},
}
# Compatibilité avec le workflow antérieur, sans modifier les spécialités.
WEIGHTS = {nom: {critere: 1 / len(cfg['criteres']) for critere in cfg['criteres']}
           for nom, cfg in MOTEURS.items()}


def maintenant_paris():
    return dt.datetime.now(PARIS)


def analyser_date(valeur):
    if not isinstance(valeur, str):
        raise ValueError('Date de départ invalide')
    date = dt.datetime.fromisoformat(valeur.replace('Z', '+00:00'))
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError('Date sans fuseau horaire')
    return date.astimezone(PARIS)


def lire_json(chemin):
    with chemin.open(encoding='utf-8') as fichier:
        return json.load(fichier)


def ecrire_json(chemin, donnees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=chemin.parent,
                                         suffix='.tmp', delete=False) as f:
            temporaire = Path(f.name)
            json.dump(donnees, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporaire, chemin)
    finally:
        if temporaire is not None:
            temporaire.unlink(missing_ok=True)


def valeur_sportive(cheval, critere):
    valeur = cheval.get(critere)
    if type(valeur) not in (int, float) or not math.isfinite(valeur):
        return None
    return float(valeur) if 0 <= valeur <= 1 else None


def verifier_course(course):
    if not isinstance(course, dict):
        raise ValueError('Course invalide')
    identifiant = course.get('id')
    if not isinstance(identifiant, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identifiant):
        raise ValueError('Identifiant de course non sécurisé')
    depart = analyser_date(course.get('depart'))
    chevaux = course.get('partants')
    if not isinstance(chevaux, list) or len(chevaux) < 2:
        raise ValueError('Liste des chevaux invalide')
    numeros = set()
    for cheval in chevaux:
        if not isinstance(cheval, dict) or type(cheval.get('numero')) is not int or cheval['numero'] <= 0:
            raise ValueError('Numéro de cheval invalide')
        if cheval['numero'] in numeros:
            raise ValueError('Numéro de cheval dupliqué')
        numeros.add(cheval['numero'])
        if not isinstance(cheval.get('nom'), str) or not cheval['nom'].strip():
            raise ValueError('Nom de cheval manquant')
    np = course.get('non_partants', [])
    if not isinstance(np, list) or any(type(n) is not int for n in np):
        raise ValueError('Liste NP invalide')
    if len(np) != len(set(np)) or not set(np).issubset(numeros):
        raise ValueError('NP incohérents')
    np_set = set(np)
    np_set.update(c['numero'] for c in chevaux if c.get('non_partant') is True)
    actifs = [c for c in chevaux if c['numero'] not in np_set]
    return depart, actifs, sorted(np_set)


def analyser_moteur(nom_moteur, chevaux, heure_analyse, heure_depart):
    cfg = MOTEURS[nom_moteur]
    criteres = cfg['criteres']
    classement = []
    for cheval in chevaux:
        valeurs = [valeur_sportive(cheval, critere) for critere in criteres]
        disponibles = [v for v in valeurs if v is not None]
        complet = len(disponibles) == len(criteres)
        classement.append({
            'numero': cheval['numero'], 'nom': cheval['nom'],
            'score': round(sum(disponibles) / len(disponibles), 4) if complet else None,
            'couverture': round(len(disponibles) / len(criteres), 3),
        })
    donnees_completes = len(classement) >= 2 and all(c['score'] is not None for c in classement)
    if donnees_completes:
        classement.sort(key=lambda c: (-c['score'], c['numero']))
    else:
        classement.sort(key=lambda c: c['numero'])
    eligible = (donnees_completes and heure_analyse < heure_depart
                and classement[0]['score'] > classement[1]['score'])
    ordre = [c['numero'] for c in classement[:5]] if eligible else []
    if heure_analyse >= heure_depart:
        motif = 'Départ atteint ou dépassé'
    elif not donnees_completes:
        motif = 'Critères sportifs manquants : abstention'
    elif not eligible:
        motif = 'Premiers scores ex aequo : abstention'
    else:
        motif = 'Scores complets et distincts; analyse expérimentale'
    return {
        'moteur': nom_moteur, 'specialite': cfg['specialite'],
        'classement_detail': classement[:5],
        'classement': ordre, 'ordre_arrivee_espere': ordre,
        'gagnant_espere': ordre[0] if ordre else None,
        'place_espere': ordre[1] if len(ordre) > 1 else None,
        'qualification': 'candidate' if eligible else 'abstention',
        'motif': motif, 'pari': 'Aucun pari proposé',
        'couverture': min((c['couverture'] for c in classement), default=0),
    }


def chemin_fige(identifiant):
    return FIGES_DIR / (identifiant + '.json')


def verifier_fige(chemin, course):
    try:
        contenu = chemin.read_bytes()
        archive = json.loads(contenu)
        depart = analyser_date(archive['depart'])
        fige_a = analyser_date(archive['fige_a'])
        valide = (archive.get('course_id') == course['id']
                  and depart == analyser_date(course['depart'])
                  and fige_a < depart
                  and isinstance(archive.get('moteurs'), dict)
                  and set(archive['moteurs']) == set(MOTEURS))
        # L'empreinte recalculée détecte des changements seulement si elle est
        # comparée à une empreinte de référence conservée séparément.
        empreinte = hashlib.sha256(contenu).hexdigest()
        return archive, empreinte, valide
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None, None, False


def enregistrer_fige(course, analyses, heure_analyse):
    FIGES_DIR.mkdir(parents=True, exist_ok=True)
    chemin = chemin_fige(course['id'])
    archive = {
        'logiciel': 'TURBOFUSION 3.0', 'course_id': course['id'],
        'depart': course['depart'], 'fige_a': heure_analyse.isoformat(),
        'moteurs': analyses, 'source': course.get('source'),
        'pv': 'PV1', 'version': 'V1',
    }
    contenu = (json.dumps(archive, ensure_ascii=False, sort_keys=True,
                          indent=2, allow_nan=False) + '\n').encode('utf-8')
    try:
        with chemin.open('xb') as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
    except FileExistsError:
        pass
    return verifier_fige(chemin, course)


def traiter_courses(arguments):
    heure = maintenant_paris()
    if not COURSES_FILE.is_file():
        raise RuntimeError('data/courses.json absent : exécuter collect_courses.py')
    donnees = lire_json(COURSES_FILE)
    if not isinstance(donnees, dict) or not isinstance(donnees.get('courses'), list):
        raise ValueError('Format courses[] invalide')
    publications = []
    avertissements = []
    identifiants = set()
    for course in donnees['courses']:
        try:
            depart, chevaux, np = verifier_course(course)
            if course['id'] in identifiants:
                raise ValueError('Course dupliquée')
            identifiants.add(course['id'])
            if depart.date() != heure.date():
                continue
            analyses = {nom: analyser_moteur(nom, chevaux, heure, depart) for nom in MOTEURS}
            qualifies = [nom for nom, a in analyses.items() if a['qualification'] == 'candidate']
            admissible = bool(qualifies) and len(chevaux) >= 2
            publication = {
                'id': course['id'], 'hippodrome': course.get('hippodrome', ''),
                'depart': course['depart'], 'partants': len(chevaux),
                'non_partants': np, 'source': course.get('source'),
                'analyse_a': heure.isoformat(), 'moteurs': analyses,
                'moteurs_qualifies': qualifies,
                'qualification': 'verte' if admissible else 'non_valide',
                'statut': 'analyse_provisoire' if admissible else 'non_valide',
            }
            chemin = chemin_fige(course['id'])
            archive = empreinte = None
            valide = False
            if chemin.exists():
                archive, empreinte, valide = verifier_fige(chemin, course)
            elif arguments.figer and admissible and heure < depart - dt.timedelta(minutes=arguments.safety_minutes):
                archive, empreinte, valide = enregistrer_fige(course, analyses, heure)
            if chemin.exists():
                publication['fichier_fige'] = chemin.relative_to(BASE_DIR).as_posix()
                publication['sha256'] = empreinte
                if valide:
                    publication['statut'] = 'fige'
                    publication['pv'] = archive.get('pv', 'PV1')
                    publication['version'] = archive.get('version', 'V1')
                    publication['fige_a'] = archive['fige_a']
                    # Afficher le pronostic archivé, jamais une reconstruction.
                    publication['moteurs'] = archive['moteurs']
                    publication['moteurs_qualifies'] = [
                        nom for nom, a in archive['moteurs'].items()
                        if isinstance(a, dict) and a.get('qualification') == 'candidate'
                    ]
                    publication['qualification'] = 'verte' if publication['moteurs_qualifies'] else 'non_valide'
                else:
                    publication['statut'] = 'fige_invalide'
                    publication['qualification'] = 'non_valide'
                    avertissements.append(course['id'] + ' : FIGÉ non vérifiable')
                publication['preuve_fige'] = {
                    'verifie': False, 'horodatage_avant_depart': bool(valide),
                    'sha256_verifie': False, 'pv_verifie': False,
                }
            publications.append(publication)
        except (ValueError, TypeError, KeyError) as erreur:
            avertissements.append(str(course.get('id', '?')) + ' : ' + str(erreur))
            if arguments.strict_input:
                raise
    publications.sort(key=lambda c: analyser_date(c['depart']))
    resultat = {
        'logiciel': 'TURBOFUSION 3.0', 'date': heure.date().isoformat(),
        'genere_a': heure.isoformat(), 'statut_collecte': 'structure_validee',
        'moteurs': list(MOTEURS), 'courses': publications,
        'audits': [], 'avertissements': avertissements + [
            'Scores uniquement issus des données fournies.',
            'FIGÉS non certifiés cryptographiquement sans empreinte externe.',
            'Aucun pari réel exécuté. Aucune garantie de gain.',
        ],
    }
    ecrire_json(PUBLICATION_FILE, resultat)
    print(f'TURBOFUSION : {len(publications)} course(s) publiée(s), '
          f'{sum(c["statut"] == "fige" for c in publications)} FIGÉ(s) historiques.')
    for avertissement in avertissements:
        print('AVERTISSEMENT :', avertissement, file=sys.stderr)


def diagnostic():
    print('TURBOFUSION 3.0 — DIAGNOSTIC')
    print('Heure Paris :', maintenant_paris().isoformat())
    for nom, cfg in MOTEURS.items():
        print(nom, cfg['specialite'], '—', ', '.join(cfg['criteres']))
    for chemin in (COURSES_FILE, PUBLICATION_FILE, FIGES_DIR):
        print(chemin.relative_to(BASE_DIR), 'présent :', chemin.exists())
    print('Diagnostic structurel seulement : aucun pronostic certifié.')


def main():
    parser = argparse.ArgumentParser(description='TURBOFUSION 3.0 M1 à M5')
    parser.add_argument('--diagnostic', action='store_true')
    parser.add_argument('--figer', action='store_true')
    parser.add_argument('--strict-input', action='store_true')
    parser.add_argument('--safety-minutes', type=int, default=2)
    args = parser.parse_args()
    if args.safety_minutes < 0:
        parser.error('Le délai de sécurité doit être positif ou nul')
    if args.diagnostic:
        diagnostic()
    else:
        traiter_courses(args)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as erreur:
        print('ERREUR TURBOFUSION :', erreur, file=sys.stderr)
        sys.exit(1)
