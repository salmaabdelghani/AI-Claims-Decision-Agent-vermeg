"""
Schemas Pydantic — un schema "metier" par entite (Client, Vehicule,
Garanties, Exclusion) + un schema composite pour Contrat, qui est l'objet
metier central : un contrat = 1 client + 1 vehicule + 1 jeu de garanties +
1 jeu d'exclusions.
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


# ─── Client ───────────────────────────────────────────────────────────────

class ClientPayload(BaseModel):
    client_id: Optional[int] = None  # si fourni -> reutilise un client existant
    nom: Optional[str] = None
    prenom: Optional[str] = None
    cin: Optional[str] = None
    date_naissance: Optional[date] = None
    adresse: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    profession: Optional[str] = None
    numero_permis: Optional[str] = None
    date_delivrance_permis: Optional[date] = None


class ClientOut(ClientPayload):
    client_id: int
    nb_contrats: Optional[int] = None
    nb_sinistres: Optional[int] = None


# ─── Vehicule ─────────────────────────────────────────────────────────────

class VehiculePayload(BaseModel):
    immatriculation: Optional[str] = None
    vin: Optional[str] = None
    marque: Optional[str] = None
    modele: Optional[str] = None
    annee: Optional[int] = None
    energie: Optional[str] = None
    couleur: Optional[str] = None
    valeur_assuree: Optional[float] = None
    usage: Optional[str] = None


class VehiculeOut(VehiculePayload):
    vehicule_id: int
    contrat_id: Optional[int] = None


# ─── Garanties ────────────────────────────────────────────────────────────

class GarantiesPayload(BaseModel):
    dommages_collision_active: bool = False
    dommages_collision_franchise: Optional[float] = None
    dommages_collision_plafond: Optional[float] = None
    dommages_collision_couverture: Optional[int] = None
    rc_active: bool = False
    rc_franchise: Optional[float] = None
    rc_plafond: Optional[float] = None
    rc_couverture: Optional[int] = None
    vol_active: bool = False
    vol_franchise: Optional[float] = None
    vol_plafond: Optional[float] = None
    vol_couverture: Optional[int] = None
    incendie_active: bool = False
    incendie_franchise: Optional[float] = None
    incendie_plafond: Optional[float] = None
    incendie_couverture: Optional[int] = None
    bris_glace_active: bool = False
    bris_glace_franchise: Optional[float] = None
    bris_glace_plafond: Optional[float] = None
    bris_glace_couverture: Optional[int] = None


class GarantiesOut(GarantiesPayload):
    garantie_id: int


# ─── Exclusion ────────────────────────────────────────────────────────────

class ExclusionPayload(BaseModel):
    conduite_sous_alcool: bool = False
    conducteur_non_autorise: bool = False


class ExclusionOut(ExclusionPayload):
    exclusion_id: int


# ─── Contrat (objet metier composite) ──────────────────────────────────────

class ContratCore(BaseModel):
    num_police: str
    type_contrat: Optional[str] = None
    statut: Optional[str] = "En attente"
    date_souscription: Optional[date] = None
    date_effet: Optional[date] = None
    date_expiration: Optional[date] = None
    bonus_malus: Optional[float] = None
    prime_annuelle: Optional[float] = None
    mode_paiement: Optional[str] = None
    agence: Optional[str] = None
    numero_agence: Optional[int] = Field(default=None, gt=0)


class ContratCreate(BaseModel):
    contrat: ContratCore
    client: ClientPayload
    vehicule: VehiculePayload
    garanties: GarantiesPayload
    exclusion: ExclusionPayload


class ContratUpdate(ContratCreate):
    pass


class ContratListItem(BaseModel):
    contrat_id: int
    num_police: Optional[str]
    statut: Optional[str]
    type_contrat: Optional[str]
    prime_annuelle: Optional[float]
    date_expiration: Optional[date]
    client_nom: Optional[str]
    client_prenom: Optional[str]
    vehicule_marque: Optional[str]
    vehicule_modele: Optional[str]


class ContratDetail(BaseModel):
    contrat: dict
    client: Optional[dict] = None
    vehicule: Optional[dict] = None
    garanties: Optional[dict] = None
    exclusion: Optional[dict] = None


# ─── Dossiers sinistres (lecture + actions de gestion) ─────────────────────

class SinistrePatch(BaseModel):
    statut: Optional[str] = None
    expert: Optional[str] = None
    commentaire: Optional[list] = None
    avis_expert: Optional[str] = None
    statut_remboursement: Optional[str] = None
    montant_rembourse: Optional[float] = None
    date_remboursement: Optional[date] = None


# ─── Dashboard "Agent" (sinistres traites par l'agent email, table `sinistres`) ──

class AgentSinistrePatch(BaseModel):
    dashboard_statut: str  # 'nouveau' (a traiter) | 'traite' (revu/cloture par un gestionnaire)


class AgentConfigPatch(BaseModel):
    is_running: Optional[bool] = None
    polling_interval_seconds: Optional[int] = None


class BaremeOverridePatch(BaseModel):
    taux_a: float
    taux_b: float


class InsuranceCompanyCreate(BaseModel):
    nom: str


class OcrCorrection(BaseModel):
    ocr_json: dict
