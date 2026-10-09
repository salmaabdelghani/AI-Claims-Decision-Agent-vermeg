"""
Detection et traitement des emails de "complement de dossier".

Cas vise : un client a deja envoye une declaration de sinistre incomplete
(constat et/ou photos manquants). Il renvoie ensuite un nouvel email avec
le(s) document(s) manquant(s). Cet email doit :
  1. Etre reconnu comme relie a une declaration de sinistre existante
     (et pas traite comme une toute nouvelle declaration independante).
  2. Etre verifie contre le dossier existant : meme expediteur + statut
     "incomplet" en base + confirmation dans le md_content ("Dossier Incomplet").
  3. Si les pieces jointes correspondent bien au(x) document(s) manquant(s)
     (constat / photos), elles sont ajoutees au dossier (Mongo + Postgres),
     le statut est recalcule, et le md_content est REGENERE dans le MEME
     FORMAT qu'un dossier recu complet des le depart (memes sections :
     Informations email / Resume / Pieces jointes / OCR / Metadonnees),
     avec juste une petite section "Historique" en trace : email original
     (id + date) et email de completion (id + date).

Si aucune correspondance n'est trouvee, la fonction renvoie False et
l'email est alors traite normalement par le pipeline principal (main.py),
comme une declaration potentiellement nouvelle.
"""
import base64
import logging
import mimetypes
from email.utils import parseaddr

from agent.classifier import classify_attachment
from agent.constat_ocr import check_required_documents, determine_status, extract_constat
from agent.report_generator import generate_sinistre_md
from agent.email_sender import build_complete_reply, build_missing_documents_reply
from agent.photo_damage_analyzer import analyze_photo_coherence
from agent.responsabilite import determine_responsabilite
from agent.pdf_report_generator import generate_pdf_report

logger = logging.getLogger(__name__)

INCOMPLETE_STATUSES = ("PAS_DE_CONSTAT", "PAS_DE_PHOTOS", "PAS_DE_CONSTAT_PHOTOS")


def extract_email_address(raw_sender: str) -> str:
    """Extrait juste l'adresse email d'un champ From brut ('Nom <email>')."""
    _, addr = parseaddr(raw_sender or "")
    return addr


def _photos_with_data(all_docs: list[dict], new_attachments: list[dict], mongo) -> list[dict]:
    """
    Reconstitue la liste des photos de dommages AVEC leur contenu binaire
    (champ "data" en base64), requis par analyze_photo_coherence().

    - Les pieces jointes de CET email (new_attachments) l'ont deja en memoire.
    - Les documents deja stockes lors de la declaration initiale (all_docs,
      issus de Postgres) n'ont que leurs metadonnees : on va chercher leur
      contenu dans MongoDB GridFS via leur gridfs_id.
    """
    new_by_filename = {a.get("filename"): a for a in new_attachments if a.get("data")}
    result = []

    for doc in all_docs:
        nature = (doc.get("nature") or "").lower()
        if not ("photo" in nature or "dommage" in nature):
            continue

        if doc.get("filename") in new_by_filename:
            result.append(new_by_filename[doc["filename"]])
            continue

        gridfs_id = doc.get("gridfs_id")
        if not gridfs_id:
            continue
        try:
            raw_bytes = mongo.get_attachment(gridfs_id)
            content_type = mimetypes.guess_type(doc.get("filename") or "")[0] or "image/jpeg"
            result.append({
                "filename": doc.get("filename"),
                "nature": doc.get("nature"),
                "content_type": content_type,
                "data": base64.b64encode(raw_bytes).decode("utf-8"),
            })
        except Exception as e:
            logger.warning(
                f"Impossible de recuperer la photo '{doc.get('filename')}' depuis "
                f"MongoDB (gridfs_id={gridfs_id}) pour l'analyse de coherence: {e}"
            )

    return result


def try_process_complement(email_data: dict, pg, mongo, contracts_db, mailer) -> bool:
    """
    Tente de traiter cet email comme un complement a un dossier existant.

    Retourne True si l'email a ete traite comme complement (le pipeline
    principal doit alors etre saute pour cet email), False sinon (le
    pipeline principal doit s'executer normalement).
    """
    if not email_data.get("attachments"):
        return False

    sender_email = extract_email_address(email_data.get("sender"))
    if not sender_email:
        return False

    pending = pg.find_pending_incomplete_sinistre(sender_email)
    if not pending:
        return False

    status = pending["status"]
    if status not in INCOMPLETE_STATUSES:
        return False

    missing_constat = status in ("PAS_DE_CONSTAT", "PAS_DE_CONSTAT_PHOTOS")
    missing_photos = status in ("PAS_DE_PHOTOS", "PAS_DE_CONSTAT_PHOTOS")

    # ── Classifie les pieces jointes du nouvel email ────────────────────────
    new_attachments = []
    for att in email_data["attachments"]:
        att_type, nature = classify_attachment(att)
        new_attachments.append({**att, "classified_type": att_type, "nature": nature})

    natures = [a["nature"].lower() for a in new_attachments]
    brings_constat = missing_constat and any("constat" in n for n in natures)
    brings_photos = missing_photos and any(("photo" in n or "dommage" in n) for n in natures)

    if not (brings_constat or brings_photos):
        logger.info(
            f"Email de {sender_email} : dossier incomplet existant trouve "
            f"(id={pending['id']}, statut={status}) mais aucune piece jointe "
            f"ne correspond au document manquant — traite comme email independant."
        )
        return False

    sinistre_id = pending["id"]
    logger.info(
        f"→ COMPLEMENT detecte pour sinistre id={sinistre_id} "
        f"(statut precedent={status}) — nouvelles pieces : "
        f"{[a['filename'] for a in new_attachments]}"
    )

    # ── Stockage MongoDB des nouvelles pieces jointes ───────────────────────
    gridfs_ids = mongo.store_attachments(
        attachments=new_attachments, sinistre_id=sinistre_id, email_data=email_data,
    )
    for att, gid in zip(new_attachments, gridfs_ids):
        att["gridfs_id"] = gid

    # ── Stockage PostgreSQL des nouvelles pieces jointes ────────────────────
    pg.add_documents_to_sinistre(sinistre_id, new_attachments)

    # ── Recalcul de l'etat des documents (anciens + nouveaux confondus) ─────
    all_docs = pg.get_documents_for_sinistre(sinistre_id)
    doc_check = check_required_documents(all_docs)

    # ── OCR : nouveau constat fourni -> extraction ; sinon reutilise l'OCR
    #    deja stocke lors de la declaration initiale (cas ou seules les
    #    photos manquaient) ─────────────────────────────────────────────────
    ocr_data = None
    if brings_constat:
        constat_att = next((a for a in new_attachments if "constat" in a["nature"].lower()), None)
        if constat_att:
            ocr_data = extract_constat(constat_att)
            if "error" not in ocr_data:
                pg.store_constat_ocr(sinistre_id, ocr_data)
    elif doc_check["has_constat"]:
        ocr_data = pg.get_constat_ocr_json(sinistre_id)

    # ── Determination du nouveau statut ─────────────────────────────────────
    status_result = determine_status(doc_check, ocr_data)
    new_status = status_result["status"]
    new_note = status_result["note"]

    contract_check = None
    if new_status == "A_TRAITER" and ocr_data and "error" not in ocr_data:
        try:
            contract_check = contracts_db.verify_from_ocr(ocr_data)
            if not contract_check["found"]:
                new_status = "CONTRAT_INTROUVABLE"
                new_note = (
                    f"Aucun contrat correspondant trouve en base assurance "
                    f"(numeros de police detectes: {contract_check['checked']})."
                )
            elif not contract_check["valid"]:
                new_status = "CONTRAT_INVALIDE"
                new_note = contract_check["invalid_reason"]
        except Exception as e:
            logger.warning(f"Verification contrat impossible lors du complement: {e}")

    # Details complets du contrat (garanties/exclusions/vehicule) pour le
    # rapport PDF — voir main.py, meme logique.
    contract_full = None
    if contract_check and contract_check.get("contrat_id"):
        contract_full = contracts_db.get_full_contract_details(contract_check["contrat_id"])

    # ── Coherence photos de dommages <-> constat ─────────────────────────────
    # Meme controle que dans le pipeline principal (main.py) : des que le
    # dossier est complet (constat + photos) et que l'OCR a reussi, on
    # verifie que les photos correspondent au constat. Une incoherence
    # est prioritaire sur tout autre statut.
    # `photos_hydratees` est calcule ici (pas seulement quand la coherence
    # est verifiee) car il est reutilise plus bas pour embarquer les photos
    # dans le rapport PDF, meme sur un dossier qui reste incomplet.
    photos_hydratees = _photos_with_data(all_docs, new_attachments, mongo)
    coherence_photos = None
    if doc_check["complete"] and ocr_data and "error" not in ocr_data:
        coherence_photos = analyze_photo_coherence(photos_hydratees, ocr_data)
        if coherence_photos.get("coherent") is False:
            new_status = "INVALIDE"
            new_note = coherence_photos.get("explication")
            logger.warning(
                f"→ Photos INCOHERENTES avec le constat (complement) — {new_note}"
            )

    # ── Determination du taux de responsabilite (meme logique que main.py) ──
    # Manquait jusqu'ici dans le flux "complement" : un dossier complete via
    # un email de complement ne se voyait jamais attribuer de taux, meme une
    # fois passe A_TRAITER.
    responsabilite = None
    if new_status == "A_TRAITER" and ocr_data and "error" not in ocr_data:
        responsabilite = determine_responsabilite(ocr_data, overrides=pg.get_bareme_overrides())
        logger.info(
            f"→ Responsabilite proposee (complement) : A={round(responsabilite['taux_a']*100)}% "
            f"B={round(responsabilite['taux_b']*100)}% (cas {responsabilite['cas_type']}, "
            f"statut={responsabilite['statut']})"
        )

    # ── Regeneration complete du md_content (meme format qu'un dossier
    #    recu complet des le depart) ─────────────────────────────────────────
    new_md_content = _regenerate_full_md(
        pending=pending, email_data=email_data, all_docs=all_docs,
        doc_check=doc_check, ocr_data=ocr_data, status=new_status, status_note=new_note,
        coherence_photos=coherence_photos, responsabilite=responsabilite,
    )

    pg.replace_after_complement(
        sinistre_id, new_md_content, new_status,
        mongo_ref_append=",".join(gridfs_ids),
    )

    if responsabilite:
        pg.update_sinistre_responsabilite(sinistre_id, responsabilite)

    # ── Reponse automatique au client ────────────────────────────────────────
    try:
        if doc_check["complete"]:
            subject, body = build_complete_reply(email_data)
        else:
            subject, body = build_missing_documents_reply(email_data, doc_check["missing"])
        mailer.send_reply(email_data, subject, body)
    except Exception as e:
        logger.error(f"Echec envoi email de reponse (complement): {e}")

    # ── Rapport d'analyse PDF (meme logique que main.py, ETAPE 8bis) ────────
    # Manquait entierement dans le flux "complement" : un dossier complete
    # via un email de complement ne generait jusqu'ici aucun rapport PDF.
    pdf_path = generate_pdf_report(
        sinistre_id=sinistre_id,
        email_data=original_email_data_for_client(pending, email_data),
        ocr_data=ocr_data,
        doc_check=doc_check,
        status=new_status,
        status_note=new_note,
        responsabilite=responsabilite,
        coherence_photos=coherence_photos,
        contract_check=contract_check,
        contract_full=contract_full,
        classified_attachments=photos_hydratees,
    )
    if pdf_path:
        logger.info(f"→ Rapport d'analyse PDF disponible (complement) : {pdf_path}")

    pg.update_sinistre_agent_details(
        sinistre_id,
        contract_check=contract_check,
        coherence_photos=coherence_photos,
        pdf_path=pdf_path,
    )

    pg.set_agent_activity("decision", f"Decision finale (complement) : {new_status}")
    if new_status == "A_TRAITER":
        logger.info(f"✅ Complement traite — sinistre id={sinistre_id} desormais A_TRAITER "
                    f"— en attente de confirmation par un gestionnaire.")
    else:
        logger.info(f"⚠️ Complement traite — sinistre id={sinistre_id}, statut={new_status}.")

    return True


def original_email_data_for_client(pending: dict, email_data: dict) -> dict:
    """
    Reconstruit un dict minimal (message_id/sender/subject/date) a partir
    du dossier ORIGINAL en base, pour l'envoi au mock_api. On garde le
    message_id/sujet/date de la declaration initiale (c'est elle qui
    identifie le dossier), mais rien n'empeche de retracer l'email de
    complement dans les logs si besoin.
    """
    return {
        "message_id": pending.get("message_id"),
        "sender": pending.get("sender"),
        "subject": pending.get("subject"),
        "date": pending.get("email_date"),
    }


def _regenerate_full_md(pending: dict, email_data: dict, all_docs: list[dict],
                         doc_check: dict, ocr_data: dict, status: str, status_note: str,
                         coherence_photos: dict = None, responsabilite: dict = None) -> str:
    """
    Reconstruit le md_content complet du dossier, EXACTEMENT dans le meme
    format qu'un dossier recu complet des le depart (generate_sinistre_md),
    en repartant des informations de l'email ORIGINAL (expediteur, objet,
    date, resume, type de sinistre) fusionnees avec l'ensemble des documents
    desormais disponibles (anciens + nouveaux). Une section "Historique" est
    ajoutee a la fin pour tracer les deux emails (original + completion).
    """
    original_email_data = {
        "sender": pending.get("sender"),
        "cc": pending.get("cc"),
        "bcc": pending.get("bcc"),
        "subject": pending.get("subject"),
        "date": pending.get("email_date"),
    }
    classification = {
        "sinistre_type": pending.get("sinistre_type"),
        "confidence": pending.get("confidence") or 0,
        "reason": pending.get("reason"),
    }
    # Reconstitue une liste "classified_attachments" au format attendu par
    # generate_sinistre_md a partir de TOUS les documents en base (anciens +
    # nouveaux) — la colonne "source" (integree/jointe) n'est pas conservee
    # en base, elle est donc affichee par defaut comme "Jointe".
    merged_attachments = [
        {
            "filename": d.get("filename"),
            "classified_type": d.get("file_format"),
            "nature": d.get("nature"),
            "size_bytes": d.get("size_bytes", 0),
            "source": "attachment",
        }
        for d in all_docs
    ]
    analysis = {
        "summary": pending.get("summary"),
        "classified_attachments": merged_attachments,
    }

    md_content = generate_sinistre_md(
        original_email_data, classification, analysis,
        ocr_data=ocr_data, doc_check=doc_check,
        status=status, status_note=status_note,
        coherence_photos=coherence_photos,
        responsabilite=responsabilite,
    )

    # ── Trace : email original (incomplet) + email de completion ───────────
    history_lines = [
        "---", "",
        "## Historique du dossier", "",
        f"- **Declaration initiale (incomplete)** — email `{pending.get('message_id') or 'N/A'}` "
        f"du {pending.get('email_date') or 'N/A'} (recu {pending.get('created_at') or ''})",
        f"- **Complement (documents manquants renvoyes)** — email "
        f"`{email_data.get('message_id') or 'N/A'}` du {email_data.get('date') or 'N/A'}",
        "",
    ]
    return md_content + "\n".join(history_lines)
