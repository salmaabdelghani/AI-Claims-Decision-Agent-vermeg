"""
Lecture et actions de gestion sur `dossiers_sinistres` (alimentee par
l'agent de traitement des emails ; ce routeur permet au gestionnaire de
consulter les dossiers, de les filtrer, d'assigner un expert, de faire
evoluer le statut metier (En expertise / Valide / Refuse / Cloture...) et
de supprimer un dossier si necessaire).

Chaque dossier est transmis ici (voir routers/agent.py::confirm_agent_sinistre)
avec TOUTES les donnees necessaires pour etre autonome : constat complet
(ocr_json), responsabilite, contexte de verification (contract_check,
coherence_photos), et le rapport PDF — donc pas besoin de rejoindre la table
`sinistres` de l'agent pour afficher une fiche complete.
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.database import get_cursor
from app.schemas import SinistrePatch

router = APIRouter(prefix="/api/sinistres", tags=["sinistres"])

RAPPORT_ANALYSE_DIR = os.getenv(
    "RAPPORT_ANALYSE_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "mailconnector", "mailconnector", "rapport_analyse"),
)

LIST_COLS = """
    id, numero_dossier, sinistre_id, created_at, updated_at, statut, expert,
    sender, subject, email_date, date_accident, heure_accident, lieu_accident,
    blesses, ass_a_numero_police, ass_b_numero_police,
    veh_a_marque, veh_a_modele, veh_a_immatriculation,
    veh_b_marque, veh_b_modele, veh_b_immatriculation,
    responsabilite, statut_remboursement, montant_rembourse
"""


@router.get("")
def list_sinistres(q: str | None = None, statut: str | None = None):
    query = f"""
        SELECT {LIST_COLS} FROM dossiers_sinistres
        WHERE (%(q)s::text IS NULL OR
               numero_dossier ILIKE '%%' || %(q)s || '%%' OR
               sender ILIKE '%%' || %(q)s || '%%' OR
               ass_a_numero_police ILIKE '%%' || %(q)s || '%%' OR
               ass_b_numero_police ILIKE '%%' || %(q)s || '%%')
          AND (%(statut)s::text IS NULL OR statut = %(statut)s)
        ORDER BY created_at DESC NULLS LAST, id DESC
    """
    with get_cursor() as cur:
        cur.execute(query, {"q": q, "statut": statut})
        return cur.fetchall()


@router.get("/{sinistre_id}")
def get_sinistre(sinistre_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dossiers_sinistres WHERE id = %s", (sinistre_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Dossier sinistre introuvable")
        cur.execute(
            """
            SELECT id, filename, nature, gridfs_id, file_format
            FROM sinistre_documents WHERE sinistre_id = %s ORDER BY id
            """,
            (row["sinistre_id"],),
        )
        row["documents"] = cur.fetchall()
    return row


@router.get("/{sinistre_id}/rapport.pdf")
def get_sinistre_pdf(sinistre_id: int, download: bool = False):
    with get_cursor() as cur:
        cur.execute("SELECT pdf_path FROM dossiers_sinistres WHERE id = %s", (sinistre_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Dossier sinistre introuvable")

    pdf_path = row.get("pdf_path")
    candidates = []
    if pdf_path:
        candidates.append(pdf_path)
        candidates.append(os.path.join(RAPPORT_ANALYSE_DIR, os.path.basename(pdf_path)))
    found = next((c for c in candidates if c and os.path.isfile(c)), None)
    if not found:
        raise HTTPException(404, "Rapport PDF non disponible pour ce dossier")

    return FileResponse(
        found, media_type="application/pdf", filename=os.path.basename(found),
        content_disposition_type="attachment" if download else "inline",
    )


@router.patch("/{sinistre_id}")
def patch_sinistre(sinistre_id: int, payload: SinistrePatch):
    """Mise a jour partielle : statut / expert affecte / commentaires de suivi."""
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "Aucune donnee a mettre a jour")
    import json
    if "commentaire" in fields:
        fields["commentaire"] = json.dumps(fields["commentaire"])
    set_clause = ", ".join(f"{k} = %({k})s" for k in fields)
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE dossiers_sinistres SET {set_clause}, updated_at = now() "
            f"WHERE id = %(id)s RETURNING *",
            {**fields, "id": sinistre_id},
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Dossier sinistre introuvable")
    return row


@router.delete("/{sinistre_id}", status_code=204)
def delete_sinistre(sinistre_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM dossiers_sinistres WHERE id = %s", (sinistre_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Dossier sinistre introuvable")
