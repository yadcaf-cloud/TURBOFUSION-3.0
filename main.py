def analyze_engine(
    engine,
    weights,
    horses,
    at,
    start,
):
    """
    TURBOFUSION 3.0
    Analyse indépendante M1 à M5.

    - Étude des données disponibles
    - Classement par score sportif
    - Qualification contrôlée
    - Gagnant et meilleur placé espérés
    - Proposition de pari hippique
    - Aucun pari réel exécuté
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
            "numero": int(horse["numero"]),
            "nom": str(horse["nom"]),
            "score": round(score, 4),
            "couverture": round(coverage, 3),
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
        first["couverture"] >= MIN_COVERAGE
        and second["couverture"] >= MIN_COVERAGE
        and gap >= MIN_GAP
        and at < start
    )

    if eligible:
        motif = "Critères du moteur satisfaits"

    elif at >= start:
        motif = "Départ atteint ou dépassé"

    elif (
        first["couverture"] < MIN_COVERAGE
        or second["couverture"] < MIN_COVERAGE
    ):
        motif = "Données sportives insuffisantes"

    else:
        motif = "Écart de score insuffisant"

    ordre = [
        horse["numero"]
        for horse in ranking[:5]
    ]

    # ==========================================
    # SÉLECTION AUTONOME DU PARI PROPOSÉ
    # ==========================================

    pari = "Aucun pari proposé"
    type_pari = None

    if eligible:

        # Écart suffisamment marqué :
        # proposition Simple Gagnant.
        if gap >= 0.08:

            type_pari = "Simple Gagnant"

            pari = (
                "Simple Gagnant n°"
                + str(first["numero"])
            )

        # Écart plus modéré :
        # proposition Simple Placé.
        else:

            type_pari = "Simple Placé"

            pari = (
                "Simple Placé n°"
                + str(first["numero"])
            )

    # ==========================================
    # RAPPORT OFFICIEL DU MOTEUR
    # ==========================================

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

        "pari": pari,

        "type_pari": type_pari,

        "mise_reelle": False,

        "couverture": (
            first["couverture"]
        ),

        "donnees_disponibles": (
            round(first["couverture"] * 100, 1)
        ),

        "statut_pari": (
            "proposition"
            if eligible else "abstention"
        ),
    }
    
