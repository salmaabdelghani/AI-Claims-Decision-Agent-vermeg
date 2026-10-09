"""
Verification de l'existence d'un contrat dans la base "assurance"
(tables: client, contrats, vehicules, garanties, exclusion).

Cette base est distincte de la base "sinistres" utilisee pour le suivi des
emails/dossiers (voir storage/postgres_storage.py). On s'y connecte separement
via les variables d'environnement CONTRACTS_DB_* (voir env.example).

Logique :
- L'OCR du constat amiable (agent/constat_ocr.py) extrait un numero de police
  ("numero_police") pour le vehicule A et pour le vehicule B, pas un contrat_id
  directement.
- On recherche ce numero de police dans la table `contrats` (colonne
  `num_police`). Si trouve -> le contrat existe, on recupere son `contrat_id`
  et les infos liees (client, vehicule, garanties, exclusions).
- Sinon -> le contrat est considere comme introuvable.
- Si le contrat EXISTE, deux controles supplementaires sont effectues
  (fonction `check_contract_validity`) avant de considerer le sinistre comme
  exploitable :
    1) `contrats.statut` == "Actif"
    2) `date_effet` < date du sinistre < `date_expiration`
  Si l'un des deux echoue, le contrat est trouve (`found=True`) mais
  invalide (`valid=False`), avec un motif precis dans `invalid_reason`.

NOTE SUR LES NOMS DE COLONNES :
Les colonnes `id-vehicule`, `id-garanties`, `id-exclusion` (avec tirets) ne
sont pas des identifiants SQL valides sans guillemets : on suppose ici qu'elles
sont en realite nommees `id_vehicule`, `id_garanties`, `id_exclusion` (underscore).
Idem, les tables `garanties` et `exclusion` sont supposees avoir une cle
primaire (`garantie_id`, `exclusion_id`) puisque non precisee dans le schema
fourni. Adaptez les constantes ci-dessous si vos noms reels different.
"""
import logging
import re
import datetime
import psycopg

try:
    from ressources.insurance_name import INSURANCE_NAMES
except ImportError:
    INSURANCE_NAMES = {}

logger = logging.getLogger(__name__)

# ─── Noms de colonnes/tables — a adapter si votre schema reel differe ────────
TABLE_CONTRATS   = "contrats"
TABLE_CLIENT     = "client"
TABLE_VEHICULES  = "vehicules"
TABLE_GARANTIES  = "garanties"
TABLE_EXCLUSION  = "exclusion"

COL_GARANTIE_PK  = "garantie_id"   # cle primaire supposee de `garanties`
COL_EXCLUSION_PK = "exclusion_id"  # cle primaire supposee de `exclusion`
# NOTE : garanties/exclusion ne sont plus jointes par defaut dans
# find_contract_by_police/find_contract_by_id. Un `g.*, e.*` sans alias avait
# provoque un bug silencieux : une colonne de ces tables portant le meme nom
# qu'une colonne de `contrats` (ex: "agence") ecrasait la valeur voulue dans
# le dict renvoye par psycopg (dict_row garde la DERNIERE occurrence d'une
# cle en cas de doublon). Si vous avez besoin de donnees de garanties/exclusion,
# rejoignez-les avec des alias explicites et uniques (ex: "g.plafond AS
# garantie_plafond"), jamais via un wildcard `.*` combine a d'autres tables.

# Nom canonique de notre propre compagnie (cle dans INSURANCE_NAMES). Le
# numero de police du constat ne sera verifie en base QUE pour la partie
# (vehicule A ou B) assuree chez cette compagnie.
NOTRE_COMPAGNIE = "AMI Assurances"


def _normalize_company(name: str) -> str:
    """Normalise un nom de compagnie pour comparaison (casse, accents, espaces, ponctuation)."""
    if not name:
        return ""
    n = name.strip().lower()
    n = n.replace("é", "e").replace("è", "e").replace("ê", "e")
    n = re.sub(r"[^a-z0-9]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


# Valeur attendue de `contrats.statut` pour qu'un contrat soit considere
# comme actif. Comparaison insensible a la casse/accents (voir _normalize_company).
STATUT_ACTIF = "Actif"


def _parse_date(value) -> "datetime.date | None":
    """
    Normalise une date en objet `datetime.date`, que la valeur provienne :
    - de psycopg (deja un `datetime.date`/`datetime.datetime` pour une colonne
      DATE/TIMESTAMP) -> renvoyee telle quelle (ou .date() si datetime) ;
    - de l'OCR du constat, au format texte tunisien "JJ/MM/AAAA".
    Renvoie None si la valeur est vide/manquante ou non interpretable.
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    if not text or text.lower() == "manquant":
        return None
    try:
        return datetime.datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None


def _is_our_company(raw_societe: str, canonical: str = NOTRE_COMPAGNIE) -> bool:
    """
    Verifie si `raw_societe` (valeur brute lue par l'OCR) correspond, une fois
    normalise, a notre compagnie `canonical` ou l'un de ses alias declares
    dans ressources/insurance_name.py.
    """
    if not raw_societe or str(raw_societe).lower() == "manquant":
        return False
    aliases = INSURANCE_NAMES.get(canonical, [])
    normalized_targets = {_normalize_company(a) for a in aliases}
    normalized_targets.add(_normalize_company(canonical))
    return _normalize_company(raw_societe) in normalized_targets


def check_contract_validity(contract: dict, date_sinistre) -> dict:
    """
    Une fois un contrat trouve (numero de police existant en base), verifie
    qu'il est bien exploitable pour ce sinistre :

        1) contract["statut"] == "Actif" (comparaison normalisee)
        2) date_effet < date_sinistre < date_expiration
           (le sinistre doit survenir DURANT la periode de couverture)

    `date_sinistre` peut etre un `datetime.date` ou une chaine "JJ/MM/AAAA"
    (format extrait par l'OCR, cf. accident.date).

    Renvoie :
        {
            "valid": bool,
            "reason": None | str,   # motif d'invalidite (precis), None si valid
        }
    """
    statut = contract.get("contrat_statut")
    statut_ok = _normalize_company(statut) == _normalize_company(STATUT_ACTIF)
    if not statut_ok:
        return {
            "valid": False,
            "reason": f"Contrat non actif (statut en base : '{statut or 'inconnu'}', attendu '{STATUT_ACTIF}').",
        }

    d_sinistre = _parse_date(date_sinistre)
    d_effet = _parse_date(contract.get("contrat_date_effet"))
    d_expiration = _parse_date(contract.get("contrat_date_expiration"))

    if d_sinistre is None:
        return {
            "valid": False,
            "reason": "Date du sinistre manquante ou illisible — impossible de verifier la periode de couverture.",
        }
    if d_effet is None or d_expiration is None:
        return {
            "valid": False,
            "reason": "Dates d'effet/d'expiration du contrat manquantes en base — impossible de verifier la periode de couverture.",
        }

    if not (d_effet < d_sinistre < d_expiration):
        return {
            "valid": False,
            "reason": (
                f"Date du sinistre ({d_sinistre.strftime('%d/%m/%Y')}) hors periode de "
                f"couverture du contrat (effet: {d_effet.strftime('%d/%m/%Y')}, "
                f"expiration: {d_expiration.strftime('%d/%m/%Y')})."
            ),
        }

    return {"valid": True, "reason": None}


def _normalize_text(value: str) -> str:
    """
    Normalisation generique pour comparer des chaines issues de l'OCR a des
    valeurs en base (casse, accents, espaces multiples, ponctuation legere).
    Reutilise la meme logique que _normalize_company, sous un nom plus generique
    car utilisee aussi pour nom/prenom/agence/marque/modele.
    """
    return _normalize_company(value)


def _normalize_immat(value: str) -> str:
    """
    Normalise une immatriculation tunisienne pour comparaison : supprime tout
    ce qui n'est pas alphanumerique et met en majuscules, afin que
    "170 TN 8569", "170TN8569" et "170-tn-8569" soient consideres identiques.
    """
    if not value:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()


def _is_missing(value) -> bool:
    """Vrai si la valeur OCR est vide/None/'manquant' (insensible a la casse)."""
    return value is None or str(value).strip() == "" or str(value).strip().lower() == "manquant"


def _parse_validite_range(text: str) -> "tuple[datetime.date | None, datetime.date | None]":
    """
    Extrait deux dates "JJ/MM/AAAA" depuis le texte libre du champ
    "assurance.validite" du constat (ex: "du 27/01/2024 au 26/01/2025").
    Renvoie (date_debut, date_fin) ou (None, None) si le texte est manquant
    ou si on n'y trouve pas exactement deux dates exploitables.
    """
    if _is_missing(text):
        return None, None
    dates_found = re.findall(r"\d{2}/\d{2}/\d{4}", str(text))
    if len(dates_found) < 2:
        return None, None
    d1 = _parse_date(dates_found[0])
    d2 = _parse_date(dates_found[1])
    return d1, d2


def _texts_match(ocr_value: str, db_value: str) -> bool:
    """
    Compare une valeur OCR a une valeur base apres normalisation. Tolerant :
    considere une correspondance si les chaines normalisees sont egales, ou
    si l'une contient l'autre (utile quand le constat porte "Mercedes-Benz 240D"
    et que la base ne stocke que "Mercedes-Benz", ou l'inverse).
    Une valeur OCR manquante n'est jamais consideree comme un mismatch bloquant
    (on ne peut pas contredire une donnee qu'on n'a pas lue).
    """
    if _is_missing(ocr_value):
        return True
    if not db_value or not str(db_value).strip():
        return True
    a, b = _normalize_text(ocr_value), _normalize_text(db_value)
    if not a or not b:
        return True
    return a == b or a in b or b in a


def check_contract_coherence(ocr_vehicule: dict, contract: dict) -> dict:
    """
    Une fois un contrat trouve ET valide pour la partie assuree chez nous,
    verifie que les informations lues sur le constat (pour cette partie
    UNIQUEMENT) sont coherentes avec celles enregistrees en base :

        - assurance.agence             <-> contrats.numero_agence, avec repli sur
                                            contrats.agence (nom/region) si le
                                            numero ne correspond pas
        - assurance.validite (du/au)  <-> contrats.date_effet / date_expiration
        - assure.nom / assure.prenom  <-> client.nom / client.prenom
        - vehicule.marque             <-> vehicules.marque
        - vehicule.type_modele        <-> vehicules.modele
        - vehicule.immatriculation    <-> vehicules.immatriculation

    (Le numero de police est deja verifie en amont dans `verify_from_ocr`.)

    Un champ OCR "manquant" n'est jamais compte comme une incoherence (on ne
    bloque pas un dossier a cause d'un champ que l'OCR n'a pas reussi a lire) :
    seule une VALEUR LUE ET DIFFERENTE de la base declenche un mismatch.

    Renvoie :
        {
            "coherent": bool,          # True si aucun mismatch detecte
            "mismatches": [
                {"champ": "agence", "constat": "731", "contrat": "745"},
                ...
            ],
        }
    """
    mismatches = []

    assurance = (ocr_vehicule or {}).get("assurance", {}) or {}
    assure    = (ocr_vehicule or {}).get("assure", {}) or {}
    vehicule  = (ocr_vehicule or {}).get("vehicule", {}) or {}

    # ── Agence ────────────────────────────────────────────────────────────
    # Sur le constat, le champ "Agence" est cense contenir le NUMERO d'agence
    # (ex: "712"), mais il arrive qu'un client y ecrive plutot le NOM/la
    # region de l'agence (ex: "Mahdia", "Sfax Centre") par erreur ou par
    # habitude. Strategie :
    #   1) Si la valeur lue est numerique, on la compare au numero d'agence
    #      en base (contrat_numero_agence).
    #   2) Si cette comparaison echoue (ou si la valeur n'est pas numerique),
    #      on retente avec le nom d'agence en base (contrat_agence) avant de
    #      conclure a une incoherence.
    #   3) Mismatch UNIQUEMENT si ni le numero NI le nom ne correspondent.
    agence_ocr = assurance.get("agence")
    if not _is_missing(agence_ocr):
        numero_agence_db = contract.get("contrat_numero_agence")
        nom_agence_db = contract.get("contrat_agence")

        numero_ok = False
        if str(agence_ocr).strip().isdigit() and numero_agence_db is not None:
            numero_ok = int(str(agence_ocr).strip()) == int(numero_agence_db)

        nom_ok = _texts_match(agence_ocr, nom_agence_db) if not _is_missing(nom_agence_db) else False

        if not numero_ok and not nom_ok:
            mismatches.append({
                "champ": "agence",
                "constat": agence_ocr,
                "contrat": f"n°{numero_agence_db} / {nom_agence_db}",
            })

    # ── Attestation valable du ... au ... ───────────────────────────────────
    d_debut_constat, d_fin_constat = _parse_validite_range(assurance.get("validite"))
    d_effet_contrat = _parse_date(contract.get("contrat_date_effet"))
    d_expiration_contrat = _parse_date(contract.get("contrat_date_expiration"))
    if d_debut_constat is not None and d_fin_constat is not None:
        if d_effet_contrat is None or d_expiration_contrat is None or \
           d_debut_constat != d_effet_contrat or d_fin_constat != d_expiration_contrat:
            mismatches.append({
                "champ": "attestation_valable",
                "constat": f"{d_debut_constat.strftime('%d/%m/%Y')} au {d_fin_constat.strftime('%d/%m/%Y')}",
                "contrat": (
                    f"{d_effet_contrat.strftime('%d/%m/%Y')} au {d_expiration_contrat.strftime('%d/%m/%Y')}"
                    if d_effet_contrat and d_expiration_contrat else "manquant en base"
                ),
            })

    # ── Assure : nom / prenom ───────────────────────────────────────────────
    if not _texts_match(assure.get("nom"), contract.get("client_nom")):
        mismatches.append({
            "champ": "assure.nom",
            "constat": assure.get("nom"),
            "contrat": contract.get("client_nom"),
        })
    if not _texts_match(assure.get("prenom"), contract.get("client_prenom")):
        mismatches.append({
            "champ": "assure.prenom",
            "constat": assure.get("prenom"),
            "contrat": contract.get("client_prenom"),
        })

    # ── Vehicule : marque / modele / immatriculation ────────────────────────
    if not _texts_match(vehicule.get("marque"), contract.get("vehicule_marque")):
        mismatches.append({
            "champ": "vehicule.marque",
            "constat": vehicule.get("marque"),
            "contrat": contract.get("vehicule_marque"),
        })
    if not _texts_match(vehicule.get("type_modele"), contract.get("vehicule_modele")):
        mismatches.append({
            "champ": "vehicule.modele",
            "constat": vehicule.get("type_modele"),
            "contrat": contract.get("vehicule_modele"),
        })

    immat_ocr = vehicule.get("immatriculation")
    immat_db = contract.get("vehicule_immatriculation")
    if not _is_missing(immat_ocr) and immat_db and \
       _normalize_immat(immat_ocr) != _normalize_immat(immat_db):
        mismatches.append({
            "champ": "vehicule.immatriculation",
            "constat": immat_ocr,
            "contrat": immat_db,
        })

    return {"coherent": len(mismatches) == 0, "mismatches": mismatches}


class ContractStorage:

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
        self.conn.autocommit = True
        logger.info(f"Base assurance connectee ({self.dbname}@{self.host}, client_encoding=UTF8).")

    def close(self):
        if self.conn:
            self.conn.close()

    # ─── Recherche brute par numero de police ────────────────────────────────

    def find_contract_by_police(self, num_police: str) -> dict | None:
        """
        Cherche un contrat par son numero de police et renvoie toutes les
        informations liees (client, vehicule, garanties, exclusions).
        Renvoie None si aucun contrat ne correspond.
        """
        if not num_police or not str(num_police).strip():
            return None

        query = f"""
            SELECT
                c.contrat_id, c.num_police, c.client_id,
                c.type_contrat   AS contrat_type_contrat,
                c.statut         AS contrat_statut,
                c.date_souscription AS contrat_date_souscription,
                c.date_effet     AS contrat_date_effet,
                c.date_expiration AS contrat_date_expiration,
                c.bonus_malus    AS contrat_bonus_malus,
                c.prime_annuelle AS contrat_prime_annuelle,
                c.mode_paiement  AS contrat_mode_paiement,
                c.agence         AS contrat_agence,
                c.numero_agence  AS contrat_numero_agence,

                cl.nom AS client_nom, cl.prenom AS client_prenom,
                cl.cin AS client_cin, cl.date_naissance AS client_date_naissance,
                cl.adresse AS client_adresse, cl.telephone AS client_telephone,
                cl.email AS client_email, cl.profession AS client_profession,
                cl.numero_permis AS client_numero_permis,
                cl.date_delivrance_permis AS client_date_delivrance_permis,

                v.vehicule_id,
                v.immatriculation AS vehicule_immatriculation,
                v.vin AS vehicule_vin,
                v.marque AS vehicule_marque,
                v.modele AS vehicule_modele,
                v.annee AS vehicule_annee,
                v.energie AS vehicule_energie,
                v.couleur AS vehicule_couleur,
                v.valeur_assuree AS vehicule_valeur_assuree,
                v.usage AS vehicule_usage

            FROM {TABLE_CONTRATS} c
            LEFT JOIN {TABLE_CLIENT} cl ON cl.client_id = c.client_id
            LEFT JOIN {TABLE_VEHICULES} v ON v.contrat_id = c.contrat_id
            WHERE c.num_police = %s
            LIMIT 1
        """
        with self.conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(query, (str(num_police).strip(),))
            row = cur.fetchone()
        return dict(row) if row else None

    def find_contract_by_id(self, contrat_id: int) -> dict | None:
        """Meme chose, mais recherche directement par contrat_id."""
        query = f"""
            SELECT
                c.contrat_id, c.num_police, c.client_id,
                c.type_contrat   AS contrat_type_contrat,
                c.statut         AS contrat_statut,
                c.date_souscription AS contrat_date_souscription,
                c.date_effet     AS contrat_date_effet,
                c.date_expiration AS contrat_date_expiration,
                c.bonus_malus    AS contrat_bonus_malus,
                c.prime_annuelle AS contrat_prime_annuelle,
                c.mode_paiement  AS contrat_mode_paiement,
                c.agence         AS contrat_agence,
                c.numero_agence  AS contrat_numero_agence,

                cl.nom AS client_nom, cl.prenom AS client_prenom,
                cl.cin AS client_cin, cl.date_naissance AS client_date_naissance,
                cl.adresse AS client_adresse, cl.telephone AS client_telephone,
                cl.email AS client_email, cl.profession AS client_profession,
                cl.numero_permis AS client_numero_permis,
                cl.date_delivrance_permis AS client_date_delivrance_permis,

                v.vehicule_id,
                v.immatriculation AS vehicule_immatriculation,
                v.vin AS vehicule_vin,
                v.marque AS vehicule_marque,
                v.modele AS vehicule_modele,
                v.annee AS vehicule_annee,
                v.energie AS vehicule_energie,
                v.couleur AS vehicule_couleur,
                v.valeur_assuree AS vehicule_valeur_assuree,
                v.usage AS vehicule_usage

            FROM {TABLE_CONTRATS} c
            LEFT JOIN {TABLE_CLIENT} cl ON cl.client_id = c.client_id
            LEFT JOIN {TABLE_VEHICULES} v ON v.contrat_id = c.contrat_id
            WHERE c.contrat_id = %s
            LIMIT 1
        """
        with self.conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(query, (contrat_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    def get_full_contract_details(self, contrat_id: int) -> dict | None:
        """
        Comme find_contract_by_id, mais joint EN PLUS les garanties et
        exclusions liees au contrat (tables `garanties`/`exclusion`, via les
        cles etrangeres contrats.id_garanties / contrats.id_exclusion).

        Destine au rapport d'analyse PDF (agent/pdf_report_generator.py) qui
        a besoin du detail complet des garanties/exclusions pour que
        l'expert/gestionnaire puisse decider sans repasser par la base.

        Chaque colonne de `garanties`/`exclusion` est explicitement aliasee
        (jamais de wildcard `.*`) pour eviter tout ecrasement silencieux de
        colonnes homonymes entre tables (voir note en tete de fichier).
        """
        if not contrat_id:
            return None

        query = f"""
            SELECT
                c.contrat_id, c.num_police, c.client_id,
                c.type_contrat   AS contrat_type_contrat,
                c.statut         AS contrat_statut,
                c.date_souscription AS contrat_date_souscription,
                c.date_effet     AS contrat_date_effet,
                c.date_expiration AS contrat_date_expiration,
                c.bonus_malus    AS contrat_bonus_malus,
                c.prime_annuelle AS contrat_prime_annuelle,
                c.mode_paiement  AS contrat_mode_paiement,
                c.agence         AS contrat_agence,
                c.numero_agence  AS contrat_numero_agence,

                cl.nom AS client_nom, cl.prenom AS client_prenom,
                cl.cin AS client_cin, cl.date_naissance AS client_date_naissance,
                cl.adresse AS client_adresse, cl.telephone AS client_telephone,
                cl.email AS client_email, cl.profession AS client_profession,
                cl.numero_permis AS client_numero_permis,
                cl.date_delivrance_permis AS client_date_delivrance_permis,

                v.vehicule_id,
                v.immatriculation AS vehicule_immatriculation,
                v.vin AS vehicule_vin,
                v.marque AS vehicule_marque,
                v.modele AS vehicule_modele,
                v.annee AS vehicule_annee,
                v.energie AS vehicule_energie,
                v.couleur AS vehicule_couleur,
                v.valeur_assuree AS vehicule_valeur_assuree,
                v.usage AS vehicule_usage,

                g.garantie_id AS garantie_id,
                g."Dommages_Collision_Active"     AS garantie_dommages_collision_active,
                g."Dommages_Collision_franchise"  AS garantie_dommages_collision_franchise,
                g."Dommages_Collision_plafond"    AS garantie_dommages_collision_plafond,
                g."Dommages_Collision_Couverture" AS garantie_dommages_collision_couverture,
                g."RC_Active"     AS garantie_rc_active,
                g."RC_franchise"  AS garantie_rc_franchise,
                g."RC_plafond"    AS garantie_rc_plafond,
                g."RC_Couverture" AS garantie_rc_couverture,
                g."Vol_Active"     AS garantie_vol_active,
                g."Vol_franchise"  AS garantie_vol_franchise,
                g."vol-plafond"    AS garantie_vol_plafond,
                g."Vol_Couverture" AS garantie_vol_couverture,
                g."Incendie_Active"     AS garantie_incendie_active,
                g."Incendie_franchise"  AS garantie_incendie_franchise,
                g."Incendie_plafond"    AS garantie_incendie_plafond,
                g."Incendie_Couverture" AS garantie_incendie_couverture,
                g."Bris_de_Glace_Active"     AS garantie_bris_glace_active,
                g."Bris_de_Glace_franchise"  AS garantie_bris_glace_franchise,
                g."Bris_de_Glace_plafond"    AS garantie_bris_glace_plafond,
                g."Bris_de_Glace_Couverture" AS garantie_bris_glace_couverture,

                e.exclusion_id AS exclusion_id,
                e."Exclusions_Conduite_sous_alcool"    AS exclusion_conduite_sous_alcool,
                e."Exclusions_Conducteur_non_autorise" AS exclusion_conducteur_non_autorise

            FROM {TABLE_CONTRATS} c
            LEFT JOIN {TABLE_CLIENT} cl ON cl.client_id = c.client_id
            LEFT JOIN {TABLE_VEHICULES} v ON v.contrat_id = c.contrat_id
            LEFT JOIN {TABLE_GARANTIES} g ON g.{COL_GARANTIE_PK} = c.id_garanties
            LEFT JOIN {TABLE_EXCLUSION} e ON e.{COL_EXCLUSION_PK} = c.id_exclusion
            WHERE c.contrat_id = %s
            LIMIT 1
        """
        try:
            with self.conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(query, (contrat_id,))
                row = cur.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Echec recuperation details complets contrat_id={contrat_id}: {e}")
            return None

    def contract_exists(self, num_police: str) -> bool:
        """Verification rapide (booleenne), sans recuperer tout le detail."""
        if not num_police or not str(num_police).strip():
            return False
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT 1 FROM {TABLE_CONTRATS} WHERE num_police = %s LIMIT 1",
                (str(num_police).strip(),),
            )
            return cur.fetchone() is not None

    # ─── Verification a partir des donnees OCR du constat ───────────────────

    def verify_from_ocr(self, ocr_data: dict, notre_compagnie: str = NOTRE_COMPAGNIE) -> dict:
        """
        Prend le resultat OCR du constat (voir agent/constat_ocr.py) et
        verifie l'existence du contrat, mais UNIQUEMENT pour la partie
        (vehicule A ou B) dont la compagnie d'assurance ("societe") correspond
        a `notre_compagnie` (normalisation via ressources/insurance_name.py).
        L'autre partie (assuree ailleurs) n'est jamais verifiee.

        Renvoie un dict:
        {
            "found": bool,           # le numero de police existe en base
            "valid": bool,           # found ET (statut Actif ET dans la periode de couverture)
            "party": "A" | "B" | None,
            "num_police": str | None,
            "contrat_id": int | None,
            "contract": dict | None,
            "checked": {"A": "12345", "B": "manquant"},   # polices lues sur le constat
            "companies": {"A": "AMI Assurances", "B": "STAR Assurances"},
            "reason": None | "compagnie_non_reconnue" | "police_introuvable"
                      | "contrat_invalide" | "contrat_incoherent",
            "invalid_reason": None | str,   # motif precis si valid=False alors que found=True
            "coherent": bool,        # True seulement si found ET valid ET donnees coherentes
            "mismatches": [          # champs constat/base qui different (vide si coherent=True)
                {"champ": "agence", "constat": "731", "contrat": "745"}, ...
            ],
        }

        `date_sinistre` (accident.date de l'OCR, format "JJ/MM/AAAA") est
        automatiquement recupere depuis `ocr_data["accident"]["date"]` afin de
        verifier que le sinistre survient bien pendant la periode de
        couverture du contrat (date_effet < date_sinistre < date_expiration).
        """
        assurance_a = (ocr_data.get("vehicule_a", {}) or {}).get("assurance", {}) or {}
        assurance_b = (ocr_data.get("vehicule_b", {}) or {}).get("assurance", {}) or {}

        societe_a, police_a = assurance_a.get("societe"), assurance_a.get("numero_police")
        societe_b, police_b = assurance_b.get("societe"), assurance_b.get("numero_police")

        checked   = {"A": police_a, "B": police_b}
        companies = {"A": societe_a, "B": societe_b}
        date_sinistre = (ocr_data.get("accident", {}) or {}).get("date")

        # Ne garde que les parties dont la compagnie correspond a la notre
        candidates = [
            (party, num_police)
            for party, societe, num_police in (("A", societe_a, police_a), ("B", societe_b, police_b))
            if _is_our_company(societe, notre_compagnie)
        ]

        if not candidates:
            logger.warning(
                f"Aucune partie assuree chez {notre_compagnie} — "
                f"compagnies detectees sur le constat: {companies}"
            )
            return {
                "found": False, "valid": False, "party": None, "num_police": None,
                "contrat_id": None, "contract": None,
                "checked": checked, "companies": companies,
                "reason": "compagnie_non_reconnue", "invalid_reason": None,
                "coherent": False, "mismatches": [],
            }

        for party, num_police in candidates:
            if not num_police or str(num_police).lower() == "manquant":
                continue
            contract = self.find_contract_by_police(num_police)
            if contract:
                logger.info(
                    f"Contrat trouve pour vehicule {party} (assure chez {notre_compagnie}) — "
                    f"num_police={num_police} -> contrat_id={contract['contrat_id']}"
                )
                validity = check_contract_validity(contract, date_sinistre)
                if not validity["valid"]:
                    logger.warning(
                        f"Contrat {num_police} trouve mais INVALIDE pour ce sinistre : "
                        f"{validity['reason']}"
                    )
                    return {
                        "found": True, "valid": False, "party": party, "num_police": num_police,
                        "contrat_id": contract["contrat_id"], "contract": contract,
                        "checked": checked, "companies": companies,
                        "reason": "contrat_invalide", "invalid_reason": validity["reason"],
                        "coherent": False, "mismatches": [],
                    }

                ocr_vehicule = ocr_data.get(f"vehicule_{party.lower()}", {}) or {}
                coherence = check_contract_coherence(ocr_vehicule, contract)
                if not coherence["coherent"]:
                    logger.warning(
                        f"Contrat {num_police} trouve et valide mais donnees INCOHERENTES "
                        f"avec la base pour vehicule {party} : {coherence['mismatches']}"
                    )
                    return {
                        "found": True, "valid": True, "party": party, "num_police": num_police,
                        "contrat_id": contract["contrat_id"], "contract": contract,
                        "checked": checked, "companies": companies,
                        "reason": "contrat_incoherent", "invalid_reason": None,
                        "coherent": False, "mismatches": coherence["mismatches"],
                    }

                return {
                    "found": True, "valid": True, "party": party, "num_police": num_police,
                    "contrat_id": contract["contrat_id"], "contract": contract,
                    "checked": checked, "companies": companies,
                    "reason": None, "invalid_reason": None,
                    "coherent": True, "mismatches": [],
                }

        logger.warning(
            f"Compagnie {notre_compagnie} reconnue mais numero de police introuvable en base — "
            f"polices detectees: {checked}"
        )
        return {
            "found": False, "valid": False, "party": None, "num_police": None,
            "contrat_id": None, "contract": None,
            "checked": checked, "companies": companies,
            "reason": "police_introuvable", "invalid_reason": None,
            "coherent": False, "mismatches": [],
        }
