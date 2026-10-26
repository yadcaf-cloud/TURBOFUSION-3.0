#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 3.0 — analyse M1-M5, PV et FIGÉS non rétroactifs.

Entrée: data/courses.json (courses réellement sourcées).
Sortie: data/publication_latest.json et archives immuables data/figes/.
Aucune récupération réseau, aucun score artificiel, aucun pari exécuté.
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


def now():
    return dt.datetime.now(PARIS)


def date_iso(s):
    if not isinstance(s, str):
        raise ValueError('Date absente')
    x = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
    if x.tzinfo is None or x.utcoffset() is None:
        raise ValueError('Date sans fuseau horaire')
    return x.astimezone(PARIS)


def no_duplicates(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError('Clé JSON dupliquée : ' + k)
        obj[k] = v
    return obj


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
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            f.write(serialized(value))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def unique_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(serialized(value))
        f.flush()
        os.fsync(f.fileno())


def verify_course(c):
    if not isinstance(c, dict):
        raise ValueError('Course non objet')
    cid = c.get('id')
    if not isinstance(cid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', cid):
        raise ValueError('Identifiant de course invalide')
    depart = date_iso(c.get('depart'))
    if not isinstance(c.get('hippodrome'), str) or not c['hippodrome'].strip():
        raise ValueError(cid + ' : hippodrome absent')
    if str(c.get('pays', '')).strip().upper() not in ('FR', 'FRANCE'):
        raise ValueError(cid + ' : pays français non confirmé')
    url = c.get('source')
    parsed = urlparse(url) if isinstance(url, str) else None
    if not parsed or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(cid + ' : source HTTPS absente ou invalide')
    horses = c.get('partants')
    if not isinstance(horses, list) or len(horses) < 2:
        raise ValueError(cid + ' : partants insuffisants')
    nums = set()
    for h in horses:
        if not isinstance(h, dict) or type(h.get('numero')) is not int or h['numero'] <= 0:
            raise ValueError(cid + ' : numéro invalide')
        if h['numero'] in nums:
            raise ValueError(cid + ' : numéro dupliqué')
        nums.add(h['numero'])
        if not isinstance(h.get('nom'), str) or not h['nom'].strip():
            raise ValueError(cid + ' : nom absent')
    np = c.get('non_partants', [])
    if not isinstance(np, list) or any(type(n) is not int for n in np):
        raise ValueError(cid + ' : NP invalides')
    if len(np) != len(set(np)) or not set(np).issubset(nums):
        raise ValueError(cid + ' : NP incohérents')
    exclusions = set(np) | {h['numero'] for h in horses if h.get('non_partant') is True}
    active = [h for h in horses if h['numero'] not in exclusions]
    return depart, active, sorted(exclusions)


def score(horse, key):
    value = horse.get(key)
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return float(value) if 0 <= value <= 1 else None


def engine(name, horses, instant, depart):
    speciality, criteria = MOTEURS[name]
    ranking = []
    for h in horses:
        values = [score(h, k) for k in criteria]
        complete = all(v is not None for v in values)
        ranking.append({
            'numero': h['numero'], 'nom': h['nom'],
            'score': round(sum(values) / len(values), 6) if complete else None,
            'couverture': sum(v is not None for v in values) / len(values),
        })
    all_complete = len(ranking) >= 2 and all(x['score'] is not None for x in ranking)
    if all_complete:
        ranking.sort(key=lambda x: (-x['score'], x['numero']))
    else:
        ranking.sort(key=lambda x: x['numero'])
    qualified = (instant < depart and all_complete and
                 ranking[0]['score'] > ranking[1]['score'])
    order = [x['numero'] for x in ranking[:5]] if qualified else []
    reason = ('Départ atteint' if instant >= depart else
              'Données sportives incomplètes' if not all_complete else
              'Égalité des deux premiers scores' if not qualified else
              'Classement expérimental calculé sur les données fournies')
    return {
        'moteur': name, 'specialite': speciality, 'criteres': list(criteria),
        'classement_detail': ranking[:5], 'classement': order,
        'ordre_arrivee_espere': order,
        'gagnant_espere': order[0] if order else None,
        'place_espere': order[1] if len(order) > 1 else None,
        'qualification': 'candidate' if qualified else 'abstention',
        'motif': reason, 'pari': 'Aucun pari exécuté',
        'couverture': min((x['couverture'] for x in ranking), default=0),
    }


def paths(cid):
    return ARCHIVES / (cid + '.json'), ARCHIVES / (cid + '.pv.json')


def load_archive(cid, depart):
    fig, pv = paths(cid)
    if not fig.exists() and not pv.exists():
        return None, None, False, None
    if not fig.exists() or not pv.exists():
        return None, None, False, 'Archive FIGÉ/PV incomplète'
    try:
        archive, proof = read(fig), read(pv)
        content_hash = hashlib.sha256(fig.read_bytes()).hexdigest()
        valid = (archive.get('course_id') == cid and
                 date_iso(archive['depart']) == depart and
                 date_iso(archive['fige_a']) < depart and
                 set(archive.get('moteurs', {})) == set(MOTEURS) and
                 proof.get('course_id') == cid and
                 proof.get('sha256_fige') == content_hash and
                 proof.get('fige_a') == archive['fige_a'] and
                 proof.get('version') == archive.get('version'))
        return archive, content_hash, valid, None if valid else 'PV/FIGÉ incohérents'
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
        return None, None, False, 'Archive illisible : ' + str(e)


def freeze(course, analyses, instant):
    cid = course['id']
    fig, pv = paths(cid)
    if fig.exists() or pv.exists():
        return
    archive = {
        'logiciel': 'TURBOFUSION 3.0', 'course_id': cid,
        'depart': course['depart'], 'fige_a': instant.isoformat(),
        'source': course['source'], 'moteurs': analyses,
        'pv': 'PV1', 'version': 'V1',
    }
    digest = hashlib.sha256(serialized(archive)).hexdigest()
    proof = {
        'course_id': cid, 'pv': 'PV1', 'version': 'V1',
        'fige_a': archive['fige_a'], 'sha256_fige': digest,
        'decision': 'FIGÉ expérimental avant départ',
        'note': 'Horodatage local du workflow; non certifié par tiers indépendant',
    }
    # Écriture exclusive : jamais d'écrasement d'un FIGÉ existant.
    unique_write(fig, archive)
    unique_write(pv, proof)


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
                raise ValueError('Identifiant de course dupliqué : ' + cid)
            seen.add(cid)
            if depart.date() != instant.date():
                continue
            fig, pv = paths(cid)
            archive, digest, valid, error = load_archive(cid, depart)
            analyses = {name: engine(name, horses, instant, depart) for name in MOTEURS}
            qualified = [n for n, a in analyses.items() if a['qualification'] == 'candidate']
            if args.figer and not fig.exists() and not pv.exists() and qualified and len(horses) >= 2 and instant < depart - dt.timedelta(minutes=args.safety_minutes):
                freeze(course, analyses, instant)
                archive, digest, valid, error = load_archive(cid, depart)
            status = 'fige' if valid else ('fige_invalide' if fig.exists() or pv.exists() else
                     'analyse_provisoire' if qualified else 'non_valide')
            if valid:
                analyses = archive['moteurs']
                qualified = [n for n, a in analyses.items() if a.get('qualification') == 'candidate']
            if error:
                warnings.append(cid + ' : ' + error)
            entry = {
                'id': cid, 'hippodrome': course['hippodrome'], 'depart': course['depart'],
                'partants': len(horses), 'non_partants': np, 'source': course['source'],
                'analyse_a': instant.isoformat(), 'moteurs': analyses,
                'moteurs_qualifies': qualified,
                'qualification': 'verte' if qualified and status != 'fige_invalide' else 'non_valide',
                'statut': status,
                'preuve_fige': {
                    'verifie': bool(valid), 'horodatage_avant_depart': bool(valid),
                    'sha256_verifie': bool(valid), 'pv_verifie': bool(valid),
                    'certification_externe': False,
                },
            }
            if fig.exists():
                entry['fichier_fige'] = fig.relative_to(ROOT).as_posix()
            if pv.exists():
                entry['fichier_pv'] = pv.relative_to(ROOT).as_posix()
            if digest:
                entry['sha256'] = digest
            if valid:
                entry.update({'pv': archive['pv'], 'version': archive['version'],
                              'fige_a': archive['fige_a']})
            output.append(entry)
        except (ValueError, KeyError, TypeError) as e:
            warnings.append(str(course.get('id', '?')) + ' : ' + str(e))
            if args.strict_input:
                raise
    output.sort(key=lambda x: date_iso(x['depart']))
    publication = {
        'logiciel': 'TURBOFUSION 3.0', 'date': instant.date().isoformat(),
        'genere_a': instant.isoformat(), 'statut_collecte': 'structure_validee',
        'moteurs': list(MOTEURS), 'courses': output, 'audits': [],
        'avertissements': warnings + [
            'Origine des données non vérifiée indépendamment.',
            'FIGÉS avec PV local, sans certification externe indépendante.',
            'Aucun pari réel exécuté. Aucune garantie de gain.',
        ],
    }
    atomic_write(PUBLICATION, publication)
    print('TURBOFUSION :', len(output), 'course(s),',
          sum(x['statut'] == 'fige' for x in output), 'FIGÉ(s) avec PV.')
    for w in warnings:
        print('AVERTISSEMENT :', w, file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--diagnostic', action='store_true')
    p.add_argument('--figer', action='store_true')
    p.add_argument('--strict-input', action='store_true')
    p.add_argument('--safety-minutes', type=int, default=2)
    a = p.parse_args()
    if a.safety_minutes < 0:
        p.error('safety-minutes doit être positif ou nul')
    if a.diagnostic:
        print('TURBOFUSION 3.0 —', now().isoformat())
        for n, (s, criteria) in MOTEURS.items():
            print(n, s, '—', ', '.join(criteria))
        print('Source présente :', SOURCE.is_file())
        print('Diagnostic structurel, pas de pronostic certifié.')
    else:
        run(a)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
        print('ERREUR TURBOFUSION :', e, file=sys.stderr)
        sys.exit(1)
            
