
INSURANCE_COMPANIES = [
    "AMI Assurances",
    "ASTREE Assurances",
    "AT-Takafulia",
    "BH Assurances",
    "BIAT Assurances",
    "BNA Assurances",
    "CARTE Assurances",
    "COMAR Assurances",
    "CTAMA",
    "GAT Assurances",
    "LLOYD Assurances",
    "MAE Assurances",
    "Maghrebia Assurances",
    "Salim Assurances",
    "STAR Assurances",
    "Zitouna Takaful"
]


def set_companies(noms: list[str]):
    """
    Remplace le CONTENU de la liste EN PLACE (pas de reassignation) afin que
    les modules l'ayant deja importee par reference (`from
    ressources.insurance_companies import INSURANCE_COMPANIES`) voient la
    mise a jour sans avoir a re-importer. Appelee une fois au demarrage de
    l'agent (voir main.py) avec la liste courante en base de donnees
    (editable depuis le dashboard).
    """
    if not noms:
        return
    INSURANCE_COMPANIES.clear()
    INSURANCE_COMPANIES.extend(noms)