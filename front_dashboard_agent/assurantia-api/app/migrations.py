"""
Migrations executees au demarrage de l'API (voir main.py -> lifespan).
Toutes en `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` :
sans danger a rejouer a chaque demarrage, quel que soit l'ordre de
demarrage entre l'agent mailconnector et cette API (les deux partagent la
meme base Postgres "sinistres").
"""
from app.database import get_cursor

# Dossiers sinistres confirmes par un gestionnaire depuis le dashboard Agent
# (voir routers/agent.py::confirm_agent_sinistre). Reprend le schema
# original du mock_api (aujourd'hui supprime — cette table est desormais
# entierement geree par assurantia-api, qui est la seule a y ecrire).
CREATE_DOSSIERS_SINISTRES = """
CREATE TABLE IF NOT EXISTS dossiers_sinistres (
    id                      SERIAL PRIMARY KEY,
    numero_dossier          TEXT UNIQUE NOT NULL,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),

    sinistre_id             INTEGER,
    message_id              TEXT,
    sender                  TEXT,
    subject                 TEXT,
    email_date              TEXT,

    statut                  TEXT NOT NULL DEFAULT 'Nouveau',
    expert                  TEXT,
    commentaire             JSONB DEFAULT '[]',

    ocr_json                JSONB,

    date_accident           TEXT,
    heure_accident          TEXT,
    lieu_accident           TEXT,
    blesses                 TEXT,
    degats_materiels_autres TEXT,
    temoins                 JSONB,

    ass_a_societe           TEXT, ass_a_numero_police TEXT, ass_a_carte_verte TEXT,
    ass_a_validite          TEXT, ass_a_agence TEXT,
    cond_a_nom              TEXT, cond_a_prenom TEXT, cond_a_adresse TEXT,
    cond_a_telephone        TEXT, cond_a_permis TEXT, cond_a_date_permis TEXT,
    assure_a_nom            TEXT, assure_a_prenom TEXT, assure_a_adresse TEXT, assure_a_telephone TEXT,
    veh_a_marque            TEXT, veh_a_modele TEXT, veh_a_immatriculation TEXT, veh_a_pays TEXT,
    circ_a_sens             TEXT, circ_a_venant_de TEXT, circ_a_allant_a TEXT,
    circ_a_point_choc       TEXT, circ_a_degats_apparents TEXT, circ_a_observations TEXT,
    circ_a_en_stationnement BOOLEAN, circ_a_quittait_stationnement BOOLEAN, circ_a_prenait_stationnement BOOLEAN,
    circ_a_sortait_parking  BOOLEAN, circ_a_engageait_giratoire BOOLEAN, circ_a_circulait_giratoire BOOLEAN,
    circ_a_heurtait_arriere BOOLEAN, circ_a_meme_sens_meme_file BOOLEAN, circ_a_changeait_file BOOLEAN,
    circ_a_depassait        BOOLEAN, circ_a_virait_droite BOOLEAN, circ_a_virait_gauche BOOLEAN,
    circ_a_reculait         BOOLEAN, circ_a_empiete_sens_inverse BOOLEAN, circ_a_venait_droite BOOLEAN,
    circ_a_non_prioritaire  BOOLEAN,
    signature_a             BOOLEAN,

    ass_b_societe           TEXT, ass_b_numero_police TEXT, ass_b_carte_verte TEXT,
    ass_b_validite          TEXT, ass_b_agence TEXT,
    cond_b_nom              TEXT, cond_b_prenom TEXT, cond_b_adresse TEXT,
    cond_b_telephone        TEXT, cond_b_permis TEXT, cond_b_date_permis TEXT,
    assure_b_nom            TEXT, assure_b_prenom TEXT, assure_b_adresse TEXT, assure_b_telephone TEXT,
    veh_b_marque            TEXT, veh_b_modele TEXT, veh_b_immatriculation TEXT, veh_b_pays TEXT,
    circ_b_sens             TEXT, circ_b_venant_de TEXT, circ_b_allant_a TEXT,
    circ_b_point_choc       TEXT, circ_b_degats_apparents TEXT, circ_b_observations TEXT,
    circ_b_en_stationnement BOOLEAN, circ_b_quittait_stationnement BOOLEAN, circ_b_prenait_stationnement BOOLEAN,
    circ_b_sortait_parking  BOOLEAN, circ_b_engageait_giratoire BOOLEAN, circ_b_circulait_giratoire BOOLEAN,
    circ_b_heurtait_arriere BOOLEAN, circ_b_meme_sens_meme_file BOOLEAN, circ_b_changeait_file BOOLEAN,
    circ_b_depassait        BOOLEAN, circ_b_virait_droite BOOLEAN, circ_b_virait_gauche BOOLEAN,
    circ_b_reculait         BOOLEAN, circ_b_empiete_sens_inverse BOOLEAN, circ_b_venait_droite BOOLEAN,
    circ_b_non_prioritaire  BOOLEAN,
    signature_b             BOOLEAN,

    croquis_present         BOOLEAN,
    description_croquis     TEXT
);
"""

# Dossiers sinistres confirmes/transmis par un gestionnaire depuis le
# dashboard Agent (voir routers/agent.py::confirm_agent_sinistre) : en plus
# des champs constat deja existants, on stocke ici tout ce qui permet au
# dossier d'etre autonome (plus besoin de retourner voir la table `sinistres`
# de l'agent) + le suivi metier propre a un vrai logiciel d'assurance
# (avis d'expert, statut et montant de remboursement).
ALTER_DOSSIERS_SINISTRES = """
ALTER TABLE dossiers_sinistres ADD COLUMN IF NOT EXISTS responsabilite JSONB;
ALTER TABLE dossiers_sinistres ADD COLUMN IF NOT EXISTS contract_check JSONB;
ALTER TABLE dossiers_sinistres ADD COLUMN IF NOT EXISTS coherence_photos JSONB;
ALTER TABLE dossiers_sinistres ADD COLUMN IF NOT EXISTS pdf_path TEXT;
ALTER TABLE dossiers_sinistres ADD COLUMN IF NOT EXISTS avis_expert TEXT;
ALTER TABLE dossiers_sinistres ADD COLUMN IF NOT EXISTS statut_remboursement TEXT DEFAULT 'Non initié';
ALTER TABLE dossiers_sinistres ADD COLUMN IF NOT EXISTS montant_rembourse NUMERIC(12,2);
ALTER TABLE dossiers_sinistres ADD COLUMN IF NOT EXISTS date_remboursement DATE;
"""

# Reprend exactement la definition de mailconnector/storage/postgres_storage.py
# (meme table partagee) — voir la note d'idempotence ci-dessus.
CREATE_AGENT_ACTIVITY = """
CREATE TABLE IF NOT EXISTS agent_activity (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    is_idle         BOOLEAN DEFAULT true,
    sender          TEXT,
    subject         TEXT,
    step            TEXT,
    step_label      TEXT,
    started_at      TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT NOW(),
    CONSTRAINT agent_activity_singleton CHECK (id = 1)
);
"""
SEED_AGENT_ACTIVITY = """
INSERT INTO agent_activity (id, is_idle) VALUES (1, true)
ON CONFLICT (id) DO NOTHING;
"""

# Reprennent exactement les definitions de
# mailconnector/storage/postgres_storage.py (meme table partagee).
CREATE_AGENT_CONFIG = """
CREATE TABLE IF NOT EXISTS agent_config (
    id                          INTEGER PRIMARY KEY DEFAULT 1,
    is_running                  BOOLEAN DEFAULT true,
    polling_interval_seconds    INTEGER DEFAULT 60,
    updated_at                  TIMESTAMP DEFAULT NOW(),
    CONSTRAINT agent_config_singleton CHECK (id = 1)
);
"""
SEED_AGENT_CONFIG = """
INSERT INTO agent_config (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;
"""
CREATE_BAREME_OVERRIDES = """
CREATE TABLE IF NOT EXISTS bareme_overrides (
    cas         TEXT PRIMARY KEY,
    taux_a      NUMERIC(5,4) NOT NULL,
    taux_b      NUMERIC(5,4) NOT NULL,
    updated_at  TIMESTAMP DEFAULT NOW()
);
"""
CREATE_INSURANCE_COMPANIES = """
CREATE TABLE IF NOT EXISTS insurance_companies (
    nom         TEXT PRIMARY KEY,
    created_at  TIMESTAMP DEFAULT NOW()
);
"""


def run_migrations():
    with get_cursor(commit=True) as cur:
        cur.execute(CREATE_DOSSIERS_SINISTRES)
        cur.execute(ALTER_DOSSIERS_SINISTRES)
        cur.execute(CREATE_AGENT_ACTIVITY)
        cur.execute(SEED_AGENT_ACTIVITY)
        cur.execute(CREATE_AGENT_CONFIG)
        cur.execute(SEED_AGENT_CONFIG)
        cur.execute(CREATE_BAREME_OVERRIDES)
        cur.execute(CREATE_INSURANCE_COMPANIES)
