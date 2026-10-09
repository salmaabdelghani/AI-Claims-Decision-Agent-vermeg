"""
Stockage MongoDB GridFS des pièces jointes (fichiers binaires).

Chaque fichier est stocké dans GridFS avec des métadonnées riches :
- sinistre_id (référence PostgreSQL)
- nature (CIN, constat, contrat...)
- sender, subject, date de l'email
"""
import base64
import logging
from datetime import datetime
from pymongo import MongoClient
import gridfs

logger = logging.getLogger(__name__)


class MongoGridFSStorage:

    def __init__(self, mongo_uri: str, db_name: str = "sinistres"):
        """
        mongo_uri: mongodb://user:pass@host:27017/
        db_name: nom de la base MongoDB
        """
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.client = None
        self.db = None
        self.fs = None

    def connect(self):
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.db_name]
        self.fs = gridfs.GridFS(self.db, collection="pieces_jointes")
        logger.info(f"MongoDB connecté — base: {self.db_name}")

    def store_attachments(
        self,
        attachments: list[dict],
        sinistre_id: int,
        email_data: dict,
    ) -> list[str]:
        """
        Stocke les pièces jointes dans GridFS.
        Retourne la liste des ObjectId (str) créés.
        """
        object_ids = []

        for att in attachments:
            raw_data = base64.b64decode(att.get("data", ""))
            if not raw_data:
                continue

            metadata = {
                "sinistre_id": sinistre_id,
                "original_filename": att.get("filename"),
                "content_type": att.get("content_type"),
                "file_format": att.get("classified_type"),
                "nature": att.get("nature"),
                "size_bytes": att.get("size_bytes", 0),
                # Contexte email
                "email_sender": email_data.get("sender"),
                "email_subject": email_data.get("subject"),
                "email_date": email_data.get("date"),
                "uploaded_at": datetime.utcnow(),
            }

            file_id = self.fs.put(
                raw_data,
                filename=att.get("filename"),
                **metadata,
            )

            str_id = str(file_id)
            object_ids.append(str_id)
            logger.info(
                f"Fichier stocké GridFS: {att['filename']} → {str_id} "
                f"(nature: {att.get('nature')})"
            )

        return object_ids

    def get_attachment(self, gridfs_id: str) -> bytes:
        """Récupère le binaire d'une pièce jointe depuis GridFS."""
        from bson import ObjectId
        grid_out = self.fs.get(ObjectId(gridfs_id))
        return grid_out.read()

    def list_attachments_for_sinistre(self, sinistre_id: int) -> list[dict]:
        """Liste les métadonnées de toutes les PJ d'un sinistre."""
        cursor = self.db["pieces_jointes.files"].find(
            {"metadata.sinistre_id": sinistre_id},
            {"filename": 1, "metadata": 1, "length": 1, "uploadDate": 1},
        )
        return [
            {
                "gridfs_id": str(doc["_id"]),
                "filename": doc.get("filename"),
                "nature": doc.get("metadata", {}).get("nature"),
                "file_format": doc.get("metadata", {}).get("file_format"),
                "size_bytes": doc.get("length", 0),
                "upload_date": doc.get("uploadDate"),
            }
            for doc in cursor
        ]

    def close(self):
        if self.client:
            self.client.close()
