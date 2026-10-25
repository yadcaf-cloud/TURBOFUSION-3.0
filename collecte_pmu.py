#!/usr/bin/env python3
"""Collecte PMU française; n'invente jamais de scores sportifs."""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo('Europe/Paris')
BASE = os.environ.get(
    'PMU_API_BASE',
    'https://online.turfinfo.api.pmu.fr/rest/client/61'
).rstrip('/')
OUT = Path('data/courses.json')


def get_json(url):
    last = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    'Accept': 'application/json',
                    'User-Agent': 'TURBOFUSION-3.0/2.0'
                }
            )
            with urllib.request.urlopen(request, timeout=18) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            last = error
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f'PMU indisponible: {last}')


def label(value):
    if isinstance(value, dict):
        return str(
            value.get('libelleLong')
            or value.get('libelleCourt')
            or value.get('libelle')
            or value.get('nom')
            or ''
        )
    return str(value or '')


def number(value):
    try:
        if isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def instant(value):
    if value is None:
        return None
    try:
        if isinstance(value, (float, int)):
            return dt.datetime.fromtimestamp(
                value / 1000 if value > 1e11 else value,
                dt.timezone.utc
            ).isoformat()
        parsed = dt.datetime.fromisoformat(
            str(value).replace('Z', '+00:00')
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=PARIS)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def collect():
    today = dt.datetime.now(PARIS).date()
    stamp = today.strftime('%d%m%Y')
    url = f'{BASE}/programme/{stamp}'
    payload = get_json(url)
    reunions = (payload.get('programme') or {}).get('reunions') or []

    if not isinstance(reunions, list) or not reunions:
        raise RuntimeError('Programme PMU vide ou format modifié')

    courses = []
    failures = []

    for reunion in reunions:
        if not isinstance(reunion, dict):
            continue

        country = label(
            reunion.get('paysCode') or reunion.get('pays')
        ).upper()

        if country not in ('FR', 'FRA', 'FRANCE'):
            continue

        r = number(reunion.get('numOfficiel'))
        if r is None:
            continue

        for raw in reunion.get('courses') or []:
            if not isinstance(raw, dict):
                continue

            c = number(raw.get('numOrdre'))
            start = instant(
                raw.get('heureDepart')
                or raw.get('heureDepartPrevue')
            )

            if c is None or start is None:
                continue

            if dt.datetime.fromisoformat(start).astimezone(PARIS).date() != today:
                continue

            participants_url = (
                f'{BASE}/programme/{stamp}/R{r}/C{c}/participants'
            )

            runners = []

            try:
                detail = get_json(participants_url)
                participants = (
                    detail.get('participants')
                    if isinstance(detail, dict)
                    else detail
                )

                if not isinstance(participants, list):
                    raise ValueError(
                        'Participants absents ou format inconnu'
                    )

                for horse in participants:
                    if not isinstance(horse, dict):
                        continue

                    n = number(
                        horse.get('numPmu') or horse.get('numero')
                    )
                    name = label(horse.get('nom'))

                    if n is None or not name:
                        continue

                    runners.append({
                        'numero': n,
                        'nom': name,
                        'non_partant': (
                            horse.get('statut') == 'NON_PARTANT'
                            or horse.get('nonPartant') is True
                        ),
                        'jockey_nom': label(
                            horse.get('jockey') or horse.get('driver')
                        ),
                        'entraineur_nom': label(
                            horse.get('entraineur')
                        ),
                    })

            except (RuntimeError, ValueError) as error:
                failures.append(f'R{r}C{c}: {error}')

            courses.append({
                'id': f'{today.isoformat()}-R{r}-C{c}',
                'reunion': r,
                'course': c,
                'hippodrome': label(reunion.get('hippodrome')),
                'nom': label(raw.get('libelle')),
                'depart': start,
                'distance_metres': number(raw.get('distance')),
                'discipline': label(raw.get('discipline')),
                'source': participants_url,
                'partants': runners,
                'collecte_participants': (
                    'ok' if runners else 'indisponible'
                ),
            })

    if not courses:
        raise RuntimeError(
            'Aucune course française dans le programme'
        )

    courses.sort(key=lambda c: (c['depart'], c['id']))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.json.tmp')

    tmp.write_text(
        json.dumps(
            {
                'date': today.isoformat(),
                'collecte_a': dt.datetime.now(
                    dt.timezone.utc
                ).isoformat(),
                'source': url,
                'erreurs_participants': failures,
                'courses': courses,
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False
        ) + '\n',
        encoding='utf-8'
    )

    os.replace(tmp, OUT)

    print(
        f'Collecte: {len(courses)} courses, '
        f'{len(failures)} erreurs de participants'
    )


if __name__ == '__main__':
    try:
        collect()
    except (RuntimeError, OSError, ValueError) as exc:
        print(f'ERREUR COLLECTE: {exc}', file=sys.stderr)
        sys.exit(1)
        
