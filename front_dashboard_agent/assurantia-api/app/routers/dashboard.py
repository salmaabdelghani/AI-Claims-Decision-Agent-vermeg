"""
Indicateurs agreges pour le tableau de bord (vue metier synthetique).
"""
from fastapi import APIRouter

from app.database import get_cursor

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Statuts de dossier consideres comme "clos" (ne comptent plus comme "en cours")
STATUTS_CLOS = ("Validé", "Refusé", "Clôturé")


@router.get("/stats")
def get_stats():
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM contrats")
        total_contrats = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM contrats WHERE statut = 'Actif'")
        contrats_actifs = cur.fetchone()["n"]

        cur.execute(
            "SELECT COUNT(*) AS n FROM dossiers_sinistres WHERE statut != ALL(%s)",
            (list(STATUTS_CLOS),),
        )
        sinistres_en_cours = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM dossiers_sinistres")
        total_sinistres = cur.fetchone()["n"]

        cur.execute("SELECT COALESCE(SUM(prime_annuelle), 0) AS s FROM contrats WHERE statut = 'Actif'")
        primes_encaissees = float(cur.fetchone()["s"])

        taux_sinistralite = round((total_sinistres / contrats_actifs * 100), 2) if contrats_actifs else 0.0

        cur.execute(
            """
            SELECT type_contrat, COUNT(*) AS n
            FROM contrats
            GROUP BY type_contrat
            ORDER BY n DESC
            """
        )
        repartition_types = cur.fetchall()

        cur.execute(
            """
            SELECT statut, COUNT(*) AS n
            FROM dossiers_sinistres
            GROUP BY statut
            ORDER BY n DESC
            """
        )
        repartition_statuts_sinistres = cur.fetchall()

        # Sinistres declares par mois (date_accident stockee en texte 'dd/mm/yyyy')
        cur.execute(
            """
            SELECT
                split_part(date_accident, '/', 2) AS mois,
                split_part(date_accident, '/', 3) AS annee,
                COUNT(*) AS n
            FROM dossiers_sinistres
            WHERE date_accident ~ '^\\d{2}/\\d{2}/\\d{4}$'
            GROUP BY mois, annee
            ORDER BY annee, mois
            """
        )
        par_mois_raw = cur.fetchall()

        # Activite recente : derniers dossiers sinistres + derniers contrats
        cur.execute(
            """
            SELECT 'sinistre' AS nature, numero_dossier AS ref, statut, created_at AS moment
            FROM dossiers_sinistres
            ORDER BY created_at DESC NULLS LAST LIMIT 5
            """
        )
        recents_sinistres = cur.fetchall()

        cur.execute(
            """
            SELECT 'contrat' AS nature, num_police AS ref, statut,
                   date_souscription::timestamptz AS moment
            FROM contrats
            WHERE date_souscription IS NOT NULL
            ORDER BY date_souscription DESC LIMIT 5
            """
        )
        recents_contrats = cur.fetchall()

    activite_recente = sorted(
        [*recents_sinistres, *recents_contrats],
        key=lambda r: r["moment"] or "",
        reverse=True,
    )[:6]

    return {
        "total_contrats": total_contrats,
        "contrats_actifs": contrats_actifs,
        "sinistres_en_cours": sinistres_en_cours,
        "total_sinistres": total_sinistres,
        "primes_encaissees": primes_encaissees,
        "taux_sinistralite": taux_sinistralite,
        "repartition_types_contrats": repartition_types,
        "repartition_statuts_sinistres": repartition_statuts_sinistres,
        "sinistres_par_mois": par_mois_raw,
        "activite_recente": activite_recente,
    }
