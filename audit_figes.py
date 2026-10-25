#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 3.0 — audit vérifiable des FIGÉS M1–M5.
Usage: python audit_figes.py --results data/arrivees_officielles.json
Le fichier des arrivées doit être fourni par une source officielle contrôlée.
Format: {"courses":[{"id":"2026-10-25-R1-C1","arrivee":[4,2,7,1,5],
"source":"https://...","statut":"definitive"}]}
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo('Europe/Paris')
MOTEURS = ('M1', 'M2', 'M3', 'M4', 'M5')


def lire(path):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f'Clé JSON dupliquée: {k}')
            out[k] = v
        return out

    def invalide(x):
        raise ValueError(f'Nombre JSON interdit: {x}')

    return json.loads(
        Path(path).read_text(encoding='utf-8'),
        object_pairs_hook=unique,
        parse_constant=invalide
    )


def empreinte(rapport):
    payload = json.dumps(
        rapport,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False
    ).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def heure(s):
    x = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
    if x.tzinfo is None or x.utcoffset() is None:
        raise ValueError('Horodatage sans fuseau')
    return x.astimezone(dt.timezone.utc)


def verifier_fige(fichier, marge):
    record = lire(fichier)
    rapport = record['rapport']

    if empreinte(rapport) != record['sha256']:
        raise ValueError('Empreinte SHA-256 incorrecte')

    if heure(record['fige_a']) >= heure(
        rapport['depart']
    ) - dt.timedelta(minutes=marge):
        raise ValueError('FIGÉ trop tardif')

    if not isinstance(rapport.get('id'), str) or not rapport['id']:
        raise ValueError('Identifiant absent')

    moteurs = rapport.get('moteurs')
    if not isinstance(moteurs, dict):
        raise ValueError('Moteurs absents')

    qualifies = [
        m for m in MOTEURS
        if isinstance(moteurs.get(m), dict)
        and moteurs[m].get('qualification') == 'candidate'
    ]

    if not qualifies:
        raise ValueError('Aucun moteur qualifié')

    for m in qualifies:
        ordre = moteurs[m].get('ordre_arrivee_espere')
        if (
            not isinstance(ordre, list)
            or not ordre
            or any(type(n) is not int or n <= 0 for n in ordre)
            or len(set(ordre)) != len(ordre)
        ):
            raise ValueError(f'Classement invalide: {m}')

    return record


def evaluer(record, resultat):
    rapport = record['rapport']
    arrivee = resultat['arrivee']

    if (
        not isinstance(arrivee, list)
        or not arrivee
        or any(type(n) is not int or n <= 0 for n in arrivee)
        or len(set(arrivee)) != len(arrivee)
    ):
        raise ValueError('Arrivée invalide')

    if (
        resultat.get('statut') != 'definitive'
        or not str(resultat.get('source') or '').startswith(
            ('https://', 'http://')
        )
    ):
        raise ValueError('Résultat non confirmé / source manquante')

    evaluations = {}

    for nom in MOTEURS:
        moteur = rapport['moteurs'].get(nom, {})

        if moteur.get('qualification') != 'candidate':
            evaluations[nom] = {'statut': 'abstention'}
            continue

        ordre = moteur['ordre_arrivee_espere']

        evaluations[nom] = {
            'statut': 'audite',
            'ordre_espere': ordre,
            'gagnant_correct': ordre[0] == arrivee[0],
            'premier_dans_trois': ordre[0] in arrivee[:3],
            'chevaux_dans_cinq': len(
                set(ordre[:5]) & set(arrivee[:5])
            ),
            'ordre_exact': (
                ordre[:len(arrivee)] == arrivee[:len(ordre)]
            ),
            'pari_reel': 'non_verifie',
        }

    return {
        'id': rapport['id'],
        'depart': rapport['depart'],
        'fige_a': record['fige_a'],
        'sha256': record['sha256'],
        'source_arrivee': resultat['source'],
        'arrivee_officielle': arrivee,
        'moteurs': evaluations,
        'statut': 'audite',
    }


def ecrire(path, objet):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(
        '.' + path.name + f'.{os.getpid()}.tmp'
    )

    try:
        temp.write_text(
            json.dumps(
                objet,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False
            ) + '\n',
            encoding='utf-8'
        )
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--data',
        type=Path,
        default=Path('data')
    )
    parser.add_argument(
        '--results',
        type=Path,
        default=Path('data/arrivees_officielles.json')
    )
    parser.add_argument(
        '--safety-minutes',
        type=int,
        default=2
    )

    args = parser.parse_args()

    if args.safety_minutes < 0:
        parser.error('Marge de sécurité négative')

    if not args.results.is_file():
        print(
            'Arrivées officielles absentes : '
            'aucun audit de performance fabriqué.'
        )
        return 0

    source = lire(args.results)

    if (
        not isinstance(source, dict)
        or not isinstance(source.get('courses'), list)
    ):
        raise ValueError('Format des arrivées invalide')

    resultats = {}

    for item in source['courses']:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get('id'), str)
            or item['id'] in resultats
        ):
            raise ValueError('Résultat dupliqué ou invalide')

        resultats[item['id']] = item

    audits, erreurs = [], []

    for fichier in sorted(
        (args.data / 'figes').glob('*/*.json')
    ):
        try:
            record = verifier_fige(
                fichier,
                args.safety_minutes
            )
            cid = record['rapport']['id']

            if cid in resultats:
                audits.append(
                    evaluer(record, resultats[cid])
                )

        except (
            ValueError,
            TypeError,
            KeyError,
            OSError
        ) as exc:
            erreurs.append({
                'fichier': str(fichier),
                'erreur': str(exc)
            })

    sortie = {
        'logiciel': 'TURBOFUSION 3.0',
        'genere_a': dt.datetime.now(PARIS).isoformat(),
        'statut': (
            'audit_partiel' if erreurs else 'audit_execute'
        ),
        'audits': audits,
        'erreurs': erreurs,
        'avertissement': (
            'SHA-256 prouve l’intégrité du contenu, '
            'pas à lui seul son antériorité ni '
            'l’authenticité des résultats.'
        )
    }

    ecrire(
        args.data / 'audits_officiels.json',
        sortie
    )

    print(
        f"Audits: {len(audits)} ; "
        f"anomalies: {len(erreurs)}"
    )

    return 1 if erreurs else 0


if __name__ == '__main__':
    raise SystemExit(main())
             
