#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 3.0 — cinq moteurs indépendants, audits et FIGÉS pré-départ.

Aucune note sportive inventée. Aucun pari réel exécuté.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
FEATURES = ("forme", "aptitude", "regularite", "jockey",
            "entraineur", "distance", "terrain")
WEIGHTS = {
    "M1": (4, 3, 3, 1, 1, 2, 2),
    "M2": (2, 4, 2, 2, 1, 3, 3),
    "M3": (3, 2, 4, 2, 2, 1, 1),
    "M4": (2, 2, 2, 4, 4, 1, 1),
    "M5": (3, 3, 3, 2, 2, 3, 2),
}
MIN_COVERAGE = 0.70
MIN_GAP = 0.035


def now():
    return dt.datetime.now(PARIS)


def serialized(data):
    return json.dumps(data, ensure_ascii=False, indent=2,
                      sort_keys=True, allow_nan=False) + "\n"


def write_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + str(os.getpid()) + ".tmp")
    try:
        temp.write_text(serialized(data), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def load_courses(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("courses"), list):
        raise ValueError('Format attendu : {"courses": [...]}')
    if not data["courses"]:
        raise ValueError("Aucune course disponible")
    return data["courses"]


def departure(course):
    value = course["depart"]
    if not isinstance(value, str):
        raise ValueError("Horaire de depart invalide")
    instant = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Date de depart sans fuseau horaire")
    return instant.astimezone(PARIS)


def validate_runners(course):
    runners = course.get("partants")
    if not isinstance(runners, list) or len(runners) < 2:
        raise ValueError("Liste des partants absente ou insuffisante")
    numbers = set()
    active = []
    for horse in runners:
        if not isinstance(horse, dict):
            raise ValueError("Fiche cheval invalide")
        raw_number = horse.get("numero")
        if isinstance(raw_number, bool) or not isinstance(raw_number, (int, str)):
            raise ValueError("Numero de cheval invalide")
        try:
            numero = int(raw_number)
        except ValueError as exc:
            raise ValueError("Numero de cheval invalide") from exc
        if numero <= 0 or numero in numbers:
            raise ValueError("Numero nul, negatif ou duplique")
        numbers.add(numero)
        if not str(horse.get("nom") or "").strip():
            raise ValueError(f"Nom manquant pour le numero {numero}")
        for feature in FEATURES:
            if feature not in horse or horse[feature] is None:
                continue
            value = horse[feature]
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f"Score invalide : {feature}, cheval {numero}")
        if not horse.get("non_partant", False):
            active.append(horse)
    if len(active) < 2:
        raise ValueError("Moins de deux chevaux actifs")
    return runners, active


def analyze_engine(engine, weights, horses, at, start):
    ranking = []
    for horse in horses:
        present = [
            (float(horse[feature]), weight)
            for feature, weight in zip(FEATURES, weights)
            if horse.get(feature) is not None
        ]
        coverage = len(present) / len(FEATURES)
        score = (sum(value * weight for value, weight in present)
                 / sum(weight for _, weight in present)) if present else 0.0
        ranking.append({
            "numero": int(horse["numero"]),
            "nom": str(horse["nom"]),
            "score": round(score, 4),
            "couverture": round(coverage, 3),
        })
    ranking.sort(key=lambda h: (-h["score"], -h["couverture"], h["numero"]))
    first, second = ranking[:2]
    gap = first["score"] - second["score"]
    eligible = (
        first["couverture"] >= MIN_COVERAGE
        and second["couverture"] >= MIN_COVERAGE
        and gap >= MIN_GAP
        and at < start
    )
    if eligible:
        motif = "Criteres du moteur satisfaits"
    elif at >= start:
        motif = "Depart atteint ou depasse"
    elif first["couverture"] < MIN_COVERAGE or second["couverture"] < MIN_COVERAGE:
        motif = "Donnees sportives insuffisantes"
    else:
        motif = "Ecart de score insuffisant"
    return {
        "moteur": engine,
        "classement": ranking[:5],
        "gagnant_espere": first["numero"] if eligible else None,
        "place_espere": second["numero"] if eligible else None,
        "ecart": round(gap, 4),
        "qualification": "candidate" if eligible else "abstention",
        "motif": motif,
        "pari": "aucun pari automatique",
        "couverture": first["couverture"],
    }


def analyze(course, at):
    cid = str(course.get("id", "inconnu"))
    try:
        if not cid.strip() or cid == "inconnu":
            raise ValueError("Identifiant de course manquant")
        start = departure(course)
        source = course.get("source")
        if not isinstance(source, str) or not source.strip() or source == "non_documentee":
            raise ValueError("Source de course non documentee")
        runners, active = validate_runners(course)
        motors = {
            engine: analyze_engine(engine, weights, active, at, start)
            for engine, weights in WEIGHTS.items()
        }
        candidates = [
            name for name, result in motors.items()
            if result["qualification"] == "candidate"
        ]
        return {
            "id": cid,
            "hippodrome": course.get("hippodrome", ""),
            "depart": start.isoformat(),
            "partants": len(active),
            "non_partants": len(runners) - len(active),
            "source": source,
            "moteurs": motors,
            "moteurs_qualifies": candidates,
            "statut": "analyse_provisoire",
            "analyse_a": at.isoformat(),
        }
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        return {"id": cid, "statut": "rejetee",
                "motif": str(exc), "analyse_a": at.isoformat()}


def verify_frozen(record, course_id, safety_minutes):
    try:
        report = record["rapport"]
        payload = json.dumps(report, ensure_ascii=False, sort_keys=True,
                             allow_nan=False).encode("utf-8")
        if hashlib.sha256(payload).hexdigest() != record["sha256"]:
            return False
        if report["id"] != course_id:
            return False
        frozen_at = dt.datetime.fromisoformat(record["fige_a"])
        start = dt.datetime.fromisoformat(report["depart"])
        if frozen_at.tzinfo is None or start.tzinfo is None:
            return False
        if frozen_at >= start - dt.timedelta(minutes=safety_minutes):
            return False
        if not any(m.get("qualification") == "candidate"
                   for m in report["moteurs"].values()):
            return False
        return True
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def freeze(report, output_dir, date, at, safety_minutes):
    if report["statut"] != "analyse_provisoire":
        return report
    start = dt.datetime.fromisoformat(report["depart"])
    safe_id = "".join(
        c if c.isascii() and (c.isalnum() or c in "-_") else "_"
        for c in report["id"]
    )[:65]
    identity = hashlib.sha256(report["id"].encode("utf-8")).hexdigest()[:16]
    folder = Path(output_dir) / "figes" / date
    target = folder / (safe_id + "_" + identity + ".json")

    if target.exists():
        try:
            record = json.loads(target.read_text(encoding="utf-8"))
            valid = verify_frozen(record, report["id"], safety_minutes)
        except (OSError, ValueError):
            valid = False
        report["statut"] = "fige_existant" if valid else "fige_invalide"
        report["fichier_fige"] = str(target)
        return report

    if at >= start - dt.timedelta(minutes=safety_minutes):
        report["motif_fige"] = "Delai de securite depasse"
        return report

    qualified = [
        name for name, motor in report["moteurs"].items()
        if motor["qualification"] == "candidate"
    ]
    if not qualified:
        report["motif_fige"] = "Aucun moteur qualifie"
        return report

    folder.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True,
                         allow_nan=False).encode("utf-8")
    record = {
        "rapport": dict(report),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "fige_a": at.isoformat(),
    }
    try:
        with target.open("x", encoding="utf-8") as file:
            file.write(serialized(record))
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError:
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            valid = verify_frozen(existing, report["id"], safety_minutes)
        except (OSError, ValueError):
            valid = False
        report["statut"] = "fige_existant" if valid else "fige_invalide"
    else:
        report["statut"] = "fige"
    report["fichier_fige"] = str(target)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=now().date().isoformat())
    parser.add_argument("--input", type=Path, default=Path("data/courses.json"))
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--figer", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--strict-input", action="store_true")
    parser.add_argument("--safety-minutes", type=int, default=2)
    args = parser.parse_args(argv)

    if args.diagnostic:
        print(serialized({
            "logiciel": "TURBOFUSION 3.0",
            "python": sys.version.split()[0],
            "timezone": str(PARIS),
            "moteurs": list(WEIGHTS),
            "source_presente": args.input.is_file(),
            "paris_reels": "desactives",
        }))
        return 0

    try:
        dt.date.fromisoformat(args.date)
    except ValueError:
        parser.error("Date invalide : AAAA-MM-JJ")
    if args.safety_minutes < 0:
        parser.error("--safety-minutes doit etre positif")

    at = now()
    reports = []
    status = "ok"

    if not args.input.is_file():
        if args.strict_input:
            parser.error("Fichier absent : " + str(args.input))
        status = "en_attente_donnees"
    else:
        try:
            courses = load_courses(args.input)
        except (OSError, ValueError) as exc:
            parser.error("Entree invalide : " + str(exc))
        seen = set()
        for course in courses:
            if not isinstance(course, dict):
                reports.append({"statut": "rejetee", "motif": "Course non objet"})
                continue
            try:
                course_date = departure(course).date().isoformat()
                if course_date != args.date:
                    continue
            except (KeyError, TypeError, ValueError, OverflowError):
                pass
            cid = str(course.get("id", "")).strip()
            if cid and cid in seen:
                reports.append({"id": cid, "statut": "rejetee",
                                "motif": "Identifiant duplique"})
                continue
            seen.add(cid)
            report = analyze(course, at)
            if args.figer:
                report = freeze(report, args.output, args.date,
                                at, args.safety_minutes)
            reports.append(report)
        if not reports:
            status = "aucune_course_verifiee"

    audit = {
        "date": args.date,
        "genere_a": at.isoformat(),
        "statut_collecte": status,
        "courses": reports,
        "source": str(args.input) if args.input.is_file() else None,
        "avertissement": (
            "Aucune garantie de gain ; donnees sportives verifiees requises"
        ),
    }
    write_atomic(args.output / ("audit_" + args.date + ".json"), audit)
    write_atomic(args.output / "audit_latest.json", audit)

    from publish_data import publish
    publish(data_dir=args.output)
    print(serialized({
        "logiciel": "TURBOFUSION 3.0",
        "statut": status,
        "courses": len(reports),
        "moteurs": list(WEIGHTS),
        "candidatures": sum(len(r.get("moteurs_qualifies", [])) for r in reports),
        "figees": sum(r.get("statut") == "fige" for r in reports),
        "heure_paris": at.isoformat(),
    }))
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
    
