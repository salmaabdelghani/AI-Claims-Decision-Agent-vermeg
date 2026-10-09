"""
Sert les pieces jointes (constats scannes, photos de dommages) stockees par
l'agent mailconnector dans MongoDB GridFS — utilise par la fiche Sinistre et
le dashboard Agent pour afficher les documents originaux.
"""
import io
import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import mongo
from app.database import get_cursor

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/{gridfs_id}")
def get_document(gridfs_id: str, download: bool = False):
    with get_cursor() as cur:
        cur.execute("SELECT filename FROM sinistre_documents WHERE gridfs_id = %s LIMIT 1", (gridfs_id,))
        row = cur.fetchone()
    filename = (row or {}).get("filename") or "document"

    data = mongo.get_attachment(gridfs_id)
    if data is None:
        raise HTTPException(404, "Document introuvable (MongoDB indisponible ou fichier absent)")

    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    headers = {"Content-Disposition": f'{"attachment" if download else "inline"}; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(data), media_type=media_type, headers=headers)
