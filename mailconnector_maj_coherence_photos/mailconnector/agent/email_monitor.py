"""
Agent de monitoring des emails - Declarations de sinistres.
Extrait les pieces jointes ET les images inline (CID embeds).
"""
import imaplib
import email
import email.header
import base64
import logging
from datetime import datetime
from typing import Optional
from email.message import Message

logger = logging.getLogger(__name__)


class EmailMonitor:
    def __init__(self, imap_host: str, username: str, password: str, port: int = 993):
        self.imap_host = imap_host
        self.username = username
        self.password = password
        self.port = port
        self.conn: Optional[imaplib.IMAP4_SSL] = None

    def connect(self):
        self.conn = imaplib.IMAP4_SSL(self.imap_host, self.port)
        self.conn.login(self.username, self.password)
        logger.info(f"Connecte a {self.imap_host} en tant que {self.username}")

    def disconnect(self):
        if self.conn:
            try:
                self.conn.logout()
            except Exception:
                pass

    def fetch_unread_emails(self, folder: str = "INBOX") -> list[dict]:
        if not self.conn:
            self.connect()
        self.conn.select(folder)
        _, msg_ids = self.conn.search(None, "UNSEEN")
        emails = []
        for msg_id in msg_ids[0].split():
            _, msg_data = self.conn.fetch(msg_id, "(RFC822)")
            raw_email = msg_data[0][1]
            parsed = email.message_from_bytes(raw_email)
            emails.append({"id": msg_id.decode(), "raw": raw_email, "parsed": parsed})
            logger.info(f"Email recupere ID={msg_id.decode()}")
        return emails

    def mark_as_read(self, msg_id: str):
        if self.conn:
            self.conn.store(msg_id.encode(), "+FLAGS", "\\Seen")


def parse_email(parsed_msg: Message) -> dict:
    """
    Extrait metadonnees, corps et TOUTES les images/fichiers :
    - pieces jointes explicites (Content-Disposition: attachment)
    - images inline / embedded (Content-ID, multipart/related)
    """

    def decode_header_value(value: str) -> str:
        if not value:
            return ""
        parts = email.header.decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)

    def extract_body(msg: Message) -> str:
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    if payload:
                        body += payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            if payload:
                body = payload.decode(charset, errors="replace")
        return body.strip()

    def extract_all_files(msg: Message) -> list[dict]:
        """
        Extrait TOUS les fichiers binaires de l'email :
        1. Pieces jointes (Content-Disposition: attachment)
        2. Images inline/embedded (multipart/related, Content-ID)
        Deduplique par nom de fichier.
        """
        files = []
        seen_names = set()
        inline_counter = 0

        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = part.get("Content-Disposition", "") or ""
            content_id = part.get("Content-ID", "") or ""
            payload = part.get_payload(decode=True)

            if not payload:
                continue

            # Cas 1 : piece jointe explicite
            is_attachment = "attachment" in disposition.lower()

            # Cas 2 : image inline via CID (ex: <image001.jpg@...>)
            is_inline_image = (
                "inline" in disposition.lower() or content_id
            ) and content_type.startswith("image/")

            # Cas 3 : partie image sans disposition declaree (Gmail embed)
            is_embedded = (
                not disposition
                and content_type.startswith("image/")
            )

            if not (is_attachment or is_inline_image or is_embedded):
                continue

            # Nom du fichier
            filename = decode_header_value(part.get_filename() or "")
            if not filename:
                # Genere un nom depuis le Content-ID ou un compteur
                if content_id:
                    cid_clean = content_id.strip("<>").split("@")[0]
                    ext = content_type.split("/")[-1].split(";")[0]
                    filename = f"{cid_clean}.{ext}"
                else:
                    inline_counter += 1
                    ext = content_type.split("/")[-1].split(";")[0]
                    filename = f"image_inline_{inline_counter}.{ext}"

            # Deduplique
            base_name = filename
            counter = 1
            while filename in seen_names:
                name, _, ext = base_name.rpartition(".")
                filename = f"{name}_{counter}.{ext}"
                counter += 1
            seen_names.add(filename)

            source = "attachment" if is_attachment else "inline"
            files.append({
                "filename": filename,
                "content_type": content_type,
                "source": source,          # "attachment" ou "inline"
                "content_id": content_id.strip("<>") if content_id else "",
                "data": base64.b64encode(payload).decode(),
                "size_bytes": len(payload),
            })
            logger.info(f"Fichier extrait [{source}]: {filename} ({len(payload)} octets, {content_type})")

        return files

    attachments = extract_all_files(parsed_msg)

    # Log recapitulatif
    nb_attach = sum(1 for a in attachments if a["source"] == "attachment")
    nb_inline = sum(1 for a in attachments if a["source"] == "inline")
    logger.info(f"Total fichiers: {len(attachments)} ({nb_attach} pieces jointes + {nb_inline} images inline)")

    return {
        "sender":     decode_header_value(parsed_msg.get("From", "")),
        "cc":         decode_header_value(parsed_msg.get("CC", "")),
        "bcc":        decode_header_value(parsed_msg.get("BCC", "")),
        "subject":    decode_header_value(parsed_msg.get("Subject", "")),
        "date":       parsed_msg.get("Date", datetime.now().isoformat()),
        "message_id": parsed_msg.get("Message-ID", ""),
        "body":       extract_body(parsed_msg),
        "attachments": attachments,
    }