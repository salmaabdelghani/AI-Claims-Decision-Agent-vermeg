"""
Reference du bareme de responsabilite FTUSA, pour AFFICHAGE et EDITION DES
TAUX uniquement (voir routers/agent.py). La logique de correspondance
(cases cochees -> cas du bareme) reste entierement dans
mailconnector/mailconnector/ressources/bareme_responsabilite.py, qui est la
seule source de verite structurelle — ce fichier n'en duplique que le
sous-ensemble utile a un tableau lisible (cas, titre, taux par defaut).

Duplique intentionnellement plutot que partage entre les deux projets (pas
de dependance Python croisee) — si le bareme officiel change cote
mailconnector, mettre a jour cette liste en consequence.
"""

BAREME_REFERENCE = [
    {"cas": "01", "titre": "Y heurte X à l'arrière (même sens, même file)", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": True},
    {"cas": "02", "titre": "Frottement sans changement de file (files différentes, aucun ne change de file)", "taux_a_defaut": 0.5, "taux_b_defaut": 0.5, "fiable": True},
    {"cas": "02bis", "titre": "X et Y changent tous deux de file (files différentes)", "taux_a_defaut": 0.5, "taux_b_defaut": 0.5, "fiable": True},
    {"cas": "03", "titre": "Y change de file (bifurque à gauche) pendant que X double en empiétant sur l'axe médian", "taux_a_defaut": 0.5, "taux_b_defaut": 0.5, "fiable": False},
    {"cas": "04", "titre": "Y change de file seul, X circule normalement", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": True},
    {"cas": "05", "titre": "Y quitte un stationnement (déboîtement)", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": True},
    {"cas": "05bis", "titre": "X et Y manœuvrent tous deux pour prendre le même stationnement", "taux_a_defaut": 0.5, "taux_b_defaut": 0.5, "fiable": True},
    {"cas": "06", "titre": "Y empiète/dépasse l'axe médian, X circule dans son couloir (sens inverse)", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": True},
    {"cas": "07", "titre": "X et Y empiètent tous deux sur l'axe médian (sens inverse)", "taux_a_defaut": 0.5, "taux_b_defaut": 0.5, "fiable": True},
    {"cas": "08", "titre": "X prioritaire de droite empiète sur l'axe médian, Y circule dans son couloir", "taux_a_defaut": 0.25, "taux_b_defaut": 0.75, "fiable": False},
    {"cas": "09", "titre": "X prioritaire de droite circule normalement ou bifurque", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": True},
    {"cas": "10-13", "titre": "X en stationnement (regroupe les cas 10 à 13 selon régularité/gêne)", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": False},
    {"cas": "10-13bis", "titre": "X à l'arrêt de circulation (regroupe les cas 10 à 13)", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": False},
    {"cas": "14", "titre": "Y n'a pas respecté une signalisation (priorité, feu, stop, sens interdit...)", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": True},
    {"cas": "15", "titre": "Y circule en marche arrière ou fait un demi-tour", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": True},
    {"cas": "15bis", "titre": "X et Y reculent/font demi-tour tous les deux", "taux_a_defaut": 0.5, "taux_b_defaut": 0.5, "fiable": True},
    {"cas": "16", "titre": "Y sort d'un parking, lieu privé, chemin de terre", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": True},
    {"cas": "16bis", "titre": "X et Y sortent tous deux d'un parking/lieu privé", "taux_a_defaut": 0.5, "taux_b_defaut": 0.5, "fiable": True},
    {"cas": "17", "titre": "X s'engage dans un parking/lieu privé SANS changement de file", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": True},
    {"cas": "18", "titre": "X s'engage dans un parking/lieu privé AVEC changement de file", "taux_a_defaut": 1.0, "taux_b_defaut": 0.0, "fiable": True},
    {"cas": "19", "titre": "X heurte une portière ouverte du véhicule Y (sans case dédiée)", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": False},
    {"cas": "20", "titre": "Y cause des dommages par jets de pierres/objets (sans case dédiée)", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": False},
    {"cas": "21", "titre": "Y circule sans éclairage hors agglomération (sans case dédiée)", "taux_a_defaut": 0.0, "taux_b_defaut": 1.0, "fiable": False},
    {"cas": "22", "titre": "Y circule sans éclairage en agglomération (sans case dédiée)", "taux_a_defaut": 0.5, "taux_b_defaut": 0.5, "fiable": False},
    {"cas": "23", "titre": "Désaccord sur l'origine de l'accident / cause indéterminée (dernier recours)", "taux_a_defaut": 0.5, "taux_b_defaut": 0.5, "fiable": False},
]
