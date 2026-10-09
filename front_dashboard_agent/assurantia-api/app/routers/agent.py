"""
Dashboard "Agent" — expose les sinistres traites par l'agent email
(mailconnector), avec :
  - un indicateur d'activite en direct (que fait l'agent maintenant ?)
  - un chronogramme metier de chaque etape du pipeline, chaque etape donnant
    acces a l'objet complet concerne (email, constat extrait, verification
    contrat, controle photos, responsabilite)
  - le rapport PDF genere pour chaque dossier
  - l'action de confirmation : un gestionnaire qui valide le raisonnement de
    l'agent transmet alors le dossier au systeme de gestion
    (`dossiers_sinistres`, lu par le dashboard "Sinistres" principal).

Lit directement la table `sinistres` (+ `constat_ocr`, `sinistre_documents`,
et `dossiers_sinistres` en complement) — c'est la table alimentee par
mailconnector/mailconnector/main.py et agent/complement_handler.py, qui
contient TOUS les sinistres traites par l'agent (pas seulement ceux ayant
abouti a A_TRAITER, contrairement a `dossiers_sinistres`).
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import mongo
from app.bareme_reference import BAREME_REFERENCE
from app.database import get_cursor
from app.ocr_flatten import flatten_ocr_data
from app.schemas import AgentConfigPatch, AgentSinistrePatch, BaremeOverridePatch, InsuranceCompanyCreate, OcrCorrection

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Chemin vers le projet mailconnector et l'interpreteur Python a utiliser
# pour le lancer depuis le dashboard (voir POST /launch ci-dessous) — a
# adapter dans le .env si l'agent tourne dans un venv different de celui
# de cette API.
MAILCONNECTOR_DIR = os.getenv(
    "MAILCONNECTOR_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "mailconnector", "mailconnector"),
)
MAILCONNECTOR_PYTHON = os.getenv("MAILCONNECTOR_PYTHON", sys.executable)

# Duree au-dela de laquelle on considere que le processus agent n'envoie
# plus de battement de vie (voir set_agent_idle appele meme quand l'agent
# est "arrete" via le flag is_running — donc ce battement est independant
# de la file d'attente, c'est un vrai indicateur "le programme tourne-t-il").
HEARTBEAT_STALE_SECONDS = 30

RAPPORT_ANALYSE_DIR = os.getenv(
    "RAPPORT_ANALYSE_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "mailconnector", "mailconnector", "rapport_analyse"),
)

STATUTS_INCOMPLET = ("PAS_DE_CONSTAT", "PAS_DE_PHOTOS", "PAS_DE_CONSTAT_PHOTOS")

STATUT_LABELS = {
    "A_TRAITER": "Dossier complet et pret pour traitement",
    "INVALIDE": "Photos incoherentes avec le constat",
    "CONTRAT_INTROUVABLE": "Aucun contrat correspondant en base",
    "CONTRAT_INVALIDE": "Contrat trouve mais non exploitable",
    "CONTRAT_INCOHERENT": "Contrat valide mais donnees incoherentes",
    "CONSTAT_INCOMPLET": "Constat lu mais trop incomplet",
    "PAS_DE_CONSTAT": "En attente du constat amiable",
    "PAS_DE_PHOTOS": "En attente des photos de dommages",
    "PAS_DE_CONSTAT_PHOTOS": "En attente du constat et des photos",
}

STEP_LABELS = {
    "reception": "Email recu",
    "detection": "Sinistre detecte",
    "documents": "Documents recus",
    "ocr": "Lecture du constat",
    "contrat": "Verification du contrat",
    "photos": "Controle des photos",
    "responsabilite": "Estimation de responsabilite",
    "decision": "Decision finale",
}

LIST_QUERY = """
    SELECT
        s.id, s.created_at, s.updated_at, s.sender, s.subject, s.email_date,
        s.sinistre_type, s.confidence, s.reason, s.summary,
        s.status, s.dashboard_statut, s.pdf_path,
        s.responsabilite, s.responsabilite_statut, s.responsabilite_justification,
        s.contract_check, s.coherence_photos,
        oc.ocr_json,
        COALESCE(dc.has_constat, false) AS has_constat,
        COALESCE(dc.has_photos, false) AS has_photos,
        COALESCE(docs.documents, '[]'::json) AS documents,
        ds.id AS dossier_id, ds.numero_dossier, ds.expert, ds.statut AS gestion_statut,
        ds.created_at AS transmis_le
    FROM sinistres s
    LEFT JOIN LATERAL (
        SELECT ocr_json FROM constat_ocr
        WHERE sinistre_id = s.id ORDER BY created_at DESC LIMIT 1
    ) oc ON true
    LEFT JOIN LATERAL (
        SELECT
            bool_or(nature ILIKE '%%constat%%') AS has_constat,
            bool_or(nature ILIKE '%%photo%%' OR nature ILIKE '%%dommage%%') AS has_photos
        FROM sinistre_documents WHERE sinistre_id = s.id
    ) dc ON true
    LEFT JOIN LATERAL (
        SELECT json_agg(json_build_object(
            'id', d.id, 'filename', d.filename, 'nature', d.nature,
            'gridfs_id', d.gridfs_id, 'file_format', d.file_format
        ) ORDER BY d.id) AS documents
        FROM sinistre_documents d WHERE d.sinistre_id = s.id
    ) docs ON true
    LEFT JOIN dossiers_sinistres ds ON ds.sinistre_id = s.id
"""


def _extract_note(summary: str) -> str | None:
    if not summary or "⚠️" not in summary:
        return None
    return summary.rsplit("⚠️", 1)[-1].strip()


def _step(key, outcome, detail, data=None):
    return {"key": key, "label": STEP_LABELS[key], "outcome": outcome, "detail": detail, "data": data}


def _circonstances_cochees(circ: dict) -> list[str]:
    if not isinstance(circ, dict):
        return []
    return [k for k, v in circ.items() if v is True]


def _build_chronogram(row: dict) -> list[dict]:
    """
    Reconstitue, a partir des donnees stockees, un chronogramme oriente
    metier des grandes etapes du traitement par l'agent. Chaque etape porte
    aussi `data` : l'objet complet a consulter (email, constat, contrat,
    photos, responsabilite), pas seulement une phrase resumee.
    """
    steps = []
    status = row.get("status")
    ocr = row.get("ocr_json") or {}
    contract_check = row.get("contract_check")
    coherence = row.get("coherence_photos")
    responsabilite = row.get("responsabilite")

    # 1. Reception de l'email
    when = row["created_at"].strftime("%d/%m/%Y a %H:%M") if row.get("created_at") else "-"
    steps.append(_step("reception", "ok", f"Recu de {row.get('sender') or 'expediteur inconnu'} le {when}", data={
        "sender": row.get("sender"), "subject": row.get("subject"), "email_date": row.get("email_date"),
        "created_at": row.get("created_at"),
    }))

    # 2. Detection du sinistre
    conf = row.get("confidence")
    conf_txt = f" (confiance {round(conf * 100)} %)" if conf is not None else ""
    steps.append(_step("detection", "ok", f"Classe comme declaration de sinistre{conf_txt}", data={
        "sinistre_type": row.get("sinistre_type"), "confidence": conf, "reason": row.get("reason"),
    }))

    # 3. Documents recus
    has_constat, has_photos = row.get("has_constat"), row.get("has_photos")
    documents = row.get("documents") or []
    if has_constat and has_photos:
        steps.append(_step("documents", "ok", "Constat amiable et photos de dommages recus", data=documents))
    elif status in STATUTS_INCOMPLET:
        manquants = []
        if not has_constat:
            manquants.append("constat amiable")
        if not has_photos:
            manquants.append("photos de dommages")
        steps.append(_step("documents", "warning",
                            f"En attente : {', '.join(manquants)} — un email de complement est attendu du declarant",
                            data=documents))
    else:
        steps.append(_step("documents", "ok" if (has_constat or has_photos) else "ko",
                            "Constat amiable et/ou photos recus" if (has_constat or has_photos) else "Aucun document exploitable recu",
                            data=documents))

    # 4. Lecture du constat (OCR)
    if not ocr:
        outcome = "pending" if status in STATUTS_INCOMPLET else "ko"
        steps.append(_step("ocr", outcome, "Non realisee — constat non recu ou illisible"))
    elif "error" in ocr:
        steps.append(_step("ocr", "ko", "Echec de la lecture automatique du constat", data=ocr))
    else:
        acc = ocr.get("accident", {}) or {}
        date_acc = acc.get("date") or "date non lue"
        lieu_acc = acc.get("lieu") or "lieu non precise"
        outcome = "warning" if status == "CONSTAT_INCOMPLET" else "ok"
        note = "trop de champs manquants pour continuer" if status == "CONSTAT_INCOMPLET" else "lecture exploitable"
        steps.append(_step("ocr", outcome, f"Accident du {date_acc} a {lieu_acc} — {note}", data=ocr))

    # 5. Verification du contrat
    if contract_check is None:
        pending_reason = "en attente (documents incomplets)" if status in STATUTS_INCOMPLET else "non realisee (constat illisible)"
        steps.append(_step("contrat", "pending", pending_reason.capitalize()))
    elif not contract_check.get("found"):
        steps.append(_step("contrat", "ko", "Aucun contrat correspondant trouve en base assurance", data=contract_check))
    elif not contract_check.get("valid"):
        steps.append(_step("contrat", "ko", contract_check.get("invalid_reason") or "Contrat trouve mais non exploitable", data=contract_check))
    elif not contract_check.get("coherent", True):
        steps.append(_step("contrat", "warning", "Contrat valide mais donnees du constat incoherentes avec la base", data=contract_check))
    else:
        steps.append(_step("contrat", "ok",
                            f"Contrat n°{contract_check.get('num_police')} trouve et valide (vehicule {contract_check.get('party')})",
                            data=contract_check))

    # 6. Controle des photos
    if coherence is None or not coherence.get("analyzed"):
        pending_reason = "en attente (photos ou constat manquants)" if status in STATUTS_INCOMPLET else "non concluant"
        detail = (coherence or {}).get("explication") or pending_reason.capitalize()
        steps.append(_step("photos", "pending", detail, data=coherence))
    elif coherence.get("coherent") is True:
        steps.append(_step("photos", "ok", coherence.get("explication") or "Photos coherentes avec le constat", data=coherence))
    elif coherence.get("coherent") is False:
        steps.append(_step("photos", "ko", coherence.get("explication") or "Photos incoherentes avec le constat", data=coherence))
    else:
        steps.append(_step("photos", "warning", coherence.get("explication") or "Controle non concluant", data=coherence))

    # 7. Estimation de responsabilite
    if responsabilite:
        taux_a = round((responsabilite.get("taux_a") or 0) * 100)
        taux_b = round((responsabilite.get("taux_b") or 0) * 100)
        outcome = "ok" if row.get("responsabilite_statut") == "CONFIRME_BAREME" else "warning"
        steps.append(_step("responsabilite", outcome,
                            f"A = {taux_a} % / B = {taux_b} % — {row.get('responsabilite_justification') or ''}".strip(" —"),
                            data=responsabilite))
    else:
        steps.append(_step("responsabilite", "pending", "Non realisee — dossier pas encore complet et coherent"))

    # 8. Decision finale
    note = _extract_note(row.get("summary"))
    label_final = STATUT_LABELS.get(status, status or "Statut inconnu")
    outcome_final = "ok" if status == "A_TRAITER" else ("warning" if status in STATUTS_INCOMPLET else "ko")
    steps.append(_step("decision", outcome_final,
                        f"{label_final}" + (f" — {note}" if note and note != label_final else ""),
                        data={"status": status, "note": note}))

    return steps


def _serialize(row: dict, full: bool = False) -> dict:
    out = {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "sender": row["sender"],
        "subject": row["subject"],
        "status": row["status"],
        "status_label": STATUT_LABELS.get(row["status"], row["status"]),
        "dashboard_statut": row.get("dashboard_statut") or "nouveau",
        "numero_dossier": row.get("numero_dossier"),
        "transmis": bool(row.get("numero_dossier")),
        "transmis_le": row.get("transmis_le"),
        "expert": row.get("expert"),
        "num_police": (row.get("contract_check") or {}).get("num_police"),
        "responsabilite_resume": (
            f"A {round((row['responsabilite'].get('taux_a') or 0) * 100)}% / "
            f"B {round((row['responsabilite'].get('taux_b') or 0) * 100)}%"
            if row.get("responsabilite") else None
        ),
        "pdf_available": bool(row.get("pdf_path")),
        "chronogram": _build_chronogram(row),
    }
    if full:
        out["ocr_json"] = row.get("ocr_json")
        out["responsabilite"] = row.get("responsabilite")
        out["contract_check"] = row.get("contract_check")
        out["coherence_photos"] = row.get("coherence_photos")
        out["documents"] = row.get("documents") or []
        out["reason"] = row.get("reason")
        out["confidence"] = row.get("confidence")
        out["email_date"] = row.get("email_date")
    return out


@router.get("/activity")
def get_agent_activity():
    """
    Que fait l'agent en ce moment ? Interroge par le front toutes les
    quelques secondes. Inclut aussi `process_alive` : independant du flag
    is_running (qui peut etre a false), ce champ indique si le PROGRAMME
    lui-meme tourne encore quelque part (battement de vie mis a jour par
    main.py a chaque cycle, meme quand l'agent est en pause).
    """
    with get_cursor() as cur:
        cur.execute("SELECT is_idle, sender, subject, step, step_label, started_at, updated_at FROM agent_activity WHERE id = 1")
        row = cur.fetchone()
    if not row:
        return {"is_idle": True, "sender": None, "subject": None, "step": None, "step_label": None, "process_alive": False}
    row["step_display_label"] = STEP_LABELS.get(row.get("step"))
    if row.get("updated_at"):
        age = (datetime.now() - row["updated_at"]).total_seconds()
        row["seconds_since_heartbeat"] = round(age)
        row["process_alive"] = age < HEARTBEAT_STALE_SECONDS
    else:
        row["seconds_since_heartbeat"] = None
        row["process_alive"] = False
    return row


@router.post("/launch")
def launch_agent_process():
    """
    Lance reellement le programme mailconnector (processus Python autonome,
    detache) — pour ne plus jamais avoir a l'ouvrir manuellement via VSCode.
    A utiliser quand `process_alive` est faux (voir /activity). Active aussi
    is_running pour qu'il se mette au travail des le demarrage.

    Alternative plus robuste pour un usage durable : configurer un
    demarrage automatique du processus a l'ouverture de session Windows
    (Planificateur de taches) — ce bouton reste utile en secours, ou pour
    un premier lancement, sans jamais ouvrir de terminal.
    """
    main_py = os.path.abspath(os.path.join(MAILCONNECTOR_DIR, "main.py"))
    if not os.path.isfile(main_py):
        raise HTTPException(
            500,
            f"main.py introuvable a l'emplacement configure ({main_py}). "
            f"Verifiez la variable MAILCONNECTOR_DIR dans le .env de l'API.",
        )
    try:
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            [MAILCONNECTOR_PYTHON, main_py],
            cwd=os.path.abspath(MAILCONNECTOR_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            **kwargs,
        )
    except Exception as e:
        raise HTTPException(500, f"Echec du lancement du processus agent : {e}")

    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE agent_config SET is_running = true, updated_at = now() WHERE id = 1")

    return {"launched": True, "python": MAILCONNECTOR_PYTHON, "script": main_py}


@router.get("")
def list_agent_sinistres(tab: str = "a_traiter", q: str | None = None):
    """
    tab = 'a_traiter' (dashboard_statut='nouveau') ou 'traites'
    (dashboard_statut='traite'). q filtre sur expediteur/objet/police.
    """
    dashboard_statut = "traite" if tab == "traites" else "nouveau"
    query = LIST_QUERY + """
        WHERE s.dashboard_statut = %(dashboard_statut)s
          AND (%(q)s::text IS NULL OR
               s.sender ILIKE '%%' || %(q)s || '%%' OR
               s.subject ILIKE '%%' || %(q)s || '%%' OR
               (s.contract_check->>'num_police') ILIKE '%%' || %(q)s || '%%')
        ORDER BY s.updated_at DESC NULLS LAST, s.created_at DESC
    """
    with get_cursor() as cur:
        cur.execute(query, {"dashboard_statut": dashboard_statut, "q": q})
        rows = cur.fetchall()
    return [_serialize(r) for r in rows]


@router.get("/stats")
def agent_stats():
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM sinistres WHERE coalesce(dashboard_statut,'nouveau') = 'nouveau'")
        a_traiter = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM sinistres WHERE dashboard_statut = 'traite'")
        traites = cur.fetchone()["n"]
        cur.execute(
            "SELECT COUNT(*) AS n FROM sinistres "
            "WHERE coalesce(dashboard_statut,'nouveau') = 'nouveau' AND updated_at > %s",
            (datetime.now() - timedelta(hours=24),),
        )
        actifs_24h = cur.fetchone()["n"]
    return {"a_traiter": a_traiter, "traites": traites, "actifs_24h": actifs_24h}


@router.get("/sinistres/{sinistre_id}")
def get_agent_sinistre(sinistre_id: int):
    query = LIST_QUERY + " WHERE s.id = %(id)s"
    with get_cursor() as cur:
        cur.execute(query, {"id": sinistre_id})
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Sinistre introuvable")
    return _serialize(row, full=True)


@router.patch("/sinistres/{sinistre_id}")
def patch_agent_sinistre(sinistre_id: int, payload: AgentSinistrePatch):
    """
    Marque un dossier comme traite/rouvert SANS le transmettre au systeme de
    gestion — reserve aux dossiers qui ne sont pas au statut A_TRAITER (rien
    de fiable a transmettre : contrat introuvable, documents manquants...).
    Pour un dossier A_TRAITER, utiliser /confirm, qui transmet ET marque
    traite en une seule action coherente.
    """
    if payload.dashboard_statut not in ("nouveau", "traite"):
        raise HTTPException(400, "dashboard_statut doit etre 'nouveau' ou 'traite'")

    with get_cursor() as cur:
        cur.execute("SELECT status FROM sinistres WHERE id = %s", (sinistre_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Sinistre introuvable")
        cur.execute("SELECT numero_dossier FROM dossiers_sinistres WHERE sinistre_id = %s", (sinistre_id,))
        transmis = cur.fetchone()

    if transmis:
        raise HTTPException(
            400,
            f"Ce dossier a deja ete transmis (n°{transmis['numero_dossier']}) — "
            f"sa gestion se poursuit desormais depuis le dashboard Sinistres.",
        )
    if row["status"] == "A_TRAITER" and payload.dashboard_statut == "traite":
        raise HTTPException(400, "Ce dossier est pret (A_TRAITER) : utilisez 'Confirmer et transmettre'.")

    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE sinistres SET dashboard_statut = %s, updated_at = now() WHERE id = %s RETURNING id",
            (payload.dashboard_statut, sinistre_id),
        )
    return {"id": sinistre_id, "dashboard_statut": payload.dashboard_statut}


def _generate_numero_dossier(cur) -> str:
    import random
    import string
    year = datetime.now().year
    for _ in range(10):
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        numero = f"DOS-{year}-{suffix}"
        cur.execute("SELECT 1 FROM dossiers_sinistres WHERE numero_dossier = %s", (numero,))
        if not cur.fetchone():
            return numero
    raise RuntimeError("Impossible de generer un numero de dossier unique")


@router.post("/sinistres/{sinistre_id}/confirm")
def confirm_agent_sinistre(sinistre_id: int):
    """
    Le gestionnaire a consulte le raisonnement complet de l'agent (chaque
    etape du chronogramme + le dossier final) et confirme : le dossier est
    ALORS, et seulement alors, cree dans `dossiers_sinistres` — l'agent
    mailconnector ne le fait jamais automatiquement. Le dossier n'apparait
    dans le dashboard "Sinistres" principal qu'a partir de cet instant.

    La creation (numero de dossier, validation des champs) est entierement
    geree ici par assurantia-api — il n'y a plus de service intermediaire.
    """
    query = LIST_QUERY + " WHERE s.id = %(id)s"
    with get_cursor() as cur:
        cur.execute(query, {"id": sinistre_id})
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Sinistre introuvable")
    if row["status"] != "A_TRAITER":
        raise HTTPException(
            400,
            f"Seul un dossier au statut A_TRAITER peut etre confirme et transmis "
            f"(statut actuel : {STATUT_LABELS.get(row['status'], row['status'])}).",
        )
    if row.get("numero_dossier"):
        raise HTTPException(409, f"Ce dossier a deja ete transmis (n°{row['numero_dossier']}).")
    if not row.get("ocr_json"):
        raise HTTPException(400, "Constat illisible : rien a transmettre.")

    payload = {
        "sinistre_id": sinistre_id,
        "message_id": None,
        "sender": row.get("sender"),
        "subject": row.get("subject"),
        "email_date": row.get("email_date"),
        "statut": "Nouveau",
        "responsabilite": row.get("responsabilite"),
        "contract_check": row.get("contract_check"),
        "coherence_photos": row.get("coherence_photos"),
        "pdf_path": row.get("pdf_path"),
    }
    payload.update(flatten_ocr_data(row["ocr_json"]))

    jsonb_cols = {"ocr_json", "responsabilite", "contract_check", "coherence_photos", "temoins"}
    cols = list(payload.keys())
    values = {
        c: (json.dumps(payload[c], ensure_ascii=False, default=str) if c in jsonb_cols and payload[c] is not None else payload[c])
        for c in cols
    }

    with get_cursor(commit=True) as cur:
        numero_dossier = _generate_numero_dossier(cur)
        placeholders = ", ".join(f"%({c})s" for c in cols)
        col_list = ", ".join(cols)
        cur.execute(
            f"INSERT INTO dossiers_sinistres (numero_dossier, {col_list}) "
            f"VALUES (%(numero_dossier)s, {placeholders}) RETURNING id, numero_dossier",
            {"numero_dossier": numero_dossier, **values},
        )
        created = cur.fetchone()
        cur.execute("UPDATE sinistres SET dashboard_statut = 'traite', updated_at = now() WHERE id = %s", (sinistre_id,))

    return {"id": sinistre_id, "numero_dossier": created["numero_dossier"], "dossier_id": created["id"]}


@router.get("/sinistres/{sinistre_id}/rapport.pdf")
def get_agent_sinistre_pdf(sinistre_id: int, download: bool = False):
    with get_cursor() as cur:
        cur.execute("SELECT pdf_path FROM sinistres WHERE id = %s", (sinistre_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Sinistre introuvable")

    pdf_path = row.get("pdf_path")
    candidates = []
    if pdf_path:
        candidates.append(pdf_path)
        candidates.append(os.path.join(RAPPORT_ANALYSE_DIR, os.path.basename(pdf_path)))

    found = next((c for c in candidates if c and os.path.isfile(c)), None)
    if not found:
        raise HTTPException(404, "Rapport PDF non disponible pour ce sinistre")

    filename = os.path.basename(found)
    return FileResponse(
        found, media_type="application/pdf",
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
    )


# ─── Pilotage de l'agent (demarrer/arreter, intervalle de polling) ─────────

@router.get("/config")
def get_agent_config():
    with get_cursor() as cur:
        cur.execute("SELECT is_running, polling_interval_seconds, updated_at FROM agent_config WHERE id = 1")
        row = cur.fetchone()
    return row or {"is_running": False, "polling_interval_seconds": 60, "updated_at": None}


@router.patch("/config")
def patch_agent_config(payload: AgentConfigPatch):
    fields, values = [], []
    if payload.is_running is not None:
        fields.append("is_running = %s")
        values.append(payload.is_running)
    if payload.polling_interval_seconds is not None:
        if payload.polling_interval_seconds < 10:
            raise HTTPException(400, "L'intervalle de polling doit etre d'au moins 10 secondes.")
        fields.append("polling_interval_seconds = %s")
        values.append(payload.polling_interval_seconds)
    if not fields:
        raise HTTPException(400, "Aucun champ a mettre a jour.")
    fields.append("updated_at = now()")
    with get_cursor(commit=True) as cur:
        cur.execute(f"UPDATE agent_config SET {', '.join(fields)} WHERE id = 1", values)
        cur.execute("SELECT is_running, polling_interval_seconds, updated_at FROM agent_config WHERE id = 1")
        return cur.fetchone()


# ─── Bareme de responsabilite (affichage + surcharge des taux) ─────────────

@router.get("/bareme")
def get_bareme():
    with get_cursor() as cur:
        cur.execute("SELECT cas, taux_a, taux_b, updated_at FROM bareme_overrides")
        overrides = {r["cas"]: r for r in cur.fetchall()}
    result = []
    for regle in BAREME_REFERENCE:
        ov = overrides.get(regle["cas"])
        result.append({
            **regle,
            "taux_a_actuel": float(ov["taux_a"]) if ov else regle["taux_a_defaut"],
            "taux_b_actuel": float(ov["taux_b"]) if ov else regle["taux_b_defaut"],
            "personnalise": ov is not None,
            "modifie_le": ov["updated_at"] if ov else None,
        })
    return result


@router.patch("/bareme/{cas}")
def patch_bareme(cas: str, payload: BaremeOverridePatch):
    if not any(r["cas"] == cas for r in BAREME_REFERENCE):
        raise HTTPException(404, f"Cas de barème '{cas}' inconnu.")
    total = payload.taux_a + payload.taux_b
    if abs(total - 1.0) > 0.01:
        raise HTTPException(400, f"La somme des taux doit être égale à 1 (actuellement {total}).")
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO bareme_overrides (cas, taux_a, taux_b, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (cas) DO UPDATE SET taux_a = EXCLUDED.taux_a, taux_b = EXCLUDED.taux_b, updated_at = now()
            """,
            (cas, payload.taux_a, payload.taux_b),
        )
    return {"cas": cas, "taux_a": payload.taux_a, "taux_b": payload.taux_b}


@router.delete("/bareme/{cas}")
def reset_bareme(cas: str):
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM bareme_overrides WHERE cas = %s", (cas,))
    return {"cas": cas, "reinitialise": True}


# ─── Compagnies d'assurance reconnues par l'OCR ────────────────────────────

@router.get("/insurance-companies")
def list_insurance_companies():
    with get_cursor() as cur:
        cur.execute("SELECT nom FROM insurance_companies ORDER BY nom")
        return [r["nom"] for r in cur.fetchall()]


@router.post("/insurance-companies")
def add_insurance_company(payload: InsuranceCompanyCreate):
    nom = payload.nom.strip()
    if not nom:
        raise HTTPException(400, "Le nom de la compagnie ne peut pas être vide.")
    with get_cursor(commit=True) as cur:
        cur.execute("INSERT INTO insurance_companies (nom) VALUES (%s) ON CONFLICT DO NOTHING", (nom,))
    return {"nom": nom}


@router.delete("/insurance-companies/{nom}")
def remove_insurance_company(nom: str):
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM insurance_companies WHERE nom = %s", (nom,))
    return {"nom": nom, "supprime": True}


# ─── Correction du constat / ajout de photos AVANT confirmation ────────────
# Permet a un gestionnaire de corriger une donnee mal lue par l'OCR (ex:
# plaque d'immatriculation, nom de compagnie) ou d'ajouter des photos de
# dommages complementaires, depuis la section "Dossier final" du dashboard
# Agent — uniquement tant que le dossier n'a pas encore ete confirme/transmis.

def _assert_not_transmitted(sinistre_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM dossiers_sinistres WHERE sinistre_id = %s", (sinistre_id,))
        if cur.fetchone():
            raise HTTPException(400, "Ce dossier a déjà été transmis — il ne peut plus être modifié ici.")


@router.patch("/sinistres/{sinistre_id}/ocr")
def correct_agent_sinistre_ocr(sinistre_id: int, payload: OcrCorrection):
    _assert_not_transmitted(sinistre_id)
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE constat_ocr SET ocr_json = %s
            WHERE sinistre_id = %s AND id = (
                SELECT id FROM constat_ocr WHERE sinistre_id = %s ORDER BY created_at DESC LIMIT 1
            )
            RETURNING id
            """,
            (json.dumps(payload.ocr_json, ensure_ascii=False), sinistre_id, sinistre_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Aucun constat OCR existant pour ce sinistre.")
    return {"sinistre_id": sinistre_id, "ocr_corrige": True}


@router.post("/sinistres/{sinistre_id}/photos")
async def add_agent_sinistre_photo(sinistre_id: int, file: UploadFile = File(...)):
    _assert_not_transmitted(sinistre_id)
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM sinistres WHERE id = %s", (sinistre_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Sinistre introuvable")

    data = await file.read()
    gridfs_id = mongo.put_attachment(file.filename, file.content_type or "image/jpeg", data)
    if not gridfs_id:
        raise HTTPException(503, "MongoDB indisponible — impossible d'enregistrer la photo.")

    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO sinistre_documents (sinistre_id, filename, nature, gridfs_id, size_bytes)
            VALUES (%s, %s, 'Photos de dommages', %s, %s)
            RETURNING id, filename, nature, gridfs_id
            """,
            (sinistre_id, file.filename, gridfs_id, len(data)),
        )
        return cur.fetchone()
