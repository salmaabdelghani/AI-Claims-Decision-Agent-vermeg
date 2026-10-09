"""
CRUD sur l'objet metier "Contrat".

Un contrat, cote metier, regroupe 4 tables : contrats, client, vehicules,
garanties, exclusion. Ce routeur expose donc des operations composites :
la creation d'un contrat cree (ou reutilise) le client, cree le vehicule,
les garanties et les exclusions associees, puis le contrat qui les relie.
"""
from fastapi import APIRouter, HTTPException

from app.database import get_cursor
from app.db_columns import GARANTIE_COLS, EXCLUSION_COLS, select_list, insert_clause, set_clause
from app.schemas import ContratCreate, ContratUpdate, ContratListItem, ContratDetail

router = APIRouter(prefix="/api/contrats", tags=["contrats"])

CONTRAT_FIELDS = [
    "num_police", "type_contrat", "statut", "date_souscription", "date_effet",
    "date_expiration", "bonus_malus", "prime_annuelle", "mode_paiement",
    "agence", "numero_agence",
]

VEHICULE_FIELDS = [
    "immatriculation", "vin", "marque", "modele", "annee", "energie",
    "couleur", "valeur_assuree", "usage",
]

CLIENT_FIELDS = [
    "nom", "prenom", "cin", "date_naissance", "adresse", "telephone",
    "email", "profession", "numero_permis", "date_delivrance_permis",
]

DETAIL_QUERY = """
    SELECT
        c.contrat_id, c.num_police, c.type_contrat, c.statut,
        c.date_souscription, c.date_effet, c.date_expiration,
        c.bonus_malus, c.prime_annuelle, c.mode_paiement,
        c.agence, c.numero_agence, c.client_id, c.id_vehicule,
        c.id_garanties, c.id_exclusion
    FROM contrats c
    WHERE c.contrat_id = %s
"""

LIST_QUERY = """
    SELECT
        c.contrat_id, c.num_police, c.statut, c.type_contrat,
        c.prime_annuelle, c.date_expiration,
        cl.nom AS client_nom, cl.prenom AS client_prenom,
        v.marque AS vehicule_marque, v.modele AS vehicule_modele
    FROM contrats c
    LEFT JOIN client cl ON cl.client_id = c.client_id
    LEFT JOIN vehicules v ON v.vehicule_id = c.id_vehicule
    WHERE (%(q)s::text IS NULL OR
           c.num_police ILIKE '%%' || %(q)s || '%%' OR
           cl.nom ILIKE '%%' || %(q)s || '%%' OR
           cl.prenom ILIKE '%%' || %(q)s || '%%')
      AND (%(statut)s::text IS NULL OR c.statut = %(statut)s)
      AND (%(type_contrat)s::text IS NULL OR c.type_contrat = %(type_contrat)s)
    ORDER BY c.contrat_id DESC
"""


def _fetch_detail(cur, contrat_id: int) -> ContratDetail:
    cur.execute(DETAIL_QUERY, (contrat_id,))
    contrat = cur.fetchone()
    if not contrat:
        raise HTTPException(404, "Contrat introuvable")

    client = None
    if contrat.get("client_id"):
        cur.execute("SELECT * FROM client WHERE client_id = %s", (contrat["client_id"],))
        client = cur.fetchone()

    vehicule = None
    if contrat.get("id_vehicule"):
        cur.execute("SELECT * FROM vehicules WHERE vehicule_id = %s", (contrat["id_vehicule"],))
        vehicule = cur.fetchone()

    garanties = None
    if contrat.get("id_garanties"):
        cur.execute(
            f"SELECT garantie_id, {select_list(GARANTIE_COLS)} FROM garanties WHERE garantie_id = %s",
            (contrat["id_garanties"],),
        )
        garanties = cur.fetchone()

    exclusion = None
    if contrat.get("id_exclusion"):
        cur.execute(
            f"SELECT exclusion_id, {select_list(EXCLUSION_COLS)} FROM exclusion WHERE exclusion_id = %s",
            (contrat["id_exclusion"],),
        )
        exclusion = cur.fetchone()

    return {"contrat": contrat, "client": client, "vehicule": vehicule,
            "garanties": garanties, "exclusion": exclusion}


@router.get("", response_model=list[ContratListItem])
def list_contrats(q: str | None = None, statut: str | None = None, type_contrat: str | None = None):
    with get_cursor() as cur:
        cur.execute(LIST_QUERY, {"q": q, "statut": statut, "type_contrat": type_contrat})
        return cur.fetchall()


@router.get("/{contrat_id}", response_model=ContratDetail)
def get_contrat(contrat_id: int):
    with get_cursor() as cur:
        return _fetch_detail(cur, contrat_id)


@router.post("", response_model=ContratDetail, status_code=201)
def create_contrat(payload: ContratCreate):
    with get_cursor(commit=True) as cur:
        # 1) Client : reutilise si client_id fourni, sinon cree
        if payload.client.client_id:
            client_id = payload.client.client_id
            cur.execute("SELECT 1 FROM client WHERE client_id = %s", (client_id,))
            if not cur.fetchone():
                raise HTTPException(404, "client_id fourni introuvable")
        else:
            data = payload.client.model_dump(exclude={"client_id"})
            cols = ", ".join(CLIENT_FIELDS)
            ph = ", ".join(f"%({f})s" for f in CLIENT_FIELDS)
            cur.execute(f"INSERT INTO client ({cols}) VALUES ({ph}) RETURNING client_id", data)
            client_id = cur.fetchone()["client_id"]

        # 2) Vehicule
        data = payload.vehicule.model_dump()
        cols = ", ".join(VEHICULE_FIELDS)
        ph = ", ".join(f"%({f})s" for f in VEHICULE_FIELDS)
        cur.execute(f"INSERT INTO vehicules ({cols}) VALUES ({ph}) RETURNING vehicule_id", data)
        vehicule_id = cur.fetchone()["vehicule_id"]

        # 3) Garanties
        data = payload.garanties.model_dump()
        cols, ph = insert_clause(GARANTIE_COLS)
        cur.execute(f"INSERT INTO garanties ({cols}) VALUES ({ph}) RETURNING garantie_id", data)
        garantie_id = cur.fetchone()["garantie_id"]

        # 4) Exclusion
        data = payload.exclusion.model_dump()
        cols, ph = insert_clause(EXCLUSION_COLS)
        cur.execute(f"INSERT INTO exclusion ({cols}) VALUES ({ph}) RETURNING exclusion_id", data)
        exclusion_id = cur.fetchone()["exclusion_id"]

        # 5) Contrat (relie tout)
        data = payload.contrat.model_dump()
        cur.execute("SELECT 1 FROM contrats WHERE num_police = %(num_police)s", data)
        if cur.fetchone():
            raise HTTPException(409, f"Le numero de police '{data['num_police']}' existe deja.")
        cols = ", ".join(CONTRAT_FIELDS + ["client_id", "id_vehicule", "id_garanties", "id_exclusion"])
        ph = ", ".join(f"%({f})s" for f in CONTRAT_FIELDS) + ", %(client_id)s, %(vehicule_id)s, %(garantie_id)s, %(exclusion_id)s"
        cur.execute(
            f"INSERT INTO contrats ({cols}) VALUES ({ph}) RETURNING contrat_id",
            {**data, "client_id": client_id, "vehicule_id": vehicule_id,
             "garantie_id": garantie_id, "exclusion_id": exclusion_id},
        )
        contrat_id = cur.fetchone()["contrat_id"]

        # Le vehicule reference aussi son contrat (colonne vehicules.contrat_id)
        cur.execute("UPDATE vehicules SET contrat_id = %s WHERE vehicule_id = %s", (contrat_id, vehicule_id))

        return _fetch_detail(cur, contrat_id)


@router.put("/{contrat_id}", response_model=ContratDetail)
def update_contrat(contrat_id: int, payload: ContratUpdate):
    with get_cursor(commit=True) as cur:
        cur.execute(DETAIL_QUERY, (contrat_id,))
        existing = cur.fetchone()
        if not existing:
            raise HTTPException(404, "Contrat introuvable")

        # Numero de police unique (hors ce contrat)
        cur.execute(
            "SELECT 1 FROM contrats WHERE num_police = %s AND contrat_id != %s",
            (payload.contrat.num_police, contrat_id),
        )
        if cur.fetchone():
            raise HTTPException(409, f"Le numero de police '{payload.contrat.num_police}' est deja utilise.")

        # Client
        if payload.client.client_id:
            client_id = payload.client.client_id
        else:
            client_id = existing["client_id"]
        if client_id:
            data = payload.client.model_dump(exclude={"client_id"})
            set_c = ", ".join(f"{f} = %({f})s" for f in CLIENT_FIELDS)
            cur.execute(f"UPDATE client SET {set_c} WHERE client_id = %(client_id)s",
                        {**data, "client_id": client_id})

        # Vehicule
        if existing["id_vehicule"]:
            data = payload.vehicule.model_dump()
            set_v = ", ".join(f"{f} = %({f})s" for f in VEHICULE_FIELDS)
            cur.execute(f"UPDATE vehicules SET {set_v} WHERE vehicule_id = %(vehicule_id)s",
                        {**data, "vehicule_id": existing["id_vehicule"]})

        # Garanties
        if existing["id_garanties"]:
            data = payload.garanties.model_dump()
            cur.execute(
                f"UPDATE garanties SET {set_clause(GARANTIE_COLS)} WHERE garantie_id = %(garantie_id)s",
                {**data, "garantie_id": existing["id_garanties"]},
            )

        # Exclusion
        if existing["id_exclusion"]:
            data = payload.exclusion.model_dump()
            cur.execute(
                f"UPDATE exclusion SET {set_clause(EXCLUSION_COLS)} WHERE exclusion_id = %(exclusion_id)s",
                {**data, "exclusion_id": existing["id_exclusion"]},
            )

        # Contrat
        data = payload.contrat.model_dump()
        set_ct = ", ".join(f"{f} = %({f})s" for f in CONTRAT_FIELDS)
        cur.execute(
            f"UPDATE contrats SET {set_ct}, client_id = %(client_id)s WHERE contrat_id = %(contrat_id)s",
            {**data, "client_id": client_id, "contrat_id": contrat_id},
        )

        return _fetch_detail(cur, contrat_id)


@router.delete("/{contrat_id}", status_code=204)
def delete_contrat(contrat_id: int):
    """
    Supprime le contrat ainsi que le vehicule, les garanties et l'exclusion
    qui lui sont propres (modele 1 contrat <-> 1 vehicule / 1 jeu de
    garanties / 1 jeu d'exclusions dans ce schema). Le client, lui, est
    conserve (il peut avoir d'autres contrats).
    """
    with get_cursor(commit=True) as cur:
        cur.execute(DETAIL_QUERY, (contrat_id,))
        existing = cur.fetchone()
        if not existing:
            raise HTTPException(404, "Contrat introuvable")

        cur.execute("DELETE FROM contrats WHERE contrat_id = %s", (contrat_id,))
        if existing["id_vehicule"]:
            cur.execute("DELETE FROM vehicules WHERE vehicule_id = %s", (existing["id_vehicule"],))
        if existing["id_garanties"]:
            cur.execute("DELETE FROM garanties WHERE garantie_id = %s", (existing["id_garanties"],))
        if existing["id_exclusion"]:
            cur.execute("DELETE FROM exclusion WHERE exclusion_id = %s", (existing["id_exclusion"],))
