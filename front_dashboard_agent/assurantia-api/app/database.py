"""
Connexion a la base PostgreSQL "sinistres" (pool partage par toute l'API).
"""
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

load_dotenv()

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB", "sinistres")
PG_USER = os.getenv("POSTGRES_USER", "user")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

CONNINFO = (
    f"host={PG_HOST} port={PG_PORT} dbname={PG_DB} "
    f"user={PG_USER} password={PG_PASSWORD}"
)

# Pool ouvert au demarrage de l'app (voir main.py -> lifespan)
pool = ConnectionPool(conninfo=CONNINFO, min_size=1, max_size=10, open=False)


@contextmanager
def get_cursor(commit: bool = False):
    """
    Fournit un curseur psycopg (dict_row : chaque ligne -> dict) sur une
    connexion prise dans le pool. Commit automatique si `commit=True` et
    qu'aucune exception n'a ete levee ; rollback sinon.
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                yield cur
                if commit:
                    conn.commit()
            except Exception:
                conn.rollback()
                raise
