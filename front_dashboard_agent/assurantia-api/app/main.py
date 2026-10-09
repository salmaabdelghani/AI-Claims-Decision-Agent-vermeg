"""
API Assurantia — backend FastAPI expose au frontend React, branche
directement sur la base PostgreSQL "sinistres".

Lancement local :
    cp .env.example .env   # puis renseigner les identifiants Postgres
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.database import pool
from app import mongo, migrations
from app.routers import clients, contrats, sinistres, dashboard, agent, documents


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    migrations.run_migrations()
    mongo.connect()
    yield
    pool.close()
    mongo.close()


app = FastAPI(
    title="Assurantia API",
    description="API metier pour la gestion des contrats, clients et sinistres assurance.",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clients.router)
app.include_router(contrats.router)
app.include_router(sinistres.router)
app.include_router(dashboard.router)
app.include_router(agent.router)
app.include_router(documents.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    """Valeurs de reference utilisees par les formulaires/filtres du frontend."""
    return {
        "types_contrat": ["Auto", "Habitation", "Santé", "Vie"],
        "statuts_contrat": ["Actif", "En attente", "Résilié", "Expiré"],
        "modes_paiement": ["Annuel", "Semestriel", "Trimestriel", "Mensuel"],
        "statuts_sinistre_pipeline": [
            "A_TRAITER", "PAS_DE_CONSTAT", "PAS_DE_PHOTOS", "PAS_DE_CONSTAT_PHOTOS",
            "CONSTAT_INCOMPLET", "CONSTAT_A_VERIFIER", "CONTRAT_INTROUVABLE",
            "CONTRAT_INVALIDE", "CONTRAT_INCOHERENT", "INVALIDE",
        ],
        "statuts_sinistre_gestion": ["En expertise", "Validé", "Refusé", "Clôturé"],
        "statuts_remboursement": ["Non initié", "En cours", "Remboursé", "Refusé"],
    }
