"""
Liste officielle et exhaustive des 17 cases a cocher de la rubrique
"circonstances" (case 12) du constat amiable europeen/tunisien.

C'est la SEULE source de verite pour ces champs : le prompt OCR (vision),
le schema de la table `constat_ocr` (PostgreSQL) et l'affichage du rapport
Markdown s'appuient tous sur cette liste, afin d'eviter toute divergence
entre eux (cle Python <-> colonne SQL <-> libelle affiche).

Chaque entree est un tuple (cle_python, libelle_officiel_francais).
L'ordre correspond a l'ordre d'impression sur le formulaire papier.
"""

CIRCONSTANCES: list[tuple[str, str]] = [
    ("en_stationnement", "En stationnement"),
    ("quittait_stationnement", "Quittait un stationnement"),
    ("prenait_stationnement", "Prenait un stationnement"),
    ("sortait_parking", "Sortait d'un parking, d'un lieu prive, d'un chemin de terre"),
    ("engageait_parking", "S'engageait dans un parking, un lieu prive, un chemin de terre"),
    ("arret_circulation", "Arret de circulation"),
    ("frottement_sans_changement_file", "Frottement sans changement de file"),
    ("heurtait_arriere_meme_file", "Heurtait a l'arriere, en roulant dans le meme sens et sur une meme file"),
    ("roulait_file_differente", "Roulait dans le meme sens et sur une file differente"),
    ("changeait_file", "Changeait de file"),
    ("doublait", "Doublait"),
    ("virait_droite", "Virait a droite"),
    ("virait_gauche", "Virait a gauche"),
    ("reculait", "Reculait"),
    ("empietait_sens_inverse", "Empietait sur la partie de chaussee reservee a la circulation en sens inverse"),
    ("venait_droite", "Venait de droite (dans un carrefour)"),
    ("non_observe_signal_priorite", "N'avait pas observe le signal de priorite"),
]

# Cles seules, dans l'ordre (pratique pour construire des listes de colonnes SQL, etc.)
CIRCONSTANCES_KEYS: list[str] = [key for key, _ in CIRCONSTANCES]

# Acces rapide libelle <- cle
CIRCONSTANCES_LABELS: dict[str, str] = dict(CIRCONSTANCES)
