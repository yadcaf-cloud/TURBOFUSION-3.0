#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 3.0 — audit prudent des FIGÉS M1–M5.

Usage: python audit_figes.py --results data/arrivees_officielles.json
Un audit n'est dit officiel que si la provenance des résultats et
l'antériorité de publication sont vérifiées indépendamment.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

PARIS = ZoneInfo('Europe/Paris')
MOTEURS = ('M1', 'M2', 'M3', 'M4', 'M5')


def lire(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Clé JSON dupliquée : {key}')
            result[key] = value
        return result

    def constante_invalide(value):
        raise ValueError(f'Constante JSON interdite : {value}')

    return json.loads(Path(path).read_text(encoding='utf-8'),
                      object_pairs_hook=unique,
                      parse_constant=constante_invalide)


def empreinte(objet):
    contenu = json.dumps(objet, ensure_ascii=False, sort_keys=True,
                         allow_nan=False).encode('utf-8')
    return hashlib.sha256(contenu).hexdigest()


def heure(texte):
    if not isinstance(texte, str):
        raise ValueError('Horodatage absent ou invalide')
    date = dt.datetime.fromisoformat(texte.replace('Z', '+00:00'))
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError('Horodatage sans fuseau')
    return date.astimezone(dt.timezone.utc)


def numeros(valeurs, libelle, longueur_min=1):
    if (not isinstance(valeurs, list) or len(valeurs) < longueur_min
            or any(type(n) is not int or n <= 0 for n in valeurs)
            or len(set(valeurs)) != len(valeurs)):
        raise ValueError(f'{libelle} invalide')
    return valeurs


def verifier_fige(fichier, marge):
    record = lire(fichier)
    if not isinstance(record, dict):
        raise ValueError('Enveloppe FIGÉ invalide')
    rapport = record.get('rapport')
    if not isinstance(rapport, dict):
        raise ValueError('Rapport FIGÉ absent')
    if not isinstance(record.get('sha256'), str) or empreinte(rapport) != record['sha256']:
        raise ValueError('Empreinte SHA-256 incorrecte')
    if not isinstance(rapport.get('id'), str) or not rapport['id'].strip():
        raise ValueError('Identifiant de course absent')
    depart = heure(rapport.get('depart'))
    fige_a = heure(record.get('fige_a'))
    if fige_a >= depart - dt.timedelta(minutes=marge):
        raise ValueError('FIGÉ trop tardif selon son horodatage déclaré')
    moteurs = rapport.get('moteurs')
    if not isinstance(moteurs, dict):
        raise ValueError('Moteurs absents')
    qualifies = 0
    for nom in MOTEURS:
        moteur = moteurs.get(nom)
        if moteur is None:
            continue
        if not isinstance(moteur, dict):
            raise ValueError(f'Moteur {nom} invalide')
        if moteur.get('qualification') == 'candidate':
            qualifies += 1
            numeros(moteur.get('ordre_arrivee_espere'), f'Classement {nom}')
    if not qualifies:
        raise ValueError('Aucun moteur qualifié')
    return record


def verifier_resultat(resultat):
    if not isinstance(resultat, dict):
        raise ValueError('Résultat invalide')
    arrivee = numeros(resultat.get('arrivee'), 'Arrivée officielle', 5)
    if resultat.get('statut') != 'definitive':
        raise ValueError('Arrivée non définitive')
    url = resultat.get('source')
    if not isinstance(url, str):
        raise ValueError('Source absente')
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('URL de source HTTPS invalide')
    np = numeros(resultat['non_partants'], 'Non-partants', 0) if 'non_partants' in resultat else []
    if set(arrivee) & set(np):
        raise ValueError('Cheval présent dans arrivée et non-partants')
    return arrivee, np


def evaluer(record, resultat):
    rapport = record['rapport']
    arrivee, np = verifier_resultat(resultat)
    evaluations = {}
    for nom in MOTEURS:
        moteur = rapport['moteurs'].get(nom) or {}
        if moteur.get('qualification') != 'candidate':
            evaluations[nom] = {'statut': 'abstention'}
            continue
        ordre = moteur['ordre_arrivee_espere']
        if set(ordre) & set(np):
            evaluations[nom] = {
                'statut': 'non_evaluable_np',
                'numeros_np_selectionnes': sorted(set(ordre) & set(np))
            }
            continue
        evaluations[nom] = {
            'statut': 'compare',
            'ordre_espere': ordre,
            'gagnant_correct': ordre[0] == arrivee[0],
            'premier_dans_trois': ordre[0] in arrivee[:3],
            'chevaux_dans_cinq': len(set(ordre[:5]) & set(arrivee[:5])),
            'ordre_exact_top5': len(ordre) >= 5 and ordre[:5] == arrivee[:5],
            'pari_reel': 'non_verifie'
        }
    return {
        'id': rapport['id'], 'depart': rapport['depart'],
        'fige_a_declare': record['fige_a'], 'sha256': record['sha256'],
        'source_arrivee_declaree': resultat['source'],
        'arrivee_declaree': arrivee, 'non_partants_declares': np,
        'moteurs': evaluations,
        'statut': 'comparaison_documentaire_non_certifiee',
        'preuve_publication_avant_depart': 'non_verifiee',
        'preuve_source_officielle': 'non_verifiee'
    }


def ecrire_nouveau(path, objet):
    path.parent.mkdir(parents=True, exist_ok=True)
    contenu = json.dumps(objet, ensure_ascii=False, indent=2,
                         sort_keys=True, allow_nan=False) + '\n'
    # Création exclusive : aucune archive existante n'est écrasée.
    with path.open('x', encoding='utf-8') as sortie:
        sortie.write(contenu)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--results', type=Path,
                        default=Path('data/arrivees_officielles.json'))
    parser.add_argument('--safety-minutes', type=int, default=2)
    args = parser.parse_args()
    if args.safety_minutes < 0:
        parser.error('Marge de sécurité négative')
    if not args.results.is_file():
        print('Arrivées absentes : aucun audit de performance créé.')
        return 0
    source = lire(args.results)
    if not isinstance(source, dict) or not isinstance(source.get('courses'), list):
        raise ValueError('Format des arrivées invalide')
    resultats = {}
    for item in source['courses']:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'].strip():
            raise ValueError('Identifiant de résultat invalide')
        if item['id'] in resultats:
            raise ValueError(f'Résultat dupliqué : {item["id"]}')
        resultats[item['id']] = item

    audits, erreurs, vus = [], [], set()
    for fichier in sorted((args.data / 'figes').glob('*/*.json')):
        try:
            record = verifier_fige(fichier, args.safety_minutes)
            cid = record['rapport']['id']
            if cid not in resultats:
                continue
            cle = (cid, record['sha256'])
            if cle in vus:
                continue
            vus.add(cle)
            audit = evaluer(record, resultats[cid])
            audit['fichier_fige'] = str(fichier)
            audits.append(audit)
        except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
            erreurs.append({'fichier': str(fichier), 'erreur': str(exc)})

    sortie = {
        'logiciel': 'TURBOFUSION 3.0',
        'genere_a': dt.datetime.now(PARIS).isoformat(),
        'statut': 'comparaison_partielle' if erreurs else 'comparaison_documentaire',
        'audits': audits, 'erreurs': erreurs,
        'avertissement': (
            'Le SHA-256 prouve seulement la cohérence du contenu. '
            'La date déclarée, la publication antérieure et la provenance '
            'officielle des résultats nécessitent des preuves indépendantes. '
            'Aucun pari ni gain réel n’est certifié.'
        )
    }
    horodatage = dt.datetime.now(PARIS).strftime('%Y%m%dT%H%M%S%f')
    chemin = args.data / f'audit_documentaire_{horodatage}_{os.getpid()}.json'
    ecrire_nouveau(chemin, sortie)
    print(f'Audits documentaires : {len(audits)} ; anomalies : {len(erreurs)}')
    print(f'Archive créée : {chemin}')
    return 1 if erreurs else 0


if __name__ == '__main__':
    raise SystemExit(main())
