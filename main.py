#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 3.0 : analyses M1-M5, PV et FIGÉS versionnés.

Entrée : data/courses.json. Aucune collecte réseau ni score inventé.
Sorties : data/publication_latest.json et data/figes/<id>.Vn.{json,pv.json}.
Les archives existantes ne sont jamais écrasées. Les données doivent être vérifiées
par un fournisseur externe ; une URL HTTPS ne prouve pas leur authenticité.
"""
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
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
SOURCE = DATA / 'courses.json'
PUBLICATION = DATA / 'publication_latest.json'
ARCHIVES = DATA / 'figes'
PARIS = ZoneInfo('Europe/Paris')
MOTEURS = {
    'M1': ('Forme et régularité', ('forme', 'regularite')),
    'M2': ('Aptitudes et conditions', ('aptitude', 'distance', 'terrain')),
    'M3': ('Origines et entourage', ('origines', 'jockey', 'entraineur')),
    'M4': ('Classe et stratégie', ('classe', 'strategie')),
    'M5': ('Risques et fiabilité', ('fiabilite', 'regularite')),
}
ID_RE = re.compile(r'[A-Za-z0-9_-]{1,80}\Z')


def now():
    return dt.datetime.now(PARIS)


def date_iso(value):
    if not isinstance(value, str):
        raise ValueError('Date ISO-8601 absente')
    try:
        result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Date ISO-8601 invalide') from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Date sans fuseau horaire')
    return result.astimezone(PARIS)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Clé JSON dupliquée : ' + key)
        result[key] = value
    return result


def bad_constant(value):
    raise ValueError('Constante JSON interdite : ' + value)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'),
                      object_pairs_hook=no_duplicates, parse_constant=bad_constant)


def serialized(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + '\n').encode('utf-8')


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
            tmp = Path(file.name)
            file.write(serialized(value))
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def exclusive_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as file:
        file.write(serialized(value))
        file.flush()
        os.fsync(file.fileno())


def verify_course(course):
    if not isinstance(course, dict):
        raise ValueError('Course invalide : objet attendu')
    cid = course.get('id')
    if not isinstance(cid, str) or not ID_RE.fullmatch(cid):
        raise ValueError('Identifiant de course invalide')
    depart = date_iso(course.get('depart'))
    if not isinstance(course.get('hippodrome'), str) or not course['hippodrome'].strip():
        raise ValueError(cid + ' : hippodrome absent')
    if str(course.get('pays', '')).strip().upper() not in ('FR', 'FRANCE'):
        raise ValueError(cid + ' : localisation française non confirmée')
    source = course.get('source')
    parsed = urlparse(source) if isinstance(source, str) else None
    if not parsed or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(cid + ' : URL HTTPS source invalide')
    horses = course.get('partants')
    if not isinstance(horses, list) or len(horses) < 2:
        raise ValueError(cid + ' : partants insuffisants')
    numbers = set()
    for horse in horses:
        if not isinstance(horse, dict) or type(horse.get('numero')) is not int or horse['numero'] <= 0:
            raise ValueError(cid + ' : numéro invalide')
        if horse['numero'] in numbers:
            raise ValueError(cid + ' : numéro dupliqué')
        numbers.add(horse['numero'])
        if not isinstance(horse.get('nom'), str) or not horse['nom'].strip():
            raise ValueError(cid + ' : nom de cheval absent')
        if 'non_partant' in horse and type(horse['non_partant']) is not bool:
            raise ValueError(cid + ' : indicateur non_partant invalide')
    np = course.get('non_partants', [])
    if not isinstance(np, list) or any(type(n) is not int or n <= 0 for n in np):
        raise ValueError(cid + ' : non-partants invalides')
    if len(set(np)) != len(np) or not set(np).issubset(numbers):
        raise ValueError(cid + ' : non-partants incohérents')
    exclusions = set(np) | {h['numero'] for h in horses if h.get('non_partant') is True}
    active = [h for h in horses if h['numero'] not in exclusions]
    return depart, active, sorted(exclusions)


def score(horse, criterion):
    value = horse.get(criterion)
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return float(value) if 0 <= value <= 1 else None


def engine(name, horses, instant, depart):
    speciality, criteria = MOTEURS[name]
    ranking = []
    for horse in horses:
        values = [score(horse, criterion) for criterion in criteria]
        complete = all(value is not None for value in values)
        ranking.append({
            'numero': horse['numero'], 'nom': horse['nom'],
            'score': round(sum(values) / len(values), 6) if complete else None,
            'couverture': round(sum(v is not None for v in values) / len(values), 3),
        })
    all_complete = len(ranking) >= 2 and all(h['score'] is not None for h in ranking)
    if all_complete:
        ranking.sort(key=lambda h: (-h['score'], h['numero']))
    else:
        ranking.sort(key=lambda h: h['numero'])
    qualified = instant < depart and all_complete and ranking[0]['score'] > ranking[1]['score']
    order = [h['numero'] for h in ranking[:5]] if qualified else []
    reason = ('Départ atteint ou dépassé' if instant >= depart else
              'Moins de deux partants actifs ou scores incomplets' if not all_complete else
              'Deux premiers scores ex aequo' if not qualified else
              'Candidat expérimental : critères renseignés, sans validation prédictive')
    return {
        'moteur': name, 'specialite': speciality, 'criteres': list(criteria),
        'classement_detail': ranking[:5], 'classement': order,
        'ordre_arrivee_espere': order,
        'gagnant_espere': order[0] if order else None,
        'place_espere': order[1] if len(order) > 1 else None,
        'qualification': 'candidate' if qualified else 'abstention',
        'motif': reason, 'pari': 'Aucun pari exécuté',
        'couverture': min((h['couverture'] for h in ranking), default=0),
    }


def paths(cid, version):
    stem = f'{cid}.V{version}'
    return ARCHIVES / f'{stem}.json', ARCHIVES / f'{stem}.pv.json'


def archive_versions(cid):
    versions = set()
    if ARCHIVES.is_dir():
        for path in ARCHIVES.glob(cid + '.V*.json'):
            match = re.fullmatch(re.escape(cid) + r'\.V([1-9][0-9]*)\.(?:pv\.)?json', path.name)
            if match:
                versions.add(int(match.group(1)))
    # Ancien format : conserver l'archive historique, sans conversion automatique.
    if (ARCHIVES / f'{cid}.json').exists() or (ARCHIVES / f'{cid}.pv.json').exists():
        raise ValueError(cid + ' : archive ancienne détectée ; migration contrôlée nécessaire')
    return sorted(versions)


def load_archive(cid, version, depart):
    fig, pv = paths(cid, version)
    if not fig.exists() or not pv.exists():
        return None, None, False, 'FIGÉ/PV incomplet'
    try:
        archive, proof = read(fig), read(pv)
        digest = hashlib.sha256(fig.read_bytes()).hexdigest()
        motors = archive.get('moteurs')
        if not isinstance(motors, dict):
            return None, digest, False, 'Moteurs archivés invalides'
        valid = (archive.get('course_id') == cid and
                 date_iso(archive['depart']) == depart and
                 date_iso(archive['fige_a']) < depart and
                 set(motors) == set(MOTEURS) and
                 all(isinstance(motors[n], dict) for n in MOTEURS) and
                 archive.get('version') == f'V{version}' and
                 archive.get('pv') == f'PV{version}' and
                 proof.get('course_id') == cid and
                 proof.get('sha256_fige') == digest and
                 proof.get('fige_a') == archive['fige_a'] and
                 proof.get('version') == archive['version'] and
                 proof.get('pv') == archive['pv'])
        return archive, digest, valid, None if valid else 'FIGÉ/PV incohérents'
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return None, None, False, 'Archive illisible : ' + str(exc)


def snapshot(horses, np):
    return {'partants_actifs': sorted(h['numero'] for h in horses), 'non_partants': np}


def freeze(course, analyses, instant, version, horses, np):
    depart = date_iso(course['depart'])
    if instant >= depart:
        raise ValueError('FIGÉ rétroactif interdit')
    fig, pv = paths(course['id'], version)
    if fig.exists() or pv.exists():
        raise FileExistsError('Version FIGÉ/PV déjà présente')
    archive = {
        'logiciel': 'TURBOFUSION 3.0', 'course_id': course['id'],
        'depart': course['depart'], 'fige_a': instant.isoformat(),
        'source': course['source'], 'moteurs': analyses,
        'effectif': snapshot(horses, np),
        'pv': f'PV{version}', 'version': f'V{version}',
    }
    proof = {
        'course_id': course['id'], 'pv': f'PV{version}',
        'version': f'V{version}', 'fige_a': instant.isoformat(),
        'sha256_fige': hashlib.sha256(serialized(archive)).hexdigest(),
        'decision': 'FIGÉ expérimental avant départ',
        'certification_externe': False,
    }
    # Les deux créations sont exclusives. Une interruption laisse un état
    # incomplet, signalé et bloquant, jamais réparé silencieusement.
    exclusive_write(fig, archive)
    exclusive_write(pv, proof)


def run(args):
    instant = now()
    if not SOURCE.is_file():
        raise RuntimeError('data/courses.json absent : exécuter collecte_pmu.py')
    data = read(SOURCE)
    if not isinstance(data, dict) or not isinstance(data.get('courses'), list):
        raise ValueError('Format attendu : {"courses": [...]}')
    seen, output, warnings = set(), [], []
    for course in data['courses']:
        try:
            depart, horses, np = verify_course(course)
            cid = course['id']
            if cid in seen:
                raise ValueError('Identifiant dupliqué : ' + cid)
            seen.add(cid)
            if depart.date() != instant.date():
                continue
            versions = archive_versions(cid)
            archives = []
            for version in versions:
                item = load_archive(cid, version, depart)
                if not item[2]:
                    raise ValueError(f'{cid} V{version} : {item[3]}')
                archives.append((version, *item))
            current_snapshot = snapshot(horses, np)
            latest = archives[-1] if archives else None
            changed = bool(latest and latest[1].get('effectif') != current_snapshot)
            analyses = {name: engine(name, horses, instant, depart) for name in MOTEURS}
            qualified = [name for name, result in analyses.items()
                         if result['qualification'] == 'candidate']
            can_freeze = (args.figer and qualified and len(horses) >= 2 and
                          instant < depart - dt.timedelta(minutes=args.safety_minutes))
            if can_freeze and (latest is None or changed):
                next_version = versions[-1] + 1 if versions else 1
                freeze(course, analyses, instant, next_version, horses, np)
                item = load_archive(cid, next_version, depart)
                if not item[2]:
                    raise ValueError(cid + ' : nouvel archivage invalide')
                latest = (next_version, *item)
                changed = False
            if latest and not changed:
                version, archive, digest, _, _ = latest
                analyses = archive['moteurs']
                qualified = [name for name, result in analyses.items()
                             if result.get('qualification') == 'candidate']
                status = 'fige'
            elif changed:
                status = 'fige_a_reviser' if instant < depart else 'fige_obsolete_np'
                version, archive, digest = latest[:3]
                # Ne jamais présenter l'ancien pronostic comme FIGÉ courant.
                qualified = []
                warnings.append(cid + ' : changement de partants/NP ; ancien FIGÉ non applicable')
            else:
                version, archive, digest = None, None, None
                status = ('non_valide' if instant >= depart or not qualified else
                          'analyse_provisoire')
            entry = {
                'id': cid, 'hippodrome': course['hippodrome'], 'depart': course['depart'],
                'partants': len(horses), 'non_partants': np, 'source': course['source'],
                'analyse_a': instant.isoformat(), 'moteurs': analyses,
                'moteurs_qualifies': qualified,
                'qualification': 'verte' if status == 'fige' and qualified else 'non_valide',
                'statut': status,
                'preuve_fige': {
                    'verifie': status == 'fige',
                    'horodatage_avant_depart': status == 'fige',
                    'sha256_verifie': status == 'fige',
                    'pv_verifie': status == 'fige',
                    'certification_externe': False,
                },
            }
            if latest:
                fig, pv = paths(cid, version)
                entry.update({
                    'fichier_fige': fig.relative_to(ROOT).as_posix(),
                    'fichier_pv': pv.relative_to(ROOT).as_posix(),
                    'sha256': digest, 'pv': f'PV{version}', 'version': f'V{version}',
                    'fige_a': archive['fige_a'],
                })
            output.append(entry)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            warnings.append(str(course.get('id', '?') if isinstance(course, dict) else '?') + ' : ' + str(exc))
            if args.strict_input:
                raise
    output.sort(key=lambda course: date_iso(course['depart']))
    atomic_write(PUBLICATION, {
        'logiciel': 'TURBOFUSION 3.0', 'date': instant.date().isoformat(),
        'genere_a': instant.isoformat(), 'statut_collecte': 'structure_validee',
        'moteurs': list(MOTEURS), 'courses': output, 'audits': [],
        'avertissements': warnings + [
            'Source HTTPS et pays FR déclarés, non authentifiés indépendamment.',
            'Scores expérimentaux fournis en entrée, non validés statistiquement.',
            'PV/FIGÉs locaux sans certification externe.',
            'Aucun pari réel exécuté ; aucune garantie de gain.',
        ],
    })
    print(f'TURBOFUSION : {len(output)} course(s), '
          f'{sum(c["statut"] == "fige" for c in output)} FIGÉ(s) courants.')
    for warning in warnings:
        print('AVERTISSEMENT :', warning, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='TURBOFUSION 3.0 M1-M5')
    parser.add_argument('--diagnostic', action='store_true')
    parser.add_argument('--figer', action='store_true')
    parser.add_argument('--strict-input', action='store_true')
    parser.add_argument('--safety-minutes', type=int, default=2)
    args = parser.parse_args()
    if args.safety_minutes < 0:
        parser.error('safety-minutes doit être positif ou nul')
    if args.diagnostic:
        print('TURBOFUSION 3.0 —', now().isoformat())
        for name, (speciality, criteria) in MOTEURS.items():
            print(name, speciality, '—', ', '.join(criteria))
        print('Fichier courses présent :', SOURCE.is_file())
        print('Diagnostic structurel ; aucun pronostic certifié.')
    else:
        run(args)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print('ERREUR TURBOFUSION :', exc, file=sys.stderr)
        sys.exit(1)
            
