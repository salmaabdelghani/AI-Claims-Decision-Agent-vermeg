"""
Generation du rapport d'analyse PDF pour un sinistre traite par le pipeline
(voir main.py, ETAPE 6bis).

Objectif : produire, pour CHAQUE sinistre traite (dossier valide "A_TRAITER"
comme dossier invalide/incomplet), un document PDF autonome, lisible en
quelques minutes par un expert ou un gestionnaire sinistre, contenant :

  1. Un bandeau de decision immediat (VALIDE / NON VALIDE + raison precise)
  2. Le numero de contrat concerne
  3. Une description synthetique de l'accident
  4. Les degats declares ET les photos de dommages jointes
  5. Le taux de responsabilite estime, avec justification detaillee
     (tracabilite du raisonnement : bareme applique, cases cochees, etc.)
  6. Le detail complet du contrat en base assurance : contrat, vehicule,
     garanties, exclusions (uniquement si un contrat a pu etre identifie)
  7. Le resultat du controle de coherence photos <-> constat
  8. Une note de tracabilite/audit (elements pris en compte, incoherences)

En cas de dossier NON valide, le rapport explique TOUJOURS la raison precise
(documents manquants, contrat introuvable/inactif/hors periode, incoherence
photos/constat, incoherence constat/base assurance...), meme lorsque
certaines sections (responsabilite, detail contrat) ne peuvent pas etre
renseignees faute de donnees fiables.

Fichier de sortie : mailconnector/mailconnector/rapport_analyse/<nom>.pdf
(dossier cree automatiquement si absent, au meme niveau que agent/, storage/,
ressources/).

Convention de nommage (voir _build_filename) :
    RAPPORT_<STATUT>_SIN<sinistre_id>_<police_ou_SANSPOLICE>_<AAAAMMJJ_HHMMSS>.pdf
    ex: RAPPORT_A_TRAITER_SIN00285_912345X_20260722_001432.pdf
Ce nom permet, sans ouvrir le fichier, de trier/filtrer par statut, de
retrouver un dossier par son identifiant interne ou son numero de police, et
de reperer immediatement la version la plus recente (horodatage).
"""
import base64
import io
import logging
import os
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Image as RLImage, KeepTogether, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

from ressources.circonstances import CIRCONSTANCES_LABELS
from .photo_damage_analyzer import get_photo_attachments

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

logger = logging.getLogger(__name__)

# mailconnector/mailconnector/rapport_analyse — sibling de agent/, storage/, ressources/
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rapport_analyse"
)

PAGE_WIDTH, _ = A4
CONTENT_WIDTH = PAGE_WIDTH - 2 * 1.8 * cm

# ─── Libelles / couleurs par statut ─────────────────────────────────────────

STATUT_LABELS = {
    "A_TRAITER": "Dossier complet, coherent et pret pour traitement",
    "INVALIDE": "Dossier INVALIDE — incoherence entre les photos et le constat",
    "CONTRAT_INTROUVABLE": "Aucun contrat correspondant trouve en base assurance",
    "CONTRAT_INVALIDE": "Contrat trouve mais non exploitable pour ce sinistre",
    "CONTRAT_INCOHERENT": "Contrat trouve et valide, mais donnees du constat incoherentes avec la base",
    "CONSTAT_INCOMPLET": "Constat present mais OCR incomplet (trop de champs manquants)",
    "PAS_DE_CONSTAT": "Constat amiable manquant",
    "PAS_DE_PHOTOS": "Photos de dommages manquantes",
    "PAS_DE_CONSTAT_PHOTOS": "Constat ET photos de dommages manquants",
}

# Vert = valide, rouge = bloquant, orange = a verifier / donnees suspectes
COULEUR_VALIDE = colors.HexColor("#1e7e34")
COULEUR_INVALIDE = colors.HexColor("#c0392b")
COULEUR_ATTENTION = colors.HexColor("#b8860b")
COULEUR_FOND_VALIDE = colors.HexColor("#eafaf1")
COULEUR_FOND_INVALIDE = colors.HexColor("#fdecea")
COULEUR_FOND_ATTENTION = colors.HexColor("#fef6e0")
COULEUR_ENTETE_TABLE = colors.HexColor("#2c3e50")
COULEUR_LIGNE_ALT = colors.HexColor("#f4f6f7")


def _statut_couleurs(status: str) -> tuple:
    """Renvoie (couleur_texte, couleur_fond) selon la gravite du statut."""
    if status == "A_TRAITER":
        return COULEUR_VALIDE, COULEUR_FOND_VALIDE
    if status == "INVALIDE":
        return COULEUR_INVALIDE, COULEUR_FOND_INVALIDE
    return COULEUR_ATTENTION, COULEUR_FOND_ATTENTION


def _hex(color) -> str:
    """Convertit un reportlab.lib.colors.Color en chaine '#RRGGBB' utilisable
    dans l'attribut color= d'un Paragraph (color.hexval() renvoie '0x..',
    invalide pour le XML de reportlab)."""
    return "#%02x%02x%02x" % (round(color.red * 255), round(color.green * 255), round(color.blue * 255))


# ─── Nommage du fichier ──────────────────────────────────────────────────

def _slug(value) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Za-z0-9]+", "", str(value))


def _build_filename(sinistre_id: int, status: str, num_police: str = None) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    status_slug = _slug(status) or "INCONNU"
    police_slug = _slug(num_police) or "SANSPOLICE"
    sid = f"{int(sinistre_id):05d}" if sinistre_id is not None else "00000"
    return f"RAPPORT_{status_slug}_SIN{sid}_{police_slug}_{ts}.pdf"


# ─── Styles ─────────────────────────────────────────────────────────────

def _build_styles():
    base = getSampleStyleSheet()
    styles = {
        "titre": ParagraphStyle(
            "titre", parent=base["Title"], fontSize=18, spaceAfter=2,
            textColor=COULEUR_ENTETE_TABLE,
        ),
        "sous_titre": ParagraphStyle(
            "sous_titre", parent=base["Normal"], fontSize=10, textColor=colors.grey,
            spaceAfter=10,
        ),
        "section": ParagraphStyle(
            "section", parent=base["Heading1"], fontSize=13, spaceBefore=14,
            spaceAfter=6, textColor=COULEUR_ENTETE_TABLE, borderPadding=0,
        ),
        "sous_section": ParagraphStyle(
            "sous_section", parent=base["Heading2"], fontSize=10.5, spaceBefore=8,
            spaceAfter=4, textColor=COULEUR_ENTETE_TABLE,
        ),
        "corps": ParagraphStyle(
            "corps", parent=base["Normal"], fontSize=9.5, leading=13.5,
        ),
        "corps_petit": ParagraphStyle(
            "corps_petit", parent=base["Normal"], fontSize=8.3, leading=11.5,
            textColor=colors.HexColor("#444444"),
        ),
        "decision_titre": ParagraphStyle(
            "decision_titre", parent=base["Normal"], fontSize=13, leading=16,
            fontName="Helvetica-Bold",
        ),
        "decision_corps": ParagraphStyle(
            "decision_corps", parent=base["Normal"], fontSize=9.5, leading=13,
            spaceBefore=4,
        ),
        "legende": ParagraphStyle(
            "legende", parent=base["Normal"], fontSize=8, textColor=colors.grey,
            alignment=TA_CENTER, spaceBefore=2, spaceAfter=10,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontSize=7.5, textColor=colors.grey,
            leading=10,
        ),
    }
    return styles


def _p(text, style):
    return Paragraph(text if text not in (None, "") else "-", style)


def _hr():
    return HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#d0d0d0"), spaceBefore=4, spaceAfter=8)


# ─── Section : en-tete ──────────────────────────────────────────────────

def _section_header(sinistre_id: int, status: str, email_data: dict, styles) -> list:
    couleur_texte, _ = _statut_couleurs(status)
    generated_at = datetime.now().strftime("%d/%m/%Y a %H:%M")
    story = [
        Paragraph("RAPPORT D'ANALYSE DE SINISTRE", styles["titre"]),
        Paragraph(
            f"Sinistre interne n&#176; {sinistre_id} — genere automatiquement le {generated_at}",
            styles["sous_titre"],
        ),
        _hr(),
    ]
    return story


# ─── Section : bandeau de decision ──────────────────────────────────────

def _build_invalid_reasons(status: str, status_note: str, doc_check: dict,
                            contract_check: dict, coherence_photos: dict) -> list:
    """Compile la liste des raisons precises expliquant pourquoi le dossier
    n'est pas au statut A_TRAITER — tracabilite complete pour l'expert."""
    raisons = []

    if doc_check and not doc_check.get("complete"):
        manquants = doc_check.get("missing") or []
        if manquants:
            raisons.append(f"Document(s) manquant(s) dans l'email : {', '.join(manquants)}.")

    if status_note:
        raisons.append(status_note)

    if contract_check:
        if not contract_check.get("found"):
            checked = contract_check.get("checked") or {}
            raisons.append(
                f"Numero(s) de police detecte(s) sur le constat non trouve(s) en base "
                f"assurance : A={checked.get('A') or 'manquant'}, B={checked.get('B') or 'manquant'}."
            )
        elif contract_check.get("found") and not contract_check.get("valid") and contract_check.get("invalid_reason"):
            raisons.append(f"Contrat n&#176;{contract_check.get('num_police')} : {contract_check['invalid_reason']}")
        elif contract_check.get("found") and contract_check.get("valid") and not contract_check.get("coherent"):
            for m in (contract_check.get("mismatches") or []):
                raisons.append(
                    f"Incoherence champ '{m['champ']}' — constat : '{m['constat']}' / base assurance : '{m['contrat']}'."
                )

    if coherence_photos and coherence_photos.get("coherent") is False:
        raisons.append(f"Photos de dommages incoherentes avec le constat : {coherence_photos.get('explication')}")

    # Deduplique en gardant l'ordre (evite de repeter status_note s'il a deja ete ajoute ailleurs)
    seen = set()
    uniq = []
    for r in raisons:
        if r and r not in seen:
            uniq.append(r)
            seen.add(r)
    return uniq


def _section_decision(status: str, status_note: str, doc_check: dict,
                       contract_check: dict, coherence_photos: dict, styles) -> list:
    couleur_texte, couleur_fond = _statut_couleurs(status)
    libelle = STATUT_LABELS.get(status, status or "Statut inconnu")

    if status == "A_TRAITER":
        titre = "DOSSIER VALIDE — PRET POUR TRAITEMENT"
        corps = [
            _p(
                "Documents requis presents (constat + photos), OCR du constat complet, "
                "photos coherentes avec le constat, contrat identifie, actif et coherent "
                "avec les donnees declarees.",
                styles["decision_corps"],
            )
        ]
    else:
        titre = f"DOSSIER NON VALIDE — {libelle}"
        raisons = _build_invalid_reasons(status, status_note, doc_check, contract_check, coherence_photos)
        if raisons:
            corps = [Paragraph(f"&#8226;&#160;{r}", styles["decision_corps"]) for r in raisons]
        else:
            corps = [_p(status_note or "Raison non precisee.", styles["decision_corps"])]

    cell_content = [Paragraph(titre, ParagraphStyle(
        "decision_titre_couleur", parent=styles["decision_titre"], textColor=couleur_texte,
    ))] + corps

    table = Table([[cell_content]], colWidths=[CONTENT_WIDTH])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), couleur_fond),
        ("BOX", (0, 0), (-1, -1), 1, couleur_texte),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [table, Spacer(1, 12)]


# ─── Section : numero de contrat concerne ───────────────────────────────

def _section_numero_contrat(contract_check: dict, ocr_data: dict, styles) -> list:
    story = [Paragraph("1. Contrat concerne", styles["section"])]

    if contract_check and contract_check.get("contrat_id"):
        data = [
            ["Numero de police", contract_check.get("num_police") or "-"],
            ["Identifiant contrat (base)", str(contract_check.get("contrat_id"))],
            ["Vehicule concerne sur le constat", f"Vehicule {contract_check.get('party')}" if contract_check.get("party") else "-"],
        ]
        story.append(_simple_kv_table(data))
    else:
        assurance_a = ((ocr_data or {}).get("vehicule_a", {}) or {}).get("assurance", {}) or {}
        assurance_b = ((ocr_data or {}).get("vehicule_b", {}) or {}).get("assurance", {}) or {}
        story.append(_p(
            "Aucun contrat n'a pu etre identifie en base assurance pour ce sinistre. "
            f"Police(s) lue(s) sur le constat — Vehicule A : {assurance_a.get('numero_police') or 'manquant'} "
            f"({assurance_a.get('societe') or 'compagnie manquante'}) ; "
            f"Vehicule B : {assurance_b.get('numero_police') or 'manquant'} "
            f"({assurance_b.get('societe') or 'compagnie manquante'}).",
            styles["corps"],
        ))
    story.append(Spacer(1, 6))
    return story


def _simple_kv_table(rows: list, col_widths=None) -> Table:
    col_widths = col_widths or [CONTENT_WIDTH * 0.4, CONTENT_WIDTH * 0.6]
    styles = _build_styles()
    data = [[Paragraph(f"<b>{k}</b>", styles["corps"]), Paragraph(str(v) if v not in (None, "") else "-", styles["corps"])]
            for k, v in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f2f5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# ─── Section : description de l'accident ────────────────────────────────

def _circonstances_labels(circ: dict) -> list:
    if not isinstance(circ, dict):
        return []
    return [CIRCONSTANCES_LABELS.get(k, k.replace("_", " ")) for k, v in circ.items() if v is True]


def _describe_vehicule(ocr_data: dict, prefix: str, lettre: str) -> str:
    veh = (ocr_data or {}).get(prefix, {}) or {}
    auto = veh.get("vehicule", {}) or {}
    marque = auto.get("marque") or "marque non lue"
    modele = auto.get("type_modele") or ""
    immat = auto.get("immatriculation") or "immatriculation non lue"
    circ_labels = _circonstances_labels((ocr_data or {}).get(f"circonstances_{lettre.lower()}", {}))
    circ_txt = ", ".join(circ_labels) if circ_labels else "aucune circonstance cochee"
    return f"<b>Vehicule {lettre}</b> : {marque} {modele} ({immat}) — {circ_txt}."


def _section_description_accident(ocr_data: dict, email_data: dict, styles) -> list:
    story = [Paragraph("2. Description de l'accident", styles["section"])]

    if not ocr_data or "error" in ocr_data:
        story.append(_p(
            "Aucune donnee de constat exploitable (OCR indisponible ou en echec) — "
            "description de l'accident non disponible.",
            styles["corps"],
        ))
        story.append(Spacer(1, 6))
        return story

    acc = ocr_data.get("accident", {}) or {}
    date = acc.get("date") or "date non lue"
    heure = acc.get("heure")
    lieu = acc.get("lieu") or "lieu non precise"
    blesses = acc.get("blesses")

    intro = f"Accident survenu le {date}"
    if heure and str(heure).lower() != "manquant":
        intro += f" a {heure}"
    intro += f", a {lieu}."
    if blesses not in (None, "manquant", False, "False"):
        intro += " <b>Presence de blesse(s) signalee.</b>"

    story.append(_p(intro, styles["corps"]))
    story.append(Spacer(1, 3))
    story.append(_p(_describe_vehicule(ocr_data, "vehicule_a", "A"), styles["corps"]))
    story.append(_p(_describe_vehicule(ocr_data, "vehicule_b", "B"), styles["corps"]))

    if ocr_data.get("croquis_present"):
        story.append(Spacer(1, 3))
        story.append(_p(
            f"<b>Croquis :</b> {ocr_data.get('description_croquis') or 'present mais sans description exploitable'}.",
            styles["corps"],
        ))
    else:
        story.append(_p("<b>Croquis :</b> absent ou non exploitable sur le constat.", styles["corps"]))

    story.append(Spacer(1, 8))
    return story


# ─── Section : degats + photos ──────────────────────────────────────────

def _section_degats(ocr_data: dict, classified_attachments: list, styles) -> list:
    story = [Paragraph("3. Degats declares et constates", styles["section"])]

    if ocr_data and "error" not in ocr_data:
        circ_a = (ocr_data.get("vehicule_a", {}) or {}).get("circulation", {}) or {}
        circ_b = (ocr_data.get("vehicule_b", {}) or {}).get("circulation", {}) or {}
        rows = [
            ["", "Vehicule A", "Vehicule B"],
            ["Point de choc declare", circ_a.get("point_choc") or "-", circ_b.get("point_choc") or "-"],
            ["Degats apparents declares", circ_a.get("degats_apparents") or "-", circ_b.get("degats_apparents") or "-"],
            ["Observations", circ_a.get("observations") or "-", circ_b.get("observations") or "-"],
        ]
        style_cell = _build_styles()["corps_petit"]
        data = [[Paragraph(f"<b>{c}</b>", style_cell) if i == 0 else Paragraph(str(c), style_cell)
                 for c in row] for i, row in enumerate(rows)]
        t = Table(data, colWidths=[CONTENT_WIDTH * 0.28, CONTENT_WIDTH * 0.36, CONTENT_WIDTH * 0.36])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 0), (-1, 0), COULEUR_ENTETE_TABLE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f0f2f5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))
    else:
        story.append(_p("Details des degats indisponibles (OCR du constat non exploitable).", styles["corps"]))

    photos = get_photo_attachments(classified_attachments or [])
    if not photos:
        story.append(_p("<i>Aucune photo de dommages exploitable jointe a ce dossier.</i>", styles["corps"]))
        return story

    story.append(Paragraph(f"Photos de dommages jointes ({len(photos)}) :", styles["sous_section"]))
    for photo in photos:
        img_flowable = _photo_to_flowable(photo)
        if img_flowable:
            legende = _p(photo.get("filename") or "photo", styles["legende"])
            story.append(KeepTogether([img_flowable, legende]))
    return story


def _photo_to_flowable(photo: dict, max_width_cm: float = 12.0, max_height_cm: float = 8.0):
    try:
        raw = base64.b64decode(photo["data"])
        buf = io.BytesIO(raw)
        if PILImage is not None:
            with PILImage.open(io.BytesIO(raw)) as im:
                w, h = im.size
        else:
            w, h = (1000, 700)  # ratio par defaut si Pillow indisponible

        max_w, max_h = max_width_cm * cm, max_height_cm * cm
        ratio = min(max_w / w, max_h / h, 1.0)
        buf.seek(0)
        return RLImage(buf, width=w * ratio, height=h * ratio)
    except Exception as e:
        logger.warning(f"Photo '{photo.get('filename')}' non embarquee dans le PDF (erreur: {e})")
        return None


# ─── Section : responsabilite ───────────────────────────────────────────

def _section_responsabilite(responsabilite: dict, styles) -> list:
    story = [Paragraph("4. Taux de responsabilite estime", styles["section"])]

    taux_a = responsabilite.get("taux_a")
    taux_b = responsabilite.get("taux_b")
    pct_a = f"{round((taux_a or 0) * 100)} %"
    pct_b = f"{round((taux_b or 0) * 100)} %"

    statut_resp = responsabilite.get("statut")
    couleur_resp = COULEUR_VALIDE if statut_resp == "CONFIRME_BAREME" else COULEUR_ATTENTION

    rows = [
        ["", "Vehicule A", "Vehicule B"],
        ["Taux de responsabilite propose", pct_a, pct_b],
    ]
    style_cell = _build_styles()["corps"]
    data = [[Paragraph(f"<b>{c}</b>", style_cell) if i == 0 or j == 0 else Paragraph(str(c), style_cell)
             for j, c in enumerate(row)] for i, row in enumerate(rows)]
    t = Table(data, colWidths=[CONTENT_WIDTH * 0.4, CONTENT_WIDTH * 0.3, CONTENT_WIDTH * 0.3])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (-1, 0), COULEUR_ENTETE_TABLE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f0f2f5")),
        ("FONTSIZE", (1, 1), (-1, -1), 13),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 6))

    badge_txt = {
        "CONFIRME_BAREME": "CONFIRME PAR LE BAREME — taux fiable, aucune expertise complementaire requise sur ce point",
        "PROPOSITION_A_VALIDER": "PROPOSITION A VALIDER — cas non couvert directement par une regle fiable du bareme, assistance par raisonnement automatise : validation humaine requise",
        "INDETERMINE": "INDETERMINE — donnees insuffisantes, repartition par defaut 50/50 : expertise obligatoire",
    }.get(statut_resp, statut_resp or "-")

    story.append(Paragraph(
        f'<font color="{_hex(couleur_resp)}"><b>{badge_txt}</b></font>',
        styles["corps"],
    ))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Explication detaillee du raisonnement :", styles["sous_section"]))
    story.append(_p(responsabilite.get("justification") or "Non renseignee.", styles["corps"]))

    if responsabilite.get("cas_type"):
        story.append(_p(f"<i>Cas du bareme retenu : {responsabilite.get('cas_type')} "
                         f"(methode : {responsabilite.get('methode')}).</i>", styles["corps_petit"]))

    story.append(Spacer(1, 8))
    return story


# ─── Section : coherence photos / constat ───────────────────────────────

def _section_coherence_photos(coherence_photos: dict, styles) -> list:
    story = [Paragraph("5. Controle de coherence photos / constat", styles["section"])]

    coherent = coherence_photos.get("coherent")
    if coherent is True:
        couleur, libelle = COULEUR_VALIDE, "COHERENT"
    elif coherent is False:
        couleur, libelle = COULEUR_INVALIDE, "INCOHERENT"
    else:
        couleur, libelle = COULEUR_ATTENTION, "NON CONCLUANT"

    story.append(Paragraph(f'<font color="{_hex(couleur)}"><b>Resultat : {libelle}</b></font>', styles["corps"]))
    story.append(Spacer(1, 3))

    details = coherence_photos.get("details") or {}
    sous_controles = [
        ("Coherence entre les photos (meme vehicule)", details.get("coherence_inter_photos")),
        ("Coherence points de choc / degats vs constat", details.get("coherence_points_choc_degats")),
        ("Coherence avec le croquis et les circonstances", details.get("coherence_croquis_circonstances")),
    ]
    sous_controles = [(label, sc) for label, sc in sous_controles if sc]
    if sous_controles:
        style_cell = _build_styles()["corps_petit"]
        data = [[Paragraph("<b>Controle</b>", style_cell), Paragraph("<b>Resultat</b>", style_cell), Paragraph("<b>Explication</b>", style_cell)]]
        for label, sc in sous_controles:
            ok = sc.get("coherent")
            resultat = "OK" if ok else ("ECHEC" if ok is False else "?")
            data.append([Paragraph(label, style_cell), Paragraph(resultat, style_cell), Paragraph(sc.get("explication", "-"), style_cell)])
        t = Table(data, colWidths=[CONTENT_WIDTH * 0.32, CONTENT_WIDTH * 0.13, CONTENT_WIDTH * 0.55])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 0), (-1, 0), COULEUR_ENTETE_TABLE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))

    story.append(Paragraph("Explication detaillee :", styles["sous_section"]))
    story.append(_p(coherence_photos.get("explication") or "Non renseignee.", styles["corps"]))
    story.append(Spacer(1, 8))
    return story


# ─── Section : detail du contrat (base assurance) ───────────────────────

def _bool_txt(v) -> str:
    if v is True:
        return "Oui"
    if v is False:
        return "Non"
    return "-"


def _montant(v) -> str:
    if v in (None, ""):
        return "-"
    try:
        return f"{float(v):,.2f} DT".replace(",", " ")
    except (TypeError, ValueError):
        return str(v)


def _section_contrat_detail(contract_full: dict, styles) -> list:
    story = [Paragraph("6. Informations contrat (base assurance)", styles["section"])]

    story.append(Paragraph("Contrat", styles["sous_section"]))
    story.append(_simple_kv_table([
        ("Identifiant contrat", contract_full.get("contrat_id")),
        ("Numero de police", contract_full.get("num_police")),
        ("Type de contrat", contract_full.get("contrat_type_contrat")),
        ("Statut du contrat", contract_full.get("contrat_statut")),
        ("Bonus/malus", contract_full.get("contrat_bonus_malus")),
        ("Date d'effet", contract_full.get("contrat_date_effet")),
        ("Date d'expiration", contract_full.get("contrat_date_expiration")),
        ("Prime annuelle", _montant(contract_full.get("contrat_prime_annuelle"))),
        ("Agence", f"{contract_full.get('contrat_agence') or '-'} (n&#176;{contract_full.get('contrat_numero_agence') or '-'})"),
    ]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Vehicule assure", styles["sous_section"]))
    story.append(_simple_kv_table([
        ("Marque / modele", f"{contract_full.get('vehicule_marque') or '-'} {contract_full.get('vehicule_modele') or ''}"),
        ("Annee", contract_full.get("vehicule_annee")),
        ("Immatriculation", contract_full.get("vehicule_immatriculation")),
        ("Couleur", contract_full.get("vehicule_couleur")),
        ("Energie", contract_full.get("vehicule_energie")),
        ("Usage", contract_full.get("vehicule_usage")),
        ("Valeur assuree", _montant(contract_full.get("vehicule_valeur_assuree"))),
    ]))
    story.append(Spacer(1, 8))

    # ── Garanties ──
    story.append(Paragraph("Garanties", styles["sous_section"]))
    garanties_rows = [
        ("Dommages Collision", "garantie_dommages_collision_active", "garantie_dommages_collision_franchise",
         "garantie_dommages_collision_plafond", "garantie_dommages_collision_couverture"),
        ("Responsabilite Civile (RC)", "garantie_rc_active", "garantie_rc_franchise",
         "garantie_rc_plafond", "garantie_rc_couverture"),
        ("Vol", "garantie_vol_active", "garantie_vol_franchise",
         "garantie_vol_plafond", "garantie_vol_couverture"),
        ("Incendie", "garantie_incendie_active", "garantie_incendie_franchise",
         "garantie_incendie_plafond", "garantie_incendie_couverture"),
        ("Bris de glace", "garantie_bris_glace_active", "garantie_bris_glace_franchise",
         "garantie_bris_glace_plafond", "garantie_bris_glace_couverture"),
    ]
    style_cell = _build_styles()["corps_petit"]
    header = ["Garantie", "Active", "Franchise", "Plafond", "Couverture"]
    data = [[Paragraph(f"<b>{h}</b>", style_cell) for h in header]]
    for label, k_active, k_franchise, k_plafond, k_couv in garanties_rows:
        data.append([
            Paragraph(label, style_cell),
            Paragraph(_bool_txt(contract_full.get(k_active)), style_cell),
            Paragraph(_montant(contract_full.get(k_franchise)), style_cell),
            Paragraph(_montant(contract_full.get(k_plafond)), style_cell),
            Paragraph(str(contract_full.get(k_couv)) if contract_full.get(k_couv) is not None else "-", style_cell),
        ])
    t = Table(data, colWidths=[CONTENT_WIDTH * 0.28, CONTENT_WIDTH * 0.13, CONTENT_WIDTH * 0.20, CONTENT_WIDTH * 0.20, CONTENT_WIDTH * 0.19])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (-1, 0), COULEUR_ENTETE_TABLE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    # ── Exclusions ──
    story.append(Paragraph("Exclusions", styles["sous_section"]))
    story.append(_simple_kv_table([
        ("Conduite sous alcool", _bool_txt(contract_full.get("exclusion_conduite_sous_alcool"))),
        ("Conducteur non autorise", _bool_txt(contract_full.get("exclusion_conducteur_non_autorise"))),
    ]))
    story.append(Spacer(1, 8))
    return story


# ─── Section : tracabilite / pied de page ───────────────────────────────

def _section_tracabilite(sinistre_id: int, email_data: dict, status: str, styles) -> list:
    story = [_hr()]
    generated_at = datetime.now().strftime("%d/%m/%Y a %H:%M:%S")
    story.append(Paragraph(
        f"Rapport genere automatiquement le {generated_at} — Sinistre interne n&#176;{sinistre_id} — "
        f"Statut au moment de la generation : {status}. "
        f"Expediteur : {email_data.get('sender', '-')} — Sujet : {email_data.get('subject', '-')}.<br/>"
        "Ce document est une aide a la decision generee automatiquement a partir de l'OCR du constat, "
        "des photos jointes et de la base assurance. Il ne remplace pas l'analyse d'un gestionnaire "
        "sinistre ou d'un expert, qui reste seul decisionnaire final.",
        styles["footer"],
    ))
    return story


# ─── Point d'entree ─────────────────────────────────────────────────────

def generate_pdf_report(
    sinistre_id: int,
    email_data: dict,
    ocr_data: dict | None,
    doc_check: dict | None,
    status: str,
    status_note: str | None,
    responsabilite: dict | None,
    coherence_photos: dict | None,
    contract_check: dict | None,
    contract_full: dict | None,
    classified_attachments: list | None,
) -> str | None:
    """
    Construit et ecrit sur disque le rapport d'analyse PDF pour ce sinistre.
    Renvoie le chemin absolu du fichier genere, ou None en cas d'echec
    (n'interrompt jamais le pipeline appelant : toute erreur est capturee et
    journalisee).
    """
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        num_police = (contract_check or {}).get("num_police")
        filename = _build_filename(sinistre_id, status, num_police)
        filepath = os.path.join(OUTPUT_DIR, filename)

        doc = SimpleDocTemplate(
            filepath, pagesize=A4,
            leftMargin=1.8 * cm, rightMargin=1.8 * cm,
            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
            title=f"Rapport d'analyse sinistre {sinistre_id}",
            author="Agent mailconnector",
        )

        styles = _build_styles()
        story = []
        story += _section_header(sinistre_id, status, email_data, styles)
        story += _section_decision(status, status_note, doc_check, contract_check, coherence_photos, styles)
        story += _section_numero_contrat(contract_check, ocr_data, styles)
        story += _section_description_accident(ocr_data, email_data, styles)
        story += _section_degats(ocr_data, classified_attachments, styles)

        if responsabilite:
            story += _section_responsabilite(responsabilite, styles)

        if coherence_photos and coherence_photos.get("analyzed"):
            story += _section_coherence_photos(coherence_photos, styles)

        if contract_full:
            story.append(PageBreak())
            story += _section_contrat_detail(contract_full, styles)

        story += _section_tracabilite(sinistre_id, email_data, status, styles)

        doc.build(story)
        logger.info(f"→ Rapport d'analyse PDF genere : {filepath}")
        return filepath

    except Exception as e:
        logger.error(f"Echec generation rapport PDF pour sinistre_id={sinistre_id}: {e}")
        return None
