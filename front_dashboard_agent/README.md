# Assurantia — back-office assurance

Application de gestion des contrats, clients et sinistres, branchee sur
votre base PostgreSQL "sinistres".

```
front/
├── assurantia/          Frontend React + Vite + Tailwind
└── assurantia-api/      Backend FastAPI (CRUD + tableau de bord)
```

## 1. Backend — `assurantia-api/`

```bash
cd assurantia-api
cp .env.example .env
# Editer .env avec vos identifiants Postgres (POSTGRES_HOST/PORT/DB/USER/PASSWORD)

python3 -m venv .venv && source .venv/bin/activate   # optionnel mais recommande
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

L'API est alors disponible sur `http://localhost:8000` (doc interactive sur
`http://localhost:8000/docs`).

Endpoints principaux :
- `GET/POST /api/contrats`, `GET/PUT/DELETE /api/contrats/{id}` — objet metier
  composite (contrat + client + vehicule + garanties + exclusions)
- `GET/POST /api/clients`, `GET/PUT/DELETE /api/clients/{id}`
- `GET /api/sinistres`, `GET/PATCH/DELETE /api/sinistres/{id}` — dossiers
  alimentes par l'agent de traitement des emails
- `GET /api/dashboard/stats` — indicateurs agreges
- `GET /api/meta` — listes de reference pour les formulaires/filtres

## 2. Frontend — `assurantia/`

```bash
cd assurantia
cp .env.example .env
# VITE_API_URL doit pointer vers l'API (http://localhost:8000 par defaut)

npm install
npm run dev
```

L'application est servie sur `http://localhost:5173`. Si l'API n'est pas
joignable, un bandeau rouge s'affiche en haut de l'ecran avec l'instruction
pour la demarrer.

## Fonctionnalites

- **Tableau de bord** : contrats actifs, sinistres en cours, primes
  encaissees, taux de sinistralite, sinistres par mois, activite recente —
  tout calcule en direct depuis la base.
- **Contrats** : recherche/filtrage par statut et type, creation et edition
  via un formulaire unique qui couvre le contrat, le client, le vehicule,
  les garanties et les exclusions, suppression avec confirmation.
- **Clients** : CRUD complet, compteurs de contrats/sinistres lies,
  suppression bloquee si le client possede encore des contrats.
- **Sinistres** : consultation des dossiers remontes par l'agent email,
  affectation d'un expert, changement de statut de gestion (En expertise /
  Valide / Refuse / Cloture), suppression.
- **Dashboard Agent** : icône flottante (en bas à droite, accessible depuis
  n'importe quelle fenêtre) qui ouvre le suivi en temps réel du traitement
  automatique des sinistres par l'agent email (mailconnector) — deux files
  "À traiter" / "Traités", chronogramme métier de chaque étape du pipeline
  (documents reçus, lecture du constat, vérification du contrat, contrôle
  des photos, estimation de responsabilité, décision finale) et accès direct
  au rapport PDF généré pour chaque dossier (visualisation ou téléchargement).
  Alimenté par les colonnes `contract_check`, `coherence_photos`, `pdf_path`
  et `dashboard_statut` de la table `sinistres` (voir
  `mailconnector/mailconnector/storage/postgres_storage.py`) — nécessite donc
  que l'agent mailconnector ait bien ajouté ces colonnes lors de son
  initialisation (`initialize_schema()`).

Toutes les actions de creation/modification/suppression affichent une
notification de confirmation ou d'erreur, et les listes se rechargent
automatiquement apres chaque operation.
