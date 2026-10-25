#!/usr/bin/env python3
"""TURBOFUSION 3.0 - Collecte des programmes PMU."""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
BASE = os.getenv(
    "PMU_API_BASE",
    "https://online.turfinfo.api.pmu.fr/rest/client/1"
).rstrip("/")
SORTIE = Path("data/publication_latest.json")
TIMEOUT = 20


def maintenant():
    return datetime.now(timezone.utc).isoformat()


def telecharger(url):
    erreur = None
    for essai in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "TURBOFUSION-3.0/1.0"
                }
            )
            with urllib.request.urlopen(
                req, timeout=TIMEOUT
            ) as rep:
                return json.load(rep)
        except (
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            OSError
        ) as exc:
            erreur = exc
            if essai < 2:
                time.sleep(2 ** essai)
    raise RuntimeError(
        f"Source PMU inaccessible : {erreur}"
    )


def liste(valeur):
    return valeur if isinstance(valeur, list) else []


def texte(valeur):
    if isinstance(valeur, dict):
        return str(
            valeur.get("libelleLong")
            or valeur.get("libelleCourt")
            or valeur.get("libelle")
            or valeur.get("nom")
            or ""
        )
    return str(valeur or "")


def date_depart(valeur):
    if valeur is None:
        return None
    try:
        if isinstance(valeur, (int, float)):
            # Le PMU utilise des timestamps en millisecondes.
            return datetime.fromtimestamp(
                valeur / 1000 if valeur > 1e11 else valeur,
                tz=timezone.utc
            ).isoformat()
        if isinstance(valeur, str):
            dt = datetime.fromisoformat(
                valeur.replace("Z", "+00:00")
            )
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=PARIS)
            return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        pass
    return None


def entier(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def main():
    date = datetime.now(PARIS).strftime("%d%m%Y")
    url = f"{BASE}/programme/{date}"
    brut = telecharger(url)

    reunions = liste(brut.get("programme", {}).get("reunions"))
    if not reunions:
        raise RuntimeError(
            "Aucune réunion trouvée : format PMU à vérifier"
        )

    courses = []
    total_reunions = len(reunions)

    for reunion in reunions:
        pays = texte(
            reunion.get("pays")
            or reunion.get("paysCode")
        ).upper()

        # Ne retenir que les courses physiquement en France.
        if pays not in ("FR", "FRA", "FRANCE"):
            continue

        nr = entier(reunion.get("numOfficiel"))
        if nr is None:
            continue

        hippodrome = texte(reunion.get("hippodrome"))
        for course in liste(reunion.get("courses")):
            nc = entier(course.get("numOrdre"))
            if nc is None:
                continue

            depart = date_depart(
                course.get("heureDepart")
                or course.get("heureDepartPrevue")
            )
            if not depart:
                continue

            identifiant = f"R{nr}C{nc}"
            courses.append({
                "id": identifiant,
                "reunion": nr,
                "course": nc,
                "hippodrome": hippodrome,
                "nom": texte(course.get("libelle")),
                "depart": depart,
                "partants": entier(
                    course.get("nombrePartants")
                ),
                "distance": entier(course.get("distance")),
                "discipline": texte(
                    course.get("discipline")
                ),
                "moteurs": {
                    f"M{i}": {
                        "qualification": "Non analysé",
                        "ordre_espere": []
                    }
                    for i in range(1, 6)
                },
                "statut": "Programme collecté - non figé"
            })

    courses.sort(key=lambda c: (c["depart"], c["id"]))

    if not courses:
        raise RuntimeError(
            "Aucune course française exploitable trouvée"
        )

    publication = {
        "application": "TURBOFUSION 3.0",
        "date_programme": datetime.now(PARIS).date().isoformat(),
        "genere_a": maintenant(),
        "source": BASE,
        "statut_collecte": "Programme PMU collecté",
        "reunions_source": total_reunions,
        "nombre_courses": len(courses),
        "analyses_confirmees": False,
        "courses": courses
    }

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    temporaire = SORTIE.with_suffix(".json.tmp")
    temporaire.write_text(
        json.dumps(
            publication,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )
    os.replace(temporaire, SORTIE)

    print(
        f"Collecte réussie : {len(courses)} courses françaises"
    )
    print(f"Publication : {SORTIE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERREUR COLLECTE : {exc}", file=sys.stderr)
        sys.exit(1)
