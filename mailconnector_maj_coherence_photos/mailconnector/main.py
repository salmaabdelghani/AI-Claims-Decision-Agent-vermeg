"""
Agent de monitoring de sinistres — Pipeline complet :
1. Lecture emails non lus
2. Classification sinistre/non-sinistre
3. Analyse pieces jointes (vision LLM)
4. Verification documents requis (constat + photos)
5. OCR du constat amiable (extraction de tous les champs)
6. Determination du statut final
7. Stockage PostgreSQL + MongoDB GridFS

Statuts possibles en base (colonne sinistres.status) :
  PAS_DE_CONSTAT          : aucun constat trouve dans l'email
  PAS_DE_PHOTOS           : aucune photo de dommages trouvee
  PAS_DE_CONSTAT_PHOTOS   : les deux manquent
  CONSTAT_INCOMPLET       : constat present mais OCR n'a pas extrait assez de champs
  CONTRAT_INTROUVABLE     : constat/OCR complets mais aucun contrat correspondant en base assurance
  CONTRAT_INVALIDE        : le contrat existe mais n'est pas exploitable pour ce sinistre
                            (statut != "Actif" et/ou date du sinistre hors periode de
                            couverture [date_effet, date_expiration])
  CONTRAT_INCOHERENT      : le contrat existe et est valide, mais au moins une info lue sur
                            le constat (agence, attestation valable, nom/prenom assure,
                            marque/modele/immatriculation vehicule) ne correspond pas a la
                            base assurance
  INVALIDE                : constat et photos presents et OCR complet, mais les photos de
                            dommages sont incoherentes avec le constat (vehicules differents
                            entre les photos, point de choc / degats ne correspondant pas a
                            ceux declares, ou incompatibles avec le croquis et les
                            circonstances cochees) — voir section "Coherence constat-degats"
                            du rapport pour l'explication detaillee
  A_TRAITER               : dossier complet, contrat trouve, valide ET coherent avec la base,
                            pret pour traitement humain
"""
import os
import time
import logging

from dotenv import load_dotenv
load_dotenv(encoding="latin-1")

from agent.email_monitor import EmailMonitor, parse_email
from agent.classifier import classify_email, analyze_sinistre
from agent.report_generator import generate_sinistre_md, slug_from_email
from agent.constat_ocr import (
    check_required_documents, extract_constat, get_constat_attachment,
    determine_status,
)
from agent.responsabilite import determine_responsabilite
from agent.photo_damage_analyzer import analyze_photo_coherence
from agent.pdf_report_generator import generate_pdf_report
from agent.email_sender import (
    EmailSender, build_complete_reply, build_missing_documents_reply,
)
from agent.complement_handler import try_process_complement
from storage.postgres_storage import PostgresStorage
from storage.mongo_storage import MongoGridFSStorage
from storage.contract_storage import ContractStorage
from ressources.insurance_companies import set_companies as set_insurance_companies

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("main")


def run_agent():
    pg = PostgresStorage(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        dbname=os.environ.get("POSTGRES_DB", "sinistres"),
        user=os.environ.get("POSTGRES_USER", "user"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
    )
    pg.connect()
    pg.initialize_schema()

    # Charge la liste courante (editable depuis le dashboard) des compagnies
    # d'assurance reconnues par l'OCR — voir ressources/insurance_companies.py.
    set_insurance_companies(pg.get_insurance_companies())

    mongo = MongoGridFSStorage(
        mongo_uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017/"),
        db_name=os.environ.get("MONGO_DB", "sinistres"),
    )
    mongo.connect()

    contracts_db = ContractStorage(
        host=os.environ.get("CONTRACTS_DB_HOST", os.environ.get("POSTGRES_HOST", "localhost")),
        port=int(os.environ.get("CONTRACTS_DB_PORT", os.environ.get("POSTGRES_PORT", 5432))),
        dbname=os.environ.get("CONTRACTS_DB_NAME", os.environ.get("POSTGRES_DB", "sinistres")),
        user=os.environ.get("CONTRACTS_DB_USER", os.environ.get("POSTGRES_USER", "user")),
        password=os.environ.get("CONTRACTS_DB_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "")),
    )
    contracts_db.connect()

    monitor = EmailMonitor(
        imap_host=os.environ.get("IMAP_HOST", "imap.gmail.com"),
        username=os.environ["IMAP_USERNAME"],
        password=os.environ["IMAP_PASSWORD"],
        port=int(os.environ.get("IMAP_PORT", 993)),
    )

    # Reutilise par defaut les identifiants IMAP pour l'envoi SMTP (cas usuel
    # Gmail : meme compte + mot de passe d'application pour lire et envoyer).
    # Surcharge possible via des variables SMTP_* dediees dans le .env.
    mailer = EmailSender(
        smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        username=os.environ.get("SMTP_USERNAME", os.environ["IMAP_USERNAME"]),
        password=os.environ.get("SMTP_PASSWORD", os.environ["IMAP_PASSWORD"]),
        port=int(os.environ.get("SMTP_PORT", 587)),
        use_tls=os.environ.get("SMTP_USE_TLS", "true").lower() != "false",
        display_name=os.environ.get("SMTP_DISPLAY_NAME", "Service Sinistres"),
    )

    logger.info("Agent pret — pilotage (demarrer/arreter, intervalle de polling) depuis le dashboard.")

    try:
        while True:
            config = pg.get_agent_config()
            if not config.get("is_running"):
                pg.set_agent_idle()
                time.sleep(5)  # verifie frequemment si le gestionnaire vient de demarrer l'agent
                continue

            process_inbox(monitor, pg, mongo, contracts_db, mailer)
            interval = max(5, int(config.get("polling_interval_seconds") or 60))
            logger.info(f"Prochain cycle dans {interval}s...")
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Arret de l'agent.")
    finally:
        monitor.disconnect()
        pg.close()
        mongo.close()
        contracts_db.close()


def process_inbox(monitor: EmailMonitor, pg: PostgresStorage, mongo: MongoGridFSStorage,
                   contracts_db: ContractStorage, mailer: EmailSender):
    try:
        monitor.connect()
        raw_emails = monitor.fetch_unread_emails(
            folder=os.environ.get("IMAP_FOLDER", "INBOX")
        )
        logger.info(f"{len(raw_emails)} email(s) non lu(s) trouve(s).")
        if not raw_emails:
            pg.set_agent_idle()
    except Exception as e:
        logger.error(f"Erreur IMAP: {e}")
        pg.set_agent_idle()
        return

    for raw in raw_emails:
        monitor.mark_as_read(raw["id"])
        time.sleep(2)
        email_data = parse_email(raw["parsed"])
        logger.info(f"Analyse: [{email_data['subject']}] de {email_data['sender']}")
        pg.set_agent_activity("reception", "Lecture de l'email", sender=email_data.get("sender"),
                               subject=email_data.get("subject"), reset_started=True)

        # ── ETAPE 0 : Ce mail complete-t-il un dossier existant incomplet ? ──
        # (meme expediteur + statut incomplet en base + document manquant
        # effectivement fourni). Si oui, le dossier existant est mis a jour
        # et on ne traite PAS cet email comme une nouvelle declaration.
        if try_process_complement(email_data, pg, mongo, contracts_db, mailer):
            continue

        # ── ETAPE 1 : Classification sinistre ──────────────────────────────
        pg.set_agent_activity("detection", "Classification de l'email (sinistre ou non)")
        classification = classify_email(email_data)

        if not classification.get("is_sinistre"):
            logger.info("→ Pas un sinistre, ignore.")
            continue

        logger.info(
            f"→ SINISTRE detecte ({classification.get('sinistre_type')}, "
            f"confiance {round(classification.get('confidence', 0)*100)}%)"
        )

        # ── ETAPE 2 : Analyse pieces jointes ───────────────────────────────
        analysis = analyze_sinistre(email_data)

        # ── ETAPE 3 : Verification documents requis ────────────────────────
        pg.set_agent_activity("documents", "Verification des documents recus (constat / photos)")
        doc_check = check_required_documents(analysis["classified_attachments"])

        # ── ETAPE 3bis : Reponse automatique au client ──────────────────────
        # Independant du reste du pipeline (OCR / contrat) : on informe le
        # client uniquement sur la base de la presence du constat et des
        # photos de dommages dans son email.
        try:
            if doc_check["complete"]:
                subject, body = build_complete_reply(email_data)
                mailer.send_reply(email_data, subject, body)
                logger.info("→ Email envoye : accuse de reception (dossier complet).")
            else:
                subject, body = build_missing_documents_reply(email_data, doc_check["missing"])
                mailer.send_reply(email_data, subject, body)
                logger.info(f"→ Email envoye : demande de document(s) manquant(s) ({', '.join(doc_check['missing'])}).")
        except Exception as e:
            logger.error(f"Echec envoi email de reponse automatique: {e}")

        ocr_data = None

        # ── ETAPE 4 : OCR (uniquement si constat present) ───────────────────
        if doc_check["has_constat"]:
            pg.set_agent_activity("ocr", "Lecture automatique du constat amiable (OCR)")
            constat_att = get_constat_attachment(analysis["classified_attachments"])
            if constat_att:
                ocr_data = extract_constat(constat_att)
                if "error" not in ocr_data:
                    acc = ocr_data.get("accident", {})
                    logger.info(
                        f"OCR constat: date={acc.get('date')} lieu={acc.get('lieu')} "
                        f"completude={ocr_data.get('completude_pct')}%"
                    )
                else:
                    logger.error(f"Echec OCR: {ocr_data['error']}")

        # ── ETAPE 4bis : Verification du contrat dans la base assurance ────
        contract_check = None
        if ocr_data and "error" not in ocr_data:
            pg.set_agent_activity("contrat", "Verification du contrat en base assurance")
            contract_check = contracts_db.verify_from_ocr(ocr_data)
            if contract_check["found"] and contract_check["valid"] and contract_check["coherent"]:
                logger.info(
                    f"→ Contrat trouve et valide — contrat_id={contract_check['contrat_id']} "
                    f"(police {contract_check['num_police']}, vehicule {contract_check['party']})"
                )
            elif contract_check["found"] and contract_check["valid"] and not contract_check["coherent"]:
                logger.warning(
                    f"→ Contrat trouve et valide mais donnees INCOHERENTES avec la base "
                    f"(police {contract_check['num_police']}) — {contract_check['mismatches']}"
                )
            elif contract_check["found"] and not contract_check["valid"]:
                logger.warning(
                    f"→ Contrat trouve mais INVALIDE pour ce sinistre "
                    f"(police {contract_check['num_police']}) — {contract_check['invalid_reason']}"
                )
            else:
                logger.warning(
                    f"→ Aucun contrat correspondant en base assurance "
                    f"(polices detectees: {contract_check['checked']})"
                )

        # Details complets du contrat (garanties/exclusions/vehicule) pour le
        # rapport PDF — recupere des qu'un contrat a ete identifie en base,
        # meme s'il s'avere invalide/incoherent ensuite (utile pour que
        # l'expert voie le contrat concerne dans le rapport quel que soit
        # le statut final).
        contract_full = None
        if contract_check and contract_check.get("contrat_id"):
            contract_full = contracts_db.get_full_contract_details(contract_check["contrat_id"])

        # ── ETAPE 4ter : Coherence photos de dommages <-> constat ──────────
        # Uniquement quand constat + photos sont presents et l'OCR a reussi :
        # verifie que les photos correspondent bien entre elles (meme
        # vehicule), que la zone de choc/degats visible correspond au point
        # de choc / degats declares dans le constat, et que le tout est
        # coherent avec le croquis et les circonstances cochees.
        coherence_photos = None
        if doc_check["complete"] and ocr_data and "error" not in ocr_data:
            pg.set_agent_activity("photos", "Controle de coherence des photos de dommages")
            coherence_photos = analyze_photo_coherence(
                analysis["classified_attachments"], ocr_data
            )
            if coherence_photos.get("coherent") is False:
                logger.warning(
                    f"→ Photos INCOHERENTES avec le constat — {coherence_photos.get('explication')}"
                )
            elif coherence_photos.get("coherent") is True:
                logger.info("→ Photos coherentes avec le constat (points de choc, degats, croquis).")
            else:
                logger.info(
                    f"→ Analyse de coherence photos/constat non concluante — {coherence_photos.get('explication')}"
                )

        # ── ETAPE 5 : Determination du statut final ─────────────────────────
        status_result = determine_status(doc_check, ocr_data)
        status = status_result["status"]
        note   = status_result["note"]

        # Si tout est complet mais que le contrat n'est pas exploitable, on ne
        # passe pas le dossier en A_TRAITER :
        #   - police introuvable en base -> CONTRAT_INTROUVABLE
        #   - police trouvee mais statut != Actif ou hors periode de
        #     couverture -> CONTRAT_INVALIDE (motif precis dans la note)
        if status == "A_TRAITER" and contract_check is not None and not contract_check["found"]:
            status = "CONTRAT_INTROUVABLE"
            note = (
                f"Aucun contrat correspondant trouve en base assurance "
                f"(numeros de police detectes: {contract_check['checked']})."
            )
        elif status == "A_TRAITER" and contract_check is not None and contract_check["found"] and not contract_check["valid"]:
            status = "CONTRAT_INVALIDE"
            note = contract_check["invalid_reason"]
        elif status == "A_TRAITER" and contract_check is not None and contract_check["found"] \
                and contract_check["valid"] and not contract_check["coherent"]:
            status = "CONTRAT_INCOHERENT"
            details = "; ".join(
                f"{m['champ']} (constat: '{m['constat']}' / base: '{m['contrat']}')"
                for m in contract_check["mismatches"]
            )
            note = f"Donnees du constat non conformes au contrat en base — {details}."

        # Incoherence photos/constat detectee : prioritaire sur les autres
        # statuts (y compris CONTRAT_*), car elle remet en cause la
        # sincerite meme de la declaration.
        if coherence_photos is not None and coherence_photos.get("coherent") is False:
            status = "INVALIDE"
            note = coherence_photos.get("explication")

        if status != "A_TRAITER":
            logger.warning(f"Statut={status} — {note}")
        else:
            logger.info("Documents requis presents et OCR complet — dossier pret.")

        # ── ETAPE 5bis : Determination du taux de responsabilite ───────────
        # Uniquement quand le dossier est complet/coherent (A_TRAITER) : sur
        # les cas incomplets/incoherents, le constat n'est pas fiable a 100%
        # (champs manquants, contrat suspect) donc on ne calcule pas de taux.
        responsabilite = None
        if status == "A_TRAITER" and ocr_data and "error" not in ocr_data:
            pg.set_agent_activity("responsabilite", "Estimation du taux de responsabilite")
            responsabilite = determine_responsabilite(ocr_data, overrides=pg.get_bareme_overrides())
            logger.info(
                f"→ Responsabilite proposee : A={round(responsabilite['taux_a']*100)}% "
                f"B={round(responsabilite['taux_b']*100)}% (cas {responsabilite['cas_type']}, "
                f"statut={responsabilite['statut']})"
            )

        # ── ETAPE 6 : Generation rapport MD ───────────────────────────────
        md_slug    = slug_from_email(email_data)
        md_content = generate_sinistre_md(
            email_data, classification, analysis,
            ocr_data=ocr_data, doc_check=doc_check,
            status=status, status_note=note,
            responsabilite=responsabilite,
            coherence_photos=coherence_photos,
        )

        # ── ETAPE 7 : Stockage PostgreSQL ──────────────────────────────────
        sinistre_id = pg.insert_sinistre(
            email_data=email_data,
            classification=classification,
            analysis=analysis,
            md_content=md_content,
            md_slug=md_slug,
            mongo_ref="",
        )

        if sinistre_id <= 0:
            logger.error("Echec insertion PostgreSQL (doublon ou erreur).")
            continue

        # Applique le statut final calcule
        pg.update_sinistre_status(sinistre_id, status, note)

        # OCR → table constat_ocr (meme si incomplet, on garde la trace)
        if ocr_data and "error" not in ocr_data:
            pg.store_constat_ocr(sinistre_id, ocr_data)

        # Responsabilite → colonnes dediees de sinistres (md_content deja a
        # jour depuis l'ETAPE 6, pas besoin de le repasser ici)
        if responsabilite:
            pg.update_sinistre_responsabilite(sinistre_id, responsabilite)

        # ── ETAPE 8 : Stockage MongoDB GridFS (toujours, meme incomplet) ────
        gridfs_ids = mongo.store_attachments(
            attachments=analysis["classified_attachments"],
            sinistre_id=sinistre_id,
            email_data=email_data,
        )
        for att, gid in zip(analysis["classified_attachments"], gridfs_ids):
            att["gridfs_id"] = gid

        if gridfs_ids:
            pg.update_mongo_ref(sinistre_id, ",".join(gridfs_ids))
            pg.update_documents_gridfs_ids(sinistre_id, analysis["classified_attachments"])

        # ── ETAPE 8bis : Rapport d'analyse PDF ──────────────────────────────
        # Genere pour CHAQUE sinistre traite (dossier valide A_TRAITER comme
        # dossier invalide/incomplet) — voir agent/pdf_report_generator.py.
        # Sauvegarde locale dans mailconnector/mailconnector/rapport_analyse/.
        # N'interrompt jamais le pipeline en cas d'echec (log + continue).
        pdf_path = generate_pdf_report(
            sinistre_id=sinistre_id,
            email_data=email_data,
            ocr_data=ocr_data,
            doc_check=doc_check,
            status=status,
            status_note=note,
            responsabilite=responsabilite,
            coherence_photos=coherence_photos,
            contract_check=contract_check,
            contract_full=contract_full,
            classified_attachments=analysis["classified_attachments"],
        )
        if pdf_path:
            logger.info(f"→ Rapport d'analyse PDF disponible : {pdf_path}")

        # Persiste les resultats structures (contrat / coherence photos / lien
        # PDF) pour le dashboard "Agent" du front assurantia — voir
        # storage/postgres_storage.py::update_sinistre_agent_details.
        pg.update_sinistre_agent_details(
            sinistre_id,
            contract_check=contract_check,
            coherence_photos=coherence_photos,
            pdf_path=pdf_path,
        )

        # ── ETAPE 9 : Decision finale ────────────────────────────────────────
        # La creation du dossier dans le systeme de gestion (mock_api /
        # `dossiers_sinistres`) n'est PLUS automatique : elle n'a lieu que
        # lorsqu'un gestionnaire consulte le raisonnement de l'agent dans le
        # dashboard "Agent" du front assurantia et confirme explicitement la
        # transmission (voir assurantia-api : POST /api/agent/sinistres/{id}/confirm).
        pg.set_agent_activity("decision", f"Decision finale : {status}")
        if status == "A_TRAITER":
            logger.info(f"✅ Sinistre complet enregistre — PG id={sinistre_id}, slug={md_slug} "
                        f"— en attente de confirmation par un gestionnaire.")
        else:
            logger.info(f"⚠️ Sinistre enregistre avec statut {status} — PG id={sinistre_id}")

    pg.set_agent_idle()


if __name__ == "__main__":
    run_agent()