import json
"""
Stockage PostgreSQL — utilise psycopg (v3) qui gère correctement
l'encodage Windows sans crash sur les chemins avec accents.
"""
import psycopg
import logging

logger = logging.getLogger(__name__)

CREATE_SINISTRES = """
CREATE TABLE IF NOT EXISTS sinistres (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMP DEFAULT NOW(),
    message_id      TEXT UNIQUE,
    sender          TEXT NOT NULL,
    cc              TEXT,
    bcc             TEXT,
    subject         TEXT,
    email_date      TEXT,
    sinistre_type   TEXT,
    confidence      FLOAT,
    reason          TEXT,
    summary         TEXT,
    md_content      TEXT,
    md_slug         TEXT,
    status          TEXT DEFAULT 'A_TRAITER',
    mongo_ref       TEXT
);
"""

# Migration pour les bases deja existantes (creees avant l'ajout de `reason`).
ALTER_SINISTRES_ADD_REASON = """
ALTER TABLE sinistres ADD COLUMN IF NOT EXISTS reason TEXT;
"""

# Migration pour les bases deja existantes (creees avant l'ajout du module de
# determination de responsabilite). `responsabilite` stocke le resultat
# complet en JSON (taux, cas_type, methode, elements_pris_en_compte...),
# `responsabilite_statut` et `responsabilite_justification` sont dupliques
# en colonnes dediees pour faciliter le filtrage/l'affichage sans parser le JSON.
ALTER_SINISTRES_ADD_RESPONSABILITE = """
ALTER TABLE sinistres ADD COLUMN IF NOT EXISTS responsabilite JSONB;
ALTER TABLE sinistres ADD COLUMN IF NOT EXISTS responsabilite_statut TEXT;
ALTER TABLE sinistres ADD COLUMN IF NOT EXISTS responsabilite_justification TEXT;
"""

# Migration pour le dashboard "Agent" (front assurantia) : trace, pour
# chaque sinistre, le resultat structure des etapes du pipeline qui
# n'etaient jusqu'ici visibles que dans les logs / le rapport PDF :
#   - contract_check     : resultat de la verification contrat (trouve /
#     valide / coherent / police / contrat_id / raison d'echec eventuelle)
#   - coherence_photos   : resultat du controle photos <-> constat
#   - pdf_path            : chemin du rapport PDF le plus recent genere
#     pour ce sinistre (evite d'avoir a chercher le fichier par pattern)
#   - dashboard_statut    : suivi de gestion cote dashboard agent
#     ('nouveau' = a traiter, 'traite' = revu/cloture par un gestionnaire) —
#     independant du statut pipeline `status` et du statut metier de
#     `dossiers_sinistres.statut` (qui ne couvre que les dossiers A_TRAITER)
#   - updated_at          : derniere modification, pour un suivi "temps reel"
ALTER_SINISTRES_ADD_AGENT_DASHBOARD = """
ALTER TABLE sinistres ADD COLUMN IF NOT EXISTS contract_check JSONB;
ALTER TABLE sinistres ADD COLUMN IF NOT EXISTS coherence_photos JSONB;
ALTER TABLE sinistres ADD COLUMN IF NOT EXISTS pdf_path TEXT;
ALTER TABLE sinistres ADD COLUMN IF NOT EXISTS dashboard_statut TEXT DEFAULT 'nouveau';
ALTER TABLE sinistres ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();
"""

# Ligne unique (id=1) tracant en direct ce que l'agent est en train de faire
# (ou son inactivite), pour l'indicateur "en direct" du dashboard Agent du
# front assurantia. `step` reprend les memes cles que le chronogramme
# reconstruit cote API (reception, detection, documents, ocr, contrat,
# photos, responsabilite, decision) afin que le front puisse surligner la
# meme etape dans le dossier en cours de traitement.
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

# Pilotage de l'agent depuis le dashboard (demarrer/arreter, intervalle de
# polling IMAP) — ligne unique relue a chaque cycle de la boucle principale
# (voir main.py::run_agent), donc un changement depuis le dashboard prend
# effet au cycle suivant sans redemarrer le processus.
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

# Surcharges du bareme de responsabilite (ressources/bareme_responsabilite.py
# reste la source de verite structurelle — cases cochees, etc.) : seuls les
# taux peuvent etre ajustes depuis le dashboard, pour rester sans danger
# pour le moteur de correspondance (agent/responsabilite.py les applique
# APRES avoir trouve la regle correspondante).
CREATE_BAREME_OVERRIDES = """
CREATE TABLE IF NOT EXISTS bareme_overrides (
    cas         TEXT PRIMARY KEY,
    taux_a      NUMERIC(5,4) NOT NULL,
    taux_b      NUMERIC(5,4) NOT NULL,
    updated_at  TIMESTAMP DEFAULT NOW()
);
"""

# Liste des compagnies d'assurance reconnues par l'OCR (contrainte le LLM a
# un vocabulaire ferme). Remplace ressources/insurance_companies.py comme
# source vivante ; ce fichier reste le contenu de depart (seed).
CREATE_INSURANCE_COMPANIES = """
CREATE TABLE IF NOT EXISTS insurance_companies (
    nom         TEXT PRIMARY KEY,
    created_at  TIMESTAMP DEFAULT NOW()
);
"""

CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS sinistre_documents (
    id              SERIAL PRIMARY KEY,
    sinistre_id     INTEGER REFERENCES sinistres(id) ON DELETE CASCADE,
    filename        TEXT,
    file_format     TEXT,
    nature          TEXT,
    size_bytes      INTEGER,
    gridfs_id       TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);
"""

CREATE_FTS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_sinistres_fts
    ON sinistres USING gin(to_tsvector('french', coalesce(summary,'') || ' ' || coalesce(subject,'')));
"""


class PostgresStorage:

    def __init__(self, host: str, port: int, dbname: str, user: str, password: str):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.conn = None

    def connect(self):
        self.conn = psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            options="-c client_encoding=UTF8",
        )
        self.conn.autocommit = False
        logger.info("PostgreSQL connecté (psycopg3, client_encoding=UTF8).")

    def initialize_schema(self):
        with self.conn.cursor() as cur:
            cur.execute(CREATE_SINISTRES)
            cur.execute(ALTER_SINISTRES_ADD_REASON)
            cur.execute(ALTER_SINISTRES_ADD_RESPONSABILITE)
            cur.execute(ALTER_SINISTRES_ADD_AGENT_DASHBOARD)
            cur.execute(CREATE_AGENT_ACTIVITY)
            cur.execute(SEED_AGENT_ACTIVITY)
            cur.execute(CREATE_AGENT_CONFIG)
            cur.execute(SEED_AGENT_CONFIG)
            cur.execute(CREATE_BAREME_OVERRIDES)
            cur.execute(CREATE_INSURANCE_COMPANIES)
            cur.execute(CREATE_DOCUMENTS)
            cur.execute(CREATE_FTS_INDEX)
        self.conn.commit()

        # Amorce la table insurance_companies avec la liste statique de
        # depart, uniquement si elle est encore vide (ne jamais ecraser des
        # modifications faites depuis le dashboard).
        try:
            from ressources.insurance_companies import INSURANCE_COMPANIES
            with self.conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM insurance_companies")
                if cur.fetchone()[0] == 0:
                    for nom in INSURANCE_COMPANIES:
                        cur.execute(
                            "INSERT INTO insurance_companies (nom) VALUES (%s) ON CONFLICT DO NOTHING",
                            (nom,),
                        )
            self.conn.commit()
        except Exception as e:
            logger.warning(f"Amorçage insurance_companies ignoré: {e}")

        logger.info("Schéma PostgreSQL initialisé.")

    def insert_sinistre(self, email_data, classification, analysis, md_content, md_slug, mongo_ref="") -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sinistres
                    (message_id, sender, cc, bcc, subject, email_date,
                     sinistre_type, confidence, reason, summary, md_content, md_slug, mongo_ref)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (message_id) DO NOTHING
                RETURNING id
                """,
                (
                    email_data.get("message_id"),
                    email_data.get("sender"),
                    email_data.get("cc"),
                    email_data.get("bcc"),
                    email_data.get("subject"),
                    email_data.get("date"),
                    classification.get("sinistre_type"),
                    classification.get("confidence"),
                    classification.get("reason"),
                    analysis.get("summary"),
                    md_content,
                    md_slug,
                    mongo_ref,
                ),
            )
            row = cur.fetchone()
            if row is None:
                logger.warning("Email déjà traité (message_id dupliqué), ignoré.")
                self.conn.rollback()
                return -1
            sinistre_id = row[0]

            for att in analysis.get("classified_attachments", []):
                cur.execute(
                    """
                    INSERT INTO sinistre_documents
                        (sinistre_id, filename, file_format, nature, size_bytes, gridfs_id)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (sinistre_id, att.get("filename"), att.get("classified_type"),
                     att.get("nature"), att.get("size_bytes", 0), att.get("gridfs_id", "")),
                )

        self.conn.commit()
        logger.info(f"Sinistre inséré PostgreSQL id={sinistre_id}")
        return sinistre_id

    def search_sinistres(self, query: str, limit: int = 20) -> list[dict]:
        with self.conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                SELECT id, created_at, sender, subject, sinistre_type, status
                FROM sinistres
                WHERE to_tsvector('french', coalesce(summary,'') || ' ' || coalesce(subject,''))
                      @@ plainto_tsquery('french', %s)
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (query, limit),
            )
            return cur.fetchall()

    def close(self):
        if self.conn:
            self.conn.close()


    def store_constat_ocr(self, sinistre_id: int, ocr_data: dict):
        """Stocke les donnees OCR du constat dans une table dediee.

        La table couvre TOUS les champs du constat amiable :
          - Informations generales (accident)
          - Vehicule A & B : assurance, conducteur, assure, vehicule, circulation, dommages
          - Circonstances A & B (16 cases a cocher)
          - Croquis + signatures
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS constat_ocr (
                    id              SERIAL PRIMARY KEY,
                    sinistre_id     INTEGER REFERENCES sinistres(id) ON DELETE CASCADE,
                    created_at      TIMESTAMP DEFAULT NOW(),
                    ocr_json        JSONB,

                    -- ── Informations generales ──────────────────────────────
                    date_accident               TEXT,
                    heure_accident              TEXT,
                    lieu_accident               TEXT,
                    blesses                     TEXT,
                    degats_materiels_autres      TEXT,
                    temoins                     JSONB,

                    -- ── Vehicule A — Assurance ──────────────────────────────
                    ass_a_societe               TEXT,
                    ass_a_numero_police         TEXT,
                    ass_a_carte_verte           TEXT,
                    ass_a_validite              TEXT,
                    ass_a_agence                TEXT,

                    -- ── Vehicule A — Conducteur ─────────────────────────────
                    cond_a_nom                  TEXT,
                    cond_a_prenom               TEXT,
                    cond_a_adresse              TEXT,
                    cond_a_telephone            TEXT,
                    cond_a_permis               TEXT,
                    cond_a_date_permis          TEXT,

                    -- ── Vehicule A — Assure ─────────────────────────────────
                    assure_a_nom                TEXT,
                    assure_a_prenom             TEXT,
                    assure_a_adresse            TEXT,
                    assure_a_telephone          TEXT,

                    -- ── Vehicule A — Vehicule ───────────────────────────────
                    veh_a_marque                TEXT,
                    veh_a_modele                TEXT,
                    veh_a_immatriculation       TEXT,
                    veh_a_pays                  TEXT,

                    -- ── Vehicule A — Circulation & Dommages ─────────────────
                    circ_a_sens                 TEXT,
                    circ_a_venant_de            TEXT,
                    circ_a_allant_a             TEXT,
                    circ_a_point_choc           TEXT,
                    circ_a_degats_apparents     TEXT,
                    circ_a_observations         TEXT,

                    -- ── Vehicule A — Circonstances (cases 1-16) ─────────────
                    circ_a_en_stationnement         BOOLEAN,
                    circ_a_quittait_stationnement   BOOLEAN,
                    circ_a_prenait_stationnement    BOOLEAN,
                    circ_a_sortait_parking          BOOLEAN,
                    circ_a_engageait_giratoire      BOOLEAN,
                    circ_a_circulait_giratoire      BOOLEAN,
                    circ_a_heurtait_arriere         BOOLEAN,
                    circ_a_meme_sens_meme_file      BOOLEAN,
                    circ_a_changeait_file           BOOLEAN,
                    circ_a_depassait                BOOLEAN,
                    circ_a_virait_droite            BOOLEAN,
                    circ_a_virait_gauche            BOOLEAN,
                    circ_a_reculait                 BOOLEAN,
                    circ_a_empiete_sens_inverse     BOOLEAN,
                    circ_a_venait_droite            BOOLEAN,
                    circ_a_non_prioritaire          BOOLEAN,

                    -- ── Vehicule A — Signature ───────────────────────────────
                    signature_a                     BOOLEAN,

                    -- ── Vehicule B — Assurance ──────────────────────────────
                    ass_b_societe               TEXT,
                    ass_b_numero_police         TEXT,
                    ass_b_carte_verte           TEXT,
                    ass_b_validite              TEXT,
                    ass_b_agence                TEXT,

                    -- ── Vehicule B — Conducteur ─────────────────────────────
                    cond_b_nom                  TEXT,
                    cond_b_prenom               TEXT,
                    cond_b_adresse              TEXT,
                    cond_b_telephone            TEXT,
                    cond_b_permis               TEXT,
                    cond_b_date_permis          TEXT,

                    -- ── Vehicule B — Assure ─────────────────────────────────
                    assure_b_nom                TEXT,
                    assure_b_prenom             TEXT,
                    assure_b_adresse            TEXT,
                    assure_b_telephone          TEXT,

                    -- ── Vehicule B — Vehicule ───────────────────────────────
                    veh_b_marque                TEXT,
                    veh_b_modele                TEXT,
                    veh_b_immatriculation       TEXT,
                    veh_b_pays                  TEXT,

                    -- ── Vehicule B — Circulation & Dommages ─────────────────
                    circ_b_sens                 TEXT,
                    circ_b_venant_de            TEXT,
                    circ_b_allant_a             TEXT,
                    circ_b_point_choc           TEXT,
                    circ_b_degats_apparents     TEXT,
                    circ_b_observations         TEXT,

                    -- ── Vehicule B — Circonstances (cases 1-16) ─────────────
                    circ_b_en_stationnement         BOOLEAN,
                    circ_b_quittait_stationnement   BOOLEAN,
                    circ_b_prenait_stationnement    BOOLEAN,
                    circ_b_sortait_parking          BOOLEAN,
                    circ_b_engageait_giratoire      BOOLEAN,
                    circ_b_circulait_giratoire      BOOLEAN,
                    circ_b_heurtait_arriere         BOOLEAN,
                    circ_b_meme_sens_meme_file      BOOLEAN,
                    circ_b_changeait_file           BOOLEAN,
                    circ_b_depassait                BOOLEAN,
                    circ_b_virait_droite            BOOLEAN,
                    circ_b_virait_gauche            BOOLEAN,
                    circ_b_reculait                 BOOLEAN,
                    circ_b_empiete_sens_inverse     BOOLEAN,
                    circ_b_venait_droite            BOOLEAN,
                    circ_b_non_prioritaire          BOOLEAN,

                    -- ── Vehicule B — Signature ───────────────────────────────
                    signature_b                     BOOLEAN,

                    -- ── Partie commune — Croquis ─────────────────────────────
                    croquis_present             BOOLEAN,
                    description_croquis         TEXT
                );
            """)

            # ── Extraction des sous-objets ──────────────────────────────────
            acc      = ocr_data.get("accident", {})
            veh_a    = ocr_data.get("vehicule_a", {})
            veh_b    = ocr_data.get("vehicule_b", {})
            ass_a    = veh_a.get("assurance", {})
            ass_b    = veh_b.get("assurance", {})
            cond_a   = veh_a.get("conducteur", {})
            cond_b   = veh_b.get("conducteur", {})
            assure_a = veh_a.get("assure", {})
            assure_b = veh_b.get("assure", {})
            auto_a   = veh_a.get("vehicule", {})
            auto_b   = veh_b.get("vehicule", {})
            mvt_a    = veh_a.get("circulation", {})
            mvt_b    = veh_b.get("circulation", {})
            cases_a  = ocr_data.get("circonstances_a", {})
            cases_b  = ocr_data.get("circonstances_b", {})

            def _nullify(val):
                """Convertit 'manquant' en None pour les champs TEXT."""
                if val == "manquant" or val == "":
                    return None
                return val

            def _bool(val):
                """Convertit en bool nullable (None si manquant)."""
                if val == "manquant" or val is None:
                    return None
                return bool(val)

            temoins = acc.get("temoins")
            if isinstance(temoins, list) and len(temoins) == 0:
                temoins = None

            cur.execute("""
                INSERT INTO constat_ocr (
                    sinistre_id, ocr_json,

                    date_accident, heure_accident, lieu_accident,
                    blesses, degats_materiels_autres, temoins,

                    ass_a_societe, ass_a_numero_police, ass_a_carte_verte,
                    ass_a_validite, ass_a_agence,

                    cond_a_nom, cond_a_prenom, cond_a_adresse, cond_a_telephone,
                    cond_a_permis, cond_a_date_permis,

                    assure_a_nom, assure_a_prenom, assure_a_adresse, assure_a_telephone,

                    veh_a_marque, veh_a_modele, veh_a_immatriculation, veh_a_pays,

                    circ_a_sens, circ_a_venant_de, circ_a_allant_a,
                    circ_a_point_choc, circ_a_degats_apparents, circ_a_observations,

                    circ_a_en_stationnement, circ_a_quittait_stationnement,
                    circ_a_prenait_stationnement, circ_a_sortait_parking,
                    circ_a_engageait_giratoire, circ_a_circulait_giratoire,
                    circ_a_heurtait_arriere, circ_a_meme_sens_meme_file,
                    circ_a_changeait_file, circ_a_depassait,
                    circ_a_virait_droite, circ_a_virait_gauche,
                    circ_a_reculait, circ_a_empiete_sens_inverse,
                    circ_a_venait_droite, circ_a_non_prioritaire,

                    signature_a,

                    ass_b_societe, ass_b_numero_police, ass_b_carte_verte,
                    ass_b_validite, ass_b_agence,

                    cond_b_nom, cond_b_prenom, cond_b_adresse, cond_b_telephone,
                    cond_b_permis, cond_b_date_permis,

                    assure_b_nom, assure_b_prenom, assure_b_adresse, assure_b_telephone,

                    veh_b_marque, veh_b_modele, veh_b_immatriculation, veh_b_pays,

                    circ_b_sens, circ_b_venant_de, circ_b_allant_a,
                    circ_b_point_choc, circ_b_degats_apparents, circ_b_observations,

                    circ_b_en_stationnement, circ_b_quittait_stationnement,
                    circ_b_prenait_stationnement, circ_b_sortait_parking,
                    circ_b_engageait_giratoire, circ_b_circulait_giratoire,
                    circ_b_heurtait_arriere, circ_b_meme_sens_meme_file,
                    circ_b_changeait_file, circ_b_depassait,
                    circ_b_virait_droite, circ_b_virait_gauche,
                    circ_b_reculait, circ_b_empiete_sens_inverse,
                    circ_b_venait_droite, circ_b_non_prioritaire,

                    signature_b,

                    croquis_present, description_croquis
                ) VALUES (
                    %s,%s,
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,
                    %s,%s
                )
            """, (
                sinistre_id,
                json.dumps(ocr_data, ensure_ascii=False),

                # accident
                _nullify(acc.get("date")),
                _nullify(acc.get("heure")),
                _nullify(acc.get("lieu")),
                _nullify(str(acc.get("blesses"))) if acc.get("blesses") not in (None, "manquant") else None,
                _nullify(acc.get("degats_materiels_autres")),
                json.dumps(temoins, ensure_ascii=False) if temoins else None,

                # assurance A
                _nullify(ass_a.get("societe")),
                _nullify(ass_a.get("numero_police")),
                _nullify(ass_a.get("carte_verte")),
                _nullify(ass_a.get("validite")),
                _nullify(ass_a.get("agence")),

                # conducteur A
                _nullify(cond_a.get("nom")),
                _nullify(cond_a.get("prenom")),
                _nullify(cond_a.get("adresse")),
                _nullify(cond_a.get("telephone")),
                _nullify(cond_a.get("permis")),
                _nullify(cond_a.get("date_permis")),

                # assure A
                _nullify(assure_a.get("nom")),
                _nullify(assure_a.get("prenom")),
                _nullify(assure_a.get("adresse")),
                _nullify(assure_a.get("telephone")),

                # vehicule A
                _nullify(auto_a.get("marque")),
                _nullify(auto_a.get("type_modele")),
                _nullify(auto_a.get("immatriculation")),
                _nullify(auto_a.get("pays")),

                # circulation A
                _nullify(mvt_a.get("sens")),
                _nullify(mvt_a.get("venant_de")),
                _nullify(mvt_a.get("allant_a")),
                _nullify(mvt_a.get("point_choc")),
                _nullify(mvt_a.get("degats_apparents")),
                _nullify(mvt_a.get("observations")),

                # circonstances A
                _bool(cases_a.get("en_stationnement")),
                _bool(cases_a.get("quittait_stationnement")),
                _bool(cases_a.get("prenait_stationnement")),
                _bool(cases_a.get("sortait_parking")),
                _bool(cases_a.get("engageait_giratoire")),
                _bool(cases_a.get("circulait_giratoire")),
                _bool(cases_a.get("heurtait_arriere")),
                _bool(cases_a.get("meme_sens_meme_file")),
                _bool(cases_a.get("changeait_file")),
                _bool(cases_a.get("depassait")),
                _bool(cases_a.get("virait_droite")),
                _bool(cases_a.get("virait_gauche")),
                _bool(cases_a.get("reculait")),
                _bool(cases_a.get("empiete_sens_inverse")),
                _bool(cases_a.get("venait_droite")),
                _bool(cases_a.get("non_prioritaire")),

                # signature A
                _bool(ocr_data.get("signature_a")),

                # assurance B
                _nullify(ass_b.get("societe")),
                _nullify(ass_b.get("numero_police")),
                _nullify(ass_b.get("carte_verte")),
                _nullify(ass_b.get("validite")),
                _nullify(ass_b.get("agence")),

                # conducteur B
                _nullify(cond_b.get("nom")),
                _nullify(cond_b.get("prenom")),
                _nullify(cond_b.get("adresse")),
                _nullify(cond_b.get("telephone")),
                _nullify(cond_b.get("permis")),
                _nullify(cond_b.get("date_permis")),

                # assure B
                _nullify(assure_b.get("nom")),
                _nullify(assure_b.get("prenom")),
                _nullify(assure_b.get("adresse")),
                _nullify(assure_b.get("telephone")),

                # vehicule B
                _nullify(auto_b.get("marque")),
                _nullify(auto_b.get("type_modele")),
                _nullify(auto_b.get("immatriculation")),
                _nullify(auto_b.get("pays")),

                # circulation B
                _nullify(mvt_b.get("sens")),
                _nullify(mvt_b.get("venant_de")),
                _nullify(mvt_b.get("allant_a")),
                _nullify(mvt_b.get("point_choc")),
                _nullify(mvt_b.get("degats_apparents")),
                _nullify(mvt_b.get("observations")),

                # circonstances B
                _bool(cases_b.get("en_stationnement")),
                _bool(cases_b.get("quittait_stationnement")),
                _bool(cases_b.get("prenait_stationnement")),
                _bool(cases_b.get("sortait_parking")),
                _bool(cases_b.get("engageait_giratoire")),
                _bool(cases_b.get("circulait_giratoire")),
                _bool(cases_b.get("heurtait_arriere")),
                _bool(cases_b.get("meme_sens_meme_file")),
                _bool(cases_b.get("changeait_file")),
                _bool(cases_b.get("depassait")),
                _bool(cases_b.get("virait_droite")),
                _bool(cases_b.get("virait_gauche")),
                _bool(cases_b.get("reculait")),
                _bool(cases_b.get("empiete_sens_inverse")),
                _bool(cases_b.get("venait_droite")),
                _bool(cases_b.get("non_prioritaire")),

                # signature B
                _bool(ocr_data.get("signature_b")),

                # croquis
                _bool(ocr_data.get("croquis_present")),
                _nullify(ocr_data.get("description_croquis")),
            ))

        self.conn.commit()
        logger.info(f"OCR constat stocke PostgreSQL pour sinistre_id={sinistre_id}")

    def update_sinistre_status(self, sinistre_id: int, status: str, note: str = ""):
        """Met a jour le statut d'un sinistre."""
        with self.conn.cursor() as cur:
            if note:
                cur.execute(
                    "UPDATE sinistres SET status=%s, summary=coalesce(summary,'')||%s, updated_at=now() WHERE id=%s",
                    (status, f"\n\n⚠️ {note}", sinistre_id)
                )
            else:
                cur.execute("UPDATE sinistres SET status=%s, updated_at=now() WHERE id=%s", (status, sinistre_id))
        self.conn.commit()

    def update_sinistre_agent_details(self, sinistre_id: int, contract_check: dict = None,
                                       coherence_photos: dict = None, pdf_path: str = None):
        """
        Persiste les resultats structures des etapes du pipeline qui
        n'etaient jusqu'ici visibles que dans les logs et le rapport PDF,
        pour alimenter le dashboard "Agent" du front assurantia (chronogramme
        metier, statut de chaque etape, lien vers le rapport PDF).

        N'ecrase que les champs fournis (les autres restent inchanges).
        N'echoue jamais bruyamment : une erreur ici ne doit pas interrompre
        le pipeline appelant (elle est journalisee puis ignoree).
        """
        fields, values = [], []
        if contract_check is not None:
            fields.append("contract_check=%s")
            values.append(json.dumps(contract_check, ensure_ascii=False, default=str))
        if coherence_photos is not None:
            fields.append("coherence_photos=%s")
            values.append(json.dumps(coherence_photos, ensure_ascii=False, default=str))
        if pdf_path is not None:
            fields.append("pdf_path=%s")
            values.append(pdf_path)
        if not fields:
            return
        fields.append("updated_at=now()")
        values.append(sinistre_id)
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"UPDATE sinistres SET {', '.join(fields)} WHERE id=%s", values)
            self.conn.commit()
        except Exception as e:
            logger.error(f"Echec update_sinistre_agent_details pour sinistre_id={sinistre_id}: {e}")
            self.conn.rollback()

    def set_agent_activity(self, step: str, step_label: str, sender: str = None,
                            subject: str = None, reset_started: bool = False):
        """
        Met a jour la ligne unique `agent_activity` avec l'etape en cours de
        traitement — alimente l'indicateur "en direct" du dashboard Agent.
        `reset_started=True` au tout debut du traitement d'un nouvel email
        (nouveau sender/subject + horodatage de debut) ; False pour les
        etapes suivantes du meme email (on ne garde qu'un seul sender/subject
        courants, pas d'accumulation).
        N'interrompt jamais le pipeline en cas d'echec (log + ignore).
        """
        try:
            with self.conn.cursor() as cur:
                if reset_started:
                    cur.execute(
                        """
                        UPDATE agent_activity
                        SET is_idle=false, sender=%s, subject=%s, step=%s, step_label=%s,
                            started_at=now(), updated_at=now()
                        WHERE id=1
                        """,
                        (sender, subject, step, step_label),
                    )
                else:
                    cur.execute(
                        "UPDATE agent_activity SET is_idle=false, step=%s, step_label=%s, updated_at=now() WHERE id=1",
                        (step, step_label),
                    )
            self.conn.commit()
        except Exception as e:
            logger.warning(f"set_agent_activity a echoue (ignore): {e}")
            self.conn.rollback()

    def set_agent_idle(self):
        """Agent au repos (en attente du prochain cycle de polling IMAP)."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_activity
                    SET is_idle=true, sender=NULL, subject=NULL, step=NULL, step_label=NULL,
                        started_at=NULL, updated_at=now()
                    WHERE id=1
                    """
                )
            self.conn.commit()
        except Exception as e:
            logger.warning(f"set_agent_idle a echoue (ignore): {e}")
            self.conn.rollback()

    def get_agent_config(self) -> dict:
        """Lu a chaque cycle de la boucle principale (voir main.py::run_agent)."""
        try:
            with self.conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute("SELECT is_running, polling_interval_seconds FROM agent_config WHERE id = 1")
                row = cur.fetchone()
            return dict(row) if row else {"is_running": False, "polling_interval_seconds": 60}
        except Exception as e:
            logger.warning(f"get_agent_config a echoue, repli sur valeurs par defaut: {e}")
            return {"is_running": False, "polling_interval_seconds": 60}

    def get_bareme_overrides(self) -> dict:
        """{"cas": (taux_a: float, taux_b: float)} — voir agent/responsabilite.py."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT cas, taux_a, taux_b FROM bareme_overrides")
                return {row[0]: (float(row[1]), float(row[2])) for row in cur.fetchall()}
        except Exception as e:
            logger.warning(f"get_bareme_overrides a echoue, aucune surcharge appliquee: {e}")
            return {}

    def get_insurance_companies(self) -> list[str]:
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT nom FROM insurance_companies ORDER BY nom")
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.warning(f"get_insurance_companies a echoue, repli sur la liste statique: {e}")
            from ressources.insurance_companies import INSURANCE_COMPANIES
            return INSURANCE_COMPANIES

    def update_mongo_ref(self, sinistre_id: int, mongo_ref: str):
        """Met a jour la reference MongoDB dans la table sinistres."""
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE sinistres SET mongo_ref=%s, updated_at=now() WHERE id=%s",
                (mongo_ref, sinistre_id)
            )
        self.conn.commit()

    def update_sinistre_responsabilite(self, sinistre_id: int, responsabilite: dict, md_content: str = None):
        """
        Enregistre le resultat du module de determination de responsabilite
        (voir agent/responsabilite.py) :
          - `responsabilite`             (JSONB) : resultat complet (taux_a/b,
            cas_type, methode, elements_pris_en_compte...)
          - `responsabilite_statut`      (TEXT)  : CONFIRME_BAREME | PROPOSITION_A_VALIDER | INDETERMINE
          - `responsabilite_justification` (TEXT) : explication detaillee
        Met egalement a jour `md_content` si un rapport regenere est fourni
        (le rapport Markdown inclut alors la section "Determination de responsabilite").
        """
        with self.conn.cursor() as cur:
            if md_content is not None:
                cur.execute(
                    """
                    UPDATE sinistres
                    SET responsabilite=%s, responsabilite_statut=%s,
                        responsabilite_justification=%s, md_content=%s, updated_at=now()
                    WHERE id=%s
                    """,
                    (
                        json.dumps(responsabilite, ensure_ascii=False),
                        responsabilite.get("statut"),
                        responsabilite.get("justification"),
                        md_content,
                        sinistre_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE sinistres
                    SET responsabilite=%s, responsabilite_statut=%s, responsabilite_justification=%s, updated_at=now()
                    WHERE id=%s
                    """,
                    (
                        json.dumps(responsabilite, ensure_ascii=False),
                        responsabilite.get("statut"),
                        responsabilite.get("justification"),
                        sinistre_id,
                    ),
                )
        self.conn.commit()
        logger.info(f"Responsabilité enregistrée sinistre id={sinistre_id} statut={responsabilite.get('statut')}")

    def get_sinistre_responsabilite(self, sinistre_id: int) -> dict | None:
        """Recupere le resultat de determination de responsabilite (JSON) d'un sinistre."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT responsabilite FROM sinistres WHERE id=%s", (sinistre_id,))
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def update_documents_gridfs_ids(self, sinistre_id: int, attachments: list[dict]):
        """Met a jour les gridfs_id dans sinistre_documents."""
        with self.conn.cursor() as cur:
            for att in attachments:
                if att.get("gridfs_id"):
                    cur.execute(
                        "UPDATE sinistre_documents SET gridfs_id=%s WHERE sinistre_id=%s AND filename=%s",
                        (att["gridfs_id"], sinistre_id, att.get("filename"))
                    )
        self.conn.commit()

    # ─── Complement de dossier (documents manquants renvoyes) ─────────────────

    def find_pending_incomplete_sinistre(self, sender_email: str) -> dict | None:
        """
        Cherche le dossier incomplet le plus recent du meme expediteur.

        Double verification, comme demande :
          - le statut est bien l'un des statuts "incomplet" (colonne status)
          - le md_content contient bien la section "Dossier Incomplet"
            (confirme que le document a bien ete signale manquant a l'epoque)

        Renvoie aussi toutes les infos de l'email ORIGINAL (message_id, sender,
        cc, bcc, subject, email_date, sinistre_type, confidence, reason, summary,
        created_at) afin de pouvoir regenerer un md_content complet, dans le
        meme format qu'un dossier recu complet des le depart.
        """
        incomplete_statuses = ["PAS_DE_CONSTAT", "PAS_DE_PHOTOS", "PAS_DE_CONSTAT_PHOTOS"]
        with self.conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                SELECT id, message_id, sender, cc, bcc, subject, email_date,
                       status, md_content, mongo_ref,
                       sinistre_type, confidence, reason, summary, created_at
                FROM sinistres
                WHERE sender ILIKE %s
                  AND status = ANY(%s)
                  AND md_content ILIKE %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (f"%{sender_email}%", incomplete_statuses, "%Dossier Incomplet%"),
            )
            return cur.fetchone()

    def add_documents_to_sinistre(self, sinistre_id: int, attachments: list[dict]):
        """Ajoute des pieces jointes (complement) a un sinistre existant."""
        with self.conn.cursor() as cur:
            for att in attachments:
                cur.execute(
                    """
                    INSERT INTO sinistre_documents
                        (sinistre_id, filename, file_format, nature, size_bytes, gridfs_id)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (sinistre_id, att.get("filename"), att.get("classified_type"),
                     att.get("nature"), att.get("size_bytes", 0), att.get("gridfs_id", "")),
                )
        self.conn.commit()
        logger.info(f"{len(attachments)} document(s) complementaire(s) ajoute(s) — sinistre_id={sinistre_id}")

    def get_documents_for_sinistre(self, sinistre_id: int) -> list[dict]:
        """Recupere tous les documents (anciens + nouveaux) d'un sinistre."""
        with self.conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                "SELECT filename, file_format, nature, size_bytes, gridfs_id "
                "FROM sinistre_documents WHERE sinistre_id=%s ORDER BY created_at",
                (sinistre_id,),
            )
            return cur.fetchall()

    def get_constat_ocr_json(self, sinistre_id: int) -> dict | None:
        """Recupere le dernier resultat OCR complet (JSONB) stocke pour ce sinistre."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT ocr_json FROM constat_ocr WHERE sinistre_id=%s "
                "ORDER BY created_at DESC LIMIT 1",
                (sinistre_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def replace_after_complement(self, sinistre_id: int, md_content: str, status: str,
                                  mongo_ref_append: str = ""):
        """
        Apres reception d'un complement : REMPLACE md_content par une version
        entierement regeneree (meme format qu'un dossier recu complet des le
        depart, avec juste une section "Historique" tracant le mail original
        incomplet + le mail de completion), et met a jour le statut et mongo_ref.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sinistres
                SET md_content = %s,
                    status = %s,
                    mongo_ref = CASE WHEN %s <> ''
                                     THEN trim(both ',' from coalesce(mongo_ref, '') || ',' || %s)
                                     ELSE mongo_ref END,
                    updated_at = now()
                WHERE id = %s
                """,
                (md_content, status, mongo_ref_append, mongo_ref_append, sinistre_id),
            )
        self.conn.commit()
        logger.info(f"Sinistre id={sinistre_id} regenere apres complement — nouveau statut: {status}")

