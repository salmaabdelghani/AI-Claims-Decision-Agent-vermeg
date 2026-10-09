"""
Barème de responsabilité — Fédération Tunisienne des Sociétés d'Assurances (FTUSA).

Source : "BAREME DE RESPONSABILITE — Réparation des dégâts matériels", FTUSA,
version en vigueur au 23/08/2024 (Annexe n°01), conforme à l'article 123 du
Code des Assurances tunisien. Fichiers de référence fournis par l'utilisateur :
  - ملحق-عدد-01-جدول-تحديد-المسؤولية.pdf (texte intégral, 24 cas + collisions 3+ véhicules)
  - bareme2.pdf (version 1999, mêmes cas, avec croquis illustratifs)

C'EST LA SEULE SOURCE DE VERITE pour ce barème. Toute modification doit être
répercutée ici uniquement (même principe que ressources/circonstances.py pour
les 17 cases à cocher du constat).

── Principe d'encodage ────────────────────────────────────────────────────
Le barème raisonne en véhicules génériques "X" et "Y". Chaque règle ci-dessous
liste :
  - x_true / y_true   : cases qui DOIVENT être cochées pour X / Y
  - x_false / y_false : cases qui DOIVENT être décochées pour X / Y
                         (sert à distinguer des cas voisins, ex. cas 03 vs 04)
  - taux_x, taux_y    : part de responsabilité (fractions Python, somme = 1)
  - fiable            : True si la seule combinaison de cases cochées suffit
                         à trancher sans ambiguïté ; False si le barème exige
                         une information absente du formulaire à cases
                         (ex. "en agglomération", "gênant la circulation",
                         "stationnement régulier") — dans ce cas la règle
                         reste indicative et DOIT être confirmée par un
                         humain ou une analyse du texte libre (lieu /
                         observations / croquis).

Le moteur de correspondance (agent/responsabilite.py) teste les deux
affectations possibles (A=X,B=Y) et (A=Y,B=X) et retourne la première règle
qui correspond intégralement.

── Cas volontairement NON couverts par une case à cocher ─────────────────
Les cas n°19 (portière ouverte), n°20 (jets de pierres/objets), n°21 et n°22
(absence d'éclairage) du barème officiel ne correspondent à AUCUNE des 17
cases du constat amiable : ils ne peuvent être détectés que par le texte
libre (observations, description du croquis). Ils sont documentés ici
(CAS_SANS_CASE) à titre de référence pour le module LLM de secours, mais ne
génèrent jamais de correspondance automatique fiable.

Les accidents impliquant 3 véhicules ou plus (cas "Accidents en chaîne" et
"Chocs successifs") sont hors du périmètre de ce moteur : le schéma OCR
actuel (constat_ocr.py) ne modélise que deux véhicules (A et B).
"""
from fractions import Fraction as F

# ─── Règles à correspondance directe (cases cochées) ──────────────────────
# Ordonnées dans l'ordre du barème officiel. Chaque règle doit être
# mutuellement exclusive de ses voisines grâce aux conditions *_false.

REGLES: list[dict] = [

    {
        "cas": "01",
        "titre": "Y heurte X à l'arrière (même sens, même file)",
        "x_true": frozenset(), "x_false": frozenset(),
        "y_true": frozenset({"heurtait_arriere_meme_file"}), "y_false": frozenset(),
        "taux_x": F(0), "taux_y": F(1),
        "fiable": True,
        "note": "Le véhicule heurté à l'arrière n'est pas en tort.",
    },
    {
        "cas": "02",
        "titre": "Frottement sans changement de file (X et Y sur files différentes, aucun ne change de file)",
        "x_true": frozenset({"frottement_sans_changement_file"}), "x_false": frozenset(),
        "y_true": frozenset({"frottement_sans_changement_file"}), "y_false": frozenset(),
        "taux_x": F(1, 2), "taux_y": F(1, 2),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "02bis",
        "titre": "X et Y changent tous deux de file (files différentes)",
        "x_true": frozenset({"changeait_file"}), "x_false": frozenset({"doublait", "empietait_sens_inverse", "engageait_parking"}),
        "y_true": frozenset({"changeait_file"}), "y_false": frozenset({"doublait", "empietait_sens_inverse", "engageait_parking"}),
        "taux_x": F(1, 2), "taux_y": F(1, 2),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "03",
        "titre": "Y change de file (bifurque à gauche) pendant que X double en empiétant sur l'axe médian",
        "x_true": frozenset({"doublait", "empietait_sens_inverse"}), "x_false": frozenset({"engageait_parking"}),
        "y_true": frozenset({"changeait_file"}), "y_false": frozenset({"engageait_parking"}),
        "taux_x": F(1, 2), "taux_y": F(1, 2),
        "fiable": False,
        "note": ("Attention exceptions barème : en sens unique, si Y change de file pour "
                 "virer alors que X circule normalement dans son couloir, Y est responsable "
                 "à 100% ; inversement si X double seul en empiétant, X est responsable à "
                 "100%. Vérifier le sens de circulation (lieu / croquis) avant de valider ce taux."),
    },
    {
        "cas": "04",
        "titre": "Y change de file seul, X circule normalement",
        "x_true": frozenset(), "x_false": frozenset({"doublait", "empietait_sens_inverse"}),
        "y_true": frozenset({"changeait_file"}), "y_false": frozenset({"engageait_parking"}),
        "taux_x": F(0), "taux_y": F(1),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "05",
        "titre": "Y quitte un stationnement (déboîtement)",
        "x_true": frozenset(), "x_false": frozenset({"prenait_stationnement"}),
        "y_true": frozenset({"quittait_stationnement"}), "y_false": frozenset(),
        "taux_x": F(0), "taux_y": F(1),
        "fiable": True,
        "note": "L'arrêt en oblique de Y s'apprêtant à quitter le stationnement n'exclut pas sa responsabilité.",
    },
    {
        "cas": "05bis",
        "titre": "X et Y manœuvrent tous deux pour prendre le même stationnement",
        "x_true": frozenset({"prenait_stationnement"}), "x_false": frozenset(),
        "y_true": frozenset({"prenait_stationnement"}), "y_false": frozenset(),
        "taux_x": F(1, 2), "taux_y": F(1, 2),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "06",
        "titre": "Y empiète/dépasse l'axe médian, X circule dans son couloir (sens inverse)",
        "x_true": frozenset(), "x_false": frozenset({"empietait_sens_inverse", "venait_droite"}),
        "y_true": frozenset({"empietait_sens_inverse"}), "y_false": frozenset({"venait_droite"}),
        "taux_x": F(0), "taux_y": F(1),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "07",
        "titre": "X et Y empiètent tous deux sur l'axe médian (sens inverse) ou position indéterminée",
        "x_true": frozenset({"empietait_sens_inverse"}), "x_false": frozenset({"venait_droite"}),
        "y_true": frozenset({"empietait_sens_inverse"}), "y_false": frozenset({"venait_droite"}),
        "taux_x": F(1, 2), "taux_y": F(1, 2),
        "fiable": True,
        "note": "Si les trajectoires ne se coupent pas, doit être requalifié en accident de croisement (cas 08/09).",
    },
    {
        "cas": "08",
        "titre": "X prioritaire de droite empiète sur l'axe médian (chaussée à double sens), Y circule dans son couloir",
        "x_true": frozenset({"venait_droite", "empietait_sens_inverse"}), "x_false": frozenset(),
        "y_true": frozenset(), "y_false": frozenset({"venait_droite", "empietait_sens_inverse"}),
        "taux_x": F(1, 4), "taux_y": F(3, 4),
        "fiable": False,
        "note": "Ne s'applique que si la position de X par rapport à l'axe médian est prouvée sans ambiguïté (croquis).",
    },
    {
        "cas": "09",
        "titre": "X prioritaire de droite circule dans son couloir ou bifurque à droite/gauche",
        "x_true": frozenset({"venait_droite"}), "x_false": frozenset({"empietait_sens_inverse"}),
        "y_true": frozenset(), "y_false": frozenset(),
        "taux_x": F(0), "taux_y": F(1),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "10-13",
        "titre": "X en stationnement (case commune aux cas 10 à 13 du barème)",
        "x_true": frozenset({"en_stationnement"}), "x_false": frozenset(),
        "y_true": frozenset(), "y_false": frozenset(),
        # Valeur par défaut = cas 10 (stationnement régulier), la plus fréquente.
        # NE JAMAIS considérer ce taux comme définitif : voir "cases_alternatives".
        "taux_x": F(0), "taux_y": F(1),
        "fiable": False,
        "cases_alternatives": [
            {"cas": "10", "condition": "stationnement/arrêt régulier", "taux_x": F(0), "taux_y": F(1)},
            {"cas": "11", "condition": "stationnement/arrêt interdit en agglomération, le long d'un trottoir, sans gêne", "taux_x": F(0), "taux_y": F(1)},
            {"cas": "12", "condition": "stationnement/arrêt interdit en agglomération, gênant la circulation (gêne à prouver)", "taux_x": F(1, 4), "taux_y": F(3, 4)},
            {"cas": "13", "condition": "stationnement/arrêt irrégulier hors agglomération", "taux_x": F(1, 2), "taux_y": F(1, 2)},
        ],
        "note": ("Le formulaire ne coche que 'en_stationnement' pour ces 4 cas du barème, "
                 "qui se distinguent uniquement par : (a) régularité du stationnement, "
                 "(b) caractère agglomération/hors agglomération du lieu, (c) existence "
                 "d'une gêne prouvée à la circulation. Ces informations doivent être "
                 "établies à partir de 'accident.lieu' et des 'observations' — nécessite "
                 "confirmation humaine ou passage par le module LLM de secours."),
    },
    {
        "cas": "10-13bis",
        "titre": "X à l'arrêt de circulation (case commune aux cas 10 à 13 du barème)",
        "x_true": frozenset({"arret_circulation"}), "x_false": frozenset(),
        "y_true": frozenset(), "y_false": frozenset(),
        "taux_x": F(0), "taux_y": F(1),
        "fiable": False,
        "cases_alternatives": [
            {"cas": "10", "condition": "stationnement/arrêt régulier", "taux_x": F(0), "taux_y": F(1)},
            {"cas": "11", "condition": "stationnement/arrêt interdit en agglomération, le long d'un trottoir, sans gêne", "taux_x": F(0), "taux_y": F(1)},
            {"cas": "12", "condition": "stationnement/arrêt interdit en agglomération, gênant la circulation (gêne à prouver)", "taux_x": F(1, 4), "taux_y": F(3, 4)},
            {"cas": "13", "condition": "stationnement/arrêt irrégulier hors agglomération", "taux_x": F(1, 2), "taux_y": F(1, 2)},
        ],
        "note": ("Le formulaire ne coche que 'arret_circulation' pour ces 4 cas du barème — "
                 "mêmes réserves que le cas 10-13 (voir ci-dessus)."),
    },
    {
        "cas": "14",
        "titre": ("Y n'a pas respecté une signalisation (agent, priorité/STOP, feu, sens interdit, "
                  "interdiction de dépasser/virer, ligne continue, marquage au sol, trottoir)"),
        "x_true": frozenset(), "x_false": frozenset(),
        "y_true": frozenset({"non_observe_signal_priorite"}), "y_false": frozenset(),
        "taux_x": F(0), "taux_y": F(1),
        "fiable": True,
        "note": ("La case du constat 'N'avait pas observé le signal de priorité' couvre "
                 "l'ensemble de ces infractions dans la pratique — le détail exact de "
                 "l'infraction reste à confirmer via les observations si nécessaire."),
    },
    {
        "cas": "15",
        "titre": "Y circule en marche arrière ou fait un demi-tour en quittant/prenant un stationnement",
        "x_true": frozenset(), "x_false": frozenset({"reculait"}),
        "y_true": frozenset({"reculait"}), "y_false": frozenset(),
        "taux_x": F(0), "taux_y": F(1),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "15bis",
        "titre": "X et Y reculent/font demi-tour tous les deux",
        "x_true": frozenset({"reculait"}), "x_false": frozenset(),
        "y_true": frozenset({"reculait"}), "y_false": frozenset(),
        "taux_x": F(1, 2), "taux_y": F(1, 2),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "16",
        "titre": "Y sort d'un parking, d'un lieu non ouvert à la circulation, d'un chemin de terre",
        "x_true": frozenset(), "x_false": frozenset({"sortait_parking"}),
        "y_true": frozenset({"sortait_parking"}), "y_false": frozenset(),
        "taux_x": F(0), "taux_y": F(1),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "16bis",
        "titre": "X et Y sortent tous deux d'un parking/lieu non ouvert/chemin de terre",
        "x_true": frozenset({"sortait_parking"}), "x_false": frozenset(),
        "y_true": frozenset({"sortait_parking"}), "y_false": frozenset(),
        "taux_x": F(1, 2), "taux_y": F(1, 2),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "17",
        "titre": "X s'engage dans un parking/lieu non ouvert/chemin de terre SANS changement de file",
        "x_true": frozenset({"engageait_parking"}), "x_false": frozenset({"changeait_file"}),
        "y_true": frozenset(), "y_false": frozenset(),
        "taux_x": F(0), "taux_y": F(1),
        "fiable": True,
        "note": None,
    },
    {
        "cas": "18",
        "titre": "X s'engage dans un parking/lieu non ouvert/chemin de terre AVEC changement de file",
        "x_true": frozenset({"engageait_parking", "changeait_file"}), "x_false": frozenset(),
        "y_true": frozenset(), "y_false": frozenset(),
        "taux_x": F(1), "taux_y": F(0),
        "fiable": True,
        "note": None,
    },
]

# ─── Cas du barème sans case à cocher correspondante ───────────────────────
# Fournis pour référence au module LLM de secours (agent/responsabilite.py) ;
# ne participent jamais à la correspondance automatique par cases cochées.
CAS_SANS_CASE: list[dict] = [
    {"cas": "19", "titre": "X heurte une portière ouverte du véhicule Y", "taux_x": F(0), "taux_y": F(1)},
    {"cas": "20", "titre": "Y cause des dommages par jets de pierres ou objets transportés", "taux_x": F(0), "taux_y": F(1)},
    {"cas": "21", "titre": "Y circule sans éclairage hors agglomération", "taux_x": F(0), "taux_y": F(1)},
    {"cas": "22", "titre": "Y circule sans éclairage en agglomération", "taux_x": F(1, 2), "taux_y": F(1, 2)},
]

# ─── Clause générale de secours (cas 23 du barème) ─────────────────────────
CAS_DESACCORD = {
    "cas": "23",
    "titre": "Désaccord sur l'origine de l'accident / impossibilité de prouver la cause",
    "taux_x": F(1, 2), "taux_y": F(1, 2),
    "note": "Application uniquement en dernier recours, quand aucune autre règle ne correspond.",
}

# ─── Hors périmètre (nécessitent un schéma à 3+ véhicules) ─────────────────
CAS_MULTI_VEHICULES = {
    "accidents_en_chaine": "Le dernier véhicule de la chaîne supporte 100% de la responsabilité.",
    "chocs_successifs": "Chaque véhicule supporte 100% des dégâts arrière du véhicule qui le précède.",
}
