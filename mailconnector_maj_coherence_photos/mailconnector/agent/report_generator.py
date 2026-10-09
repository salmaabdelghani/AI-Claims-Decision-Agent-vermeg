"""
Generation du fichier Markdown structure.
Supporte : doc_check (documents manquants) et ocr_data (champs du constat).
"""
from datetime import datetime
import re

from ressources.circonstances import CIRCONSTANCES_LABELS


def generate_sinistre_md(
    email_data: dict,
    classification: dict,
    analysis: dict,
    ocr_data: dict = None,
    doc_check: dict = None,
    status: str = None,
    status_note: str = None,
    responsabilite: dict = None,
    coherence_photos: dict = None,
) -> str:
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stype = (classification.get("sinistre_type") or "non precise").capitalize()

    lines = [
        "# Declaration de Sinistre", "",
        f"> Genere le {now}",
        f"> Type : **{stype}** | Confiance : {round(classification.get('confidence',0)*100)}%",
        "",
    ]

    # Alerte documents manquants
    if doc_check and not doc_check.get("complete"):
        lines += [
            "## ⚠️ Dossier Incomplet", "",
            f"**Documents manquants :** {', '.join(doc_check.get('missing', []))}",
            "",
            doc_check.get("message", ""),
            "", "---", "",
        ]

    lines += [
        "## Informations de l'email", "",
        "| Champ | Valeur |", "|-------|--------|",
        f"| **Expediteur** | {email_data.get('sender','N/A')} |",
        f"| **CC** | {email_data.get('cc','') or '-'} |",
        f"| **BCC** | {email_data.get('bcc','') or '-'} |",
        f"| **Objet** | {email_data.get('subject','Sans objet')} |",
        f"| **Date** | {email_data.get('date','N/A')} |",
        "", "---", "",
        "## Resume de la demande", "",
        analysis.get("summary", "Resume non disponible."),
        "", "---", "",
    ]

    # Tableau pieces jointes
    attachments = analysis.get("classified_attachments", [])
    if attachments:
        nb_i = sum(1 for a in attachments if a.get("source") == "inline")
        nb_a = len(attachments) - nb_i
        lines += [
            f"## Pieces jointes ({len(attachments)} : {nb_a} jointes + {nb_i} integrees)", "",
            "| # | Fichier | Format | Nature | Source | Taille |",
            "|---|---------|--------|--------|--------|--------|",
        ]
        for i, att in enumerate(attachments, 1):
            size  = f"{round(att.get('size_bytes',0)/1024,1)} Ko"
            src   = "Integree" if att.get("source") == "inline" else "Jointe"
            lines.append(
                f"| {i} | `{att['filename']}` | {att.get('classified_type','?')} "
                f"| {att.get('nature','?')} | {src} | {size} |"
            )
        lines += ["", "---", ""]
    else:
        lines += ["## Pieces jointes", "", "_Aucune piece jointe._", "", "---", ""]

    # Section OCR constat
    if ocr_data and "error" not in ocr_data:
        lines += _ocr_section(ocr_data)
    elif ocr_data and "error" in ocr_data:
        lines += ["## OCR Constat Amiable", "", f"_Extraction echouee : {ocr_data['error']}_", ""]

    # Section coherence constat-degats (photos)
    if coherence_photos:
        lines += _coherence_photos_section(coherence_photos)

    # Section determination de responsabilite
    if responsabilite:
        lines += _responsabilite_section(responsabilite)

    lines += [
        "## Metadonnees", "",
        f"- **Statut** : {status or ('A traiter' if (not doc_check or doc_check.get('complete')) else 'INCOMPLET')}",
        f"- **Agent** : SinistreBot v2.0",
        f"- **Motif** : {classification.get('reason','N/A')}",
    ]
    if status_note:
        lines.append(f"- **Note** : {status_note}")
    lines.append("")
    return "\n".join(lines)


def _ocr_section(ocr: dict) -> list[str]:
    """Formate les donnees OCR du constat en Markdown."""
    lines = ["## OCR Constat Amiable", ""]

    acc = ocr.get("accident", {})
    blesses = acc.get('blesses')
    degats_autres = acc.get('degats_materiels_autres')
    # Garde-fou : si le LLM a renvoye un booleen au lieu d'un texte
    if isinstance(blesses, bool):
        blesses = "Oui" if blesses else "Non"
    if isinstance(degats_autres, bool):
        degats_autres = "manquant"
    lines += [
        "### Informations generales", "",
        "| Champ | Valeur |", "|-------|--------|",
        f"| Date | {acc.get('date') or '-'} |",
        f"| Heure | {acc.get('heure') or '-'} |",
        f"| Lieu | {acc.get('lieu') or '-'} |",
        f"| Blesses | {blesses or '-'} |",
        f"| Degats autres | {degats_autres or '-'} |",
        "",
    ]

    for label, key in [("Vehicule A", "vehicule_a"), ("Vehicule B", "vehicule_b")]:
        veh  = ocr.get(key, {})
        cond = veh.get("conducteur", {})
        ass  = veh.get("assurance", {})
        assure = veh.get("assure", {})
        v    = veh.get("vehicule", {})
        circ = veh.get("circulation", {})

        lines += [
            f"### {label}", "",
            "**Conducteur**",
            f"Nom : {cond.get('nom') or '-'} | Prenom : {cond.get('prenom') or '-'} | "
            f"Adresse : {cond.get('adresse') or '-'}",
            f"Tel : {cond.get('telephone') or '-'} | Permis : {cond.get('permis') or '-'} | "
            f"Delivre le : {cond.get('date_permis') or '-'}",
            "",
            "**Assure (souscripteur)**",
            f"Nom : {assure.get('nom') or '-'} | Prenom : {assure.get('prenom') or '-'} | "
            f"Adresse : {assure.get('adresse') or '-'} | Tel : {assure.get('telephone') or '-'}",
            "",
            "**Assurance**",
            f"Societe : {ass.get('societe') or '-'} | Police : {ass.get('numero_police') or '-'} | "
            f"Agence : {ass.get('agence') or '-'}",
            f"Validite : {ass.get('validite') or '-'}",
            "",
            "**Vehicule**",
            f"Marque : {v.get('marque') or '-'} | Modele : {v.get('type_modele') or '-'} | "
            f"Immat : {v.get('immatriculation') or '-'}",
            "",
            "**Circulation**",
            f"Sens suivi : {circ.get('sens') or '-'} | Venant de : {circ.get('venant_de') or '-'} | "
            f"Allant a : {circ.get('allant_a') or '-'}",
            f"Choc : {circ.get('point_choc') or '-'} | Degats : {circ.get('degats_apparents') or '-'}",
            f"Observations : {circ.get('observations') or '-'}",
            "",
        ]

    # Circonstances cochees
    for label, key in [("Circonstances A", "circonstances_a"), ("Circonstances B", "circonstances_b")]:
        circ_dict = ocr.get(key, {})
        coches = [CIRCONSTANCES_LABELS.get(k, k.replace("_", " ")) for k, v in circ_dict.items() if v is True]
        lines += [
            f"### {label} — cases cochees", "",
            (", ".join(coches) if coches else "_Aucune case cochee_"),
            "",
        ]

    # Croquis
    lines += [
        "### Croquis de l'accident", "",
        f"Present : {'✅ Oui' if ocr.get('croquis_present') else '❌ Non'}",
        "",
        f"Description : {ocr.get('description_croquis') or '-'}",
        "",
    ]

    # Completude OCR
    if "completude_pct" in ocr:
        lines += [
            "### Completude de l'extraction", "",
            f"{ocr.get('champs_total',0) - ocr.get('champs_manquant',0)}/{ocr.get('champs_total',0)} "
            f"champs extraits ({ocr.get('completude_pct',0)}%)",
            "",
        ]

    # Validation du format des champs (regex metier)
    validation = ocr.get("validation")
    if validation:
        lines += ["### Validation du format des champs", ""]
        if validation.get("nb_errors", 0) == 0:
            lines += [f"✅ {validation.get('nb_checked',0)} champ(s) verifie(s), aucune anomalie de format.", ""]
        else:
            lines += [
                f"⚠️ {validation['nb_errors']} champ(s) au format invalide "
                f"sur {validation.get('nb_checked',0)} verifie(s) :",
                "",
                "| Champ | Valeur | Anomalie |",
                "|-------|--------|----------|",
            ]
            for err in validation["errors"]:
                lines.append(f"| {err['label']} | `{err['value']}` | {err['reason']} |")
            lines.append("")

    # Signatures
    lines += [
        "### Signatures", "",
        f"- Conducteur A : {'✅ Presente' if ocr.get('signature_a') else '❌ Absente'}",
        f"- Conducteur B : {'✅ Presente' if ocr.get('signature_b') else '❌ Absente'}",
        "", "---", "",
    ]
    return lines


def _coherence_photos_section(coherence: dict) -> list[str]:
    """Formate le resultat de photo_damage_analyzer.py en Markdown."""
    analyzed = coherence.get("analyzed")
    coherent = coherence.get("coherent")
    explication = coherence.get("explication", "")
    details = coherence.get("details") or {}

    if coherent is True:
        icone = "✅ Coherent"
    elif coherent is False:
        icone = "❌ INCOHERENT — dossier a verifier"
    else:
        icone = "⚠️ Non concluant"

    lines = [
        "## Coherence constat-degats", "",
        f"**Statut** : {icone}", "",
    ]

    if analyzed and details:
        nb_photos = details.get("nb_photos_analysees")
        nb_veh = details.get("nb_vehicules_identifies")
        lines += [
            f"- **Photos analysees** : {nb_photos if nb_photos is not None else '-'}",
            f"- **Vehicules identifies sur les photos** : {nb_veh if nb_veh is not None else '-'}",
            "",
        ]

        sous_controles = [
            ("Coherence entre les photos (meme vehicule)", details.get("coherence_inter_photos")),
            ("Coherence points de choc / degats vs constat", details.get("coherence_points_choc_degats")),
            ("Coherence avec le croquis et les circonstances", details.get("coherence_croquis_circonstances")),
        ]
        controles_renseignes = [c for c in sous_controles if c[1]]
        if controles_renseignes:
            lines += ["| Controle | Resultat | Explication |", "|----------|----------|-------------|"]
            for label, sc in controles_renseignes:
                ok = sc.get("coherent")
                resultat = "✅" if ok else ("❌" if ok is False else "⚠️")
                lines.append(f"| {label} | {resultat} | {sc.get('explication','-')} |")
            lines.append("")

    lines += [
        "### Explication detaillee", "",
        explication or "Aucune explication disponible.",
        "",
    ]

    if coherent is False:
        lines += [
            "> ⚠️ **Incoherence detectee entre les photos de dommages et le constat amiable.** "
            "Le dossier est marque comme **INVALIDE** et necessite une verification manuelle "
            "avant tout traitement.",
            "",
        ]

    lines += ["---", ""]
    return lines


def _responsabilite_section(resp: dict) -> list[str]:
    """Formate le resultat du module agent/responsabilite.py en Markdown."""
    statut_icones = {
        "CONFIRME_BAREME": "✅ Confirmé par le barème",
        "PROPOSITION_A_VALIDER": "⚠️ Proposition à valider par un expert",
        "INDETERMINE": "❌ Indéterminé",
    }
    statut = resp.get("statut", "INDETERMINE")
    taux_a = resp.get("taux_a")
    taux_b = resp.get("taux_b")

    lines = [
        "## Détermination de responsabilité", "",
        f"**Statut** : {statut_icones.get(statut, statut)}", "",
        "| Véhicule | Taux de responsabilité |", "|----------|------------------------|",
        f"| A | {round(taux_a*100) if taux_a is not None else '-'}% |",
        f"| B | {round(taux_b*100) if taux_b is not None else '-'}% |",
        "",
        f"**Cas du barème FTUSA retenu** : {resp.get('cas_type') or 'Non déterminé'}",
        f"**Méthode** : {resp.get('methode', '-')}",
        "",
        "### Explication détaillée", "",
        resp.get("justification", "Aucune justification disponible."),
        "",
    ]

    elements = resp.get("elements_pris_en_compte") or {}
    if elements:
        lines += [
            "### Éléments pris en compte", "",
            f"- **Circonstances A cochées** : {', '.join(elements.get('circonstances_cochees_a') or []) or '_aucune_'}",
            f"- **Circonstances B cochées** : {', '.join(elements.get('circonstances_cochees_b') or []) or '_aucune_'}",
            f"- **Croquis présent** : {'Oui' if elements.get('croquis_present') else 'Non'}",
            f"- **Description du croquis** : {elements.get('description_croquis') or '-'}",
            f"- **Point de choc A / Dégâts A** : {elements.get('point_choc_a') or '-'} / {elements.get('degats_apparents_a') or '-'}",
            f"- **Point de choc B / Dégâts B** : {elements.get('point_choc_b') or '-'} / {elements.get('degats_apparents_b') or '-'}",
            "",
        ]

    if resp.get("necessite_expertise"):
        lines += [
            "> ⚠️ **Ce taux est une proposition automatique et ne doit pas être considéré comme "
            "définitif.** Une validation par un gestionnaire sinistre est requise avant tout "
            "recours entre assureurs.",
            "",
        ]

    lines += ["---", ""]
    return lines


def slug_from_email(email_data: dict) -> str:
    now  = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    subj = email_data.get("subject", "sinistre")
    slug = re.sub(r"[^\w\s-]", "", subj.lower())
    slug = re.sub(r"[\s_]+", "-", slug)[:40]
    return f"{now}_{slug}"