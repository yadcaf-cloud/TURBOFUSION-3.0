#!/usr/bin/env python3
"""Collecte prudente des programmes PMU pour TURBOFUSION 3.0.

Interface PMU non contractuelle : les endpoints et leur schéma peuvent changer.
Aucune note prédictive n'est inventée.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
BASE = os.getenv(
    "PMU_API_BASE",
    "https://online.turfinfo.api.pmu.fr/rest/client/61"
).rstrip("/")
OUTPUT = Path("data/courses.json")
MAX_BYTES = 8_000_000


def fetch_json(path):
    url = BASE + path
    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 TURBOFUSION/3.0",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("Réponse PMU trop volumineuse")
                return json.loads(raw.decode("utf-8-sig"))
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(f"Échec requête {path}: {last_error}")


def iso_depart(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000 if value > 10**11 else value
        return datetime.fromtimestamp(
            seconds, timezone.utc
        ).astimezone(PARIS).isoformat()

    if isinstance(value, str):
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            raise ValueError("Départ sans fuseau")
        return d.astimezone(PARIS).isoformat()

    raise ValueError("Horaire de départ inconnu")


def pick(obj, *keys):
    for key in keys:
        value = obj.get(key)
        if value is not None and value != "":
            return value
    return None


def name(obj):
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, dict):
        return str(
            pick(obj, "libelle", "nom", "name") or ""
        ).strip()
    return ""


def participants(reunion, course, date_pmu):
    rid = pick(reunion, "numOfficiel", "numReunion")
    cid = pick(course, "numOrdre", "numCourse")

    if rid is None or cid is None:
        raise ValueError("Identifiants réunion/course manquants")

    path = (
        f"/programme/{date_pmu}/R{int(rid)}"
        f"/C{int(cid)}/participants"
    )
    payload = fetch_json(path)

    entries = (
        payload if isinstance(payload, list)
        else payload.get("participants", [])
    )
    if not isinstance(entries, list):
        raise ValueError("Liste de participants invalide")

    result = []
    seen = set()

    for horse in entries:
        if not isinstance(horse, dict):
            continue

        try:
            number = int(
                pick(horse, "numPmu", "numero", "numCheval")
            )
        except (TypeError, ValueError):
            continue

        horse_name = name(
            pick(horse, "nom", "nomCheval")
        )

        if number <= 0 or number in seen or not horse_name:
            continue

        seen.add(number)

        record = {
            "numero": number,
            "nom": horse_name,
            "non_partant": bool(
                horse.get("nonPartant", False)
            ),
        }

        for target, keys in {
            "jockey_nom": ("nomJockey", "jockey"),
            "entraineur_nom": (
                "nomEntraineur", "entraineur"
            ),
            "driver_nom": ("nomDriver", "driver"),
        }.items():
            value = name(pick(horse, *keys))
            if value:
                record[target] = value

        result.append(record)

    return result


def collect():
    today = datetime.now(PARIS).date()
    date_pmu = today.strftime("%d%m%Y")

    programme = fetch_json(
        f"/programme/{date_pmu}"
    )
    reunions = programme.get(
        "programme", {}
    ).get("reunions", [])

    if not isinstance(reunions, list):
        raise ValueError(
            "Structure des réunions PMU invalide"
        )

    courses = []
    errors = []

    for reunion in reunions:
        if not isinstance(reunion, dict):
            continue

        pays = name(
            pick(reunion, "pays", "paysLibelle")
        )
        if pays and pays.upper() not in (
            "FRANCE", "FR", "FRA"
        ):
            continue

        for course in reunion.get("courses", []):
            try:
                rid = int(
                    pick(
                        reunion,
                        "numOfficiel",
                        "numReunion",
                    )
                )
                cid = int(
                    pick(
                        course,
                        "numOrdre",
                        "numCourse",
                    )
                )

                depart = iso_depart(
                    pick(
                        course,
                        "heureDepart",
                        "heureDepartPrevue",
                    )
                )

                if (
                    datetime.fromisoformat(depart).date()
                    != today
                ):
                    continue

                runners = participants(
                    reunion, course, date_pmu
                )

                if len(runners) < 2:
                    raise ValueError(
                        "Moins de deux chevaux identifiés"
                    )

                item = {
                    "id": (
                        f"{today.isoformat()}"
                        f"-R{rid}-C{cid}"
                    ),
                    "hippodrome": name(
                        pick(
                            reunion,
                            "hippodrome",
                            "libelleHippodrome",
                        )
                    ),
                    "reunion": rid,
                    "course": cid,
                    "depart": depart,
                    "source": (
                        BASE
                        + f"/programme/{date_pmu}"
                        + f"/R{rid}/C{cid}/participants"
                    ),
                    "partants": runners,
                }

                distance = pick(
                    course,
                    "distance",
                    "distanceMetres",
                )
                if (
                    isinstance(distance, (int, float))
                    and not isinstance(distance, bool)
                    and distance > 0
                ):
                    item["distance_metres"] = distance

                courses.append(item)

            except (
                ValueError,
                TypeError,
                KeyError,
                RuntimeError,
            ) as exc:
                errors.append(
                    f"R{reunion.get('numOfficiel', '?')} "
                    f"C{course.get('numOrdre', '?')}: "
                    f"{exc}"
                )

    if not courses:
        raise RuntimeError(
            "Aucune course française valide récupérée; "
            "ancien fichier conservé. "
            + "; ".join(errors[:3])
        )

    courses.sort(
        key=lambda x: (x["depart"], x["id"])
    )

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )
    temp = OUTPUT.with_suffix(".json.tmp")

    try:
        temp.write_text(
            json.dumps(
                {"courses": courses},
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            ) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, OUTPUT)
    finally:
        temp.unlink(missing_ok=True)

    print(
        f"Collecte : {len(courses)} courses "
        f"françaises; {len(errors)} avertissements"
    )

    for error in errors[:10]:
        print("AVERTISSEMENT :", error)


if __name__ == "__main__":
    try:
        collect()
    except Exception as exc:
        print(
            "ERREUR COLLECTE :", exc,
            file=sys.stderr
        )
        sys.exit(1)
                
