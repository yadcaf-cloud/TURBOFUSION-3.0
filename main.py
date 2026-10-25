#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🇸🇳🧠🔥 TURBOFUSION 3.0
INTELLIGENCE HIPPIQUE SPÉCIALISÉE — M1 À M5

LA MAGIE DU SAVOIR

La mémoire conserve.
L'analyse comprend.
L'expérience enseigne.

M1 : Forme et régularité
M2 : Aptitudes et conditions
M3 : Origines et entourage
M4 : Classe et stratégie
M5 : Risques et fiabilité

Fonctions :
- Lecture des courses PMU collectées
- Contrôle des partants et non-partants
- Analyse indépendante M1 à M5
- Classements par ordre d'arrivée espéré
- Qualification des moteurs
- FIGÉS pré-départ horodatés
- Empreintes SHA-256
- Conservation des historiques
- Publication du tableau officiel
- Détection des erreurs

Aucun score sportif inventé.
Aucun pari réel exécuté.
Aucune garantie de gain.
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


# ============================================================
# CONFIGURATION GÉNÉRALE
# ============================================================

VERSION = "3.0"
LOGICIEL = "TURBOFUSION 3.0"

PARIS = ZoneInfo("Europe/Paris")

DATA_DIR = Path("data")

FEATURES = (
    "forme",
    "aptitude",
    "regularite",
    "jockey",
    "entraineur",
    "distance",
    "terrain",
)

# Pondérations distinctes pour chaque moteur.
# Ce sont des règles heuristiques expérimentales,
# et non des probabilités scientifiquement calibrées.

WEIGHTS = {
    "M1": (4, 3, 3, 1, 1, 2, 2),
    "M2": (2, 4, 2, 2, 1, 3, 3),
    "M3": (3, 2, 4, 2, 2, 1, 1),
    "M4": (2, 2, 2, 4, 4, 1, 1),
    "M5": (3, 3, 3, 2, 2, 3, 2),
}

SPECIALITES = {
    "M1": "Forme et régularité",
    "M2": "Aptitudes et conditions",
    "M3": "Origines et entourage",
    "M4": "Classe et stratégie",
    "M5": "Risques et fiabilité",
}

MIN_COVERAGE = 0.70
MIN_GAP = 0.035
DEFAULT_SAFETY_MINUTES = 2


# ============================================================
# HORLOGE ET SÉRIALISATION
# ============================================================

def now():
    return dt.datetime.now(PARIS)


def serialized(data):
    return json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def write_atomic(path, data):
    """
    Écriture atomique des fichiers JSON.
    """
    path = Path(path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_name(
        path.name + "." + str(os.getpid()) + ".tmp"
    )

    try:
        temporary.write_text(
            serialized(data),
            encoding="utf-8",
        )

        os.replace(temporary, path)

    finally:
        temporary.unlink(missing_ok=True)


def sha256_report(report):
    """
    Empreinte reproductible du rapport.
    """
    payload = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


# ============================================================
# CHARGEMENT DES COURSES
# ============================================================

def load_courses(path):
    """
    Lecture stricte du fichier de collecte.
    """
    path = Path(path)

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Format JSON principal invalide"
        )

    courses = data.get("courses")

    if not isinstance(courses, list):
        raise ValueError(
            "Liste des courses absente"
        )

    if not courses:
        raise ValueError(
            "Aucune course disponible"
        )

    return courses


def departure(course):
    """
    Convertit l'heure de départ
    dans le fuseau Europe/Paris.
    """
    value = course["depart"]

    if not isinstance(value, str):
        raise ValueError(
            "Horaire de départ invalide"
        )

    instant = dt.datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if (
        instant.tzinfo is None
        or instant.utcoffset() is None
    ):
        raise ValueError(
            "Date de départ sans fuseau horaire"
        )

    return instant.astimezone(PARIS)


# ============================================================
# VALIDATION DES PARTANTS
# ============================================================

def validate_runners(course):
    """
    Vérifie :
    - Numéros uniques
    - Noms présents
    - Scores entre 0 et 1
    - Non-partants
    - Minimum deux chevaux actifs
    """

    runners = course.get("partants")

    if (
        not isinstance(runners, list)
        or len(runners) < 2
    ):
        raise ValueError(
            "Liste des partants insuffisante"
        )

    numbers = set()
    active = []

    for horse in runners:

        if not isinstance(horse, dict):
            raise ValueError(
                "Fiche cheval invalide"
            )

        raw_number = horse.get("numero")

        if (
            isinstance(raw_number, bool)
            or not isinstance(
                raw_number, (int, str)
            )
        ):
            raise ValueError(
                "Numéro de cheval invalide"
            )

        try:
            numero = int(raw_number)

        except ValueError as exc:
            raise ValueError(
                "Numéro de cheval invalide"
            ) from exc

        if numero <= 0:
            raise ValueError(
                "Numéro de cheval non positif"
            )

        if numero in numbers:
            raise ValueError(
                "Numéro de cheval dupliqué"
            )

        numbers.add(numero)

        nom = str(
            horse.get("nom") or ""
        ).strip()

        if not nom:
            raise ValueError(
                f"Nom absent pour le cheval {numero}"
            )

        for feature in FEATURES:

            value = horse.get(feature)

            if value is None:
                continue

            if (
                isinstance(value, bool)
                or not isinstance(
                    value, (int, float)
                )
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError(
                    f"Score invalide : "
                    f"{feature}, cheval {numero}"
                )

        if not horse.get(
            "non_partant", False
        ):
            active.append(horse)

    if len(active) < 2:
        raise ValueError(
            "Moins de deux chevaux actifs"
        )

    return runners, active


# ============================================================
# CALCUL INDÉPENDANT DES MOTEURS
# ============================================================

def analyze_engine(
    engine,
    weights,
    horses,
    at,
    start,
):
    """
    Analyse individuelle des chevaux.

    Le classement résulte uniquement
    des critères sportifs disponibles.

    Une donnée absente n'est jamais
    remplacée par une note fictive.
    """

    ranking = []

    for horse in horses:

        present = []

        for feature, weight in zip(
            FEATURES, weights
        ):

            value = horse.get(feature)

            if value is None:
                continue

            present.append(
                (float(value), weight)
            )

        coverage = (
            len(present) / len(FEATURES)
        )

        if present:

            weighted_sum = sum(
                value * weight
                for value, weight in present
            )

            total_weight = sum(
                weight
                for _, weight in present
            )

            score = (
                weighted_sum / total_weight
            )

        else:
            score = 0.0

        ranking.append({
            "numero": int(
                horse["numero"]
            ),
            "nom": str(
                horse["nom"]
            ),
            "score": round(
                score, 4
            ),
            "couverture": round(
                coverage, 3
            ),
        })

    ranking.sort(
        key=lambda horse: (
            -horse["score"],
            -horse["couverture"],
            horse["numero"],
        )
    )

    first = ranking[0]
    second = ranking[1]

    gap = (
        first["score"]
        - second["score"]
    )

    eligible = (
        first["couverture"]
        >= MIN_COVERAGE
        and second["couverture"]
        >= MIN_COVERAGE
        and gap >= MIN_GAP
        and at < start
    )

    if eligible:

        motif = (
            "Critères du moteur satisfaits"
        )

    elif at >= start:

        motif = (
            "Départ atteint ou dépassé"
        )

    elif (
        first["couverture"] < MIN_COVERAGE
        or second["couverture"] < MIN_COVERAGE
    ):

        motif = (
            "Données sportives insuffisantes"
        )

    else:

        motif = (
            "Écart de score insuffisant"
        )

    ordre = [
        horse["numero"]
        for horse in ranking[:5]
    ]

    return {
        "moteur": engine,
        "specialite": SPECIALITES[engine],
        "classement": ranking[:5],
        "ordre_arrivee_espere": (
            ordre if eligible else []
        ),
        "gagnant_espere": (
            first["numero"]
            if eligible else None
        ),
        "place_espere": (
            second["numero"]
            if eligible else None
        ),
        "ecart": round(gap, 4),
        "qualification": (
            "candidate"
            if eligible else "abstention"
        ),
        "motif": motif,
        "pari": (
            "aucun pari automatique"
        ),
        "couverture": (
            first["couverture"]
        ),
    }


# ============================================================
# ANALYSE COMPLÈTE D'UNE COURSE
# ============================================================

def analyze(course, at):

    cid = str(
        course.get("id", "")
    ).strip()

    try:

        if not cid:
            raise ValueError(
                "Identifiant de course manquant"
            )

        start = departure(course)

        source = course.get("source")

        if (
            not isinstance(source, str)
            or not source.strip()
            or source == "non_documentee"
        ):
            raise ValueError(
                "Source non documentée"
            )

        runners, active = (
            validate_runners(course)
        )

        motors = {}

        for engine, weights in (
            WEIGHTS.items()
        ):

            motors[engine] = (
                analyze_engine(
                    engine,
                    weights,
                    active,
                    at,
                    start,
                )
            )

        candidates = [
            name
            for name, result
            in motors.items()
            if result["qualification"]
            == "candidate"
        ]

        return {
            "id": cid,
            "hippodrome": course.get(
                "hippodrome", ""
            ),
            "depart": start.isoformat(),
            "partants": len(active),
            "non_partants": (
                len(runners) - len(active)
            ),
            "source": source,
            "moteurs": motors,
            "moteurs_qualifies": candidates,
            "statut": "analyse_provisoire",
            "analyse_a": at.isoformat(),
        }

    except (
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        AttributeError,
    ) as exc:

        return {
            "id": cid,
            "statut": "rejetee",
            "motif": str(exc),
            "analyse_a": at.isoformat(),
        }


# ============================================================
# VÉRIFICATION DES FIGÉS
# ============================================================

def verify_frozen(
    record,
    course_id,
    safety_minutes,
):
    """
    Vérifie :
    - Intégrité SHA-256
    - Identité de la course
    - FIGÉ avant départ
    - Délai de sécurité
    - Présence d'un moteur qualifié
    """

    try:

        report = record["rapport"]

        expected_hash = (
            sha256_report(report)
        )

        if (
            expected_hash
            != record["sha256"]
        ):
            return False

        if report["id"] != course_id:
            return False

        frozen_at = (
            dt.datetime.fromisoformat(
                record["fige_a"]
            )
        )

        start = (
            dt.datetime.fromisoformat(
                report["depart"]
            )
        )

        if (
            frozen_at.tzinfo is None
            or start.tzinfo is None
        ):
            return False

        if (
            frozen_at
            >= start - dt.timedelta(
                minutes=safety_minutes
            )
        ):
            return False

        motors = report["moteurs"]

        if not any(
            motor.get("qualification")
            == "candidate"
            for motor in motors.values()
        ):
            return False

        return True

    except (
        KeyError,
        ValueError,
        TypeError,
        AttributeError,
    ):
        return False


# ============================================================
# CRÉATION DES FIGÉS IMMUTABLES
# ============================================================

def freeze(
    report,
    output_dir,
    date,
    at,
    safety_minutes,
):
    """
    Un FIGÉ ne peut être créé
    qu'avant le départ.

    Un FIGÉ historique existant
    n'est jamais remplacé.
    """

    if (
        report.get("statut")
        != "analyse_provisoire"
    ):
        return report

    start = (
        dt.datetime.fromisoformat(
            report["depart"]
        )
    )

    safe_id = "".join(
        character
        if (
            character.isascii()
            and (
                character.isalnum()
                or character in "-_"
            )
        )
        else "_"
        for character in report["id"]
    )[:65]

    identity = hashlib.sha256(
        report["id"].encode("utf-8")
    ).hexdigest()[:16]

    folder = (
        Path(output_dir)
        / "figes"
        / date
    )

    target = folder / (
        safe_id
        + "_"
        + identity
        + ".json"
    )

    # Priorité à la conservation
    # des FIGÉS déjà existants.

    if target.exists():

        try:

            record = json.loads(
                target.read_text(
                    encoding="utf-8"
                )
            )

            valid = verify_frozen(
                record,
                report["id"],
                safety_minutes,
            )

        except (
            OSError,
            ValueError,
        ):
            valid = False

        report["statut"] = (
            "fige_existant"
            if valid else "fige_invalide"
        )

        report["fichier_fige"] = (
            str(target)
        )

        return report

    # Protection contre un FIGÉ tardif.

    if (
        at >= start - dt.timedelta(
            minutes=safety_minutes
        )
    ):

        report["motif_fige"] = (
            "Délai de sécurité dépassé"
        )

        return report

    qualified = [
        name
        for name, motor
        in report["moteurs"].items()
        if motor["qualification"]
        == "candidate"
    ]

    if not qualified:

        report["motif_fige"] = (
            "Aucun moteur qualifié"
        )

        return report

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = {
        "rapport": dict(report),
        "sha256": sha256_report(
            report
        ),
        "fige_a": at.isoformat(),
    }

    try:

        with target.open(
            "x",
            encoding="utf-8",
        ) as file:

            file.write(
                serialized(record)
            )

            file.flush()
            os.fsync(
                file.fileno()
            )

    except FileExistsError:

        try:

            existing = json.loads(
                target.read_text(
                    encoding="utf-8"
                )
            )

            valid = verify_frozen(
                existing,
                report["id"],
                safety_minutes,
            )

        except (
            OSError,
            ValueError,
        ):
            valid = False

        report["statut"] = (
            "fige_existant"
            if valid else "fige_invalide"
        )

    else:

        report["statut"] = "fige"

    report["fichier_fige"] = (
        str(target)
    )

    return report


# ============================================================
# DIAGNOSTIC
# ============================================================

def diagnostic(input_path):

    print(serialized({
        "logiciel": LOGICIEL,
        "version": VERSION,
        "python": sys.version.split()[0],
        "timezone": str(PARIS),
        "heure_paris": now().isoformat(),
        "moteurs": {
            name: SPECIALITES[name]
            for name in WEIGHTS
        },
        "source_presente": (
            Path(input_path).is_file()
        ),
        "paris_reels": "desactives",
        "figes": "SHA-256",
        "publication": (
            "controlee"
        ),
    }))

    return 0


# ============================================================
# EXÉCUTION PRINCIPALE
# ============================================================

def main(argv=None):

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--date",
        default=now().date().isoformat(),
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DATA_DIR / "courses.json",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR,
    )

    parser.add_argument(
        "--figer",
        action="store_true",
    )

    parser.add_argument(
        "--diagnostic",
        action="store_true",
    )

    parser.add_argument(
        "--strict-input",
        action="store_true",
    )

    parser.add_argument(
        "--safety-minutes",
        type=int,
        default=DEFAULT_SAFETY_MINUTES,
    )

    args = parser.parse_args(argv)

    if args.diagnostic:
        return diagnostic(args.input)

    try:
        dt.date.fromisoformat(
            args.date
        )

    except ValueError:
        parser.error(
            "Date invalide : AAAA-MM-JJ"
        )

    if args.safety_minutes < 0:
        parser.error(
            "Le délai de sécurité doit "
            "être positif"
        )

    at = now()

    reports = []
    status = "ok"

    # --------------------------------------------------------
    # CONTRÔLE DU FICHIER SOURCE
    # --------------------------------------------------------

    if not args.input.is_file():

        if args.strict_input:
            parser.error(
                "Fichier absent : "
                + str(args.input)
            )

        status = "en_attente_donnees"

    else:

        try:
            courses = load_courses(
                args.input
            )

        except (
            OSError,
            ValueError,
        ) as exc:

            parser.error(
                "Entrée invalide : "
                + str(exc)
            )

        seen = set()

        # ----------------------------------------------------
        # ANALYSE DE CHAQUE COURSE
        # ----------------------------------------------------

        for course in courses:

            if not isinstance(
                course, dict
            ):

                reports.append({
                    "statut": "rejetee",
                    "motif": (
                        "Course non objet"
                    ),
                })

                continue

            try:

                course_date = (
                    departure(course)
                    .date()
                    .isoformat()
                )

                if course_date != args.date:
                    continue

            except (
                KeyError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                pass

            cid = str(
                course.get("id", "")
            ).strip()

            if cid and cid in seen:

                reports.append({
                    "id": cid,
                    "statut": "rejetee",
                    "motif": (
                        "Identifiant dupliqué"
                    ),
                })

                continue

            seen.add(cid)

            report = analyze(
                course,
                at,
            )

            # FIGÉ uniquement sur demande
            # de l'exécution programmée.

            if args.figer:

                report = freeze(
                    report,
                    args.output,
                    args.date,
                    at,
                    args.safety_minutes,
                )

            reports.append(report)

        if not reports:
            status = (
                "aucune_course_verifiee"
            )

    # --------------------------------------------------------
    # AUDIT DU PASSAGE
    # --------------------------------------------------------

    audit = {
        "logiciel": LOGICIEL,
        "date": args.date,
        "genere_a": at.isoformat(),
        "statut_collecte": status,
        "courses": reports,
        "source": (
            str(args.input)
            if args.input.is_file()
            else None
        ),
        "avertissement": (
            "Analyses expérimentales. "
            "Aucune garantie de gain. "
            "Données sportives vérifiées requises."
        ),
    }

    write_atomic(
        args.output / (
            "audit_"
            + args.date
            + ".json"
        ),
        audit,
    )

    write_atomic(
        args.output / "audit_latest.json",
        audit,
    )

    # --------------------------------------------------------
    # PUBLICATION OFFICIELLE CONTRÔLÉE
    # --------------------------------------------------------

    try:

        from publish_data import publish

        publication = publish(
            data_dir=args.output
        )

    except Exception as exc:

        print(
            "ERREUR TURBOFUSION : "
            f"publication impossible : {exc}",
            file=sys.stderr,
        )

        return 3

    if publication is None:

        print(
            "ERREUR TURBOFUSION : "
            "publication du tableau officiel "
            "impossible",
            file=sys.stderr,
        )

        return 3

    # --------------------------------------------------------
    # RAPPORT FINAL
    # --------------------------------------------------------

    summary = {
        "logiciel": LOGICIEL,
        "version": VERSION,
        "statut": status,
        "courses": len(reports),
        "moteurs": list(WEIGHTS),
        "candidatures": sum(
            len(
                report.get(
                    "moteurs_qualifies", []
                )
            )
            for report in reports
        ),
        "figees": sum(
            report.get("statut")
            == "fige"
            for report in reports
        ),
        "figes_existants": sum(
            report.get("statut")
            == "fige_existant"
            for report in reports
        ),
        "figes_invalides": sum(
            report.get("statut")
            == "fige_invalide"
            for report in reports
        ),
        "heure_paris": at.isoformat(),
        "publication": "reussie",
        "fichier_publication": str(
            publication
        ),
        "paris_reels": "desactives",
    }

    print(
        serialized(summary)
    )

    return (
        0 if status == "ok"
        else 2
    )


# ============================================================
# DÉMARRAGE DU LOGICIEL
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
