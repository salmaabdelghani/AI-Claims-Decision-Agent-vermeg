"""
Connexion MongoDB GridFS (lecture seule) — meme base que celle utilisee par
l'agent mailconnector pour stocker les pieces jointes (constats, photos de
dommages). Permet au dashboard Agent et a la fiche Sinistre du front
assurantia d'afficher ces documents sans dupliquer leur contenu en Postgres.
"""
import os

import gridfs
from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "sinistres")

_client: MongoClient | None = None
_fs: gridfs.GridFS | None = None


def connect():
    global _client, _fs
    _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    _fs = gridfs.GridFS(_client[MONGO_DB], collection="pieces_jointes")


def close():
    global _client
    if _client:
        _client.close()


def get_attachment(gridfs_id: str) -> bytes | None:
    """Renvoie le contenu binaire d'une piece jointe, ou None si absente/Mongo indisponible."""
    if _fs is None or not gridfs_id:
        return None
    try:
        from bson import ObjectId
        return _fs.get(ObjectId(gridfs_id)).read()
    except Exception:
        return None


def put_attachment(filename: str, content_type: str, data: bytes) -> str | None:
    """
    Stocke un nouveau fichier dans GridFS (ex: photo de dommages ajoutee par
    un gestionnaire depuis le dashboard Agent, avant confirmation du
    dossier). Renvoie l'id GridFS (str) ou None si Mongo indisponible.
    """
    if _fs is None:
        return None
    try:
        return str(_fs.put(data, filename=filename, content_type=content_type))
    except Exception:
        return None
