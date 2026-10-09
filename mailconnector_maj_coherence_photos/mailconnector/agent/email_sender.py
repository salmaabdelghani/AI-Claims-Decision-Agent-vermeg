"""
Module d'envoi d'emails — Reponses automatiques au client.

Deux cas geres (cf. main.py, juste apres check_required_documents) :
  1. Dossier complet (constat + photos recus)      -> email d'accuse de reception
  2. Dossier incomplet (constat et/ou photos manquants) -> email de demande de complement

Les emails sont envoyes EN REPONSE au message original (In-Reply-To / References)
afin qu'ils s'inserent dans le meme fil de discussion chez le client.
"""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr

logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self, smtp_host: str, username: str, password: str,
                 port: int = 587, use_tls: bool = True, display_name: str = "Service Sinistres"):
        self.smtp_host = smtp_host
        self.username = username
        self.password = password
        self.port = port
        self.use_tls = use_tls
        self.display_name = display_name

    def send_reply(self, to_email_data: dict, subject: str, body: str) -> bool:
        """
        Envoie une reponse dans le meme fil que l'email original.
        to_email_data : dict issu de parse_email() (contient sender + message_id)
        """
        _, recipient_addr = parseaddr(to_email_data.get("sender", ""))
        if not recipient_addr:
            logger.error("Impossible d'extraire l'adresse du destinataire, envoi annule.")
            return False

        msg = MIMEMultipart()
        msg["From"] = formataddr((self.display_name, self.username))
        msg["To"] = recipient_addr
        msg["Subject"] = subject

        original_message_id = to_email_data.get("message_id")
        if original_message_id:
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id

        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_host, self.port, timeout=30) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.username, [recipient_addr], msg.as_string())
            logger.info(f"Email de reponse envoye a {recipient_addr} — sujet: {subject}")
            return True
        except Exception as e:
            logger.error(f"Echec envoi email a {recipient_addr}: {e}")
            return False


# ─── Templates de reponse ─────────────────────────────────────────────────────

def build_complete_reply(email_data: dict) -> tuple[str, str]:
    """Sujet + corps de l'email d'accuse de reception (dossier complet)."""
    original_subject = email_data.get("subject", "").strip()
    subject = f"Re: {original_subject}" if original_subject else "Re: Declaration de sinistre"

    body = (
        "Bonjour,\n\n"
        "Nous accusons reception de votre declaration de sinistre.\n\n"
        "Le constat amiable ainsi que les photos des dommages ont bien ete recus "
        "et sont en cours de traitement par nos services.\n\n"
        "Nous reviendrons vers vous si des informations ou documents "
        "complementaires sont necessaires.\n\n"
        "Cordialement,\n"
        "Le Service Sinistres"
    )
    return subject, body


def build_missing_documents_reply(email_data: dict, missing: list[str]) -> tuple[str, str]:
    """Sujet + corps de l'email de demande de document(s) manquant(s)."""
    original_subject = email_data.get("subject", "").strip()
    subject = f"Re: {original_subject}" if original_subject else "Re: Declaration de sinistre"

    docs = " et ".join(missing)
    body = (
        "Bonjour,\n\n"
        "Nous avons bien recu votre declaration de sinistre. Cependant, votre dossier "
        f"est incomplet : il manque le(s) document(s) suivant(s) : {docs}.\n\n"
        "Merci de bien vouloir nous renvoyer un email en repondant a ce message, "
        "en joignant le(s) document(s) manquant(s), afin que nous puissions "
        "poursuivre le traitement de votre dossier dans les meilleurs delais.\n\n"
        "Cordialement,\n"
        "Le Service Sinistres"
    )
    return subject, body
