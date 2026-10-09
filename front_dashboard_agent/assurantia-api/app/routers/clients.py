"""
CRUD sur la table `client`.
"""
from fastapi import APIRouter, HTTPException

from app.database import get_cursor
from app.schemas import ClientPayload, ClientOut

router = APIRouter(prefix="/api/clients", tags=["clients"])

FIELDS = [
    "nom", "prenom", "cin", "date_naissance", "adresse", "telephone",
    "email", "profession", "numero_permis", "date_delivrance_permis",
]


@router.get("", response_model=list[ClientOut])
def list_clients(q: str | None = None):
    """Liste des clients, avec le nombre de contrats et de sinistres lies (vue metier)."""
    query = """
        SELECT
            c.*,
            COUNT(DISTINCT ct.contrat_id) AS nb_contrats,
            COUNT(DISTINCT ds.id) AS nb_sinistres
        FROM client c
        LEFT JOIN contrats ct ON ct.client_id = c.client_id
        LEFT JOIN dossiers_sinistres ds
            ON ds.ass_a_numero_police = ct.num_police OR ds.ass_b_numero_police = ct.num_police
        WHERE (%(q)s::text IS NULL OR
               c.nom ILIKE '%%' || %(q)s || '%%' OR
               c.prenom ILIKE '%%' || %(q)s || '%%' OR
               c.cin ILIKE '%%' || %(q)s || '%%')
        GROUP BY c.client_id
        ORDER BY c.nom NULLS LAST, c.prenom NULLS LAST
    """
    with get_cursor() as cur:
        cur.execute(query, {"q": q})
        return cur.fetchall()


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: int):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT c.*,
                   COUNT(DISTINCT ct.contrat_id) AS nb_contrats,
                   COUNT(DISTINCT ds.id) AS nb_sinistres
            FROM client c
            LEFT JOIN contrats ct ON ct.client_id = c.client_id
            LEFT JOIN dossiers_sinistres ds
                ON ds.ass_a_numero_police = ct.num_police OR ds.ass_b_numero_police = ct.num_police
            WHERE c.client_id = %s
            GROUP BY c.client_id
            """,
            (client_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Client introuvable")
    return row


@router.post("", response_model=ClientOut, status_code=201)
def create_client(payload: ClientPayload):
    data = payload.model_dump(exclude={"client_id"})
    cols = ", ".join(FIELDS)
    placeholders = ", ".join(f"%({f})s" for f in FIELDS)
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"INSERT INTO client ({cols}) VALUES ({placeholders}) RETURNING *",
            data,
        )
        row = cur.fetchone()
    return {**row, "nb_contrats": 0, "nb_sinistres": 0}


@router.put("/{client_id}", response_model=ClientOut)
def update_client(client_id: int, payload: ClientPayload):
    data = payload.model_dump(exclude={"client_id"})
    set_clause = ", ".join(f"{f} = %({f})s" for f in FIELDS)
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE client SET {set_clause} WHERE client_id = %(client_id)s RETURNING *",
            {**data, "client_id": client_id},
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Client introuvable")
    return row


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT 1 FROM contrats WHERE client_id = %s LIMIT 1", (client_id,))
        if cur.fetchone():
            raise HTTPException(
                409,
                "Impossible de supprimer ce client : il possede encore des contrats. "
                "Supprimez ou reassignez d'abord ses contrats.",
            )
        cur.execute("DELETE FROM client WHERE client_id = %s", (client_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Client introuvable")
