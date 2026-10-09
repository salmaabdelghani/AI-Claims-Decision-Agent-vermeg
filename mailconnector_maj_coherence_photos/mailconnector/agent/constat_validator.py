"""
Validation des champs extraits du constat amiable (post-OCR).

Chaque champ extrait par `constat_ocr.extract_constat()` est controle par
une regex metier (format tunisien : dates JJ/MM/AAAA, heures HH:MM,
telephones commencant par 2/4/5/7/9, immatriculation "170 TN 8569", etc.).

Un champ valant "manquant" (ou vide / None) n'est PAS considere en erreur
de format : il est deja compte comme "manquant" par `_count_manquant()`
dans constat_ocr.py. Ce module ne signale que les champs REMPLIS dont le
contenu ne respecte pas le format attendu (ex: date "31/13/2024",
telephone a 6 chiffres, immatriculation mal formee...).

Usage:
    from .constat_validator import validate_constat
    validation = validate_constat(ocr_data)
    # validation = {
    #     "valid": bool,
    #     "nb_errors": int,
    #     "nb_checked": int,
    #     "errors": [
    #         {"field": "vehicule_a.conducteur.telephone", "label": "Telephone",
    #          "value": "12345", "reason": "Format invalide"},
    #         ...
    #     ],
    # }
"""
import re
from ressources.syntax_constat import (
    DATE_RE,
    HEURE_RE,
    LIEU_RE,
    OUI_NON_RE,
    TEMOINS_RE,
    NOM_ASSUR_RE,
    POLICE_RE,
    AGENCE_RE,
    NOM_PRENOM_RE,
    ADRESSE_RE,
    TEL_TN_RE,
    PERMIS_RE,
    MARQUE_RE,
    MODELE_RE,
    IMMAT_TN_RE,
    TEXTE_LIBRE_RE,
)

MANQUANT = "manquant"




def _get(data: dict, path: str):
    """Recupere une valeur imbriquee via un chemin 'a.b.c'."""
    node = data
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _rules_for_vehicule(prefix: str) -> list[tuple[str, str, str]]:
    """Genere les regles (chemin, regex, libelle) pour un vehicule A ou B."""
    return [
        (f"{prefix}.assurance.societe",        NOM_ASSUR_RE,  "Nom assurance"),
        (f"{prefix}.assurance.numero_police",  POLICE_RE,     "N° Police"),
        (f"{prefix}.assurance.agence",         AGENCE_RE,     "Agence"),
        (f"{prefix}.conducteur.nom",           NOM_PRENOM_RE, "Nom conducteur"),
        (f"{prefix}.conducteur.prenom",        NOM_PRENOM_RE, "Prenom conducteur"),
        (f"{prefix}.conducteur.adresse",       ADRESSE_RE,    "Adresse conducteur"),
        (f"{prefix}.conducteur.telephone",     TEL_TN_RE,     "Telephone conducteur"),
        (f"{prefix}.conducteur.permis",        PERMIS_RE,     "N° Permis"),
        (f"{prefix}.conducteur.date_permis",   DATE_RE,       "Date delivrance permis"),
        (f"{prefix}.assure.nom",               NOM_PRENOM_RE, "Nom assure"),
        (f"{prefix}.assure.prenom",            NOM_PRENOM_RE, "Prenom assure"),
        (f"{prefix}.assure.adresse",           ADRESSE_RE,    "Adresse assure"),
        (f"{prefix}.assure.telephone",         TEL_TN_RE,     "Telephone assure"),
        (f"{prefix}.vehicule.marque",          MARQUE_RE,     "Marque"),
        (f"{prefix}.vehicule.type_modele",     MODELE_RE,     "Modele"),
        (f"{prefix}.vehicule.immatriculation", IMMAT_TN_RE,   "Immatriculation"),
        (f"{prefix}.circulation.sens",         TEXTE_LIBRE_RE, "Sens suivi"),
        (f"{prefix}.circulation.venant_de",    TEXTE_LIBRE_RE, "Venant de"),
        (f"{prefix}.circulation.allant_a",     TEXTE_LIBRE_RE, "Allant a"),
    ]


def _base_rules() -> list[tuple[str, str, str]]:
    rules = [
        ("accident.date",    DATE_RE,    "Date accident"),
        ("accident.heure",   HEURE_RE,   "Heure"),
        ("accident.lieu",    LIEU_RE,    "Lieu"),
        ("accident.blesses", OUI_NON_RE, "Blesses"),
    ]
    rules += _rules_for_vehicule("vehicule_a")
    rules += _rules_for_vehicule("vehicule_b")
    return rules


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        # Les cases a cocher (circonstances) ne sont pas des champs texte
        return True
    if isinstance(value, str) and (value.strip() == "" or value.strip().lower() == MANQUANT):
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def validate_constat(ocr_data: dict) -> dict:
    """
    Verifie le format de chaque champ extrait par l'OCR selon les regex
    metier. Ne signale que les champs REMPLIS mais mal formes ; les champs
    "manquant" sont ignores ici (deja traites par la logique de completude).
    """
    if not ocr_data or "error" in ocr_data:
        return {"valid": False, "nb_errors": 0, "nb_checked": 0, "errors": [],
                "note": "Pas de donnees OCR a valider."}

    errors = []
    nb_checked = 0

    for path, pattern, label in _base_rules():
        value = _get(ocr_data, path)
        if _is_empty(value):
            continue
        nb_checked += 1
        text_value = str(value)
        if not re.match(pattern, text_value):
            errors.append({
                "field": path,
                "label": label,
                "value": text_value,
                "reason": "Format invalide",
            })

    # Temoins : champ liste -> concatene en texte libre (<=300 caracteres)
    temoins = _get(ocr_data, "accident.temoins")
    if not _is_empty(temoins):
        nb_checked += 1
        temoins_text = ", ".join(temoins) if isinstance(temoins, list) else str(temoins)
        if not re.match(TEMOINS_RE, temoins_text):
            errors.append({
                "field": "accident.temoins",
                "label": "Temoins",
                "value": temoins_text,
                "reason": "Format invalide (300 caracteres max)",
            })

    return {
        "valid": len(errors) == 0,
        "nb_errors": len(errors),
        "nb_checked": nb_checked,
        "errors": errors,
    }
